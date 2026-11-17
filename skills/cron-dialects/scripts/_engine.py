"""Cron engine: parse and validate per dialect, compute run instants with DST policy.

Standard library only.  Errors are raised as ``CronError`` (code + parameters,
rendered in the user's language by ``cronx``); non-fatal findings are
``Warn`` objects.

Run computation is a set jump, not a minute scan: month filter -> matching
days (combination rule) -> time-of-day product -> wall clock to instant with
DST gap/fold policy.
"""
from __future__ import annotations

import calendar
import re
import time
import zoneinfo
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterator, NamedTuple

from _dialect_table import (
    ALIASES, DIALECTS, DOW_NAMES, FIELD_BOUNDS, MAX_DAYS, MAX_RUNS, MONTH_NAMES,
)

UTC = timezone.utc


# --------------------------------------------------------------------------
# errors and warnings
# --------------------------------------------------------------------------

class CronError(Exception):
    """A user-facing error with a stable code and a process exit code."""

    def __init__(self, code: str, exit_code: int = 2, source: str | None = None,
                 msg_key: str | None = None, **params):
        super().__init__(code)
        self.code = code
        self.msg_key = msg_key or code          # message table key; the public code stays stable
        self.exit_code = exit_code
        self.source = source
        self.params = params


@dataclass
class Warn:
    code: str
    params: dict = field(default_factory=dict)
    source: str | None = None


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

@dataclass
class Field:
    kind: str
    raw: str
    values: frozenset            # canonical values: dow is 0=Sunday..6=Saturday
    specials: tuple = ()         # ("L",) ("L-n", n) ("W", d) ("LW",) ("nL", sun0) ("#", sun0, n)
    star: bool = False           # first character is '*' (Vixie rule)
    free: bool = False           # unrestricted in robfig/cron v3 terms: '*' or '?' with step 1 or none
    plain_free: bool = False     # exactly '*' or '?'
    qmark: bool = False
    wrapped: bool = False        # contains a reversed range such as 22-2
    single_step: bool = False    # contains a/n (start with step, no range)
    has_names: bool = False


_NUM = re.compile(r"^\d+$")
_RE_DOM_LAST_N = re.compile(r"^L-(\d+)$")
_RE_DOM_W = re.compile(r"^(\d+)W$")
_RE_DOW_LAST = re.compile(r"^(\d+|[A-Z]{3})L$")
_RE_DOW_NTH = re.compile(r"^(\d+|[A-Z]{3})#(\d+)$")


_SPECIALS_BY_FIELD = {"dom": {"?", "L", "L-n", "W", "LW"}, "dow": {"?", "#", "L", "nL"}}


def _allowed_here(kind: str, allowed) -> str:
    """Special characters this dialect accepts in the named field (for error hints)."""
    return " ".join(sorted(set(allowed) & _SPECIALS_BY_FIELD.get(kind, set()))) or "-"


def _bounds(kind: str, d: dict) -> tuple[int, int]:
    if kind == "dow":
        return d["dow_base"], d["dow_max"]
    if kind == "year":
        return d["year_range"]
    return FIELD_BOUNDS[kind]


def _value(kind: str, tok: str, d: dict, dialect: str, field_text: str) -> int:
    """Numeric value of one token in the dialect's own numbering."""
    t = tok.upper()
    if _NUM.match(t):
        return int(t)
    if kind == "month" and t in MONTH_NAMES:
        return MONTH_NAMES.index(t) + 1
    if kind == "dow" and t in DOW_NAMES:
        return DOW_NAMES.index(t) + d["dow_base"]
    raise CronError("E_SYNTAX", source=d["sources"]["syntax"], dialect=dialect, field=kind, token=tok, text=field_text)


def _check_range(kind: str, v: int, d: dict, dialect: str) -> None:
    lo, hi = _bounds(kind, d)
    if not lo <= v <= hi:
        raise CronError("E_RANGE", source=d["sources"]["syntax"], dialect=dialect, field=kind, value=v, lo=lo, hi=hi)


def _canon(kind: str, v: int, d: dict) -> int:
    return (v - d["dow_base"]) % 7 if kind == "dow" else v


