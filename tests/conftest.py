"""Shared helpers: run cronx in-process and count runs through the engine API."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "cron-dialects" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cronx  # noqa: E402
from _dialect_table import DIALECTS  # noqa: E402
from _engine import parse, parse_instant, resolve_zone, run_instants  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("CRON_DIALECTS_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def cli(capsys):
    """cli(["next", ...]) -> (exit_code, stdout, stderr)"""

    def run(argv):
        code = cronx.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


@pytest.fixture
def cli_json(cli):
    def run(argv):
        code, out, err = cli(list(argv) + ["--json"])
        return code, json.loads(out), err

    return run


def count_runs(expr: str, dialect: str, tz: str = "UTC", start: str = "2027-01-01T00:00Z", days: int = 365) -> int:
    sched = parse(expr, dialect)
    zone = resolve_zone(tz)
    lo = parse_instant(start, zone)
    return len(run_instants(sched, zone, DIALECTS[dialect]["dst"], lo, lo + days * 86400))
