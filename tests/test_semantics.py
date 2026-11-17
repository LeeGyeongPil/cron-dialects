"""AC-1: combination rules, weekday numbering, fixed 2027 counts (UTC)."""
from __future__ import annotations

import pytest

from conftest import count_runs


def test_unix_ors_day_fields():
    assert count_runs("0 9 1-7 * 1", "unix") == 124


def test_spring_ands_day_fields():
    assert count_runs("0 0 9 1-7 * 1", "spring") == 12


@pytest.mark.parametrize("dialect", ["unix", "cronie"])
def test_vixie_first_star_rule_gives_and(dialect):
    # '*/2' starts with '*', so day-of-month counts as unrestricted and the fields are ANDed
    assert count_runs("0 0 */2 * 1", dialect) == 27


def test_k8s_robfig_treats_star_step_as_restricted():
    # robfig/cron v3 clears its "star" bit when a step > 1 is given, so the day fields are ORed
    assert count_runs("0 0 */2 * 1", "k8s") == 211
    assert count_runs("0 0 * * 1", "k8s") == 52
    assert count_runs("0 0 */1 * 1", "k8s") == 52          # step 1 keeps the star bit: AND


def test_k8s_warns_with_robfig_note_not_vixie(cli_json):
    code, data, _ = cli_json(["explain", "0 0 */2 * 1", "--dialect", "k8s", "--from", "2027-01-01T00:00Z", "--tz", "UTC"])
    codes = [w["code"] for w in data["warnings"]]
    assert "W_ROBFIG_STEP" in codes and "W_VIXIE_STAR" not in codes


def test_unix_to_k8s_diff_is_not_equivalent(cli):
    code, out, _ = cli(["diff", "0 0 */2 * 1", "0 0 */2 * 1", "--dialect", "unix", "--dialect2", "k8s",
                        "--from", "2027-01-01T00:00Z", "--tz", "UTC"])
    assert code == 1


def test_explicit_step_range_is_restricted_so_or():
    assert count_runs("0 0 1-31/2 * 1", "unix") == 211


def test_quartz_weekday_numbering_starts_at_sunday():
    assert count_runs("0 0 12 ? * 2-6", "quartz") == 261


def test_quartz_first_run_is_friday_jan_first(cli_json):
    code, data, _ = cli_json(["next", "0 0 12 ? * 2-6", "--dialect", "quartz", "--from", "2027-01-01T00:00Z",
                              "--count", "2"])
    assert code == 0
    assert data["runs"][0]["utc"] == "2027-01-01T12:00:00Z"
    assert data["runs"][1]["utc"] == "2027-01-04T12:00:00Z"   # Monday, not Saturday


def test_unix_numbers_sunday_as_zero_and_seven():
    assert count_runs("0 0 * * 0", "unix") == count_runs("0 0 * * 7", "unix") == 52


def test_names_and_numbers_agree():
    assert count_runs("0 12 * * MON-FRI", "unix") == count_runs("0 12 * * 1-5", "unix") == 261


def test_eventbridge_matches_quartz_for_same_schedule():
    assert count_runs("0 12 ? * MON-FRI *", "eventbridge") == 261


def test_warnings_explain_the_trap(cli_json):
    code, data, _ = cli_json(["next", "0 9 1-7 * 1", "--dialect", "unix", "--from", "2027-01-01T00:00Z"])
    codes = [w["code"] for w in data["warnings"]]
    assert "W_DOM_DOW_OR" in codes and "W_TZ_LOCAL" in codes
    code, data, _ = cli_json(["parse", "0 0 */2 * 1", "--dialect", "unix"])
    assert "W_VIXIE_STAR" in [w["code"] for w in data["warnings"]]
    code, data, _ = cli_json(["parse", "0 0 9 1-7 * 1", "--dialect", "spring"])
    assert "W_DOM_DOW_AND" in [w["code"] for w in data["warnings"]]


def test_github_min_interval_warning(cli_json):
    _, data, _ = cli_json(["parse", "*/2 * * * *", "--dialect", "github"])
    assert "W_MIN_INTERVAL" in [w["code"] for w in data["warnings"]]
    _, data, _ = cli_json(["parse", "*/5 * * * *", "--dialect", "github"])
    assert "W_MIN_INTERVAL" not in [w["code"] for w in data["warnings"]]


def test_aliases_expand():
    assert count_runs("@daily", "unix") == 365
    assert count_runs("@daily", "spring") == 365
    assert count_runs("@hourly", "k8s") == 365 * 24


def test_year_field_limits_runs():
    assert count_runs("0 0 12 1 1 ? 2027", "quartz", days=730) == 1
    assert count_runs("0 12 1 1 ? 2028", "eventbridge", days=365) == 0


def test_wrapped_ranges_where_allowed():
    # EventBridge allows an hour range that crosses midnight
    assert count_runs("0 22-2 * * ? *", "eventbridge") == 365 * 5
