# europe-room-hunt-bot

Automates the tedious part of hunting for a room/flat on wg-gesucht.de, the
biggest shared-flat and apartment marketplace for Germany, Austria, and
Switzerland:

1. Searches wg-gesucht.de on a schedule for new listings matching your
   criteria (city, budget, radius, move-in date, room type).
2. Automatically skips listings restricted to a gender you don't match, and
   never re-messages a listing you've already contacted — including ones you
   messaged yourself by hand, not just through the bot.
3. Sends each new match a contact message automatically (once you turn this
   on) — bilingual by default (German + English in one message) so it works
   regardless of the landlord's language.
4. Checks your wg-gesucht inbox for replies and pings a Discord channel when
   one comes in, flagging common rental-scam red flags along the way.

## Before you start: two important caveats

- **wg-gesucht's terms of service prohibit automated/bot use of the site.**
  This is built for personal, low-volume use (a handful of messages a day,
  human-like delays between actions) — not scraping at scale. Even so, there
  is real risk of the account getting flagged or suspended. Don't run this
  on an account you can't afford to lose, and don't crank up
  `max_new_contacts_per_run` or lower the delays in `config.yaml`.
- **Free wg-gesucht accounts have a real cap on contact requests** before
  the site demands a paid package. The exact number isn't published and
  isn't guessed here — `src/messenger.py` detects wg-gesucht's own
  upgrade/paywall prompt if and when it actually appears, and reports it via
  Discord distinctly from a normal send failure, rather than the bot
  enforcing some made-up limit.

## Quick start

```bash
git clone <this-repo-url>
cd europe-room-hunt-bot
./start.sh
```

That's it — `start.sh` sets up everything Python-related on its own (first
run only), then walks you through the rest with plain-English prompts: your
search criteria (by answering questions, not editing files), Discord
alerts, your message to landlords, logging in, a safe test run, and turning
on automatic scheduling. No command line experience beyond running that one
command is needed. It's safe to run again any time — anything already set
up gets skipped automatically, and it'll ask before changing anything.

The sections below explain what each piece does and how to do it by hand
instead, if you'd rather have full control over each step (or need to
troubleshoot something `start.sh` did for you).

## Manual setup

### 0. Environment (start.sh does this automatically)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 1. Discord webhooks (for alerts)

Two channels are used, so replies stand out from routine status noise:

- `DISCORD_WEBHOOK_URL` — new listings found, messages sent, errors/session-expiry.
- `DISCORD_REPLIES_WEBHOOK_URL` — only landlord replies land here.

For each channel: in Discord, go to Channel Settings → Integrations →
Webhooks → New Webhook, name it, and copy the **Webhook URL**.

Then:
```bash
cp .env.example .env
# edit .env and set both DISCORD_WEBHOOK_URL and DISCORD_REPLIES_WEBHOOK_URL
```
If you only set up one webhook, replies fall back to posting in the main channel.

### 2. Log in to wg-gesucht (you do this by hand, once)

```bash
python scripts/setup_login.py
```

A real Chrome window opens. **You** type in your wg-gesucht username/password
and solve any captcha — this script never sees or handles your password.
Once you can see your account in the browser, press Enter in the terminal.
It saves your session to `storage_state.json` and tries to auto-detect your
inbox URL for reply-checking (if it can't, it'll tell you what to set
manually in `config.yaml`).

Your session will eventually expire (days to weeks) — if the bot posts a
"🔒 session expired" alert to Discord, just re-run this script.

### 3. Configure your search

```bash
python scripts/configure.py
```

An interactive wizard — no YAML editing needed. It asks for your city (by
name — "Munich", "Zurich", "Vienna", whatever; it resolves this against
wg-gesucht's own city lookup, so you never need their internal numeric
IDs), room type, budget, radius, move-in date, your own gender
(`applicant_gender`, used to skip listings you're not eligible for — some
flatshares only want a specific gender), an optional preference for
current residents' gender (`room_gender_preference`), and how often to
check for new listings. It writes `config.yaml` (gitignored, so none of
this gets committed) and is safe to re-run any time you want to change
your criteria.

