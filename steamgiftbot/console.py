#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Everything the user sees on screen: the banner, colours, progress lines."""
import os
import sys

from steamgiftbot.logging_setup import configure, getLogger

try:
    from colorama import init, Fore
    init()
except ImportError:
    Fore = None

LOGO = ["    ______                   ______ _____    ___                      ",
        "   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \\___ ________ ___ ____",
        "  _\\ \\/ __/ -_) _ `/  ' \\  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/",
        " /___/\\__/\\__/\\_,_/_/_/_/  \\___/_/_/ \\__/ /_/   \\_,_/_/ /___/\\__/_/   "]

# The screen is wiped every so often so a long run does not scroll for ever.
LINES_BEFORE_CLEAR = 60

_printedLines = 0


def isInteractive():
    return (sys.stdin is not None and sys.stdin.isatty()
            and sys.stdout is not None and sys.stdout.isatty())


def startLogFile(writeFile, logDir=None):
    return configure(writeFile) if logDir is None else configure(writeFile, logDir)


def _maybeClearScreen():
    global _printedLines
    _printedLines += 1
    if _printedLines <= LINES_BEFORE_CLEAR:
        return
    _printedLines = 0
    # Only wipe a real terminal: doing this to a log file or to `docker logs`
    # would either throw escape codes around or spawn a useless subprocess.
    if isInteractive():
        os.system('cls' if os.name == 'nt' else 'clear')


def log(text, color="white"):
    _maybeClearScreen()
    getLogger().info(text.replace('\n', ' '))
    if Fore:
        print(getattr(Fore, color.upper()) + text + Fore.RESET)
    else:
        print(text)


def printBanner():
    for line in LOGO:
        log(line, "green")
    log("\nEnjoy using our product!", "white")
    log("Created by: github.com/PalmaLuv | palmaluv.live\n"
        "Stay tuner for further app updates", "red")
