# Report job migration

Old (Quartz): `0 0 12 ? * 2-6`  - weekdays at noon

New (crontab): `0 12 * * 2-6`   - copied the day numbers as they were