Prefer editing YAML by hand instead? `cp config.example.yaml config.yaml`
and fill it in directly — every field is commented there. The one thing
the wizard can't do for you: if you'd rather build your search visually on
wg-gesucht.de itself (any filter, not just the ones the wizard asks about)
and paste the resulting URL, set that as `search.custom_url` and it takes
priority over everything else in `search:`. If you do that, also set
wg-gesucht's own "Gesucht" filter when building the URL — the gender
settings above still apply a client-side backstop either way, but the
server-side filter is more thorough.

### 4. Write the message

```bash
cp message_template.example.txt message_template.txt
```

Fill in the `[bracketed placeholders]` with your real name, situation, and
contact details. The template is bilingual: a German version first
(landlords respond faster to German), then an English version below a
divider — so it works whether or not the landlord speaks English, without
the bot ever needing to detect language or re-send anything.
`{listing_title}` is filled in automatically per listing.

The bot refuses to go live (`--dry-run` still works) if it finds any
`[bracketed placeholder text]` still left in the template — that's the
signal it's not finished being edited yet.

### 5. Test with a dry run (no login needed, sends nothing)

```bash
python -m src.main --dry-run
```

This searches and posts any matches to Discord as "dry run" alerts, but
never logs in or sends anything. Confirm the listings it finds actually
match what you want before going further.

### 6. Go live

Edit `config.yaml`: set `live_mode: true`. Then run once by hand to watch it
work:

```bash
python -m src.main
```

Check Discord for the "✅ Sent message" alerts, and log into wg-gesucht
yourself to confirm the messages actually look right on a listing or two
before trusting it fully.

### 7. Pick a schedule mode

Set `schedule.mode` in `config.yaml` to control how often the bot checks for
new listings:

| Mode | Interval | Tradeoff |
|---|---|---|
| `aggressive` | every 1 hour | Catches listings fastest; most bot-like pattern, highest detection risk |
| `laid_back` | every 3 hours | |
| `normal` | every 6 hours | Lowest risk, slowest to react (default) |

### 8. Schedule it

**macOS**, using launchd — generates the schedule from `schedule.mode` above
and loads it:

```bash
./scripts/install_launchd.sh
```

Re-run this any time you change `schedule.mode` to apply the new interval.
To stop it: `launchctl unload ~/Library/LaunchAgents/com.roomhunt.bot.plist`

