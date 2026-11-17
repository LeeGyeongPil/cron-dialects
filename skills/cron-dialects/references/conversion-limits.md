# Conversion limits

Contents: [What convert does](#what-convert-does) - [Cases that need more than one expression](#cases-that-need-more-than-one-expression) - [Cases with no equivalent](#cases-with-no-equivalent) - [Time zone and DST caveats](#time-zone-and-dst-caveats)

## What convert does

`convert` rewrites the fields for the target dialect (weekday numbers, `?`, seconds, year, aliases) and then ALWAYS compares the run instants of the original and the result over the window (default 365 days). `equivalent: true` is a measured fact for that window, not a claim from the rewrite rules. When it reports a mismatch, show the `first_mismatch` instant to the user.

## Cases that need more than one expression

- Unix-style OR to Quartz, EventBridge or Spring: `0 9 1-7 * 1` means "days 1-7 OR Mondays". The target cannot say OR in one expression, so convert returns two (`0 0 9 1-7 * ?` and `0 0 9 ? * 2` for Quartz) and checks that their union equals the original. Create them as separate rules or triggers.
- Spring first-Monday style AND (`0 0 9 1-7 * 1`) to Quartz or EventBridge becomes one expression with `#` (`0 0 9 ? * 2#1`), for the ranges 1-7, 8-14, 15-21, 22-28 and 29-31.

## Cases with no equivalent

- `L`, `W`, `LW`, `#`, `dL` to crontab, Kubernetes or GitHub: five-field cron has no such characters. Keep a daily job and test the date inside the job, or move to a scheduler that has them.
- Seconds other than 0 to a dialect without a seconds field.
- A year restriction to a dialect without a year field.
- Spring AND with both day fields restricted (other than the `#` pattern) to Unix-style or `?` dialects: check one of the conditions inside the job.
- Quartz `L-n` to EventBridge (not documented there).

## Time zone and DST caveats

Both sides are evaluated in the same `--tz`. If the schedulers handle DST days differently (see dst-policies.md), a conversion can be equivalent in UTC and not equivalent in `America/New_York`; the diff reports the first instant where they differ. EventBridge rules always run in UTC, so give a UTC expression or use EventBridge Scheduler with a time zone.
