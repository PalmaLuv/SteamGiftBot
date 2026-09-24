#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Every setting the bot needs, gathered from three places.

Precedence, lowest first: config.ini -> environment -> command line.
Anything still unset is asked interactively, or reported as an error when the
bot runs unattended.
"""
import configparser
import getpass
import os
import re
import subprocess
import sys

from dataclasses import dataclass, fields
from pathlib import Path


# Where a user will look for config.ini, which is not where the code lives once
# the program is packed into an .exe: PyInstaller unpacks the modules into a
# temporary folder and deletes it on exit, so settings saved beside them would
# be gone by the next run.
def baseDir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    # A checkout or the Docker image: next to main.py, one level above the
    # package. Installed with pip, that would be site-packages, so the folder
    # the bot is started from is used instead.
    root = Path(__file__).resolve().parent.parent
    return root if (root / 'main.py').exists() else Path.cwd()


# How the user started the program, so advice names a command that works for
# them: the .exe, the installed script, python -m, or main.py from a checkout.
def launchCommand(argv0=None, frozen=None):
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    if frozen:
        return 'SteamGiftBot.exe'
    if argv0 is None:
        argv0 = sys.argv[0] if sys.argv else ''
    name = Path(argv0).name.lower()
    if name == '__main__.py':
        return 'python -m steamgiftbot'
    if name in ('steamgiftbot', 'steamgiftbot.exe', 'steamgiftbot-script.py'):
        return 'steamgiftbot'
    return 'python main.py'


def hint(flags):
    return f"{launchCommand()} {flags}"


BASE_DIR            = baseDir()
DEFAULT_CONFIG_PATH = BASE_DIR / 'config.ini'

ENV_PREFIX = 'STEAMGIFTBOT_'

GIFT_TYPES = ['All', 'WishList', 'Recommended', 'Copies', 'DLC', 'New']

# Settings the bot cannot start without. log_info and once have safe defaults.
REQUIRED = ('cookie', 'gift_type', 'pinned', 'min_points')

# Belong to a single run, so the settings menu never writes them to the file.
# A value put there by hand is still read, and still kept when the file is saved.
RUNTIME_ONLY = ('once', 'dry_run')

TRUE_WORDS  = ('1', 'yes', 'true', 'on', 'y')
FALSE_WORDS = ('0', 'no', 'false', 'off', 'n')


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    cookie      : str         = ''
    log_info    : bool | None = None
    gift_type   : str         = ''
    pinned      : bool | None = None
    min_points  : int | None  = None
    once        : bool        = False
    dry_run     : bool        = False
    points_wait : int | None  = None

    # Filters. Unset means 'do not filter on this'.
    max_cost    : int | None  = None
    max_entries : int | None  = None
    cards_only  : bool        = False
    blacklist   : tuple       = ()
    whitelist   : tuple       = ()
    # Your contributor level, from your SteamGifts profile. Unset means the bot
    # does not look at the level a giveaway asks for.
    contributor_level  : int | None = None
    skip_region_locked : bool       = False

    # Where to report the result of an unattended run.
    discord_webhook : str = ''
    telegram_token  : str = ''
    telegram_chat   : str = ''
    # Explicit off switch. Unset means 'on as soon as a token and a chat exist'.
    telegram_enabled : bool | None = None

    # Watch /giveaways/won and announce anything new.
    check_wins       : bool | None = None

    # Names of the required settings that are still empty.
    def missing(self):
        empty = []
        for name in REQUIRED:
            value = getattr(self, name)
            if value is None or value == '':
                empty.append(name)
        return empty


def toBool(value):
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == '':
        return None
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    raise ValueError(f"expected yes/no, got {value!r}")


def toInt(value):
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip()
    if text == '':
        return None
    number = int(text)
    if number < 0:
        raise ValueError("cannot be negative")
    return number


# Accepts 'wishlist' as happily as 'WishList'.
def toGiftType(value):
    if value is None or str(value).strip() == '':
        return ''
    text = str(value).strip().lower()
    for known in GIFT_TYPES:
        if known.lower() == text:
            return known
    raise ValueError(f"unknown type {value!r}, expected one of: {', '.join(GIFT_TYPES)}")


# Comma or newline separated, so config.ini can spread a long list over lines.
def toNames(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(value)
    parts = str(value).replace('\n', ',').split(',')
    return tuple(part.strip() for part in parts if part.strip())


# Quotes come along from JSON and shell habits, and configparser keeps them.
def toText(value):
    if value is None:
        return None
    text = str(value).strip()
    for quote in ('"', "'"):
        if len(text) > 1 and text.startswith(quote) and text.endswith(quote):
            text = text[1:-1].strip()
    return text


# 123456789:AAHxxxxxxxx... Checked because a token that is subtly wrong fails
# silently at the worst moment: you find out by never being told you won.
TOKEN_SHAPE = re.compile(r'^\d+:[A-Za-z0-9_-]{20,}$')

# A chat id is a number, negative for groups, or an @name for a public channel.
CHAT_SHAPE = re.compile(r'^(-?\d+|@[A-Za-z0-9_]+)$')


def explainBadValue(text, what):
    if '#' in text or ';' in text:
        return (f"does not look like {what}: it still has a comment attached. "
                "config.ini only understands comments on a line of their own")
    if any(character.isspace() for character in text):
        return f"does not look like {what}: it has a space in it"
    return (f"does not look like {what}. Copy it again, without quotes, "
            "and check nothing was cut off")


def toTelegramToken(value):
    text = toText(value)
    if not text:
        return text
    if not TOKEN_SHAPE.match(text):
        raise ValueError(explainBadValue(text, "a bot token (123456789:AAH...)"))
    return text


def toTelegramChat(value):
    text = toText(value)
    if not text:
        return text
    if not CHAT_SHAPE.match(text):
        raise ValueError(explainBadValue(text, "a chat id (987654321, or -100... "
                                               "for a group). Run "
                                               f"'{hint('--telegram-chat-id')}' "
                                               "to find yours"))
    return text


# Only Discord's own webhook address. The value is posted to as it is, so a
# typo or a pasted link to somewhere else must not become a request to it.
WEBHOOK_SHAPE = re.compile(
    r'^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+/?$')


def toDiscordWebhook(value):
    text = toText(value)
    if not text:
        return text
    if not WEBHOOK_SHAPE.match(text):
        raise ValueError(explainBadValue(
            text, "a Discord webhook (https://discord.com/api/webhooks/<id>/<token>)"))
    return text


CONVERTERS = {
    'cookie'    : toText,
    'log_info'  : toBool,
    'gift_type' : toGiftType,
    'pinned'    : toBool,
    'min_points': toInt,
    'once'      : toBool,
    'dry_run'   : toBool,
    'points_wait': toInt,

    'max_cost'  : toInt,
    'max_entries': toInt,
    'cards_only': toBool,
    'blacklist' : toNames,
    'whitelist' : toNames,
    'contributor_level' : toInt,
    'skip_region_locked': toBool,

    'discord_webhook': toDiscordWebhook,
    'telegram_token' : toTelegramToken,
    'telegram_chat'  : toTelegramChat,
    'telegram_enabled': toBool,
    'check_wins'     : toBool,
}


# Applies one layer of values on top of the settings, ignoring anything unset,
# and turns a bad value into a message naming both the source and the setting.
def applyLayer(settings, values, source):
    for name, raw in values.items():
        if raw is None:
            continue
        try:
            value = CONVERTERS[name](raw)
        except ValueError as error:
            raise SettingsError(f"{source}: '{name}' {error}") from error
        if value is None or value == '':
            continue
        setattr(settings, name, value)
    return settings


def readConfigFile(config_path):
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding='utf-8')
    except configparser.Error as error:
        raise SettingsError(f"{config_path}: {error}") from error
    section = parser['DEFAULT']
    return {field.name: section.get(field.name) for field in fields(Settings)}


# STEAMGIFTBOT_COOKIE_FILE=/run/secrets/cookie reads the value from that file,
# the way Docker and Kubernetes hand out secrets. A plain -e value shows up in
# 'docker inspect'; a mounted secret does not.
def readSecretFile(variable, path):
    try:
        return Path(path).read_text(encoding='utf-8').strip()
    except OSError as error:
        raise SettingsError(f"environment: {variable} points at {path}, "
                            f"which cannot be read: {error.strerror or error}") from error


def readEnvironment():
    values = {}
    for field in fields(Settings):
        name = ENV_PREFIX + field.name.upper()
        value = os.environ.get(name)
        if value is None and os.environ.get(name + '_FILE'):
            value = readSecretFile(name + '_FILE', os.environ[name + '_FILE'])
        values[field.name] = value
    return values


def readArguments(args):
    if args is None:
        return {}
    return {field.name: getattr(args, field.name, None) for field in fields(Settings)}


def load(config_path=DEFAULT_CONFIG_PATH, args=None):
    settings = Settings()
    applyLayer(settings, readConfigFile(config_path), str(config_path))
    applyLayer(settings, readEnvironment(), f"environment ({ENV_PREFIX}*)")
    applyLayer(settings, readArguments(args), "command line")
    return settings


# The file holds a live session cookie, so keep it to the owner. On Windows
# that means an ACL: drop the inherited entries and grant the current user
# alone. Returns False when the file could not be locked down.
def restrictToOwner(path, windows=None, runner=subprocess.run):
    windows = sys.platform == 'win32' if windows is None else windows
    if not windows:
        try:
            os.chmod(path, 0o600)
        except OSError:
            return False
        return True

    try:
        result = runner(['icacls', str(path), '/inheritance:r',
                         '/grant:r', f'{getpass.getuser()}:F'],
                        capture_output=True, check=False)
    except (OSError, KeyError):
        # KeyError: getpass found no user name to grant the file to.
        return False
    return result.returncode == 0


# The per run settings stay out of the file on purpose; see RUNTIME_ONLY.
# Returns whether the file ended up readable by its owner only.
def save(settings, config_path=DEFAULT_CONFIG_PATH):
    parser = configparser.ConfigParser()
    parser.read(config_path, encoding='utf-8')
    previous = {name: parser['DEFAULT'].get(name) for name in RUNTIME_ONLY}

    written = {
        'cookie'    : settings.cookie,
        'log_info'  : 'yes' if settings.log_info else 'no',
        'gift_type' : settings.gift_type,
        'pinned'    : 'yes' if settings.pinned else 'no',
        'min_points': str(settings.min_points),
        'cards_only': 'yes' if settings.cards_only else 'no',
        'skip_region_locked': 'yes' if settings.skip_region_locked else 'no',
        'blacklist' : ', '.join(settings.blacklist),
        'whitelist' : ', '.join(settings.whitelist),
        'discord_webhook': settings.discord_webhook,
        'telegram_token' : settings.telegram_token,
        'telegram_chat'  : settings.telegram_chat,
        'telegram_enabled': 'no' if settings.telegram_enabled is False else 'yes',
        'check_wins'     : 'no' if settings.check_wins is False else 'yes',
    }
    # An absent max_cost means 'no limit', which is not the same as zero.
    if settings.max_cost is not None:
        written['max_cost'] = str(settings.max_cost)
    if settings.max_entries is not None:
        written['max_entries'] = str(settings.max_entries)
    if settings.contributor_level is not None:
        written['contributor_level'] = str(settings.contributor_level)
    if settings.points_wait is not None:
        written['points_wait'] = str(settings.points_wait)

    parser['DEFAULT'] = written
    for name, value in previous.items():
        if value is not None:
            parser['DEFAULT'][name] = value

    config_path = Path(config_path)
    with config_path.open('w', encoding='utf-8') as configFile:
        parser.write(configFile)

    return restrictToOwner(config_path)