Logs land in `bot.log` (the app's own log) and `launchd.out.log` /
`launchd.err.log` (anything launchd itself captures).

**Linux**, using cron:

```bash
python scripts/install_cron.py
```

Reads `schedule.mode` and installs (or updates) a single crontab line for
it — only ever touches its own marked line, never your other cron jobs. To
remove it: `crontab -e` and delete the line containing
`# europe-room-hunt-bot`.

**Either way**, this only runs while the machine is on and awake. For 24/7
coverage regardless of your own computer, run it on a small always-on VM
instead (a few euros/month on any provider) — the setup steps are identical,
just run them there.

## Scam awareness

Rental scams are common on wg-gesucht (fake "landlord," asks for a deposit
or a wire transfer before any viewing, claims to be abroad and can't show
the place in person, offers to mail keys). `src/scam_check.py` scans every
incoming reply for known red-flag phrases (payment-before-viewing, Western
Union/MoneyGram, "I'm abroad," keys by courier, pressure to pay
immediately) and prepends a 🚨 warning to the Discord alert when it finds
one. This is a heuristic, not a guarantee — treat any request for money or
documents with normal caution regardless of whether it gets flagged.

## Gender filtering

Some wg-gesucht listings are restricted to one gender (e.g. "Frauen-WG" /
women-only flatshares), and some applicants have a preference about who
they'd be living with. Both are configurable — see `applicant_gender` and
`room_gender_preference` in step 3 of Setup above. Under the hood,
`src/searcher.py` uses wg-gesucht's own server-side filters (`wgSea` for who
a listing is recruiting, `wgFla` for current residents' gender), plus a
client-side backstop that reads each listing's "who are they looking for"
icon and title/description text for restrictions the structured field
missed.

## Duplicate-contact protection

Several independent safeguards, since a duplicate message to a landlord is
one of the worst failure modes:

- **Checks real conversations, not just its own memory.** Before
  auto-sending to any "new" listing, `sync_conversation_listing_map()` in
  `src/inbox.py` checks your actual wg-gesucht conversation list. If you
  message a landlord yourself between scheduled runs, the bot sees that
  conversation already exists and skips it.
- **Single-instance lock.** `src/main.py` takes an exclusive file lock
  (`bot.lock`) for the duration of a run. If a run is still going when the
  next scheduled one fires (a slow run, a network hang), the second
  instance skips itself instead of both processes racing on the same
  "not yet contacted" state.
- **Mark-before-send.** A listing is recorded as contacted (and excluded
  from future runs) *before* the send is attempted, not after. If the
  process is killed mid-send, the listing is never retried — worst case its
  outcome is unknown and gets flagged once via Discord for you to check by
  hand, but it can never be auto-sent twice.
- **Dedup within a single search.** `src/searcher.py` drops repeated ad IDs
  on the same results page (wg-gesucht can render a promoted listing
  twice), so one listing can't end up in the send queue twice in one run.

None of this can undo a message already sent — it's all about making sure
each real listing only ever gets one automated attempt.

- **Atomic, corruption-safe state saves.** `src/state.py` writes to a temp
  file and renames it over `state.json`, so a crash mid-write can't leave a
  half-written file. If `state.json` is ever unreadable anyway (disk
  corruption, manual editing gone wrong), the bot refuses to run live and
  alerts loudly rather than treating it as "nothing contacted yet" — the
  one thing that could actually cause mass re-contacting.

## Troubleshooting

- **"Could not find a message box / send button"**: wg-gesucht changed their
  contact page markup, or this particular listing has a non-standard
  contact form (some require extra questions). The bot takes a screenshot
  into `screenshots/` when this happens and posts to Discord so you can send
  that one manually — check `src/messenger.py` if it's happening a lot.
- **No replies ever detected**: the inbox-scraping in `src/inbox.py` is a
  best-effort heuristic built by inspecting the real logged-in page once
  (never by having an AI assistant or anyone else handle your password). If
  it stops catching replies after a wg-gesucht redesign, open your messages
  page yourself and compare against the selectors in `src/inbox.py`.
- **Session expired constantly**: wg-gesucht uses a short-lived access token
  plus a long-lived refresh token (the refresh token is what actually keeps
  you logged in). `src/browser_session.py` re-saves `storage_state.json`
  after every run specifically so any silent token renewal carries forward
  instead of being discarded — this should make logins last close to the
  refresh token's own lifetime (roughly a year). If it's still expiring
  fast, check the "Stay logged in" box during `setup_login.py`, and check
  whether `X-Refresh-Token` in `storage_state.json` has a far-future expiry
  (a short one there means the account/browser wasn't actually granted a
  persistent login).

## Project layout

```
start.sh                       the one command to run — sets up the environment, then runs onboard.py
scripts/onboard.py             interactive wizard covering every setup step, skips what's already done
scripts/configure.py           interactive wizard — writes config.yaml, no YAML editing needed
config.example.yaml            template — for editing config.yaml by hand instead
message_template.example.txt   template — copy to message_template.txt and fill in
scripts/generate_plist.py      builds the launchd plist from config.yaml's schedule.mode
.env.example                   template — copy to .env and add your Discord webhooks
scripts/setup_login.py         one-time interactive login
scripts/install_launchd.sh     generates + installs the macOS launchd schedule
scripts/install_cron.py        generates + installs the Linux cron schedule
src/searcher.py                scrapes search results, filters gender-restricted listings (no login needed)
src/messenger.py               sends the contact message (needs login)
src/inbox.py                   checks for replies and existing conversations (needs login)
src/scam_check.py              flags common rental-scam patterns in replies
src/notify.py                  posts alerts to Discord
src/main.py                    orchestrates one run (called on a schedule)
state.json                     tracks what's already been seen/contacted (not committed)
```

## License

MIT — see `LICENSE`.