def _parse_field(kind: str, text: str, d: dict, dialect: str, notes: list[str]) -> Field:
    lo, hi = _bounds(kind, d)
    star_hi = d["dow_base"] + 6 if kind == "dow" else hi        # '*' in the weekday field covers one week
    values: set[int] = set()
    specials: list[tuple] = []
    wrapped = False
    single_step = False
    has_names = bool(re.search(r"[A-Za-z]", text)) and kind in ("month", "dow")
    qmark = False
    hash_parts = 0
    allowed = d["specials"]
    src = d["sources"]["syntax"]

    if text == "?" or text.startswith("?"):
        if kind not in ("dom", "dow") or "?" not in allowed or text != "?":
            raise CronError("E_SPECIAL_UNSUPPORTED", source=src, dialect=dialect, token=text, field=kind,
                            allowed=_allowed_here(kind, allowed))
        qmark = True
        full = range(1, 32) if kind == "dom" else range(0, 7)
        return Field(kind, "?", frozenset(full), (), star=True, free=True, plain_free=True, qmark=True)

    parts = text.split(",")
    for part in parts:
        if part == "":
            raise CronError("E_SYNTAX", source=src, dialect=dialect, field=kind, token=part, text=text)
        up = part.upper()
        step = None
        base = up
        if "/" in up:
            base, _, s = up.partition("/")
            if not _NUM.match(s) or int(s) < 1 or "/" in s:
                raise CronError("E_SYNTAX", source=src, dialect=dialect, field=kind, token=part, text=text)
            step = int(s)
        # ---- special tokens ------------------------------------------------
        sp = None
        if kind == "dom":
            m = _RE_DOM_LAST_N.match(base)
            if base == "L":
                sp, key = ("L",), "L"
            elif base == "LW":
                sp, key = ("LW",), "LW"
            elif m:
                n = int(m.group(1))
                if not 1 <= n <= 30:
                    raise CronError("E_RANGE", source=src, dialect=dialect, field=kind, value=n, lo=1, hi=30)
                sp, key = ("L-n", n), "L-n"
            else:
                m = _RE_DOM_W.match(base)
                if m:
                    day = int(m.group(1))
                    _check_range("dom", day, d, dialect)
                    sp, key = ("W", day), "W"
        elif kind == "dow":
            m = _RE_DOW_NTH.match(base)
            m2 = _RE_DOW_LAST.match(base)
            if m:
                n = int(m.group(2))
                if not 1 <= n <= 5:
                    raise CronError("E_NTH_RANGE", source=src, dialect=dialect, value=n)
                v = _value("dow", m.group(1), d, dialect, text)
                _check_range("dow", v, d, dialect)
                sp, key = ("#", _canon("dow", v, d), n), "#"
                hash_parts += 1
            elif base == "L":
                if not d["dow_bare_l"]:
                    raise CronError("E_SPECIAL_UNSUPPORTED", source=src, dialect=dialect, token=part, field=kind,
                                    allowed=_allowed_here(kind, allowed))
                values.add(6)                 # bare L in the weekday field = last day of the week (Saturday)
                continue
            elif m2:
                v = _value("dow", m2.group(1), d, dialect, text)
                _check_range("dow", v, d, dialect)
                sp, key = ("nL", _canon("dow", v, d)), "nL"
        if sp is not None:
            if step is not None or key not in allowed:
                raise CronError("E_SPECIAL_UNSUPPORTED", source=src, dialect=dialect, token=part, field=kind,
                                allowed=_allowed_here(kind, allowed))
            specials.append(sp)
            continue
        if re.search(r"[LW#]", base) and not re.search(r"^[A-Z]{3}(-[A-Z]{3})?$", base):
            raise CronError("E_SPECIAL_UNSUPPORTED", source=src, dialect=dialect, token=part, field=kind,
                            allowed=_allowed_here(kind, allowed))
        # ---- plain tokens ---------------------------------------------------
        if base == "*":
            a, b = lo, star_hi
        elif "-" in base:
            x, _, y = base.partition("-")
            if not x or not y or "-" in y:
                raise CronError("E_SYNTAX", source=src, dialect=dialect, field=kind, token=part, text=text)
            a = _value(kind, x, d, dialect, text)
            b = _value(kind, y, d, dialect, text)
            if kind == "dow" and d["dow_max"] == 7 and y in DOW_NAMES and y == "SUN" and a > 0:
                b = 7                                           # FRI-SUN: Sunday closes the range
            _check_range(kind, a, d, dialect)
            _check_range(kind, b, d, dialect)
        else:
            a = _value(kind, base, d, dialect, text)
            _check_range(kind, a, d, dialect)
            if step is None:
                values.add(_canon(kind, a, d))
                continue
            b = hi                                              # a/n = from a to the end, every n
            single_step = True
            if not d["single_step"]:
                notes.append("step")
        if "-" in base and a > b:
            if not d["range_wrap"]:
                raise CronError("E_RANGE_REVERSED", source=src, dialect=dialect, field=kind, token=part)
            wrapped = True
            seq = list(range(a, hi + 1)) + list(range(lo, b + 1))
        else:
            seq = list(range(a, b + 1))
        if step:
            seq = seq[::step]
        for v in seq:
            values.add(_canon(kind, v, d))
    if hash_parts > 1 and d["hash_single"]:
        raise CronError("E_HASH_MULTI", source=src, dialect=dialect, field=kind)
    if has_names and not d["names_in_lists"] and ("," in text or "-" in text):
        notes.append("name_range")
    star = text.startswith("*")
    plain_free = text == "*"
    free = any(re.fullmatch(r"\*(/0*1)?", p) for p in text.split(","))
    return Field(kind, text.upper(), frozenset(values), tuple(specials), star=star, free=free,
                 plain_free=plain_free, qmark=qmark, wrapped=wrapped, single_step=single_step, has_names=has_names)


