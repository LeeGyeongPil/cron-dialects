"""Per-scheduler cron rule table (data only).

Every rule that differs between schedulers lives here, together with the
documentation page it comes from (checked 2026-11-17).  Nothing in this file
computes anything; ``_engine`` and ``_convert`` read it.

Field kinds are ``second minute hour dom month dow year``.
"""
from __future__ import annotations

DOW_NAMES = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
MONTH_NAMES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

_URL_CRONTAB = "https://man7.org/linux/man-pages/man5/crontab.5.html"
_URL_DEBIAN = "https://manpages.debian.org/bookworm/cron/cron.8.en.html"
_URL_K8S = "https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/"
_URL_ROBFIG = "https://pkg.go.dev/github.com/robfig/cron/v3"
_URL_GITHUB = "https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows"
_URL_SPRING = "https://docs.spring.io/spring-framework/reference/integration/scheduling.html"
_URL_SPRING_SRC = ("https://raw.githubusercontent.com/spring-projects/spring-framework/main/"
                   "spring-context/src/main/java/org/springframework/scheduling/support/CronExpression.java")
_URL_QUARTZ = "https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html"
_URL_EB_RULE = "https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html"
_URL_EB_SCHED = "https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html"

# Alias -> five-field expansion (the sixth "0 seconds" field is added for spring).
ALIASES = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

# DST policy codes.
#   gap:  "shift" = run at the transition instant, "skip" = no run that day
#   fold: "first" = once (first pass), "second" = once (second pass), "both" = twice
# *_documented False means the scheduler's documentation does not say; the
# engine still has to pick something, and it warns instead of asserting.


def _dst(gap: str, fold: str, gap_doc: bool, fold_doc: bool, source: str) -> dict:
    return {"gap": gap, "fold": fold, "gap_documented": gap_doc, "fold_documented": fold_doc, "source": source}


