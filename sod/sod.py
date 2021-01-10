import click
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
import glob
import hashlib
import logging
import os
import pygit2
import re
import shlex
import shutil
import stat as stat_m
import subprocess
import sys
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SOD_DIR = '.sod'
SODIGNORE_FILE = '.sodignore'
FAKE_SIGNATURE = pygit2.Signature('sod', 'sod@localhost')
BLOCK_SIZE = 65536
HASH_ALGORITHM = 'sha1'
HEXDIGEST_SIZE = hashlib.new(HASH_ALGORITHM).digest_size * 2
HEXDIGEST_ABBREV_SIZE = 10
ATTR_DIGEST = 'user.sod.digest'
ATTR_DIGEST_VERSION = 1
SKIP_TREE_NAMES = {'.snapshots', SOD_DIR}
SKIP_TREE_FLAGS = {'.git', '.svn', SODIGNORE_FILE}
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

DELTA_STATUS_NAME = {
    pygit2.GIT_DELTA_UNMODIFIED: 'unmodified',
    pygit2.GIT_DELTA_ADDED: 'added',
    pygit2.GIT_DELTA_DELETED: 'deleted',
    pygit2.GIT_DELTA_MODIFIED: 'modified',
    pygit2.GIT_DELTA_RENAMED: 'renamed',
    pygit2.GIT_DELTA_COPIED: 'copied',
    pygit2.GIT_DELTA_IGNORED: 'ignored',
    pygit2.GIT_DELTA_UNTRACKED: 'untracked',
    pygit2.GIT_DELTA_TYPECHANGE: 'type-changed',
    pygit2.GIT_DELTA_UNREADABLE: 'unreadable',
    pygit2.GIT_DELTA_CONFLICTED: 'conflicted',
}
DELTA_STATUS_MAX_LENGTH = max([len(name) for name in DELTA_STATUS_NAME.values()])

def init_logging(debug=False):
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d [%(name)s] %(message)s',
                                  datefmt='%H:%M:%S')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    if debug:
        handler.setLevel(logging.DEBUG)
        root_logger.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

def hash_file(path):
    hasher = hashlib.new(HASH_ALGORITHM)
    try:
        with open(path, 'rb') as f:
            block = f.read(BLOCK_SIZE)
            while len(block) > 0:
                hasher.update(block)
                block = f.read(BLOCK_SIZE)
    except:
        return '0' * HEXDIGEST_SIZE
    return hasher.hexdigest()

@contextmanager
def temporarily_writable(path, stat=None):
    if not stat:
        stat = os.stat(path)

    was_writable = stat.st_mode & stat_m.S_IWUSR
    if not was_writable:
        try:
            os.chmod(path, stat.st_mode | stat_m.S_IWUSR)
        except:
            logger.debug('Failed to temprarily make file writable %s', path)
            pass

    try:
        yield
    finally:
        if not was_writable:
            try:
                os.chmod(path, stat.st_mode)
            except:
                logger.debug('Failed to restore permissions for %s', path)
                pass


def digest_for(path, rehash=False):
    stat = os.stat(path)

    digest = None

    if not rehash:
        try:
            cached_digest = os.getxattr(path, ATTR_DIGEST)
            version, timestamp, algorithm, digest = cached_digest.decode().split(':')
        except:
            pass
        else:
            if int(version) != ATTR_DIGEST_VERSION or algorithm != HASH_ALGORITHM:
                logger.debug('Found incompatible cached digest for %s', path)
                digest = None
            elif int(timestamp) < stat.st_mtime_ns:
                logger.debug('Found outdated cached digest for %s', path)
                digest = None
            else:
                logger.debug('Found valid cached digest for %s', path)

    if not digest:
        logger.debug('Computing digest for %s', path)
        digest = hash_file(path)
        cached_digest = ':'.join([str(ATTR_DIGEST_VERSION), str(stat.st_mtime_ns), HASH_ALGORITHM,
            digest])

        with temporarily_writable(path, stat=stat):
            try:
                os.setxattr(path, ATTR_DIGEST, cached_digest.encode())
            except:
                logger.debug('Failed to cache digest for %s', path)
                pass

    return digest

