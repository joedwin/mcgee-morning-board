# McGee Morning Board

A one-page weekday departure board for getting between North Berkeley and Salesforce Tower: the transbay buses under 37 minutes from the closest stop on each AC Transit line (J and FS both from Sacramento & University, G from San Pablo & Cedar), plus the next BART trains. Morning and evening tabs, Bus-only or Bus + BART.

Ten looks, switchable from the picker: Classic, Split-flap, Map (schematic), Sky (follows the real Berkeley sky), Type, Real map (OpenStreetMap with true route geometry), Strips, Radar, River (timeline), Bay (silhouette). The map-style looks draw vehicles live along the routes.

- Static HTML, no build step. Open `index.html` or host it anywhere. Deep links: `?look=strip`, `?mode=bus`, `?dir=pm`.
- BART real-time comes from the public BART API and works out of the box. Train positions are derived from arrival estimates at the far end of the leg.
- AC Transit real-time (predictions and bus positions) needs a free personal token from https://api.actransit.org/transit/Account/Register. Paste it under "About" on the page; it is stored only in your browser.
- Timetables: AC Transit J (Dec 2023), FS (current Realign schedule via the actransit.org stop pages, Sep 2026), G (Feb 2026); BART weekday schedule. Route shapes from the AC Transit GTFS feed. Stops that aren't printed timepoints (FS at University & Sacramento, G at San Pablo & Cedar) show ~ estimated times.
- Stop IDs in the page are AC Transit's public five-digit IDs (the ones on the stop signs), which is what the real-time API keys predictions and pattern points by.
