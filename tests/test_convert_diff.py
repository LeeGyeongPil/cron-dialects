"""AC-4: convert proves itself by diffing run instants; diff reports the first mismatch."""
from __future__ import annotations

import json


def _convert(cli_json, expr, src, dst, *extra):
    return cli_json(["convert", expr, "--from-dialect", src, "--to", dst, "--from", "2027-01-01T00:00Z", *extra])


def test_quartz_to_unix_is_verified(cli_json):
    code, data, _ = _convert(cli_json, "0 0 12 ? * 2-6", "quartz", "unix")
    assert code == 0
    assert data["converted"] == "0 12 * * 1-5"
    assert data["equivalent"] is True
    assert data["counts"] == {"a": 261, "b": 261}


def test_quartz_to_eventbridge_keeps_numbering_and_adds_year(cli_json):
    code, data, _ = _convert(cli_json, "0 0 12 ? * 2-6", "quartz", "eventbridge")
    assert code == 0 and data["converted"] == "0 12 ? * 2-6 *"
    assert data["wrapped"] == "cron(0 12 ? * 2-6 *)" and data["equivalent"] is True


def test_eventbridge_to_quartz_adds_seconds(cli_json):
    code, data, _ = _convert(cli_json, "0 12 ? * MON-FRI *", "eventbridge", "quartz")
    assert code == 0 and data["converted"] == "0 0 12 ? * MON-FRI *" and data["equivalent"] is True


def test_spring_to_eventbridge_drops_zero_seconds_and_renumbers(cli_json):
    code, data, _ = _convert(cli_json, "0 0 0 * * 1-5", "spring", "eventbridge")
    assert code == 0 and data["converted"] == "0 0 ? * 2-6 *"


def test_spring_first_monday_becomes_hash(cli_json):
    code, data, _ = _convert(cli_json, "0 0 9 1-7 * 1", "spring", "quartz")
    assert code == 0 and data["converted"] == "0 0 9 ? * 2#1" and data["counts"]["a"] == 12


def test_unix_or_rule_needs_a_split_for_quartz(cli_json):
    code, data, _ = _convert(cli_json, "0 9 1-7 * 1", "unix", "quartz")
    assert code == 1
    assert data["converted"] is None
    assert data["split"] == ["0 0 9 1-7 * ?", "0 0 9 ? * 2"]
    assert data["split_equivalent"] is True
    assert data["reasons"][0]["code"] == "C_OR_SPLIT"


def test_unix_weekday_wrap_renumbers(cli_json):
    code, data, _ = _convert(cli_json, "0 12 * * 5-7", "unix", "quartz")
    assert code == 0 and data["converted"] == "0 0 12 ? * 1,6-7" and data["equivalent"] is True


def test_specials_cannot_go_to_five_fields(cli_json):
    code, data, _ = _convert(cli_json, "0 0 0 ? * 5#2", "quartz", "unix")
    assert code == 1 and data["converted"] is None
    assert data["reasons"][0]["code"] == "C_SPECIAL"


def test_and_rule_cannot_be_one_unix_expression(cli_json):
    code, data, _ = _convert(cli_json, "0 0 9 1-15 * 1", "spring", "unix")
    assert code == 1 and data["reasons"][0]["code"] == "C_AND"


def test_seconds_cannot_go_to_eventbridge(cli_json):
    code, data, _ = _convert(cli_json, "30 0 12 ? * *", "quartz", "eventbridge")
    assert code == 1 and data["reasons"][0]["code"] == "C_SECONDS"


def test_year_cannot_go_to_unix(cli_json):
    code, data, _ = _convert(cli_json, "0 0 12 1 1 ? 2028", "quartz", "unix")
    assert code == 1 and data["reasons"][0]["code"] == "C_YEAR"


def test_convert_text_output(cli):
    code, out, _ = cli(["convert", "0 0 12 ? * 2-6", "--from-dialect", "quartz", "--to", "unix", "--from",
                        "2027-01-01T00:00Z"])
    assert code == 0
    assert "unix: 0 12 * * 1-5" in out and "equivalent: 261 runs in both" in out


def test_diff_same_count_but_not_equivalent(cli_json):
    code, data, _ = cli_json(["diff", "0 0 12 ? * 2-6", "0 12 * * 2-6", "--dialect", "quartz", "--dialect2", "unix",
                              "--from", "2027-01-01T00:00Z"])
    assert code == 1
    assert data["counts"] == {"a": 261, "b": 261}
    assert data["equivalent"] is False
    assert data["first_mismatch"] == {"instant": "2027-01-02T12:00:00Z", "only_in": "b"}
    codes = [w["code"] for w in data["warnings"]]
    assert "W_DOW_BASE" in codes and "W_DAYS_DIFFER" in codes


def test_diff_equivalent_exits_zero(cli):
    code, out, _ = cli(["diff", "0 0 12 ? * 2-6", "0 12 * * 1-5", "--dialect", "quartz", "--dialect2", "unix",
                        "--from", "2027-01-01T00:00Z"])
    assert code == 0 and out.startswith("A: ") and "equivalent: 261 runs in both" in out


