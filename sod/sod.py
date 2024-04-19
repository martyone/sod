# This file is part of sod.
#
# Copyright (C) 2020,2021 Martin Kampas <martin.kampas@ubedi.net>
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
    class BriefFormatter(logging.Formatter):
        def __init__(self, fmt):
            super().__init__(fmt)

        def format(self, record):
            if record.levelno == logging.INFO:
                return record.getMessage()
            return super().format(record)

    for name, level in logging.getLevelNamesMapping().items():
        logging.addLevelName(level, name.capitalize())

    if debug:
        level = logging.DEBUG
        formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(levelname)7s [%(name)s] '
                                      '%(message)s',
                                      datefmt='%H:%M:%S')
    else:
        level = logging.INFO
        formatter = BriefFormatter('%(levelname)s: %(message)s')

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
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
        old_unique = old_path[len(common_prefix) + 1:]
        new_unique = new_path[len(common_prefix) + 1:]
    else:
        old_unique = old_path
        new_unique = new_path

    common_suffix = ''
    while True:
        old_unique_h, old_unique_t = os.path.split(old_unique)
        new_unique_h, new_unique_t = os.path.split(new_unique)
        if old_unique_t != new_unique_t:
            break
        common_suffix = os.path.join(old_unique_t, common_suffix)
        old_unique = old_unique_h
        new_unique = new_unique_h

    if not old_unique or not new_unique:
        if common_prefix:
            common_prefix_h, common_prefix_t = os.path.split(common_prefix)
            old_unique = os.path.normpath(os.path.join(common_prefix_t, old_unique))
            new_unique = os.path.normpath(os.path.join(common_prefix_t, new_unique))
            common_prefix = common_prefix_h
        elif common_suffix:
            common_suffix_lead, common_suffix_rest = common_suffix.split(os.sep, maxsplit=1)
            old_unique = os.path.join(old_unique, common_suffix_lead)
            new_unique = os.path.join(new_unique, common_suffix_lead)
            common_suffix = common_suffix_rest
        else:
            assert False

    if common_prefix or common_suffix:
        retv = os.path.join(common_prefix,
                '{' + old_unique + ' -> ' + new_unique + '}',
                common_suffix)
        retv = retv.rstrip(os.path.sep)
    else:
        retv = old_path + ' -> ' + new_path

    return retv

def diff_filter_is_valid(filter):
    return filter and (filter.upper() == filter or filter.lower() == filter)

def diff_filter_matches(filter, delta_status):
    assert diff_filter_is_valid(filter)

    status_code = gittools.DELTA_STATUS_CODE[delta_status]
    if filter[0].isupper():
        return status_code in filter
    else:
        return status_code.lower() not in filter

def format_diff(repo, git_diff, abbreviate=True, obey_cwd=True, filter=None):
    for delta in git_diff.deltas:
        if filter and not diff_filter_matches(filter, delta.status):
            continue

        if obey_cwd:
            old_path = os.path.relpath(os.path.join(repo.path, delta.old_file.path))
            new_path = os.path.relpath(os.path.join(repo.path, delta.new_file.path))
        else:
            old_path = delta.old_file.path
            new_path = delta.new_file.path

        if delta.old_file.path == delta.new_file.path:
            path_info = old_path
        else:
            path_info = format_path_change(old_path, new_path)

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

def format_raw_diff(repo, git_diff, null_terminated=False, filter=None):
    if null_terminated:
        path_separator = '\0'
        record_separator = '\0'
    else:
        path_separator = '\t'
        record_separator = '\n'

    for delta in git_diff.deltas:
        if filter and not diff_filter_matches(filter, delta.status):
            continue

        old_path = delta.old_file.path
        new_path = delta.new_file.path

        if delta.old_file.path == delta.new_file.path:
            path_info = old_path
        else:
            path_info = old_path + path_separator + new_path

        if delta.similarity != 100 and delta.status != pygit2.GIT_DELTA_ADDED:
            old_blob = repo.git.get(delta.old_file.id)
            old_digest = old_blob.data.decode().strip()
        else:
            old_digest = '-'

        digest_size = hashing.digest_size()

        yield '{status} {old_digest:{digest_w}}{path_sep}{path_info}{record_sep}'.format(
            status=gittools.DELTA_STATUS_CODE[delta.status],
            old_digest=old_digest[0:digest_size],
            digest_w=digest_size,
            path_sep=path_separator,
            path_info=path_info,
            record_sep=record_separator)

