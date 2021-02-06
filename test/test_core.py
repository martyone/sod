import inspect
import pytest

STATUS_STAGED_HEADING = 'Changes staged for commit:'
STATUS_UNSTAGED_HEADING = 'Changes not staged for commit:'

def test_core(testcli):
    expected_status = inspect.cleandoc(f"""
    {STATUS_STAGED_HEADING}

    {STATUS_UNSTAGED_HEADING}
    """) + '\n\n'

    result = testcli(['status'])
    assert result.output == expected_status
