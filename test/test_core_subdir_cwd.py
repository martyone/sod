from datetime import datetime
import os
import pytest
import re
import textwrap

from . import utils
from .utils import STATUS_STAGED_HEADING, STATUS_UNSTAGED_HEADING, INITIAL_COMMIT_LOG

@pytest.mark.xfail
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

@pytest.mark.xfail
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

@pytest.mark.xfail
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

@pytest.mark.xfail
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

    @pytest.mark.xfail
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

    @pytest.mark.xfail
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
