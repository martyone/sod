import click
import hashlib
import logging
import os
import pygit2
import stat as stat_m

logger = logging.getLogger(__name__)

SOD_DIR = '.sod'
SODIGNORE_FILE = '.sodignore'
FAKE_SIGNATURE = pygit2.Signature('sod', 'sod@localhost')
BLOCK_SIZE = 65536
DIGEST_SIZE = 40 # sha-1
ATTR_DIGEST = 'user.sod.digest'
ATTR_DIGEST_VERSION = 1
SKIP_TREE_NAMES = {'.snapshots', SOD_DIR}
SKIP_TREE_FLAGS = {'.git', '.svn', SODIGNORE_FILE}

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

def digest_for(path):
    stat = os.stat(path)

    digest = None

    try:
        cached_digest = os.getxattr(path, ATTR_DIGEST)
        version, timestamp, digest = cached_digest.decode('utf-8').split(':')
        if int(version) != ATTR_DIGEST_VERSION:
            logger.debug('XXX found incompatible cached digest for %s', path)
            digest = None
        elif int(timestamp) < stat.st_mtime_ns:
            logger.debug('XXX found outdated cached digest for %s', path)
            digest = None
        else:
            logger.debug('XXX found valid cached digest for %s', path)
    except:
        pass

    if not digest:
        logger.debug('XXX computing digest for %s', path)
        digest = hash_file(path)
        cached_digest = ':'.join([str(ATTR_DIGEST_VERSION), str(stat.st_mtime_ns), digest])

        was_writable = stat.st_mode & stat_m.S_IWUSR
        if not was_writable:
            try:
                os.chmod(path, stat.st_mode | stat_m.S_IWUSR)
            except:
                logger.debug('XXX failed to temprarily make file writable %s', path)
                pass

        try:
            os.setxattr(path, ATTR_DIGEST, cached_digest.encode('utf-8'))
        except:
            logger.debug('XXX failed to cache digest for %s', path)
            pass

        if not was_writable:
            try:
                os.chmod(path, stat.st_mode)
            except:
                logger.debug('XXX failed to restore permissions for %s', path)
                pass

    return digest

def walk_bottom_up(top, skip_tree_names, skip_tree_flags):
    dirs = []
    files = []
    symlinks = []

    try:
        it = os.scandir(top)
    except OSError as e:
        logger.error('scandir failed: %s', e)
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
                logger.error('next failed: %s', e)
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

def print_status(git_diff):
    for delta in git_diff.deltas:
        if delta.old_file.path == delta.new_file.path:
            path_info = delta.old_file.path
        elif common_path := os.path.commonpath([delta.old_file.path, delta.new_file.path]):
            old_unique = delta.old_file.path[len(common_path):]
            new_unique = delta.new_file.path[len(common_path):]
            path_info = common_path + '{' + old_unique + ' -> ' + new_unique + '}'
        else:
            path_info = delta.old_file.path + ' -> ' + delta.new_file.path
        print('{} {}'.format(delta.status_char(), path_info))

class Repository:
    def __init__(self, path):
        self.path = path
        self.data_dir = os.path.dirname(path)
        self.git = pygit2.Repository(self.path)

    def build_tree(self, top_dir):
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
                digest = digest_for(os.path.join(root, name))
                oid = self.git.create_blob((digest + '\n').encode('utf-8'))
                builder.insert(name, oid, pygit2.GIT_FILEMODE_BLOB)
                item_count += 1
            for name in symlinks:
                try:
                    target = os.readlink(os.path.join(root, name))
                except OSError:
                    logger.error('failed to read symlink %s', os.path.join(root, name))
                    continue
                oid = self.git.create_blob(target)
                builder.insert(name, oid, pygit2.GIT_FILEMODE_LINK)
                item_count += 1

            if item_count > 0:
                trees[root] = builder.write()
            else:
                trees[root] = None

        assert len(trees) == 1
        assert top_dir in trees

        return trees.pop(top_dir)

def discover_repository(path):
    root_dir = find_upward(path, SOD_DIR, test=os.path.isdir)

    if not root_dir:
        return None

    return Repository(os.path.join(root_dir, SOD_DIR))

@click.group()
@click.option('--debug', is_flag=True, help='Enable debugging output')
def cli(debug):
    init_logging(debug=debug)

@click.command()
def init():
    git = pygit2.init_repository(SOD_DIR, bare=True)
    if not git:
        logger.error('Failed to init git repository')
        return 1

    git.config['core.quotePath'] = False

    empty_tree_oid = git.TreeBuilder().write()

    initial_commit_oid = git.create_commit('refs/heads/master',
            FAKE_SIGNATURE, FAKE_SIGNATURE,
            'Empty initial commit', empty_tree_oid, [])
    if not initial_commit_oid:
        logger.error('Failed to create empty initial commit')
        return 1
cli.add_command(init)

@click.command()
@click.option('--staged', is_flag=True, help='Only check the index')
def status(staged):
    repository = discover_repository(os.getcwd())
    if not repository:
        logger.error('Not a sod managed tree')
        return 1

    if not staged:
        work_tree_oid = repository.build_tree(repository.data_dir)
        if not work_tree_oid:
            logger.error('empty tree')
            return 1

        logger.debug('work tree: %s', work_tree_oid)

    head = repository.git.get(repository.git.head.target)
    diff_cached = repository.git.index.diff_to_tree(head.tree)
    diff_cached.find_similar()

    print('Staged:')
    print_status(diff_cached)

    if not staged:
        print('')
        print('Unstaged:')
        work_tree = repository.git.get(work_tree_oid)
        diff = repository.git.index.diff_to_tree(work_tree, flags=pygit2.GIT_DIFF_REVERSE)
        diff.find_similar()
        print_status(diff)

cli.add_command(status)

@click.command()
def add():
    pass

@click.command()
def reset():
    pass

@click.command()
@click.option('--message', help='Commit message')
def commit(message):
    repository = discover_repository(os.getcwd())
    if not repository:
        logger.error('Not a sod managed tree')
        return 1

    root = repository.build_tree(repository.data_dir)

    if not root:
        logger.error('empty tree')
        return 1

    parent, ref = repository.git.resolve_refish(refish=repository.git.head.name)
    oid = repository.git.create_commit(ref.name, FAKE_SIGNATURE, FAKE_SIGNATURE,
            message, repository.git.index.write_tree(), [parent.oid])
    if not oid:
        logger.error('Failed to create empty initial commit')
        return 1
cli.add_command(commit)

@click.command()
def log():
    pass

@click.command()
def test():
    repository = discover_repository(os.getcwd())
    if not repository:
        logger.error('Not a sod managed tree')
        return 1

    root = repository.build_tree(repository.data_dir)

    if not root:
        logger.error('empty tree')
        return 1

    repository.git.index.read_tree(root)
    repository.git.index.write()
    logger.info("tree: %s", root)
cli.add_command(test)
