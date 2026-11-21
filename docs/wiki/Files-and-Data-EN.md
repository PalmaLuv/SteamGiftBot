# Files and data

All files live in the project folder, or, if the farm was started with
`--data`, in the folder given there.

| File | What it contains | In git |
| --- | --- | --- |
| `farm.json` | the panel password hash, the session signing key, the settings of the farm and of every site (cookies included), autostart | no |
| `config.ini` | SteamGifts and Telegram settings, shared with the command-line bot | no |
| `botfarm-state.json` | entry and win history, per-day counters, giveaways already seen, internal flags | no |
| `farm.json.bak`, `botfarm-state.json.bak` | the previous good version of the file, in case the current one turns out broken; `farm.json.bak` holds the same secrets as `farm.json` | no |
| `farm.json.corrupt-<time>`, `botfarm-state.json.corrupt-<time>` | a broken file found at start: the farm puts it aside instead of writing over it | no |
| `steamgiftbot-state.json` | which SteamGifts wins have already been reported | no |
| `accounts/<key>/` | files of SteamGifts cards in other [profiles](Multiple-Profiles-EN.md): their own `config.ini` with the cookie and their own `steamgiftbot-state.json` | no |
| `log/botfarm.log` | the farm log, up to 5 MB, plus three older files | no |
| `debug/` | pages the farm could not parse (currently only OpiumPulses) | no |
| `backups/` | archives from `scripts/backup-farm.sh` | no |

## farm.json

```json
{
  "web": {"password": {"salt": "…", "hash": "…"}, "secret": "…"},
  "settings": {"timezone": "Europe/Kyiv", "steam_api_key": "…", "…": "…"},
  "platforms": {
    "indiegala": {"autostart": true, "settings": {"cookie": "…", "sort": "smart", "…": "…"}},
    "steamfree": {"autostart": true, "connected": true, "settings": {}},
    "indiegala-2": {"autostart": true, "connected": true, "profile": "p2",
                    "account": "brother", "settings": {"cookie": "…"}}
  },
  "profiles": [{"id": "main", "name": "Основная"},
               {"id": "p2", "name": "Брат", "asf_bot": "Brother"}],
  "accounts": [{"key": "indiegala-2", "kind": "indiegala"}],
  "accountSeq": {"indiegala": 2},
  "profileSeq": 2
}
```

`profiles` are the [profiles](Multiple-Profiles-EN.md) ("Основная" is the
default name of the Main profile, "Брат" means "Brother"); `accounts` are the
sites connected in them beyond a site's first card; `accountSeq` and
`profileSeq` are the last numbers handed out: the number of a deleted card is
never given to a new one, so histories do not get mixed up.

You can edit the file by hand while the farm is stopped, but the panel is more
convenient. If you delete `web.secret`, all panel sessions end.

## botfarm-state.json

One key per site:

| Field | What it is |
| --- | --- |
| `entries` | the last 2000 entries: `time`, `name`, `cost`, `url` |
| `wins` | wins: `time`, `name`, `url`, `status` (`""`, `received`, `activated`), `cdkey`, `redeem` |
| `daily` | per-day counters for 120 days: `{"2026-11-20": {"e": entries, "s": spent, "w": wins}}` |
| `seen` | up to 5000 most recently processed giveaways, so they are not entered twice |
| `flags` | internal flags |
| `totalEntered`, `totalSpent` | all-time counters |

The `_farm` key holds the farm's own internal flags, for example the day of
the last summary sent.

The file is rewritten in full after every change, atomically: it is first
written to a temporary file, which then replaces the old one. So even a sudden
power-off will not leave it half-written.

## The backup copy and broken files

`farm.json` and `botfarm-state.json` reach the disk before they replace the
old file, and the old one stays next to them as `<name>.bak`.

If a file turns out broken at start (cut short, not JSON), the farm renames
it to `<name>.corrupt-<date>-<time>-<ms>`, takes the data from `<name>.bak`
and writes a warning to `log/botfarm.log`. Without a backup copy the farm
starts with an empty file, but the broken one stays next to it. The farm
never deletes the files it put aside: once you are done with them, delete
them yourself.

If a file is there but cannot be read (no permission, a disk error), the farm
does not start and says why: starting empty would, two saves later, write
over both the file and its backup copy.

`*.bak` and `*.corrupt-*` are in `.gitignore` and `.dockerignore`: they hold
the same password, session key and cookies.

## Moving to another computer

1. Stop the farm.
2. Copy `farm.json`, `config.ini`, `botfarm-state.json`,
   `steamgiftbot-state.json` and the `accounts/` folder into the project
   folder on the new computer. The easiest way is an archive from
   `scripts/backup-farm.sh`.
3. Start the farm there. The cookies keep working as long as the browser they
   were copied from has not signed out of the accounts.
