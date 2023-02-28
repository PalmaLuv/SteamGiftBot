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
