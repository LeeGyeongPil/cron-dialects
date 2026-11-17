#!/usr/bin/env python3
"""cronx - interpret, convert and verify cron expressions per scheduler dialect.

Subcommands: parse, next, explain, convert, diff, dialects.
Standard library only (Python 3.10+).  Messages: --lang en|ko.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import _i18n
from _convert import convert as convert_expression
from _dialect_table import DIALECT_IDS, DIALECTS, DOW_NAMES, DST_TABLE_IDS, MAX_COUNT, MAX_DAYS, MONTH_NAMES
from _engine import (
    CronError, Skipped, Warn, check_zone_for_dialect, diff_sets, dst_rows, estimate_runs, iso_utc,
    next_runs, now_minute, parse, parse_instant, resolve_zone, run_instants, window, zone_warnings,
)

PROG = "cronx"
EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_NO_RUN, EXIT_NO_TZDATA = 0, 1, 2, 3, 4


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

class Out:
    """Collects a command's text lines and JSON payload."""

    def __init__(self, lang: str):
        self.lang = lang
        self.lines: list[str] = []
        self.payload: dict = {}

    def t(self, key: str, **kw) -> str:
        return _i18n.t(self.lang, key, **kw)

    def line(self, text: str = "") -> None:
        self.lines.append(text)


def _warn_json(out: Out, warns: list[Warn]) -> list[dict]:
    return [{"code": w.code, "message": out.t("warn." + w.code, **w.params), "source": w.source} for w in warns]


def _warn_text(out: Out, warns: list[Warn]) -> None:
    if not warns:
        return
    out.line()
    out.line(out.t("label.warnings"))
    for w in warns:
        out.line(f"  {w.code}: {out.t('warn.' + w.code, **w.params)}")
        if w.source:
            out.line(f"      {out.t('label.source')}: {w.source}")


def _dedupe(warns: list[Warn]) -> list[Warn]:
    seen, res = set(), []
    for w in warns:
        key = (w.code, tuple(sorted((k, str(v)) for k, v in w.params.items())))
        if key not in seen:
            seen.add(key)
            res.append(w)
    return res


def _runs_json(zone, runs, show=None) -> list[dict]:
    items = []
    for r in runs:
        item = {"local": zone.local_iso(r.instant), "utc": iso_utc(r.instant), "dst": r.kind}
        if show is not None:
            item["show"] = show.local_iso(r.instant)
        items.append(item)
    return items


def _fmt_values(kind: str, f) -> str:
    """Readable value list of one parsed field."""
    if f.plain_free and not f.specials:
        return "*"
    vals = sorted(f.values)
    if kind in ("dow", "month"):
        names = DOW_NAMES if kind == "dow" else MONTH_NAMES
        shift = 0 if kind == "dow" else 1
        ordered = []
        i = 0
        while i < len(vals):                       # consecutive names collapse: MON,TUE,WED -> MON-WED
            j = i
            while j + 1 < len(vals) and vals[j + 1] == vals[j] + 1:
                j += 1
            if j - i >= 2:
                ordered.append(f"{names[vals[i] - shift]}-{names[vals[j] - shift]}")
            else:
                ordered.extend(names[v - shift] for v in vals[i:j + 1])
            i = j + 1
    else:
        ordered = [str(v) for v in vals]
    text = ",".join(ordered) if len(ordered) <= 12 else f"{ordered[0]}..{ordered[-1]} ({len(ordered)})"
    extra = [raw for raw in f.raw.split(",") if any(c in raw for c in "LW#")]
    parts = ([text] if ordered else []) + extra
    return ",".join(parts)


def _fields_json(s) -> list[dict]:
    return [{"name": k, "raw": f.raw, "values": _fmt_values(k, f)} for k, f in s.fields.items()]


