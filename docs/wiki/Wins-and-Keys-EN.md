# Wins and keys

## How the farm learns about wins

| Site | How |
| --- | --- |
| SteamGifts | checks the [won giveaways](https://www.steamgifts.com/giveaways/won) page after every run |
| OpiumPulses | checks the [your keys](https://www.opiumpulses.com/user/giveawaykeys) page if "Track won keys" («Следить за выигранными ключами») is on |
| IndieGala | not tracked yet. Wins are visible on the site and in IndieGala's emails; you can mark them in the panel by hand |
| Free Steam games, GOG, itch.io | these are not wins: the games go straight into the library and are recorded in the entry history |

When there is a new win:

- a green banner appears on the Overview (Обзор);
- a counter appears next to Wins (Выигрыши) in the menu, and 🎉 in the
  browser tab;
- a message arrives on Telegram.

## The Wins section

The filter at the top: "New" («Новые»), "Key received" («Ключ получен»),
"Activated" («Активированы»), "All" («Все»).

| Column | What it contains |
| --- | --- |
| When, Site, Game (Когда, Площадка, Игра) | a link to the giveaway on the site |
| Key (Ключ) | if there is no key, a "Paste the key" («Вставьте ключ») field. If there is one, `•••••-•••••-•••••` with the "Show" («Показать»), "Copy" («Скопировать») and "Activate in ASF" («Активировать в ASF») buttons |
| Status (Статус) | "New" («Новый»), "Key received", "Activated" («Активирован») |

## Statuses

- **New**: nobody has marked the win yet. It stays as a banner on the
  Overview and is included in the reminder in the daily summary.
- **Key received**: you have taken the key from the site.
- **Activated**: the key has been activated on Steam.

The status is changed with the buttons on the banner or with the drop-down
list in the table. For SteamGifts you can turn on the "Mark as received on
the site" («Отмечать на сайте «получено»») setting: then marking a win in the
panel clicks the same button on the site (see
[SteamGifts](SteamGifts-EN.md#wins)).

## Activation through ArchiSteamFarm

1. Paste the key into the field next to the win and press "Save"
   («Сохранить»).
2. Press **Activate in ASF**. The farm sends the key to an ASF bot (the one
   chosen in the settings, or the first one online) and shows the result.
3. If the key was activated or the game was already in the library, the
   status becomes "Activated" by itself. The result also arrives on Telegram.

If "Activate won keys immediately" («Активировать выигранные ключи сразу») is
on in [Settings → ArchiSteamFarm](Farm-Settings-EN.md), step 2 happens
automatically as soon as the win has a key.

What Steam's responses mean is explained on the
[ArchiSteamFarm](ArchiSteamFarm-EN.md#activation-responses) page.

## Where keys are stored

In `botfarm-state.json` on the server, with each win (the `cdkey` field).
Only the owner has access to the file. In the panel the key stays hidden until
you press "Show".
