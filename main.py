import getopt
import logging
import os
import sys
import traceback

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

import ElDBScheme
import ElLogger
import constants
from ElConfig import ElConfig
from ElDBScheme import DBScheme, DBFactory
from ElMainWindow import MainWindow

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
logger = ElLogger.setLogger(__name__)


# constants.LAST_OPEN_FILE = "last_open_file"
HOME = os.getenv('HOME')
basedir = os.path.dirname(__file__)

# constants.STARTUP_MODE_CATALOG = "C"
# constants.STARTUP_MODE_PROJECTS = "P"
#
# constants.CONFIG_DB_FILE = "db_file"
# constants.CONFIG_STARTUP_MODE = "startup_mode"

config = ElConfig()
# db_file = ""
# CURRENT_FACTORY_OBJ = None
startupMode = constants.STARTUP_MODE_CATALOG


def appStartUp(window: MainWindow):
    pass


def MainWindowOpen(factory, startupMode):
    win_width = 1000 if not config or not config.has_value("width", "window") else config.get_value("width", "window")
    win_height = 600 if not config or not config.has_value("height", "window") else config.get_value("height", "window")
    x = 300 if not config or not config.has_value("x", "window") else config.get_value("x", "window")
    y = 150 if not config or not config.has_value("y", "winsdow") else config.get_value("y", "window")

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(os.path.join(basedir, "icons", "main1.png")))
    window = MainWindow(factory, config)
    window.resize(win_width, win_height)
    window.resize_contents()
    logger.debug("Window position x=%s, y=%s", x, y)
    window.move(x, y)
    # window.config = config

    window.setStartupMode(startupMode)

    window.show()
    app.exec()


def main():
    prog_name = "elworks"  ##  Rename to PartsDB
    conf_name = prog_name + ".conf"
    resources_path_list = []
    config_file = ""
    log_file = None
    log_level = logging.ERROR
    db_file = ""
    verb = False


    path = os.path.join(HOME, "." + prog_name)
    if not os.path.exists(path):
        os.mkdir(path)
    resources_path_list.append(path)

    path = os.path.join(basedir, "resources")
    if not os.path.exists(path):
        # os.mkdir(path)
        resources_path_list.append(path)

    startupMode = constants.STARTUP_MODE_CATALOG if not config or not config.has_value(
        constants.CONFIG_STARTUP_MODE) else config.get_value(constants.CONFIG_STARTUP_MODE)

    argv = sys.argv[1:]
    options, args = getopt.getopt(argv, "c:i:d:l:v", ["config=", "input=", "dbpath=", "logfile=", "verbose"])

    for name, value in options:
        if name in ['-c', '--conf']:
            config_file = value
        elif name in ['-i', '--input']:
            input_file = value
        elif name in ['-d', '--dbpath']:
            db_file = value
        elif name in ['-l', '--logfile']:
            log_file = value
        elif name in ['-v', '--verbose']:
            verb = True

    if config_file:
        config.load(config_file)
    else:
        for fpath in resources_path_list:
            config_file = os.path.join(fpath, prog_name + ".conf")
            if os.path.isfile(config_file):
                config.load(config_file)
                break

    ElConfig.CONFIG_OBJECT = config

    if db_file:
        factory = DBFactory(db_file)
        config.set_value(constants.CONFIG_DB_FILE, factory.db_file)
    elif config.has_value(constants.CONFIG_DB_FILE):
        db_file = config.get_value(constants.CONFIG_DB_FILE)
        factory = DBFactory(db_file)
    else:
        for fpath in resources_path_list:
            db_file = os.path.join(fpath, prog_name + ".sqlite")
            if os.path.isfile(db_file):
                factory = DBFactory(db_file)
                config.set_value(constants.CONFIG_DB_FILE, factory.db_file)
                break

    if verb:
        log_level = logging.DEBUG
    else:
        llconf = config.get_value(constants.LOG_LEVEL)
        if llconf is None:
            loglevel = logging.ERROR
            log_level = logging.ERROR
            config.set_value(constants.LOG_LEVEL, "err")
        elif llconf == "err":
            log_level = logging.ERROR
        elif llconf == "debug":
            log_level = logging.DEBUG
        else:
            log_level = logging.ERROR
            config.set_value(constants.LOG_LEVEL, "err")

    ElLogger.setLevel(log_level)

    if log_file is None:
        log_file = config.get_value(constants.LOG_FILE)

    if log_file is not None and log_file != "":
        ElLogger.setLogFile(log_file)
    else:
        log_file = os.path.join("/tmp", prog_name + ".log")
        ElLogger.setLogFile(log_file)


    ElDBScheme.DB_FACTORY = factory

    try:
        MainWindowOpen(factory, startupMode)
    except Exception as err:
        message = f"Unexpected {err=}, {type(err)=}"
        e_traceback = traceback.format_exception(err.__class__, err, err.__traceback__)
        traceback_lines = []
        for line in [line.rstrip('\n') for line in e_traceback]:
            traceback_lines.extend(line.splitlines())
        logger.critical(traceback_lines.__str__())

        logger.exception(message)
        # if logger:
        #     logger.exception(message)
        # if logger is None:
        #     logging.exception(message)
        # return None
    finally:
        logger.info("Close DB Connection.")
        factory.disconnect()
        config.set_value(constants.CONFIG_STARTUP_MODE, startupMode)
        config.save(config_file)


if __name__ == '__main__':
    main()
