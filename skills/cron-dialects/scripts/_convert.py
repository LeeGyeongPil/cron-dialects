"""Rewrite a cron expression from one dialect to another.

The rewrite only decides *what to write*; whether it means the same thing is
decided by the caller, which always diffs run instants afterwards.  When one
expression cannot express the original, ``convert`` returns reasons (and, for
the day-of-month OR day-of-week case, a split into two expressions).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from _dialect_table import DIALECTS, DOW_NAMES
from _engine import CronError, Field, Schedule, parse


@dataclass
class Conversion:
    converted: str | None = None
    split: list[str] = field(default_factory=list)
    reasons: list[tuple[str, dict]] = field(default_factory=list)


def _runs(numbers: list[int]) -> str:
    """[1,2,3,5] -> '1-3,5' (consecutive numbers collapse into ranges)."""
    out, i = [], 0
    nums = sorted(set(numbers))
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ",".join(out)


def _render_set(values: frozenset, kind: str, t: dict) -> str:
    if kind == "dow":
        return _runs([(v + t["dow_base"]) for v in values])
    return _runs(list(values))


def _copy_simple(f: Field, t: dict) -> str:
    """Time fields, month, year: keep the text unless the target cannot read it."""
    needs_set = (f.wrapped and not t["range_wrap"]) or (f.single_step and not t["single_step"])
    if needs_set:
        return _render_set(f.values, f.kind, t)
    return f.raw


_NAME_PART = re.compile(r"^[A-Z]{3}(-[A-Z]{3})?$")


def _map_dow_value(token: str, src: dict, tgt: dict) -> int | None:
    if not token.isdigit():
        return None
    v = int(token)
    return (v - src["dow_base"]) % 7 + tgt["dow_base"]


def _convert_dow(f: Field, src: dict, tgt: dict) -> tuple[str | None, str | None]:
    """Weekday text for the target; second item is an unsupported special token if any."""
    out = []
    for part in f.raw.split(","):
        base, _, step = part.partition("/")
        if base in ("*", "?"):
            out.append(part if base == "*" else "*")
            continue
        m = re.match(r"^(\d+|[A-Z]{3})#(\d+)$", base)
        if m:
            if "#" not in tgt["specials"]:
                return None, part
            tok = m.group(1)
            mapped = _map_dow_value(tok, src, tgt)
            out.append(f"{tok if mapped is None else mapped}#{m.group(2)}")
            continue
        m = re.match(r"^(\d+|[A-Z]{3})L$", base)
        if m:
            if "nL" not in tgt["specials"]:
                return None, part
            tok = m.group(1)
            mapped = _map_dow_value(tok, src, tgt)
            out.append(f"{tok if mapped is None else mapped}L")
            continue
        if base == "L":
            if not tgt["dow_bare_l"]:
                return None, part
            out.append("L")
            continue
        if step:
            # a/n or a-b/n: spell out the weekdays, numbering differs between dialects
            vals = _part_values(part, src)
            out.append(_render_set(vals, "dow", tgt))
            continue
        if _NAME_PART.match(base) and "-" not in base:
            out.append(base)
            continue
        if _NAME_PART.match(base):
            a, b = base.split("-")
            if DOW_NAMES.index(a) <= DOW_NAMES.index(b):
                out.append(base)
            else:
                out.append(_render_set(_part_values(part, src), "dow", tgt))
            continue
        if "-" in base:
            x, y = base.split("-")
            nx, ny = _map_dow_value(x, src, tgt), _map_dow_value(y, src, tgt)
            if nx is not None and ny is not None and nx <= ny and (int(y) - int(x)) == (ny - nx):
                out.append(f"{nx}-{ny}")
            else:
                out.append(_render_set(_part_values(part, src), "dow", tgt))
            continue
        mapped = _map_dow_value(base, src, tgt)
        out.append(str(mapped) if mapped is not None else base)
    return ",".join(dict.fromkeys(out)), None


def _part_values(part: str, src: dict) -> frozenset:
    """Canonical weekday set of one list element (re-parsed in the source dialect)."""
    names = {n: i for i, n in enumerate(DOW_NAMES)}
    base, _, step = part.partition("/")
    lo, hi = src["dow_base"], src["dow_base"] + 6
    if src["dow_max"] == 7 and src["dow_base"] == 0:
        hi_range = 7
    else:
        hi_range = src["dow_max"]

    def val(tok: str) -> int:
        return names[tok] + src["dow_base"] if tok in names else int(tok)

    if base == "*":
        a, b = lo, hi
    elif "-" in base:
        x, y = base.split("-")
        a, b = val(x), val(y)
        if y == "SUN" and src["dow_max"] == 7 and a > 0:
            b = 7
    else:
        a, b = val(base), hi_range
    seq = list(range(a, b + 1)) if a <= b else list(range(a, hi_range + 1)) + list(range(lo, b + 1))
    if step:
        seq = seq[::int(step)]
    return frozenset((v - src["dow_base"]) % 7 for v in seq)


def _nth_weekday(dom: Field, dow: Field, dow_txt: str) -> str | None:
    """Day-of-month '1-7' ANDed with one weekday -> 'W#1' (the same days), else None."""
    m = re.match(r"^(\d+)-(\d+)$", dom.raw)
    if not m or dow.specials or "," in dow.raw or "/" in dow.raw or "-" in dow.raw or dow.raw in ("*", "?"):
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a % 7 != 1 or a > 29:
        return None
    k = (a - 1) // 7
    if b != min(a + 6, 31) and not (a == 29 and b == 31):
        return None
    return f"{dow_txt}#{k + 1}"


def _dom_text(f: Field, tgt: dict) -> tuple[str | None, str | None]:
    for sp in f.specials:
        key = {"L": "L", "L-n": "L-n", "W": "W", "LW": "LW"}[sp[0]]
        if key not in tgt["specials"]:
            return None, f.raw
    if f.raw in ("*", "?"):
        return "*", None
    return (f.raw if f.specials else _copy_simple(f, tgt)), None


def _mode(s: Schedule) -> str:
    """none | dom | dow | or | and — which day fields constrain the schedule."""
    dom, dow = s.fields["dom"], s.fields["dow"]
    c = s.d["combine"]
    if c == "qmark":
        if dom.qmark:
            return "none" if dow.plain_free else "dow"
        return "none" if dom.plain_free else "dom"
    if dom.plain_free and dow.plain_free:
        return "none"
    if dom.plain_free:
        return "dow"
    if dow.plain_free:
        return "dom"
    if c == "vixie" and not dom.star and not dow.star:
        return "or"
    if c == "robfig" and not dom.free and not dow.free:
        return "or"
    return "and"


def _unstar(text: str, lo: int, hi: int) -> str:
    """Replace a leading '*' in each list item by an explicit range (``*/2`` -> ``1-31/2``)."""
    return ",".join(f"{lo}-{hi}{x[1:]}" if x.startswith("*") else x for x in text.split(","))


def convert(src: Schedule, target: str) -> Conversion:
    """Rewrite ``src`` for the ``target`` dialect."""
    t = DIALECTS[target]
    s = src.d
    res = Conversion()
    f = src.fields
    layout = t["layout"]

    # ---- seconds and year ----------------------------------------------------
    parts: dict[str, str] = {}
    if "second" in layout:
        parts["second"] = f["second"].raw if "second" in f else "0"
    elif "second" in f and f["second"].values != frozenset({0}):
        res.reasons.append(("C_SECONDS", {"target": target}))
    if "year" in layout:
        if "year" in f:
            parts["year"] = f["year"].raw
        elif t["min_fields"] == len(layout):          # the year field is required (EventBridge), optional in Quartz
            parts["year"] = "*"
        else:
            layout = layout[:-1]
    elif "year" in f and not f["year"].plain_free:
        res.reasons.append(("C_YEAR", {"target": target}))
    for kind in ("minute", "hour", "month"):
        parts[kind] = _copy_simple(f[kind], t)

    # ---- day fields -----------------------------------------------------------
    mode = _mode(src)
    dom_f, dow_f = f["dom"], f["dow"]
    dom_txt, bad = _dom_text(dom_f, t)
    if bad:
        res.reasons.append(("C_SPECIAL", {"token": bad, "target": target}))
    dow_txt, bad = _convert_dow(dow_f, s, t)
    if bad:
        res.reasons.append(("C_SPECIAL", {"token": bad, "target": target}))
    if res.reasons:
        return res
    assert dom_txt is not None and dow_txt is not None

    def build(dom: str, dow: str) -> str:
        p = dict(parts)
        p["dom"], p["dow"] = dom, dow
        return " ".join(p[k] for k in layout)

    tc = t["combine"]
    if tc in ("vixie", "robfig"):
        if mode == "none":
            res.converted = build("*", "*")
        elif mode == "dom":
            res.converted = build(dom_txt, "*")
        elif mode == "dow":
            res.converted = build("*", dow_txt)
        elif mode == "or":
            if tc == "vixie":      # crontab ANDs a field that starts with '*'; spell the range out to keep the OR
                dom_txt = _unstar(dom_txt, 1, 31)
                dow_txt = _unstar(dow_txt, t["dow_base"], t["dow_base"] + 6)
            res.converted = build(dom_txt, dow_txt)
        elif s["combine"] == tc or (tc == "vixie" and s["combine"] == "robfig"):
            res.converted = build(dom_txt, dow_txt)
        else:
            res.reasons.append(("C_AND", {"target": target}))
    else:                                                      # target has '?' (qmark) or ANDs (spring)
        free_dow = "?" if tc == "qmark" else "*"
        if mode == "none":
            res.converted = build("*", free_dow)
        elif mode == "dom":
            res.converted = build(dom_txt, free_dow)
        elif mode == "dow":
            res.converted = build("?" if tc == "qmark" else "*", dow_txt)
        elif mode == "or":
            res.split = [build(dom_txt, free_dow), build("?" if tc == "qmark" else "*", dow_txt)]
            res.reasons.append(("C_OR_SPLIT", {"target": target, "n": 2}))
        elif tc == "and" and s["combine"] in ("and", "vixie", "robfig"):
            res.converted = build(dom_txt, dow_txt)
        else:
            nth = _nth_weekday(dom_f, dow_f, dow_txt) if "#" in t["specials"] else None
            if nth:
                res.converted = build("?", nth)
            else:
                res.reasons.append(("C_AND", {"target": target}))
    if res.converted is not None:
        try:
            parse(res.converted, target)
        except CronError as e:
            res.reasons.append(("C_INVALID", {"target": target, "code": e.code}))
            res.converted = None
    for x in res.split:
        try:
            parse(x, target)
        except CronError as e:
            res.reasons.append(("C_INVALID", {"target": target, "code": e.code}))
            res.split = []
            break
    return res
