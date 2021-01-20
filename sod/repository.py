from collections import defaultdict
import glob
import logging
import os
import pygit2
import re
import shlex
import shutil
import subprocess
from urllib.parse import urlparse

from . import Error
from . import gittools
from . import hashing

logger = logging.getLogger(__name__)

SOD_DIR = '.sod'
SODIGNORE_FILE = '.sodignore'
SKIP_TREE_NAMES = {'.snapshots', SOD_DIR}
SKIP_TREE_FLAGS = {'.git', '.svn', SODIGNORE_FILE}
FAKE_SIGNATURE = pygit2.Signature('sod', 'sod@localhost')
SNAPSHOT_REF_PREFIX = 'refs/snapshots/'

DIFF_FLAGS = pygit2.GIT_DIFF_INCLUDE_UNMODIFIED
DIFF_FIND_SIMILAR_FLAGS = (
        pygit2.GIT_DIFF_FIND_RENAMES
        | pygit2.GIT_DIFF_FIND_COPIES
        | pygit2.GIT_DIFF_FIND_COPIES_FROM_UNMODIFIED
        | pygit2.GIT_DIFF_FIND_EXACT_MATCH_ONLY
        | pygit2.GIT_DIFF_FIND_REMOVE_UNMODIFIED
        )

# FIXME The above flags do not work as expected. Copies are not detected,
# unmodified entries are not removed.
DIFF_FLAGS = 0
DIFF_FIND_SIMILAR_FLAGS = 0

class Repository:
    def __init__(self, path):
        self.path = path
        self.git = pygit2.Repository(os.path.join(self.path, SOD_DIR))
        self.aux_stores = AuxStores(self)
        self.snapshots = Snapshots(self)

    @staticmethod
    def initialize(path):
        if not os.path.isdir(path):
            raise Error('Not a directory: ' + path)

        git_path = os.path.join(path, SOD_DIR)
        if os.path.exists(git_path):
            raise Error('Attempt to reinitialize: ' + path)

        git = pygit2.init_repository(git_path, bare=True,
                flags=pygit2.GIT_REPOSITORY_INIT_NO_REINIT|pygit2.GIT_REPOSITORY_INIT_MKDIR)

        git.config['core.quotePath'] = False

    def _make_create_blob(self, rehash=False):
        def create_blob(git, path):
            digest = hashing.digest_for(path, rehash)
            oid = git.create_blob((digest + '\n').encode())
            return oid
        return create_blob

    def _tree_build(self, top_dir, rehash=False):
        return gittools.tree_build(self.git, top_dir, create_blob=self._make_create_blob(rehash),
                skip_tree_names=SKIP_TREE_NAMES, skip_tree_flags=SKIP_TREE_FLAGS)

    def _index_add(self, index, path, rehash=False):
        return gittools.index_add(self.git, index, path, create_blob=self._make_create_blob(rehash),
                skip_tree_names=SKIP_TREE_NAMES, skip_tree_flags=SKIP_TREE_FLAGS)

    def add(self, paths=[]):
        if not paths:
            tmp_tree_oid = self._tree_build(self.path)
            self.git.index.read_tree(tmp_tree_oid)
        else:
            for path in paths:
                self._index_add(self.git.index, path)

        self.git.index.write()

    def reset(self, paths=[]):
        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            head = None

        if head:
            head_tree = head.tree
        else:
            head_tree = gittools.empty_tree(self.git)

        if not paths:
            self.git.index.read_tree(head_tree)
        else:
            for path in paths:
                gittools.index_reset_path(self.git, self.git.index, path, head_tree)

        self.git.index.write()

    def diff_staged(self, paths=[]):
        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            head = None

        if not paths:
            if head:
                diff = self.git.index.diff_to_tree(head.tree, flags=DIFF_FLAGS)
                diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS)
            else:
                diff = self.git.index.diff_to_tree(gittools.empty_tree(self.git))
        else:
            if head:
                old_tree = head.tree
            else:
                old_tree = gittools.empty_tree(self.git)

            new_tree = self.git.get(self.git.index.write_tree())

            old_tree = gittools.tree_filter(self.git, old_tree, paths)
            new_tree = gittools.tree_filter(self.git, new_tree, paths)

            diff = old_tree.diff_to_tree(new_tree, flags=DIFF_FLAGS)
            diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS)

        return diff

    def diff_not_staged(self, paths=[], rehash=False):
        if not paths:
            tmp_tree_oid = self._tree_build(self.path, rehash)
            tmp_tree = self.git.get(tmp_tree_oid)
            diff = self.git.index.diff_to_tree(tmp_tree, flags=DIFF_FLAGS|pygit2.GIT_DIFF_REVERSE)
            diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS)
        else:
            old_tree = self.git.get(self.git.index.write_tree())
            old_tree = gittools.tree_filter(self.git, old_tree, paths)

            new_index = pygit2.Index()
            for path in paths:
                self._index_add(new_index, path, rehash)
            new_tree = self.git.get(new_index.write_tree(self.git))

            diff = old_tree.diff_to_tree(new_tree, flags=DIFF_FLAGS)
            diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS)

        return diff

    def _snapshots_by_oid(self):
        snapshots = defaultdict(lambda: [])

        for snapshot in self.snapshots:
            obj = self.git.references[snapshot.reference].peel()
            snapshots[obj.id].append(snapshot)

        return snapshots

    def log(self, oid):
        snapshots = self._snapshots_by_oid()

        for commit in self.git.walk(oid):
            if commit.parents:
                diff = commit.tree.diff_to_tree(commit.parents[0].tree, swap=True, flags=DIFF_FLAGS)
                diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS)
            else:
                diff = commit.tree.diff_to_tree(swap=True)

            try:
                matching_snapshots = snapshots[commit.id]
            except KeyError:
                pass

            yield (commit, matching_snapshots, diff)

    def commit(self, message):
        if not self.diff_staged():
            raise Error('No changes staged for commit')

        try:
            parent, ref = self.git.resolve_refish(self.git.head.name)
            parents = [parent.oid]
            ref_name = ref.name
        except pygit2.GitError:
            parents = []
            ref_name = 'refs/heads/master'

        self.git.create_commit(ref_name, FAKE_SIGNATURE, FAKE_SIGNATURE,
                message, self.git.index.write_tree(), parents)

    def restore(self, path, refish, aux_store_name):
        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            raise Error('No commit found')

        if os.path.exists(path):
            raise Error('File exists - refusing to overwrite: ' + path)

        if refish:
            try:
                snapshot = self.snapshots[refish]
            except KeyError:
                pass
            else:
                refish = snapshot.reference

            try:
                commit = self.git.resolve_refish(refish)[0]
            except pygit2.GitError:
                raise Error('Bad revision: ' + refish)
        else:
            commit = head

        try:
            obj = commit.tree[path]
        except KeyError:
            raise Error('No such file known to sod. Try different revision?')

        if obj.filemode == pygit2.GIT_FILEMODE_TREE:
            raise Error('Unsupported operation. Cannot restore directories')

        if obj.filemode == pygit2.GIT_FILEMODE_LINK:
            target = obj.data
            try:
                os.symlink(target, path)
            except OSError as e:
                raise Error('Failed to create symlink: ' + str(e))
            return

        assert obj.filemode == pygit2.GIT_FILEMODE_BLOB

        snapshots_by_oid = self._snapshots_by_oid()

        matching_snapshots = []
        for ancestor in self.git.walk(commit.id):
            if ancestor.id not in snapshots_by_oid:
                continue

            ancestor_path = gittools.find_object(ancestor.tree, obj.id, path_hint=path)
            if ancestor_path:
                for snapshot in snapshots_by_oid[ancestor.id]:
                    matching_snapshots.append((snapshot, ancestor_path))

        if not matching_snapshots:
            raise Error('No snapshot seems to contain the file in the desired revision')

        excluded_snapshots = []
        restored = False

        for snapshot, ancestor_path in matching_snapshots:
            if aux_store_name and snapshot.store_name != aux_store_name:
                excluded_snapshots.append(snapshot)
                continue

            logger.info('Trying to restore from ' + snapshot.name)
            try:
                snapshot.restore(ancestor_path, path)
            except Error as e:
                logger.warning('Failed to restore from ' + snapshot.name + ': ' + str(e))
            else:
                restored = True
                break

        if not restored:
            if excluded_snapshots:
                logger.info('Also available from the following skipped snapshots:')
                for snapshot in excluded_snapshots:
                    logger.info('  ' + snapshot.name)
            raise Error('Could not restore')