def walk_bottom_up(top, skip_tree_names, skip_tree_flags):
    dirs = []
    files = []
    symlinks = []

    try:
        it = os.scandir(top)
    except OSError as e:
        logger.error('scandir() failed: %s', e)
        yield top, [], [], []
        return

    with it:
        while True:
            try:
                try:
                    entry = next(it)
                except StopIteration:
                    break
            except OSError as e:
                logger.error('next() failed: %s', e)
                yield top, [], [], []
                return

            if entry.name in skip_tree_flags:
                yield top, [], [], []
                return

            try:
                if entry.is_symlink():
                    symlinks.append(entry.name)
                elif entry.is_dir():
                    if entry.name not in skip_tree_names:
                        dirs.append(entry.name)
                else:
                    files.append(entry.name)
            except OSError:
                # Similarly os.path.isdir() and os.path.islink() do
                files.append(entry.name)

    for subdir in dirs:
        yield from walk_bottom_up(os.path.join(top, subdir), skip_tree_names, skip_tree_flags)
    yield top, dirs, files, symlinks

def find_upward(path, name, test=os.path.exists):
    current = path
    while current != os.path.dirname(current) \
            and not test(os.path.join(current, name)):
        current = os.path.dirname(current)

    if current == os.path.dirname(current):
        return None
    else:
        return current

def format_path_change(old_path, new_path):
    common_prefix = os.path.commonpath([old_path, new_path])
    if common_prefix:
        common_prefix += os.path.sep
    old_unique = old_path[len(common_prefix):]
    new_unique = new_path[len(common_prefix):]
    common_suffix = ''
    while True:
        old_unique_h, old_unique_t = os.path.split(old_unique)
        new_unique_h, new_unique_t = os.path.split(new_unique)
        if old_unique_t != new_unique_t:
            break
        common_suffix = os.path.join(old_unique_t, common_suffix)
        old_unique = old_unique_h
        new_unique = new_unique_h

    if common_prefix or common_suffix:
        retv = os.path.join(common_prefix,
                '{' + old_unique + ' -> ' + new_unique + '}',
                common_suffix)
        retv = retv.rstrip(os.path.sep)
    else:
        retv = old_path + ' -> ' + new_path

    return retv

class Error(Exception):
    pass

