# Server and service

To keep the farm running all the time and have it start by itself after a
reboot, on Linux it is run as a systemd service.

## systemd service

The repository contains a template,
[`deploy/botfarm.service`](../../deploy/botfarm.service).

1. Copy it next to the original under your own name. Git ignores
   `*.local.service` files, so your personal addresses and paths do not end up
   in the repository:

   ```bash
   cp deploy/botfarm.service deploy/botfarm.local.service
   ```

2. In the copy, replace:
   - `YOUR_USER` with the user the farm will run as (not root);
   - `/opt/SteamGiftBot` with the path to the project (two places);
   - `192.168.1.10` with your own addresses, for example `192.168.1.10,100.64.0.5`.
3. Set the panel password if you have not done so yet:
   `env/bin/python -m steamgiftbot.farm --set-password`.
4. Install and start the service:

   ```bash
   sudo cp deploy/botfarm.local.service /etc/systemd/system/botfarm.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now botfarm
   ```

### Managing it

```bash
systemctl status botfarm                 # is it running
sudo systemctl restart botfarm           # after updating the code
sudo systemctl stop botfarm              # stop it
journalctl -u botfarm -f                 # live log
journalctl -u botfarm --since "-1 hour"  # log for the last hour
```

Settings changed in the panel do not need a restart. A restart is only needed
after `git pull`. If the farm crashes, systemd brings it back up after 30
seconds (`Restart=always`).

If the command-line bot used to run as a separate service (for example,
`steamgiftbot.service`), turn it off: `sudo systemctl disable --now
steamgiftbot`. The farm runs SteamGifts itself, and two processes on the same
account will get in each other's way.

## Firewall

If the panel opens on the server itself (`curl http://address:8092/`) but not
from other devices, the port is blocked by a firewall.

**ufw (Ubuntu):**

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8092 proto tcp comment 'BotFarm panel'
sudo ufw allow in on tailscale0          # if you use Tailscale
```

You can tell that requests are being blocked from `/var/log/ufw.log`: it will
have `[UFW BLOCK] … DPT=8092` lines.

**firewalld (Fedora, CentOS):**

```bash
sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=192.168.1.0/24 port port=8092 protocol=tcp accept'
sudo firewall-cmd --reload
```

**Windows:** "Windows Defender Firewall" → "Advanced settings" → "Inbound
Rules" → a new rule for TCP port 8092, "Private" profile.

## Several addresses

`--host` accepts several addresses separated by commas, and the farm opens a
separate copy of the panel on each. If an address does not exist yet
(Tailscale comes up later than the network), the farm retries every 15
seconds and mentions it in the log once.

## Backups

[`scripts/backup-farm.sh`](../../scripts/backup-farm.sh) packs `farm.json`,
`config.ini` and the state files into `backups/botfarm-YYYYMMDD-HHMMSS.tar.gz`.
The archives are readable only by the owner, and the last 14 are kept (the
`KEEP` variable).

A daily run through cron (`crontab -e`):

```
27 4 * * * /opt/SteamGiftBot/scripts/backup-farm.sh
```

> The archives contain live cookies and tokens. Do not publish them and do not
> keep them in shared folders.

**Restoring:** stop the service, unpack the archive you need into the project
folder (`tar -xzf backups/botfarm-….tar.gz`) and start the service again.

## Updating

```bash
cd /opt/SteamGiftBot
git pull
env/bin/pip install -r requirements.txt
sudo systemctl restart botfarm
```

It is a good idea to make a backup before updating: `scripts/backup-farm.sh`.
