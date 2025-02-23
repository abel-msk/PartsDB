import sys

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *


class FileListW():
    def __init__(self, parent):
        self.verticalLayout = QtWidgets.QVBoxLayout(parent)
        self.verticalLayout.setObjectName("verticalLayout")
        self.widget = QtWidgets.QWidget(parent=parent)
        self.widget.setObjectName("widget")

        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.widget)
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")

        self.treeview = QTreeView()
        self.listview = QListView()
        self.horizontalLayout_2.addWidget(self.treeview)
        self.horizontalLayout_2.addWidget(self.listview)

        path = QDir.rootPath()

        self.dirModel = QFileSystemModel()
        self.dirModel.setRootPath(QDir.rootPath())
        self.dirModel.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs)

        self.fileModel = QFileSystemModel()
        self.fileModel.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.Files)

        self.treeview.setModel(self.dirModel)
        self.listview.setModel(self.fileModel)

        self.treeview.setRootIndex(self.dirModel.index(path))
        self.listview.setRootIndex(self.fileModel.index(path))

        self.treeview.clicked.connect(self.on_clicked)

    def on_clicked(self, index):
        path = self.dirModel.fileInfo(index).absoluteFilePath()
        self.listview.setRootIndex(self.fileModel.setRootPath(path))
