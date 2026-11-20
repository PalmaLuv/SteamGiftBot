# ArchiSteamFarm

[ArchiSteamFarm](https://github.com/JustArchiNET/ArchiSteamFarm) (ASF) is a
separate program that keeps your Steam accounts online. The farm talks to it
over IPC, ASF's built-in API, in order to:

- **activate won keys** on Steam (the Wins (Выигрыши) section);
- **add free Steam games to the library** (the
  [Free Steam games](Free-Steam-Games-EN.md) site).

The farm does not manage ASF and does not change its settings.

## Setup

### ASF on the same server

If ASF lives in `~/asf`, listens on `http://127.0.0.1:1242` and has
`IPCPassword` set in `~/asf/config/ASF.json`, there is nothing to fill in: the
farm reads the password by itself. Open **Settings → ArchiSteamFarm
(Настройки → ArchiSteamFarm)** and press **Check ASF (Проверить ASF)**.

### ASF on another computer

1. Set `IPCPassword` in that ASF's `config/ASF.json`.
2. Allow access to IPC from more than the local machine. In
   `config/IPC.config` set the address, for example `"Url": "http://*:1242"`,
   and open the port in the firewall for your own network only.
3. In **Settings → ArchiSteamFarm**, enter the "IPC address" («Адрес IPC»),
   for example `http://192.168.1.20:1242`, and the "IPC password" («Пароль
   IPC»). Press **Check ASF**.

| Setting | What it does |
| --- | --- |
| IPC address | where to find ASF |
| IPC password | `IPCPassword`. If empty, the farm takes it from `~/asf/config/ASF.json` |
| Bot for keys (Бот для ключей) | the name of the bot to activate keys on. If empty, the first bot online. A key can only be activated once, so a single bot is always chosen |
| Activate won keys immediately (Активировать выигранные ключи сразу) | as soon as a win has a key, the farm sends it to ASF |

Free games are added to **all** ASF bots (or only to the bots you specify).

## Activation responses

| Response | What it means | What the farm does |
| --- | --- | --- |
| activated | the key worked, the game is in the library | win status → "Activated" («Активирован») |
| already in the library | you already had the game | status → "Activated" |
| not for your region | the key is for another region | leaves the win as it is |
| invalid key | a typo, or it is not a Steam key | leaves it as it is |
| key already activated by someone | the key has been used | leaves it as it is |
| the base game is required first | it is a DLC | leaves it as it is |
| not a game key | a wallet code or a gift | leaves it as it is |
| Steam asks to wait | too many activations in an hour | try again later |
| ASF bot offline / Steam gave no answer | ASF or Steam is unavailable | try again later |

The result is written under the key in the Wins section and arrives on
Telegram.

## Connection errors

| Message | What to do |
| --- | --- |
| ASF is unavailable at … (ASF недоступен по адресу …) | ASF is not running, the address is wrong or the port is closed |
| ASF did not accept the IPC password (ASF не принял пароль IPC) | the password does not match `IPCPassword` |
| ASF does not let this address in (ASF не пускает этот адрес) | `IPCPassword` is not set in ASF, and the request does not come from the local machine |
| ASF has no bots online (в ASF нет ни одного бота в сети) | the bots are turned off or waiting for a Steam Guard code; check the ASF web interface |