@dataclass
class Schedule:
    dialect: str
    source: str
    fields: dict
    normalized: str
    warnings: list
    _times: list | None = None
    _days: dict = field(default_factory=dict)

    @property
    def d(self) -> dict:
        return DIALECTS[self.dialect]

    @property
    def months(self) -> frozenset:
        return self.fields["month"].values

    @property
    def years(self) -> frozenset | None:
        f = self.fields.get("year")
        if f is None or f.plain_free:
            return None
        return f.values

    def per_day(self) -> int:
        n = len(self.fields["hour"].values) * len(self.fields["minute"].values)
        sec = self.fields.get("second")
        return n * (len(sec.values) if sec else 1)

    def times(self) -> list[int]:
        """Sorted seconds-of-day at which the expression fires on a matching day."""
        if self._times is None:
            secs = sorted(self.fields["second"].values) if "second" in self.fields else [0]
            self._times = sorted(h * 3600 + m * 60 + s for h in self.fields["hour"].values
                                 for m in self.fields["minute"].values for s in secs)
        return self._times

    # ---- day matching -----------------------------------------------------

    def _dom_days(self, y: int, m: int) -> set[int]:
        f = self.fields["dom"]
        last = calendar.monthrange(y, m)[1]
        out = {v for v in f.values if v <= last}
        for sp in f.specials:
            if sp[0] == "L":
                out.add(last)
            elif sp[0] == "L-n":
                if last - sp[1] >= 1:
                    out.add(last - sp[1])
            elif sp[0] == "W":
                if sp[1] <= last:
                    out.add(_nearest_weekday(y, m, sp[1], last))
            elif sp[0] == "LW":
                out.add(_nearest_weekday(y, m, last, last, last_weekday=True))
        return out

    def _dow_days(self, y: int, m: int) -> set[int]:
        f = self.fields["dow"]
        last = calendar.monthrange(y, m)[1]
        out = set()
        wd0 = (calendar.weekday(y, m, 1) + 1) % 7                 # weekday of the 1st, 0=Sunday
        if f.values:
            for day in range(1, last + 1):
                if (wd0 + day - 1) % 7 in f.values:
                    out.add(day)
        for sp in f.specials:
            if sp[0] == "#":
                first = 1 + (sp[1] - wd0) % 7
                day = first + 7 * (sp[2] - 1)
                if day <= last:
                    out.add(day)
            elif sp[0] == "nL":
                wd_last = (wd0 + last - 1) % 7
                out.add(last - (wd_last - sp[1]) % 7)
        return out

    def day_set(self, y: int, m: int) -> tuple[int, ...]:
        key = (y, m)
        got = self._days.get(key)
        if got is not None:
            return got
        dom, dow = self.fields["dom"], self.fields["dow"]
        last = calendar.monthrange(y, m)[1]
        everything = set(range(1, last + 1))
        dom_days = everything if dom.plain_free else self._dom_days(y, m)
        dow_days = everything if dow.plain_free else self._dow_days(y, m)
        mode = self.d["combine"]
        if mode in ("vixie", "robfig"):
            anded = (dom.star or dow.star) if mode == "vixie" else (dom.free or dow.free)
            res = (dom_days & dow_days) if anded else (dom_days | dow_days)
        elif mode == "and":
            res = dom_days & dow_days
        else:                                                      # qmark: the '?' side does not constrain
            res = dow_days if dom.qmark else dom_days
        got = tuple(sorted(res))
        self._days[key] = got
        return got