def _dst_warnings(dialect: str, runs, skipped: Skipped | None) -> list[Warn]:
    pol = DIALECTS[dialect]["dst"]
    out: list[Warn] = []
    kinds = {r.kind for r in runs}
    if "gap-shifted" in kinds and not pol["gap_documented"]:
        out.append(Warn("W_DST_UNDOCUMENTED", {"dialect": dialect, "what": "gap", "assumed": "shift"}, pol["source"]))
    if "fold-first" in kinds and not pol["fold_documented"]:
        out.append(Warn("W_DST_UNDOCUMENTED", {"dialect": dialect, "what": "fold", "assumed": "first"}, pol["source"]))
    if skipped and skipped.count:
        out.append(Warn("W_DST_SKIPPED", {"dialect": dialect, "count": skipped.count, "first": skipped.first},
                        pol["source"]))
    return out


def _tz_info(dialect: str, tz_arg: str | None) -> dict:
    """스케줄러의 기본 시간대 종류와, --tz 가 없어 UTC 로 '가정'해 계산했는지 여부(JSON 에 그대로 실림)."""
    default = DIALECTS[dialect]["default_tz"]
    # 기본값이 UTC 가 아닌 스케줄러(crontab·k8s·Spring·Quartz)는 --tz 없이는 실제 시간대를 알 수 없다
    return {"tz_default": default, "tz_assumed": tz_arg is None and default != "UTC"}


def _tz_json(out: Out, dialect: str, tz_arg: str | None, zone_name: str, suffix: str = "") -> dict:
    """JSON 의 시간대 필드 3개: tz_default·tz_assumed + 답에 그대로 옮길 한 문장 tz_note.

    에이전트는 긴 경고문을 요약하다가 핵심 낱말(예: 컨트롤러의 '로컬' 시간대)을 빠뜨리기 쉽다.
    그래서 "이 스케줄이 실제로 어느 시간대에서 도는가"에 대한 답을 짧은 한 문장으로 따로 준다.
    """
    info = _tz_info(dialect, tz_arg)
    if info["tz_assumed"]:
        note = out.t("tz_note.assumed", default=out.t("tz." + info["tz_default"]))
    else:
        note = out.t("tz_note.set", zone=zone_name)
    return {"tz_default" + suffix: info["tz_default"], "tz_assumed" + suffix: info["tz_assumed"],
            "tz_note" + suffix: note}


def _zone_label(out: Out, dialect: str, zone, tz_arg: str | None) -> str:
    """텍스트 머리글의 시간대 표기: 가정한 UTC 를 실제 시간대처럼 보이게 쓰지 않는다."""
    info = _tz_info(dialect, tz_arg)
    if not info["tz_assumed"]:
        return zone.name
    return out.t("label.tz_assumed", zone=zone.name, default=out.t("tz." + info["tz_default"]))


def _prepare(expr: str, dialect: str, tz: str | None):
    sched = parse(expr, dialect)
    zone = resolve_zone(tz)
    check_zone_for_dialect(dialect, zone)
    warns = list(sched.warnings) + zone_warnings(dialect, tz is not None)
    return sched, zone, warns


def _start(args, zone) -> int:
    return parse_instant(args.from_, zone) if args.from_ else now_minute()


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_parse(args, out: Out) -> int:
    sched, zone, warns = _prepare(args.expr, args.dialect, args.tz)
    out.payload = {"command": "parse", "dialect": args.dialect, "tz": zone.name,
                   **_tz_json(out, args.dialect, args.tz, zone.name), "normalized": sched.normalized,
                   "fields": _fields_json(sched), "warnings": _warn_json(out, _dedupe(warns))}
    out.line(out.t("parse.ok", dialect=args.dialect) + f"   ({_zone_label(out, args.dialect, zone, args.tz)})")
    out.line(f"  {out.t('label.normalized')}: {sched.normalized}")
    for f in out.payload["fields"]:
        out.line(f"  {out.t('field.' + f['name']):<14} {f['raw']:<12} -> {f['values']}")
    _warn_text(out, _dedupe(warns))
    return EXIT_OK


