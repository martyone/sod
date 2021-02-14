import click
from datetime import datetime
import logging
import os
import pygit2
import sys

from . import Error
from . import gittools
from . import hashing
from . import repository
from .aux.plain import PlainAuxStore

logger = logging.getLogger(__name__)

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

def format_diff(repo, git_diff, abbreviate=True, obey_cwd=True):
    for delta in git_diff.deltas:
        if obey_cwd:
            rel_old_path = os.path.relpath(os.path.join(repo.path, delta.old_file.path))
            rel_new_path = os.path.relpath(os.path.join(repo.path, delta.new_file.path))
        else:
            rel_old_path = delta.old_file.path
            rel_new_path = delta.new_file.path

        if delta.old_file.path == delta.new_file.path:
            path_info = rel_old_path
        else:
            path_info = format_path_change(rel_old_path, rel_new_path)

        if delta.similarity != 100 and delta.status != pygit2.GIT_DELTA_ADDED:
            old_blob = repo.git.get(delta.old_file.id)
            old_digest = old_blob.data.decode().strip()
        else:
            old_digest = '-'

        digest_size = hashing.digest_size(abbreviate)

        yield '  {status:{status_w}}  {old_digest:{digest_w}}  {path_info}\n'.format(
            status=gittools.DELTA_STATUS_NAME[delta.status] + ':',
            status_w=gittools.DELTA_STATUS_MAX_LENGTH + 1,
            old_digest=old_digest[0:digest_size],
            digest_w=digest_size,
            path_info=path_info)

class ErrorHandlingGroup(click.Group):
    def __call__(self, *args, **kwargs):
        try:
            super().__call__(*args, **kwargs)
        except Error as e:
            click.ClickException(e).show()
            sys.exit(1)

class DiscoveredRepository(repository.Repository):
    def __init__(self):
        root_dir = find_upward(os.getcwd(), repository.SOD_DIR, test=os.path.isdir)
        if not root_dir:
            raise click.ClickException('Not a sod repository')

        super().__init__(root_dir)

pass_repository = click.make_pass_decorator(DiscoveredRepository, ensure=True)

@click.group(cls=ErrorHandlingGroup)
@click.option('--debug', is_flag=True, help='Enable debugging output')
def cli(debug):
    """sod - a digest tracker"""
    if not cli.initialized:
        init_logging(debug=debug)
        repository.AuxStore.register_type(PlainAuxStore)
        cli.initialized = True

# FIXME Properly allow invoking cli repeatedly (e.g. for testing)
cli.initialized = False

@cli.command()
def init():
    """Initialize a sod repository under the current working directory."""
    repository.Repository.initialize(os.getcwd())

@cli.command()
@click.option('--staged', is_flag=True, help='Only check the index')
@click.option('-r', '--rehash', is_flag=True, help='Do not use cached digests')
@click.option('--abbrev/--no-abbrev', default=True, help='Abbreviate old content digest')
@click.argument('paths', nargs=-1)
@pass_repository
def status(repository, staged, rehash, abbrev, paths):
    """Summarize changes since last commit."""
    abspaths = tuple(map(os.path.abspath, paths))

    diff_cached = repository.diff_staged(abspaths)

    if not staged:
        diff_not_staged = repository.diff_not_staged(abspaths, rehash)

    click.echo('Changes staged for commit:')
    click.echo(''.join(format_diff(repository, diff_cached, abbreviate=abbrev)))

    if not staged:
        click.echo('Changes not staged for commit:')
        click.echo(''.join(format_diff(repository, diff_not_staged, abbreviate=abbrev)))

@cli.command()
@click.argument('paths', nargs=-1)
@pass_repository
def add(repository, paths):
    """Stage changes for recording with next commit."""
    abspaths = tuple(map(os.path.abspath, paths))
    repository.add(abspaths)

@cli.command()
@click.argument('paths', nargs=-1)
@pass_repository
def reset(repository, paths):
    """Reset changes staged for recording with next commit."""
    abspaths = tuple(map(os.path.abspath, paths))
    repository.reset(abspaths)

@cli.command()
@click.option('-m', '--message', help='Commit message')
@pass_repository
def commit(repository, message):
    """Record changes to the repository."""
    repository.commit(message)

@cli.command()
@click.option('--abbrev/--no-abbrev', default=True, help='Abbreviate old content digest')
@pass_repository
def log(repository, abbrev):
    """Show commit log."""
    try:
        head = repository.git.head.target
    except pygit2.GitError:
        raise Error('No commit found')

    def format_commit(commit, snapshots, diff):
        refs = [snapshot.reference for snapshot in snapshots]
        if commit.id == head:
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
        yield from format_diff(repository, diff, abbreviate=abbrev, obey_cwd=False)
        yield '\n'

    def format_log(log):
        for commit, snapshots, diff in log:
            yield from format_commit(commit, snapshots, diff)

    click.echo_via_pager(format_log(repository.log(head)))

@cli.group()
def aux():
    """Manage auxiliary data stores."""
    pass

@aux.command()
@pass_repository
def list(repository):
    """List auxiliary data stores."""
    for store in repository.aux_stores:
        click.echo(store.name + ' ' + store.url + ' (' + store.type_name() + ')')

@aux.command()
@click.argument('name')
@click.argument('url')
@click.option('--type', 'store_type', metavar='TYPE', default=PlainAuxStore.type_name(),
        help='Store type')
@pass_repository
def add(repository, name, url, store_type):
    """Add an auxiliary data store.

    Available types:

        plain
    """
    repository.aux_stores.create(store_type, name, url)

@aux.command()
@click.argument('name')
@pass_repository
def remove(repository, name):
    """Remove an auxiliary data store."""
    repository.aux_stores.delete(name)

@aux.command()
@click.option('--all', 'update_all', is_flag=True, help='Update all auxiliary data stores')
@click.argument('name', required=False)
@pass_repository
def update(repository, update_all, name):
    """Update an auxiliary data store."""
    if name:
        repository.aux_stores.update([name])
    elif update_all:
        repository.aux_stores.update()
    else:
        raise click.UsageError('No store selected')

@cli.command()
@click.argument('path')
@click.argument('ref-ish', required=False)
@click.option('--from', 'aux_store', help='Choose particular auxiliary data store to restore from')
@pass_repository
def restore(repository, path, ref_ish, aux_store):
    """Restore data from an auxiliary data store."""
    abspath = os.path.abspath(path)
    repository.restore(abspath, ref_ish, aux_store)
