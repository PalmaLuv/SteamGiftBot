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
| ✅ KEY ACTIVATED / ⏳ WILL RETRY LATER / ⚠️ KEY REJECTED | the ASF activation result | Wins |
| 📊 DAILY SUMMARY | every day at the chosen hour | Open the panel, Wins |

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
ones. The sending time is chosen in the "Summary hour" («Час отправки
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

## If it does not work

| Problem | What to check |
| --- | --- |
| "Send test" shows an error from Telegram | `Unauthorized`: wrong token; `chat not found`: wrong chat ID, or you have not written to the bot |
| The bot is silent in a group | is the bot added to the group? A group ID starts with `-100…` |
| Commands get no reply | is "Control the farm with commands" on and saved? Is the farm running? Is the same token used somewhere else (for example, in another program with a webhook)? Telegram delivers messages to only one receiver |
| Messages arrive, but no summary | is "Send daily summary" («Присылать сводку за сутки») on? The hour is in the farm's time zone |
