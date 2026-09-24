#!/usr/bin/env python3
"""Build data/schedule.json for the McGee Morning Board from the official timetable feeds.

Reads AC Transit's and BART's GTFS files (zip or folder) and writes, for each of the next few weeks,
the J / FS / G trips between your stops and the Salesforce Transit Center, and the useful BART trips
between North Berkeley and Montgomery St (direct, or with one cross-platform change).

    python3 tools/build_schedule.py --actransit act.zip --bart bart.zip --out data/schedule.json

Either feed may be missing; the page then keeps its built-in times for that part.
"""
import argparse, bisect, csv, datetime as dt, hashlib, io, json, math, os, re, sys, zipfile
from collections import defaultdict

try:
    from zoneinfo import ZoneInfo
except ImportError:                                   # pragma: no cover
    ZoneInfo = None

TZ = 'America/Los_Angeles'
TC = (37.7893, -122.3972)                             # Salesforce Transit Center
# Each leg: where you get on and where you get off. A public stop code (the number on the sign)
# with a position to fall back on if the feed files the corner under another code; 'TC' = any Transit Center bay.
LEGS = {
    'am': {
        'J':  {'board': ('55998', (37.87007, -122.28208)), 'exit': ('TC', TC)},
        'FS': {'board': ('55722', (37.87044, -122.28210)), 'exit': ('TC', TC)},
        'G':  {'board': ('59600', (37.87542, -122.29433)), 'exit': ('TC', TC)},
    },
    'pm': {
        'J':  {'board': ('TC', TC), 'exit': ('55998', (37.87007, -122.28208))},
        'FS': {'board': ('TC', TC), 'exit': ('56667', (37.87037, -122.28135))},
        'G':  {'board': ('TC', TC), 'exit': ('55165', (37.87560, -122.29420))},
    },
}
WINDOW = {'am': (4 * 60 + 30, 11 * 60), 'pm': (14 * 60 + 30, 21 * 60 + 30)}   # departure minutes kept
BART_ENDS = {'am': ('NBRK', 'MONT'), 'pm': ('MONT', 'NBRK')}
BART_XFER = ['MCAR', '19TH', '12TH']
BART_NAMES = {'NBRK': r'north berkeley', 'MONT': r'montgomery', 'MCAR': r'macarthur', '19TH': r'19th', '12TH': r'12th'}
PALETTE = {'Red': (237, 28, 36), 'Orange': (250, 166, 26), 'Yellow': (255, 232, 0), 'Green': (77, 184, 72),
           'Blue': (0, 174, 239), 'Grey': (213, 207, 163)}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- reading GTFS
class Feed:
    """A GTFS feed from a zip file or a folder; files may sit in a subfolder of the zip."""
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if os.path.isfile(path) else None
        if self.zip:
            self.members = {os.path.basename(n).lower(): n for n in self.zip.namelist() if not n.endswith('/')}
        else:
            self.members = {n.lower(): os.path.join(path, n) for n in os.listdir(path)}

    def has(self, name):
        return name in self.members

    def rows(self, name):
        if not self.has(name):
            return
        raw = self.zip.open(self.members[name]) if self.zip else open(self.members[name], 'rb')
        with raw:
            text = io.TextIOWrapper(raw, encoding='utf-8-sig', newline='')
            reader = csv.reader(text)
            head = [h.strip() for h in next(reader, [])]
            for rec in reader:
                if rec:
                    yield {h: (rec[i].strip() if i < len(rec) else '') for i, h in enumerate(head)}


def secs(t):
    t = (t or '').strip()
    if not t:
        return None
    p = t.split(':')
    return int(p[0]) * 3600 + int(p[1]) * 60 + (int(float(p[2])) if len(p) > 2 else 0)


def meters(a, b):
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[1] - b[1]) * 111320 * math.cos(lat), (a[0] - b[0]) * 110540)