class Repository:
    def __init__(self, path):
        self.path = path
        self.git = pygit2.Repository(os.path.join(self.path, SOD_DIR))
        self.snapshot_groups = SnapshotGroups(self)
        self.snapshots = Snapshots(self)
        self.EMPTY_TREE_OID = self.git.TreeBuilder().write()

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

    def _tree_build(self, top_dir, rehash=False):
        trees = {}

        for root, dirs, files, symlinks in walk_bottom_up(top_dir, SKIP_TREE_NAMES, SKIP_TREE_FLAGS):
            item_count = 0
            builder = self.git.TreeBuilder()
            for name in dirs:
                oid = trees.pop(os.path.join(root, name))
                if not oid:
                    continue
                builder.insert(name, oid, pygit2.GIT_FILEMODE_TREE)
                item_count += 1
            for name in files:
                digest = digest_for(os.path.join(root, name), rehash)
                oid = self.git.create_blob((digest + '\n').encode())
                builder.insert(name, oid, pygit2.GIT_FILEMODE_BLOB)
                item_count += 1
            for name in symlinks:
                try:
                    target = os.readlink(os.path.join(root, name))
                except OSError as e:
                    logger.warning('Failed to read symlink: %s: %s', os.path.join(root, name), e)
                    continue
                oid = self.git.create_blob(target)
                builder.insert(name, oid, pygit2.GIT_FILEMODE_LINK)
                item_count += 1

            if item_count > 0:
                trees[root] = builder.write()
            else:
                trees[root] = self.EMPTY_TREE_OID

        assert len(trees) == 1
        assert top_dir in trees

        return trees.pop(top_dir)

    def add(self, paths=[]):
        if not paths:
            tmp_tree_oid = self._tree_build(self.path)
            self.git.index.read_tree(tmp_tree_oid)
        else:
            for path in paths:
                self._index_add(self.git.index, path)

        self.git.index.write()

    def _index_add(self, index, path, rehash=False):
        if os.path.islink(path):
            try:
                target = os.readlink(path)
            except OSError as e:
                logger.warning('Failed to read symlink: %s: %s', path, e)
                return
            oid = self.git.create_blob(target)
            index.add(pygit2.IndexEntry(path, oid, pygit2.GIT_FILEMODE_LINK))
        elif os.path.isdir(path):
            index.remove_all([path])
            oid = self._tree_build(path, rehash)
            self._index_add_tree(index, path, self.git.get(oid))
        elif os.path.isfile(path):
            digest = digest_for(path, rehash)
            oid = self.git.create_blob((digest + '\n').encode())
            index.add(pygit2.IndexEntry(path, oid, pygit2.GIT_FILEMODE_BLOB))
        else:
            index.remove_all([path])

    def _index_add_tree(self, index, path, tree):
        for item in tree:
            item_path = os.path.join(path, item.name)
            if item.filemode != pygit2.GIT_FILEMODE_TREE:
                index.add(pygit2.IndexEntry(item_path, item.id, item.filemode))
            else:
                self._index_add_tree(index, item_path, self.git.get(item.id))

    def _index_add_object(self, index, path, obj):
        if obj.filemode != pygit2.GIT_FILEMODE_TREE:
            index.add(pygit2.IndexEntry(path, obj.id, obj.filemode))
        else:
            self._index_add_tree(index, path, obj)

    def reset(self, paths=[]):
        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            head = None

        if head:
            head_tree = head.tree
        else:
            head_tree = self.git.get(self.EMPTY_TREE_OID)

        if not paths:
            self.git.index.read_tree(head_tree)
        else:
            for path in paths:
                self._index_reset_path(self.git.index, path, head_tree)

        self.git.index.write()

    def _index_reset_path(self, index, path, tree):
        index.remove_all([path])

        try:
            obj = tree[path]
        except KeyError:
            return

        if obj.filemode == pygit2.GIT_FILEMODE_TREE:
            self._index_add_tree(index, path, obj)
        else:
            index.add(pygit2.IndexEntry(path, obj.oid, obj.filemode))

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
                empty_tree = self.git.get(self.EMPTY_TREE_OID)
                diff = self.git.index.diff_to_tree(empty_tree)
        else:
            if head:
                old_tree = head.tree
            else:
                old_tree = self.git.get(self.EMPTY_TREE_OID)

            new_tree = self.git.get(self.git.index.write_tree())

            old_tree = self._tree_filter(old_tree, paths)
            new_tree = self._tree_filter(new_tree, paths)

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
            old_tree = self._tree_filter(old_tree, paths)

            new_index = pygit2.Index()
            for path in paths:
                self._index_add(new_index, path, rehash)
            new_tree = self.git.get(new_index.write_tree(self.git))

            diff = old_tree.diff_to_tree(new_tree, flags=DIFF_FLAGS)
            diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS)

        return diff

    def _tree_filter(self, tree, paths):
        index = pygit2.Index()

        for path in paths:
            try:
                obj = tree[path]
            except KeyError as e:
                pass
            else:
                self._index_add_object(index, path, obj)

        return self.git.get(index.write_tree(self.git))

    def format_diff(self, git_diff, abbreviate=True):
        for delta in git_diff.deltas:
            if delta.old_file.path == delta.new_file.path:
                path_info = delta.old_file.path
            else:
                path_info = format_path_change(delta.old_file.path, delta.new_file.path)

            if delta.similarity != 100 and delta.status != pygit2.GIT_DELTA_ADDED:
                old_blob = self.git.get(delta.old_file.id)
                old_digest = old_blob.data.decode().strip()
            else:
                old_digest = '-'

            digest_size = [HEXDIGEST_SIZE, HEXDIGEST_ABBREV_SIZE][abbreviate]

            yield '  {status:{status_w}}  {old_digest:{digest_w}}  {path_info}\n'.format(
                status=DELTA_STATUS_NAME[delta.status] + ':',
                status_w=DELTA_STATUS_MAX_LENGTH + 1,
                old_digest=old_digest[0:digest_size],
                digest_w=digest_size,
                path_info=path_info)

    def _snapshots_by_oid(self):
        snapshots = defaultdict(lambda: [])

        for snapshot in self.snapshots:
            obj = self.git.references[snapshot.reference].peel()
            snapshots[obj.id].append(snapshot)

        return snapshots

    def format_log(self, oid, abbreviate=False):
        snapshots = self._snapshots_by_oid()

        head_obj = self.git.references['HEAD'].peel()

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

            refs = []
            if matching_snapshots:
                refs = [snapshot.shorthand_reference for snapshot in matching_snapshots]
            if commit.id == head_obj.id:
                refs.insert(0, 'HEAD')

            if refs:
                decoration = ' (' + ', '.join(refs) + ')'
            else:
                decoration = ''

            yield 'commit {}{}\n'.format(commit.id, decoration)
            yield 'Date: {:%c}\n'.format(datetime.fromtimestamp(commit.commit_time))
            yield '\n'
            yield '    {}\n'.format(commit.message)
            yield '\n'
            yield from self.format_diff(diff, abbreviate=abbreviate)
            yield '\n'

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

    def format_snapshot_list(self):
        for group in self.snapshot_groups:
            yield group.name + '  ' + group.url_pattern + '\n'

    def restore(self, path, refish, snapshot_name):
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

            ancestor_path = self._find_object(ancestor.tree, obj.id, path_hint=path)
            if ancestor_path:
                for snapshot in snapshots_by_oid[ancestor.id]:
                    matching_snapshots.append((snapshot, ancestor_path))

        if not matching_snapshots:
            raise Error('No snapshot seems to contain the file in the desired revision')

        excluded_snapshots = []
        restored = False

        for snapshot, ancestor_path in matching_snapshots:
            if snapshot_name and snapshot.group_name != snapshot_name:
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

    def _find_object(self, tree, oid, path_hint):
        if path_hint:
            try:
                obj = tree[path_hint]
            except KeyError:
                pass
            if obj.id == oid:
                return path_hint

        for obj in tree:
            if obj.type == pygit2.GIT_FILEMODE_TREE:
                path = self._find(obj, oid, None)
                if path:
                    return obj.name + '/' + path
            elif obj.id == oid:
                return obj.name

        return None

