from datetime import datetime
import os
import pytest
import textwrap

from . import utils

STATUS_STAGED_HEADING = 'Changes staged for commit:'
STATUS_UNSTAGED_HEADING = 'Changes not staged for commit:'

def test_core(testcli):
    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}

    """)

    utils.write('a.txt', 'a content')
    utils.write('b.txt', 'b content')
    utils.write('c.txt', 'c content')
    os.makedirs('x/y')
    utils.write('x/y/d.txt', 'd content')
    utils.write('x/y/e.txt', 'e content')
    utils.write('x/y/f.txt', 'f content')

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          added:         -           a.txt
          added:         -           b.txt
          added:         -           c.txt
          added:         -           x/y/d.txt
          added:         -           x/y/e.txt
          added:         -           x/y/f.txt

    """)

    testcli(['add', 'a.txt'])
    testcli(['add', 'c.txt'])
    testcli(['add', 'x/y/e.txt'])

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          added:         -           a.txt
          added:         -           c.txt
          added:         -           x/y/e.txt

        {STATUS_UNSTAGED_HEADING}
          added:         -           b.txt
          added:         -           x/y/d.txt
          added:         -           x/y/f.txt

    """)

    os.environ['SOD_COMMIT_DATE'] = utils.format_commit_date(1970, 1, 1)
    testcli(['commit', '-m', 'Initial'])

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          added:         -           b.txt
          added:         -           x/y/d.txt
          added:         -           x/y/f.txt

    """)

    utils.write('a.txt', 'a updated content')
    os.remove('c.txt')
    os.rename('x/y/e.txt', 'x/y/E.txt')

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a.txt
          added:         -           b.txt
          deleted:       34f0bbc310  c.txt
          renamed:       -           x/y/{{e.txt -> E.txt}}
          added:         -           x/y/d.txt
          added:         -           x/y/f.txt

    """)

    testcli(['add', 'c.txt'])
    testcli(['add', 'x/y/e.txt'])

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       34f0bbc310  c.txt
          deleted:       776b0e8fbd  x/y/e.txt

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a.txt
          added:         -           b.txt
          added:         -           x/y/E.txt
          added:         -           x/y/d.txt
          added:         -           x/y/f.txt

    """)

    testcli(['add', 'x/y/E.txt'])

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       34f0bbc310  c.txt
          renamed:       -           x/y/{{e.txt -> E.txt}}

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a.txt
          added:         -           b.txt
          added:         -           x/y/d.txt
          added:         -           x/y/f.txt

    """)

    testcli(['reset', 'x/y/e.txt'])

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       34f0bbc310  c.txt
          added:         -           x/y/E.txt

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a.txt
          added:         -           b.txt
          added:         -           x/y/d.txt
          deleted:       776b0e8fbd  x/y/e.txt
          added:         -           x/y/f.txt

    """)

    testcli(['add', 'a.txt'])
    testcli(['add', 'x/y/e.txt'])

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          modified:      112c74d3c7  a.txt
          deleted:       34f0bbc310  c.txt
          renamed:       -           x/y/{{e.txt -> E.txt}}

        {STATUS_UNSTAGED_HEADING}
          added:         -           b.txt
          added:         -           x/y/d.txt
          added:         -           x/y/f.txt

    """)

    os.environ['SOD_COMMIT_DATE'] = utils.format_commit_date(1970, 1, 2)
    testcli(['commit', '-m', 'Update 1'])

    result = testcli(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          added:         -           b.txt
          added:         -           x/y/d.txt
          added:         -           x/y/f.txt

    """)

    result = testcli(['log'])
    assert result.output == textwrap.dedent(f"""\
        commit ce2ae575feb8305d85cb41667b15aae02dfe5e43 (HEAD)
        Date: Fri Jan  2 01:00:00 1970

            Update 1

          modified:      112c74d3c7  a.txt
          deleted:       34f0bbc310  c.txt
          renamed:       -           x/y/{{e.txt -> E.txt}}

        commit fbae4e311218d479e4e6e5fa9f269796b319e5c9
        Date: Thu Jan  1 01:00:00 1970

            Initial

          added:         -           a.txt
          added:         -           c.txt
          added:         -           x/y/e.txt


    """)
