# First farm run

Here you start the farm by hand to check that everything works. How to make it
start on its own after a reboot is covered in
[Server and service](Server-and-Service-EN.md).

## 1. Set the panel password

```bash
env/bin/python -m steamgiftbot.farm --set-password
```

The password must be at least 6 characters long. `farm.json` stores only its
hash (PBKDF2). If you forget the password, run the same command again.

## 2. Find the computer's network address

The panel should listen on an address in your home network, not on every
address at once.

```bash
ip -4 addr show | grep inet        # Linux: look for 192.168.x.x or 10.x.x.x
ipconfig                           # Windows: "IPv4 Address"
tailscale ip -4                    # if Tailscale is installed: a 100.x.x.x address
```

## 3. Start the farm

```bash
env/bin/python -m steamgiftbot.farm --host 192.168.1.10
```

| Option | What it does |
| --- | --- |
| `--host` | which address the panel runs on. Several can be given, separated by commas: `192.168.1.10,100.64.0.5`. If an address does not exist yet (Tailscale during boot, for example), the farm retries every 15 seconds |
| `--port` | panel port, `8092` by default |
| `--data` | folder for `farm.json`, the history and the logs; the project folder by default |
| `--config` | path to `config.ini`; by default it is in the data folder |
| `--no-autostart` | start only the panel; all sites stay stopped |
| `--set-password` | set the panel password and exit |

Instead of options you can set the environment variables `BOTFARM_HOST`,
`BOTFARM_PORT`, `BOTFARM_DATA` and `BOTFARM_PASSWORD`.

> **Do not use `--host 0.0.0.0` on a computer with a public IP.** The panel
> holds your accounts' cookies and has no business being on the internet. To
> reach the panel away from home, use Tailscale; see
> [Panel on your phone](Mobile-Panel-EN.md).

## 4. Open the panel

In a browser on any device in the same network, open
`http://192.168.1.10:8092/` and sign in with the password from step 1. The
browser stays signed in for 30 days.

If the page does not open, the port is most likely blocked by a firewall. How
to open it is described in [Server and service](Server-and-Service-EN.md#firewall).

## 5. Connect your first site

**Sites (Площадки) → Add site (Добавить площадку) → Connect (Подключить)**.
The connection wizard shows step by step what to copy from the browser. See
[Connecting sites](Connecting-Sites-EN.md) for details.

If you used the command-line bot before, SteamGifts is already connected: the
farm reads the same `config.ini`.

## 6. Check what the farm is going to do

On the site's page, open the **Preview (Что возьмёт)** tab. It is a trial run:
the farm shows the current giveaways and what it would do with each one,
without spending anything.

## 7. Remaining settings

In the **Settings (Настройки)** section, check:

- **General → Time zone (Общее → Часовой пояс).** Working hours and the
  summary time follow it.
- **Telegram.** The farm will send wins and errors; see [Telegram](Telegram-EN.md).
- **Steam library (Библиотека Steam).** So the farm does not enter giveaways
  for games you already own.
- **Start with the farm (Что запускать вместе с фермой).** Tick the sites
  that should start on their own.

That's it, the farm is running. When you are ready to leave it on for good,
move on to [Server and service](Server-and-Service-EN.md).
