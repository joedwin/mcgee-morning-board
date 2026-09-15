# McGee Morning Board

A one-page weekday morning departure board for getting from North Berkeley to Salesforce Tower: the transbay buses under 37 minutes from the closest stop on each AC Transit line (J, FS, G), plus the next BART trains from North Berkeley.

- Static HTML, no build step. Open `index.html` or host it anywhere.
- BART real-time departures come from the public BART API and work out of the box.
- AC Transit real-time needs a free personal token from https://api.actransit.org/transit/Account/Register. Paste it under "Live predictions" on the page; it is stored only in your browser.
- Timetables: AC Transit J (Dec 2023), FS (Dec 2021), G (Feb 2026); BART weekday schedule.
