# Security

The farm holds your accounts' cookies, the Telegram token and the ASF
password. Below is how the farm protects them and what you should do
yourself.

## What the farm does

**Signing in to the panel**

- `farm.json` stores only the password hash: PBKDF2-SHA256, 200,000
  iterations, with a random salt.
- After signing in, the browser gets a 30-day session cookie with the
  `HttpOnly` and `SameSite=Strict` flags. The cookie is signed with a key that
  changes when you change the password and when you use "Sign out on all other
  devices" («Выйти на всех других устройствах»).
- After 10 wrong passwords within 10 minutes from one address, signing in is
  blocked for 10 minutes. On top of that, every failed attempt waits one
  second.

**Requests to the panel**

- Every POST must carry the `X-Requested-With: BotFarm` header. A form on
  someone else's site cannot send it, so nobody can quietly press a button in
  your panel through your browser.
- The page is served with a Content-Security-Policy that allows scripts,
  styles and images to load only from the farm itself, and with framing
  forbidden (`X-Frame-Options: DENY`). API responses are not cached.

**Secrets**

- The API never returns saved cookies, tokens or passwords, only a "set"
  flag.
- From a pasted cURL, only the cookies and the User-Agent are saved.
- `farm.json` and `botfarm-state.json` are created with `600` permissions:
  only the owner can read them.
- Backups from `scripts/backup-farm.sh` are created with the same
  permissions.

**Network**

- The farm listens only on the addresses from `--host`, not on every address
  at once.

## What you should do

- **Do not expose the panel to the internet.** Do not use `--host 0.0.0.0` on
  a computer with a public IP, and do not forward the port on your router. For
  access away from home there is
  [Tailscale](Mobile-Panel-EN.md#away-from-home-tailscale).
- **Pick a separate panel password**, not the one you use for Steam or email.
- **Lock down `config.ini`:** `chmod 600 config.ini`. It holds the SteamGifts
  cookie and the Telegram token.
- **Do not publish** `farm.json`, `config.ini`, `botfarm-state.json`, the
  `backups/` folder or HAR files saved from the browser. The first three are
  already in `.gitignore`.
- **Do not post screenshots** of the developer tools with cookies visible.
- **If your cookies leak**, sign out of your account on the site: that
  invalidates them. Then [connect](Connecting-Sites-EN.md) the site again.
- **If you lose your phone**, press **Settings → Security → Sign out on all
  other devices (Настройки → Безопасность → Выйти на всех других
  устройствах)**.

## Site rules

Automated giveaway entry is a grey area: some sites forbid it in their rules.
The farm behaves like a careful user: it pauses between entries, backs off
when a site asks it to slow down, looks through a limited number of pages by
default, and does not get around captchas or checks. But responsibility for
the account stays with you. Read each site's rules, and on SteamGifts mark
your wins as received and activate the keys. For SteamGifts, whose rules do
not allow automatic entry, the connect wizard shows a separate warning (more
in [SteamGifts](SteamGifts-EN.md#risk-to-the-account)).
