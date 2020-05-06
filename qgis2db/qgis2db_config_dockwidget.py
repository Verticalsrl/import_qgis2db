# -*- coding: utf-8 -*-
"""
/***************************************************************************
 qgis2dbConfigDockWidget
                                 A QGIS plugin
Import shapefile layers from QGis project to PostgreSQL DB
                             -------------------
        begin                : 2020/05/06
        git sha              : $Format:%H$
        copyright            : (C) 2020 by A.R.Gaeta/Vertical Srl
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

#recupero la versione di QGis dell'utente:
global qgis_version
try:
    from qgis.core import Qgis #versione qgis 3.x
except ImportError:
    from qgis.core import QGis as Qgis #versione qgis 2.x
qgis_version = Qgis.QGIS_VERSION

if (int(qgis_version[0]) < 3):
    from PyQt4 import QtGui, uic
    qgs_dialog = QtGui.QDialog
else:
    from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QDialog, QLineEdit
    qgs_dialog = QDialog
#from PyQt4 import QtGui, uic

from qgis.PyQt import uic


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'qgis2db_config_dockwidget_base.ui'))


#class qgis2dbConfigDockWidget(QtGui.QDialog, FORM_CLASS):
class qgis2dbConfigDockWidget(qgs_dialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(qgis2dbConfigDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)
