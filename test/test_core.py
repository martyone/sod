from datetime import datetime
import math
import os
import pytest
import re
import textwrap

from . import utils

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

def test_empty_repo_status(empty_repo):
    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}

    """)

def test_unstaged_additions_status(no_commit_repo):
    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          added:         -           a  (-_*).txt
          added:         -           b  (-_*).txt
          added:         -           c  (-_*).txt
          added:         -           x/y/d  (-_*).txt
          added:         -           x/y/e  (-_*).txt
          added:         -           x/y/f  (-_*).txt

    """)

def test_stage_additions(no_commit_repo):
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'c  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          added:         -           a  (-_*).txt
          added:         -           c  (-_*).txt
          added:         -           x/y/e  (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          added:         -           b  (-_*).txt
          added:         -           x/y/d  (-_*).txt
          added:         -           x/y/f  (-_*).txt

    """)

@pytest.mark.xfail
def test_stage_additions_from_dot(no_commit_repo):
    utils.run(['add', '.'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          added:         -           a  (-_*).txt
          added:         -           b  (-_*).txt
          added:         -           c  (-_*).txt
          added:         -           x/y/d  (-_*).txt
          added:         -           x/y/e  (-_*).txt
          added:         -           x/y/f  (-_*).txt

        {STATUS_UNSTAGED_HEADING}

    """)

