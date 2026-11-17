---
type: regex
pattern: '"local": "2027-11-07T01:30:00-05:00",\s*"utc": "2027-11-07T06:30:00Z",\s*"dst": "fold-second"'
target: {source: file, path: fold.json}
---
