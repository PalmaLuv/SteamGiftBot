# Telegram

Through Telegram the farm reports wins and problems, and if you turn on
commands, you can control it from your phone.

## Setup in 4 steps

1. **Create a bot.** Open [@BotFather](https://t.me/BotFather) in Telegram,
   send `/newbot`, and choose a name and a username (the username must end in
   `bot`). BotFather sends you a token like `123456789:AAH…`.
2. **Paste the token** into **Settings → Telegram → Bot token (Настройки →
   Telegram → Токен бота)**.
3. **Write to the bot.** Find it in Telegram by its username and send it any
   message. For the farm to write to a group, add the bot to the group and
   write there.
4. **Find the chat.** Press **Find my chat (Найти мой чат)** and pick your
   chat from the list. Then press **Save (Сохранить)** and **Send test
   (Отправить тест)**.

If "Find my chat" finds nothing, write to the bot again and retry: Telegram
keeps only recent messages.

## What the farm sends

Messages are laid out like the project page and the panel: an icon and a
title in capitals, the site's code (SG, IG, OP, GOG), the point in bold,
figures in a monospace table, and buttons that open the right page of the
panel or the site. The language is the one chosen in the panel.

```
🎉 WIN · SG SteamGifts
Hollow Knight
Get the key and mark it as received in the panel: SteamGifts requires it.
[ Get key ] [ Wins ]
```

| Title | When | Buttons |
| --- | --- | --- |
| 🎉 WIN | the farm noticed a win (SteamGifts, IndieGala, OpiumPulses) | Get key, Wins |
| 🔑 SIGN-IN NEEDED | the site stopped accepting the cookie; the site is stopped | Reconnect |
| ⛔ SITE STOPPED | the farm cannot go on (no cookie, account banned, settings error) | Open the site |
| ⚠️ NOT WORKING | the site could not be reached for about an hour | Log |
| ✅ WORKING AGAIN | the first successful run after such an outage | — |
| ⚠️ NO ENTRIES | a giveaway site went a day (and at least 6 runs) without entering anything; one message until it enters again | Preview, Settings |
| 🎁 FREE | free games claimed (GOG, Steam, itch.io), one message per run | Site |
| 🔑 KEY RECEIVED | the farm found a win's key on the SteamGifts won page, and it does not go to ASF at once | Wins |
| ✅ KEY ACTIVATED / ⏳ WILL RETRY LATER / ⚠️ KEY REJECTED | the ASF activation result | Wins |
| 📊 DAILY SUMMARY | every day at the chosen hour | Open the panel, Wins |

With [commands](#commands) on, a win also gets "Key received" and
"Activate in ASF" buttons; see [Buttons under a win](#buttons-under-a-win).

Command replies look the same: `/status` is a table of sites with state
icons, `/preview` is "PREVIEW" with the list of giveaways, `/wins` lists the
unmarked wins.

If Telegram refuses a button that links to a home address, the message still
arrives, with the links written out under it.

A single network blip does not send anything: the farm quietly tries again
(after 1, 2 and 5 minutes when the site could not be reached at all, then every
15 minutes) and only writes when the outage lasts about an hour.

The "Send notifications" («Присылать уведомления») switch turns messages off
without erasing the token.

### Daily summary

For each site: entries and spending in 24 hours, balance, wins and the last
error, and at the end the total number of wins. For SteamGifts, IndieGala
and OpiumPulses a luck line follows: "🍀 IG за историю: выигрышей 1,
ожидалось ≈0.5 · 10 iS за выигрыш · вход в среднем 5 iS" (wins over the kept
history, the wins expected, the currency per win and the average entry cost),
the same as "Luck against expectation" on the panel's Overview
([Web panel](Web-Panel-EN.md)). If there are unmarked wins,
the summary includes a reminder: SteamGifts requires you to mark received
ones. Wins whose key is not activated yet get a line of their own, "🔑 Key in
hand but not activated" («🔑 Ключ есть, но не активирован»): SteamGifts bans
for those most often. The sending time is chosen in the "Summary hour" («Час отправки
сводки») list and follows the farm's time zone. The "Send summary now"
(«Прислать сводку сейчас») button sends it right away.

## Commands

Turn on **"Control the farm with commands" («Управлять фермой командами»)**
and save. Within a minute the bot starts replying, and the commands appear in
the Telegram menu (the `/` button next to the input field).

| Command | What it does |
| --- | --- |
| `/status` | the state of every connected site: entries in 24 hours, balance, reason for waiting, error |
| `/start indiegala` | starts a site; `/start all` starts every connected one |
| `/pause steamgifts` | stops a site; `/pause all` stops all of them |
| `/run indiegala` | starts a run now, without waiting for the pause to end (the site must be running) |
| `/preview indiegala` | a trial run: what the farm would enter right now and how much it would spend |
| `/wins` | wins that are not marked yet |
| `/report` | the daily summary |
| `/help` | the list of commands |

A site can be named by the start of its name: `/start ind`, `/preview op`,
`/pause itch`. If the prefix matches several sites, the command applies to all
of them. For example, `steam` matches both `steamgifts` and `steamfree` (free
Steam games). Site names: `steamgifts`, `indiegala`, `opiumpulses`,
`steamfree`, `gog`, `itch`. `/stop` works the same as `/pause`.

**Command security.**

- The bot replies only in the chat given in the settings. It ignores messages
  from other chats.
- Commands sent while the farm was off are skipped at startup rather than
  executed after the fact.
- The farm never takes keys or cookies through Telegram: they are pasted in
  the panel only.

### Buttons under a win

With commands on, the "🎉 WIN" message (SteamGifts, IndieGala, OpiumPulses)
gets buttons the farm carries out itself:

```
🎉 WIN · IG IndieGala
Pirate Guy 2 New Land
The key is saved in the panel's Wins section.
[ Activate in ASF ] [ Key received ]
[ Wins ] [ IndieGala library ]
```

| Button | When it is there | What it does |
| --- | --- | --- |
| Activate in ASF («Активировать в ASF») | the win has a Steam key (IndieGala for now), ASF is set up (an IPC password is given, `~/asf/config/ASF.json` exists, another address is set or free Steam games are connected) and "Activate won keys immediately" is off | the same as the button in the Wins section: the key goes to ASF and the result comes as a separate "KEY ACTIVATED" (or similar) message |
| Key received («Ключ получен») | always | sets the win's status to "Key received"; for SteamGifts with "Mark as received on the site" on, the mark goes to the site too |

A pressed button with nothing left to do disappears: "Key received" once the
win is marked, both once the key is activated. Links stay.

- The buttons work only in the farm's chat; a press in another chat does
  nothing.
- A button carries neither the game's name nor the key, only a short random
  id of the win. It is kept with the win, so the buttons keep working after
  the farm restarts. If the win has already left the history, the bot answers
  that the button is out of date.
- Presses made while the farm was off are skipped, like commands.
- Without commands, win messages stay as before, with link buttons only:
  nobody would be there to take a press.

## If it does not work

| Problem | What to check |
| --- | --- |
| "Send test" shows an error from Telegram | `Unauthorized`: wrong token; `chat not found`: wrong chat ID, or you have not written to the bot |
| The bot is silent in a group | is the bot added to the group? A group ID starts with `-100…` |
| Commands get no reply | is "Control the farm with commands" on and saved? Is the farm running? Is the same token used somewhere else (for example, in another program with a webhook)? Telegram delivers messages to only one receiver |
| Messages arrive, but no summary | is "Send daily summary" («Присылать сводку за сутки») on? The hour is in the farm's time zone |