def test_stage_additions_by_dir(no_commit_repo):
    utils.run(['add', 'x'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          added:         -           x/y/d  (-_*).txt
          added:         -           x/y/e  (-_*).txt
          added:         -           x/y/f  (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          added:         -           a  (-_*).txt
          added:         -           b  (-_*).txt
          added:         -           c  (-_*).txt

    """)

class TestCommitAdditions:
    @pytest.fixture(scope='class', autouse=True)
    def commit_additions(self, no_commit_repo):
        utils.run(['add', 'a  (-_*).txt'])
        utils.run(['add', 'c  (-_*).txt'])
        utils.run(['add', 'x/y/e  (-_*).txt'])
        with utils.commit_date(1970, 1, 1):
            utils.run(['commit', '-m', 'Initial'])

    def test_status(self):
        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}

            {STATUS_UNSTAGED_HEADING}
              added:         -           b  (-_*).txt
              added:         -           x/y/d  (-_*).txt
              added:         -           x/y/f  (-_*).txt

        """)

    def test_log(self):
        result = utils.run(['log'])
        assert result.output == textwrap.dedent("""\
            commit e3df93855539e590a6c185b388f69f3f5f80a7b2 (HEAD)
            Date: Thu Jan  1 01:00:00 1970

                Initial

              added:         -           a  (-_*).txt
              added:         -           c  (-_*).txt
              added:         -           x/y/e  (-_*).txt


        """)

def test_stage_modifications(one_commit_repo):
    utils.write('a  (-_*).txt', 'a updated content')
    utils.write('x/y/e  (-_*).txt', 'e updated content')
    utils.run(['add', 'a  (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          modified:      112c74d3c7  a  (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          modified:      776b0e8fbd  x/y/e  (-_*).txt

    """)

class TestCommitModifications:
    @pytest.fixture(scope='class', autouse=True)
    def commit_modifications(self, one_commit_repo):
        utils.write('a  (-_*).txt', 'a updated content')
        utils.write('x/y/e  (-_*).txt', 'e updated content')
        utils.run(['add', 'a  (-_*).txt'])
        with utils.commit_date(1970, 1, 2):
            utils.run(['commit', '-m', 'Update 1'])

    def test_status(self):
        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}

            {STATUS_UNSTAGED_HEADING}
              modified:      776b0e8fbd  x/y/e  (-_*).txt

        """)

    def test_log(self):
        result = utils.run(['log'])
        assert result.output == textwrap.dedent("""\
            commit 7868c3880c865226b10511ad19c9c370980e1679 (HEAD)
            Date: Fri Jan  2 01:00:00 1970

                Update 1

              modified:      112c74d3c7  a  (-_*).txt

        """) + INITIAL_COMMIT_LOG

def test_stage_deletions(one_commit_repo):
    os.remove('a  (-_*).txt')
    os.remove('c  (-_*).txt')
    os.remove('x/y/e  (-_*).txt')
    utils.run(['add', 'c  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       34f0bbc310  c  (-_*).txt
          deleted:       776b0e8fbd  x/y/e  (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          deleted:       112c74d3c7  a  (-_*).txt

    """)

class TestCommitDeletions:
    @pytest.fixture(scope='class', autouse=True)
    def commit_deletions(self, one_commit_repo):
        os.remove('a  (-_*).txt')
        os.remove('c  (-_*).txt')
        os.remove('x/y/e  (-_*).txt')
        utils.run(['add', 'c  (-_*).txt'])
        utils.run(['add', 'x/y/e  (-_*).txt'])
        with utils.commit_date(1970, 1, 2):
            utils.run(['commit', '-m', 'Update 1'])

    def test_status(self):
        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}

            {STATUS_UNSTAGED_HEADING}
              deleted:       112c74d3c7  a  (-_*).txt

        """)

    def test_log(self):
        result = utils.run(['log'])
        assert result.output == textwrap.dedent("""\
            commit 2cd8622c34df084b09bfae219863c1d23616611a (HEAD)
            Date: Fri Jan  2 01:00:00 1970

                Update 1

              deleted:       34f0bbc310  c  (-_*).txt
              deleted:       776b0e8fbd  x/y/e  (-_*).txt

        """) + INITIAL_COMMIT_LOG


def test_stage_renames_partial(one_commit_repo):
    os.rename('a  (-_*).txt', 'A  (-_*).txt')
    os.rename('x/y/e  (-_*).txt', 'x/y/E  (-_*).txt')
    utils.run(['add', 'a  (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       112c74d3c7  a  (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          added:         -           A  (-_*).txt
          renamed:       -           x/y/{{e  (-_*).txt -> E  (-_*).txt}}

    """)

def test_stage_renames(one_commit_repo):
    os.rename('a  (-_*).txt', 'A  (-_*).txt')
    os.rename('x/y/e  (-_*).txt', 'x/y/E  (-_*).txt')
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'A  (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          renamed:       -           a  (-_*).txt -> A  (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          renamed:       -           x/y/{{e  (-_*).txt -> E  (-_*).txt}}

    """)

class TestCommitRenames:
    @pytest.fixture(scope='class', autouse=True)
    def commit_renames(self, one_commit_repo):
        os.rename('a  (-_*).txt', 'A  (-_*).txt')
        os.rename('x/y/e  (-_*).txt', 'x/y/E  (-_*).txt')
        utils.run(['add', 'a  (-_*).txt'])
        utils.run(['add', 'A  (-_*).txt'])
        with utils.commit_date(1970, 1, 2):
            utils.run(['commit', '-m', 'Update 1'])

    def test_status(self):
        result = utils.run(['status'])
        assert result.output == textwrap.dedent(f"""\
            {STATUS_STAGED_HEADING}

            {STATUS_UNSTAGED_HEADING}
              renamed:       -           x/y/{{e  (-_*).txt -> E  (-_*).txt}}

        """)

    def test_log(self):
        result = utils.run(['log'])
        assert result.output == textwrap.dedent("""\
            commit bf76bea4807eaff5711ffa5d57e05b1234e78291 (HEAD)
            Date: Fri Jan  2 01:00:00 1970

                Update 1

              renamed:       -           a  (-_*).txt -> A  (-_*).txt

        """) + INITIAL_COMMIT_LOG

def test_commit_now(no_commit_repo):
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['commit', '-m', 'Initial'])
    result = utils.run(['log'])
    commit_date_str = re.search(r'^Date: (.*)$', result.output, re.MULTILINE).group(1)
    commit_date = datetime.strptime(commit_date_str, '%c')
    assert math.fabs(datetime.now().timestamp() - commit_date.timestamp()) < 10