def _nearest_weekday(y: int, m: int, day: int, last: int, last_weekday: bool = False) -> int:
    """Nearest Monday-Friday to ``day`` without leaving the month; LW = last weekday of the month."""
    wd = calendar.weekday(y, m, day)           # Monday=0
    if wd < 5:
        return day
    if last_weekday:
        return day - (wd - 4)
    if wd == 5:                                # Saturday
        return day - 1 if day > 1 else day + 2
    return day + 1 if day + 1 <= last else day - 2   # Sunday


def _alias_expand(expr: str, dialect: str, d: dict) -> str:
    low = expr.lower()
    if not d["aliases"] or low not in ALIASES:
        raise CronError("E_ALIAS_UNSUPPORTED", source=d["sources"]["syntax"], dialect=dialect, alias=expr,
                        supported=" ".join(sorted(ALIASES)) if d["aliases"] else "-")
    five = ALIASES[low]
    return "0 " + five if d["layout"][0] == "second" else five


def parse(expr: str, dialect: str) -> Schedule:
    """Parse and validate ``expr`` for ``dialect``; raises CronError on invalid input."""
    if dialect not in DIALECTS:
        raise CronError("E_UNKNOWN_DIALECT", dialect=dialect, known=" ".join(DIALECTS))
    d = DIALECTS[dialect]
    text = expr.strip()
    if re.match(r"^(CRON_TZ|TZ)=", text):
        raise CronError("E_TZ_IN_EXPR", source=d["sources"]["tz"], dialect=dialect)
    if dialect.startswith("eventbridge"):
        m = re.match(r"^cron\((.*)\)$", text, re.I | re.S)
        if m:
            text = m.group(1).strip()
    elif re.match(r"^cron\(", text, re.I):
        raise CronError("E_CRON_WRAPPER", source=d["sources"]["syntax"], dialect=dialect)
    if text.startswith("@"):
        text = _alias_expand(text, dialect, d)
    parts = text.split()
    layout = d["layout"]
    lo_n, hi_n = d["min_fields"], len(layout)
    if not lo_n <= len(parts) <= hi_n:
        raise CronError("E_FIELD_COUNT", source=d["sources"]["syntax"], dialect=dialect,
                        expected=str(lo_n) if lo_n == hi_n else f"{lo_n} or {hi_n}",
                        names=" ".join({"dom": "day-of-month", "dow": "day-of-week"}.get(k, k) for k in layout), got=len(parts))
    notes: list[str] = []
    fields = {}
    for kind, part in zip(layout, parts):
        fields[kind] = _parse_field(kind, part, d, dialect, notes)
    if d["combine"] == "qmark":
        q = sum(1 for k in ("dom", "dow") if fields[k].qmark)
        if q != 1:
            raise CronError("E_QMARK_REQUIRED", source=d["sources"]["days"], dialect=dialect,
                            dom=fields["dom"].raw, dow=fields["dow"].raw)
    sched = Schedule(dialect, expr, fields, " ".join(f.raw for f in fields.values()), [])
    sched.warnings = _static_warnings(sched, notes)
    return sched