def cmd_next(args, out: Out) -> int:
    sched, zone, warns = _prepare(args.expr, args.dialect, args.tz)
    start = _start(args, zone)
    show = resolve_zone(args.show_tz) if args.show_tz else None
    if args.count is not None and args.until:
        raise CronError("E_COUNT_UNTIL")
    until = parse_instant(args.until, zone) if args.until else None
    count = None if until is not None else (args.count if args.count is not None else 5)
    if count is not None and not 1 <= count <= MAX_COUNT:
        raise CronError("E_COUNT_RANGE", count=count, max=MAX_COUNT)
    skipped = Skipped()
    runs = next_runs(sched, zone, DIALECTS[args.dialect]["dst"], start, count, until, skipped)
    if not runs and until is None:
        raise CronError("E_NO_RUN", exit_code=EXIT_NO_RUN, days=MAX_DAYS, start=iso_utc(start))
    warns += _dst_warnings(args.dialect, runs, skipped)
    warns = _dedupe(warns)
    out.payload = {"command": "next", "dialect": args.dialect, "tz": zone.name,
                   **_tz_json(out, args.dialect, args.tz, zone.name), "normalized": sched.normalized,
                   "from": iso_utc(start), "runs": _runs_json(zone, runs, show), "warnings": _warn_json(out, warns)}
    out.line(f"{out.t('label.expression')}: {args.expr}   "
             f"({args.dialect}, {_zone_label(out, args.dialect, zone, args.tz)})")
    out.line(f"{out.t('label.normalized')}: {sched.normalized}")
    out.line(f"{out.t('label.from')}: {iso_utc(start)}")
    out.line()
    head = f"{'#':>3}  {out.t('col.local'):<27}{out.t('col.utc'):<22}"
    if show:
        head += f"{out.t('col.shown', tz=show.name):<27}"
    out.line(head + out.t("col.dst"))
    for i, item in enumerate(out.payload["runs"], 1):
        row = f"{i:>3}  {item['local']:<27}{item['utc']:<22}"
        if show:
            row += f"{item['show']:<27}"
        out.line(row + out.t("kind." + item["dst"]))
    if not runs:
        out.line(out.t("next.none"))
    _warn_text(out, warns)
    return EXIT_OK


def _describe_dst_row(out: Out, row: dict, pid: str) -> str:
    res = row["results"][pid]
    if res["skipped"]:
        return out.t("dst.skipped")
    runs = res["runs"]
    if len(runs) == 2:
        return out.t("dst.both", a=runs[0]["local"], b=runs[1]["local"])
    kind = runs[0]["kind"]
    return out.t("dst." + kind, local=runs[0]["local"])