def format_ignored_paths(repo, paths, obey_cwd=True):
    for path in paths:
        maybe_trailing_sep = os.sep if os.path.isdir(path) else ''

        if obey_cwd:
            path = os.path.relpath(os.path.join(repo.path, path))

        yield '  {}{}\n'.format(path, maybe_trailing_sep)

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
    """sod - a digest tracker

    Sod is a special-purpose revision control system focused on efficient and
    transparent large file support at the cost of limited rollback ability.

    Motto: What are backups for if you do not review what you back up?

    In contrast to total data loss, partial data loss or corruption as the
    possible result of incidents ranging from user errors to data degradation
    (bit rot) easily goes unnoticed long enough to propagate into backups and
    eventually destroy the last available copy of the original data.

    Protecting data integrity using conventional means is not always feasible.
    Consider a large collection of binary files like media files maintained on
    a laptop.  Available storage may be too limited for RAID implementation.
    Similar is the situation with conventional revision control systems, which
    usually keep a pristine copy of each managed file, and those that don't
    may store repository files primarily in a private area and expose them
    using (symbolic) links, breaking transparency.  Detecting changes by
    comparing data to (remote) backups may be too slow for regular use and
    backups may not be always accessible.

    Sod approaches this by tracking nothing but cryptographic digests of the
    actual data (Efficient), keeping the actual data intact (Transparent) and
    relying on auxiliary data stores for rollback purposes (Limited
    rollback).

    Sod is meant for single-user, single-history use - it provides no means of
    replicating history between repositories or maintaining alternate
    histories (Special-purpose).


    INITIALIZATION

    Sod repository can be initialized with the 'sod init' command executed
    under an existing directory.  Sod will store its data under a subdirectory
    named '.sod'.  Initially, a Sod repository has no history.  Any
    pre-existing files found under the repository at initialization time are
    treated equally as files appearing later after initialization.


    RECORDING CHANGES

    Changes since the last commit, as well as the initially untracked content
    under a freshly initialized repository, can be listed with the 'sod
    status' command.

    Recording changes is a two phase process.  First the changes to be
    recorded with the next commit are prepared (staged) with the 'sod add'
    command.  Changes can be added step-by-step with multiple 'sod add'
    invocations and any change previously staged can be unstaged with the 'sod
    reset' command during this preparation phase.  The 'sod status' command
    lists changes that are staged for next commit separately from those that
    are not staged.

    Once finished, the staged changes can be recorded with the 'sod commit'
    command.  All commits in repository history can be listed with the 'sod
    log' command.


    UNDOING CHANGES

    If a particular revision of a file is to be restored, the digest recorded
    by Sod can be used to locate an exact copy of that file revision e.g. on
    a backup.  Sod can assist that with the 'sod restore' command, accompanied
    by the 'sod aux' group of commands for management of the so called
    auxiliary data stores, the possible sources of older file revisions.

    An auxiliary data store provides one or more snapshots of the original Sod
    repository together with an information on which revision the snapshot was
    taken at (or more correctly "taken after" - a snapshot taken while
    uncommitted changes existed does not fully match the said revision).

    In the output of the 'sod log' command, each revision with snapshots
    available is annotated with the snapshots listed as
    '<aux-name>[/<snapshot-id>]', omitting the optional part for stores
    providing just single snapshot.

    The simplest form of an auxiliary data store is a plain copy of the
    original Sod repository. It may be a local copy or a remote one, in the
    latter case accessed via SSH. Use 'sox aux add --help-types' to learn about
    the possible auxiliary data store types.

    The 'snapshot.command' configuration option can be used to let Sod trigger
    snapshot creation automatically whenever a new content is committed. See
    the 'sod config' and 'sod commit' commands for more information.


    IGNORED PATHS

    Sod automatically ignores any directory that looks like a Git repository,
    SVN repository or snapper's snapshot directory. Additionally, any directory
    which contains a file named '.sodignore' is ignored. Ignoring individual
    files is not possible. Use the 'sod status --ignored' command to see the
    list of ignored files.
    """

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
@click.option('--rename-limit', default=repository.DIFF_RENAME_LIMIT,
        help='Maximum number of file renames to try to detect')
