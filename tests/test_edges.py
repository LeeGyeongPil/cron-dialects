"""AC-5: boundaries, error paths, performance and standard-library-only imports."""
from __future__ import annotations

import ast
import subprocess
import sys
import time
import zoneinfo

import _engine
from _dialect_table import DIALECTS
from _engine import CronError, parse, parse_instant, resolve_zone, run_instants

from conftest import SCRIPTS, count_runs


def _first(cli_json, expr, dialect, start, *extra):
    code, data, _ = cli_json(["next", expr, "--dialect", dialect, "--from", start, "--count", "3", *extra])
    assert code == 0
    return [r["utc"] for r in data["runs"]]


def test_leap_day(cli_json):
    assert _first(cli_json, "0 0 29 2 *", "unix", "2027-01-01T00:00Z")[0] == "2028-02-29T00:00:00Z"


def test_quartz_w_does_not_cross_month_boundary(cli_json):
    # May 1st 2027 is a Saturday: 1W is Monday the 3rd, not Friday April 30th
    runs = _first(cli_json, "0 0 0 1W * ?", "quartz", "2027-05-01T00:00Z")
    assert runs[0] == "2027-05-03T00:00:00Z"


def test_quartz_w_last_day_sunday_moves_back(cli_json):
    # 31W in a month whose 31st is a Sunday -> Friday the 29th (Jan 2027: the 31st is a Sunday)
    runs = _first(cli_json, "0 0 0 31W 1 ?", "quartz", "2027-01-01T00:00Z")
    assert runs[0] == "2027-01-29T00:00:00Z"


def test_quartz_lw_and_l_offsets(cli_json):
    assert _first(cli_json, "0 0 0 LW 5 ?", "quartz", "2027-05-01T00:00Z")[0] == "2027-05-31T00:00:00Z"
    assert _first(cli_json, "0 0 0 LW 1 ?", "quartz", "2027-01-01T00:00Z")[0] == "2027-01-29T00:00:00Z"
    assert _first(cli_json, "0 0 0 L-2 2 ?", "quartz", "2027-01-01T00:00Z")[0] == "2027-02-26T00:00:00Z"
    assert _first(cli_json, "0 0 0 L 2 ?", "quartz", "2028-01-01T00:00Z")[0] == "2028-02-29T00:00:00Z"


def test_quartz_fifth_wednesday_skips_months_without_one(cli_json):
    runs = _first(cli_json, "0 0 0 ? * 4#5", "quartz", "2027-01-01T00:00Z")
    assert runs[0] == "2027-03-31T00:00:00Z"            # January 2027 and February 2027 have only four Wednesdays


def test_last_friday_and_bare_l(cli_json):
    assert _first(cli_json, "0 0 12 ? * 6L", "quartz", "2027-01-01T00:00Z")[0] == "2027-01-29T12:00:00Z"
    assert _first(cli_json, "0 0 12 ? * L", "quartz", "2027-01-01T00:00Z")[0] == "2027-01-02T12:00:00Z"


def test_spring_second_friday_hash(cli_json):
    assert _first(cli_json, "0 0 0 ? * 5#2", "spring", "2027-01-01T00:00Z")[0] == "2027-01-08T00:00:00Z"


def test_no_run_exits_3(cli_json):
    code, data, _ = cli_json(["next", "0 0 30 2 *", "--dialect", "unix", "--from", "2027-01-01T00:00Z"])
    assert code == 3 and data["error"]["code"] == "E_NO_RUN"


def test_unknown_time_zone_exits_2(cli_json):
    code, data, _ = cli_json(["next", "0 0 * * *", "--dialect", "unix", "--tz", "Mars/Phobos"])
    assert code == 2 and data["error"]["code"] == "E_UNKNOWN_TZ"


def test_missing_tzdata_exits_4(cli_json, monkeypatch):
    def broken(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)

    monkeypatch.setattr(_engine.zoneinfo, "ZoneInfo", broken)
    monkeypatch.setattr(_engine.zoneinfo, "available_timezones", lambda: set())
    code, data, _ = cli_json(["next", "0 0 * * *", "--dialect", "unix", "--tz", "America/New_York"])
    assert code == 4 and data["error"]["code"] == "E_NO_TZDATA"
    assert "uv run --with tzdata" in data["error"]["message"]
    # UTC and fixed offsets need no tz database
    code, _, _ = cli_json(["next", "0 0 * * *", "--dialect", "unix", "--tz", "UTC", "--from", "2027-01-01T00:00Z"])
    assert code == 0
    code, _, _ = cli_json(["next", "0 0 * * *", "--dialect", "unix", "--tz", "+05:30", "--from", "2027-01-01T00:00Z"])
    assert code == 0


