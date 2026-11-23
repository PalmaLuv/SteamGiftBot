#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""File logging, on top of the standard library instead of a hand rolled one."""
import logging
import logging.handlers
import os
import re
import time

from datetime import datetime
from pathlib import Path

LOGGER_NAME     = 'steamgiftbot'
FILENAME_FORMAT = 'log-%d.%m.%Y-%H.%M.%S.log'
LOG_FORMAT      = '[%(levelname)s:%(asctime)s] %(message)s'

# A run producing more than this rolls over instead of growing without end.
MAX_BYTES    = 5 * 1024 * 1024
BACKUP_COUNT = 3


# Files written by the bots hold logged-in pages and the odd secret in an
# error text: only the owner may read them.
PRIVATE_MODE = 0o600

# Secrets that ride in URLs: requests puts the whole URL, query string and all,
# into its error texts ('... for url: https://api.steampowered.com/...?key=…').
# A query value whose name says key, token, secret, password, auth, session
# or signature is masked, and so is a Telegram bot token in the URL's path.
SECRET_QUERY = re.compile(
    r'([?&;](?:[\w.\-]*?)(?:key|token|secret|passw(?:or)?d|auth|session|sig(?:nature)?)'
    r'(?:_?id)?=)[^&\s#\'"<>]+', re.IGNORECASE)
BOT_TOKEN    = re.compile(r'(/bot)\d{5,}:[\w-]{20,}')
MASK         = '***'


def redactSecrets(text):
    if not text:
        return text
    text = SECRET_QUERY.sub(lambda found: found.group(1) + MASK, str(text))
    return BOT_TOKEN.sub(lambda found: found.group(1) + MASK, text)


class RedactFilter(logging.Filter):
    """Masks secrets in a record before any handler writes it. Put on handlers,
    not loggers: a logger's filter never sees the records its children pass up."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:
            return True
        clean = redactSecrets(message)
        if clean != message:
            record.msg, record.args = clean, None
        if record.exc_info and not record.exc_text:
            # The formatter reuses exc_text, so the traceback is masked too.
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redactSecrets(record.exc_text)
        if record.stack_info:
            record.stack_info = redactSecrets(record.stack_info)
        return True


# Creates the file owner-only, or takes the other users' access away from one
# already there. Best effort: a file system without modes (FAT, Windows)
# simply keeps what it has.
def makePrivate(path):
    path = Path(path)
    try:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, PRIVATE_MODE))
        os.chmod(path, PRIVATE_MODE)
    except OSError:
        pass
    return path


def writePrivate(path, text, encoding='utf-8'):
    makePrivate(path)
    Path(path).write_text(text, encoding=encoding)


class PrivateRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating log whose file, and every one it rolls over to, is 0600."""

    def _open(self):
        makePrivate(self.baseFilename)
        return super()._open()


def privateLogHandler(path, **options):
    handler = PrivateRotatingFileHandler(path, **options)
    handler.addFilter(RedactFilter())
    return handler


# Owner-only for what is already on disk: the logs and debug pages written
# before files were created private.
def tightenFiles(folder, patterns):
    folder = Path(folder)
    if not folder.is_dir():
        return 0
    fixed = 0
    for pattern in patterns:
        for path in folder.glob(pattern):
            try:
                if path.is_file() and path.stat().st_mode & 0o077:
                    os.chmod(path, PRIVATE_MODE)
                    fixed += 1
            except OSError:
                continue
    return fixed


LOG_PATTERNS = ('botfarm.log', 'botfarm.log.*', 'log-*.log', 'log-*.log.*')
RUN_LOG      = re.compile(r'^log-.+\.log(?:\.\d+)?$')


# The command line bot leaves a log file per start, hundreds of them over the
# months. Those not written to for `days` go; the farm's own botfarm.log and
# its rotations never do. Returns how many were deleted.
def pruneRunLogs(logDir, days=30, now=None):
    logDir = Path(logDir)
    if not logDir.is_dir():
        return 0
    cutoff = (time.time() if now is None else now) - days * 86400
    removed = 0
    for path in logDir.glob('log-*.log*'):
        if not RUN_LOG.match(path.name):
            continue
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def getLogger():
    return logging.getLogger(LOGGER_NAME)


# Attaches a log file for this run, or a NullHandler when logging is off.
# Returns the path of the file that was created, or None.
def configure(writeFile, logDir='log'):
    logger = getLogger()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    if not writeFile:
        # Without a handler the logger would fall back to lastResort and print
        # every message to stderr a second time.
        logger.addHandler(logging.NullHandler())
        return None

    logDir = Path(logDir)
    logDir.mkdir(parents=True, exist_ok=True)
    logPath = logDir / datetime.now().strftime(FILENAME_FORMAT)

    handler = privateLogHandler(logPath, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                encoding='utf-8')
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    return logPath
