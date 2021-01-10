from contextlib import contextmanager
import hashlib
import logging
import os
import stat as stat_m

logger = logging.getLogger(__name__)

BLOCK_SIZE = 65536
HASH_ALGORITHM = 'sha1'
HEXDIGEST_SIZE = hashlib.new(HASH_ALGORITHM).digest_size * 2
HEXDIGEST_ABBREV_SIZE = 10
ATTR_DIGEST = 'user.sod.digest'
ATTR_DIGEST_VERSION = 1

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

def digest_size(abbreviated=False):
    return [HEXDIGEST_SIZE, HEXDIGEST_ABBREV_SIZE][abbreviated]

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