def cmd_explain(args, out: Out) -> int:
    sched, zone, warns = _prepare(args.expr, args.dialect, args.tz)
    d = DIALECTS[args.dialect]
    dow = sched.fields["dow"]
    if d["dow_base"] == 1 and any(c.isdigit() for c in dow.raw):
        warns.append(Warn("W_DOW_BASE", {"dialect": args.dialect}, d["sources"]["syntax"]))
    if zone.name == "UTC" and args.dialect in ("github", "eventbridge"):
        warns.append(Warn("W_TZ_UTC_FIXED", {"dialect": args.dialect}, d["sources"]["tz"]))
    start = _start(args, zone)
    days = args.days
    counts = None
    try:
        lo, hi = window(start, days)
        counts = len(run_instants(sched, zone, d["dst"], lo, hi))
    except CronError as e:
        if e.code != "E_TOO_MANY_RUNS":
            raise
    out.payload = {"command": "explain", "dialect": args.dialect, "tz": zone.name,
                   **_tz_json(out, args.dialect, args.tz, zone.name), "normalized": sched.normalized,
                   "fields": _fields_json(sched), "counts": {"a": counts, "days": days, "from": iso_utc(start)}}
    out.line(f"{out.t('label.expression')}: {args.expr}   "
             f"({args.dialect}, {_zone_label(out, args.dialect, zone, args.tz)})")
    out.line(f"{out.t('label.normalized')}: {sched.normalized}")
    out.line(f"{out.t('label.combine')}: {out.t('combine.' + d['combine'])}")
    for f in out.payload["fields"]:
        out.line(f"  {out.t('field.' + f['name']):<14} {f['raw']:<12} -> {f['values']}")
    if counts is not None:
        out.line(out.t("explain.count", n=counts, days=days, start=iso_utc(start)))
    if args.dst:
        year = args.year if args.year else int(iso_utc(start)[:4])
        policies = {pid: DIALECTS[pid]["dst"] for pid in DST_TABLE_IDS}
        rows = dst_rows(sched, zone, year, policies)
        out.payload["dst"] = {"year": year, "tz": zone.name, "rows": rows}
        out.line()
        out.line(out.t("dst.title", year=year, tz=zone.name))
        if not rows:
            out.line("  " + out.t("dst.none"))
        for row in rows:
            out.line("  " + out.t("dst.row." + row["type"], date=row["date"], wall=row["wall"]))
            for pid in DST_TABLE_IDS:
                pol = DIALECTS[pid]["dst"]
                doc = []
                if row["type"] == "gap" and not pol["gap_documented"]:
                    doc.append("(" + out.t("dst.undocumented") + ")")
                if row["type"] == "fold" and not pol["fold_documented"]:
                    doc.append("(" + out.t("dst.undocumented") + ")")
                out.line(f"    {pid:<22} {_describe_dst_row(out, row, pid)} {' '.join(doc)}".rstrip())
            if row["more"]:
                out.line("    " + out.t("dst.more", n=row["more"]))
        out.line()
        for pid in DST_TABLE_IDS:
            out.line(f"  {pid}: {DIALECTS[pid]['dst']['source']}")
    warns = _dedupe(warns)
    out.payload["warnings"] = _warn_json(out, warns)
    _warn_text(out, warns)
    return EXIT_OK


def _equiv_lines(out: Out, res, days: int, start: int) -> None:
    if res.equivalent:
        out.line(out.t("diff.same", a=res.count_a, days=days, start=iso_utc(start)))
    else:
        out.line(out.t("diff.differ", a=res.count_a, b=res.count_b, instant=iso_utc(res.first_mismatch),
                       side=res.only_in.upper()))


def _diff_payload(res) -> dict:
    out = {"equivalent": res.equivalent, "counts": {"a": res.count_a, "b": res.count_b}}
    if not res.equivalent:
        out["first_mismatch"] = {"instant": iso_utc(res.first_mismatch), "only_in": res.only_in}
    return out


def cmd_diff(args, out: Out) -> int:
    dialect_b = args.dialect2 or args.dialect
    sa, za, warns = _prepare(args.expr, args.dialect, args.tz)
    sb, zb, warns_b = _prepare(args.expr2, dialect_b, args.tz2 or args.tz)
    start = _start(args, za)
    lo, hi = window(start, args.days)
    a = run_instants(sa, za, DIALECTS[args.dialect]["dst"], lo, hi)
    b = run_instants(sb, zb, DIALECTS[dialect_b]["dst"], lo, hi)
    res = diff_sets(a, b)
    warns = warns + warns_b
    if not res.equivalent:
        da, db = DIALECTS[args.dialect], DIALECTS[dialect_b]
        if da["dow_base"] != db["dow_base"] and sa.fields["dow"].raw == sb.fields["dow"].raw \
                and any(c.isdigit() for c in sa.fields["dow"].raw):
            warns.append(Warn("W_DOW_BASE", {"dialect": f"{args.dialect}/{dialect_b}"}, da["sources"]["syntax"]))
        if da["combine"] != db["combine"]:
            warns.append(Warn("W_DAYS_DIFFER", {"a": f"{args.dialect}: {out.t('combine.' + da['combine'])}",
                                                "b": f"{dialect_b}: {out.t('combine.' + db['combine'])}"},
                              da["sources"]["days"]))
    warns = _dedupe(warns)
    tz_b = args.tz2 or args.tz
    out.payload = {"command": "diff", "dialect": args.dialect, "dialect2": dialect_b, "tz": za.name, "tz2": zb.name,
                   **_tz_json(out, args.dialect, args.tz, za.name),
                   **_tz_json(out, dialect_b, tz_b, zb.name, suffix="2"),
                   "normalized": sa.normalized, "normalized2": sb.normalized,
                   "window": {"from": iso_utc(lo), "to": iso_utc(hi), "days": args.days},
                   **_diff_payload(res), "warnings": _warn_json(out, warns)}
    out.line(f"A: {args.expr}   ({args.dialect}, {_zone_label(out, args.dialect, za, args.tz)})")
    out.line(f"B: {args.expr2}   ({dialect_b}, {_zone_label(out, dialect_b, zb, tz_b)})")
    _equiv_lines(out, res, args.days, lo)
    _warn_text(out, warns)
    return EXIT_OK if res.equivalent else EXIT_FAIL


