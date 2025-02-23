#!/bin/bash
set -x

pyuic6  ./qt/ElPartsMain.ui -o ElParts.py
pyuic6  ./qt/AppsPathSetup.ui -o ElAppPathWnd.py
pyuic6  ./qt/ElOpenFileWnd.ui -o ElOpenFileWnd.py
pyuic6  ./qt/ElHdrEditWnd.ui -o ElHdrEditWnd.py
#pyuic5  qt/ElPartAddDialog.ui -o ElPartAddDialog.py
#pyuic5  qt/ElPartHeaders.ui -o ElPartHeaders.py
#pyuic5  qt/ElAddTypeDlg.ui -o ElAddTypeDlg.py

pyside6-rcc  ./qt/resources.qrc -o resources.pyx
cat resources.pyx | sed 's/PySide6/PyQt6/' > resources.py