@click.option('--ignored', is_flag=True, help='Show ignored files')
@click.argument('paths', nargs=-1)
@pass_repository
def status(repository, staged, rehash, abbrev, rename_limit, ignored, paths):
    """Summarize changes since last commit."""
    abspaths = tuple(map(os.path.abspath, paths))
    repository.DIFF_RENAME_LIMIT = rename_limit

    diff_cached = repository.diff_staged(abspaths)

    if not staged:
        diff_not_staged = repository.diff_not_staged(abspaths, rehash)

    if ignored:
        ignored_paths = repository.ignored_paths(abspaths)

    click.echo('Changes staged for commit:')
    click.echo(''.join(format_diff(repository, diff_cached, abbreviate=abbrev)))

    if not staged:
        click.echo('Changes not staged for commit:')
        click.echo(''.join(format_diff(repository, diff_not_staged, abbreviate=abbrev)))

    if ignored:
        click.echo('Ignored files:')
        click.echo(''.join(format_ignored_paths(repository, ignored_paths)))

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
@click.option('--no-snapshot', is_flag=True, help='Suppress automatic snapshot creation')
@pass_repository
def commit(repository, message, no_snapshot):
    """Record changes to the repository.

    When the 'snapshot.command' configuration option is set and the changes
    staged for this commit introduce a new content (new files added or existing
    modified), the shell command denoted by the 'snapshot.command'
    configuration option will be executed unless the '--no-snapshot' option is
    passed.
    """
    repository.commit(message, no_snapshot)

@cli.command()
@click.option('--abbrev/--no-abbrev', default=True, help='Abbreviate old content digest')
@click.option('--rename-limit', default=repository.DIFF_RENAME_LIMIT,
        help='Maximum number of file renames to try to detect')
@pass_repository
def log(repository, abbrev, rename_limit):
    """Show commit log."""
    repository.DIFF_RENAME_LIMIT = rename_limit

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

@cli.command()
@click.option('--abbrev/--no-abbrev', default=True, help='Abbreviate old content digest')
@click.option('--raw', is_flag=True, help='''Output in a format suitable for parsing.
    Implies '--no-abbrev'.''')
@click.option('--null-terminated', is_flag=True, help='''Use NULs as output fields terminators.
    Implies '--raw'.''')
@click.option('--filter', help='''Limit output to files that were Added (A),
    Copied (C), Deleted (D), Modified (M) or Renamed (R). Multiple filter
    characters may be passed.  Pass lower-case characters to select the
    complement.''')
@click.option('--rename-limit', default=repository.DIFF_RENAME_LIMIT,
        help='Maximum number of file renames to try to detect')
@click.argument('old-commit')
@click.argument('new-commit', default='HEAD')
@pass_repository
def diff(repository, abbrev, raw, null_terminated, filter, rename_limit, old_commit, new_commit):
    """Show differences between two commits. New commit defaults to 'HEAD'.

    When '--raw' is used, the output format is:

    STATUS_LETTER ' ' OLD_DIGEST '<TAB>' OLD_PATH ['<TAB>' NEW_PATH] '<LF>'

    When '--raw' and '--null-terminated' is used, the output format is:

    STATUS_LETTER ' ' OLD_DIGEST '<NUL>' OLD_PATH ['<NUL>' NEW_PATH] '<NUL>'

    Possible STATUS_LETTER is any of the letters the '--filter' option accepts.
    """
    if filter and not diff_filter_is_valid(filter):
        raise Error('Not a valid filter string: ' + filter)

    repository.DIFF_RENAME_LIMIT = rename_limit

    diff = repository.diff(old_commit, new_commit)

    if null_terminated:
        raw = True

    if raw:
        print(*format_raw_diff(repository, diff,
            null_terminated=null_terminated, filter=filter), sep='', end='')
    else:
        click.echo_via_pager(format_diff(repository, diff, abbreviate=abbrev,
            obey_cwd=False, filter=filter))

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

@cli.command()
@click.argument('assignment', metavar='[NAME[=[VALUE]]]', required=False)
@pass_repository
def config(repository, assignment):
    """Show or set configuration options.

    When invoked without argument, list all options with their values. When
    invoked with NAME only, show the particular option value.  When just the
    VALUE is omitted, clear the option value. Otherwise assign the VALUE.

    The list of configuration options follows:

    snapshot.command STRING

        Use the command STRING as a system command to automatically create a
        file system snapshot whenever a new content is comitted (new files
        added or existing modified). The command STRING will be executed as is
        in a subshell.

    """
    if assignment == '' or assignment and assignment.startswith('='):
        click.UsageError('Got empty name')

    name = None
    op = None
    value = None
    if assignment:
        name, op, value = assignment.partition('=')

    if not name:
        for pair in repository.get_config():
            click.echo('='.join(pair))
    elif not op:
        click.echo(repository.get_config_value(name))
    elif not value:
        repository.clear_config(name)
    else:
        repository.set_config(name, value)
