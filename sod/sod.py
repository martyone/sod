import click
import logging
import os
import pygit2
import sys

from . import Error
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
