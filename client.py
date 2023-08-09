#    ______                   ______ _____    ___                      
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   
#                                                                    
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0

import six 
from PyInquirer import ValidationError, Validator, prompt
from prompt_toolkit import document as doc
from main import config
import keyboard
import clipboard
import os

try:
    from colorama import init, Fore
    init()
except ImportError:
    Fore = None

from logs import editFileLog, createFileLog  

array_logo = ["    ______                   ______ _____    ___                      ",
              "   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____",
              "  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/",
              " /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   " ]

# Storing the right variables. 
class statusLogs:
    def __init__(self):
        self._valLogs = False
        self._valTextConsole = 0

    @property 
    def valTextConsole(self): 
        return self._valTextConsole

    @property
    def valLogs(self):
        return self._valLogs

    @valTextConsole.setter
    def valTextConsole(self, value):
        self._valTextConsole = value

    @valLogs.setter
    def valLogs(self, value):
        self._valLogs = value

boolLogs = statusLogs()

def createdLogs(status):
    if True == status:
        createFileLog()
        boolLogs.valLogs = status

def log(str, color="white"):
    if boolLogs.valTextConsole < 60: 
        boolLogs.valTextConsole += 1
    elif 60 <= boolLogs.valTextConsole: 
        boolLogs.valTextConsole = 0
        os.system('cls')
    if boolLogs.valLogs: 
        editFileLog(str.replace('\n', ' '))
    if Fore:
        fore_str = getattr(Fore, color.upper()) + str + Fore.RESET
        six.print_(fore_str)
    else:
        six.print_(str)

class PointValidator(Validator):
    def validate(self, document: doc.Document):
        value = document.text
        try:
            value = int(value)
        except Exception:
            raise ValidationError(message = 'Value should be greater than 0', cursor_position = len(document.text))

        if value <= 0:
            raise ValidationError(message = 'Value should be greater than 0', cursor_position = len(document.text))
        return True

def ask(type, name, msg, validate=None, choices=[]):
    questions = [
        {
            'type'      : type, 
            'name'      : name,
            'message'   : msg,
            'validate'  : validate
        }
    ]
    if choices:
        questions[0].update({'choices':choices})
    if type == 'input':
        keyboard.add_hotkey('ctrl+v', lambda: keyboard.write(clipboard.paste()))
        answers = prompt(questions)
        keyboard.remove_hotkey('ctrl+v')
    else :
        answers = prompt(questions)
    return answers

def askReadConfig(cookie_value, log_info_value):
    config.set('DEFAULT', 'cookie', cookie_value)
    config.set('DEFAULT', 'log_info', str(log_info_value))
    with open('config.ini', 'w') as configFile:
        config.write(configFile)

def askCookie():
    cookie = ask('input', 'cookie', 'Enter PHPSESSID cookie')
    return cookie['cookie']

def askLog(): 
    log = ask('confirm', 'logs', 
    'Do you want to leave a log file after each run of the script?')['logs']
    return log