class AuxStores:
    def __init__(self, repository):
        self._repository = repository

    def __contains__(self, name):
        return self._url_config_key(name) in self._repository.git.config

    def __getitem__(self, name):
        try:
            url = self._repository.git.config[self._url_config_key(name)]
        except KeyError:
            raise KeyError(name)
        return AuxStore(self._repository, name, url)

    def __iter__(self):
        pattern = re.compile('^sod-aux-store\.([^.]+)\.url$')
        for item in self._repository.git.config:
            match = pattern.search(item.name)
            if not match:
                continue
            name = match.group(1)
            url = item.value
            yield AuxStore(self._repository, name, url)

    def create(self, name, url):
        if '/' in name:
            raise Error('Auxiliary data store name may not contain slashes')
        if name in self:
            raise Error('Auxiliary data store of this name already exists')
        try:
            AuxStore.parse_url(url)
        except Error:
            raise
        self._repository.git.config[self._url_config_key(name)] = url

    def delete(self, name):
        try:
            store = self.__getitem__(name)
        except KeyError:
            raise Error('No such auxiliary data store')

        store._remove_remotes()

        for key in [
                self._url_config_key(name),
                ]:
            try:
                del self._repository.git.config[key]
            except KeyError:
                continue

    def update(self, names):
        if not names:
            stores = list(self.__iter__())
        else:
            stores = filter(lambda s: s.name in names, self.__iter__())

        for store in stores:
            store.update()

    def _url_config_key(self, name):
        return 'sod-aux-store.{}.url'.format(name)

