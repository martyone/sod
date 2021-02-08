from datetime import datetime
import os
import pytest
import textwrap

from . import utils

STATUS_STAGED_HEADING = 'Changes staged for commit:'
STATUS_UNSTAGED_HEADING = 'Changes not staged for commit:'

def test_core(empty_repo):
    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}

    """)

    utils.write('a (-_*).txt', 'a content')
    utils.write('b (-_*).txt', 'b content')
    utils.write('c (-_*).txt', 'c content')
    os.makedirs('x/y')
    utils.write('x/y/d (-_*).txt', 'd content')
    utils.write('x/y/e (-_*).txt', 'e content')
    utils.write('x/y/f (-_*).txt', 'f content')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          added:         -           a (-_*).txt
          added:         -           b (-_*).txt
          added:         -           c (-_*).txt
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/e (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    utils.run(['add', 'a (-_*).txt'])
    utils.run(['add', 'c (-_*).txt'])
    utils.run(['add', 'x/y/e (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          added:         -           a (-_*).txt
          added:         -           c (-_*).txt
          added:         -           x/y/e (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          added:         -           b (-_*).txt
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    os.environ['SOD_COMMIT_DATE'] = utils.format_commit_date(1970, 1, 1)
    utils.run(['commit', '-m', 'Initial'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          added:         -           b (-_*).txt
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    utils.write('a (-_*).txt', 'a updated content')
    os.remove('c (-_*).txt')
    os.rename('x/y/e (-_*).txt', 'x/y/E (-_*).txt')

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a (-_*).txt
          added:         -           b (-_*).txt
          deleted:       34f0bbc310  c (-_*).txt
          renamed:       -           x/y/{{e (-_*).txt -> E (-_*).txt}}
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    utils.run(['add', 'c (-_*).txt'])
    utils.run(['add', 'x/y/e (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       34f0bbc310  c (-_*).txt
          deleted:       776b0e8fbd  x/y/e (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a (-_*).txt
          added:         -           b (-_*).txt
          added:         -           x/y/E (-_*).txt
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    utils.run(['add', 'x/y/E (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       34f0bbc310  c (-_*).txt
          renamed:       -           x/y/{{e (-_*).txt -> E (-_*).txt}}

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a (-_*).txt
          added:         -           b (-_*).txt
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    utils.run(['reset', 'x/y/e (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          deleted:       34f0bbc310  c (-_*).txt
          added:         -           x/y/E (-_*).txt

        {STATUS_UNSTAGED_HEADING}
          modified:      112c74d3c7  a (-_*).txt
          added:         -           b (-_*).txt
          added:         -           x/y/d (-_*).txt
          deleted:       776b0e8fbd  x/y/e (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    utils.run(['add', 'a (-_*).txt'])
    utils.run(['add', 'x/y/e (-_*).txt'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}
          modified:      112c74d3c7  a (-_*).txt
          deleted:       34f0bbc310  c (-_*).txt
          renamed:       -           x/y/{{e (-_*).txt -> E (-_*).txt}}

        {STATUS_UNSTAGED_HEADING}
          added:         -           b (-_*).txt
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    os.environ['SOD_COMMIT_DATE'] = utils.format_commit_date(1970, 1, 2)
    utils.run(['commit', '-m', 'Update 1'])

    result = utils.run(['status'])
    assert result.output == textwrap.dedent(f"""\
        {STATUS_STAGED_HEADING}

        {STATUS_UNSTAGED_HEADING}
          added:         -           b (-_*).txt
          added:         -           x/y/d (-_*).txt
          added:         -           x/y/f (-_*).txt

    """)

    result = utils.run(['log'])
    assert result.output == textwrap.dedent(f"""\
        commit e3773e8b4337e2b2709a4f1b0976f42b55884c96 (HEAD)
        Date: Fri Jan  2 01:00:00 1970

            Update 1

          modified:      112c74d3c7  a (-_*).txt
          deleted:       34f0bbc310  c (-_*).txt
          renamed:       -           x/y/{{e (-_*).txt -> E (-_*).txt}}

        commit f3fdfaa0b19548074c5d9879e98b20c2749dad78
        Date: Thu Jan  1 01:00:00 1970

            Initial

          added:         -           a (-_*).txt
          added:         -           c (-_*).txt
          added:         -           x/y/e (-_*).txt


    """)
