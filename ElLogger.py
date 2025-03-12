import logging
import sys


# loafFileHandler = None
loggers = {}
handlers = []

handler = logging.StreamHandler(stream=sys.stderr)
handler.setFormatter(logging.Formatter(fmt='[%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
handlers.append(handler)

def_level = None

def setLogger(modName):
    logger = logging.getLogger(modName)
    if def_level is None:
        logger.setLevel(level=logging.ERROR)
    else:
        logger.setLevel(level=logging.DEBUG)

    loggers[modName] = logger

    for hdl in handlers:
        logger.addHandler(hdl)
    return logger

def setLevel(level):
    def_level = level
    for key, logger in loggers.items():
        logger.setLevel(level=level)

def setLogFile(FN):
    handler = logging.FileHandler(FN, mode='a', encoding="UTF-8", delay=False, errors=None)
    handler.setFormatter(logging.Formatter(fmt='%(asctime)s: [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
    handlers.append(handler)

    print("Create log file {}".format(FN))
    for key, logger in loggers.items():
            logger.addHandler(handler)

