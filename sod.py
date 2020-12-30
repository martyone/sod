import click
import hashlib
import logging
import os
import pygit2
import stat as stat_m

logger = logging.getLogger(__name__)

BLOCK_SIZE = 65536
DIGEST_SIZE = 40 # sha-1
ATTR_DIGEST = 'user.hashfs_digest'
ATTR_DIGEST_VERSION = 1
SKIP_TREE_NAMES = {'.snapshots', '.sod'}
SKIP_TREE_FLAGS = {'.git', '.svn', '.sodignore'}

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
    root_dir = find_upward(path, '.sod', test=os.path.isdir)

    if not root_dir:
        return None

    return Repository(os.path.join(root_dir, '.sod'))

@click.group()
@click.option('--debug', is_flag=True, help='Enable debugging output')
def cli(debug):
    init_logging(debug=debug)

@click.command()
def status():
    pass

@click.command()
def add():
    pass

@click.command()
def reset():
    pass

@click.command()
def commit():
    pass

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
