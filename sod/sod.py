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

def format_diff(git_repo, git_diff, abbreviate=True):
    for delta in git_diff.deltas:
        if delta.old_file.path == delta.new_file.path:
            path_info = delta.old_file.path
        else:
            path_info = format_path_change(delta.old_file.path, delta.new_file.path)

        if delta.similarity != 100 and delta.status != pygit2.GIT_DELTA_ADDED:
            old_blob = git_repo.get(delta.old_file.id)
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
    click.echo(''.join(format_diff(repository.git, diff_cached, abbreviate=abbrev)))

    if not staged:
        click.echo('Changes not staged for commit:')
        click.echo(''.join(format_diff(repository.git, diff_not_staged, abbreviate=abbrev)))

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

    def format_commit(commit, snapshots, diff):
        refs = [snapshot.shorthand_reference for snapshot in snapshots]
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
        yield from format_diff(repository.git, diff, abbreviate=abbrev)
        yield '\n'

    def format_log(log):
        for commit, snapshots, diff in log:
            yield from format_commit(commit, snapshots, diff)

    click.echo_via_pager(format_log(repository.log(head)))

@cli.group()
def aux():
    pass

@aux.command()
@pass_repository
def list(repository):
    for store in repository.aux_stores:
        click.echo(store.name + ' ' + store.url_pattern)

@aux.command()
@click.argument('name')
@click.argument('url_pattern')
@pass_repository
def add(repository, name, url_pattern):
    repository.aux_stores.create(name, url_pattern)

@aux.command()
@click.argument('name')
@pass_repository
def remove(repository, name):
    repository.aux_stores.delete(name)

@aux.command()
@click.option('--all', 'update_all', is_flag=True, help='Update all auxiliary data stores')
@click.argument('name', required=False)
@pass_repository
def update(repository, update_all, name):
    if name:
        repository.aux_stores.update([name])
    elif update_all:
        repository.aux_stores.update()
    else:
        raise click.UsageError('No store selected')

@cli.command()
@click.argument('path')
@click.argument('ref-ish', required=False)
@click.option('--from', 'aux_store', help='Restore using the given auxiliary data store')
@pass_repository
def restore(repository, path, ref_ish, aux_store):
    repository.restore(path, ref_ish, aux_store)
