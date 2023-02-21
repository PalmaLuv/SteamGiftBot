#    ______                   ______ _____    ___                      
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   
#                                                                    
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License GPL-3.0 license

import six 
from PyInquirer import ValidationError, Validator, prompt
from prompt_toolkit import document as doc
from main import config
import keyboard
import clipboard

try:
    import colorama
    colorama.init()
except ImportError:
    colorama = None

try:
    from termcolor import colored
except ImportError:
    colored = None    

array_logo = ["    ______                   ______ _____    ___                      ",
              "   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____",
              "  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/",
              " /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   " ]

# text output
def log(str,color="white"):
    if colored: 
        six.print_(colored(str, color))
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

def askCookie():
    cookie = ask('input', 'cookie',
                'Enter PHPSESSID cookie')
    config['DEFAULT']['cookie'] = cookie['cookie']
    with open('config.ini', 'w') as cofFILE :
        config.write(cofFILE)
    return cookie['cookie']