class SnapshotGroups:
    def __init__(self, repository):
        self._repository = repository

    def __contains__(self, name):
        return self._url_pattern_config_key(name) in self._repository.git.config

    def __getitem__(self, name):
        try:
            url_pattern = self._repository.git.config[self._url_pattern_config_key(name)]
        except KeyError:
            raise KeyError(name)
        return SnapshotGroup(self._repository, name, url_pattern)

    def __iter__(self):
        pattern = re.compile('^sod-snapshot\.([^.]+)\.url-pattern$')
        for item in self._repository.git.config:
            match = pattern.search(item.name)
            if not match:
                continue
            name = match.group(1)
            url_pattern = item.value
            yield SnapshotGroup(self._repository, name, url_pattern)

    def create(self, name, url_pattern):
        if '/' in name:
            raise Error('Snapshot name may not contain slashes')
        if name in self:
            raise Error('Snapshot of this name already exists')
        try:
            SnapshotGroup.parse_url(url_pattern)
        except Error:
            raise
        self._repository.git.config[self._url_pattern_config_key(name)] = url_pattern

    def delete(self, name):
        try:
            group = self.__getitem__(name)
        except KeyError:
            raise Error('No such snapshot')

        group._remove_remotes()

        for key in [
                self._url_pattern_config_key(name),
                ]:
            try:
                del self._repository.git.config[key]
            except KeyError:
                continue

    def fetch(self, names):
        if not names:
            groups = list(self.__iter__())
        else:
            groups = filter(lambda g: g.name in names, self.__iter__())

        for group in groups:
            group.fetch()

    def _url_pattern_config_key(self, name):
        return 'sod-snapshot.{}.url-pattern'.format(name)

