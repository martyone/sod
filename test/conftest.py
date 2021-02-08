from click.testing import CliRunner
import os
import pytest

import sod.sod
from . import utils

@pytest.fixture
def chdir_tmp_path(tmp_path):
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(old_cwd)

@pytest.fixture
def empty_repo(chdir_tmp_path):
    utils.run(['init'])
    return chdir_tmp_path
