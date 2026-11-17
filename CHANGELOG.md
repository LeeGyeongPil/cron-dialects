# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-17

### Fixed
- Kubernetes (`k8s`) now follows robfig/cron v3: a day field counts as unrestricted only when it is `*` or `?` without a step above 1, so `0 0 */2 * 1` is ORed (211 runs in 2027) while crontab ANDs it (27). New warning `W_ROBFIG_STEP`.
- `next --until` size errors no longer suggest the missing `--days`; unsupported-character errors list only the characters allowed in the named field.
- `--help` is translated too (no English `-h, --help` line under `--lang ko`).
- Without `--tz` the output no longer looks like the schedule runs in UTC when the scheduler's default is something else: JSON adds `tz_default` and `tz_assumed` (`tz_default2`, `tz_assumed2` for `diff`), and the text header reads `UTC assumed; the scheduler's real default is ...`.
- `W_TZ_CONTROLLER` now uses the Kubernetes wording (the kube-controller-manager's local time zone) and names the fix: set `.spec.timeZone`, not `CRON_TZ=` / `TZ=` in `.spec.schedule`. `W_TZ_LOCAL` and `W_TZ_SERVER` say to pass the real zone with `--tz`.
- JSON adds `tz_note` (`tz_note2` for `diff`), one sentence on which time zone the schedule really runs in, and SKILL.md asks the agent to quote it word for word and to pass `--lang` matching its answer language, so the answer no longer depends on translating messages printed in the OS locale.

### Added
- Skill `cron-dialects` with the bundled script `cronx.py` (standard library only, Python 3.10+).
- Eight scheduler ids: `unix`, `cronie`, `k8s`, `github`, `spring`, `quartz`, `eventbridge`, `eventbridge-scheduler`, each with its field layout, weekday numbering, day-of-month and day-of-week rule, special characters, default time zone, DST policy and documentation URL.
- Subcommands `parse`, `next`, `explain`, `convert`, `diff` and `dialects`, text and `--json` output, `--out` to save the JSON.
- DST gap and fold handling per scheduler, with `W_DST_UNDOCUMENTED` where the scheduler documentation is silent.
- `convert` that always verifies the result by comparing run instants, reports the first mismatch, and splits the day-of-month OR day-of-week case.
- Messages in English and Korean (`--lang`, `CRON_DIALECTS_LANG`, locale variables).
- Evaluation set (`evals/`), unit tests and Claude Code plugin manifests.
