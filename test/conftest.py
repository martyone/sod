import os
import pytest

import sod.sod
from . import utils

@pytest.fixture(scope='class')
def uninitialized_repo(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp('repo')
    with utils.temporary_chdir(tmp_path):
        yield tmp_path

@pytest.fixture(scope='class')
def empty_repo(uninitialized_repo):
    utils.run(['init'])
    return uninitialized_repo

@pytest.fixture(scope='class')
def no_commit_repo(empty_repo):
    utils.write('a  (-_*).txt', 'a content')
    utils.write('b  (-_*).txt', 'b content')
    utils.write('c  (-_*).txt', 'c content')
    os.makedirs('x/y')
    utils.write('x/y/d  (-_*).txt', 'd content')
    utils.write('x/y/e  (-_*).txt', 'e content')
    utils.write('x/y/f  (-_*).txt', 'f content')
    return empty_repo

@pytest.fixture(scope='class')
def one_commit_repo(no_commit_repo):
    utils.run(['add', 'a  (-_*).txt'])
    utils.run(['add', 'b  (-_*).txt'])
    utils.run(['add', 'c  (-_*).txt'])
    utils.run(['add', 'x/y/d  (-_*).txt'])
    utils.run(['add', 'x/y/e  (-_*).txt'])
    utils.run(['add', 'x/y/f  (-_*).txt'])
    with utils.commit_date(1970, 1, 1):
        utils.run(['commit', '-m', 'Initial'])
    return no_commit_repo
