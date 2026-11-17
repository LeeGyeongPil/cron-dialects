"""Message tables (English and Korean) and language selection for cronx.

Every user-visible sentence lives here, keyed identically in both languages.
Language order: --lang > CRON_DIALECTS_LANG > LC_ALL > LC_MESSAGES > LANG;
anything that is not Korean falls back to English.
"""
from __future__ import annotations

from typing import Mapping

LANGS = ("en", "ko")
ENV_VAR = "CRON_DIALECTS_LANG"


def _is_ko(value: str | None) -> bool:
    return bool(value) and value.strip().lower().replace("-", "_").startswith("ko")


def pick_lang(cli: str | None, env: Mapping[str, str]) -> str:
    """Resolve the language: explicit option first, then the tool variable, then POSIX locale variables."""
    if cli:
        return "ko" if _is_ko(cli) else "en"
    if env.get(ENV_VAR):
        return "ko" if _is_ko(env[ENV_VAR]) else "en"
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if env.get(name):
            return "ko" if _is_ko(env[name]) else "en"
    return "en"


def t(lang: str, key: str, **params) -> str:
    table = MESSAGES.get(lang, MESSAGES["en"])
    text = table.get(key) or MESSAGES["en"][key]
    for name in ("what", "assumed"):
        word = params.get(name)
        if isinstance(word, str) and f"word.{word}" in table:
            params[name] = table[f"word.{word}"]
    return text.format(**params) if params else text


