# -*- coding: utf-8 -*-
"""
/***************************************************************************
 CoreDockWidget
                                 A QGIS plugin
Procedura gestione rete ENEL
                             -------------------
        begin                : 2016-09-26
        git sha              : $Format:%H$
        copyright            : (C) 2016 by A.R.Gaeta/Vertical Srl
        email                : ar_gaeta@yahoo.it
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

#from PyQt4 import QtGui, uic
from qgis.PyQt import QtGui, uic
#from PyQt4.QtCore import pyqtSignal
from qgis.PyQt.QtCore import pyqtSignal

#recupero la versione di QGis dell'utente:
global qgis_version
try:
    from qgis.core import Qgis #versione qgis 3.x
except ImportError:
    from qgis.core import QGis as Qgis #versione qgis 2.x
qgis_version = Qgis.QGIS_VERSION

if (int(qgis_version[0]) >= 3):
    #from qgis.PyQt.QtWidgets import QTreeWidgetItem, QAction
    #import PyQt5.QtWidgets
    from qgis.PyQt.QtWidgets import (QAction,
                                 QAbstractItemView,
                                 QDialog,
                                 QFileDialog,
                                 QHBoxLayout,
                                 QTreeWidgetItem,
                                 QComboBox,
                                 QListWidget,
                                 QCheckBox,
                                 QLineEdit,
                                 QMessageBox,
                                 QToolButton,
                                 QWidget,
                                 QDockWidget,
                                 QTextBrowser)
    qwidget = QDockWidget
else:
    qwidget = QtGui.QDockWidget


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'Core_dockwidget_base.ui'))


#class CoreDockWidget(QtGui.QDockWidget, FORM_CLASS):
class CoreDockWidget(qwidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(CoreDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

