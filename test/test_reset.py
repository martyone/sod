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
from .utils import STATUS_STAGED_HEADING, STATUS_UNSTAGED_HEADING

def test_reset_addition(no_commit_repo):
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])
    utils.run(['reset', 'a  (-_*).txt'])
    utils.run(['reset', 'x/y/e  (-_*).txt'])
    result = utils.run(['status', '--staged'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

    """)

def test_reset_addition_from_dot(no_commit_repo):
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])
    utils.run(['reset', '.'])
    result = utils.run(['status', '--staged'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

    """)

def test_reset_addition_by_dir(no_commit_repo):
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])
    utils.run(['reset', 'x'])
    result = utils.run(['status', '--staged'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          added:         -           a  (-_*).txt

    """)

def test_reset_modifications(one_commit_repo):
    utils.write('a  (-_*).txt', 'a updated content')
    utils.write('x/y/e  (-_*).txt', 'e updated content')
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])
    utils.run(['reset', 'a  (-_*).txt'])
    utils.run(['reset', 'x'])

    result = utils.run(['status', '--staged'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

    """)

def test_reset_deletions(one_commit_repo):
    os.remove('a  (-_*).txt')
    os.remove('x/y/e  (-_*).txt')
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])
    utils.run(['reset', 'a  (-_*).txt'])
    utils.run(['reset', 'x'])

    result = utils.run(['status', '--staged'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

    """)

def test_reset_renames_partial(one_commit_repo):
    os.rename('a  (-_*).txt', 'A  (-_*).txt')
    os.rename('x/y/e  (-_*).txt', 'x/y/E  (-_*).txt')
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'x/y/E  (-_*).txt'])
    utils.run(['reset', 'a  (-_*).txt'])
    utils.run(['reset', 'x'])

    result = utils.run(['status', '--staged'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

    """)

def test_reset_renames(one_commit_repo):
    os.rename('a  (-_*).txt', 'A  (-_*).txt')
    os.rename('x/y/e  (-_*).txt', 'x/y/E  (-_*).txt')
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'A  (-_*).txt'])
    utils.run(['add', 'x'])
    utils.run(['reset', 'a  (-_*).txt'])
    utils.run(['reset', 'A  (-_*).txt'])
    utils.run(['reset', 'x'])

    result = utils.run(['status', '--staged'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

    """)