def _static_warnings(s: Schedule, notes: list[str]) -> list[Warn]:
    d = s.d
    out: list[Warn] = []
    dom, dow = s.fields["dom"], s.fields["dow"]
    both_restricted = not dom.plain_free and not dow.plain_free
    mode = d["combine"]
    if mode in ("vixie", "robfig"):
        flag = (lambda f: f.star) if mode == "vixie" else (lambda f: f.free)
        if both_restricted and not flag(dom) and not flag(dow):
            out.append(Warn("W_DOM_DOW_OR", {"dom": dom.raw, "dow": dow.raw}, d["sources"]["days"]))
            if mode == "robfig" and (dom.star or dow.star):
                star_field = dom if dom.star else dow
                out.append(Warn("W_ROBFIG_STEP", {"field": star_field.kind, "token": star_field.raw},
                                d["sources"]["days"]))
        elif both_restricted and mode == "robfig":
            pass
        elif both_restricted and mode == "vixie":
            star_field = dom if dom.star else dow
            out.append(Warn("W_VIXIE_STAR", {"field": star_field.kind, "token": star_field.raw}, d["sources"]["days"]))
        if both_restricted and not d["combine_documented"]:
            out.append(Warn("W_COMBINE_ASSUMED", {"dialect": s.dialect}, d["sources"]["days"]))
    elif mode == "and" and both_restricted:
        out.append(Warn("W_DOM_DOW_AND", {"dom": dom.raw, "dow": dow.raw}, d["sources"]["days"]))
    if "step" in notes:
        out.append(Warn("W_STEP_NO_RANGE", {"dialect": s.dialect}, d["sources"]["syntax"]))
    if "name_range" in notes:
        out.append(Warn("W_NAME_RANGE", {"dialect": s.dialect}, d["sources"]["syntax"]))
    limit = d["min_interval_s"]
    if limit:
        gap = _min_interval(s)
        if gap is not None and gap < limit:
            out.append(Warn("W_MIN_INTERVAL", {"seconds": gap, "limit": limit}, d["sources"]["syntax"]))
    return out


def _min_interval(s: Schedule) -> int | None:
    """Smallest gap in seconds between two runs on one day (None when it fires at most once a day)."""
    if len(s.fields["hour"].values) * len(s.fields["minute"].values) > 5000:
        mins = sorted(s.fields["minute"].values)
        gaps = [b - a for a, b in zip(mins, mins[1:])]
        return min(gaps) * 60 if gaps else None
    t = s.times()
    if len(t) < 2:
        return None
    return min(b - a for a, b in zip(t, t[1:]))


# --------------------------------------------------------------------------
# time zones
# --------------------------------------------------------------------------

class Zone:
    """A resolved time zone.  ``fixed`` zones (UTC, +09:00) never change offset."""

    def __init__(self, name: str, tz, fixed: bool):
        self.name = name
        self.tz = tz
        self.fixed = fixed

    def offset(self, naive: datetime, fold: int) -> int:
        return int(naive.replace(tzinfo=self.tz, fold=fold).utcoffset().total_seconds())

    def offset_at(self, epoch: int) -> int:
        return int(datetime.fromtimestamp(epoch, self.tz).utcoffset().total_seconds())

    def local_iso(self, epoch: int) -> str:
        return datetime.fromtimestamp(epoch, self.tz).isoformat()

    def local_date(self, epoch: int) -> date:
        return datetime.fromtimestamp(epoch, self.tz).date()


_FIXED = re.compile(r"^([+-])(\d{2}):?(\d{2})$")


def resolve_zone(name: str | None) -> Zone:
    """UTC, a fixed offset (+09:00) or an IANA name; raises E_UNKNOWN_TZ / E_NO_TZDATA."""
    if name is None or name.strip().upper() in ("UTC", "Z", "GMT"):
        return Zone("UTC", UTC, True)
    m = _FIXED.match(name.strip())
    if m:
        secs = int(m.group(2)) * 3600 + int(m.group(3)) * 60
        if m.group(1) == "-":
            secs = -secs
        return Zone(name.strip(), timezone(timedelta(seconds=secs)), True)
    try:
        return Zone(name, zoneinfo.ZoneInfo(name), False)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
        try:
            have = bool(zoneinfo.available_timezones())
        except OSError:
            have = False
        if not have:
            raise CronError("E_NO_TZDATA", exit_code=4, name=name)
        raise CronError("E_UNKNOWN_TZ", name=name)


def zone_warnings(dialect: str, tz_given: bool) -> list[Warn]:
    d = DIALECTS[dialect]
    if tz_given:
        return []
    kind = d["default_tz"]
    if kind == "UTC":
        return []
    code = {"local": "W_TZ_LOCAL", "controller-local": "W_TZ_CONTROLLER", "server": "W_TZ_SERVER"}[kind]
    return [Warn(code, {"dialect": dialect}, d["sources"]["tz"])]


def check_zone_for_dialect(dialect: str, zone: Zone) -> None:
    d = DIALECTS[dialect]
    if not d["tz_settable"] and zone.name != "UTC":
        raise CronError("E_TZ_UNSUPPORTED", source=d["sources"]["tz"], dialect=dialect, tz=zone.name)


# --------------------------------------------------------------------------
# instants
# --------------------------------------------------------------------------

