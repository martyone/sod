import click
from datetime import datetime
import hashlib
import logging
import os
import pygit2
import stat as stat_m
import sys

logger = logging.getLogger(__name__)

SOD_DIR = '.sod'
SODIGNORE_FILE = '.sodignore'
FAKE_SIGNATURE = pygit2.Signature('sod', 'sod@localhost')
BLOCK_SIZE = 65536
DIGEST_SIZE = 40 # sha-1
DIGEST_ABBREV_SIZE = 10
ATTR_DIGEST = 'user.sod.digest'
ATTR_DIGEST_VERSION = 1
SKIP_TREE_NAMES = {'.snapshots', SOD_DIR}
SKIP_TREE_FLAGS = {'.git', '.svn', SODIGNORE_FILE}

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
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(threadName)s: '
                                  '[%(name)s] %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
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
    hasher = hashlib.sha1()
    try:
        with open(path, 'rb') as f:
            block = f.read(BLOCK_SIZE)
            while len(block) > 0:
                hasher.update(block)
                block = f.read(BLOCK_SIZE)
    except:
        return "0" * DIGEST_SIZE
    return hasher.hexdigest()

def digest_for(path, rehash=False):
    stat = os.stat(path)

    digest = None

    if not rehash:
        try:
            cached_digest = os.getxattr(path, ATTR_DIGEST)
            version, timestamp, digest = cached_digest.decode('utf-8').split(':')
        except:
            pass
        else:
            if int(version) != ATTR_DIGEST_VERSION:
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
        cached_digest = ':'.join([str(ATTR_DIGEST_VERSION), str(stat.st_mtime_ns), digest])

        was_writable = stat.st_mode & stat_m.S_IWUSR
        if not was_writable:
            try:
                os.chmod(path, stat.st_mode | stat_m.S_IWUSR)
            except:
                logger.debug('Failed to temprarily make file writable %s', path)
                pass

        try:
            os.setxattr(path, ATTR_DIGEST, cached_digest.encode('utf-8'))
        except:
            logger.debug('Failed to cache digest for %s', path)
            pass

        if not was_writable:
            try:
                os.chmod(path, stat.st_mode)
            except:
                logger.debug('Failed to restore permissions for %s', path)
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
                    symdirs.append(entry.name)
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

class Error(Exception):
    pass

class Repository:
    def __init__(self, path):
        self.path = path
        self.git = pygit2.Repository(os.path.join(self.path, SOD_DIR))
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

    def _build_tree(self, top_dir, rehash=False):
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
                oid = self.git.create_blob((digest + '\n').encode('utf-8'))
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

    def stage(self, paths=[]):
        if not paths:
            tmp_tree_oid = self._build_tree(self.path)
            self.git.index.read_tree(tmp_tree_oid)
        else:
            for path in paths:
                self._stage(path)

        self.git.index.write()

    def _stage(self, path):
        if os.path.islink(path):
            try:
                target = os.readlink(path)
            except OSError as e:
                logger.warning('Failed to read symlink: %s: %s', path, e)
                return
            oid = self.git.create_blob(target)
            self.git.index.add(pygit2.IndexEntry(path, oid, pygit2.GIT_FILEMODE_LINK))
        elif os.path.isdir(path):
            self.git.index.remove_all([path])
            oid = self._build_tree(path)
            self._add_tree(path, self.git.get(oid))
        elif os.path.isfile(path):
            digest = digest_for(path)
            oid = self.git.create_blob((digest + '\n').encode('utf-8'))
            self.git.index.add(pygit2.IndexEntry(path, oid, pygit2.GIT_FILEMODE_BLOB))
        else:
            self.git.index.remove_all([path])

    def _add_tree(self, path, tree):
        for item in tree:
            item_path = os.path.join(path, item.name)
            if item.filemode != pygit2.GIT_FILEMODE_TREE:
                self.git.index.add(pygit2.IndexEntry(item_path, item.id, item.filemode))
            else:
                self._add_tree(item_path, self.git.get(item.id))

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
                self._reset(path, head_tree)

        self.git.index.write()

    def _reset(self, path, tree):
        self.git.index.remove_all([path])

        try:
            obj = tree[path]
        except KeyError:
            return

        if obj.filemode == pygit2.GIT_FILEMODE_TREE:
            self._add_tree(path, obj)
        else:
            self.git.index.add(pygit2.IndexEntry(path, obj.oid, obj.filemode))

    def diff_staged(self):
        try:
            head = self.git.get(self.git.head.target)
        except pygit2.GitError:
            head = None

        if head:
            diff = self.git.index.diff_to_tree(head.tree)
            diff.find_similar()
        else:
            empty_tree = self.git.get(self.EMPTY_TREE_OID)
            diff = self.git.index.diff_to_tree(empty_tree)

        return diff

    def diff_not_staged(self, rehash=False):
        tmp_tree_oid = self._build_tree(self.path, rehash)
        tmp_tree = self.git.get(tmp_tree_oid)
        diff = self.git.index.diff_to_tree(tmp_tree, flags=pygit2.GIT_DIFF_REVERSE)
        diff.find_similar()

        return diff

    def print_status(self, git_diff, abbreviate=True):
        for delta in git_diff.deltas:
            if delta.old_file.path == delta.new_file.path:
                path_info = delta.old_file.path
            elif common_path := os.path.commonpath([delta.old_file.path, delta.new_file.path]):
                old_unique = delta.old_file.path[len(common_path):]
                new_unique = delta.new_file.path[len(common_path):]
                path_info = common_path + '{' + old_unique + ' -> ' + new_unique + '}'
            else:
                path_info = delta.old_file.path + ' -> ' + delta.new_file.path

            if delta.similarity != 100 and delta.status != pygit2.GIT_DELTA_ADDED:
                old_blob = self.git.get(delta.old_file.id)
                old_digest = old_blob.data.decode('utf-8').strip()
            else:
                old_digest = '-'

            digest_size = [DIGEST_SIZE, DIGEST_ABBREV_SIZE][abbreviate]

            print('  {status:{status_w}}  {old_digest:{digest_w}}  {path_info}'.format(
                status=DELTA_STATUS_NAME[delta.status] + ':',
                status_w=DELTA_STATUS_MAX_LENGTH + 1,
                old_digest=old_digest[0:digest_size],
                digest_w=digest_size,
                path_info=path_info))

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
@pass_repository
def status(repository, staged, rehash, abbrev):
    diff_cached = repository.diff_staged()

    if not staged:
        diff_not_staged = repository.diff_not_staged(rehash)

    print('Changes staged for commit:')
    repository.print_status(diff_cached, abbreviate=abbrev)

    if not staged:
        print('')
        print('Changes not staged for commit:')
        repository.print_status(diff_not_staged, abbreviate=abbrev)

@cli.command()
@click.argument('path', nargs=-1)
@pass_repository
def add(repository, path):
    repository.stage(path)

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

    for commit in repository.git.walk(head):
        if commit.parents:
            diff = commit.tree.diff_to_tree(commit.parents[0].tree, swap=True)
            diff.find_similar()
        else:
            diff = commit.tree.diff_to_tree(swap=True)

        print('* {}'.format(commit.message))
        print('  {:%c}'.format(datetime.fromtimestamp(commit.commit_time)))
        print('')
        repository.print_status(diff, abbreviate=abbrev)
        print('')
