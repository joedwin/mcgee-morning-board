# McGee Morning Board

A one-page weekday departure board for getting between North Berkeley and Salesforce Tower: the transbay buses from the closest stop on each AC Transit line (J and FS both from Sacramento & University, G from San Pablo & Cedar), plus the useful BART trains. Morning and evening tabs, Bus-only or Bus + BART. Mornings leave out bus trips longer than 37 minutes.

Ten looks, switchable from the picker: Classic, Split-flap, Map (schematic), Sky (follows the real Berkeley sky), Type, Real map (OpenStreetMap with true route geometry), Strips, Radar, River (timeline), Bay (silhouette). The map-style looks draw vehicles live along the routes.

## How it fits together

| Piece | What it does | Where |
| --- | --- | --- |
| The page | Static HTML served by GitHub Pages. Deep links: `?look=strip`, `?mode=bus`, `?dir=pm`. | `index.html` |
| Timetables | Rebuilt nightly from AC Transit's and BART's official GTFS feeds: exact times at your stops, holidays, BART's real trains and one-change trips. Commits only when something changed. | `tools/`, `data/schedule.json`, `.github/workflows/timetables.yml` |
| Live data server | A Cloudflare Worker that holds the AC Transit key and forwards four read-only real-time requests, with caching and CORS. | `worker/`, `.github/workflows/worker.yml` |
| Version stamp | Shows when the page was published, and offers a reload when a newer deploy is out. | `version.json` (filled in by GitHub Pages) |

If the timetable file is missing or doesn't cover a day, the page falls back to times typed from the printed J, FS and G timetables and a regular BART pattern. If the Worker isn't deployed, a key pasted into the page still works.

## Setup: live buses on every device

1. **Cloudflare.** Create a free account at cloudflare.com and open *Workers & Pages* once, which sets up your `workers.dev` address. Then create an API token from the *Edit Cloudflare Workers* template, and copy your Account ID from the dashboard.
2. **GitHub secrets.** In this repo, go to *Settings → Secrets and variables → Actions* and add `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and `ACT_TOKEN`, your AC Transit key from https://api.actransit.org/transit/Account/Register.
3. **Run.** Under *Actions*, run *Deploy the live-data Worker* and *Refresh timetables*. The first writes `config.json` with the Worker's address, and the page picks it up on its next load.

Without those steps the timetable job still runs every night and builds BART's timetable from its public feed. Bus times stay on the built-in ones until `ACT_TOKEN` is added, because AC Transit only hands out its timetable file to key holders.

## Details

- **Trip sheet.** Tap any departure for its route as a stop list with every scheduled time, your board and exit stops, and the vehicle's live position. The bus is tied to your trip by AC Transit's trip id. BART trips show every station and the change. While the sheet is open it polls every 20 s, glides the bus to its new spot, and says how old the position is.
- **Live data without the Worker.** Paste a key into the "See this bus live" box in any bus sheet, or under About. About → "Copy setup link" moves the key to another device through a `#token=` link, which is saved on arrival and removed from the address bar. Requests try `fetch` and fall back to JSONP if the browser blocks the cross-origin call.
- **Stop IDs** are AC Transit's public five-digit codes, the numbers on the stop signs, which the real-time API uses. The timetable builder matches them by position when a feed files a corner under a different code.
- **Tests.** `python3 -m unittest discover -s tests` for the timetable builder. `cd worker && npm test` for the Worker. The timetable workflow runs the builder's tests before every build.
