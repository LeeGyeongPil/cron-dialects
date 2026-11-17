---
name: cron-dialects
description: Computes real run times for cron schedules per scheduler dialect (crontab, Kubernetes CronJob, GitHub Actions, Spring, Quartz, AWS EventBridge) with a bundled script, including time zones and DST gaps and folds, and proves a conversion between dialects by diffing a year of run instants. Use when the user gives or asks about a cron expression, wants to know when a schedule really fires, converts or migrates a schedule between schedulers, reviews a workflow, CronJob, serverless or Spring schedule, or asks what happens to a job on a daylight saving change. Not for workflow trigger filters, iCalendar RRULE, plain time zone conversion, or crontab environment problems.
license: MIT
compatibility: Python 3.10+ (standard library only). No network access. Needs the OS time zone database; on Windows run with uv run --with tzdata.
---

# Cron dialects: compute, convert and verify schedules

The same cron text means different things per scheduler (day-of-month and day-of-week OR vs AND, weekday numbering, `?` rules, default time zone, DST handling). Counting or converting by hand is where answers go quietly wrong, so run the script and quote its output.

1. Pick the dialect from where the expression lives (see the table below). If unsure, ask which scheduler runs it.
2. Run `python3 scripts/cronx.py <command> ...` (the path is relative to this skill's folder). Always pass a fixed `--from` (for example `--from 2027-01-01T00:00Z`) so results are reproducible, and `--tz` when the user names a time zone. Pass `--lang en` or `--lang ko` to match the language of your answer (otherwise messages follow the OS locale and you would have to translate them, which loses exact wording).
3. Report the run times (local time with offset, UTC, and the `dst` marker such as `gap-shifted` or `fold-second`) or counts from the output exactly as printed; when asked to save a result, save the script's own JSON with `--json --out FILE` instead of retyping it. Keep the warning codes (`W_DOM_DOW_OR`, `W_TZ_CONTROLLER`, `W_DST_UNDOCUMENTED` ...) and the source URL that comes with each, and say when a DST behaviour is marked as not documented instead of stating it as fact.
4. Time zone: look where the scheduler takes its zone from and pass that value as `--tz` (Kubernetes `.spec.timeZone`, GitHub `timezone:`, cronie `CRON_TZ=` line, Spring `zone`, EventBridge Scheduler `ScheduleExpressionTimezone`). The JSON field `tz_note` is the one-sentence answer to "which time zone does this really run in"; copy it into your answer word for word, do not shorten it (text output carries the same facts in its first line). If no zone is set, `"tz_assumed": true`, `tz_default` names the real default and the times are only a UTC stand-in: for `k8s` (`controller-local`) the note says the schedule runs in the kube-controller-manager's local time zone, which is UTC only if the controller runs in UTC. Recommend pinning it with `.spec.timeZone` (stable since v1.27), never with `CRON_TZ=` or `TZ=` inside `.spec.schedule` (Kubernetes rejects that with a validation error).
5. If the script exits with an error, show its error line as is (it names the fix) and retry with the corrected expression. Exit codes: 0 ok or equivalent, 1 not equivalent or not expressible as one expression, 2 usage or validation error, 3 no run in the search horizon, 4 time zone data missing.

| Expression lives in | Dialect id |
|---|---|
| crontab, Debian or Ubuntu cron | `unix` |
| crontab on RHEL or Fedora (cronie, `CRON_TZ`) | `cronie` |
| Kubernetes `CronJob.spec.schedule` | `k8s` |
| GitHub Actions `on.schedule` | `github` |
| Spring `@Scheduled(cron = ...)`, 6 fields | `spring` |
| Quartz `CronTrigger`, 6 or 7 fields | `quartz` |
| EventBridge rule `cron(...)`, serverless `schedule:` | `eventbridge` |
| EventBridge Scheduler (time zone settable) | `eventbridge-scheduler` |

## Commands

- Next runs: `python3 scripts/cronx.py next "0 9 1-7 * 1" --dialect unix --from 2027-01-01T00:00Z --count 5` (add `--tz America/New_York`, `--show-tz Asia/Seoul`, or `--until ISO` instead of `--count`).
- Explain, with the number of runs in the window: `python3 scripts/cronx.py explain "0 9 1-7 * 1" --dialect unix --from 2027-01-01T00:00Z` (JSON key `counts.a`). For DST behaviour per scheduler add `--tz America/New_York --dst --year 2027`.
- Validate: `python3 scripts/cronx.py parse "cron(0 12 * * MON-FRI *)" --dialect eventbridge`.
- Convert and prove: `python3 scripts/cronx.py convert "0 0 12 ? * 2-6" --from-dialect quartz --to eventbridge --from 2027-01-01T00:00Z`. It always diffs a year of run instants and prints `equivalent` or the first mismatch. When one expression cannot express the original it says why and, for the day-of-month OR day-of-week case, gives expressions to use as separate rules.
- Compare two expressions: `python3 scripts/cronx.py diff "0 0 12 ? * 2-6" "0 12 * * 2-6" --dialect quartz --dialect2 unix --from 2027-01-01T00:00Z` (`--tz2` when the zones differ). Equal counts do not mean equal schedules; trust `equivalent` and `first_mismatch`.
- Rule table with sources: `python3 scripts/cronx.py dialects`.
- Add `--json` for machine-readable output and `--out result.json` to also save the JSON; `--lang en|ko` picks the message language.

## Pitfalls the output flags

- `0 9 1-7 * 1` in crontab runs on days 1-7 OR every Monday (124 runs in 2027); Spring needs both (12 runs). Quartz and EventBridge need `?` in one of the two fields.
- A day field starting with `*` such as `*/2` makes crontab AND the two fields instead; Kubernetes (robfig/cron) treats `*/2` as restricted and ORs them (`0 0 */2 * 1`: 27 runs in crontab, 211 in Kubernetes in 2027).
- Quartz and EventBridge number weekdays 1-7 from Sunday; crontab uses 0-7. Copying `2-6` across moves the schedule by a day.
- Without `--tz` the script computes in UTC and warns: GitHub and EventBridge rules run in UTC; a Kubernetes CronJob without `.spec.timeZone` runs in the kube-controller-manager's local time zone (`W_TZ_CONTROLLER`), crontab in the daemon's local zone, Spring and Quartz in the server's zone.
- On DST days a job at a skipped or repeated wall-clock time is moved, skipped or run twice depending on the scheduler. Details and which behaviours are documented: [references/dst-policies.md](references/dst-policies.md).

## When to read the references

- Field layout, weekday numbering, special characters and combination rules per dialect: [references/dialects.md](references/dialects.md).
- Why a conversion is not possible as one expression and what to do instead (`L`, `W`, `#`, seconds, years, AND rules): [references/conversion-limits.md](references/conversion-limits.md).
