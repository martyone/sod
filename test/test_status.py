# This file is part of sod.
#
# Copyright (C) 2021 Martin Kampas <martin.kampas@ubedi.net>
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

from datetime import datetime
import os
import pytest
import re
import textwrap

from . import utils
from .utils import STATUS_STAGED_HEADING, STATUS_UNSTAGED_HEADING, INITIAL_COMMIT_LOG

# TODO: rehash

def test_constrained_status(no_commit_repo):
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])

    result = utils.run(['status', 'x', 'a  (-_*).txt'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          added:         -           a  (-_*).txt
          added:         -           x/y/e  (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          added:         -           x/y/d  (-_*).txt
          added:         -           x/y/f  (-_*).txt

    """)

def test_constrained_status_subdir_cwd(no_commit_repo):
    with utils.temporary_chdir('x'):
        utils.run(['add', '../a  (-_*).txt'])
        utils.run(['add', 'y/e  (-_*).txt'])

        result = utils.run(['status', 'y', '../a  (-_*).txt'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}
              added:         -           ../a  (-_*).txt
              added:         -           y/e  (-_*).txt

            {STATUS_UNSTAGED_HEADING}
              added:         -           y/d  (-_*).txt
              added:         -           y/f  (-_*).txt

        """)

def test_rename_level_1_dir_status(one_commit_repo):
    os.rename('x', 'X')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          renamed:       -           {{x -> X}}/y/d  (-_*).txt
          renamed:       -           {{x -> X}}/y/e  (-_*).txt
          renamed:       -           {{x -> X}}/y/f  (-_*).txt

    """)

def test_rename_level_1_and_2_dir_status(one_commit_repo):
    os.rename('x', 'X')
    os.rename('X/y', 'X/Y')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          renamed:       -           {{x/y -> X/Y}}/d  (-_*).txt
          renamed:       -           {{x/y -> X/Y}}/e  (-_*).txt
          renamed:       -           {{x/y -> X/Y}}/f  (-_*).txt

    """)

def test_rename_level_2_dir_status(one_commit_repo):
    os.rename('x/y', 'x/Y')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          renamed:       -           x/{{y -> Y}}/d  (-_*).txt
          renamed:       -           x/{{y -> Y}}/e  (-_*).txt
          renamed:       -           x/{{y -> Y}}/f  (-_*).txt

    """)

def test_move_level_2_dir_up_status(one_commit_repo):
    os.rename('x/y', 'y')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          renamed:       -           {{x/y -> y}}/d  (-_*).txt
          renamed:       -           {{x/y -> y}}/e  (-_*).txt
          renamed:       -           {{x/y -> y}}/f  (-_*).txt

    """)

def test_move_level_3_file_up_status(one_commit_repo):
    os.rename('x/y/d  (-_*).txt', 'x/d  (-_*).txt')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          renamed:       -           {{x/y -> x}}/d  (-_*).txt

    """)

def test_move_level_1_file_into_subdir_status(one_commit_repo):
    os.rename('a  (-_*).txt', 'x/a  (-_*).txt')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          renamed:       -           a  (-_*).txt -> x/a  (-_*).txt

    """)
