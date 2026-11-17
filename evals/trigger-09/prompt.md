---
name: trigger-09
max_turns: 12
---

We're moving our Spring scheduled jobs to EventBridge Scheduler - rewrite these cron strings and check they still fire at the same times: `0 0 6 * * MON-FRI`, `0 30 22 * * *`.
