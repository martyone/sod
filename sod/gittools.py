import logging
import os
from os.path import isabs
import pygit2

logger = logging.getLogger(__name__)

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

def _walk_bottom_up(top, skip_tree_names, skip_tree_flags):
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
        yield from _walk_bottom_up(os.path.join(top, subdir), skip_tree_names, skip_tree_flags)
    yield top, dirs, files, symlinks

def empty_tree_oid(repo):
    return repo.TreeBuilder().write()

def empty_tree(repo):
    return repo.get(empty_tree_oid(repo))

def tree_build(repo, top_dir, *, create_blob, skip_tree_names, skip_tree_flags):
    assert isabs(top_dir)

    trees = {}

    EMPTY_TREE_OID = empty_tree_oid(repo)

    for root, dirs, files, symlinks in _walk_bottom_up(top_dir, skip_tree_names, skip_tree_flags):
        item_count = 0
        builder = repo.TreeBuilder()
        for name in dirs:
            oid = trees.pop(os.path.join(root, name))
            if not oid:
                continue
            builder.insert(name, oid, pygit2.GIT_FILEMODE_TREE)
            item_count += 1
        for name in files:
            oid = create_blob(repo, os.path.join(root, name))
            builder.insert(name, oid, pygit2.GIT_FILEMODE_BLOB)
            item_count += 1
        for name in symlinks:
            try:
                target = os.readlink(os.path.join(root, name))
            except OSError as e:
                logger.warning('Failed to read symlink: %s: %s', os.path.join(root, name), e)
                continue
            oid = repo.create_blob(target)
            builder.insert(name, oid, pygit2.GIT_FILEMODE_LINK)
            item_count += 1

        if item_count > 0:
            trees[root] = builder.write()
        else:
            trees[root] = EMPTY_TREE_OID

    assert len(trees) == 1
    assert top_dir in trees

    return trees.pop(top_dir)

def tree_filter(repo, tree, paths):
    assert not all(map(isabs, paths))

    index = pygit2.Index()

    for path in paths:
        try:
            obj = tree[path]
        except KeyError as e:
            pass
        else:
            index_add_object(repo, index, path, obj)

    return repo.get(index.write_tree(repo))

def index_add(repo, index, top_dir, path, *, create_blob, skip_tree_names, skip_tree_flags):
    assert isabs(top_dir)
    assert isabs(path)
    assert os.path.commonpath([top_dir, path]) == top_dir

    relpath = os.path.relpath(path, top_dir)

    if os.path.islink(path):
        try:
            target = os.readlink(path)
        except OSError as e:
            logger.warning('Failed to read symlink: %s: %s', path, e)
            return
        oid = repo.create_blob(target)
        index.add(pygit2.IndexEntry(relpath, oid, pygit2.GIT_FILEMODE_LINK))
    elif os.path.isdir(path):
        index.remove_all([relpath])
        oid = tree_build(repo, path, create_blob=create_blob, skip_tree_names=skip_tree_names,
                skip_tree_flags=skip_tree_flags)
        index_add_tree(repo, index, relpath, repo.get(oid))
    elif os.path.isfile(path):
        oid = create_blob(repo, path)
        index.add(pygit2.IndexEntry(relpath, oid, pygit2.GIT_FILEMODE_BLOB))
    else:
        index.remove_all([relpath])

def index_add_tree(repo, index, path, tree):
    assert not isabs(path)

    for item in tree:
        item_path = os.path.normpath(os.path.join(path, item.name))
        if item.filemode != pygit2.GIT_FILEMODE_TREE:
            index.add(pygit2.IndexEntry(item_path, item.id, item.filemode))
        else:
            index_add_tree(repo, index, item_path, repo.get(item.id))

def index_add_object(repo, index, path, obj):
    assert not isabs(path)

    if obj.filemode != pygit2.GIT_FILEMODE_TREE:
        index.add(pygit2.IndexEntry(path, obj.id, obj.filemode))
    else:
        index_add_tree(repo, index, path, obj)

def index_reset_path(repo, index, path, tree):
    assert not isabs(path)

    index.remove_all([path])

    try:
        obj = tree[path]
    except KeyError:
        return

    if obj.filemode == pygit2.GIT_FILEMODE_TREE:
        index_add_tree(repo, index, path, obj)
    else:
        index.add(pygit2.IndexEntry(path, obj.oid, obj.filemode))

def find_object(tree, oid, path_hint):
    assert not isabs(path_hint)

    if path_hint:
        try:
            obj = tree[path_hint]
        except KeyError:
            pass
        if obj.id == oid:
            return path_hint

    for obj in tree:
        if obj.type == pygit2.GIT_FILEMODE_TREE:
            path = find_object(obj, oid, None)
            if path:
                return obj.name + '/' + path
        elif obj.id == oid:
            return obj.name

    return None
