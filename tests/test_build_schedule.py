"""Tests for tools/build_schedule.py against small synthetic GTFS feeds.

    python3 -m unittest discover -s tests
"""
import json, os, subprocess, sys, tempfile, unittest, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'tools', 'build_schedule.py')


def write_zip(path, files, folder=''):
    with zipfile.ZipFile(path, 'w') as z:
        for name, rows in files.items():
            z.writestr(folder + name, '\n'.join(','.join(str(c) for c in r) for r in rows) + '\n')


def hm(t):
    return f'{t // 60:02d}:{t % 60:02d}:00'


def actransit_feed(path):
    S = [  # stop_id, code, name, lat, lon
        (1001, 57799, 'Solano Av & Colusa Av', 37.8913, -122.2789), (1002, 53339, 'Shattuck Av & Cedar St', 37.8785, -122.2692),
        (1003, 55988, 'University Av & Martin Luther King Jr Way', 37.8716, -122.2727), (1004, 55722, 'University Av & Sacramento St', 37.87044, -122.2821),
        (1005, 52566, 'University Av & San Pablo Av', 37.86911, -122.29254), (1006, 51105, 'University Av & 6th St', 37.8677, -122.2992),
        (1100, 50019, 'Salesforce Transit Center Bay 19', 37.7894, -122.3970), (1101, 50010, 'Salesforce Transit Center Bay 10', 37.7892, -122.3973),
        (1102, 50035, 'Salesforce Transit Center Bay 35', 37.7893, -122.3968), (1103, 50012, 'Salesforce Transit Center Bay 12', 37.7891, -122.3975),
        (1200, 55998, 'Sacramento St & University Av', 37.87007, -122.28208), (1201, 55000, 'Sacramento St & Dwight Way', 37.8623, -122.2813),
        (1202, 55001, 'Ashby Av & San Pablo Av', 37.8519, -122.2872), (1300, 50650, 'El Cerrito Plaza BART', 37.9030, -122.2990),
        (1301, 55501, 'San Pablo Av & Gilman St', 37.8800, -122.2990), (1302, 59600, 'San Pablo Av & Cedar St', 37.87542, -122.29433),
        (1400, 51106, 'University Av & 6th St', 37.8678, -122.2990), (1401, 56667, 'University Av & Sacramento St', 37.87037, -122.28135),
        (1402, 55265, 'Solano Av & Colusa Av', 37.8914, -122.2790),
        (1500, 59990, 'San Pablo Av & Cedar St', 37.87562, -122.29418),      # evening G stop under an unexpected code
        (1600, 55997, 'Sacramento St & University Av', 37.87012, -122.28216),  # evening J terminal under an unexpected code
    ]
    trips, st = [], []

    def trip(tid, route, service, stops):             # stops: (stop_id, minute or None, timepoint)
        trips.append((route, service, tid))
        for n, (sid, t, tp) in enumerate(stops, 1):
            tt = hm(t) if t is not None else ''
            st.append((tid, tt, tt, sid, n, tp))

    for dep, arr in ((350, 384), (427, 470), (487, 532)):              # J mornings: 5:50, 7:07, 8:07
        trip(f'J{dep}', 'J', 'WKDY', [(1200, dep, 1), (1201, dep + 4, 0), (1202, dep + 9, 1), (1100, arr, 1)])
    for start in (370, 472):                                            # FS from Solano & Colusa 6:10 and 7:52
        trip(f'FS{start}', 'FS', 'WKDY', [(1001, start, 1), (1002, start + 9, 1), (1003, None, 0), (1004, None, 0),
                                           (1005, None, 0), (1006, start + 17, 1), (1100, start + 40, 1)])
    trip('G443', 'G', 'WKDY', [(1300, 430, 1), (1301, 438, 1), (1302, 443, 0), (1005, 446, 0), (1006, 449, 1), (1100, 470, 1)])
    trip('J1005', 'J', 'WKDY', [(1102, 1005, 1), (1202, 1035, 1), (1201, 1041, 0), (1600, 1047, 1)])
    trip('FS990', 'FS', 'WKDY', [(1101, 990, 1), (1400, 1032, 1), (1401, 1040, 0), (1402, 1055, 1)])
    trip('G970', 'G', 'WKDY', [(1103, 970, 1), (1400, 995, 1), (1500, 1006, 0), (1301, 1010, 1)])
    trip('51B', '51B', 'WKDY', [(1003, 400, 1), (1004, 403, 1), (1005, 407, 1)])  # a local line through the same corner
    write_zip(path, {
        'agency.txt': [('agency_id', 'agency_name'), ('AC', 'AC Transit')],
        'stops.txt': [('stop_id', 'stop_code', 'stop_name', 'stop_lat', 'stop_lon')] + S,
        'routes.txt': [('route_id', 'route_short_name', 'route_type'), ('J', 'J', 3), ('FS', 'FS', 3), ('G', 'G', 3), ('51B', '51B', 3)],
        'trips.txt': [('route_id', 'service_id', 'trip_id')] + trips,
        'stop_times.txt': [('trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence', 'timepoint')] + st,
        'calendar.txt': [('service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'start_date', 'end_date'),
                         ('WKDY', 1, 1, 1, 1, 1, 0, 0, 20260801, 20261231)],
        'calendar_dates.txt': [('service_id', 'date', 'exception_type'), ('WKDY', 20261126, 2)],   # Thanksgiving
    }, folder='gtfs/')


def bart_feed(path):
    names = {'NBRK': 'North Berkeley', 'DBRK': 'Downtown Berkeley', 'ASHB': 'Ashby', 'MCAR': 'MacArthur', 'ROCK': 'Rockridge',
             '19TH': '19th Street Oakland', '12TH': '12th Street / Oakland City Center', 'LAKE': 'Lake Merritt',
             'WOAK': 'West Oakland', 'EMBR': 'Embarcadero', 'MONT': 'Montgomery Street'}
    stops = [('stop_id', 'stop_name', 'stop_lat', 'stop_lon', 'location_type', 'parent_station')]
    for k, n in names.items():
        stops.append((k, n, 37.8, -122.3, 1, ''))
        stops.append((k + '_1', n + ' Platform 1', 37.8, -122.3, 0, k))
    trips, st = [], []

    def trip(tid, route, service, path_):
        trips.append((route, service, tid))
        for n, (k, t) in enumerate(path_, 1):
            st.append((tid, hm(t), hm(t), k + '_1', n))

    red = ['NBRK', 'DBRK', 'ASHB', 'MCAR', '19TH', '12TH', 'WOAK', 'EMBR', 'MONT']
    offs = [0, 2, 5, 8, 11, 13, 16, 24, 27]
    for dep in (422, 442, 462):                                  # Red 7:02 7:22 7:42, 27 minutes
        trip(f'R{dep}', 'RED', 'WKDY', [(s, dep + o) for s, o in zip(red, offs)])
    for dep in (434, 440):                                       # Orange 7:14 and 7:20 to MacArthur, then on to Lake Merritt
        trip(f'O{dep}', 'ORG', 'WKDY', [('NBRK', dep), ('DBRK', dep + 2), ('ASHB', dep + 5), ('MCAR', dep + 8), ('19TH', dep + 11), ('LAKE', dep + 16)])
    for at_mcar in (443, 463):                                   # Yellow through MacArthur 7:23 and 7:43 to Montgomery
        trip(f'Y{at_mcar}', 'YEL', 'WKDY', [('ROCK', at_mcar - 3), ('MCAR', at_mcar), ('19TH', at_mcar + 3), ('12TH', at_mcar + 5),
                                              ('WOAK', at_mcar + 8), ('EMBR', at_mcar + 16), ('MONT', at_mcar + 17)])
    trip('RN1028', 'REDN', 'WKDY', [(s, 1028 + o) for s, o in zip(list(reversed(red)), [0, 1, 9, 12, 14, 17, 20, 23, 26])])
    trip('YE1039', 'YELE', 'WKDY', [('MONT', 1039), ('EMBR', 1040), ('WOAK', 1048), ('12TH', 1051), ('19TH', 1053), ('MCAR', 1056), ('ROCK', 1059)])
    trip('ON1057', 'ORGN', 'WKDY', [('LAKE', 1052), ('19TH', 1055), ('MCAR', 1058), ('ASHB', 1061), ('DBRK', 1064), ('NBRK', 1066)])
    trip('SUN1', 'RED', 'SUN', [(s, 480 + o) for s, o in zip(red, offs)])
    write_zip(path, {
        'stops.txt': stops,
        'routes.txt': [('route_id', 'route_short_name', 'route_long_name', 'route_color'),
                       ('RED', 'Red-S', 'Richmond to Millbrae', 'ff0000'), ('REDN', 'Red-N', 'Millbrae to Richmond', 'ff0000'),
                       ('ORG', '', 'Richmond to Berryessa', 'ff9933'), ('ORGN', '', 'Berryessa to Richmond', 'ff9933'),
                       ('YEL', 'Yellow-S', 'Antioch to SFO', 'ffff33'), ('YELE', 'Yellow-N', 'SFO to Antioch', 'ffff33')],
        'trips.txt': [('route_id', 'service_id', 'trip_id')] + trips,
        'stop_times.txt': [('trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence')] + st,
        'calendar.txt': [('service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'start_date', 'end_date'),
                         ('WKDY', 1, 1, 1, 1, 1, 0, 0, 20260801, 20261231), ('SUN', 0, 0, 0, 0, 0, 0, 1, 20260801, 20261231)],
        'calendar_dates.txt': [('service_id', 'date', 'exception_type'), ('WKDY', 20261126, 2), ('SUN', 20261126, 1)],
    })


class BuildSchedule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        act, bart, out = (os.path.join(cls.tmp, n) for n in ('act.zip', 'bart.zip', 'schedule.json'))
        actransit_feed(act); bart_feed(bart)
        cls.proc = subprocess.run([sys.executable, SCRIPT, '--actransit', act, '--bart', bart, '--out', out,
                                   '--today', '2026-09-24', '--days', '70'], capture_output=True, text=True)
        cls.log = cls.proc.stderr
        with open(out) as f:
            cls.doc = json.load(f)

    def day(self, date):
        return self.doc['sets'][self.doc['days'][date]]

    def test_runs_clean(self):
        self.assertEqual(self.proc.returncode, 0, self.log)
        self.assertTrue(self.doc['sources']['actransit']['ok'] and self.doc['sources']['bart']['ok'], self.doc['sources'])

    def test_morning_buses(self):
        am = self.day('2026-09-24')['bus']['am']
        got = [(t['line'], t['dep'], t['arr']) for t in am]
        self.assertIn(('J', 350, 384), got)
        self.assertIn(('J', 427, 470), got)           # slower trips are kept; the page applies its own cutoff
        self.assertNotIn('51B', [t['line'] for t in am])
        fs = [t for t in am if t['line'] == 'FS']
        self.assertEqual([t['dep'] for t in fs], [383, 485])   # University & Sacramento, interpolated between timepoints
        self.assertTrue(all(t['ab'] for t in fs))     # ...so marked approximate
        self.assertEqual(fs[0]['stops'][fs[0]['bi']][0], '55722')
        g = [t for t in am if t['line'] == 'G'][0]
        self.assertEqual((g['dep'], g['arr'], g['code'], g['ab']), (443, 470, '59600', True))
        j = [t for t in am if t['line'] == 'J'][0]
        self.assertFalse(j['ab'])

    def test_evening_buses_and_position_fallback(self):
        pm = {t['line']: t for t in self.day('2026-09-24')['bus']['pm']}
        self.assertEqual((pm['J']['dep'], pm['J']['arr'], pm['J']['bay']), (1005, 1047, '35'))
        self.assertEqual(pm['J']['stops'][pm['J']['di']][0], '55997')   # found by position
        self.assertEqual((pm['G']['dep'], pm['G']['arr'], pm['G']['bay']), (970, 1006, '12'))
        self.assertEqual((pm['FS']['arr'], pm['FS']['ae']), (1040, True))
        self.assertIn('matched by position', self.log)

    def test_holiday_and_weekend(self):
        thanks = self.day('2026-11-26')
        self.assertEqual(thanks['bus'], {'am': [], 'pm': []})
        self.assertEqual([x['dep'] for x in thanks['bart']['am']], [480])   # BART runs its Sunday schedule
        sat = self.day('2026-09-26')
        self.assertEqual(sat['bus'], {'am': [], 'pm': []})

    def test_beyond_feed_is_unknown_not_empty(self):
        self.assertIsNone(self.day('2027-01-01')['bus']) if '2027-01-01' in self.doc['days'] else None
        doc = self.doc
        last = sorted(doc['days'])[-1]
        self.assertIsNotNone(self.day(last)['bus'])

    def test_bart_pareto(self):
        am = self.day('2026-09-24')['bart']['am']
        got = [(x['dep'], x['arr'], x['direct']) for x in am]
        self.assertIn((422, 449, True), got)
        self.assertIn((434, 460, False), got)          # Orange 7:14, change at MacArthur to the 7:23 Yellow
        self.assertNotIn(440, [x['dep'] for x in am])  # Orange 7:20 loses to the 7:22 Red
        orange = [x for x in am if x['dep'] == 434][0]
        self.assertEqual((orange['color'], orange['to'], orange['via']), ('Orange', 'Yellow', 'MacArthur'))
        self.assertEqual(orange['stops'][orange['xi']][0], 'MCAR')
        self.assertEqual(orange['stops'][0][0], 'NBRK')
        self.assertEqual(orange['stops'][-1], ['MONT', 460])
        pm = self.day('2026-09-24')['bart']['pm']
        via = [x for x in pm if not x['direct']][0]
        self.assertEqual((via['dep'], via['arr'], via['via'], via['color'], via['to']), (1039, 1066, '19th St', 'Yellow', 'Orange'))
        self.assertEqual(self.doc['stations']['NBRK'][0], 'North Berkeley')
        self.assertEqual(self.doc['stations']['12TH'][0], '12th St Oakland')

    def test_missing_feed_leaves_bus_unknown(self):
        out = os.path.join(self.tmp, 'bart-only.json')
        p = subprocess.run([sys.executable, SCRIPT, '--bart', os.path.join(self.tmp, 'bart.zip'), '--out', out,
                            '--today', '2026-09-24', '--days', '3'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        doc = json.load(open(out))
        self.assertFalse(doc['sources']['actransit']['ok'])
        self.assertTrue(all(s['bus'] is None for s in doc['sets'].values()))


if __name__ == '__main__':
    unittest.main()