def cmd_convert(args, out: Out) -> int:
    src, zone, warns = _prepare(args.expr, args.from_dialect, args.tz)
    check_zone_for_dialect(args.to, zone)
    start = _start(args, zone)
    lo, hi = window(start, args.days)
    conv = convert_expression(src, args.to)
    reasons = [{"code": code, "message": out.t("conv." + code, **p)} for code, p in conv.reasons]
    out.payload = {"command": "convert", "dialect": args.to, "from_dialect": args.from_dialect, "tz": zone.name,
                   **_tz_json(out, args.from_dialect, args.tz, zone.name),
                   "normalized": src.normalized, "converted": conv.converted,
                   "window": {"from": iso_utc(lo), "to": iso_utc(hi), "days": args.days}}
    out.line(f"{args.from_dialect}: {args.expr}")
    code = EXIT_OK
    if conv.converted is not None or conv.split:
        a = run_instants(src, zone, DIALECTS[args.from_dialect]["dst"], lo, hi)
    if conv.converted is not None:
        tgt = parse(conv.converted, args.to)
        warns += tgt.warnings
        b = run_instants(tgt, zone, DIALECTS[args.to]["dst"], lo, hi)
        res = diff_sets(a, b)
        out.payload.update(_diff_payload(res))
        if args.to.startswith("eventbridge"):
            out.payload["wrapped"] = f"cron({conv.converted})"
        out.line(f"{args.to}: {conv.converted}")
        _equiv_lines(out, res, args.days, lo)
        if not res.equivalent:
            code = EXIT_FAIL
    else:
        out.payload["split"] = list(conv.split)
        out.payload["reasons"] = reasons
        if conv.split:
            union: set[int] = set()
            for text in conv.split:
                part = parse(text, args.to)
                warns += part.warnings
                union |= run_instants(part, zone, DIALECTS[args.to]["dst"], lo, hi)
            res = diff_sets(a, union)
            out.payload["split_equivalent"] = res.equivalent
            out.payload["counts"] = {"a": res.count_a, "b": res.count_b}
            if not res.equivalent:
                out.payload["first_mismatch"] = {"instant": iso_utc(res.first_mismatch), "only_in": res.only_in}
        out.line(out.t("conv.cannot", target=args.to, reasons="; ".join(r["message"] for r in reasons)))
        for text in conv.split:
            out.line(f"  {args.to}: {text}")
        if conv.split:
            out.line("  " + out.t("conv.split_same" if out.payload["split_equivalent"] else "conv.split_differ"))
        code = EXIT_FAIL
    warns = _dedupe(warns)
    out.payload["warnings"] = _warn_json(out, warns)
    _warn_text(out, warns)
    return code


def _dow_label(d: dict) -> str:
    lo = d["dow_base"]
    if d["dow_max"] == 7 and lo == 0:
        return "0-7 (0, 7 = SUN)"
    return f"{lo}-{d['dow_max']} ({lo} = SUN)"


