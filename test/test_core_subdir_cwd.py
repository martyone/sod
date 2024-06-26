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

from datetime import datetime
import os
import pytest
import re
import textwrap

from . import utils
from .utils import STATUS_STAGED_HEADING, STATUS_UNSTAGED_HEADING, INITIAL_COMMIT_LOG

def test_unstaged_additions_status(no_commit_repo):
    with utils.temporary_chdir('x'):
        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}

            {STATUS_UNSTAGED_HEADING}
              added:         -           ../a  (-_*).txt
              added:         -           ../b  (-_*).txt
              added:         -           ../c  (-_*).txt
              added:         -           y/d  (-_*).txt
              added:         -           y/e  (-_*).txt
              added:         -           y/f  (-_*).txt

        """)

def test_stage_additions(no_commit_repo):
    with utils.temporary_chdir('x'):
        utils.run(['add', '../a  (-_*).txt'])
        utils.run(['add', '../c  (-_*).txt'])
        utils.run(['add', 'y/e  (-_*).txt'])

        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}
              added:         -           ../a  (-_*).txt
              added:         -           ../c  (-_*).txt
              added:         -           y/e  (-_*).txt

            {STATUS_UNSTAGED_HEADING}
              added:         -           ../b  (-_*).txt
              added:         -           y/d  (-_*).txt
              added:         -           y/f  (-_*).txt

        """)

def test_stage_additions_from_dot(no_commit_repo):
    with utils.temporary_chdir('x'):
        utils.run(['add', '.'])

        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}
              added:         -           y/d  (-_*).txt
              added:         -           y/e  (-_*).txt
              added:         -           y/f  (-_*).txt

            {STATUS_UNSTAGED_HEADING}
              added:         -           ../a  (-_*).txt
              added:         -           ../b  (-_*).txt
              added:         -           ../c  (-_*).txt

        """)

def test_stage_additions_by_dir(no_commit_repo):
    with utils.temporary_chdir('x'):
        utils.run(['add', 'y'])

        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}
              added:         -           y/d  (-_*).txt
              added:         -           y/e  (-_*).txt
              added:         -           y/f  (-_*).txt

            {STATUS_UNSTAGED_HEADING}
              added:         -           ../a  (-_*).txt
              added:         -           ../b  (-_*).txt
              added:         -           ../c  (-_*).txt

        """)

class TestCommitAdditions:
    @pytest.fixture(scope='class', autouse=True)
    def commit_additions(self, no_commit_repo):
        with utils.temporary_chdir('x'):
            utils.run(['add', '../a  (-_*).txt'])
            utils.run(['add', '../c  (-_*).txt'])
            utils.run(['add', 'y/e  (-_*).txt'])
            with utils.commit_date(1970, 1, 1):
                utils.run(['commit', '-m', 'Initial'])

    def test_status(self):
        with utils.temporary_chdir('x'):
            result = utils.run(['status'])
            assert result.output == textwrap.dedent(f"""\
                {STATUS_STAGED_HEADING}

                {STATUS_UNSTAGED_HEADING}
                  added:         -           ../b  (-_*).txt
                  added:         -           y/d  (-_*).txt
                  added:         -           y/f  (-_*).txt

            """)

    def test_log(self):
        with utils.temporary_chdir('x'):
            result = utils.run(['log'])
            assert result.output == textwrap.dedent("""\
                commit e3df93855539e590a6c185b388f69f3f5f80a7b2 (HEAD)
                Date: Thu Jan  1 01:00:00 1970

                    Initial

                  added:         -           a  (-_*).txt
                  added:         -           c  (-_*).txt
                  added:         -           x/y/e  (-_*).txt


            """)
