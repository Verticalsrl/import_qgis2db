from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import dbConnection
import pgRoutingLayer_utils as Utils
import os
import psycopg2
import re

#probabilmente questa libreria non viene effettivamente usata dal mio plugin

conn = dbConnection.ConnectionManager()

def reloadConnections(self, reloadMessage):
    oldReloadMessage = reloadMessage
    reloadMessage = False
    database = str(self.dlg_config.comboConnections.currentText())

    self.dlg_config.comboConnections.clear()

    actions = conn.getAvailableConnections()
    self.actionsDb = {}
    for a in actions:
        self.actionsDb[ unicode(a.text()) ] = a

    for dbname in self.actionsDb:
        db = None
        try:
            db = self.actionsDb[dbname].connect()
            con = db.con
            version = Utils.getPgrVersion(con)
            if (Utils.getPgrVersion(con) != 0):
                self.dlg_config.comboConnections.addItem(dbname)

        except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)

        finally:
            if db and db.con:
                db.con.close()

    idx = self.dlg_config.comboConnections.findText(database)
    
    if idx >= 0:
        self.dlg_config.comboConnections.setCurrentIndex(idx)
    else:
        self.dlg_config.comboConnections.setCurrentIndex(0)

    reloadMessage = oldReloadMessage
    updateConnectionEnabled(self, reloadMessage)
    
def updateConnectionEnabled(self, reloadMessage):
        dbname = str(self.dlg_config.comboConnections.currentText())
        if dbname =='':
            return

        db = self.actionsDb[dbname].connect()
        con = db.con
        self.version = Utils.getPgrVersion(con)
        Utils.logMessage('Selected database: ' + dbname)
        Utils.logMessage('reloadMessage='+ str(reloadMessage))
        if reloadMessage:
            QMessageBox.information(self.dlg_config, self.dlg_config.windowTitle(), 
                'Selected database: ' + dbname)

