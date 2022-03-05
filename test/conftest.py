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

import os
import pytest
import shutil
import sys

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

@pytest.fixture(scope='class', params=['file://', 'ssh://localhost'], ids=['file', 'ssh'])
def three_commit_repo_with_aux_stores_not_updated(request, one_commit_repo, tmp_path_factory):
    snapshot_prefix1 = tmp_path_factory.mktemp('snapshots')
    snapshot_prefix2 = tmp_path_factory.mktemp('snapshots')

    os.mkdir(os.path.join(snapshot_prefix1, '1'))
    shutil.copytree(one_commit_repo, os.path.join(snapshot_prefix1, '1/snapshot'))
    os.mkdir(os.path.join(snapshot_prefix2, '1'))
    shutil.copytree(one_commit_repo, os.path.join(snapshot_prefix2, '1/snapshot'))

    utils.write('a  (-_*).txt', 'a changed content')
    os.rename('b  (-_*).txt', 'B  (-_*).txt')
    utils.write('x/y/d  (-_*).txt', 'd changed content')
    utils.run(['add', '.'])
    with utils.commit_date(1970, 1, 2):
        utils.run(['commit', '-m', 'Change 1'])

    os.mkdir(os.path.join(snapshot_prefix1, '2'))
    shutil.copytree(one_commit_repo, os.path.join(snapshot_prefix1, '2/snapshot'))

    utils.write('a  (-_*).txt', 'a twice changed content')
    utils.write('B  (-_*).txt', 'b changed content')
    utils.run(['add', '.'])
    with utils.commit_date(1970, 1, 3):
        utils.run(['commit', '-m', 'Change 2'])

    os.mkdir(os.path.join(snapshot_prefix1, '3'))
    shutil.copytree(one_commit_repo, os.path.join(snapshot_prefix1, '3/snapshot'))
    os.mkdir(os.path.join(snapshot_prefix2, '2'))
    shutil.copytree(one_commit_repo, os.path.join(snapshot_prefix2, '2/snapshot'))

    # urllib.parse.urljoin does not work with 'ssh' scheme (see Python issue 18828)
    def make_aux_url(prefix):
        return request.param + str(prefix).replace(os.sep, '/') + '/*/snapshot'

    aux1_url = make_aux_url(snapshot_prefix1)
    aux2_url = make_aux_url(snapshot_prefix2)

    utils.run(['aux', 'add', 'aux1', aux1_url])
    utils.run(['aux', 'add', 'aux2', aux2_url])

    return (one_commit_repo, aux1_url, aux2_url)

@pytest.fixture(scope='class')
def three_commit_repo_with_aux_stores(three_commit_repo_with_aux_stores_not_updated):
    utils.run(['aux', 'update', '--all'])
    return three_commit_repo_with_aux_stores_not_updated
