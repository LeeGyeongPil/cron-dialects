"""AC-6: two languages, selection order, identical keys, language-neutral JSON."""
from __future__ import annotations

import json
import re

import pytest

import _i18n
from conftest import SCRIPTS


def test_key_sets_are_identical():
    assert set(_i18n.EN) == set(_i18n.KO)


def test_placeholders_match_between_languages():
    field = re.compile(r"\{(\w+)\}")
    for key in _i18n.EN:
        assert set(field.findall(_i18n.EN[key])) == set(field.findall(_i18n.KO[key])), key


def test_every_code_used_in_the_scripts_has_messages():
    src = "".join(p.read_text(encoding="utf-8") for p in SCRIPTS.glob("*.py"))
    for code in set(re.findall(r'CronError\(\s*"(E_\w+)"', src)):
        assert f"err.{code}" in _i18n.EN, code
    for code in set(re.findall(r'Warn\(\s*"(W_\w+)"', src)):
        assert f"warn.{code}" in _i18n.EN, code
    for code in set(re.findall(r'\("(C_\w+)"', src)):
        assert f"conv.{code}" in _i18n.EN, code


def test_every_literal_message_key_exists():
    src = "".join(p.read_text(encoding="utf-8") for p in SCRIPTS.glob("*.py"))
    for key in set(re.findall(r'\bt\("([a-z_.\-]+[a-z_])"', src)):
        assert key in _i18n.EN, key


@pytest.mark.parametrize("cli_value,env,expected", [
    ("ko", {}, "ko"),
    ("en", {"CRON_DIALECTS_LANG": "ko"}, "en"),
    (None, {"CRON_DIALECTS_LANG": "ko", "LANG": "en_US.UTF-8"}, "ko"),
    (None, {"CRON_DIALECTS_LANG": "en", "LC_ALL": "ko_KR.UTF-8"}, "en"),
    (None, {"LC_ALL": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}, "ko"),
    (None, {"LC_ALL": "en_US.UTF-8", "LANG": "ko_KR.UTF-8"}, "en"),
    (None, {"LC_MESSAGES": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}, "ko"),
    (None, {"LANG": "ko_KR.UTF-8"}, "ko"),
    (None, {"LANG": "fr_FR.UTF-8"}, "en"),
    (None, {}, "en"),
])
def test_language_priority(cli_value, env, expected):
    assert _i18n.pick_lang(cli_value, env) == expected


def test_cli_lang_switches_help_and_errors(cli):
    _, en_help, _ = cli(["--lang", "en", "next", "--help"])
    _, ko_help, _ = cli(["--lang", "ko", "next", "--help"])
    assert "number of runs to list" in en_help and "나열할 실행 횟수" in ko_help
    assert "usage:" in en_help and "사용법:" in ko_help
    _, _, en_err = cli(["--lang", "en", "parse", "0 12 * * *", "--dialect", "eventbridge"])
    _, _, ko_err = cli(["--lang", "ko", "parse", "0 12 * * *", "--dialect", "eventbridge"])
    assert "expects 6 fields" in en_err and "필드 6개" in ko_err
    assert en_err.startswith("E_FIELD_COUNT:") and ko_err.startswith("E_FIELD_COUNT:")


def test_lang_option_after_command_and_env_var(cli, monkeypatch):
    _, _, err = cli(["parse", "0 12 * * *", "--dialect", "eventbridge", "--lang", "ko"])
    assert "필드 6개" in err
    monkeypatch.setenv("CRON_DIALECTS_LANG", "ko")
    _, _, err = cli(["parse", "0 12 * * *", "--dialect", "eventbridge"])
    assert "필드 6개" in err
    _, _, err = cli(["--lang", "en", "parse", "0 12 * * *", "--dialect", "eventbridge"])
    assert "expects 6 fields" in err


def test_locale_variable_selects_korean(cli, monkeypatch):
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    code, out, _ = cli(["parse", "0 12 * * *", "--dialect", "unix"])
    assert "올바른 unix 식" in out


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_json_keys_do_not_depend_on_language(cli):
    argv = ["next", "0 9 1-7 * 1", "--dialect", "unix", "--from", "2027-01-01T00:00Z", "--count", "2", "--json"]
    _, en, _ = cli(["--lang", "en"] + argv)
    _, ko, _ = cli(["--lang", "ko"] + argv)
    a, b = json.loads(en), json.loads(ko)
    assert set(_keys(a)) == set(_keys(b))
    assert a["runs"] == b["runs"] and [w["code"] for w in a["warnings"]] == [w["code"] for w in b["warnings"]]
    assert a["warnings"][0]["message"] != b["warnings"][0]["message"]


def test_korean_dst_table_and_dialects(cli):
    code, out, _ = cli(["explain", "30 2 * * *", "--dialect", "github", "--tz", "America/New_York", "--dst",
                        "--year", "2027", "--lang", "ko"])
    assert code == 0 and "존재하지 않음" in out and "실행 안 함" in out
    code, out, _ = cli(["dialects", "--dialect", "quartz", "--lang", "ko"])
    assert "요일 번호" in out
    code, out, _ = cli(["convert", "0 9 1-7 * 1", "--from-dialect", "unix", "--to", "quartz", "--from",
                        "2027-01-01T00:00Z", "--lang", "ko"])
    assert "나눔" in out


def test_word_params_are_translated():
    text = _i18n.t("ko", "warn.W_DST_UNDOCUMENTED", dialect="spring", what="fold", assumed="first")
    assert "두 번 오는 시각" in text and "첫 번째에 한 번 실행" in text
