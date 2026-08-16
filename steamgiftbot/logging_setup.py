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

from datetime import datetime
from pathlib import Path

LOGGER_NAME     = 'steamgiftbot'
FILENAME_FORMAT = 'log-%d.%m.%Y-%H.%M.%S.log'
LOG_FORMAT      = '[%(levelname)s:%(asctime)s] %(message)s'

# A run producing more than this rolls over instead of growing without end.
MAX_BYTES    = 5 * 1024 * 1024
BACKUP_COUNT = 3


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

    handler = logging.handlers.RotatingFileHandler(
        logPath, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding='utf-8')
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    return logPath