EN: dict[str, str] = {
    # ---- help ---------------------------------------------------------------
    "help.head.usage": "usage",
    "help.head.options": "options",
    "help.head.positional": "positional arguments",
    "help.description": "Interpret, convert and verify cron expressions per scheduler dialect "
                        "(Unix, cronie, Kubernetes, GitHub Actions, Spring, Quartz, EventBridge) with time zones and DST.",
    "help.epilog": "exit codes: 0 ok / equivalent; 1 not equivalent or not expressible as one expression; "
                   "2 usage or validation error; 3 no run within the search horizon; 4 time zone data missing",
    "help.cmd.parse": "validate an expression and print its normalized form and field values",
    "help.cmd.next": "list the next runs (or all runs until a date) in a time zone",
    "help.cmd.explain": "explain every field, pitfalls and (with --dst) what each scheduler does on DST days",
    "help.cmd.convert": "rewrite an expression for another dialect and prove it with a run-instant diff",
    "help.cmd.diff": "compare the run instants of two expressions and report the first mismatch",
    "help.cmd.dialects": "print the rule table of the supported schedulers",
    "help.help": "show this help message and exit",
    "help.json": "print machine-readable JSON instead of text",
    "help.out": "also write the JSON result to FILE",
    "help.lang": "message language: en or ko (default: CRON_DIALECTS_LANG / locale / en)",
    "help.expr": "the cron expression (quote it); EventBridge cron(...) wrapping is accepted",
    "help.expr2": "the second cron expression (quote it)",
    "help.tz": "IANA time zone name, UTC or +HH:MM (default: the dialect's default, with a warning when unknown)",
    "help.tz2": "time zone of the second expression (default: --tz)",
    "help.from": "start of the window, ISO date-time; no Z or offset means local time in --tz (default: now, UTC)",
    "help.dialect": "scheduler dialect: {ids}",
    "help.dialect_a": "dialect of the first expression",
    "help.dialect_b": "dialect of the second expression (default: same as --dialect)",
    "help.dialect_opt": "show only this dialect",
    "help.count": "number of runs to list (default 5, at most {max})",
    "help.until": "list all runs before this ISO date-time instead of a count",
    "help.show_tz": "add a column with the runs shown in this second time zone",
    "help.dst": "add the per-scheduler table for the DST transition days of --year",
    "help.year": "year for --dst (default: year of --from)",
    "help.days": "window length in days, 1-{max} (default 365)",
    "help.from_dialect": "dialect of the expression to convert",
    "help.to": "dialect to convert to",
    # ---- labels ---------------------------------------------------------------
    "label.warnings": "warnings:",
    "label.source": "source",
    "label.expression": "expression",
    "label.normalized": "normalized",
    "label.from": "from",
    "label.combine": "day fields",
    "label.tz_assumed": "{zone} assumed; the scheduler's real default is {default}",
    "col.local": "local time",
    "col.utc": "UTC",
    "col.shown": "in {tz}",
    "col.dst": "DST",
    "kind.normal": "normal",
    "kind.gap-shifted": "gap, moved to transition",
    "kind.fold-first": "repeated hour, first pass",
    "kind.fold-second": "repeated hour, second pass",
    "parse.ok": "valid {dialect} expression",
    "next.none": "no runs in the requested range",
    "explain.count": "{n} runs in the {days} days from {start}",
    "field.second": "second",
    "field.minute": "minute",
    "field.hour": "hour",
    "field.dom": "day-of-month",
    "field.month": "month",
    "field.dow": "day-of-week",
    "field.year": "year",
    "combine.vixie": "OR when both are restricted (AND if either starts with '*')",
    "combine.robfig": "OR when both are restricted (AND only if one is exactly '*' or '?'; '*/2' counts as restricted)",
    "combine.and": "AND (both must match)",
    "combine.qmark": "exactly one of the two must be '?'",
    "word.gap": "skipped hour (gap)",
    "word.fold": "repeated hour (fold)",
    "word.shift": "run at the transition instant",
    "word.first": "run once on the first pass",
    "yes": "yes",
    "no": "no",
    # ---- diff / convert ---------------------------------------------------------
    "diff.same": "equivalent: {a} runs in both over {days} days from {start}",
    "diff.differ": "not equivalent: {a} vs {b} runs, first mismatch {instant} (only in {side})",
    "conv.cannot": "cannot express as one {target} expression: {reasons}",
    "conv.split_same": "the union of the expressions above matches the original run for run",
    "conv.split_differ": "the union of the expressions above does NOT match the original",
    "conv.C_SECONDS": "the source has seconds other than 0 and {target} has no seconds field",
    "conv.C_YEAR": "the source restricts the year and {target} has no year field",
    "conv.C_SPECIAL": "'{token}' has no equivalent in {target}",
    "conv.C_AND": "the source needs day-of-month AND day-of-week to match; {target} cannot say that in one "
                  "expression (check one of them inside the job)",
    "conv.C_OR_SPLIT": "the source runs when day-of-month OR day-of-week matches; split into {n} {target} expressions",
    "conv.C_INVALID": "the rewritten expression was rejected by {target} ({code})",
    # ---- dialect table ------------------------------------------------------------
    "dl.fields": "fields",
    "dl.weekdays": "weekdays",
    "dl.combine": "day fields",
    "dl.specials": "special characters",
    "dl.aliases": "aliases (@daily ...)",
    "dl.default_tz": "default time zone",
    "dl.not_settable": "cannot be changed",
    "dl.range_wrap": "reversed ranges (22-2)",
    "dl.dst": "DST",
    "dl.gap": "gap",
    "dl.fold": "fold",
    "tz.UTC": "UTC",
    "tz.local": "the daemon's local time zone",
    "tz.controller-local": "the kube-controller-manager's local time zone (not necessarily UTC)",
    "tz.server": "the server / trigger time zone",
    "tz_note.assumed": "runs in {default}; the times shown are a UTC stand-in until the real zone is passed with --tz",
    "tz_note.set": "runs in {zone}",
    "gap.shift": "runs at the transition instant",
    "gap.skip": "the run is skipped that day",
    "fold.first": "runs once (first pass)",
    "fold.second": "runs once (second pass)",
    "fold.both": "runs twice",
    # ---- DST table ------------------------------------------------------------------
    "dst.title": "DST behaviour in {year} for {tz} (whatever the day fields say, if the job is due at this wall time):",
    "dst.none": "no run time of this expression falls into a DST gap or fold (or the zone has no DST)",
    "dst.row.gap": "{date} {wall}: this wall-clock time does not exist (clocks jump forward)",
    "dst.row.fold": "{date} {wall}: this wall-clock time happens twice (clocks go back)",
    "dst.undocumented": "not documented - computed assumption",
    "dst.more": "... and {n} more affected run times that day",
    "dst.skipped": "does not run",
    "dst.both": "runs twice: {a} and {b}",
    "dst.normal": "runs at {local}",
    "dst.gap-shifted": "runs at {local} (moved to the transition instant)",
    "dst.fold-first": "runs once, first pass: {local}",
    "dst.fold-second": "runs once, second pass: {local}",
    # ---- errors ---------------------------------------------------------------------
    "err.E_UNKNOWN_DIALECT": "unknown dialect '{dialect}'; choose one of: {known}",
    "err.E_SYNTAX": "{dialect}: cannot read '{token}' in the {field} field ('{text}')",
    "err.E_RANGE": "{dialect}: {value} is outside the {field} range {lo}-{hi}",
    "err.E_RANGE_REVERSED": "{dialect}: the reversed range '{token}' in the {field} field is not allowed; "
                            "write it as two ranges separated by a comma",
    "err.E_NTH_RANGE": "{dialect}: the '#' occurrence must be 1-5, got {value}",
    "err.E_SPECIAL_UNSUPPORTED": "{dialect}: '{token}' is not supported in the {field} field "
                                 "(special characters allowed there: {allowed})",
    "err.E_HASH_MULTI": "{dialect}: only one '#' expression is allowed in the day-of-week field; "
                        "use one rule per '#' expression",
    "err.E_ALIAS_UNSUPPORTED": "{dialect} does not support the alias '{alias}' (supported: {supported}); "
                               "write the fields out",
    "err.E_TZ_IN_EXPR": "{dialect} rejects CRON_TZ= / TZ= inside the schedule; pass the zone separately "
                        "(--tz here, .spec.timeZone in a Kubernetes CronJob)",
    "err.E_CRON_WRAPPER": "'cron(...)' is the EventBridge wrapper; {dialect} takes the bare fields",
    "err.E_FIELD_COUNT": "{dialect} expects {expected} fields ({names}), got {got}",
    "err.E_QMARK_REQUIRED": "{dialect} requires '?' in exactly one of day-of-month or day-of-week "
                            "(got '{dom}' and '{dow}'); put '?' in the one you do not restrict",
    "err.E_TZ_UNSUPPORTED": "{dialect} has no time zone setting (it runs in UTC); got --tz {tz}",
    "err.E_UNKNOWN_TZ": "unknown time zone '{name}'; use an IANA name such as America/New_York, UTC or an offset "
                        "such as +09:00",
    "err.E_NO_TZDATA": "IANA time zone data not found (needed for '{name}'); run with: "
                       "uv run --with tzdata python scripts/cronx.py ...",
    "err.E_BAD_TIME": "cannot read the time '{text}'; use YYYY-MM-DD or YYYY-MM-DDTHH:MM[:SS][Z|+HH:MM]",
    "err.E_DAYS_RANGE": "--days must be between 1 and {max}, got {days}",
    "err.E_COUNT_RANGE": "--count must be between 1 and {max}, got {count}",
    "err.E_COUNT_UNTIL": "--count and --until cannot be combined; pick one",
    "err.E_TOO_MANY_RUNS": "the window would hold more than {limit} runs; shorten --days or use a less frequent expression",
    "err.E_TOO_MANY_RUNS_NEXT": "the window would hold more than {limit} runs; move --until earlier or use a less "
                                "frequent expression",
    "err.E_NO_RUN": "no run within the search horizon ({days} days from {start}); the expression may never match "
                    "(for example 0 0 30 2 *)",
    "err.E_OUT": "cannot write the --out file '{path}': {reason}",
    # ---- warnings -------------------------------------------------------------------
    "warn.W_DOM_DOW_OR": "day-of-month '{dom}' and day-of-week '{dow}' are both restricted: this scheduler runs when "
                         "EITHER matches (OR), not when both match",
    "warn.W_VIXIE_STAR": "'{token}' in the {field} field starts with '*', so it counts as unrestricted and "
                         "day-of-month and day-of-week are ANDed instead of ORed (Vixie rule)",
    "warn.W_ROBFIG_STEP": "'{token}' in the {field} field starts with '*' but has a step, so robfig/cron (used by "
                          "Kubernetes) counts it as restricted and ORs the day fields; crontab(5) would AND them",
    "warn.W_DOM_DOW_AND": "day-of-month '{dom}' and day-of-week '{dow}' are both restricted: this scheduler requires "
                          "BOTH to match (AND)",
    "warn.W_COMBINE_ASSUMED": "{dialect} does not document how day-of-month and day-of-week combine; computed as "
                              "POSIX cron (OR)",
    "warn.W_STEP_NO_RANGE": "a start value with a step (for example 5/15) is not portable in {dialect}; some "
                            "implementations reject it",
    "warn.W_NAME_RANGE": "the {dialect} documentation does not allow ranges or lists of names (MON-FRI); some "
                         "implementations reject them, numbers are safest",
    "warn.W_MIN_INTERVAL": "runs can be {seconds} s apart; GitHub Actions does not run schedules more often than "
                           "every {limit} s (5 minutes) and may delay or drop runs",
    "warn.W_TZ_LOCAL": "no --tz: {dialect} uses the daemon's local time zone, which this script cannot know; "
                       "computed in UTC - pass the real zone with --tz",
    "warn.W_TZ_CONTROLLER": "no --tz: a Kubernetes CronJob without .spec.timeZone runs in the kube-controller-manager's "
                            "local time zone (UTC only if the controller runs in UTC); computed in UTC - set "
                            ".spec.timeZone (stable since v1.27) and pass the same value with --tz; CRON_TZ= / TZ= "
                            "inside .spec.schedule fail validation",
    "warn.W_TZ_SERVER": "no --tz: {dialect} uses the server or trigger time zone unless one is configured; "
                        "computed in UTC - pass the real zone with --tz",
    "warn.W_DST_UNDOCUMENTED": "{dialect} does not document what happens at a {what}; computed as '{assumed}' - "
                               "verify on the real scheduler",
    "warn.W_DST_SKIPPED": "{count} run(s) fall into a DST gap (the wall-clock time does not exist) and are skipped by "
                          "{dialect}; first: {first}",
    "warn.W_TZ_UTC_FIXED": "{dialect} runs in UTC here: the local clock time shifts by an hour across daylight "
                           "saving changes (set a time zone to keep a local time where the scheduler supports it)",
    "warn.W_DOW_BASE": "weekday numbers are not portable (checked: {dialect}): Quartz and EventBridge count 1-7 from "
                       "Sunday (1 = SUN), Unix-style crons 0-7 (0 and 7 = SUN), so the same number is a different weekday",
    "warn.W_DAYS_DIFFER": "the dialects combine day-of-month and day-of-week differently (A {a}; B {b})",
}

