import logging
import sys
from PyQt6.QtCore import QProcess, QObject, pyqtSignal
# from PyQt6.QtCore.QProcess import ProcessError
from PyQt6.QtWidgets import QMessageBox

import ElConfig
import ElLogger

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

from ElAppList import AppList
logger = ElLogger.setLogger(__name__)

PROCESS_STATE_RUN = 1
PROCESS_STATE_START = 2
PROCESS_STATE_NOTRUN = 3
PROCESS_STATE_FINISH = 4


def showError(msg):
    msgBox = QMessageBox()
    msgBox.setText(msg)
    return msgBox.exec()


class Communicate(QObject):
    processError = pyqtSignal(str, int, str)


class Process(QObject):

    def __init__(self, name="Unnamed"):
        # super().__init__(self)
        super(Process, self).__init__()
        self.name = name
        self.processId = -1
        self.process = QProcess()
        self.comm = Communicate()
        self.process.errorOccurred.connect(self.handle_starting)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.stateChanged.connect(self.handle_state)
        self.process.finished.connect(self.process_finished)  # Clean up once complete.
        self.stateslist = {
            QProcess.ProcessState.NotRunning: PROCESS_STATE_NOTRUN,
            QProcess.ProcessState.Starting: PROCESS_STATE_START,
            QProcess.ProcessState.Running: PROCESS_STATE_RUN,
        }
        self.state = PROCESS_STATE_START
        self.app = None
        self.args = ""

    def setAppExe(self, path):
        self.app = path

    def run(self, argsAr):
        if self.app is not None:
            # logger.debug("Starting process EXE: %s ", self.app)
            # final_args = [self.app, "--args"] + argsAr
            final_args = ["-a", self.app] + argsAr
            logger.debug("Starting process EXE: open %s ", " ".join(map(str, final_args)))

            self.process.start("/usr/bin/open", final_args)
            self.process.waitForStarted()
            self.processId = self.process.processId()

            self.process.waitForStarted(1000)
            rc: QProcess.ProcessError = self.process.error()
            if rc != QProcess.ProcessError.UnknownError:
                showError("Error while running : " + " ".join(final_args))
                logger.debug("Cannot start process. Error %s (%s)", self.name, str(rc), str(self.process.errorString()))
        else:
            raise ValueError("Application path not set.")

        # https://www.pythonguis.com/tutorials/pyqt6-qprocess-external-programs/
        # open -n ./AppName.app --args -AppCommandLineArg
        # open -a APP_NAME --args ARGS
        # open -a VLC --args -L --fullscreen

    def stop(self):
        if self.processId > 0 and self.state == PROCESS_STATE_RUN:
            self.process.terminate()

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        stderr = bytes(data).decode("utf8")
        rc: QProcess.ProcessError = self.process.error()
        logger.debug("Error(%s)>>> %s,", rc, stderr)

        msgBox = QMessageBox()
        msgBox.setText("Got Error.")
        msgBox.setInformativeText(stderr)
        # msgBox.setStandardButtons(QMessageBox.StandardButton.Save)
        # msgBox.setDefaultButton(QMessageBox.StandardButton.Save.Discard)
        msgBox.exec()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8")
        logger.debug(" >>> %s", stdout)

    def handle_state(self, state):
        self.state = self.stateslist[state]
        logger.debug("Process '%s', change state %s", self.name, str(state))

    def handle_starting(self, err: QProcess.ProcessError):
        logger.warning("Process '%s', execute error: %s (%s)", self.name, str(err), str(self.process.errorString()))
        self.comm.processError.connect(self.name, err, str(self.process.errorString()))

    def process_finished(self):
        self.state = PROCESS_STATE_FINISH
        logger.debug("Process '%s' state %s", self.name, "finished")
        self.processId = -1


class ProcessFactory:
    def __init__(self):
        self.ProcessList = {}

    def createProcess(self, name) -> Process:
        if self.isProcess(name):
            pr = self.getProcess(name)
        else:
            pr = Process(name)
            self.ProcessList[name] = pr
        return pr

    def isProcess(self, name):
        return name in self.ProcessList.keys()

    def getProcess(self, name):
        if self.isProcess(name):
            return self.ProcessList[name]
        raise RuntimeError("Not process with name {}".format(name))

    def processForExt(self, name, ext):
        config: ElConfig = ElConfig.CONFIG_OBJECT
