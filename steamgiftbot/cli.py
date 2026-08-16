#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Command line entry point: parse flags, settle the settings, start the bot."""
import argparse
import sys

from pathlib import Path

from steamgiftbot import __version__, notify
from steamgiftbot import settings as steamSettings
from steamgiftbot import ui
from steamgiftbot.console import isInteractive, log, printBanner, startLogFile

EXIT_OK       = 0
EXIT_FAILED   = 1
EXIT_BADSETUP = 2


def buildParser():
    parser = argparse.ArgumentParser(
        prog='SteamGiftBot',
        description="Enter SteamGifts giveaways automatically. "
                    "With a complete config.ini the bot starts without asking anything.",
        epilog=f"Every setting can also come from the environment, "
               f"for example {steamSettings.ENV_PREFIX}COOKIE.")

    parser.add_argument('--version', action='version',
                        version=f"SteamGiftBot {__version__}")
    parser.add_argument('--config', default=steamSettings.DEFAULT_CONFIG_PATH,
                        help="path to config.ini (default: next to this script)")
    parser.add_argument('--setup', action='store_true',
                        help="open the settings menu instead of starting the bot")
    parser.add_argument('--no-input', dest='no_input', action='store_true',
                        help="never ask questions; fail if a setting is missing")

    parser.add_argument('--cookie', help="PHPSESSID cookie from steamgifts.com")
    parser.add_argument('--type', dest='gift_type', metavar='TYPE',
                        help="giveaway filter: " + ', '.join(steamSettings.GIFT_TYPES))
    parser.add_argument('--min-points', dest='min_points', metavar='N',
                        help="stop entering once the balance drops below N")

    parser.add_argument('--pinned', dest='pinned', action='store_true', default=None,
                        help="also enter pinned giveaways")
    parser.add_argument('--no-pinned', dest='pinned', action='store_false',
                        help="skip pinned giveaways")

    parser.add_argument('--log', dest='log_info', action='store_true', default=None,
                        help="write a log file for this run")
    parser.add_argument('--no-log', dest='log_info', action='store_false',
                        help="do not write a log file")

    parser.add_argument('--once', dest='once', action='store_true', default=None,
                        help="make a single pass and exit instead of sleeping for points; "
                             "meant for cron / Task Scheduler")
    parser.add_argument('--dry-run', dest='dry_run', action='store_true', default=None,
                        help="report what would be entered without spending a point")
    parser.add_argument('--points-wait', dest='points_wait', metavar='SECONDS',
                        help="how long to sleep when the balance runs out (default 900)")

    picking = parser.add_argument_group('picking giveaways')
    picking.add_argument('--max-cost', dest='max_cost', metavar='N',
                         help="skip giveaways that cost more than N points")
    picking.add_argument('--max-entries', dest='max_entries', metavar='N',
                         help=f"skip giveaways more than N people already entered "
                              f"(recommended {ui.RECOMMENDED_MAX_ENTRIES})")
    picking.add_argument('--level', dest='contributor_level', metavar='N',
                         help="your contributor level; giveaways asking for more are skipped")
    picking.add_argument('--skip-region-locked', dest='skip_region_locked',
                         action='store_true', default=None,
                         help="skip giveaways restricted to particular regions")
    picking.add_argument('--cards-only', dest='cards_only', action='store_true', default=None,
                         help="only enter games that have Steam trading cards")
    picking.add_argument('--blacklist', metavar='WORDS',
                         help="comma separated words; a giveaway whose name contains "
                              "one of them is skipped")
    picking.add_argument('--whitelist', metavar='WORDS',
                         help="comma separated words; only giveaways whose name contains "
                              "one of them are entered")

    telling = parser.add_argument_group('reporting the result')
    telling.add_argument('--discord-webhook', dest='discord_webhook', metavar='URL',
                         help="post the run summary to this Discord webhook")
    telling.add_argument('--telegram-token', dest='telegram_token', metavar='TOKEN',
                         help="Telegram bot token for the run summary")
    telling.add_argument('--telegram-chat', dest='telegram_chat', metavar='CHAT',
                         help="Telegram chat id to send the run summary to")
    telling.add_argument('--no-telegram', dest='telegram_enabled', action='store_false',
                         default=None, help="switch Telegram off without removing the token")
    telling.add_argument('--no-check-wins', dest='check_wins', action='store_false',
                         default=None, help="do not watch the won giveaways page")
    telling.add_argument('--notify-test', dest='notify_test', action='store_true',
                         help="send a test message and exit, to check the setup")
    telling.add_argument('--telegram-chat-id', dest='telegram_chat_id', action='store_true',
                         help="list the chat ids that have written to your bot, and exit")
    return parser