class SnapshotGroup:
    def __init__(self, repository, name, url_pattern):
        self._repository = repository
        self._name = name
        self._url_pattern = url_pattern

    @property
    def name(self):
        return self._name

    @property
    def url_pattern(self):
        return self._url_pattern

    def fetch(self):
        self._remove_remotes()

        for snapshot in self._expand():
            self._repository.git.remotes.create(snapshot.name, snapshot.url + '/' + SOD_DIR,
                    'HEAD:' + snapshot.reference)
            snapshot.fetch()

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

    def _expand(self):
        scheme, netloc, path_pattern = self.parse_url(self._url_pattern)
        if '*' not in path_pattern:
            yield Snapshot(self._repository, self._name, None)
            return

        # Only match directories which look like sod repositories
        path_pattern += '/' + SOD_DIR

        prefix, suffix = path_pattern.split('*', maxsplit=1)

        matching_paths = []
        if scheme == 'file':
            matching_paths = glob.glob(path_pattern)
        elif scheme == 'ssh':
            remote_command = 'ls -d --quoting-style=shell {}*{}'.format(
                    shlex.quote(prefix), shlex.quote(suffix))
            result = subprocess.run(['ssh', netloc, remote_command], capture_output=True)
            if result.returncode != 0:
                raise Error('Failed to list remote snapshots: ' + result.stderr.decode())
            matching_paths = shlex.split(result.stdout.decode())
        else:
            assert False

        for path in matching_paths:
            key = path[len(prefix):-len(suffix)]
            yield Snapshot(self._repository, self._name, key)

class Snapshots:
    def __init__(self, repository):
        self._repository = repository

    def __getitem__(self, name):
        group_name, key = self._split_name(name)
        snapshot = Snapshot(self._repository, group_name, key)
        if snapshot.reference not in self._repository.git.references:
            raise KeyError(name)
        return snapshot

    def __iter__(self):
        for ref_name in self._repository.git.references:
            if not ref_name.startswith(SNAPSHOT_REF_PREFIX):
                continue
            name = ref_name[len(SNAPSHOT_REF_PREFIX):]
            group_name, key = self._split_name(name)
            yield Snapshot(self._repository, group_name, key)

    def _split_name(self, name):
        try:
            group_name, key = name.split('/', maxsplit=1)
        except ValueError:
            key = None
        return (group_name, key)

class Snapshot:
    def __init__(self, repository, group_name, key):
        self._repository = repository
        self._group_name = group_name
        self._key = key

    @property
    def name(self):
        retv = self._group_name
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
        url = self._repository.snapshot_groups[self._group_name].url_pattern
        assert '*' not in url or self._key
        if self._key:
            url = url.replace('*', self._key, 1)
        return url

    def fetch(self):
        logger.info('Fetching %s', self.name)
        result = subprocess.run(['git', '--git-dir', self._repository.git.path, 'fetch', self.name],
            capture_output=True)
        if result.returncode != 0:
            raise Error('Failed to fetch ' + self.name + ': ' + result.stderr.decode())

    def restore(self, path, destination_path):
        self._download(self.url + '/' + path, destination_path)

    def _download(self, url, destination_path):
        scheme, netloc, path = SnapshotGroup.parse_url(url)
        if not scheme or scheme == 'file':
            assert not netloc
            try:
                shutil.copyfile(path, destination_path, follow_symlinks=False)
            except Exception as e:
                raise Error('Failed to copy file: ' + str(e))
        elif scheme == 'ssh':
            result = subprocess.run(['scp', netloc + ':' + path, destination_path])
            if result.returncode != 0:
                raise Error('Download failed: ' + result.stderr.decode())
        else:
            assert False

