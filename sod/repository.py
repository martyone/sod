# This file is part of sod.
#
# Copyright (C) 2024 Martin Kampas <martin.kampas@ubedi.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from functools import partial
import logging
import os
from os.path import isabs
import pygit2
import re
import subprocess

from . import Error
from . import gittools
from . import hashing

logger = logging.getLogger(__name__)

SOD_DIR = '.sod'
SODIGNORE_FILE = '.sodignore'
SKIP_TREE_NAMES = {'.snapshots', SOD_DIR}
SKIP_TREE_FLAGS = {'.git', '.svn', SODIGNORE_FILE}
COMMIT_DATE_ENV_VAR = 'SOD_COMMIT_DATE'
FAKE_SIGNATURE_NAME = 'sod'
FAKE_SIGNATURE_EMAIL = 'sod@localhost'
SNAPSHOT_REF_PREFIX = 'refs/snapshots/'

CONFIG_PREFIX = 'sod-config.'
CONFIG_OPTION_SNAPSHOT_COMMAND = 'snapshot.command'
CONFIG_OPTIONS = [
    CONFIG_OPTION_SNAPSHOT_COMMAND
    ]

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

DIFF_RENAME_LIMIT = 10000

class Repository:
    def __init__(self, path):
        assert isabs(path)
        self.path = path
        self.git = pygit2.Repository(os.path.join(self.path, SOD_DIR))
        self.aux_stores = AuxStores(self)

    @staticmethod
    def initialize(path):
        assert isabs(path)

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
            assert isabs(path)
            digest = hashing.digest_for(path, rehash)
            oid = git.create_blob((digest + '\n').encode())
            return oid
        return create_blob

    def _tree_build(self, top_dir, rehash=False):
        return gittools.tree_build(self.git, top_dir, create_blob=self._make_create_blob(rehash),
                skip_tree_names=SKIP_TREE_NAMES, skip_tree_flags=SKIP_TREE_FLAGS)

    def _index_add(self, index, path, rehash=False):
        assert isabs(path)
        return gittools.index_add(self.git, index, self.path, path,
                create_blob=self._make_create_blob(rehash),
                skip_tree_names=SKIP_TREE_NAMES, skip_tree_flags=SKIP_TREE_FLAGS)

    def _resolve_refish(self, refish):
        snapshots = self._snapshots_by_reference()

        try:
            snapshot = snapshots[refish]
        except KeyError:
            pass
        else:
            refish = str(snapshot.base_commit_id)

        try:
            return self.git.resolve_refish(refish)[0]
        except pygit2.GitError:
            raise Error('Bad revision: ' + refish)

    def add(self, paths=[]):
        assert all(map(isabs, paths))

        if not paths:
            tmp_tree_oid = self._tree_build(self.path)
            self.git.index.read_tree(tmp_tree_oid)
        else:
            paths = tuple(filter(lambda path: not self._is_ignored(path), paths))

            for path in paths:
                self._index_add(self.git.index, path)

        self.git.index.write()

    def reset(self, paths=[]):
        assert all(map(isabs, paths))

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
            paths = tuple(filter(lambda path: not self._is_ignored(path), paths))

            for path in paths:
                relpath = os.path.relpath(path, self.path)
                gittools.index_reset_path(self.git, self.git.index, relpath, head_tree)

        self.git.index.write()

    def diff(self, old_refish, new_refish):
        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            raise Error('No commit found')

        old_commit = self._resolve_refish(old_refish)
        if new_refish:
            new_commit = self._resolve_refish(new_refish)
        else:
            new_commit = head

        diff = old_commit.tree.diff_to_tree(new_commit.tree, flags=DIFF_FLAGS)
        diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS, rename_limit=DIFF_RENAME_LIMIT)

        return diff

    def diff_staged(self, paths=[]):
        assert all(map(isabs, paths))

        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            head = None

        if not paths:
            if head:
                diff = self.git.index.diff_to_tree(head.tree, flags=DIFF_FLAGS)
                diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS, rename_limit=DIFF_RENAME_LIMIT)
            else:
                diff = self.git.index.diff_to_tree(gittools.empty_tree(self.git))
        else:
            paths = tuple(filter(lambda path: not self._is_ignored(path), paths))

            if head:
                old_tree = head.tree
            else:
                old_tree = gittools.empty_tree(self.git)

            new_tree = self.git.get(self.git.index.write_tree())

            relpaths = tuple(map(partial(os.path.relpath, start=self.path), paths))

            old_tree = gittools.tree_filter(self.git, old_tree, relpaths)
            new_tree = gittools.tree_filter(self.git, new_tree, relpaths)

            diff = old_tree.diff_to_tree(new_tree, flags=DIFF_FLAGS)
            diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS, rename_limit=DIFF_RENAME_LIMIT)

        return diff

    def diff_not_staged(self, paths=[], rehash=False):
        assert all(map(isabs, paths))

        if not paths:
            tmp_tree_oid = self._tree_build(self.path, rehash)
            tmp_tree = self.git.get(tmp_tree_oid)
            diff = self.git.index.diff_to_tree(tmp_tree, flags=DIFF_FLAGS|pygit2.GIT_DIFF_REVERSE)
            diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS, rename_limit=DIFF_RENAME_LIMIT)
        else:
            paths = tuple(filter(lambda path: not self._is_ignored(path), paths))

            relpaths = tuple(map(partial(os.path.relpath, start=self.path), paths))

            old_tree = self.git.get(self.git.index.write_tree())
            old_tree = gittools.tree_filter(self.git, old_tree, relpaths)

            new_index = pygit2.Index()
            for path in paths:
                self._index_add(new_index, path, rehash)
            new_tree = self.git.get(new_index.write_tree(self.git))

            diff = old_tree.diff_to_tree(new_tree, flags=DIFF_FLAGS)
            diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS, rename_limit=DIFF_RENAME_LIMIT)

        return diff

    def ignored_paths(self, paths=[]):
        assert all(map(isabs, paths))

        if not paths:
            return list(self._ignored_paths(self.path))
        else:
            all_ignored = set()

            for path in paths:
                if self._is_ignored(path):
                    all_ignored.add(os.path.relpath(path, self.path))
                elif os.path.isdir(path):
                    all_ignored.update(self._ignored_paths(path))

            return list(all_ignored)

    def _ignored_paths(self, path):
        assert isabs(path)

        for root, dirs, files in os.walk(path):
            for ignored in SKIP_TREE_NAMES.intersection(dirs):
                if ignored == SOD_DIR:
                    continue
                yield os.path.relpath(os.path.join(root, ignored), self.path)
            if SKIP_TREE_FLAGS.intersection(files):
                dirs.clear()
                yield os.path.relpath(root, self.path)

    def _is_ignored(self, path):
        assert isabs(path)

        while path != self.path and os.path.dirname(path) != path:
            basename = os.path.basename(path)
            if basename != SOD_DIR and basename in SKIP_TREE_NAMES:
                return True
            for flag in SKIP_TREE_FLAGS:
                if os.path.exists(os.path.join(path, flag)):
                    return True
            path = os.path.dirname(path)

        return False

    def _snapshots_by_base_commit_id(self):
        snapshots = defaultdict(lambda: [])

        for store in self.aux_stores:
            for snapshot in store.snapshots:
                snapshots[snapshot.base_commit_id].append(snapshot)

        return snapshots

    def _snapshots_by_reference(self):
        snapshots = {}

        for store in self.aux_stores:
            for snapshot in store.snapshots:
                snapshots[snapshot.reference] = snapshot

        return snapshots

    def log(self, oid):
        snapshots = self._snapshots_by_base_commit_id()

        for commit in self.git.walk(oid):
            if commit.parents:
                diff = commit.tree.diff_to_tree(commit.parents[0].tree, swap=True, flags=DIFF_FLAGS)
                diff.find_similar(flags=DIFF_FIND_SIMILAR_FLAGS, rename_limit=DIFF_RENAME_LIMIT)
            else:
                diff = commit.tree.diff_to_tree(swap=True)

            try:
                matching_snapshots = snapshots[commit.id]
            except KeyError:
                pass

            yield (commit, matching_snapshots, diff)

    def commit(self, message, no_snapshot=False):
        changes = self.diff_staged()
        if not changes:
            raise Error('No changes staged for commit')

        try:
            parent, ref = self.git.resolve_refish(self.git.head.name)
            parents = [parent.id]
            ref_name = ref.name
        except pygit2.GitError:
            parents = []
            ref_name = 'refs/heads/master'

        time = -1
        offset = 0

        if COMMIT_DATE_ENV_VAR in os.environ:
            try:
                time, offset = self._parse_date_time(os.environ[COMMIT_DATE_ENV_VAR])
            except ValueError as e:
                raise Error(f'Invalid date string in {COMMIT_DATE_ENV_VAR} environment variable: {e}')

        signature = pygit2.Signature(FAKE_SIGNATURE_NAME, FAKE_SIGNATURE_EMAIL, time, offset)

        self.git.create_commit(ref_name, signature, signature,
                message, self.git.index.write_tree(), parents)

        if not no_snapshot:
            self.maybe_create_snapshot(changes)

    def _parse_date_time(self, string):
        result = re.match('^([0-9]+) ([-+][0-9][0-9])([0-9][0-9])$', string)
        if not result:
            raise ValueError('Could not parse date. '
                    f'Expected format: \"<unix timestamp> <time zone offset>\", got: {string}')
        return (int(result.group(1)), int(result.group(2)) * 60 + int(result.group(3)))

    def restore(self, path, refish, aux_store_name):
        assert isabs(path)

        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            raise Error('No commit found')

        if os.path.exists(path):
            raise Error('File exists - refusing to overwrite: ' + path)

        if refish:
            commit = self._resolve_refish(refish)
        else:
            commit = head

        relpath = os.path.relpath(path, self.path)

        try:
            obj = commit.tree[relpath]
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

        snapshots_by_base_commit_id = self._snapshots_by_base_commit_id()

        matching_snapshots = []
        for ancestor in self.git.walk(commit.id):
            if ancestor.id not in snapshots_by_base_commit_id:
                continue

            ancestor_path = gittools.find_object(ancestor.tree, obj.id, path_hint=relpath)
            if ancestor_path:
                for snapshot in snapshots_by_base_commit_id[ancestor.id]:
                    matching_snapshots.append((snapshot, ancestor_path))

        if not matching_snapshots:
            raise Error('No snapshot seems to contain the file in the desired revision')

        excluded_snapshots = []
        restored = False

        for snapshot, ancestor_path in matching_snapshots:
            if aux_store_name and snapshot.store.name != aux_store_name:
                excluded_snapshots.append(snapshot)
                continue

            logger.info('Trying to restore from ' + snapshot.reference)
            try:
                snapshot.store.restore(ancestor_path, path, snapshot)
            except Error as e:
                logger.warning('Failed to restore from ' + snapshot.reference + ': ' + str(e))
            else:
                restored = True
                break

        if not restored:
            if excluded_snapshots:
                logger.info('Also available from the following skipped snapshots:')
                for snapshot in excluded_snapshots:
                    logger.info('  ' + snapshot.reference)
            raise Error('Could not restore')

    def maybe_create_snapshot(self, committed_diff):
        snapshot_command = self.get_config_value(CONFIG_OPTION_SNAPSHOT_COMMAND)
        if not snapshot_command:
            return

        if not gittools.diff_adds_new_content(committed_diff):
            logger.debug('No new content comitted - skipping snapshot creation')
            return

        result = subprocess.run(snapshot_command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning('Snapshot creation failed: ' + result.stderr)

    def get_config(self, name=None):
        if name and not name in CONFIG_OPTIONS:
            raise Error('No such configuration option')
        names = [name] if name else CONFIG_OPTIONS
        for name in names:
            try:
                value = self.git.config[CONFIG_PREFIX + name]
            except KeyError:
                value = str()

            yield (name, value)

    def get_config_value(self, name):
        return next(self.get_config(name))[1]

    def set_config(self, name, value):
        if not name in CONFIG_OPTIONS:
            raise Error('No such configuration option')
        self.git.config[CONFIG_PREFIX + name] = value

    def clear_config(self, name):
        if not name in CONFIG_OPTIONS:
            raise Error('No such configuration option')
        del self.git.config[CONFIG_PREFIX + name]

class AuxStores:
    def __init__(self, repository):
        self._repository = repository

    def __contains__(self, name):
        return self._url_config_key(name) in self._repository.git.config

    def __getitem__(self, name):
        try:
            url = self._repository.git.config[self._url_config_key(name)]
            type_name = self._repository.git.config[self._type_config_key(name)]
        except KeyError:
            raise KeyError(name)
        return AuxStore.create(type_name, self._repository, name, url)

    def __iter__(self):
        pattern = re.compile(r'^sod-aux-store\.([^.]+)\.url$')
        for item in self._repository.git.config:
            match = pattern.search(item.name)
            if not match:
                continue
            name = match.group(1)
            url = item.value
            type_name = self._repository.git.config[self._type_config_key(name)]
            yield AuxStore.create(type_name, self._repository, name, url)

    def create(self, type_name, name, url):
        if '/' in name:
            raise Error('Auxiliary data store name may not contain slashes')
        if name in self:
            raise Error('Auxiliary data store of this name already exists')
        try:
            store = AuxStore.create(type_name, self._repository, name, url)
        except Error:
            raise
        self._repository.git.config[self._type_config_key(name)] = type_name
        self._repository.git.config[self._url_config_key(name)] = url

    def delete(self, name):
        try:
            store = self.__getitem__(name)
        except KeyError:
            raise Error('No such auxiliary data store')

        store._remove_remotes()

        for key in [
                self._url_config_key(name),
                self._type_config_key(name),
                ]:
            try:
                del self._repository.git.config[key]
            except KeyError:
                continue

    def update(self, names=None):
        if not names:
            stores = list(self.__iter__())
        else:
            stores = filter(lambda s: s.name in names, self.__iter__())

        for store in stores:
            store.update()

    def _url_config_key(self, name):
        return 'sod-aux-store.{}.url'.format(name)

    def _type_config_key(self, name):
        return 'sod-aux-store.{}.type'.format(name)

class AuxStore(ABC):
    _types = {}

    def __init__(self, repository, name, url):
        self._repository = repository
        self._name = name
        self._url = url

    @classmethod
    def register_type(cls, typecls):
        name = typecls.type_name()
        if name in cls._types:
            raise Error(f"Store type '{name}' already registered")
        cls._types[name] = typecls

    @classmethod
    def registered_type_names(cls):
        return cls._types.keys()

    @classmethod
    def create(cls, type_name, repository, name, url):
        if type_name not in cls._types:
            raise Error("Not a recognized auxiliary data store type: %1".format(type_name))
        typecls = cls._types[type_name]
        return typecls(repository, name, url)

    @staticmethod
    @abstractmethod
    def type_name():
        pass

    @property
    def repository(self):
        return self._repository

    @property
    def name(self):
        return self._name

    @property
    def url(self):
        return self._url

    @property
    def snapshots(self):
        for ref_name in self._repository.git.references:
            if not ref_name.startswith(SNAPSHOT_REF_PREFIX):
                continue
            name = ref_name[len(SNAPSHOT_REF_PREFIX):]
            store_name, id_ = self._split_ref_name(name)
            if store_name != self._name:
                continue
            obj = self._repository.git.references[ref_name].peel()
            yield Snapshot(self, id_, obj.id)

    @abstractmethod
    def update(self):
        pass

    @abstractmethod
    def restore(self, path, destination_path, snapshot):
        pass

    def _split_ref_name(self, name):
        try:
            store_name, id_ = name.split('/', maxsplit=1)
        except ValueError:
            id_ = None
        return (store_name, id_)

class Snapshot:
    def __init__(self, store, id_, base_commit_id):
        self.store = store
        self.id_ = id_
        self.base_commit_id = base_commit_id

    @property
    def reference(self):
        retv = self.store.name
        if self.id_:
            retv += '/' + self.id_
        return retv