DIALECTS: dict[str, dict] = {
    "unix": {
        "layout": ("minute", "hour", "dom", "month", "dow"),
        "min_fields": 5,
        "dow_base": 0, "dow_max": 7,
        "year_range": None,
        "specials": frozenset(),
        "dow_bare_l": False,
        "aliases": True,
        "combine": "vixie", "combine_documented": True,
        "default_tz": "local", "tz_settable": True,
        "range_wrap": False,
        "single_step": False,
        "names_in_lists": False,
        "hash_single": False,
        "min_interval_s": None,
        "dst": _dst("shift", "first", True, True, _URL_DEBIAN),
        "sources": {"syntax": _URL_CRONTAB, "days": _URL_CRONTAB, "tz": _URL_CRONTAB, "dst": _URL_DEBIAN},
    },
    "cronie": {
        "layout": ("minute", "hour", "dom", "month", "dow"),
        "min_fields": 5,
        "dow_base": 0, "dow_max": 7,
        "year_range": None,
        "specials": frozenset(),
        "dow_bare_l": False,
        "aliases": True,
        "combine": "vixie", "combine_documented": True,
        "default_tz": "local", "tz_settable": True,
        "range_wrap": False,
        "single_step": False,
        "names_in_lists": False,
        "hash_single": False,
        "min_interval_s": None,
        "dst": _dst("skip", "both", True, True, _URL_CRONTAB),
        "sources": {"syntax": _URL_CRONTAB, "days": _URL_CRONTAB, "tz": _URL_CRONTAB, "dst": _URL_CRONTAB},
    },
    "k8s": {
        "layout": ("minute", "hour", "dom", "month", "dow"),
        "min_fields": 5,
        "dow_base": 0, "dow_max": 6,
        "year_range": None,
        "specials": frozenset({"?"}),
        "dow_bare_l": False,
        "aliases": True,
        "combine": "robfig", "combine_documented": True,
        "default_tz": "controller-local", "tz_settable": True,
        "range_wrap": False,
        "single_step": True,
        "names_in_lists": True,
        "hash_single": False,
        "min_interval_s": None,
        "dst": _dst("skip", "first", True, False, _URL_ROBFIG),
        "sources": {"syntax": _URL_K8S, "days": "https://raw.githubusercontent.com/robfig/cron/v3.0.1/spec.go",
                    "tz": _URL_K8S, "dst": _URL_ROBFIG},
    },
    "github": {
        "layout": ("minute", "hour", "dom", "month", "dow"),
        "min_fields": 5,
        "dow_base": 0, "dow_max": 6,
        "year_range": None,
        "specials": frozenset(),
        "dow_bare_l": False,
        "aliases": False,
        "combine": "vixie", "combine_documented": False,
        "default_tz": "UTC", "tz_settable": True,
        "range_wrap": False,
        "single_step": False,
        "names_in_lists": True,
        "hash_single": False,
        "min_interval_s": 300,
        "dst": _dst("shift", "first", True, False, _URL_GITHUB),
        "sources": {"syntax": _URL_GITHUB, "days": _URL_GITHUB, "tz": _URL_GITHUB, "dst": _URL_GITHUB},
    },
    "spring": {
        "layout": ("second", "minute", "hour", "dom", "month", "dow"),
        "min_fields": 6,
        "dow_base": 0, "dow_max": 7,
        "year_range": None,
        "specials": frozenset({"?", "L", "L-n", "W", "LW", "nL", "#"}),
        "dow_bare_l": False,
        "aliases": True,
        "combine": "and", "combine_documented": True,
        "default_tz": "server", "tz_settable": True,
        "range_wrap": False,
        "single_step": True,
        "names_in_lists": True,
        "hash_single": False,
        "min_interval_s": None,
        "dst": _dst("shift", "first", False, False, _URL_SPRING),
        "sources": {"syntax": _URL_SPRING, "days": _URL_SPRING_SRC, "tz": _URL_SPRING, "dst": _URL_SPRING},
    },
    "quartz": {
        "layout": ("second", "minute", "hour", "dom", "month", "dow", "year"),
        "min_fields": 6,
        "dow_base": 1, "dow_max": 7,
        "year_range": (1970, 2099),
        "specials": frozenset({"?", "L", "L-n", "W", "LW", "nL", "#"}),
        "dow_bare_l": True,
        "aliases": False,
        "combine": "qmark", "combine_documented": True,
        "default_tz": "server", "tz_settable": True,
        "range_wrap": True,
        "single_step": True,
        "names_in_lists": True,
        "hash_single": False,
        "min_interval_s": None,
        "dst": _dst("shift", "first", False, False, _URL_QUARTZ),
        "sources": {"syntax": _URL_QUARTZ, "days": _URL_QUARTZ, "tz": _URL_QUARTZ, "dst": _URL_QUARTZ},
    },
    "eventbridge": {
        "layout": ("minute", "hour", "dom", "month", "dow", "year"),
        "min_fields": 6,
        "dow_base": 1, "dow_max": 7,
        "year_range": (1970, 2199),
        "specials": frozenset({"?", "L", "W", "nL", "#"}),
        "dow_bare_l": True,
        "aliases": False,
        "combine": "qmark", "combine_documented": True,
        "default_tz": "UTC", "tz_settable": False,
        "range_wrap": True,
        "single_step": True,
        "names_in_lists": True,
        "hash_single": True,
        "min_interval_s": None,
        "dst": _dst("shift", "first", True, True, _URL_EB_RULE),
        "sources": {"syntax": _URL_EB_RULE, "days": _URL_EB_RULE, "tz": _URL_EB_RULE, "dst": _URL_EB_RULE},
    },
    "eventbridge-scheduler": {
        "layout": ("minute", "hour", "dom", "month", "dow", "year"),
        "min_fields": 6,
        "dow_base": 1, "dow_max": 7,
        "year_range": (1970, 2199),
        "specials": frozenset({"?", "L", "W", "nL", "#"}),
        "dow_bare_l": True,
        "aliases": False,
        "combine": "qmark", "combine_documented": True,
        "default_tz": "UTC", "tz_settable": True,
        "range_wrap": True,
        "single_step": True,
        "names_in_lists": True,
        "hash_single": True,
        "min_interval_s": None,
        "dst": _dst("skip", "second", True, True, _URL_EB_SCHED),
        "sources": {"syntax": _URL_EB_SCHED, "days": _URL_EB_SCHED, "tz": _URL_EB_SCHED, "dst": _URL_EB_SCHED},
    },
}

DIALECT_IDS = tuple(DIALECTS)

# Order used by the DST table in ``explain --dst`` (EventBridge rules are UTC only, so no row).
DST_TABLE_IDS = ("unix", "cronie", "k8s", "github", "spring", "quartz", "eventbridge-scheduler")

FIELD_BOUNDS = {"second": (0, 59), "minute": (0, 59), "hour": (0, 23), "dom": (1, 31), "month": (1, 12)}

MAX_RUNS = 1_100_000          # most runs one window may contain before E_TOO_MANY_RUNS
MAX_DAYS = 3660               # longest search/diff window and search horizon
MAX_COUNT = 1000              # most runs `next --count` returns