class Run(NamedTuple):
    instant: int          # UTC epoch seconds
    offset: int           # UTC offset (seconds) the run's local time uses
    kind: str             # normal | gap-shifted | fold-first | fold-second


def _day_normal_offset(zone: Zone, day: date) -> int | None:
    """The UTC offset if it is constant all day, else None (a DST transition falls on this wall-clock day)."""
    if zone.fixed:
        return int(zone.tz.utcoffset(None).total_seconds())
    start = datetime(day.year, day.month, day.day)
    end = datetime(day.year, day.month, day.day, 23, 59, 59)
    o0, o1 = zone.offset(start, 0), zone.offset(end, 1)
    return o0 if o0 == o1 else None


def _transition_instant(zone: Zone, lo: int, hi: int, post: int) -> int:
    """First instant in (lo, hi] whose offset is ``post`` (lo has the earlier offset)."""
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if zone.offset_at(mid) == post:
            hi = mid
        else:
            lo = mid
    return hi


def resolve_wall(zone: Zone, wall: datetime, base: int, sod: int, policy: dict) -> tuple[list[Run], str | None]:
    """Instants for one local wall-clock time and the skipped marker ('gap') if the policy dropped it."""
    o0, o1 = zone.offset(wall, 0), zone.offset(wall, 1)
    if o0 == o1:
        return [Run(base + sod - o0, o0, "normal")], None
    if o0 < o1:                                                    # clocks jumped forward: wall time does not exist
        if policy["gap"] == "skip":
            return [], "gap"
        t = _transition_instant(zone, base + sod - o1, base + sod - o0, o1)
        return [Run(t, o1, "gap-shifted")], None
    first = Run(base + sod - o0, o0, "fold-first")                 # clocks went back: wall time happens twice
    second = Run(base + sod - o1, o1, "fold-second")
    if policy["fold"] == "first":
        return [first], None
    if policy["fold"] == "second":
        return [second], None
    return [first, second], None


@dataclass
class Skipped:
    count: int = 0
    first: str | None = None


def day_runs(s: Schedule, zone: Zone, policy: dict, day: date, skipped: Skipped | None = None) -> list[Run]:
    base = calendar.timegm((day.year, day.month, day.day, 0, 0, 0))
    tod = s.times()
    off = _day_normal_offset(zone, day)
    if off is not None:
        return [Run(base + sod - off, off, "normal") for sod in tod]
    out: dict[int, Run] = {}
    midnight = datetime(day.year, day.month, day.day)
    for sod in tod:
        wall = midnight + timedelta(seconds=sod)
        runs, skip = resolve_wall(zone, wall, base, sod, policy)
        if skip and skipped is not None:
            skipped.count += 1
            if skipped.first is None:
                skipped.first = wall.isoformat()
        for r in runs:
            out.setdefault(r.instant, r)
    return sorted(out.values())


def _months(d0: date, d1: date) -> Iterator[tuple[int, int]]:
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def iter_days(s: Schedule, d0: date, d1: date) -> Iterator[date]:
    """Matching days in [d0, d1] (inclusive), in order."""
    years = s.years
    ymax = max(years) if years else None
    for y, m in _months(d0, d1):
        if ymax is not None and y > ymax:
            return
        if m not in s.months or (years is not None and y not in years):
            continue
        for dd in s.day_set(y, m):
            day = date(y, m, dd)
            if d0 <= day <= d1:
                yield day


def estimate_runs(s: Schedule, zone: Zone, start: int, end: int) -> int:
    d0 = zone.local_date(start - 86400)
    d1 = zone.local_date(end + 86400)
    return sum(1 for _ in iter_days(s, d0, d1)) * s.per_day()


def iter_runs(s: Schedule, zone: Zone, policy: dict, start: int, end: int,
              skipped: Skipped | None = None) -> Iterator[Run]:
    """Runs with start <= instant < end in order."""
    d0 = zone.local_date(start - 86400)
    d1 = zone.local_date(end + 86400)
    for day in iter_days(s, d0, d1):
        for r in day_runs(s, zone, policy, day, skipped):
            if r.instant >= end:
                return
            if r.instant >= start:
                yield r


def run_instants(s: Schedule, zone: Zone, policy: dict, start: int, end: int,
                 skipped: Skipped | None = None) -> set[int]:
    if estimate_runs(s, zone, start, end) > MAX_RUNS:
        raise CronError("E_TOO_MANY_RUNS", limit=f"{MAX_RUNS:,}")
    return {r.instant for r in iter_runs(s, zone, policy, start, end, skipped)}


