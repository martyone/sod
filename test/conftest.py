from click.testing import CliRunner
import os
import pytest

import sod.sod
from . import utils

@pytest.fixture
def testcli():
    runner = CliRunner()
    with runner.isolated_filesystem():
        def invoke(args, *, expected_exit_code=0):
            result = runner.invoke(sod.sod.cli, args, catch_exceptions=False)

            if expected_exit_code == 0:
                assert result.exit_code == 0, "Command exited with non-zero exit code " \
                    + f"{result.exit_code}. output: '''{result.output}'''"
            else:
                assert result.exit_code == expected_exit_code

            return result


        invoke(['init'])

        yield invoke
