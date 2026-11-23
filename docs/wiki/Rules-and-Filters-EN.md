# Rules and filters

Every site understands these rules. They are set separately on each site's
page, in the Settings (Настройки) tab.

## Working hours

The "Working hours" («Часы работы») field sets when the site may enter
giveaways. The time follows the farm's time zone
([Settings → General](Farm-Settings-EN.md)).

| Value | What it means |
| --- | --- |
| empty | around the clock |
| `08:00-23:00` | from 8 am to 11 pm |
| `9-13, 18:30-02:00` | two windows; the second one crosses midnight |
| `22:00-06:00` | only at night |

Minutes can be left out (`9-13`). Windows are separated by a comma or a
semicolon.

Outside working hours the site spends no balance and makes no requests. It
waits for the next window, and the card says "Outside working hours, opens at
08:00" («Вне часов работы, откроется в 08:00»). If working hours end in the
middle of a run, the run stops. The "Run now" («Пройти сейчас») button starts
one run without waiting for working hours.

## Daily limits

- **Max entries per day (Макс. входов за сутки)**: how many times the site
  may enter giveaways in the last 24 hours.
- **Max spending per day (Макс. трат за сутки)**: how much may be spent in 24
  hours, in the site's currency (P, iS, OP).

The day is a rolling one: the last 24 hours, not a calendar day. When the
limit is used up, the site waits until the oldest entry of that period drops
out of the window. The card shows when that will happen: "Daily limit
reached, resets at 14:20" («Дневной лимит исчерпан, сброс в 14:20»). The bars
on the card show how much of the limit is used.

## Presets

A preset changes several settings at once and leaves the rest alone. Each
site takes from a preset only the settings it actually has. For example,
OpiumPulses has no "order", so the preset does not change the order there.

| Preset | What it is for | What it changes |
| --- | --- | --- |
| Balanced (Сбалансировано) | A good chance to win with reasonable spending. Suits most people. | no DLC and packs: yes; no 18+: no; no games you own: yes; IndieGala order: smart; max participants: 1000; IndieGala/OP reserve: 5; SteamGifts minimum points: 50; OpiumPulses free only: no |
| Economy (Экономно) | Only giveaways with few participants; the balance reserve is left untouched. | no DLC and packs: yes; no 18+: yes; no games you own: yes; IndieGala order: smart; max participants: 300; IndieGala/OP reserve: 20; SteamGifts minimum points: 100; OpiumPulses free only: yes |
| Maximum (Максимум) | Enter everywhere the balance allows. More entries, but more junk too. | no DLC and packs: no; no 18+: no; no games you own: no; IndieGala order: expiry; max participants: no limit; IndieGala/OP reserve: 0; SteamGifts minimum points: 10; OpiumPulses free only: no; pages per run: 10 |
| Games only (Только игры) | Skip DLC, soundtracks, 18+ and whatever is already in your Steam library. | no DLC and packs: yes; no 18+: yes; no games you own: yes |

## Filters

### Skip DLC, soundtracks, artbooks, packs (Пропускать DLC, саундтреки, артбуки, паки)

A giveaway is skipped if its title contains one of these words. Only whole
words match, so "Backpack Hero" stays a game even though it contains "pack".

`soundtrack`, `ost`, `original sound`, `artbook`, `art book`, `wallpaper`, `wallpapers`, `dlc`, `season pass`, `expansion pass`, `pack`, `costume`, `costumes`, `skin`, `skins`, `outfit`, `outfits`, `upgrade`, `booster`, `supporter edition`, `cosmetic`

### Skip 18+ (Пропускать 18+)

The words that mark a game as "adult" are also matched as whole words:

`hentai`, `nsfw`, `sex`, `sexy`, `erotic`, `erotica`, `lewd`, `porn`, `nude`, `nudity`, `waifu`, `uncensored`, `adult only`, `adults only`, `xxx`, `18+`

### Skip games in my Steam library (Пропускать игры из моей библиотеки Steam)

This filter needs a Steam Web API key and a profile in
[Settings → Steam library](Farm-Settings-EN.md), and "Game details" must be
set to "Public" in your Steam profile's privacy settings. A game is matched by
its Steam ID, or by title if there is no ID. The farm refreshes the game list
every 6 hours. If Steam does not return it, the filter simply does not work:
the farm keeps entering giveaways, and the "Check" («Проверить») button shows
the reason.

### Blacklist and whitelist

Words separated by commas, case does not matter, and a word matches anywhere
in the title:

- **blacklist (Чёрный список)**: skip giveaways whose title contains at least one of the
  words;
- **whitelist (Белый список)**: if set, take only giveaways whose title contains at least
  one of the words.

You can also add a game to the blacklist with the 🚫 button next to it in the
entry history or in Preview (Что возьмёт).

## Wishlist games first (Сначала игры из списка желаемого)

Turned on in [Settings → Steam library](Farm-Settings-EN.md). It needs a
Steam profile and a public wishlist; the API key is optional if the profile is
given as a SteamID64.

- **IndieGala** treats wishlist games as priority: they go first and may
  spend the reserve, if that is allowed.
- **SteamGifts** starts every run with the site's own "Wishlist" section.
  SteamGifts builds that section from your Steam wishlist.

## Order of checks

On every site, a giveaway goes through three checks:

1. the site's own conditions: price, participants, level and so on;
2. the shared filters: DLC, 18+, blacklist and whitelist, games in the
   library;
3. the budget: balance, reserve, daily limits.

The first check that fails becomes the reason for skipping. You can see it in
Preview and in the "Skipped: …" («Пропущено: …») log line at the end of a
run.