# There is no way to look your own chat id up: Telegram only reveals it once the
# bot has been spoken to. So this reads whoever has written recently and prints
# the line to paste into config.ini.
def showTelegramChats(config):
    if not config.telegram_token:
        log("Set telegram_token first: get one from @BotFather in Telegram, "
            "then run this again.", "red")
        return EXIT_BADSETUP

    try:
        chats = notify.findChats(config.telegram_token)
    except notify.NotifyError as error:
        log(str(error), "red")
        return EXIT_FAILED

    if not chats:
        log("Nobody has written to your bot yet, so Telegram will not say who you are.\n"
            "Open the bot in Telegram, send it any message (/start will do), "
            "then run this again.\n"
            "For a group, add the bot to it and write something there.", "yellow")
        return EXIT_FAILED

    log("Chats that have written to your bot:", "white")
    for chat in chats:
        log("  " + notify.describeChat(chat), "green")

    if len(chats) == 1:
        log(f"\nPut this in your config.ini:\n  telegram_chat = {chats[0].get('id')}", "white")
    else:
        log("\nPut the one you want in your config.ini as 'telegram_chat = <id>'.", "white")
    return EXIT_OK


# Says which half of the setup is absent. Naming both when one is already there
# reads as 'your token was rejected', and sends people off replacing a token
# that was fine.
def missingNotifySetting(config):
    if config.telegram_token and config.telegram_chat:
        # Both halves are there, so the only way to reach this is the off switch.
        return ("Telegram is fully set up but switched off. "
                "Set telegram_enabled = yes in your config.ini, "
                "or drop the --no-telegram flag.")
    if config.telegram_token:
        return ("The Telegram token is set but telegram_chat is not, so there is "
                "nowhere to send to.\nWrite to your bot, then run: "
                "python main.py --telegram-chat-id")
    if config.telegram_chat:
        return ("telegram_chat is set but telegram_token is not.\n"
                "Get a token from @BotFather in Telegram.")
    return ("Nothing to notify: set telegram_token and telegram_chat, "
            "or discord_webhook, in your config.ini.")


# Sends one message so a fresh Telegram or Discord setup can be checked without
# waiting for a giveaway to be won.
def sendTestNotification(config):
    if not notify.isConfigured(config):
        log(missingNotifySetting(config), "red")
        return EXIT_BADSETUP

    problems = notify.send(config, "SteamGiftBot is set up correctly. "
                                   "This is what a win will look like.")
    if problems:
        for problem in problems:
            log(f"Could not deliver the test message. {problem}", "red")
        return EXIT_FAILED

    log("Test message sent. Check your chat.", "green")
    return EXIT_OK


# Asks only for what is still missing, then remembers the answers.
def askMissing(config, configPath):
    if not config.cookie:
        config.cookie = ui.askCookie()
    if config.log_info is None:
        config.log_info = ui.askLog()
    if not config.gift_type:
        config.gift_type = ui.askGiftType()
    if config.pinned is None:
        config.pinned = ui.askPinned()
    if config.min_points is None:
        config.min_points = ui.askMinPoints()
    steamSettings.save(config, configPath)
    return config


# Editing the script settings *.ini file
def editConfig(config, configPath):
    while True:
        choice = ui.askEditChoice()
        if choice == 'Cookie':
            config.cookie = ui.askCookie()
        elif choice == 'log info':
            config.log_info = ui.askLog()
        elif choice == 'Gift type':
            config.gift_type = ui.askGiftType()
        elif choice == 'Pinned games':
            config.pinned = ui.askPinned()
        elif choice == 'Minimum points':
            config.min_points = ui.askMinPoints()
        elif choice == 'Maximum entries':
            config.max_entries = ui.askMaxEntries()
        elif choice == 'Contributor level':
            config.contributor_level = ui.askContributorLevel()
        elif choice == 'exit':
            break
        if config.log_info is not None and not config.missing():
            steamSettings.save(config, configPath)
    return config


def run(argv=None):
    from steamgiftbot.bot import SteamGift
    from steamgiftbot.state import defaultPath

    args = buildParser().parse_args(argv)
    printBanner()

    try:
        config = steamSettings.load(args.config, args)
    except steamSettings.SettingsError as error:
        log(str(error), "red")
        return EXIT_BADSETUP

    # Neither of these needs a cookie or a single giveaway: they are the steps
    # you take while still setting the notifications up.
    if args.telegram_chat_id:
        return showTelegramChats(config)

    if args.notify_test:
        return sendTestNotification(config)

    canAsk = not args.no_input and isInteractive()

    if args.setup:
        if not canAsk:
            log("--setup needs a terminal to ask questions in.", "red")
            return EXIT_BADSETUP
        config = askMissing(config, args.config)
        config = editConfig(config, args.config)
    elif config.missing():
        if not canAsk:
            # Unattended run with an incomplete setup: say exactly what is absent.
            log("Missing settings: " + ', '.join(config.missing())
                + f"\nSet them in {args.config}, in {steamSettings.ENV_PREFIX}* "
                  "environment variables, or as command line flags.", "red")
            return EXIT_BADSETUP
        config = askMissing(config, args.config)

    if config.log_info is None:
        config.log_info = False

    # Logs, config and state all live together, so a packed .exe started from
    # somewhere else does not scatter them across the disk.
    beside = Path(args.config).resolve().parent
    startLogFile(config.log_info, beside / 'log')
    return SteamGift(config, statePath=defaultPath(args.config)).start()


def main(argv=None):
    try:
        return run(argv)
    except KeyboardInterrupt:
        # Ctrl+C during the setup questions, before the bot itself is running.
        log("\nStopped by user. Bye!", "white")
        return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