def test_too_many_runs_exits_2(cli_json):
    code, data, _ = cli_json(["diff", "* * * * * ?", "* * * * * ?", "--dialect", "quartz", "--from",
                              "2027-01-01T00:00Z"])
    assert code == 2 and data["error"]["code"] == "E_TOO_MANY_RUNS"
    code, data, _ = cli_json(["next", "* * * * * ?", "--dialect", "quartz", "--from", "2027-01-01T00:00Z", "--until",
                              "2028-01-01T00:00Z"])
    assert code == 2 and data["error"]["code"] == "E_TOO_MANY_RUNS"


def test_every_second_next_is_fast_and_sorted(cli_json):
    code, data, _ = cli_json(["next", "* * * * * ?", "--dialect", "quartz", "--from", "2027-01-01T00:00Z",
                              "--count", "3"])
    assert [r["utc"] for r in data["runs"]] == ["2027-01-01T00:00:00Z", "2027-01-01T00:00:01Z",
                                                "2027-01-01T00:00:02Z"]


def test_one_year_diff_of_daily_expressions_is_fast():
    t0 = time.perf_counter()
    a = count_runs("0 9 * * *", "unix", tz="America/New_York")
    b = count_runs("0 0 9 * * ?", "quartz", tz="America/New_York")
    assert a == b == 365
    assert time.perf_counter() - t0 < 2.0


def test_every_minute_year_stays_reasonable():
    t0 = time.perf_counter()
    assert count_runs("* * * * *", "unix") == 365 * 1440
    assert time.perf_counter() - t0 < 10.0


def test_from_accepts_offsets_and_local_times():
    z = resolve_zone("America/New_York")
    assert parse_instant("2027-01-01T00:00:00Z", z) == parse_instant("2026-12-31T19:00", z)
    assert parse_instant("2027-01-01T09:00+09:00", z) == parse_instant("2027-01-01T00:00Z", z)
    assert parse_instant("2027-01-01", z) == parse_instant("2027-01-01T00:00", z)
    for bad in ("2027-13-01", "2027-02-30", "tomorrow", "2027-01-01T25:00"):
        try:
            parse_instant(bad, z)
        except CronError as e:
            assert e.code == "E_BAD_TIME"
        else:
            raise AssertionError(bad)


def test_normalization_uppercases_names():
    assert parse("0 9 * jan-mar mon-fri", "unix").normalized == "0 9 * JAN-MAR MON-FRI"


def test_name_range_warning_for_unix_not_for_k8s():
    assert "W_NAME_RANGE" in [w.code for w in parse("0 9 * * MON-FRI", "unix").warnings]
    assert "W_NAME_RANGE" not in [w.code for w in parse("0 9 * * MON-FRI", "k8s").warnings]


def test_friday_to_sunday_name_range_is_valid_for_spring():
    assert count_runs("0 0 0 * * FRI-SUN", "spring", days=7) == 3


def test_next_default_count_is_five(cli_json):
    code, data, _ = cli_json(["next", "0 0 * * *", "--dialect", "github", "--from", "2027-01-01T00:00Z"])
    assert len(data["runs"]) == 5


def test_explain_fields_and_counts(cli_json):
    code, data, _ = cli_json(["explain", "0 0 12 ? * 2-6", "--dialect", "quartz", "--from", "2027-01-01T00:00Z"])
    fields = {f["name"]: f for f in data["fields"]}
    assert fields["dow"]["values"] == "MON-FRI" or fields["dow"]["values"] == "MON,TUE,WED,THU,FRI"
    assert data["counts"]["a"] == 261
    assert "W_DOW_BASE" in [w["code"] for w in data["warnings"]]


def test_explain_text_runs(cli):
    code, out, _ = cli(["explain", "0 12 ? * MON-FRI *", "--dialect", "eventbridge", "--from", "2027-01-01T00:00Z"])
    assert code == 0 and "261 runs" in out and "W_TZ_UTC_FIXED" in out