def cmd_dialects(args, out: Out) -> int:
    ids = [args.dialect] if args.dialect else list(DIALECT_IDS)
    data = []
    for did in ids:
        d = DIALECTS[did]
        data.append({
            "id": did, "fields": list(d["layout"]), "min_fields": d["min_fields"], "weekdays": _dow_label(d),
            "combine": d["combine"], "specials": sorted(d["specials"]), "aliases": d["aliases"],
            "default_tz": d["default_tz"], "tz_settable": d["tz_settable"], "range_wrap": d["range_wrap"],
            "dst": {k: d["dst"][k] for k in ("gap", "fold", "gap_documented", "fold_documented")},
            "sources": d["sources"],
        })
    out.payload = {"command": "dialects", "dialects": data}
    for item in data:
        d = DIALECTS[item["id"]]
        out.line(item["id"])
        out.line(f"  {out.t('dl.fields')}: " + " ".join(out.t("field." + f) for f in item["fields"]))
        out.line(f"  {out.t('dl.weekdays')}: {item['weekdays']}")
        out.line(f"  {out.t('dl.combine')}: {out.t('combine.' + item['combine'])}")
        out.line(f"  {out.t('dl.specials')}: {' '.join(item['specials']) or '-'}")
        out.line(f"  {out.t('dl.aliases')}: {out.t('yes') if item['aliases'] else out.t('no')}")
        out.line(f"  {out.t('dl.default_tz')}: {out.t('tz.' + item['default_tz'])}"
                 f"{'' if item['tz_settable'] else ' (' + out.t('dl.not_settable') + ')'}")
        out.line(f"  {out.t('dl.range_wrap')}: {out.t('yes') if item['range_wrap'] else out.t('no')}")
        gap = out.t("gap." + d["dst"]["gap"]) + ("" if d["dst"]["gap_documented"] else f" ({out.t('dst.undocumented')})")
        fold = out.t("fold." + d["dst"]["fold"]) + ("" if d["dst"]["fold_documented"]
                                                      else f" ({out.t('dst.undocumented')})")
        out.line(f"  {out.t('dl.dst')}: {out.t('dl.gap')} = {gap}; {out.t('dl.fold')} = {fold}")
        out.line(f"  {out.t('label.source')}: {d['sources']['syntax']}")
    return EXIT_OK


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    def __init__(self, *a, lang: str = "en", **kw):
        self._lang = lang
        super().__init__(*a, **kw)

    def error(self, message):                                     # usage errors exit 2 like our validation errors
        self.print_usage(sys.stderr)
        sys.stderr.write(f"E_USAGE: {message}\n")
        raise SystemExit(EXIT_USAGE)

    def format_help(self):
        text = super().format_help()
        for old in ("usage:", "options:", "optional arguments:", "positional arguments:"):
            key = {"usage:": "usage", "options:": "options", "optional arguments:": "options",
                   "positional arguments:": "positional"}[old]
            text = text.replace(old, _i18n.t(self._lang, "help.head." + key) + ":", 1)
        return text


def _common(p: argparse.ArgumentParser, lang: str, top: bool) -> None:
    sup = None if top else argparse.SUPPRESS
    t = lambda key: _i18n.t(lang, key)  # noqa: E731
    p.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help=t("help.help"))
    p.add_argument("--json", action="store_true", default=False if top else sup, help=t("help.json"))
    p.add_argument("--out", metavar="FILE", default=None if top else sup, help=t("help.out"))
    p.add_argument("--lang", choices=("en", "ko"), default=None if top else sup, help=t("help.lang"))


