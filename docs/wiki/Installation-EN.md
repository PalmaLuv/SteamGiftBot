# Installation

The command-line bot and the farm are installed the same way.

## Requirements

- **Python 3.10 or newer.** Check the version with `python3 --version`.
- **Git**, to download the project and update it later.
- **For the farm**, a computer or server that stays on: Linux (best), Windows
  or macOS. The weakest mini PC is enough: the farm spends almost all of its
  time waiting.

## Linux and macOS

```bash
git clone https://github.com/PalmaLuv/SteamGiftBot.git
cd SteamGiftBot
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

`env` is a virtual environment: dependencies go into it, not into the system.
From then on, run every command either after `source env/bin/activate` or
directly through `env/bin/python`, for example `env/bin/python -m steamgiftbot.farm`.

## Windows

```powershell
git clone https://github.com/PalmaLuv/SteamGiftBot.git
cd SteamGiftBot
py -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

If you only need SteamGifts, you can skip installation entirely and download a
ready-made `SteamGiftBot.exe` from the [releases](https://github.com/PalmaLuv/SteamGiftBot/releases/latest).
See [Command-line bot](Command-Line-Bot-EN.md) for details.

## Docker

The `ghcr.io/palmaluv/steamgiftbot` image runs the command-line bot:

```bash
docker run --rm -e STEAMGIFTBOT_COOKIE=your_PHPSESSID ghcr.io/palmaluv/steamgiftbot
```

The farm can run in Docker too if you override the command. The `--data`
option moves `farm.json`, `config.ini`, the history and the logs into a
separate folder. Mount it as a volume, or everything disappears together with
the container:

```bash
docker run --rm -it -v botfarm:/data --entrypoint python ghcr.io/palmaluv/steamgiftbot \
  -m steamgiftbot.farm --data /data --set-password

docker run -d --name botfarm --restart unless-stopped \
  -p 192.168.1.10:8092:8092 -v botfarm:/data \
  --entrypoint python ghcr.io/palmaluv/steamgiftbot \
  -m steamgiftbot.farm --data /data --host 0.0.0.0
```

The first command sets the panel password once; the second starts the farm.

> Listening on `0.0.0.0` inside the container is fine: only `-p` lets the port
> out. Put your network address in `-p` (`192.168.1.10:8092:8092`), not just a
> port, otherwise the panel becomes reachable on every address of the computer.

Instead of `--data` you can set the `BOTFARM_DATA` environment variable. The
password can be passed in `BOTFARM_PASSWORD`; then `--set-password` asks
nothing.

## Updating

```bash
cd SteamGiftBot
git pull
env/bin/pip install -r requirements.txt
sudo systemctl restart botfarm      # if the farm runs as a service
```

Settings, cookies and history live in `farm.json`, `config.ini` and
`botfarm-state.json`. These files are not part of the repository, so
`git pull` does not touch them.

## Next

- [First farm run](First-Farm-Run-EN.md)
- [Server and service](Server-and-Service-EN.md): autostart, firewall, Tailscale