class Calendar:
    DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    def __init__(self, feed):
        self.cal = list(feed.rows('calendar.txt'))
        self.ex = defaultdict(list)
        for r in feed.rows('calendar_dates.txt'):
            self.ex[r['date']].append(r)
        bounds = [r['start_date'] for r in self.cal] + list(self.ex)
        ends = [r['end_date'] for r in self.cal] + list(self.ex)
        self.first, self.last = (min(bounds), max(ends)) if bounds else (None, None)

    def covers(self, ymd):
        return self.first is not None and self.first <= ymd <= self.last

    def active(self, date):
        ymd, wd = date.strftime('%Y%m%d'), self.DAYS[date.weekday()]
        on = {r['service_id'] for r in self.cal if r['start_date'] <= ymd <= r['end_date'] and r.get(wd) == '1'}
        for r in self.ex.get(ymd, []):
            if r['exception_type'] == '1':
                on.add(r['service_id'])
            elif r['exception_type'] == '2':
                on.discard(r['service_id'])
        return on


def trip_sequences(feed, keep):
    """stop_times for the trips in `keep`, ordered, with blank times filled in by interpolation."""
    st = defaultdict(list)
    for r in feed.rows('stop_times.txt'):
        if r['trip_id'] in keep:
            a, d = secs(r.get('arrival_time')), secs(r.get('departure_time'))
            tp = r.get('timepoint', '')
            st[r['trip_id']].append([int(float(r['stop_sequence'])), r['stop_id'], a, d, 0 if tp == '0' else 1])
    for seq in st.values():
        seq.sort(key=lambda x: x[0])
        known = [i for i, x in enumerate(seq) if x[2] is not None or x[3] is not None]
        for i, x in enumerate(seq):
            if x[2] is None and x[3] is not None: x[2] = x[3]
            if x[3] is None and x[2] is not None: x[3] = x[2]
        for k in range(len(known) - 1):                 # stops with no time: spread evenly, marked approximate
            i, j = known[k], known[k + 1]
            for n in range(i + 1, j):
                t = seq[i][3] + (seq[j][2] - seq[i][3]) * (n - i) / (j - i)
                seq[n][2] = seq[n][3] = int(t)
                seq[n][4] = 0
    return st