def build_parser(lang: str) -> argparse.ArgumentParser:
    t = lambda key, **kw: _i18n.t(lang, key, **kw)  # noqa: E731
    ids = " | ".join(DIALECT_IDS)
    ap = _Parser(prog=PROG, lang=lang, description=t("help.description"), epilog=t("help.epilog"), add_help=False,
                 formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(ap, lang, True)
    sub = ap.add_subparsers(dest="command", metavar="<command>", parser_class=_Parser)

    def add(name: str, **kw):
        p = sub.add_parser(name, help=t("help.cmd." + name), description=t("help.cmd." + name), lang=lang, add_help=False, **kw)
        _common(p, lang, False)
        return p

    def expr_args(p, second: bool = False):
        p.add_argument("expr", help=t("help.expr"))
        p.add_argument("--tz", default=None, help=t("help.tz"))
        p.add_argument("--from", dest="from_", metavar="ISO", default=None, help=t("help.from"))

    p = add("parse")
    p.add_argument("expr", help=t("help.expr"))
    p.add_argument("--dialect", required=True, choices=DIALECT_IDS, metavar="D", help=t("help.dialect", ids=ids))
    p.add_argument("--tz", default=None, help=t("help.tz"))
    p.set_defaults(func=cmd_parse)

    p = add("next")
    expr_args(p)
    p.add_argument("--dialect", required=True, choices=DIALECT_IDS, metavar="D", help=t("help.dialect", ids=ids))
    p.add_argument("--count", type=int, default=None, help=t("help.count", max=MAX_COUNT))
    p.add_argument("--until", metavar="ISO", default=None, help=t("help.until"))
    p.add_argument("--show-tz", default=None, help=t("help.show_tz"))
    p.set_defaults(func=cmd_next)

    p = add("explain")
    expr_args(p)
    p.add_argument("--dialect", required=True, choices=DIALECT_IDS, metavar="D", help=t("help.dialect", ids=ids))
    p.add_argument("--dst", action="store_true", help=t("help.dst"))
    p.add_argument("--year", type=int, default=None, help=t("help.year"))
    p.add_argument("--days", type=int, default=365, help=t("help.days", max=MAX_DAYS))
    p.set_defaults(func=cmd_explain)

    p = add("convert")
    expr_args(p)
    p.add_argument("--from-dialect", required=True, choices=DIALECT_IDS, metavar="A", help=t("help.from_dialect"))
    p.add_argument("--to", required=True, choices=DIALECT_IDS, metavar="B", help=t("help.to"))
    p.add_argument("--days", type=int, default=365, help=t("help.days", max=MAX_DAYS))
    p.set_defaults(func=cmd_convert)

    p = add("diff")
    expr_args(p)
    p.add_argument("expr2", help=t("help.expr2"))
    p.add_argument("--dialect", required=True, choices=DIALECT_IDS, metavar="A", help=t("help.dialect_a"))
    p.add_argument("--dialect2", choices=DIALECT_IDS, metavar="B", default=None, help=t("help.dialect_b"))
    p.add_argument("--tz2", default=None, help=t("help.tz2"))
    p.add_argument("--days", type=int, default=365, help=t("help.days", max=MAX_DAYS))
    p.set_defaults(func=cmd_diff)

    p = add("dialects")
    p.add_argument("--dialect", choices=DIALECT_IDS, metavar="D", default=None, help=t("help.dialect_opt"))
    p.set_defaults(func=cmd_dialects)
    return ap


def _lang_from_argv(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


def _emit_error(err: CronError, lang: str, as_json: bool, out_path: str | None) -> int:
    msg = _i18n.t(lang, "err." + err.msg_key, **err.params)
    if as_json:
        payload = {"error": {"code": err.code, "message": msg, "source": err.source}}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        sys.stderr.write(f"{err.code}: {msg}\n")
        if err.source:
            sys.stderr.write(f"  {_i18n.t(lang, 'label.source')}: {err.source}\n")
    return err.exit_code


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = _i18n.pick_lang(_lang_from_argv(argv), os.environ)
    parser = build_parser(lang)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if args.lang:
        lang = args.lang
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    out = Out(lang)
    try:
        code = args.func(args, out)
    except CronError as err:
        return _emit_error(err, lang, args.json, args.out)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(out.payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        except OSError as exc:
            return _emit_error(CronError("E_OUT", path=args.out, reason=exc.strerror or str(exc)), lang, args.json,
                               args.out)
    if args.json:
        print(json.dumps(out.payload, ensure_ascii=False, indent=2))
    else:
        print("\n".join(out.lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
