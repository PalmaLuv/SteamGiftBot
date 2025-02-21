#    ______                   ______ _____    ___                      
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   
#                                                                    
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License GPL-3.0 license

#log configurations
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'default_formatter': {
            'format': '[%(levelname)s:%(asctime)s] %(message)s'
        },
    },

    'handlers': {
        'rotating_file_handler': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'event_log.log',
            'formatter': 'default_formatter'
        },
        'file_handler': {
            'class': 'logging.FileHandler',
            'filename': 'event_log.log',
            'mode': 'w',
            'formatter': 'default_formatter'
        }
    },

    'loggers': {
        '__logger__': {
            'handlers': ['file_handler'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
}

# Storing the right variables. 
class LoggerCfg:
    def __init__(self):
        self._logger = False

    @property
    def logger(self):
        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value
thisLog = LoggerCfg()

# Creating files and customizing logs.
def createFileLog():
    try:
        import logging
        import logging.config
        import datetime
        import os
        filename_format = 'log/log-%d.%m.%Y-%H.%M.%S.log'
        formatted_datetime = datetime.datetime.now().strftime(filename_format)
        LOGGING_CONFIG['handlers']['rotating_file_handler']['filename'] = formatted_datetime
        LOGGING_CONFIG['handlers']['file_handler']['filename'] = formatted_datetime
        if not os.path.exists('log'):
            os.makedirs('log')
        logging.config.dictConfig(LOGGING_CONFIG)
        thisLog.logger = logging.getLogger('__logger__')
    except ImportError:
        thisLog.logger = None

# Adding log information.
def editFileLog(info):
    if thisLog.logger: 
        thisLog.logger.debug(info)
