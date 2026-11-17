"""AC-2: validation errors have fixed codes and exit code 2."""
from __future__ import annotations

import json

import pytest


def _err(cli, argv):
    code, out, err = cli(list(argv) + ["--json"])
    return code, json.loads(out)["error"]


def test_eventbridge_needs_question_mark(cli):
    code, e = _err(cli, ["parse", "0 12 * * MON-FRI *", "--dialect", "eventbridge"])
    assert code == 2 and e["code"] == "E_QMARK_REQUIRED"
    assert e["source"].startswith("https://docs.aws.amazon.com/")


def test_fixed_eventbridge_expression_is_valid(cli):
    code, out, _ = cli(["parse", "0 12 ? * MON-FRI *", "--dialect", "eventbridge"])
    assert code == 0 and "valid eventbridge expression" in out


def test_cron_wrapper_accepted_for_eventbridge(cli_json):
    code, data, _ = cli_json(["parse", "cron(0 12 ? * MON-FRI *)", "--dialect", "eventbridge"])
    assert code == 0 and data["normalized"] == "0 12 ? * MON-FRI *"


def test_both_question_marks_rejected(cli):
    code, e = _err(cli, ["parse", "0 12 ? * ? *", "--dialect", "eventbridge"])
    assert e["code"] == "E_QMARK_REQUIRED"


def test_five_field_eventbridge(cli):
    code, e = _err(cli, ["parse", "0 12 * * *", "--dialect", "eventbridge"])
    assert code == 2 and e["code"] == "E_FIELD_COUNT"
    assert "expects 6 fields (minute hour day-of-month month day-of-week year), got 5" in e["message"]


def test_quartz_field_count_message_lists_both_counts(cli):
    code, e = _err(cli, ["parse", "0 0 12 * *", "--dialect", "quartz"])
    assert e["code"] == "E_FIELD_COUNT" and "6 or 7" in e["message"]


def test_eventbridge_allows_only_one_hash(cli):
    code, e = _err(cli, ["parse", "0 12 ? * 3#1,6#3 *", "--dialect", "eventbridge"])
    assert code == 2 and e["code"] == "E_HASH_MULTI"
    code, _, _ = cli(["parse", "0 12 ? * 3#1 *", "--dialect", "eventbridge"])
    assert code == 0


def test_tz_inside_expression_rejected(cli):
    code, e = _err(cli, ["parse", "CRON_TZ=UTC 0 3 * * *", "--dialect", "k8s"])
    assert code == 2 and e["code"] == "E_TZ_IN_EXPR"
    assert ".spec.timeZone" in e["message"]


def test_github_rejects_alias(cli):
    code, e = _err(cli, ["parse", "@daily", "--dialect", "github"])
    assert code == 2 and e["code"] == "E_ALIAS_UNSUPPORTED"


def test_unsupported_alias_for_unix(cli):
    code, e = _err(cli, ["parse", "@reboot", "--dialect", "unix"])
    assert e["code"] == "E_ALIAS_UNSUPPORTED"


@pytest.mark.parametrize("expr,dialect,code", [
    ("61 * * * *", "unix", "E_RANGE"),
    ("* 24 * * *", "k8s", "E_RANGE"),
    ("0 0 * * 8", "unix", "E_RANGE"),
    ("0 0 * * 7", "github", "E_RANGE"),
    ("0 0 0 ? * 0 ", "quartz", "E_RANGE"),
    ("0 0 * * 5-1", "unix", "E_RANGE_REVERSED"),
    ("0 0 * * foo", "unix", "E_SYNTAX"),
    ("*/0 * * * *", "unix", "E_SYNTAX"),
    ("0 0 L * *", "unix", "E_SPECIAL_UNSUPPORTED"),
    ("0 0 * * 5L", "k8s", "E_SPECIAL_UNSUPPORTED"),
    ("0 0 0 ? * 6#6", "quartz", "E_NTH_RANGE"),
    ("0 0 ? * * ", "unix", "E_SPECIAL_UNSUPPORTED"),
    ("cron(0 12 * * ?)", "unix", "E_CRON_WRAPPER"),
])
def test_validation_codes(cli, expr, dialect, code):
    exit_code, e = _err(cli, ["parse", expr, "--dialect", dialect])
    assert exit_code == 2 and e["code"] == code


def test_eventbridge_rule_rejects_other_time_zone(cli):
    code, e = _err(cli, ["next", "0 12 ? * MON-FRI *", "--dialect", "eventbridge", "--tz", "Asia/Seoul"])
    assert code == 2 and e["code"] == "E_TZ_UNSUPPORTED"


def test_unknown_bad_time_and_bad_counts(cli):
    assert _err(cli, ["next", "0 0 * * *", "--dialect", "unix", "--from", "tomorrow"])[1]["code"] == "E_BAD_TIME"
    assert _err(cli, ["next", "0 0 * * *", "--dialect", "unix", "--count", "0"])[1]["code"] == "E_COUNT_RANGE"
    assert _err(cli, ["next", "0 0 * * *", "--dialect", "unix", "--count", "2", "--until", "2028-01-01"])[1][
        "code"] == "E_COUNT_UNTIL"
    assert _err(cli, ["diff", "0 0 * * *", "0 0 * * *", "--dialect", "unix", "--days", "9999"])[1][
        "code"] == "E_DAYS_RANGE"


def test_argparse_usage_error_exits_2(cli):
    code, out, err = cli(["next", "0 0 * * *", "--dialect", "nope"])
    assert code == 2 and "E_USAGE" in err


def test_error_text_goes_to_stderr_without_json(cli):
    code, out, err = cli(["parse", "0 12 * * MON-FRI *", "--dialect", "eventbridge"])
    assert code == 2 and out == "" and err.startswith("E_QMARK_REQUIRED:")
    assert "source: https://docs.aws.amazon.com" in err


def test_no_command_prints_help_and_exits_2(cli):
    code, out, err = cli([])
    assert code == 2 and "parse" in out
