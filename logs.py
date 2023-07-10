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

def createFileLog(status):
    if status == True:
        try:
            import logging
            import logging.config    
            logging.config.dictConfig(LOGGING_CONFIG)
            logger = logging.getLogger('__logger__')
        except ImportError:
            logger = None

def editFileLog(info):
    if logger: 
        logger.debug(info)
