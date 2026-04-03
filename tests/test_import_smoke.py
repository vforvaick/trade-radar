from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_import_core_bot_modules():
    import bot.backtester  # noqa: F401
    import bot.discovery_engine  # noqa: F401
    import bot.main_multi  # noqa: F401
    import bot.passport_runner  # noqa: F401
    import bot.notifier  # noqa: F401


@pytest.mark.parametrize("script_name", ["run_twin_bots.py", "run_exit_opt.py"])
def test_script_bootstrap_can_import_bot_from_repo_root(script_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / script_name
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import runpy; runpy.run_path(r'%s', run_name='__smoke__')" % script_path,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
