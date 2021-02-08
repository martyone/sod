from click.testing import CliRunner
from datetime import datetime, timezone
import os
import sod.sod

runner = CliRunner()

def run(args, *, expected_exit_code=0):
    result = runner.invoke(sod.sod.cli, args, catch_exceptions=False)

    if expected_exit_code == 0:
        assert result.exit_code == 0, "Command exited with non-zero exit code " \
            + f"{result.exit_code}. output: '''{result.output}'''"
    else:
        assert result.exit_code == expected_exit_code

    return result

def write(path, content):
    with open(path, 'w') as f:
        f.write(content)

def format_commit_date(year, month, day, hour=0, minute=0, second=0):
    dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    return str(int(dt.timestamp())) + ' +0000'
