"""AC-3: DST gap and fold follow each scheduler's documented policy."""
from __future__ import annotations

NY = "America/New_York"


def _next(cli_json, expr, dialect, start, count=3, extra=()):
    code, data, _ = cli_json(["next", expr, "--dialect", dialect, "--tz", NY, "--from", start,
                              "--count", str(count), *extra])
    assert code == 0
    return data


def _locals(data):
    return [(r["local"], r["dst"]) for r in data["runs"]]


def test_github_moves_gap_run_to_transition_instant(cli_json):
    data = _next(cli_json, "30 2 * * *", "github", "2027-03-13T00:00")
    assert _locals(data)[:3] == [("2027-03-13T02:30:00-05:00", "normal"),
                                 ("2027-03-14T03:00:00-04:00", "gap-shifted"),
                                 ("2027-03-15T02:30:00-04:00", "normal")]


def test_cronie_skips_gap_day(cli_json):
    data = _next(cli_json, "30 2 * * *", "cronie", "2027-03-14T00:00", 2)
    assert [r["local"] for r in data["runs"]] == ["2027-03-15T02:30:00-04:00", "2027-03-16T02:30:00-04:00"]
    assert any(w["code"] == "W_DST_SKIPPED" for w in data["warnings"])


def test_eventbridge_scheduler_skips_gap_day(cli_json):
    data = _next(cli_json, "30 2 * * ? *", "eventbridge-scheduler", "2027-03-14T00:00", 1)
    assert data["runs"][0]["local"] == "2027-03-15T02:30:00-04:00"


def test_cronie_runs_fold_twice(cli_json):
    data = _next(cli_json, "30 1 * * *", "cronie", "2027-11-07T00:00", 3)
    assert _locals(data) == [("2027-11-07T01:30:00-04:00", "fold-first"), ("2027-11-07T01:30:00-05:00", "fold-second"),
                             ("2027-11-08T01:30:00-05:00", "normal")]


def test_eventbridge_scheduler_runs_fold_once_second_pass(cli_json):
    data = _next(cli_json, "30 1 * * ? *", "eventbridge-scheduler", "2027-11-07T00:00", 2)
    assert _locals(data) == [("2027-11-07T01:30:00-05:00", "fold-second"), ("2027-11-08T01:30:00-05:00", "normal")]
    assert not data["warnings"] or all(w["code"] != "W_DST_UNDOCUMENTED" for w in data["warnings"])


def test_unix_debian_policy_runs_fold_once_first_pass(cli_json):
    data = _next(cli_json, "30 1 * * *", "unix", "2027-11-07T00:00", 2)
    assert _locals(data)[0] == ("2027-11-07T01:30:00-04:00", "fold-first")
    assert [w["code"] for w in data["warnings"] if w["code"] == "W_DST_UNDOCUMENTED"] == []


def test_spring_and_github_flag_undocumented_fold(cli_json):
    for expr, dialect in (("0 30 1 * * *", "spring"), ("30 1 * * *", "github")):
        data = _next(cli_json, expr, dialect, "2027-11-07T00:00", 2)
        assert [r["dst"] for r in data["runs"]][0] == "fold-first"
        assert "W_DST_UNDOCUMENTED" in [w["code"] for w in data["warnings"]]


def test_spring_flags_undocumented_gap(cli_json):
    data = _next(cli_json, "0 30 2 * * *", "spring", "2027-03-14T00:00", 1)
    assert data["runs"][0]["dst"] == "gap-shifted"
    assert "W_DST_UNDOCUMENTED" in [w["code"] for w in data["warnings"]]


def test_github_gap_is_documented_no_flag(cli_json):
    data = _next(cli_json, "30 2 * * *", "github", "2027-03-14T00:00", 1)
    assert "W_DST_UNDOCUMENTED" not in [w["code"] for w in data["warnings"]]


def test_utc_pinned_github_schedule_drifts_in_new_york(cli_json):
    code, data, _ = cli_json(["next", "0 14 * * 1-5", "--dialect", "github", "--tz", "UTC", "--show-tz", NY,
                              "--from", "2027-03-01T00:00Z", "--until", "2027-03-31T00:00Z"])
    hours = {r["show"][11:13] for r in data["runs"]}
    assert hours == {"09", "10"}


def test_explain_dst_table_lists_every_scheduler(cli_json):
    code, data, _ = cli_json(["explain", "30 2 * * *", "--dialect", "github", "--tz", NY, "--dst", "--year", "2027"])
    rows = data["dst"]["rows"]
    assert [r["type"] for r in rows] == ["gap"] and rows[0]["date"] == "2027-03-14"
    res = rows[0]["results"]
    assert res["github"]["runs"][0]["local"] == "2027-03-14T03:00:00-04:00"
    assert res["cronie"]["skipped"] and res["eventbridge-scheduler"]["skipped"] and res["k8s"]["skipped"]
    assert set(res) == {"unix", "cronie", "k8s", "github", "spring", "quartz", "eventbridge-scheduler"}


def test_explain_dst_fold_table_text(cli):
    code, out, _ = cli(["explain", "30 1 * * *", "--dialect", "unix", "--tz", NY, "--dst", "--year", "2027",
                        "--lang", "en"])
    assert code == 0
    assert "this wall-clock time happens twice" in out
    assert "runs twice: 2027-11-07T01:30:00-04:00 and 2027-11-07T01:30:00-05:00" in out
    assert "runs once, second pass: 2027-11-07T01:30:00-05:00" in out


def test_explain_dst_in_utc_has_no_rows(cli_json):
    _, data, _ = cli_json(["explain", "30 2 * * *", "--dialect", "unix", "--tz", "UTC", "--dst", "--year", "2027"])
    assert data["dst"]["rows"] == []


def test_seoul_has_no_dst(cli_json):
    code, d2, _ = cli_json(["next", "30 2 * * *", "--dialect", "github", "--tz", "Asia/Seoul", "--from",
                            "2027-03-13T00:00", "--count", "3"])
    assert {r["dst"] for r in d2["runs"]} == {"normal"}
    assert d2["runs"][0]["local"] == "2027-03-13T02:30:00+09:00"


def test_fixed_offset_zone(cli_json):
    code, d, _ = cli_json(["next", "0 9 * * *", "--dialect", "github", "--tz", "+09:00", "--from",
                           "2027-01-01T00:00Z", "--count", "1"])
    assert d["runs"][0]["utc"] == "2027-01-01T00:00:00Z"
    assert d["runs"][0]["local"] == "2027-01-01T09:00:00+09:00"
