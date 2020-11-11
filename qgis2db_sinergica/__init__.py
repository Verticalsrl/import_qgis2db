# -*- coding: utf-8 -*-
"""
/***************************************************************************
 qgis2db
                                 A QGIS plugin
 Import shapefile layers from QGis project to PostgreSQL DB
                             -------------------
        begin                : 2020/05/06
        copyright            : (C) 2020 by A.R.Gaeta/Vertical Srl
        email                : ar_gaeta@yahoo.it
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load qgis2db class from file qgis2db.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .qgis2db import qgis2db
    return qgis2db(iface)
