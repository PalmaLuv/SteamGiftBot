"""Ways to support the project, in one place: the panel's settings, the line
under a win and Telegram's /donate all read them from here.

The farm asks rarely and only when it has just been useful: a line under a
win, at most once a week, and never once the user has turned it off."""
import time

TON = 'UQBhyAtIaZxHiiLsLjmJtnG8sFmNiG77k2xkWfgr0xka7X2J'

LINKS = [
    ('GitHub Sponsors', 'https://github.com/sponsors/palmaluv'),
    ('Buy Me a Coffee', 'https://www.buymeacoffee.com/palmaluv'),
    # Opens the transfer in Tonkeeper or any TON wallet that handles the link.
    ('TON', f'https://app.tonkeeper.com/transfer/{TON}'),
]

# The project page's section with every way to support, in each language.
PAGE = {'ru': 'https://palmaluv.github.io/SteamGiftBot/#support',
        'uk': 'https://palmaluv.github.io/SteamGiftBot/uk/#support',
        'en': 'https://palmaluv.github.io/SteamGiftBot/en/#support'}

# How often the line under a win may appear in Telegram.
ASK_EVERY = 7 * 86400


def info(lang='ru'):
    """What the panel shows in Settings → About."""
    return {'links': [{'title': title, 'url': url} for title, url in LINKS], 'ton': TON,
            'page': page(lang)}


def page(lang):
    return PAGE.get(lang, PAGE['en'])


def due(enabled, asked, now=None):
    """True when the line under a win may go out: the reminder is on (the
    panel's 'support' setting) and it last went out over a week ago."""
    if not enabled:
        return False
    return (time.time() if now is None else now) - float(asked or 0) >= ASK_EVERY