def test_dialects_table_lists_all_ids(cli_json):
    code, data, _ = cli_json(["dialects"])
    assert [d["id"] for d in data["dialects"]] == list(DIALECTS)


def test_dialects_text(cli):
    code, out, _ = cli(["dialects", "--dialect", "eventbridge-scheduler"])
    assert code == 0 and "eventbridge-scheduler" in out and "https://docs.aws.amazon.com/scheduler" in out


def test_k8s_question_mark_is_star():
    assert count_runs("0 0 ? * *", "k8s") == 365


def test_scripts_import_only_standard_library():
    stdlib = set(sys.stdlib_module_names)
    local = {p.stem for p in SCRIPTS.glob("*.py")}
    offenders = []
    for path in SCRIPTS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                mods = [node.module]
            for m in mods:
                top = m.split(".")[0]
                if top not in stdlib and top not in local:
                    offenders.append((path.name, m))
    assert offenders == []


def test_script_runs_as_a_process_and_help_works():
    script = str(SCRIPTS / "cronx.py")
    env = {"PATH": "/usr/bin:/bin", "LANG": "C"}
    r = subprocess.run([sys.executable, script, "next", "0 9 1-7 * 1", "--dialect", "unix", "--from",
                        "2027-01-01T00:00Z", "--count", "3"], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0
    for stamp in ("2027-01-01T09:00", "2027-01-02T09:00", "2027-01-03T09:00", "W_DOM_DOW_OR"):
        assert stamp in r.stdout
    h = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True, env=env, timeout=60)
    assert h.returncode == 0 and "exit codes" in h.stdout
    for sub in ("parse", "next", "explain", "convert", "diff", "dialects"):
        s = subprocess.run([sys.executable, script, sub, "--help"], capture_output=True, text=True, env=env,
                           timeout=60)
        assert s.returncode == 0 and "--json" in s.stdout


def test_default_zone_is_reported_as_an_assumption(cli_json, cli):
    """Without --tz the run times are a UTC stand-in: JSON and text must say so instead of claiming UTC."""
    for dialect, expr, default in (("k8s", "0 3 * * *", "controller-local"), ("unix", "0 3 * * *", "local"),
                                   ("spring", "0 0 3 * * *", "server")):
        code, data, _ = cli_json(["next", expr, "--dialect", dialect, "--from", "2027-01-01T00:00Z", "--count", "1"])
        assert code == 0
        assert data["tz"] == "UTC" and data["tz_default"] == default and data["tz_assumed"] is True
    # GitHub and EventBridge rules really default to UTC: nothing is assumed
    code, data, _ = cli_json(["next", "0 3 * * *", "--dialect", "github", "--from", "2027-01-01T00:00Z"])
    assert data["tz_default"] == "UTC" and data["tz_assumed"] is False
    # an explicit --tz (the value of .spec.timeZone) removes the assumption and the warning
    code, data, _ = cli_json(["explain", "0 3 * * *", "--dialect", "k8s", "--tz", "Asia/Seoul",
                              "--from", "2027-01-01T00:00Z"])
    assert data["tz"] == "Asia/Seoul" and data["tz_assumed"] is False
    assert "W_TZ_CONTROLLER" not in {w["code"] for w in data["warnings"]}
    code, data, _ = cli_json(["diff", "0 3 * * *", "0 3 * * *", "--dialect", "k8s", "--dialect2", "github",
                              "--from", "2027-01-01T00:00Z", "--days", "7"])
    assert data["tz_assumed"] is True and data["tz_assumed2"] is False
    code, data, _ = cli_json(["convert", "0 3 * * *", "--from-dialect", "k8s", "--to", "unix",
                              "--from", "2027-01-01T00:00Z", "--days", "7"])
    assert data["tz_default"] == "controller-local" and data["tz_assumed"] is True


def test_k8s_controller_warning_names_the_fix(cli_json):
    code, data, _ = cli_json(["parse", "0 3 * * *", "--dialect", "k8s", "--lang", "en"])
    msg = next(w["message"] for w in data["warnings"] if w["code"] == "W_TZ_CONTROLLER")
    assert "kube-controller-manager's local time zone" in msg
    assert ".spec.timeZone" in msg and "CRON_TZ=" in msg
    code, data, _ = cli_json(["parse", "0 3 * * *", "--dialect", "k8s", "--lang", "ko"])
    msg = next(w["message"] for w in data["warnings"] if w["code"] == "W_TZ_CONTROLLER")
    assert "로컬 시간대" in msg and ".spec.timeZone" in msg


