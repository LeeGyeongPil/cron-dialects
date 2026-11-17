# DST gap and fold policies

Contents: [Terms](#terms) - [Policy table](#policy-table) - [Why results differ from Python libraries](#why-results-differ-from-python-libraries)

Checked 2026-11-17. `python3 scripts/cronx.py explain "30 2 * * *" --dialect github --tz America/New_York --dst --year 2027` prints this table for a concrete wall-clock time.

## Terms

- Gap: a wall-clock time that does not exist because clocks jump forward (New York 2027-03-14, 02:00 becomes 03:00, so 02:30 never happens).
- Fold: a wall-clock time that happens twice because clocks go back (New York 2027-11-07, 02:00 becomes 01:00, so 01:30 happens twice).

## Policy table

| id | gap | fold | documented? | source |
|---|---|---|---|---|
| `unix` (Debian cron) | runs right after the change (shifted to 03:00) | runs once, first pass | yes, for fixed-time jobs; jobs with a wildcard time field follow the new clock | https://manpages.debian.org/bookworm/cron/cron.8.en.html |
| `cronie` | never runs that day | runs twice | yes | https://man7.org/linux/man-pages/man5/crontab.5.html |
| `k8s` | does not run | computed as first pass | gap yes, fold no | https://pkg.go.dev/github.com/robfig/cron/v3 |
| `github` | moved to the next valid time (03:00) | computed as first pass | gap yes, fold no | https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows |
| `spring` | computed as shifted to the transition instant | computed as first pass | no | https://docs.spring.io/spring-framework/reference/integration/scheduling.html |
| `quartz` | computed as shifted to the transition instant | computed as first pass | no (the tutorial only warns that runs may be skipped or repeated) | https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html |
| `eventbridge` | not applicable, UTC only | not applicable | yes | https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html |
| `eventbridge-scheduler` | skipped that day | runs once, second pass | yes | https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html |

When a behaviour is not documented the script still has to pick one, marks the run kind (`gap-shifted`, `fold-first`) and emits `W_DST_UNDOCUMENTED`. Say so in the answer and suggest checking on the real scheduler or avoiding the 01:00-03:00 local window.

## Why results differ from Python libraries

croniter 7.0.0 returns 01:30 twice on the fold day while cronsim 2.8 returns it once (checked 2026-11-17 with `30 1 * * *`, America/New_York, 2027-11-07). Both put the gap run at 03:00. Neither follows any one scheduler's documented policy, so use the per-scheduler result from the script.
