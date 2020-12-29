#!/usr/bin/env python3
'''
hashfs.py - mirrors a directory tree replacing data with hashes

Caveats:

 * Inode generation numbers are not passed through but set to zero.

 * Block size (st_blksize) and number of allocated blocks (st_blocks) are not
   passed through.

 * Performance for large directories is not good, because the directory
   is always read completely.

 * There may be a way to break-out of the directory tree.

 * The readdir implementation is not fully POSIX compliant. If a directory
   contains hardlinks and is modified during a readdir call, readdir()
   may return some of the hardlinked files twice or omit them completely.

 * If you delete or rename files in the underlying file system, the
   passthrough file system will get confused.

Copyright ©  Nikolaus Rath <Nikolaus.org>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

import os
import sys

# If we are running from the pyfuse3 source directory, try
# to load the module from there first.
basedir = os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), '..'))
if (os.path.exists(os.path.join(basedir, 'setup.py')) and
    os.path.exists(os.path.join(basedir, 'src', 'pyfuse3.pyx'))):
    sys.path.insert(0, os.path.join(basedir, 'src'))

import pyfuse3
from argparse import ArgumentParser
import errno
import logging
import stat as stat_m
from pyfuse3 import FUSEError
from os import fsencode, fsdecode
from collections import defaultdict
import trio
import hashlib

import faulthandler
faulthandler.enable()

log = logging.getLogger(__name__)

BLOCK_SIZE = 65536
DIGEST_SIZE = 40 # sha-1
ATTR_DIGEST = 'user.hashfs_digest'
ATTR_DIGEST_VERSION = 1
SKIP_TREE_NAMES = {'.snapshots', '.sod'}
SKIP_TREE_FLAGS = {'.git', '.svn'}

class Operations(pyfuse3.Operations):

    def __init__(self, source):
        super().__init__()
        self._inode_path_map = { pyfuse3.ROOT_INODE: source }
        self._lookup_cnt = defaultdict(lambda : 0)
        self._inode_digest_map = dict()
        self._inode_open_count = dict()

    def _hash_file(self, path):
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

    def _inode_to_path(self, inode):
        try:
            val = self._inode_path_map[inode]
        except KeyError:
            raise FUSEError(errno.ENOENT)

        if isinstance(val, set):
            # In case of hardlinks, pick any path
            val = next(iter(val))
        return val

    def _add_path(self, inode, path):
        log.debug('_add_path for %d, %s', inode, path)
        self._lookup_cnt[inode] += 1

        # With hardlinks, one inode may map to multiple paths.
        if inode not in self._inode_path_map:
            self._inode_path_map[inode] = path
            return

        val = self._inode_path_map[inode]
        if isinstance(val, set):
            val.add(path)
        elif val != path:
            self._inode_path_map[inode] = { path, val }

    async def forget(self, inode_list):
        for (inode, nlookup) in inode_list:
            if self._lookup_cnt[inode] > nlookup:
                self._lookup_cnt[inode] -= nlookup
                continue
            log.debug('forgetting about inode %d', inode)
            assert inode not in self._inode_open_count
            del self._lookup_cnt[inode]
            try:
                del self._inode_path_map[inode]
            except KeyError: # may have been deleted
                pass

    async def lookup(self, inode_p, name, ctx=None):
        name = fsdecode(name)
        log.debug('lookup for %s in %d', name, inode_p)
        path = os.path.join(self._inode_to_path(inode_p), name)
        attr = self._getattr(path=path)
        if name != '.' and name != '..':
            self._add_path(attr.st_ino, path)
        return attr

    async def getattr(self, inode, ctx=None):
        return self._getattr(path=self._inode_to_path(inode))

    def _getattr(self, path=None, fd=None):
        assert fd is None or path is None
        assert not(fd is None and path is None)
        try:
            if fd is None:
                stat = os.lstat(path)
            else:
                stat = os.fstat(fd)
        except OSError as exc:
            raise FUSEError(exc.errno)

        entry = pyfuse3.EntryAttributes()
        for attr in ('st_ino', 'st_mode', 'st_nlink', 'st_uid', 'st_gid',
                     'st_rdev', 'st_atime_ns', 'st_mtime_ns',
                     'st_ctime_ns'):
            setattr(entry, attr, getattr(stat, attr))
        entry.generation = 0
        entry.entry_timeout = 0
        entry.attr_timeout = 0
        if stat_m.S_ISREG(entry.st_mode):
            entry.st_size = DIGEST_SIZE + 1
        else:
            entry.st_size = stat.st_size
        entry.st_blksize = 512
        entry.st_blocks = ((entry.st_size+entry.st_blksize-1) // entry.st_blksize)

        return entry

    async def readlink(self, inode, ctx):
        path = self._inode_to_path(inode)
        try:
            target = os.readlink(path)
        except OSError as exc:
            raise FUSEError(exc.errno)
        return fsencode(target)

    async def opendir(self, inode, ctx):
        return inode

    async def readdir(self, inode, off, token):
        path = self._inode_to_path(inode)
        log.debug('reading %s', path)
        entries = []
        for name in os.listdir(path):
            if name == '.' or name == '..':
                continue
            if name in SKIP_TREE_NAMES:
                continue
            if name in SKIP_TREE_FLAGS:
                log.debug('skipping tree %s', path)
                entries = []
                break
            attr = self._getattr(path=os.path.join(path, name))
            entries.append((attr.st_ino, name, attr))

        log.debug('read %d entries, starting at %d', len(entries), off)

        # This is not fully posix compatible. If there are hardlinks
        # (two names with the same inode), we don't have a unique
        # offset to start in between them. Note that we cannot simply
        # count entries, because then we would skip over entries
        # (or return them more than once) if the number of directory
        # entries changes between two calls to readdir().
        for (ino, name, attr) in sorted(entries):
            if ino <= off:
                continue
            if not pyfuse3.readdir_reply(
                token, fsencode(name), attr, ino):
                break
            self._add_path(attr.st_ino, os.path.join(path, name))

    async def unlink(self, inode_p, name, ctx):
        raise FUSEError(errno.EROFS)

    async def rmdir(self, inode_p, name, ctx):
        raise FUSEError(errno.EROFS)

    def _forget_path(self, inode, path):
        log.debug('forget %s for %d', path, inode)
        val = self._inode_path_map[inode]
        if isinstance(val, set):
            val.remove(path)
            if len(val) == 1:
                self._inode_path_map[inode] = next(iter(val))
        else:
            del self._inode_path_map[inode]

    async def symlink(self, inode_p, name, target, ctx):
        raise FUSEError(errno.EROFS)

    async def rename(self, inode_p_old, name_old, inode_p_new, name_new,
                     flags, ctx):
        raise FUSEError(errno.EROFS)

    async def link(self, inode, new_inode_p, new_name, ctx):
        raise FUSEError(errno.EROFS)

    async def setattr(self, inode, attr, fields, fh, ctx):
        raise FUSEError(errno.EROFS)

    async def mknod(self, inode_p, name, mode, rdev, ctx):
        raise FUSEError(errno.EROFS)

    async def mkdir(self, inode_p, name, mode, ctx):
        raise FUSEError(errno.EROFS)

    async def statfs(self, ctx):
        root = self._inode_path_map[pyfuse3.ROOT_INODE]
        stat_ = pyfuse3.StatvfsData()
        try:
            statfs = os.statvfs(root)
        except OSError as exc:
            raise FUSEError(exc.errno)
        for attr in ('f_bsize', 'f_frsize', 'f_blocks', 'f_bfree', 'f_bavail',
                     'f_files', 'f_ffree', 'f_favail'):
            setattr(stat_, attr, getattr(statfs, attr))
        stat_.f_namemax = statfs.f_namemax - (len(root)+1)
        return stat_

    async def open(self, inode, flags, ctx):
        if inode in self._inode_digest_map:
            self._inode_open_count[inode] += 1
            return pyfuse3.FileInfo(fh=inode)
        assert flags & os.O_CREAT == 0
        path = self._inode_to_path(inode)

        try:
            stat = os.stat(path)
        except OSError as exc:
            raise FUSEError(exc.errno)

        digest = None

        try:
            cached_digest = os.getxattr(path, ATTR_DIGEST)
            version, timestamp, digest = cached_digest.decode('utf-8').split(':')
            if int(version) != ATTR_DIGEST_VERSION:
                log.debug('XXX found incompatible cached digest for %s', path)
                digest = None
            elif int(timestamp) < stat.st_mtime_ns:
                log.debug('XXX found outdated cached digest for %s', path)
                digest = None
            else:
                log.debug('XXX found valid cached digest for %s', path)
        except:
            pass

        if not digest:
            log.debug('XXX computing digest for %s', path)
            digest = self._hash_file(path)
            cached_digest = ':'.join([str(ATTR_DIGEST_VERSION), str(stat.st_mtime_ns), digest])
            try:
                os.setxattr(path, ATTR_DIGEST, cached_digest.encode('utf-8'))
            except:
                log.debug('XXX failed to cache digest for %s', path)
                raise

        self._inode_digest_map[inode] = (digest + '\n').encode('utf-8')
        self._inode_open_count[inode] = 1

        return pyfuse3.FileInfo(fh=inode)

    async def create(self, inode_p, name, mode, flags, ctx):
        raise FUSEError(errno.EROFS)

    async def read(self, fh, offset, length):
        digest = self._inode_digest_map[fh]
        return digest[offset:length]

    async def write(self, fh, offset, buf):
        raise FUSEError(errno.EROFS)

    async def release(self, fh):
        if self._inode_open_count[fh] > 1:
            self._inode_open_count[fh] -= 1
            return

        del self._inode_open_count[fh]
        del self._inode_digest_map[fh]

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


def parse_args(args):
    '''Parse command line'''

    parser = ArgumentParser()

    parser.add_argument('source', type=str,
                        help='Directory tree to mirror')
    parser.add_argument('mountpoint', type=str,
                        help='Where to mount the file system')
    parser.add_argument('--debug', action='store_true', default=False,
                        help='Enable debugging output')
    parser.add_argument('--debug-fuse', action='store_true', default=False,
                        help='Enable FUSE debugging output')

    return parser.parse_args(args)

def main():
    options = parse_args(sys.argv[1:])
    init_logging(options.debug)
    operations = Operations(options.source)

    log.debug('Mounting...')
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add('fsname=hashfs')
    if options.debug_fuse:
        fuse_options.add('debug')
    pyfuse3.init(operations, options.mountpoint, fuse_options)

    try:
        log.debug('Entering main loop..')
        trio.run(pyfuse3.main)
    except:
        pyfuse3.close(unmount=False)
        raise

    log.debug('Unmounting..')
    pyfuse3.close()

if __name__ == '__main__':
    main()
