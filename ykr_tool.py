# -*- coding: utf-8 -*-
"""
/***************************************************************************
 YKRTool
                                 A QGIS plugin
 Tampereen tulevaisuuden yhdyskuntarakenteen ilmastovaikutusten arviointityökalu
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2019-05-05
        git sha              : $Format:%H$
        copyright            : (C) 2019 by Gispo Ltd.
        email                : mikael@gispo.fi
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
from PyQt5 import uic
from PyQt5.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction

from qgis.core import Qgis, QgsMessageLog, QgsVectorLayer
from qgis.gui import QgsFileWidget

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
import uuid
import os.path
import psycopg2
import datetime, getpass
from configparser import ConfigParser



class YKRTool:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'YKRTool_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Ilmastovaikutusten arviointityökalu')

        self.conn = None
        self.connParams = None

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        self.mainDialog = uic.loadUi(os.path.join(self.plugin_dir, 'ykr_tool_main.ui'))
        self.settingsDialog = uic.loadUi(os.path.join(self.plugin_dir, 'ykr_tool_db_settings.ui'))

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('YKRTool', message)


    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/ykr_tool/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Ilmastovaikutusten arviointityökalu'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Ilmastovaikutusten arviointityökalu'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start:
            self.first_start = False
            self.setupMainDialog()

        self.mainDialog.show()

        # Run the dialog event loop
        result = self.mainDialog.exec_()
        # See if OK was pressed
        if result:
            if not self.connParams:
                configFilePath = QSettings().value("/YKRTool/configFilePath",\
                    "", type=str)
                self.connParams = self.parseConfigFile(configFilePath)

            self.createDbConnection(self.connParams)

            self.sessionParams = self.generateSessionParameters()
            self.readProcessingInput()
            if not self.uploadData(): return
            self.runCalculations()
            self.cleanUp()

    def setupMainDialog(self):
        '''Sets up the main dialog'''
        self.mainDialog.geomArea.addItem("Tampere")
        self.mainDialog.adminArea.addItem("Pirkanmaa")
        self.mainDialog.pitkoScenario.addItems(["wem", "eu80", "kasvu", "muutos", "saasto", "static"])
        self.mainDialog.emissionsAllocation.addItems(["hjm", "em"])
        self.mainDialog.elecEmissionType.addItems(["hankinta", "tuotanto"])

        self.mainDialog.settingsButton.clicked.connect(self.displaySettingsDialog)

        self.mainDialog.ykrPopLayerList.hide()
        self.mainDialog.ykrJobsLayerList.hide()
        self.mainDialog.ykrBuildingsLayerList.hide()
        self.mainDialog.futureAreasLayerList.hide()
        self.mainDialog.futureNetworkLayerList.hide()
        self.mainDialog.futureStopsLayerList.hide()

        self.mainDialog.ykrPopLoadLayer.clicked.connect(self.handleLayerToggle)
        self.mainDialog.ykrJobsLoadLayer.clicked.connect(self.handleLayerToggle)
        self.mainDialog.ykrBuildingsLoadLayer.clicked.connect(self.handleLayerToggle)
        self.mainDialog.futureAreasLoadLayer.clicked.connect(self.handleLayerToggle)
        self.mainDialog.futureNetworkLoadLayer.clicked.connect(self.handleLayerToggle)
        self.mainDialog.futureStopsLoadLayer.clicked.connect(self.handleLayerToggle)

        self.mainDialog.calculateFuture.clicked.connect(self.handleLayerToggle)
        # Future calculations currently not supported
        self.mainDialog.calculateFuture.setEnabled(False)
        self.mainDialog.futureBox.setEnabled(False)

    def displaySettingsDialog(self):
        '''Sets up and displays the settings dialog'''
        self.settingsDialog.show()
        self.settingsDialog.configFileInput.setStorageMode(QgsFileWidget.GetFile)
        self.settingsDialog.configFileInput.setFilePath(QSettings().value\
            ("/YKRTool/configFilePath", "", type=str))
        self.settingsDialog.loadFileButton.clicked.connect(self.setConnectionParamsFromFile)

        result = self.settingsDialog.exec_()
        if result:
            self.connParams = self.readConnectionParamsFromInput()

    def setConnectionParamsFromFile(self):
        '''Reads connection parameters from file and sets them to the input fields'''
        filePath = self.settingsDialog.configFileInput.filePath()
        QSettings().setValue("/YKRTool/configFilePath", filePath)

        try:
            dbParams = self.parseConfigFile(filePath)
        except Exception as e:
            self.iface.messageBar().pushMessage('Virhe luettaessa tiedostoa',\
                str(e), Qgis.Warning, duration=10)

        self.setConnectionParamsFromInput(dbParams)

    def parseConfigFile(self, filePath):
        '''Reads configuration file and returns parameters as a dict'''
        # Setup an empty dict with correct keys to avoid keyerrors
        dbParams = {
            'host': '',
            'port': '',
            'database': '',
            'user': '',
            'password': ''
        }
        if not os.path.exists(filePath):
            self.iface.messageBar().pushMessage('Virhe', 'Tiedostoa ei voitu lukea',\
                Qgis.Warning)
            return dbParams

        parser = ConfigParser()
        parser.read(filePath)
        if parser.has_section('postgresql'):
            params = parser.items('postgresql')
            for param in params:
                dbParams[param[0]] = param[1]
        else:
            self.iface.messageBar().pushMessage('Virhe', 'Tiedosto ei sisällä\
                tietokannan yhteystietoja', Qgis.Warning)

        return dbParams

    def setConnectionParamsFromInput(self, params):
        '''Sets connection parameters to input fields'''
        self.settingsDialog.dbHost.setValue(params['host'])
        self.settingsDialog.dbPort.setValue(params['port'])
        self.settingsDialog.dbName.setValue(params['database'])
        self.settingsDialog.dbUser.setValue(params['user'])
        self.settingsDialog.dbPass.setText(params['password'])

    def readConnectionParamsFromInput(self):
        '''Reads connection parameters from user input and returns a dictionary'''
        params = {}
        params['host'] = self.settingsDialog.dbHost.value()
        params['port'] = self.settingsDialog.dbPort.value()
        params['database'] = self.settingsDialog.dbName.value()
        params['user'] = self.settingsDialog.dbUser.value()
        params['password'] = self.settingsDialog.dbPass.text()
        return params

    def handleLayerToggle(self):
        '''Toggle UI components visibility based on selection'''
        if self.mainDialog.ykrPopLoadLayer.isChecked():
            self.mainDialog.ykrPopLayerList.show()
            self.mainDialog.ykrPopFile.hide()
        else:
            self.mainDialog.ykrPopLayerList.hide()
            self.mainDialog.ykrPopFile.show()
        if self.mainDialog.ykrJobsLoadLayer.isChecked():
            self.mainDialog.ykrJobsLayerList.show()
            self.mainDialog.ykrJobsFile.hide()
        else:
            self.mainDialog.ykrJobsLayerList.hide()
            self.mainDialog.ykrJobsFile.show()
        if self.mainDialog.ykrBuildingsLoadLayer.isChecked():
            self.mainDialog.ykrBuildingsLayerList.show()
            self.mainDialog.ykrBuildingsFile.hide()
        else:
            self.mainDialog.ykrBuildingsLayerList.hide()
            self.mainDialog.ykrBuildingsFile.show()
        if self.mainDialog.futureAreasLoadLayer.isChecked():
            self.mainDialog.futureAreasLayerList.show()
            self.mainDialog.futureAreasFile.hide()
        else:
            self.mainDialog.futureAreasLayerList.hide()
            self.mainDialog.futureAreasFile.show()
        if self.mainDialog.futureNetworkLoadLayer.isChecked():
            self.mainDialog.futureNetworkLayerList.show()
            self.mainDialog.futureNetworkFile.hide()
        else:
            self.mainDialog.futureNetworkLayerList.hide()
            self.mainDialog.futureNetworkFile.show()
        if self.mainDialog.futureStopsLoadLayer.isChecked():
            self.mainDialog.futureStopsLayerList.show()
            self.mainDialog.futureStopsFile.hide()
        else:
            self.mainDialog.futureStopsLayerList.hide()
            self.mainDialog.futureStopsFile.show()

        if self.mainDialog.calculateFuture.isChecked():
            self.mainDialog.futureBox.setEnabled(True)
        else:
            self.mainDialog.futureBox.setEnabled(False)

    def createDbConnection(self, connParams):
        '''Creates a database connection and cursor based on connection params'''
        QgsMessageLog.logMessage(str(self.connParams), "YKRTool", Qgis.Info)
        if '' in list(connParams.values()):
            self.iface.messageBar().pushMessage('Virhe yhdistäessä tietokantaan',\
                'Täytä puuttuvat yhteystiedot', Qgis.Critical)
            return False
        try:
            self.conn = psycopg2.connect(host=connParams['host'],\
                port=connParams['port'], database=connParams['database'],\
                user=connParams['user'], password=connParams['password'],\
                connect_timeout=3)
            self.cur = self.conn.cursor()
        except Exception as e:
            self.iface.messageBar().pushMessage('Virhe yhdistäessä tietokantaan',\
                str(e), Qgis.Critical, duration=10)
            return False

    def generateSessionParameters(self):
        '''Get necessary values for processing session'''
        sessionParams = {}

        usr = getpass.getuser()
        sessionParams["user"] = usr.replace(" ", "_")
        now = datetime.datetime.now()
        sessionParams["startTime"] = now.strftime("%Y%m%d_%H%M%S")
        sessionParams["baseYear"] = now.year
        sessionParams["uuid"] = str(uuid.uuid4())

        return sessionParams

    def readProcessingInput(self):
        '''Read user input from main dialog'''
        if self.mainDialog.ykrPopLoadLayer.isChecked():
            self.ykrPopLayer = self.mainDialog.ykrPopLayerList.currentLayer()
        else:
            self.ykrPopLayer = QgsVectorLayer(self.mainDialog.\
                ykrPopFile.filePath(), "ykr_vaesto_2017", "ogr")
        if self.mainDialog.ykrBuildingsLoadLayer.isChecked():
            self.ykrBuildingsLayer = self.mainDialog.ykrBuildingsLayerList.currentLayer()
        else:
            self.ykrBuildingsLayer = QgsVectorLayer(self.mainDialog.\
                ykrBuildingsFile.filePath(), "pir_rakennukset_2017_piste", "ogr")
        if self.mainDialog.ykrJobsLoadLayer.isChecked():
            self.ykrJobsLayer = self.mainDialog.ykrJobsLayerList.currentLayer()
        else:
            self.ykrJobsLayer = QgsVectorLayer(self.mainDialog.\
                ykrJobsFile.filePath(), "ykr_tyopaikat_2015", "ogr")

    def uploadData(self):
        '''Load data as layers and write to database'''
        if not self.checkLayerValidity(): return False

        return True

    def checkLayerValidity(self):
        '''Checks that the layers are valid and raises an exception if necessary'''
        try:
            if not self.ykrPopLayer.isValid():
                raise Exception("Virhe ladattaessa nykytilanteen YKR-väestötasoa")
            if not self.ykrBuildingsLayer.isValid():
                raise Exception("Virhe ladattaessa nykytilanteen YKR-rakennustasoa")
            if not self.ykrJobsLayer.isValid():
                print(abcdeft)
                raise Exception("Virhe ladattaessa nykytilanteen YKR-työpaikkatasoa")
            if self.mainDialog.calculateFuture.isChecked():
                if not self.futureAreasLayer.isValid():
                    raise Exception("Virhe ladattaessa tulevaisuuden aluevaraustietoja")
                if self.futureNetworkLayer:
                    if not self.futureNetworkLayer.isValid():
                        raise Exception("Virhe ladattaessa keskusverkkotietoja")
                if self.futureStopsLayer:
                    if not self.futureStopsLayer.isValid():
                        raise Exception("Virhe ladattaessa joukkoliikennepysäkkitietoja")
            return True
        except Exception as e:
            self.iface.messageBar().pushMessage('Virhe ladattaessa tasoja', str(e), Qgis.Critical)
            return False

    def runCalculations(self):
        '''Call necessary processing functions in database'''
        pass

    def cleanUp(self):
        '''Delete temporary data and close db connection'''
        if self.conn:
            self.conn.close()