def next_runs(s: Schedule, zone: Zone, policy: dict, start: int, count: int | None, until: int | None,
              skipped: Skipped | None = None) -> list[Run]:
    """The next ``count`` runs from ``start``; or all runs up to ``until`` when it is given."""
    horizon = start + MAX_DAYS * 86400
    end = until if until is not None else horizon
    if until is not None and estimate_runs(s, zone, start, end) > MAX_RUNS:
        raise CronError("E_TOO_MANY_RUNS", msg_key="E_TOO_MANY_RUNS_NEXT", limit=f"{MAX_RUNS:,}")
    out: list[Run] = []
    for r in iter_runs(s, zone, policy, start, end, skipped):
        out.append(r)
        if count is not None and len(out) >= count:
            break
    return out


# --------------------------------------------------------------------------
# time input
# --------------------------------------------------------------------------

_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?\s*(Z|[+-]\d{2}:?\d{2})?$", re.I)


def parse_instant(text: str, zone: Zone) -> int:
    """ISO date or date-time -> epoch seconds.  Without Z/offset the text is local time in ``zone``."""
    m = _TIME.match(text.strip())
    if not m:
        raise CronError("E_BAD_TIME", text=text)
    y, mo, dd, hh, mi, ss, off = m.groups()
    try:
        naive = datetime(int(y), int(mo), int(dd), int(hh or 0), int(mi or 0), int(ss or 0))
    except ValueError:
        raise CronError("E_BAD_TIME", text=text) from None
    base = calendar.timegm((naive.year, naive.month, naive.day, naive.hour, naive.minute, naive.second))
    if off:
        if off.upper() == "Z":
            return base
        sign = -1 if off[0] == "-" else 1
        digits = off[1:].replace(":", "")
        return base - sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)
    return base - zone.offset(naive, 0)


def now_minute() -> int:
    return int(time.time()) // 60 * 60


def iso_utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def window(start: int, days: int) -> tuple[int, int]:
    if not 1 <= days <= MAX_DAYS:
        raise CronError("E_DAYS_RANGE", days=days, max=MAX_DAYS)
    return start, start + days * 86400


# --------------------------------------------------------------------------
# diff and DST explanation
# --------------------------------------------------------------------------

@dataclass
class DiffResult:
    count_a: int
    count_b: int
    equivalent: bool
    first_mismatch: int | None = None
    only_in: str | None = None


def diff_sets(a: set[int], b: set[int]) -> DiffResult:
    sym = a ^ b
    if not sym:
        return DiffResult(len(a), len(b), True)
    first = min(sym)
    return DiffResult(len(a), len(b), False, first, "a" if first in a else "b")


def dst_rows(s: Schedule, zone: Zone, year: int, policies: dict[str, dict], limit: int = 3) -> list[dict]:
    """For each DST transition day in ``year``, the wall times of ``s`` that hit the gap/fold and what each scheduler does.

    The day-of-month/day-of-week filter is ignored: the table answers "if the job is due at this wall time on that day".
    """
    rows = []
    if zone.fixed:
        return rows
    tod = s.times()
    day = date(year, 1, 1)
    while day.year == year:
        start = datetime(day.year, day.month, day.day)
        end = datetime(day.year, day.month, day.day, 23, 59, 59)
        o0, o1 = zone.offset(start, 0), zone.offset(end, 1)
        if o0 != o1:
            base = calendar.timegm((day.year, day.month, day.day, 0, 0, 0))
            affected = []
            for sod in tod:
                wall = start + timedelta(seconds=sod)
                if zone.offset(wall, 0) != zone.offset(wall, 1):
                    affected.append((sod, wall))
            kind = "gap" if o1 > o0 else "fold"
            for i, (sod, wall) in enumerate(affected[:limit]):
                results = {}
                for pid, pol in policies.items():
                    runs, skip = resolve_wall(zone, wall, base, sod, pol)
                    results[pid] = {"skipped": bool(skip),
                                    "runs": [{"local": zone.local_iso(r.instant), "kind": r.kind} for r in runs]}
                more = len(affected) - limit if i == min(limit, len(affected)) - 1 else 0
                rows.append({"date": day.isoformat(), "wall": wall.strftime("%H:%M:%S"), "type": kind,
                             "more": max(0, more), "results": results})
        day += timedelta(days=1)
    return rows
