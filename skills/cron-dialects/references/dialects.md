# Dialect rules

Checked 2026-11-17 against the pages in the last column. `python3 scripts/cronx.py dialects` prints the same table from the data the script uses.

| id | fields | weekdays | day-of-month and day-of-week | specials | default zone | source |
|---|---|---|---|---|---|---|
| `unix` | minute hour dom month dow | 0-7 (0 and 7 = Sun), names | OR; AND if a field starts with `*` | none | daemon local | https://man7.org/linux/man-pages/man5/crontab.5.html |
| `cronie` | same as `unix` | 0-7 | same as `unix` | none | daemon local, `CRON_TZ` in crontab | https://man7.org/linux/man-pages/man5/crontab.5.html |
| `k8s` | 5 fields | 0-6 | OR; AND only if a day field is exactly `*` or `?` (robfig/cron v3: `*/2` counts as restricted) | `?` = `*` | controller local, `.spec.timeZone` since v1.27 | https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/ |
| `github` | 5 fields | 0-6 or names | POSIX (assumed OR, not documented) | none | UTC, `timezone:` key since 2026-03 | https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows |
| `spring` | second minute hour dom month dow | 0-7, MON-SUN | AND | `? L L-n W LW nL #` | server, `zone` attribute | https://docs.spring.io/spring-framework/reference/integration/scheduling.html |
| `quartz` | second minute hour dom month dow [year] | 1-7 (1 = Sun) | exactly one `?` | `? L L-n W LW nL #` | trigger time zone | https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html |
| `eventbridge` | minute hour dom month dow year (inside `cron(...)`) | 1-7 (1 = Sun) | exactly one `?` | `? L W nL #` (one `#` per rule) | UTC only | https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html |
| `eventbridge-scheduler` | same as `eventbridge` | 1-7 (1 = Sun) | exactly one `?` | same | any IANA zone | https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html |

## Aliases

`@yearly @annually @monthly @weekly @daily @midnight @hourly` work in `unix`, `cronie`, `k8s` and `spring`. GitHub, Quartz and EventBridge reject them. `@reboot` and `@every` are not time-based schedules and are rejected.

## Reversed ranges

Quartz and EventBridge accept a range that wraps, such as hours `22-2`. Unix-style dialects, Spring and GitHub reject it; write `22-23,0-2`.

## Combination rule details

- Kubernetes uses robfig/cron v3.0.1: a day field counts as unrestricted only when it is `*` or `?` without a step greater than 1, so `0 0 */2 * 1` is ORed there (211 runs in 2027) while crontab ANDs it (27). Source: https://raw.githubusercontent.com/robfig/cron/v3.0.1/spec.go and parser.go (fetched 2026-11-17).
- Vixie and cronie decide whether a day field is restricted by its first character: `*/2` starts with `*`, so it counts as unrestricted and the two day fields are ANDed (`0 0 */2 * 1` runs on odd days that are also Mondays, 27 times in 2027). `1-31/2` does not start with `*`, so it is ORed (211 times). Python libraries disagree on this case, which is why the script fixes the rule per dialect.
- Spring ANDs the fields, so `0 0 9 1-7 * 1` is the first Monday.
- GitHub documents POSIX cron syntax but not the combination rule; the script computes OR and warns `W_COMBINE_ASSUMED`.

## Special characters

- `L` last day of the month (day-of-month) or Saturday (bare `L` in the weekday field of Quartz and EventBridge).
- `L-n` n days before the last day; `LW` last weekday; `nW` the weekday nearest day n without leaving the month (`1W` on a Saturday 1st is Monday the 3rd).
- `dL` last weekday d of the month; `d#n` the n-th weekday d (`4#5` skips months without a fifth Wednesday in Quartz numbering).

## Minimum interval

GitHub does not run schedules more often than every 5 minutes. EventBridge has no seconds field, so the finest schedule is one minute.