class AuxStore:
    def __init__(self, repository, name, url):
        self._repository = repository
        self._name = name
        self._url = url

    @property
    def name(self):
        return self._name

    @property
    def url(self):
        return self._url

    def update(self):
        self._remove_remotes()

        for snapshot in self._list():
            self._repository.git.remotes.create(snapshot.name, snapshot.url + '/' + SOD_DIR,
                    'HEAD:' + snapshot.reference)
            snapshot.update()

    @staticmethod
    def parse_url(url):
        parsed = urlparse(url)
        if parsed.params:
            raise Error('Unsupported URL: Parameters must be empty')
        if parsed.query:
            raise Error('Unsupported URL: Query must be empty')
        if parsed.fragment:
            raise Error('Unsupported URL: Fragment must be empty')
        if not parsed.path:
            raise Error('Invalid URL: No path specified')

        if not parsed.scheme or parsed.scheme == 'file':
            if parsed.netloc:
                raise Error('Invalid URL: Network location must be empty with the scheme used')
        elif parsed.scheme == 'ssh':
            if not parsed.netloc:
                raise Error('Invalid URL: Netwoek location must not be empty with the scheme used')
        else:
            raise Error('Unsupported URL: Unrecognized scheme')

        if '*' in parsed.netloc:
            raise Error('Unsupported URL: Network location must not contain \'*\'')
        if parsed.path.count('*') > 1:
            raise Error('Unsupported URL: Multiple \'*\' in path')

        return (parsed.scheme or 'file', parsed.netloc, parsed.path)

    def _remove_remotes(self):
        to_remove = []
        for remote in self._repository.git.remotes:
            if remote.name == self._name or remote.name.startswith(self._name + '/'):
                to_remove.append(remote.name)
        for name in to_remove:
            self._repository.git.remotes.delete(name)

    def _list(self):
        scheme, netloc, path = self.parse_url(self._url)
        if '*' not in path:
            yield Snapshot(self._repository, self._name, None)
            return

        # Only match directories which look like sod repositories
        path += '/' + SOD_DIR

        prefix, suffix = path.split('*', maxsplit=1)

        matching_paths = []
        if scheme == 'file':
            matching_paths = glob.glob(path)
        elif scheme == 'ssh':
            remote_command = 'ls -d --quoting-style=shell {}*{}'.format(
                    shlex.quote(prefix), shlex.quote(suffix))
            result = subprocess.run(['ssh', netloc, remote_command], capture_output=True)
            if result.returncode != 0:
                raise Error('Failed to list snapshots: ' + result.stderr.decode())
            matching_paths = shlex.split(result.stdout.decode())
        else:
            assert False

        for matching_path in matching_paths:
            key = matching_path[len(prefix):-len(suffix)]
            yield Snapshot(self._repository, self._name, key)

class Snapshots:
    def __init__(self, repository):
        self._repository = repository

    def __getitem__(self, name):
        store_name, key = self._split_name(name)
        snapshot = Snapshot(self._repository, store_name, key)
        if snapshot.reference not in self._repository.git.references:
            raise KeyError(name)
        return snapshot

    def __iter__(self):
        for ref_name in self._repository.git.references:
            if not ref_name.startswith(SNAPSHOT_REF_PREFIX):
                continue
            name = ref_name[len(SNAPSHOT_REF_PREFIX):]
            store_name, key = self._split_name(name)
            yield Snapshot(self._repository, store_name, key)

    def _split_name(self, name):
        try:
            store_name, key = name.split('/', maxsplit=1)
        except ValueError:
            key = None
        return (store_name, key)

class Snapshot:
    def __init__(self, repository, store_name, key):
        self._repository = repository
        self._store_name = store_name
        # TODO rename, not a "name", maybe "id"
        self._key = key

    @property
    def name(self):
        retv = self._store_name
        if self._key:
            retv += '/' + self._key
        return retv

    @property
    def reference(self):
        return SNAPSHOT_REF_PREFIX + self.shorthand_reference

    @property
    def shorthand_reference(self):
        return self.name

    @property
    def url(self):
        url = self._repository.aux_stores[self._store_name].url
        assert '*' not in url or self._key
        if self._key:
            url = url.replace('*', self._key, 1)
        return url

    def update(self):
        logger.info('Updating %s', self.name)
        result = subprocess.run(['git', '--git-dir', self._repository.git.path, 'fetch', self.name],
            capture_output=True)
        if result.returncode != 0:
            raise Error('Failed to update ' + self.name + ': ' + result.stderr.decode())

    def restore(self, path, destination_path):
        self._download(self.url + '/' + path, destination_path)

    def _download(self, url, destination_path):
        scheme, netloc, path = AuxStore.parse_url(url)
        if not scheme or scheme == 'file':
            assert not netloc
            try:
                shutil.copyfile(path, destination_path, follow_symlinks=False)
            except Exception as e:
                raise Error('Failed to copy file: ' + str(e))
        elif scheme == 'ssh':
            result = subprocess.run(['scp', netloc + ':' + path, destination_path])
            if result.returncode != 0:
                raise Error('Download failed')
        else:
            assert False