class ErrorHandlingGroup(click.Group):
    def __call__(self, *args, **kwargs):
        try:
            super().__call__(*args, **kwargs)
        except Error as e:
            click.ClickException(e).show()
            sys.exit(1)

class DiscoveredRepository(Repository):
    def __init__(self):
        root_dir = find_upward(os.getcwd(), SOD_DIR, test=os.path.isdir)
        if not root_dir:
            raise click.ClickException('Not a sod repository')

        super().__init__(root_dir)

pass_repository = click.make_pass_decorator(DiscoveredRepository, ensure=True)

@click.group(cls=ErrorHandlingGroup)
@click.option('--debug', is_flag=True, help='Enable debugging output')
def cli(debug):
    init_logging(debug=debug)

@cli.command()
def init():
    Repository.initialize(os.getcwd())

@cli.command()
@click.option('--staged', is_flag=True, help='Only check the index')
@click.option('-r', '--rehash', is_flag=True, help='Do not use cached digests')
@click.option('--abbrev/--no-abbrev', default=True, help='Abbreviate old content digest')
@click.argument('path', nargs=-1)
@pass_repository
def status(repository, staged, rehash, abbrev, path):
    diff_cached = repository.diff_staged(path)

    if not staged:
        diff_not_staged = repository.diff_not_staged(path, rehash)

    click.echo('Changes staged for commit:')
    click.echo(''.join(repository.format_diff(diff_cached, abbreviate=abbrev)))

    if not staged:
        click.echo('Changes not staged for commit:')
        click.echo(''.join(repository.format_diff(diff_not_staged, abbreviate=abbrev)))

@cli.command()
@click.argument('path', nargs=-1)
@pass_repository
def add(repository, path):
    repository.add(path)

@cli.command()
@click.argument('path', nargs=-1)
@pass_repository
def reset(repository, path):
    repository.reset(path)

@cli.command()
@click.option('-m', '--message', help='Commit message')
@pass_repository
def commit(repository, message):
    repository.commit(message)

@cli.command()
@click.option('--abbrev/--no-abbrev', default=True, help='Abbreviate old content digest')
@pass_repository
def log(repository, abbrev):
    try:
        head = repository.git.head.target
    except pygit2.GitError:
        raise Error('No commit found')

    click.echo_via_pager(repository.format_log(head, abbreviate=abbrev))

@cli.group()
def snapshot():
    pass

@snapshot.command()
@pass_repository
def list(repository):
    click.echo(''.join(repository.format_snapshot_list()))

@snapshot.command()
@click.argument('name')
@click.argument('url_pattern')
@pass_repository
def add(repository, name, url_pattern):
    repository.snapshot_groups.create(name, url_pattern)

@snapshot.command()
@click.argument('name')
@pass_repository
def remove(repository, name):
    repository.snapshot_groups.delete(name)

@snapshot.command()
@click.option('--all', 'fetch_all', is_flag=True, help='Fetch all snapshots')
@click.argument('name', required=False)
@pass_repository
def fetch(repository, fetch_all, name):
    if name:
        repository.snapshot_groups.fetch([name])
    elif fetch_all:
        repository.snapshot_groups.fetch()
    else:
        raise click.UsageError('No snapshot selected')

@cli.command()
@click.argument('path')
@click.argument('ref-ish', required=False)
@click.option('--snapshot', 'snapshot', help='Restore using the given snapshot')
@pass_repository
def restore(repository, path, ref_ish, snapshot):
    repository.restore(path, ref_ish, snapshot)