def test_diff_text_has_first_mismatch_line(cli):
    code, out, _ = cli(["diff", "0 9 1-7 * 1", "0 0 9 1-7 * 1", "--dialect", "unix", "--dialect2", "spring",
                        "--from", "2027-01-01T00:00Z"])
    assert code == 1
    assert "not equivalent: 124 vs 12 runs, first mismatch 2027-01-01T09:00:00Z (only in A)" in out


def test_diff_with_two_time_zones(cli_json):
    # 09:00 in Seoul is 00:00 UTC
    code, data, _ = cli_json(["diff", "0 9 * * *", "0 0 * * *", "--dialect", "unix", "--tz", "Asia/Seoul",
                              "--tz2", "UTC", "--from", "2027-01-01T00:00Z"])
    assert code == 0 and data["equivalent"] is True


def test_dst_policy_difference_is_reported_by_convert(cli_json):
    # same wall time, same days, but the schedulers disagree on the DST gap day
    code, data, _ = cli_json(["convert", "30 2 * * *", "--from-dialect", "github", "--to", "eventbridge-scheduler",
                              "--tz", "America/New_York", "--from", "2027-01-01T00:00Z"])
    assert code == 1 and data["equivalent"] is False
    assert data["first_mismatch"] == {"instant": "2027-03-14T07:00:00Z", "only_in": "a"}


def test_out_file_receives_json(cli, tmp_path):
    target = tmp_path / "res.json"
    code, out, _ = cli(["convert", "0 0 12 ? * 2-6", "--from-dialect", "quartz", "--to", "unix", "--from",
                        "2027-01-01T00:00Z", "--out", str(target)])
    assert code == 0
    saved = json.loads(target.read_text())
    assert saved["converted"] == "0 12 * * 1-5" and saved["equivalent"] is True


def test_out_file_error(cli, tmp_path):
    code, out, err = cli(["parse", "0 0 * * *", "--dialect", "unix", "--out", str(tmp_path / "no" / "x.json")])
    assert code == 2 and err.startswith("E_OUT:")


import pytest  # noqa: E402


@pytest.mark.parametrize("expr,src,dst,expected", [
    ("0 0 12 ? * 2#1", "quartz", "eventbridge", "0 12 ? * 2#1 *"),
    ("0 0 12 ? * 6L", "quartz", "eventbridge", "0 12 ? * 6L *"),
    ("0 12 ? * 6L *", "eventbridge", "spring", "0 0 12 * * 5L"),
    ("0 0 12 ? * 2/2", "quartz", "unix", "0 12 * * 1,3,5"),
    ("0 0 22-2 * * ?", "quartz", "unix", "0 0-2,22-23 * * *"),
    ("5/15 * * * *", "unix", "github", "5,20,35,50 * * * *"),
    ("0 0 0 ? * FRI-MON", "quartz", "unix", "0 0 * * 0-1,5-6"),
    ("0 0 0 * * MON-FRI", "spring", "quartz", "0 0 0 ? * MON-FRI"),
    ("0 0 ? * 1", "k8s", "quartz", "0 0 0 ? * 2"),
    ("0 0 * * */2", "unix", "quartz", "0 0 0 ? * */2"),
    ("0 0 12 L * ?", "quartz", "spring", "0 0 12 L * *"),
    ("0 0 12 15W * ?", "quartz", "eventbridge", "0 12 15W * ? *"),
    ("@daily", "unix", "spring", "0 0 0 * * *"),
    ("@hourly", "k8s", "github", "0 * * * *"),
    ("0 0 12 * * 0,7", "spring", "quartz", "0 0 12 ? * 1"),
])
def test_conversion_rewrites_and_proves(cli_json, expr, src, dst, expected):
    code, data, _ = _convert(cli_json, expr, src, dst)
    assert data["converted"] == expected
    assert code == 0 and data["equivalent"] is True


def test_or_split_for_spring_target(cli_json):
    code, data, _ = _convert(cli_json, "0 9 1-7 * 1", "unix", "spring")
    assert code == 1 and data["split"] == ["0 0 9 1-7 * *", "0 0 9 * * 1"] and data["split_equivalent"] is True


def test_bare_l_weekday_has_no_unix_equivalent(cli_json):
    code, data, _ = _convert(cli_json, "0 0 12 ? * L", "quartz", "unix")
    assert code == 1 and data["reasons"][0]["code"] == "C_SPECIAL"


def test_l_minus_n_not_documented_for_eventbridge(cli_json):
    code, data, _ = _convert(cli_json, "0 0 12 L-2 * ?", "quartz", "eventbridge")
    assert code == 1 and data["reasons"][0]["code"] == "C_SPECIAL"


def test_seconds_rejected_for_unix_target(cli_json):
    code, data, _ = _convert(cli_json, "* * * * * *", "spring", "unix")
    assert code == 1 and data["reasons"][0]["code"] == "C_SECONDS"


def test_eventbridge_rule_target_rejects_other_zone(cli_json):
    code, data, _ = _convert(cli_json, "0 12 * * *", "unix", "eventbridge", "--tz", "Asia/Seoul")
    assert code == 2 and data["error"]["code"] == "E_TZ_UNSUPPORTED"