KO: dict[str, str] = {
    "help.head.usage": "사용법",
    "help.head.options": "옵션",
    "help.head.positional": "위치 인자",
    "help.description": "스케줄러 방언별(Unix, cronie, Kubernetes, GitHub Actions, Spring, Quartz, EventBridge) cron 식을 "
                        "시간대·서머타임까지 고려해 해석·변환·검증합니다.",
    "help.epilog": "종료 코드: 0 성공·동치; 1 비동치 또는 한 식으로 표현 불가; 2 사용법·식 검증 오류; "
                   "3 검색 범위 안에 실행 없음; 4 시간대 데이터 없음",
    "help.cmd.parse": "식을 검증하고 정규화한 형태와 필드 값을 출력",
    "help.cmd.next": "시간대 기준으로 다음 실행 시각(또는 날짜까지 전부)을 나열",
    "help.cmd.explain": "필드 뜻·함정을 설명하고 --dst 이면 서머타임 전환일의 스케줄러별 동작을 표로 출력",
    "help.cmd.convert": "다른 방언으로 식을 바꾸고 실행 시각 대조로 증명",
    "help.cmd.diff": "두 식의 실행 시각을 비교해 첫 불일치를 보고",
    "help.cmd.dialects": "지원하는 스케줄러의 규칙표를 출력",
    "help.help": "이 도움말을 보여 주고 종료",
    "help.json": "텍스트 대신 기계가 읽는 JSON 을 출력",
    "help.out": "JSON 결과를 FILE 에도 저장",
    "help.lang": "메시지 언어: en 또는 ko (기본: CRON_DIALECTS_LANG / 로캘 / en)",
    "help.expr": "cron 식(따옴표로 감쌀 것); EventBridge 의 cron(...) 감싸기도 받음",
    "help.expr2": "두 번째 cron 식(따옴표로 감쌀 것)",
    "help.tz": "IANA 시간대 이름, UTC 또는 +HH:MM (기본: 방언 기본값, 알 수 없으면 경고)",
    "help.tz2": "두 번째 식의 시간대 (기본: --tz)",
    "help.from": "기간 시작, ISO 날짜·시각; Z·오프셋이 없으면 --tz 의 현지 시각 (기본: 지금, UTC)",
    "help.dialect": "스케줄러 방언: {ids}",
    "help.dialect_a": "첫 번째 식의 방언",
    "help.dialect_b": "두 번째 식의 방언 (기본: --dialect 와 같음)",
    "help.dialect_opt": "이 방언만 출력",
    "help.count": "나열할 실행 횟수 (기본 5, 최대 {max})",
    "help.until": "횟수 대신 이 ISO 시각 전까지 전부 나열",
    "help.show_tz": "실행 시각을 이 두 번째 시간대로도 보여 주는 열 추가",
    "help.dst": "--year 의 서머타임 전환일에 대한 스케줄러별 표 추가",
    "help.year": "--dst 의 연도 (기본: --from 의 연도)",
    "help.days": "기간 길이(일), 1-{max} (기본 365)",
    "help.from_dialect": "변환할 식의 방언",
    "help.to": "변환 대상 방언",
    "label.warnings": "경고:",
    "label.source": "근거",
    "label.expression": "식",
    "label.normalized": "정규화",
    "label.from": "시작",
    "label.combine": "일·요일 필드",
    "label.tz_assumed": "{zone} 로 가정함; 스케줄러의 실제 기본값은 {default}",
    "col.local": "현지 시각",
    "col.utc": "UTC",
    "col.shown": "{tz} 기준",
    "col.dst": "서머타임",
    "kind.normal": "일반",
    "kind.gap-shifted": "공백, 전환 순간으로 이동",
    "kind.fold-first": "반복 시각, 첫 번째",
    "kind.fold-second": "반복 시각, 두 번째",
    "parse.ok": "올바른 {dialect} 식",
    "next.none": "요청한 범위에 실행이 없음",
    "explain.count": "{start} 부터 {days}일 동안 {n}회 실행",
    "field.second": "초",
    "field.minute": "분",
    "field.hour": "시",
    "field.dom": "일",
    "field.month": "월",
    "field.dow": "요일",
    "field.year": "연",
    "combine.vixie": "둘 다 제한하면 OR (한쪽이 '*' 로 시작하면 AND)",
    "combine.robfig": "둘 다 제한하면 OR (한쪽이 정확히 '*' 또는 '?' 일 때만 AND; '*/2' 는 제한으로 취급)",
    "combine.and": "AND (둘 다 맞아야 함)",
    "combine.qmark": "둘 중 정확히 하나는 '?'",
    "word.gap": "건너뛰는 시각(공백)",
    "word.fold": "두 번 오는 시각(중복)",
    "word.shift": "전환 순간에 실행",
    "word.first": "첫 번째에 한 번 실행",
    "yes": "예",
    "no": "아니오",
    "diff.same": "동치: {start} 부터 {days}일 동안 양쪽 모두 {a}회 실행",
    "diff.differ": "동치 아님: {a}회 대 {b}회, 첫 불일치 {instant} ({side} 에만 있음)",
    "conv.cannot": "{target} 식 하나로 표현할 수 없음: {reasons}",
    "conv.split_same": "위 식들의 합집합은 원본과 실행 시각이 정확히 같음",
    "conv.split_differ": "위 식들의 합집합이 원본과 다름",
    "conv.C_SECONDS": "원본에 0이 아닌 초가 있는데 {target} 에는 초 필드가 없음",
    "conv.C_YEAR": "원본이 연도를 제한하는데 {target} 에는 연 필드가 없음",
    "conv.C_SPECIAL": "'{token}' 에 해당하는 표현이 {target} 에 없음",
    "conv.C_AND": "원본은 일과 요일이 둘 다 맞아야 실행(AND)하는데 {target} 한 식으로는 그렇게 말할 수 없음 "
                  "(둘 중 하나는 작업 안에서 검사)",
    "conv.C_OR_SPLIT": "원본은 일 또는 요일 중 하나만 맞아도 실행하므로 {target} 식 {n}개로 나눔",
    "conv.C_INVALID": "바꾼 식을 {target} 이 거부함 ({code})",
    "dl.fields": "필드",
    "dl.weekdays": "요일 번호",
    "dl.combine": "일·요일 필드",
    "dl.specials": "특수 문자",
    "dl.aliases": "별칭(@daily 등)",
    "dl.default_tz": "기본 시간대",
    "dl.not_settable": "변경 불가",
    "dl.range_wrap": "뒤집힌 범위(22-2)",
    "dl.dst": "서머타임",
    "dl.gap": "공백",
    "dl.fold": "중복",
    "tz.UTC": "UTC",
    "tz.local": "데몬의 로컬 시간대",
    "tz.controller-local": "kube-controller-manager 의 로컬 시간대(UTC 가 아닐 수 있음)",
    "tz.server": "서버·트리거의 시간대",
    "tz_note.assumed": "{default} 에서 실행됨; 표시한 시각은 실제 시간대를 --tz 로 넘기기 전까지 UTC 로 대신 계산한 값",
    "tz_note.set": "{zone} 에서 실행됨",
    "gap.shift": "전환 순간에 실행",
    "gap.skip": "그날은 실행 건너뜀",
    "fold.first": "한 번 실행(첫 번째)",
    "fold.second": "한 번 실행(두 번째)",
    "fold.both": "두 번 실행",
    "dst.title": "{tz} 의 {year}년 서머타임 동작 (일·요일 필드와 무관하게, 이 현지 시각에 작업이 예정돼 있다면):",
    "dst.none": "이 식의 실행 시각 중 서머타임 공백·중복에 걸리는 것이 없음(또는 DST 없는 시간대)",
    "dst.row.gap": "{date} {wall}: 이 현지 시각은 존재하지 않음(시계가 앞으로 건너뜀)",
    "dst.row.fold": "{date} {wall}: 이 현지 시각이 두 번 옴(시계가 뒤로 감)",
    "dst.undocumented": "문서에 없음 - 계산상 가정",
    "dst.more": "... 그날 영향받는 실행 시각 {n}개 더",
    "dst.skipped": "실행 안 함",
    "dst.both": "두 번 실행: {a}, {b}",
    "dst.normal": "{local} 에 실행",
    "dst.gap-shifted": "{local} 에 실행(전환 순간으로 이동)",
    "dst.fold-first": "한 번 실행, 첫 번째: {local}",
    "dst.fold-second": "한 번 실행, 두 번째: {local}",
    "err.E_UNKNOWN_DIALECT": "알 수 없는 방언 '{dialect}'; 다음 중에서 고르세요: {known}",
    "err.E_SYNTAX": "{dialect}: {field} 필드의 '{token}' 을(를) 읽을 수 없음 ('{text}')",
    "err.E_RANGE": "{dialect}: {value} 은(는) {field} 필드 범위 {lo}-{hi} 밖",
    "err.E_RANGE_REVERSED": "{dialect}: {field} 필드의 뒤집힌 범위 '{token}' 은 허용되지 않음; 쉼표로 나눈 두 범위로 쓰세요",
    "err.E_NTH_RANGE": "{dialect}: '#' 의 회차는 1-5 여야 함 (입력 {value})",
    "err.E_SPECIAL_UNSUPPORTED": "{dialect}: {field} 필드에서 '{token}' 을(를) 지원하지 않음 (허용 특수 문자: {allowed})",
    "err.E_HASH_MULTI": "{dialect}: 요일 필드에는 '#' 식을 하나만 쓸 수 있음; '#' 식마다 규칙을 따로 만드세요",
    "err.E_ALIAS_UNSUPPORTED": "{dialect} 은(는) 별칭 '{alias}' 을(를) 지원하지 않음 (지원: {supported}); 필드를 풀어서 쓰세요",
    "err.E_TZ_IN_EXPR": "{dialect} 은(는) 식 안의 CRON_TZ= / TZ= 를 거부함; 시간대는 따로 지정하세요 "
                        "(여기서는 --tz, Kubernetes CronJob 은 .spec.timeZone)",
    "err.E_CRON_WRAPPER": "'cron(...)' 은 EventBridge 전용 감싸기; {dialect} 은(는) 필드만 받음",
    "err.E_FIELD_COUNT": "{dialect} 은(는) 필드 {expected}개({names})가 필요한데 {got}개를 받음",
    "err.E_QMARK_REQUIRED": "{dialect} 은(는) 일·요일 중 정확히 하나에 '?' 가 필요함 (입력 '{dom}' 과 '{dow}'); "
                            "제한하지 않는 쪽에 '?' 를 쓰세요",
    "err.E_TZ_UNSUPPORTED": "{dialect} 은(는) 시간대 설정이 없음(UTC 로 실행); --tz {tz} 를 받음",
    "err.E_UNKNOWN_TZ": "알 수 없는 시간대 '{name}'; America/New_York 같은 IANA 이름, UTC, +09:00 같은 오프셋을 쓰세요",
    "err.E_NO_TZDATA": "IANA 시간대 데이터가 없음('{name}' 에 필요); 다음처럼 실행하세요: "
                       "uv run --with tzdata python scripts/cronx.py ...",
    "err.E_BAD_TIME": "시각 '{text}' 을(를) 읽을 수 없음; YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM[:SS][Z|+HH:MM] 형식을 쓰세요",
    "err.E_DAYS_RANGE": "--days 는 1에서 {max} 사이여야 함 (입력 {days})",
    "err.E_COUNT_RANGE": "--count 는 1에서 {max} 사이여야 함 (입력 {count})",
    "err.E_COUNT_UNTIL": "--count 와 --until 은 함께 쓸 수 없음; 하나만 고르세요",
    "err.E_TOO_MANY_RUNS": "이 기간에 실행이 {limit}회를 넘음; --days 를 줄이거나 덜 자주 도는 식을 쓰세요",
    "err.E_TOO_MANY_RUNS_NEXT": "이 기간에 실행이 {limit}회를 넘음; --until 을 더 앞으로 당기거나 덜 자주 도는 식을 쓰세요",
    "err.E_NO_RUN": "검색 범위({start} 부터 {days}일) 안에 실행이 없음; 식이 영원히 맞지 않을 수 있음 (예: 0 0 30 2 *)",
    "err.E_OUT": "--out 파일 '{path}' 에 쓸 수 없음: {reason}",
    "warn.W_DOM_DOW_OR": "일 '{dom}' 과 요일 '{dow}' 를 둘 다 제한함: 이 스케줄러는 둘 중 하나만 맞아도(OR) 실행함, "
                         "둘 다 맞을 때가 아님",
    "warn.W_VIXIE_STAR": "{field} 필드의 '{token}' 은 '*' 로 시작해 제한 없음으로 취급되므로 일·요일이 OR 가 아니라 "
                         "AND 로 합쳐짐 (Vixie 규칙)",
    "warn.W_ROBFIG_STEP": "{field} 필드의 '{token}' 은 '*' 로 시작하지만 간격이 있어 robfig/cron(Kubernetes)은 제한으로 "
                          "취급해 일·요일을 OR 로 합침; crontab(5) 은 AND 로 합침",
    "warn.W_DOM_DOW_AND": "일 '{dom}' 과 요일 '{dow}' 를 둘 다 제한함: 이 스케줄러는 둘 다 맞아야(AND) 실행함",
    "warn.W_COMBINE_ASSUMED": "{dialect} 은(는) 일·요일 결합 방식을 문서화하지 않음; POSIX cron(OR)으로 계산함",
    "warn.W_STEP_NO_RANGE": "시작 값에 간격을 붙인 형태(예 5/15)는 {dialect} 에서 이식성이 없음; 거부하는 구현이 있음",
    "warn.W_NAME_RANGE": "{dialect} 문서는 이름의 범위·목록(MON-FRI)을 허용하지 않음; 거부하는 구현이 있으니 숫자가 안전함",
    "warn.W_MIN_INTERVAL": "실행 간격이 {seconds}초까지 좁아질 수 있음; GitHub Actions 는 {limit}초(5분)보다 "
                           "자주 실행하지 않으며 지연·누락이 있을 수 있음",
    "warn.W_TZ_LOCAL": "--tz 없음: {dialect} 은(는) 데몬의 로컬 시간대를 쓰는데 이 스크립트는 알 수 없음; UTC 로 계산함 "
                       "- 실제 시간대를 --tz 로 넘기세요",
    "warn.W_TZ_CONTROLLER": "--tz 없음: .spec.timeZone 이 없는 Kubernetes CronJob 은 kube-controller-manager 의 "
                            "로컬 시간대로 실행됨(controller 가 UTC 로 돌 때만 UTC); UTC 로 계산함 - .spec.timeZone 을 "
                            "지정하고(v1.27 부터 정식) 같은 값을 --tz 로 넘기세요; .spec.schedule 안의 CRON_TZ= / TZ= 는 "
                            "검증 오류로 거부됨",
    "warn.W_TZ_SERVER": "--tz 없음: {dialect} 은(는) 따로 지정하지 않으면 서버·트리거의 시간대를 씀; UTC 로 계산함 "
                        "- 실제 시간대를 --tz 로 넘기세요",
    "warn.W_DST_UNDOCUMENTED": "{dialect} 은(는) {what}에서의 동작을 문서화하지 않음; '{assumed}' 로 계산함 - "
                               "실제 스케줄러에서 확인하세요",
    "warn.W_DST_SKIPPED": "{count}개 실행이 서머타임 공백(존재하지 않는 현지 시각)에 걸려 {dialect} 에서 건너뜀; 첫 번째: {first}",
    "warn.W_TZ_UTC_FIXED": "여기서 {dialect} 은(는) UTC 로 실행됨: 서머타임 전환 때 현지 시각이 1시간씩 달라짐 "
                           "(스케줄러가 지원하면 시간대를 지정해 현지 시각을 고정하세요)",
    "warn.W_DOW_BASE": "요일 번호는 이식되지 않음 (확인: {dialect}): Quartz·EventBridge 는 일요일부터 1-7 (1 = SUN), "
                       "Unix 계열 cron 은 0-7 (0·7 = SUN)이라 같은 숫자가 다른 요일을 뜻함",
    "warn.W_DAYS_DIFFER": "두 방언이 일·요일을 다르게 합침 (A {a}; B {b})",
}

MESSAGES: dict[str, dict[str, str]] = {"en": EN, "ko": KO}
