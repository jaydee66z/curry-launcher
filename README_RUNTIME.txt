Windows x64, Python 3.14+.
GUI: double-click Rakbot.pyw or run python -m rakbot gui.
Tabs: Brainrot and Steal An Egg (107778070777162); stop before switching scans.
Joiner tab: Place ID/game URL, Place ID + JobID, or VIP link. All selected workers join one server.
Joiner: persistent character sessions, same-server reconnect, LoopTp restored after reconnect.
One elected active client publishes the roster; selected bot UserIds are excluded; observer failover is automatic.
Click a player: Teleport, LoopTp, Where, Stop LoopTp, Copy username. Choose all active accounts or #N.
Joiner command field also supports chat text; stop the run before changing its target.
Persistent transport: keepalive, bounded 20 retry budget, paced NAK retransmits, 60s split deadline.
Session loss logs include stop reason and server disconnect code; code 273 waits at least 60s before retry.
Steal An Egg uses cookies.txt and native read-only field snapshots, no Roblox Player or external coordinator.
Egg sessions stay on their JobID after scans. Refresh follows the server cycle, not a fixed interval.
Wait for reset using server time; re-read night duration; wait night + reset_grace before the next report.
Egg timing defaults: cycle_fallback=300, night_fallback=10, reset_grace=2 (seconds).
config.txt eggs: min_value=10000000000, states=[Slot, empty], earnings_mode=game (default).
game follows the live scale taper and additive mutation bonuses; card income excludes server/player boosts.
Table, log, threshold and sorting all use that unboosted card income; labels truncate to 3 significant figures.
product: EarningRate * scale^1.85 * product of all mutation factors; optional mutation_multipliers overrides.
Only matching eggs reach the table and [filter] log; thresholds use unrounded income.
Live field updates are received continuously; complete snapshots atomically replace current table rows.
Both scanners: rejoin the SAME JobID after disconnect; after 5 consecutive failed reconnects assign another server.
Initial join is not a reconnect; a successful full snapshot resets the counter. One isolated VM per process group.
Egg table: name, income, weight, all mutations, rarity, area and JobID; separate eggs.sqlite3 history.
GUI history: .rakbot-ui/featured.sqlite3, chronological; full run logs in .rakbot-ui/logs.
Sort by: recently added, oldest, numeric income ascending/descending, name A-Z/Z-A across all pages.
Clear empties the result list; sessions keep running. New scan reports may add rows again.
GUI: Files of logs opens .rakbot-ui/logs; Statuses shows all account phases and failure categories.
Install dependencies: python -m pip install -r requirements.txt
Keep your existing cookies.txt locally; this archive contains no account sessions.
Account selection limit: 999999; mass files are streamed without the old 8 MiB file cap.
Scanner workers control concurrent sessions separately from the selected cookie count.
Edit config.txt: featured_pets and scanner settings. CLI flags override config values.
Choose another config with --config PATH (scanner only).
CMD title: completed servers, runtime, best income, FEATURED count and best matching pet.
FEATURED checks every row of completed scans, case-insensitive exact names.
One persistent account:
python -m rakbot connect --mass-cookie-file 1 --brainrot --only-best --scan-workers 1
Parallel persistent accounts:
python -m rakbot connect --mass-cookie-file 64 --brainrot --only-best --scan-workers 64
Brainrot stays connected after BEST; first full result includes plots and road; full rescan every 30 seconds.
New Player UserId triggers a scan of that player's Owner-linked plot, once AnimalList arrives and settles for 150ms.
Join-triggered scans decode only the new plot; other rows stay cached until the next full scan.
Join scans do not reset the 30-second schedule. Unchanged results are not reported twice.
Late data for that plot is followed for 5 seconds after its first result; no new data means no extra scan.
Network updates, subscriptions, ACK/NAK and keepalive continue between checks; normal hopping is disabled.
Each worker keeps its account; extra cookies are standby.
Accounts share CPU process groups (automatic up to 8, based on CPU count).
Override groups with --scan-processes N; 1 uses the least process overhead.
One global JobID pool and console; server pages are prefetched.
Join starts are paced; HTTP 429 waits for Retry-After and retries.
Startup loads are bounded by the group count by default; active sessions release their startup slots.
Verified game blobs persist in .rakbot-cache (8 MiB per game per group; Egg: 32 MiB).
A7 shared-string inventories avoid repeat downloads; ACK batches and loss NAKs recover UDP gaps.
Brainrot server browser accepts 6-7 players out of 8; small/full servers are excluded.
Output: [20:59:19] BEST : Mutation Name ($1M/s) | JobID: ... (computer local time).
Persistent sessions allow at least 60s for initial replication and keep processing authenticated ACK/NAK and keepalive.
Unchanged BEST is normal; use status or --scan-status for session details.
This is not the Roblox Player engine. Stop with quit or Ctrl+C.
Relay: the GUI starts a WebSocket relay for LEET NOTIFIER clients (pip install -r requirements.txt for websockets).
relay.json is created next to config.txt on first start: enabled, host (0.0.0.0), port (8765), random key.
Clients connect to ws://HOST:8765/ and send {"type":"auth","key":KEY} first (or ?key=KEY in the URL); every Featured find is broadcast as JSON (name, mutation, income, jobId, placeId).
Same pet on the same JobID is sent at most once per 120 s. Open the port in the firewall; keep relay.json private.
