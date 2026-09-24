#!/usr/bin/env python3
"""Exit 0 if the new schedule is worth committing, 1 if not.

A daily run always shifts the date window, so compare only what matters: the timetable for the dates
both files cover, which sources worked, and whether the old file is running short of future dates.
"""
import datetime as dt, json, sys

old_path, new_path = sys.argv[1], sys.argv[2]
new = json.load(open(new_path))
try:
    old = json.load(open(old_path))
except (OSError, ValueError):
    print('no previous schedule: commit'); sys.exit(0)

day = lambda doc, d: doc['sets'][doc['days'][d]]
shared = sorted(set(old['days']) & set(new['days']))
changed = [d for d in shared if json.dumps(day(old, d), sort_keys=True) != json.dumps(day(new, d), sort_keys=True)]
sources = lambda doc: {k: v.get('ok') for k, v in doc.get('sources', {}).items()}
left = (dt.date.fromisoformat(max(old['days'])) - dt.date.fromisoformat(min(new['days']))).days
lost = [k for k, ok in sources(old).items() if ok and not sources(new).get(k)]
if lost:                                               # a feed was down today: keep the good file rather than blank it
    print(f'::warning::{", ".join(lost)} timetable unavailable today; keeping the previous file'); sys.exit(1)
if changed:
    print(f'timetable changed on {len(changed)} dates, first {changed[0]}: commit'); sys.exit(0)
if sources(old) != sources(new):
    print(f'sources changed {sources(old)} -> {sources(new)}: commit'); sys.exit(0)
if left < 21:
    print(f'old file covers only {left} more days: commit'); sys.exit(0)
print(f'no timetable change; old file still covers {left} days: skip'); sys.exit(1)