def test_tz_note_states_the_real_zone(cli_json):
    """tz_note: one sentence on where the schedule really runs, for the agent to quote as is."""
    code, data, _ = cli_json(["next", "0 3 * * *", "--dialect", "k8s", "--from", "2027-01-01T00:00Z",
                              "--count", "1", "--lang", "en"])
    assert data["tz_note"] == ("runs in the kube-controller-manager's local time zone (not necessarily UTC); the times "
                               "shown are a UTC stand-in until the real zone is passed with --tz")
    code, data, _ = cli_json(["parse", "0 3 * * *", "--dialect", "unix", "--lang", "en"])
    assert data["tz_note"].startswith("runs in the daemon's local time zone;")
    code, data, _ = cli_json(["parse", "0 3 * * *", "--dialect", "github", "--lang", "en"])
    assert data["tz_note"] == "runs in UTC"
    code, data, _ = cli_json(["explain", "0 3 * * *", "--dialect", "k8s", "--tz", "Asia/Seoul",
                              "--from", "2027-01-01T00:00Z", "--lang", "en"])
    assert data["tz_note"] == "runs in Asia/Seoul"
    code, data, _ = cli_json(["diff", "0 0 3 * * *", "0 3 * * *", "--dialect", "spring", "--dialect2", "github",
                              "--from", "2027-01-01T00:00Z", "--days", "7", "--lang", "en"])
    assert "server" in data["tz_note"] and data["tz_note2"] == "runs in UTC"
    code, data, _ = cli_json(["convert", "0 3 * * *", "--from-dialect", "k8s", "--to", "unix",
                              "--from", "2027-01-01T00:00Z", "--days", "7", "--lang", "ko"])
    assert data["tz_note"].startswith("kube-controller-manager 의 로컬 시간대")


def test_k8s_text_output_names_the_controller_local_zone(cli):
    """Moved from the removed task-k8s-timezone case (v2): the text output itself says where the zone comes from.

    Kubernetes docs: "the kube-controller-manager interprets schedules relative to its local time zone".
    """
    code, out, _ = cli(["explain", "0 3 * * *", "--dialect", "k8s", "--from", "2027-01-01T00:00Z", "--lang", "en"])
    assert code == 0
    warn_line = next(line for line in out.splitlines() if line.strip().startswith("W_TZ_CONTROLLER"))
    assert "kube-controller-manager" in warn_line and "local time zone" in warn_line
    head = out.splitlines()[0]
    assert "UTC assumed" in head
    assert "kube-controller-manager" in head and "local time zone" in head


def test_k8s_explain_json_flags_the_assumption_with_its_source(cli_json):
    """AC-6 command: tz_default / tz_assumed / tz_note and W_TZ_CONTROLLER with the Kubernetes cron-jobs page."""
    code, data, _ = cli_json(["explain", "0 3 * * *", "--dialect", "k8s", "--from", "2027-01-01T00:00Z",
                              "--lang", "en"])
    assert code == 0
    assert data["tz"] == "UTC" and data["tz_default"] == "controller-local" and data["tz_assumed"] is True
    assert data["tz_note"].startswith("runs in the kube-controller-manager's local time zone")
    warn = next(w for w in data["warnings"] if w["code"] == "W_TZ_CONTROLLER")
    assert warn["source"] == "https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/"


def test_tz_note_follows_the_locale_unless_lang_is_given(cli_json, monkeypatch):
    """Moved from the removed task-k8s-timezone case (v2): on a Korean OS locale the note is Korean unless the
    caller passes --lang en (SKILL.md asks for --lang matching the answer language)."""
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    argv = ["explain", "0 3 * * *", "--dialect", "k8s", "--from", "2027-01-01T00:00Z"]
    code, data, _ = cli_json(argv)
    assert code == 0
    assert "로컬 시간대" in data["tz_note"] and "local time zone" not in data["tz_note"]
    code, data, _ = cli_json(argv + ["--lang", "en"])
    assert code == 0
    assert data["tz_note"].startswith("runs in the kube-controller-manager's local time zone")
    assert data["tz_default"] == "controller-local" and data["tz_assumed"] is True  # keys and values language-neutral
