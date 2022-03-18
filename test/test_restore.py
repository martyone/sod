# This file is part of sod.
#
# Copyright (C) 2021,2022 Martin Kampas <martin.kampas@ubedi.net>
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
import math
import os
import pytest
import re
import textwrap

import sod
from . import utils
from .utils import STATUS_STAGED_HEADING, STATUS_UNSTAGED_HEADING, INITIAL_COMMIT_LOG

def test_aux_list_no_aux(one_commit_repo):
    result = utils.run(['aux', 'list'])
    assert result.output == textwrap.dedent("""\
    """)

def test_aux_list(three_commit_repo_with_aux_stores_not_updated):
    (three_commit_repo, aux1_url, aux2_url) = three_commit_repo_with_aux_stores_not_updated
    result = utils.run(['aux', 'list'])
    assert result.output == textwrap.dedent(f"""\
        aux1 {aux1_url} (plain)
        aux2 {aux2_url} (plain)
    """)

def test_aux_remove(three_commit_repo_with_aux_stores_not_updated):
    (three_commit_repo, aux1_url, aux2_url) = three_commit_repo_with_aux_stores_not_updated
    utils.run(['aux', 'remove', 'aux1'])
    result = utils.run(['aux', 'list'])
    assert result.output == textwrap.dedent(f"""\
        aux2 {aux2_url} (plain)
    """)

def test_update_one(three_commit_repo_with_aux_stores_not_updated):
    utils.run(['aux', 'update', 'aux1'])

    result = utils.run(['log'])
    assert result.output == textwrap.dedent("""\
        commit 881ca9b742d5384171f2adcbc728a25e0db2d7ae (HEAD, aux1/3)
        Date: Sat Jan  3 01:00:00 1970

            Change 2

          modified:      743ff5540b  B  (-_*).txt
          modified:      456b562d01  a  (-_*).txt

        commit 93cd0dfbd569e4c4edd20907df13799f36ee25f4 (aux1/2)
        Date: Fri Jan  2 01:00:00 1970

            Change 1

          renamed:       -           b  (-_*).txt -> B  (-_*).txt
          modified:      112c74d3c7  a  (-_*).txt
          modified:      5e713ffd37  x/y/d  (-_*).txt

        commit c272e1c23d120e124adb247be3d271a9d18079d3 (aux1/1)
        Date: Thu Jan  1 01:00:00 1970

            Initial

          added:         -           a  (-_*).txt
          added:         -           b  (-_*).txt
          added:         -           c  (-_*).txt
          added:         -           x/y/d  (-_*).txt
          added:         -           x/y/e  (-_*).txt
          added:         -           x/y/f  (-_*).txt


    """)

def test_update_all(three_commit_repo_with_aux_stores_not_updated):
    utils.run(['aux', 'update', '--all'])

    result = utils.run(['log'])
    assert result.output == textwrap.dedent("""\
        commit 881ca9b742d5384171f2adcbc728a25e0db2d7ae (HEAD, aux1/3, aux2/2)
        Date: Sat Jan  3 01:00:00 1970

            Change 2

          modified:      743ff5540b  B  (-_*).txt
          modified:      456b562d01  a  (-_*).txt

        commit 93cd0dfbd569e4c4edd20907df13799f36ee25f4 (aux1/2)
        Date: Fri Jan  2 01:00:00 1970

            Change 1

          renamed:       -           b  (-_*).txt -> B  (-_*).txt
          modified:      112c74d3c7  a  (-_*).txt
          modified:      5e713ffd37  x/y/d  (-_*).txt

        commit c272e1c23d120e124adb247be3d271a9d18079d3 (aux1/1, aux2/1)
        Date: Thu Jan  1 01:00:00 1970

            Initial

          added:         -           a  (-_*).txt
          added:         -           b  (-_*).txt
          added:         -           c  (-_*).txt
          added:         -           x/y/d  (-_*).txt
          added:         -           x/y/e  (-_*).txt
          added:         -           x/y/f  (-_*).txt


    """)

@pytest.fixture(params=['a  (-_*).txt', 'x/y/d  (-_*).txt'])
def file_to_restore(request):
    return request.param

def test_restore_fail_on_existing(three_commit_repo_with_aux_stores, file_to_restore):
    with pytest.raises(sod.Error) as e:
        utils.run(['restore', file_to_restore])
    assert 'refusing to overwrite' in str(e.value)

def test_restore_latest(three_commit_repo_with_aux_stores, file_to_restore):
    os.remove(file_to_restore)
    utils.run(['restore', file_to_restore])
    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}

    """)

def test_restore_latest_from(three_commit_repo_with_aux_stores, file_to_restore):
    os.remove(file_to_restore)
    utils.run(['restore', file_to_restore, '--from', 'aux1'])
    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}

    """)

def test_restore_older(three_commit_repo_with_aux_stores):
    os.remove('a  (-_*).txt')
    utils.run(['restore', 'a  (-_*).txt', '93cd0dfbd5'])
    assert utils.read('a  (-_*).txt') == 'a changed content'

def test_restore_older_by_ref_name(three_commit_repo_with_aux_stores):
    os.remove('a  (-_*).txt')
    utils.run(['restore', 'a  (-_*).txt', 'aux1/2'])
    assert utils.read('a  (-_*).txt') == 'a changed content'

def test_restore_older_from(three_commit_repo_with_aux_stores):
    os.remove('a  (-_*).txt')
    utils.run(['restore', 'a  (-_*).txt', '93cd0dfbd5', '--from', 'aux1'])
    assert utils.read('a  (-_*).txt') == 'a changed content'

def test_restore_older_from_not_found(three_commit_repo_with_aux_stores):
    os.remove('a  (-_*).txt')
    with pytest.raises(sod.Error) as e:
        utils.run(['restore', 'a  (-_*).txt', '93cd0dfbd5', '--from', 'aux2'])
    assert 'Could not restore' in str(e.value)

def test_restore_older_renamed(three_commit_repo_with_aux_stores):
    utils.run(['restore', 'b  (-_*).txt', 'c272e1c23d'])
    assert utils.read('b  (-_*).txt') == 'b content'
