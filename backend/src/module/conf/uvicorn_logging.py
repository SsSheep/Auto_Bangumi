from .log import LOG_PATH

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)-8s  %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_PATH,
            "formatter": "default",
            "encoding": "utf-8",
            "maxBytes": 5242880,
            "backupCount": 3,
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "uvicorn.error": {
            "level": "WARNING",
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