# ---------------------------------------------------------------- AC Transit
def build_bus(feed, days):
    stops = {r['stop_id']: r for r in feed.rows('stops.txt')}
    code = lambda sid: (stops.get(sid, {}).get('stop_code') or '').strip() or ('id:' + sid)
    pos = lambda sid: (float(stops[sid]['stop_lat']), float(stops[sid]['stop_lon']))
    is_tc = lambda sid: bool(re.search(r'salesforce transit|transbay', stops[sid].get('stop_name', ''), re.I)) or meters(pos(sid), TC) < 250

    routes = {r['route_id']: (r.get('route_short_name') or r['route_id']).strip().upper() for r in feed.rows('routes.txt')}
    trips = {r['trip_id']: (routes.get(r['route_id']), r['service_id']) for r in feed.rows('trips.txt')
             if routes.get(r['route_id']) in ('J', 'FS', 'G')}
    seqs = trip_sequences(feed, trips)
    log(f'AC Transit: {len(trips)} J/FS/G trips, {len(seqs)} with stop times')

    def find(seq, target, after):
        want, where = target
        rng = range(after + 1, len(seq))
        if want == 'TC':
            return next((i for i in rng if is_tc(seq[i][1])), None)
        hit = next((i for i in rng if code(seq[i][1]) == want), None)
        if hit is not None:
            return hit
        near = [(meters(pos(seq[i][1]), where), i) for i in rng]
        near = [x for x in near if x[0] < 200]
        return min(near)[1] if near else None

    legs = defaultdict(list)                            # (dir, service_id) -> trips
    used, fallbacks = set(), defaultdict(int)
    for tid, (line, service) in trips.items():
        seq = seqs.get(tid)
        if not seq:
            continue
        for d in ('am', 'pm'):
            cfg = LEGS[d][line]
            b = find(seq, cfg['board'], -1)
            e = find(seq, cfg['exit'], b) if b is not None else None
            if b is None or e is None:
                continue
            dep, arr = seq[b][3] // 60, seq[e][2] // 60
            if not (WINDOW[d][0] <= dep < WINDOW[d][1]):
                continue
            for end, idx in (('board', b), ('exit', e)):
                if cfg[end][0] not in ('TC', code(seq[idx][1])):
                    fallbacks[f'{line} {d} {end}: {cfg[end][0]} -> {code(seq[idx][1])} {stops[seq[idx][1]].get("stop_name")}'] += 1
            bay = re.search(r'bay\s*(\d+)', stops[seq[b][1]].get('stop_name', ''), re.I) if d == 'pm' else None
            legs[(d, service)].append({
                'line': line, 'dep': dep, 'arr': arr, 'code': code(seq[b][1]),
                'ab': seq[b][4] == 0, 'ae': seq[e][4] == 0, 'bay': bay.group(1) if bay else None,
                'stops': [[code(x[1]), x[3] // 60, x[4]] for x in seq], 'bi': b, 'di': e,
            })
            used.update(x[1] for x in seq)
    for k, n in sorted(fallbacks.items()):
        log(f'  matched by position ({n} trips): {k}')

    cal, out = Calendar(feed), {}
    for day in days:
        ymd = day.strftime('%Y%m%d')
        if not cal.covers(ymd):
            out[day] = None                             # the feed doesn't reach this date: unknown, not "no service"
            continue
        on = cal.active(day)
        res = {}
        for d in ('am', 'pm'):
            seen, lst = set(), []
            for s in on:
                for t in legs.get((d, s), []):
                    k = (t['line'], t['dep'], t['arr'])
                    if k not in seen:
                        seen.add(k); lst.append(t)
            res[d] = sorted(lst, key=lambda t: (t['dep'], t['line']))
        out[day] = res
    stop_info = {code(s): [stops[s].get('stop_name', ''), round(pos(s)[0], 5), round(pos(s)[1], 5)] for s in used}
    return out, stop_info, cal


# ---------------------------------------------------------------- BART
def color_of(r):
    text = ' '.join(r.get(k, '') for k in ('route_short_name', 'route_long_name', 'route_desc')).lower()
    for c in ('red', 'orange', 'yellow', 'green', 'blue', 'grey', 'gray'):
        if re.search(r'\b' + c + r'\b', text):
            return 'Grey' if c == 'gray' else c.capitalize()
    h = (r.get('route_color') or '').strip().lstrip('#')
    if len(h) == 6:
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        return min(PALETTE, key=lambda c: sum((a - b) ** 2 for a, b in zip(PALETTE[c], rgb)))
    return 'BART'


def short_station(name):
    name = re.sub(r'\s*/\s*Oakland City Center', ' Oakland', name)
    name = re.sub(r'\bStreet\b', 'St', name)
    return re.sub(r'\s+(BART|Station)$', '', name).strip()


def build_bart(feed, days):
    stops = {r['stop_id']: r for r in feed.rows('stops.txt')}
    station = lambda sid: (stops.get(sid, {}).get('parent_station') or '').strip() or sid
    names = {}
    for sid, s in stops.items():
        st = station(sid)
        if st == sid or st not in names:
            names[st] = s.get('stop_name', sid) if st == sid else stops.get(st, s).get('stop_name', sid)
    key = {}
    for k, pat in BART_NAMES.items():
        hits = [st for st, n in names.items() if re.search(pat, n, re.I)]
        if hits:
            key[k] = sorted(hits, key=len)[0]
    missing = [k for k in ('NBRK', 'MONT') if k not in key]
    if missing:
        raise SystemExit(f'BART feed has no station matching {missing}')
    alias = {v: k for k, v in key.items()}
    colors = {r['route_id']: color_of(r) for r in feed.rows('routes.txt')}
    trips = {r['trip_id']: (r['route_id'], r['service_id']) for r in feed.rows('trips.txt')}
    seqs = trip_sequences(feed, trips)
    paths = {}
    for tid, seq in seqs.items():
        path = []
        for x in seq:
            st = station(x[1])
            if not path or path[-1][0] != st:
                path.append([st, x[2], x[3]])
        paths[tid] = path
    log(f'BART: {len(trips)} trips; stations {key}')

    def plans(active, d):
        O, D = (key[k] for k in BART_ENDS[d])
        X = [key[k] for k in BART_XFER if k in key]
        todays = {t: paths[t] for t in paths if trips[t][1] in active}
        idx = {t: {st: i for i, (st, _, _) in reversed(list(enumerate(p)))} for t, p in todays.items()}
        onward = defaultdict(list)                      # station -> departures there that reach D later
        for t, p in todays.items():
            if D in idx[t]:
                for x in X:
                    if x in idx[t] and idx[t][x] < idx[t][D]:
                        onward[x].append((p[idx[t][x]][2], t))
        for x in onward:
            onward[x].sort()
        its = []
        for t, p in todays.items():
            if O not in idx[t]:
                continue
            i = idx[t][O]
            dep = p[i][2]
            if not (WINDOW[d][0] <= dep // 60 < WINDOW[d][1]):
                continue
            color = colors.get(trips[t][0], 'BART')
            if D in idx[t] and idx[t][D] > i:
                j = idx[t][D]
                its.append({'dep': dep, 'arr': p[j][1], 'direct': True, 'color': color,
                            'stops': [[alias.get(s, s), a // 60 if n else dd // 60] for n, (s, a, dd) in enumerate(p[i:j + 1])], 'xi': -1})
                continue
            best = None
            for x in X:
                k = idx[t].get(x)
                if k is None or k <= i:
                    continue
                arr_x = p[k][1]
                lst = onward.get(x, [])
                n = bisect.bisect_left(lst, (arr_x, ''))
                while n < len(lst) and lst[n][1] == t:
                    n += 1
                if n == len(lst):
                    continue
                t2 = lst[n][1]
                q = todays[t2]
                a2, b2 = idx[t2][x], idx[t2][D]
                arr = q[b2][1]
                # same arrival at two changes: take the one with more time to cross the platform, then the earlier one
                rank = (arr, -(lst[n][0] - arr_x), k)
                if best is None or rank < best['_rank']:
                    first = [[alias.get(s, s), (a if n2 else dd) // 60] for n2, (s, a, dd) in enumerate(p[i:k + 1])]
                    second = [[alias.get(s, s), dd // 60] for s, a, dd in q[a2 + 1:b2]] + [[alias.get(q[b2][0], q[b2][0]), arr // 60]]
                    best = {'dep': dep, 'arr': arr, 'direct': False, 'color': color, 'to': colors.get(trips[t2][0], 'BART'),
                            'via': short_station(names[x]).replace(' Oakland', ''), 'stops': first + second, 'xi': len(first) - 1, '_rank': rank}
            if best:
                del best['_rank']
                its.append(best)
        # keep only trips nobody beats: another one leaving later (or together) and arriving earlier (or together)
        its.sort(key=lambda it: (-it['dep'], it['arr'], not it['direct']))
        kept, best_arr = [], float('inf')
        for it in its:
            if it['arr'] < best_arr:
                kept.append(it)
                best_arr = it['arr']
        for it in kept:
            it['dep'] //= 60; it['arr'] //= 60
        return sorted(kept, key=lambda it: it['dep'])

    cal, out = Calendar(feed), {}
    for day in days:
        if not cal.covers(day.strftime('%Y%m%d')):
            out[day] = None
            continue
        on = cal.active(day)
        out[day] = {d: plans(on, d) for d in ('am', 'pm')}
    info = {}
    for st, n in names.items():
        k = alias.get(st, st)
        s = stops.get(st) or {}
        try:
            info[k] = [short_station(n), round(float(s['stop_lat']), 5), round(float(s['stop_lon']), 5)]
        except (KeyError, ValueError):
            info[k] = [short_station(n), None, None]
    return out, info, cal


# ---------------------------------------------------------------- output
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--actransit', default='')
    ap.add_argument('--bart', default='')
    ap.add_argument('--out', default='data/schedule.json')
    ap.add_argument('--days', type=int, default=60)
    ap.add_argument('--today', default='')
    ap.add_argument('--source', default='', help='how the AC Transit feed was fetched, for the record')
    a = ap.parse_args()

    today = dt.date.fromisoformat(a.today) if a.today else (dt.datetime.now(ZoneInfo(TZ)) if ZoneInfo else dt.datetime.utcnow() - dt.timedelta(hours=7)).date()
    days = [today + dt.timedelta(n) for n in range(a.days)]
    sources, bus, bart, stops, stations = {}, {}, {}, {}, {}

    if a.actransit and os.path.exists(a.actransit):
        try:
            bus, stops, cal = build_bus(Feed(a.actransit), days)
            sources['actransit'] = {'ok': True, 'via': a.source or 'file', 'range': [cal.first, cal.last]}
        except Exception as e:                          # keep going: the page falls back to built-in bus times
            log(f'AC Transit feed failed: {e!r}')
            sources['actransit'] = {'ok': False, 'error': str(e)[:200]}
    else:
        sources['actransit'] = {'ok': False, 'error': 'no feed'}
    if a.bart and os.path.exists(a.bart):
        try:
            bart, stations, cal = build_bart(Feed(a.bart), days)
            sources['bart'] = {'ok': True, 'range': [cal.first, cal.last]}
        except BaseException as e:
            log(f'BART feed failed: {e!r}')
            sources['bart'] = {'ok': False, 'error': str(e)[:200]}
    else:
        sources['bart'] = {'ok': False, 'error': 'no feed'}

    sets, day_map = {}, {}
    for day in days:
        entry = {'bus': bus.get(day), 'bart': bart.get(day)}
        blob = json.dumps(entry, sort_keys=True, separators=(',', ':'))
        sid = hashlib.sha1(blob.encode()).hexdigest()[:8]
        sets[sid] = entry
        day_map[day.isoformat()] = sid
    doc = {'version': 1, 'generated': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
           'tz': TZ, 'sources': sources, 'stops': stops, 'stations': stations, 'days': day_map, 'sets': sets}

    # Short report for the workflow log: the next weekday
    probe = next((d for d in days if d.weekday() < 5), days[0])
    log(f'--- {probe.isoformat()} ({probe.strftime("%A")}) ---')
    for d in ('am', 'pm'):
        b = (bus.get(probe) or {}).get(d)
        if b is None:
            log(f'  bus {d}: unknown (no AC Transit data)')
        else:
            by = defaultdict(list)
            for t in b:
                by[t['line']].append(f"{t['dep'] // 60}:{t['dep'] % 60:02d}>{t['arr'] // 60}:{t['arr'] % 60:02d}{'~' if (t['ab'] if d == 'am' else t['ae']) else ''}")
            for ln in ('J', 'FS', 'G'):
                log(f'  {ln:2} {d}: ' + (' '.join(by[ln]) or 'none'))
        r = (bart.get(probe) or {}).get(d)
        if r is None:
            log(f'  BART {d}: unknown')
        else:
            direct = sum(1 for x in r if x['direct'])
            log(f'  BART {d}: {len(r)} trips ({direct} direct); first ' + ', '.join(
                f"{x['dep'] // 60}:{x['dep'] % 60:02d}>{x['arr'] // 60}:{x['arr'] % 60:02d} {x['color']}{'' if x['direct'] else ' via ' + x['via']}" for x in r[:6]))
    holidays = [d.isoformat() for d in days if d.weekday() < 5 and bus.get(d) is not None and not (bus[d]['am'] or bus[d]['pm'])]
    log(f'  weekdays without J/FS/G service in range: {holidays or "none"}')

    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(doc, f, separators=(',', ':'), sort_keys=True)
        f.write('\n')
    log(f'wrote {a.out}: {os.path.getsize(a.out) // 1024} KB, {len(sets)} distinct service days')


if __name__ == '__main__':
    main()
