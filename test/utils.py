# This file is part of sod.
#
# Copyright (C) 2022 Martin Kampas <martin.kampas@ubedi.net>
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

from click.testing import CliRunner
import contextlib
from datetime import datetime, timezone
import os
import sod.sod

STATUS_STAGED_HEADING = 'Changes staged for commit:'
STATUS_UNSTAGED_HEADING = 'Changes not staged for commit:'
INITIAL_COMMIT_LOG = """\
commit c272e1c23d120e124adb247be3d271a9d18079d3
Date: Thu Jan  1 01:00:00 1970

    Initial

  added:         -           a  (-_*).txt
  added:         -           b  (-_*).txt
  added:         -           c  (-_*).txt
  added:         -           x/y/d  (-_*).txt
  added:         -           x/y/e  (-_*).txt
  added:         -           x/y/f  (-_*).txt


"""

runner = CliRunner()

def run(args, *, expected_exit_code=0):
    result = runner.invoke(sod.sod.cli, args, catch_exceptions=False)

    if expected_exit_code == 0:
        assert result.exit_code == 0, "Command exited with non-zero exit code " \
            + f"{result.exit_code}. output: '''{result.output}'''"
    else:
        assert result.exit_code == expected_exit_code

    return result

def read(path):
    with open(path, 'r') as f:
        return f.read()

def write(path, content):
    with open(path, 'w') as f:
        f.write(content)

def format_commit_date(year, month, day, hour=0, minute=0, second=0):
    dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    return str(int(dt.timestamp())) + ' +0000'

@contextlib.contextmanager
def commit_date(year, month, day, hour=0, minute=0, second=0):
    os.environ['SOD_COMMIT_DATE'] = format_commit_date(year, month, day, hour, minute, second)
    try:
        yield
    finally:
        del os.environ['SOD_COMMIT_DATE']

@contextlib.contextmanager
def temporary_chdir(path):
    old_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield path
    finally:
        os.chdir(old_cwd)
