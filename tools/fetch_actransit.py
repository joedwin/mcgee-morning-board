#!/usr/bin/env python3
"""Download AC Transit's GTFS timetable for tools/build_schedule.py.

With ACT_TOKEN set, uses AC Transit's API (the active schedule). Without it, falls back to the
keyless open-data portal. Writes the result to act.zip or act_gtfs/, and records what it used in
act_path.txt / act_source.txt. Never fails the job: no feed just means the page keeps its built-in bus times.
"""
import json, os, sys, time, urllib.request, zipfile

API = 'https://api.actransit.org/transit/gtfs/download?token='
PORTAL = 'https://opendata.actransit.org/api/3/action/package_show?id=general-transit-feed-specification-gtfs'
NEEDED = ['stops.txt', 'routes.txt', 'trips.txt', 'stop_times.txt', 'calendar.txt', 'calendar_dates.txt']


def get(url, dest=None, tries=3):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'mcgee-morning-board timetable job'})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if dest:
                with open(dest, 'wb') as f:
                    f.write(data)
            return data
        except Exception as e:                        # noqa: BLE001
            print(f'  {url.split("?")[0]}: {e} (try {n + 1})', file=sys.stderr)
            time.sleep(3 * (n + 1))
    return None


def done(path, source):
    open('act_path.txt', 'w').write(path)
    open('act_source.txt', 'w').write(source)
    print(f'AC Transit timetable: {source} -> {path or "none"}')
    sys.exit(0)


token = os.environ.get('ACT_TOKEN', '').strip()
if token:
    if get(API + token, 'act.zip') and zipfile.is_zipfile('act.zip'):
        done('act.zip', 'api')
    print('AC Transit API download failed or returned something other than a zip; trying the open-data portal', file=sys.stderr)
else:
    print('No ACT_TOKEN secret yet; trying the open-data portal', file=sys.stderr)

meta = get(PORTAL)
if not meta:
    done('', 'none')
try:
    resources = json.loads(meta)['result']['resources']
except Exception as e:                                # noqa: BLE001
    print(f'Portal reply not understood: {e}', file=sys.stderr)
    done('', 'none')
stamp = lambda r: r.get('last_modified') or r.get('metadata_modified') or r.get('created') or ''
for r in resources:
    print(f"  portal: {r.get('name')!r} {r.get('format')} {stamp(r)[:10]} {r.get('url', '')[-60:]}", file=sys.stderr)

files = {}
for r in sorted(resources, key=stamp):                # newest wins
    base = os.path.basename((r.get('url') or '').split('?')[0]).lower()
    name = (r.get('name') or '').strip().lower()
    for want in NEEDED:
        if base == want or name == want or name.endswith(' ' + want) or name.endswith('- ' + want):
            files[want] = r['url']
if all(w in files for w in NEEDED[:5]):
    os.makedirs('act_gtfs', exist_ok=True)
    ok = all(get(url, os.path.join('act_gtfs', want)) is not None for want, url in files.items())
    if ok:
        done('act_gtfs', 'opendata')
zips = [r for r in sorted(resources, key=stamp, reverse=True)
        if (r.get('format') or '').lower() == 'zip' or (r.get('url') or '').lower().split('?')[0].endswith('.zip')]
for r in zips[:1]:
    if get(r['url'], 'act.zip') and zipfile.is_zipfile('act.zip'):
        done('act.zip', 'opendata-zip')
done('', 'none')
