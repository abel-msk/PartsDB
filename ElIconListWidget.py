import logging
import os
import sys

from PyQt6.QtCore import QAbstractItemModel, Qt, QObject, QProcess, pyqtSignal
from PyQt6.QtGui import QIcon, QStandardItem
from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QInputDialog, QMessageBox, QListView, QLabel, \
    QToolButton, QVBoxLayout, QListWidget, QListWidgetItem, QSizePolicy, QGraphicsView, QFrame, QGraphicsScene, \
    QAbstractItemView
import ElTypesTree
from ElDBScheme import DBFactory, Type, Parts, Part, Documents, Document
import resources   ###  Do Not delete


logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stderr)
handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
logger.addHandler(handler)

# https://stackoverflow.com/questions/74910845/pyqt-qlistmodelview-iconmode-highlight-to-be-constant-size-and-add-one-more-line
# https://www.pythonguis.com/faq/file-image-browser-app-with-thumbnails/

ICON_RESOURCES = None
ON_ITEM_SELECT = "on_item_select"

class IconsList:

    def __init__(self):
        self.icons = {}
        self.loadIcons()
        ICON_RESOURCES = self

    def loadIcons(self):
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/kikad_file.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.icons["kicad_pro"] = icon
        self.icons["pro"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/pdf_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["pdf"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/plate_file.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.icons["kicad_pcb"] = icon
        self.icons["pcb"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/scheme_file.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.icons["kicad_sch"] = icon
        self.icons["sch"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/text_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["txt"] = icon
        self.icons["text"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/img_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["png"] = icon
        # self.icons["gif"] = icon
        self.icons["jpg"] = icon
        self.icons["jpeg"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/doc_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["doc"] = icon
        self.icons["docx"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/cad_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["cad"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/html_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["html"] = icon
        self.icons["htm"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/bin_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["bin"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/add_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["addfile"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/del_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["delfile"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/edit_file.png"), QtGui.QIcon.Mode.Normal,
                       QtGui.QIcon.State.Off)
        self.icons["editfile"] = icon

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/types/icons/def_file.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.icons["default"] = icon

    def getIconByExt(self, ext: str):
        try:
            icon = self.icons[ext.lower()]
        except KeyError:
            icon = self.icons["default"]
        return icon


class Communicate(QObject):
    itemSelect = pyqtSignal(Document)


class CustomIconBtn4(QFrame):

    def __init__(self, icon: QIcon, label: str, parent=None, document: Document=None):
        super(CustomIconBtn4, self).__init__(parent)
        self.doc = document
        self.setStyleSheet("QLabel {  border: 0px; background-color: transparent; margin: 10px 0px 0px 10px ;}")

        # self.setStyleSheet("QFrame { " +
        #                    " margin: 5px 5px 0px 5px;"
        #                    " border: 1px solid #8f8f91;" +
        #                    " border-radius: 6px;" +
        #                    " background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop:" +
        #                    " 0 #f6f7fa, stop: 1 #dadbde);}"
        #                    )

        q_label = QLabel(self)
        q_label.setWordWrap(True)
        q_label.setText(label)
        font = self.font()
        font.setPointSize(10)
        q_label.setFont(font)

        q_label.setStyleSheet("QLabel {  border: 0px; background-color: transparent; margin: 0px 0px 0px 0px ;}")
        q_label_SP = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        q_label.setMinimumSize(QtCore.QSize(10, 10))
        q_label.setMaximumSize(QtCore.QSize(100, 10000))
        q_label.setSizePolicy(q_label_SP)
        q_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop)
        q_label.setObjectName("test_label")

        graphicsView = QLabel(self)
        graphicsView.setPixmap(icon.pixmap(60, 60, QIcon.Mode.Normal, QIcon.State.Off))
        # graphicsView.setStyleSheet("QLabel {  border: 0px; background-color: transparent; "
        #                            "margin: 0px 0px 0px 0px; "
        #                            "padding: 5px 0px 0px 0px ;}")
        graphicsView.setStyleSheet("QLabel {  border: 0px; background-color: transparent; margin: 5px 0px 0px 0px;}")

        graphicsViewSizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        graphicsView.setMinimumSize(QtCore.QSize(100, 65))
        graphicsView.setMaximumSize(QtCore.QSize(100, 65))
        graphicsView.setSizePolicy(graphicsViewSizePolicy)
        graphicsView.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(graphicsView)
        self.layout.addWidget(q_label)
        self.layout.addStretch(2)

    def draw(self):
        self.setLayout(self.layout)

    # def mousePressEvent(self, event):
    #     if event.button() != Qt.MouseButton.NoButton:
    #         logger.debug("Mouse press event")
    #         self.setStyleSheet("QFrame { " +
    #                            "margin: 5px 5px 0px 5px ;"
    #                            "border: 1px solid #8f8f91;" +
    #                            " border-radius: 6px;" +
    #                            " background-color: #DDDDDD;}"
    #                            )
    #
    #     # self.dispatchEvent(ElTypesTree.CLICK_EVENT_NAME, self.doc)
    #     event.ignore()
    #     super().mousePressEvent(event)
    #
    # def mouseReleaseEvent(self, event):
    #     if event.button() != Qt.MouseButton.NoButton:
    #         logger.debug("Mouse Release event")
    #         self.setStyleSheet("QFrame { " +
    #                            "margin: 5px 5px 0px 5px ;"
    #                            "border: 1px solid #8f8f91;" +
    #                            " border-radius: 6px;" +
    #                            " background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop:" +
    #                            " 0 #f6f7fa, stop: 1 #dadbde);}"
    #                            "QFrame:pressed { background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #dadbde, stop: 1 #f6f7fa);}"
    #                            )
    #     event.ignore()
    #     super().mouseReleaseEvent(event)
    #

    # def addEventListener(self, name, func):
    #     if name not in self._events:
    #         self._events[name] = [func]
    #     else:
    #         self._events[name].append(func)
    #
    # def dispatchEvent(self, name, arg):
    #     functions = self._events.get(name, [])
    #     for func in functions:
    #         QtCore.QTimer.singleShot(0, lambda: func(arg))


class IconsListWidget(QtCore.QObject):

    comm = Communicate()

    def __init__(self, factory: DBFactory, listView: QListWidget):
        super().__init__()
        self.comm = Communicate()
        self.openedDocs = {}
        self._events = {}
        self.factory = factory
        self.currentPart: Part = None
        self.listView: QListWidget = listView
        self.listView.setViewMode(QListView.ViewMode.IconMode)
        self.listView.setResizeMode(QListView.ResizeMode.Fixed)
        self.listView.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.listView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self.listView.setWordWrap(True)
        # self.model: QAbstractItemModel = self.listView.model()
        self.icons = None
        self.documents: Documents = None

        # self.icons: IconsList = ICON_RESOURCES
        # self.defaultIcon = QtGui.QIcon()
        # self.defaultIcon.addPixmap(QtGui.QPixmap(":/types/icons/doc_file.png"), QtGui.QIcon.Mode.Normal,
        #                QtGui.QIcon.State.Off)

        if self.icons is None:
            self.icons = IconsList()

        self.defaultIcon = self.icons.getIconByExt("default")

    def load(self, curPart: Part):
        self.currentPart = curPart
        self.documents = curPart.getDocuments()
        qsize = QtCore.QSize(110, 110)

        if self.icons is None:
            self.icons = IconsList()

        for doc in self.documents.documentsAr:
            try:
                self.appendDocument(doc)
            except KeyError as e:
                logger.warning("Got document file with unsupported extension/type - %s. Ignored", e)

    def onItemSelect(self, item):
        doc: Document = item.data(Qt.ItemDataRole.UserRole)
        logger.debug("Document selected %s", doc.link)
        self.comm.itemSelect.emit(doc)
    #https://stackoverflow.com/questions/55553660/how-to-emit-custom-events-to-the-event-loop-in-pyqt

    def clear(self):
        self.listView.clear()

    def getSelectedItem(self):
        index = (self.listView.selectionModel().currentIndex())
        return index.data(Qt.ItemDataRole.UserRole)

    def deleteDocument(self, inputDoc):
        for x in range(self.listView.count()):
            if self.listView.item(x):
                logger.debug("Delete document at position x=%d",x)
                theDoc: Document = self.listView.item(x).data(Qt.ItemDataRole.UserRole)
                if theDoc.id == inputDoc.id:
                    index = self.listView.indexFromItem(self.listView.item(x))
                    # self.listView.removeItemWidget(self.listView.item(x))
                    # QListWidgetItem
                    self.listView.takeItem(index.row())

    def appendDocument(self, doc: Document):
        qsize = QtCore.QSize(110, 110)
        logger.debug("Add document: %s", doc.link)
        file_name, file_extension = os.path.splitext(doc.link)
        ext = file_extension[1:]
        if str(file_name) != "" and ext != "":
            if self.icons is not None:
                icon = self.icons.getIconByExt(str(file_extension)[1:])
            else:
                icon = self.defaultIcon

            item = QListWidgetItem("", self.listView)
            # btn = CustomIconBtn4(icon, os.path.basename(doc.link), parent=item, document=doc)
            btn = CustomIconBtn4(icon, os.path.basename(doc.link), parent=self.listView, document=doc)
            # item = QListWidgetItem("", self.listView)
            item.setData(Qt.ItemDataRole.UserRole, doc)
            item.setSizeHint(qsize)
            self.listView.setItemWidget(item, btn)
            self.listView.addItem(item)
            btn.draw()
            # self.listView.update()
            self.listView.itemDoubleClicked.connect(self.onItemSelect)



