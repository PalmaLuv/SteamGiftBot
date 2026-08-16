#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""The interactive questions asked when a setting is still unknown."""
import os

from InquirerPy import prompt
from prompt_toolkit import document as doc
from prompt_toolkit.validation import ValidationError, Validator

from steamgiftbot.settings import GIFT_TYPES

# Ctrl+V support is a Windows nicety. On Linux 'keyboard' needs root and a
# readable /dev/input, which a container does not have, so the bot must keep
# working without it.
try:
    import keyboard
    import clipboard
    PASTE_HOTKEY = os.name == 'nt'
except Exception:
    PASTE_HOTKEY = False

POINTS_MESSAGE = 'Value should be a number of 0 or greater'

# Measured over 126 live giveaways: the median had 554 entries, and a limit of
# 500 keeps a little under half of them while halving the competition. Lower
# than 250 leaves so few giveaways that the bot mostly sits on unspent points.
RECOMMENDED_MAX_ENTRIES = 500
LOWEST_SENSIBLE_ENTRIES = 250

ENTRIES_MESSAGE = 'Value should be a number of 1 or greater, or empty for no limit'


class PointValidator(Validator):
    def validate(self, document: doc.Document):
        try:
            value = int(document.text)
        except ValueError:
            # ValidationError, not Exception: prompt_toolkit only catches the
            # former and re-asks instead of crashing the whole program.
            raise ValidationError(message=POINTS_MESSAGE,
                                  cursor_position=len(document.text)) from None

        if value < 0:
            raise ValidationError(message=POINTS_MESSAGE,
                                  cursor_position=len(document.text))


def ask(type, name, msg, choices=None, validate=None, default=None):
    question = {'type': type, 'name': name, 'message': msg}
    if choices:
        question['choices'] = choices
    if validate is not None:
        question['validate'] = validate
    if default is not None:
        question['default'] = default

    if type == 'input' and PASTE_HOTKEY:
        keyboard.add_hotkey('ctrl+v', lambda: keyboard.write(clipboard.paste()))
        answers = prompt([question])
        keyboard.remove_hotkey('ctrl+v')
    else:
        answers = prompt([question])
    return answers


def askCookie():
    return ask('input', 'cookie', 'Enter PHPSESSID cookie')['cookie']


def askLog():
    return ask('confirm', 'logs',
               'Do you want to leave a log file after each run of the script?')['logs']


def askGiftType():
    return ask('list', 'gift_type', 'Select type:', choices=list(GIFT_TYPES))['gift_type']


def askPinned():
    return ask('confirm', 'pinned', 'Should the bot enter pinned games?')['pinned']


def askMinPoints():
    return int(ask('input', 'min_points',
                   'What is the minimum number of points to remain?',
                   validate=PointValidator())['min_points'])


class NumberValidator(Validator):
    """A whole number of at least `minimum`, or nothing at all."""

    def __init__(self, minimum=0):
        self.minimum = minimum

    def validate(self, document: doc.Document):
        text = document.text.strip()
        if text == '':
            return
        message = f"Value should be a whole number of {self.minimum} or greater, or empty"
        try:
            value = int(text)
        except ValueError:
            raise ValidationError(message=message,
                                  cursor_position=len(document.text)) from None
        if value < self.minimum:
            raise ValidationError(message=message,
                                  cursor_position=len(document.text)) from None


# Asked with the measured number already filled in, so nobody has to invent one.
def askMaxEntries():
    answer = ask('input', 'max_entries',
                 f"Skip giveaways with more entries than this "
                 f"(recommended {RECOMMENDED_MAX_ENTRIES}, empty for no limit):",
                 validate=NumberValidator(minimum=1),
                 default=str(RECOMMENDED_MAX_ENTRIES))['max_entries'].strip()
    if answer == '':
        return None
    value = int(answer)
    if value < LOWEST_SENSIBLE_ENTRIES:
        print(f"  Note: below {LOWEST_SENSIBLE_ENTRIES} entries only a small share "
              f"of giveaways qualify, so the bot will enter few of them.")
    return value


def askContributorLevel():
    answer = ask('input', 'contributor_level',
                 "Your SteamGifts contributor level, shown on your profile "
                 "(empty to ignore levels):",
                 validate=NumberValidator(minimum=0), default='')['contributor_level'].strip()
    return int(answer) if answer else None


def askEditChoice():
    return ask('list', 'config_edit', 'Choice of Action :', choices=[
        'Cookie', 'log info', 'Gift type', 'Pinned games', 'Minimum points',
        'Maximum entries', 'Contributor level', 'exit'
    ])['config_edit']
