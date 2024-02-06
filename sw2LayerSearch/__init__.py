# -*- coding: utf-8 -*-
"""
/***************************************************************************
 sw2LayerSearch
                                 A QGIS plugin
 General purpose layer search tool - exports attributes to csv file
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2018-08-07
        copyright            : (C) 2018 by Simon Warren - SW2 ICT
        email                : simon.warren@malvernhills.gov.uk
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
    """Load sw2LayerSearch class from file sw2LayerSearch.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .sw2LayerSearch import sw2LayerSearch
    return sw2LayerSearch(iface)
