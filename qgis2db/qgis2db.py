# -*- coding: utf-8 -*-
from __future__ import print_function

"""
/***************************************************************************
 qgis2db
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

'''
NUOVE NOTE PROGETTO PNI:

- alcuni shp in caricamento possono gia' avere il campo gid, ma non e' univoco, e la procedura di caricamento su DB da errore. Non sono riuscito a omettere questo campo nel caso esista, ma solo ad eliminarlo, anche se ha un comportamento strano. Dunque carico gli shp su DB usando come PK il campo gidd, sperando che cosi scritto non esista gia sugli shp. Funzione import_shp2db

- esegui vacuum dello schema dopo l'import da shp2db, funzione import_shp2db, oppure guarda anche il python ImportIntoPostGIS recuperato da web, che sfrutta la libreria di cui non ho ancora trovato documentazione pero:
    from processing.tools import dataobjects, postgis

- le eccezioni al caricamento dei layer per la creazione di un nuovo progetto sono nella funzione crea_progetto_reindirizzando_il_template


OTTIMIZZAZIONI/DUBBI:
- ATTENZIONE!! nel cambio di datasource del progetto template devo omettere quei layer che non trovano esatto riscontro nel nome sul DB altrimenti QGis crasha. Vedi funzione import_shp2db
- creare maschere di editing sui progetti template con le dovute constraints sui campi (mappa valori) in modo tale da riportarle poi sui progetti salvati con i dati da DB
- creare maschere di editing con vari TAB per semplificare la compilazione/modifica dei campi, in base a quelli piu' frequentemente modificati dall'operatore in cantiere

- join tra ebw_pte e ebw_location per progetti C&D???? Su quale campo? Chiedere a SINERGICA/GATTI
RISPOSTA: sui campi nome, solo che su ebw_location il campo e' costituito da 2 parti. quindi con una formula QGis ad esempio posso creare un campo virtuale "nome_pte" su ebw_location:
right( "nome", ( length( trim( "nome" ) ) -  strpos( "nome", ' ') ))
e su di esso fare un join su ebw_pte (ammesso che esista, ma se non esiste non mi pare che QGis dia problemi) mostrando il campo "numero_porte". In base ad esso, visualizzare in maniera differente i ROE cioè i PTA di ebw_lcoation (colore? forma?)

- SPATIAL INDEX: nel caso volessi aggiungere a posteriori indice spaziale su vecchi schemi, da consolle python di qgis:
dest_dir = "dbname=pni_2 host=86.107.96.34 port=5432 user=operatore password=operatore_2k16"
test_conn = psycopg2.connect(dest_dir)
cur = test_conn.cursor()
schemaDB='robbiate'
cur.execute( "SELECT table_name FROM information_schema.tables WHERE table_schema = '%s' AND table_type = 'BASE TABLE';" % (schemaDB) )
dataDB = cur.fetchall()
for row in dataDB:
    #creo lo SPATIAL INDEX
    query_spatial = "CREATE INDEX %s_geoidx ON %s.%s USING gist (geom);" % (row[0], schemaDB, row[0])
    cur.execute(query_spatial)

test_conn.commit()


- RIPULISCI questo codice dalle vecchie funzioni e vecchi richiami ad altri script, che dovrai eliminare dal plugin in modo che sia un po' piu' pulito

'''


#from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
#from PyQt4.QtGui import QAction, QIcon, QFileDialog
#from PyQt4 import uic
#from PyQt4.QtCore import *
#from PyQt4.QtGui import *
from qgis.PyQt import uic
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
#recupero la versione di QGis dell'utente:
global qgis_version
try:
    from qgis.core import Qgis #versione qgis 3.x
except ImportError:
    from qgis.core import QGis as Qgis #versione qgis 2.x
qgis_version = Qgis.QGIS_VERSION


#importo alcune librerie per gestione dei layer caricati
from qgis.core import *
#from qgis.core import QgsVectorLayer, QgsMapLayerRegistry
#from qgis.utils import iface, QGis #forse importare QGis, che mi serviva solo per recuperare info sul sistema, rallenta il plugin. Difatti la 3.5b che non caricava QGis risulta essere meno onerosa
from qgis.utils import iface
from qgis.gui import *

# Initialize Qt resources from file resources.py
from . import resources
# Import the code for the dialog
from .qgis2db_config_dockwidget import qgis2dbConfigDockWidget
from .qgis2db_help_dockwidget import qgis2dbHelpDockWidget


#Importo i miei script dedicati e altre cose utili per il catasto:
#from optparse import OptionParser
from os.path import basename as path_basename
from os.path import expanduser
#import os, sys #forse importare sys, che mi serviva solo per recuperare info sul sistema, rallenta il plugin. Difatti la 3.5b che non caricava sys risulta essere meno onerosa
import os
from osgeo import ogr

#importo altre librerie prese dal plugin pgrouting
#import pgRoutingLayer_utils as Utils
from . import pgRoutingLayer_utils as Utils

#import db_utils as db_utils #ricopiavo delle funzione da pgRoutingLayer ma penso di farne a meno
#import dbConnection #ricopiavo delle funzione da pgRoutingLayer ma penso di farne a meno
import psycopg2
import psycopg2.extras
#Per aprire link web
#import webbrowser

#import db_compare as db_compare
#import db_solid as db_solid
#import computo_metrico as computo_metrico
#import numerazione_puntirete as numerazione_puntirete
#importo DockWidget
from .Core_dockwidget import CoreDockWidget

from collections import OrderedDict

if (int(qgis_version[0]) >= 3):
    #from qgis.PyQt.QtWidgets import QTreeWidgetItem, QAction
    #import PyQt5.QtWidgets
    from qgis.PyQt.QtWidgets import (QAction,
                                 QAbstractItemView,
                                 QDialog,
                                 QDialogButtonBox,
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
                                 QTextBrowser)
    xrange = range
    critical_level = Qgis.Critical
    point_geometry = QgsWkbTypes.PointGeometry
else:
    critical_level = QgsMessageLog.CRITICAL
    point_geometry = QGis.Point


class qgis2db:
    """QGIS Plugin Implementation."""
    
    #Ridefinisco la funzione selectByIds in base alla versione
    #TENTATIVO FALLITO!! Meglio usare la versione 2.18.11 new LTR
    #Qgis_sw_version = QGis.QGIS_VERSION
    #Qgis_sw_version_arr = Qgis_sw_version.split('.')
    '''global func_to_version
    func_to_version = 0
    msg = QMessageBox()
    if (int(Qgis_sw_version_arr[0]) < 2):
        msg.setText("Plugin non compatibile con questa versione di QGis!")
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Plugin non compatibile!")
        msg.setStandardButtons(QMessageBox.Ok)
        retval = msg.exec_()
    elif (int(Qgis_sw_version_arr[1]) <= 14):
        #msg.setText("Plugin per la versione " + str(Qgis_sw_version_arr[0]) + "." + str(Qgis_sw_version_arr[1]))
        QgsVectorLayer.setSelectedFeatures = QgsVectorLayer.setSelectedFeatures
        func_to_version = 1
    elif (int(Qgis_sw_version_arr[1]) >= 18):
        func_to_version = 2'''
    
    
    #NUOVO dictionary per progetto PNI: probabilmente piu utile come promemoria per me...
    LAYER_TYPE = {
        'PNI_SCORTA': 'POINT',
        'PNI_GIUNTO': 'POINT',
        'PNI_GRAFO': 'LINESTRING',
        'PNI_LOCATION': 'POINT',
        'PNI_ROUTE': 'LINESTRING',
        'PNI_CAVO': 'LINESTRING',
        'PNI_PFS': 'POLYGON',
        'PNI_PFP': 'POLYGON'
    }
    
    LAYER_NAME_PNI_ced = { #in teoria la chiave del dict dovrebbe essere composta da PNI+<nome_del_layer_in_legenda> e il value del dict dovrebbe essere uguale al nome dello shp e quindi della tavola su DB. Nel caso di ced, la key la lascio uguale al nome tavola a meno di non modificare il progetto qgis ced_template....
        'PNI_EBW_PTE': 'ebw_pte',
        'PNI_CIVICI': 'ebw_address',
        'PNI_CAVI': 'ebw_cavo',
        'PNI_GIUNTI': 'ebw_giunto',
        'PNI_POZZETTI': 'ebw_location',
        'PNI_AREA_PFP': 'ebw_pfp',
        'PNI_AREA_PFS': 'ebw_pfs',
        'PNI_AREA_POP': 'ebw_pop',
        'PNI_TRATTA': 'ebw_route',
        'PNI_SCORTA': 'ebw_scorta',
        #'PNI_GRID': 'grid_XX',
        'PNI_PLANIMETRIA': 'planimetria',
        'PNI_STRADE': 'street'
    }
    LAYER_OPZIONALI_ced = ['planimetria', 'street', 'ebw_address', 'ebw_pop', 'ebw_scorta', 'ebw_pte']
    
    #dizionario dei nomi da progetto QGIS_template (key) a tavole su DB (value):
    #questo e' il dictionary in PRODUZIONE!!
    LAYER_NAME_PNI_aib = {
        'PNI_ACCESS_POINT': 'access_point',
        'PNI_AREA_CAVO': 'ebw_area_cavo',
        'PNI_AREE_PFP': 'ebw_area_pfp',
        'PNI_AREE_PFS': 'ebw_area_pfs',
        'PNI_AREA_ANELLO': 'ebw_area_anello',
        'PNI_AREA_POP': 'ebw_area_pop',
        'PNI_CAVI': 'sheath_with_loc',
        'PNI_CIVICI': 'address',
        'PNI_COLONNINE': 'mit_terminal_enclosure',
        'PNI_DELIVERY': 'point_of_interest',
        'PNI_EDIFICI': 'building',
        'PNI_GIUNTI': 'sheath_splice',
        'PNI_PLANIMETRIA': 'planimetria',
        'PNI_POZZETTI': 'uub',
        'PNI_STRADE': 'street',
        'PNI_TRATTA': 'underground_route',
        'PNI_TRATTA_AEREA': 'aerial_route',
        'PNI_MIT_BAY': 'mit_bay'
    }
    LAYER_OPZIONALI_aib = ['planimetria', 'address']
    
    COD_POP = 0
    epsg_srid = 0
    sciape_error = []

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
            'qgis2db_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg_config = qgis2dbConfigDockWidget()
        self.dlg_help = qgis2dbHelpDockWidget()
        #self.dlg_compare = qgis2dbCompareDockWidget()
        #self.dlg_solid = qgis2dbSolidDockWidget()
        #self.dlg_export = qgis2dbExportDockWidget()
        #self.dlg_cloneschema = qgis2dbCloneschemaDockWidget()
        #self.dlg_append = qgis2dbAppendDockWidget()

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&qgis2db')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'qgis2db')
        self.toolbar.setObjectName(u'qgis2db')
        #TEST: aggiungo DockWidget
        self.pluginIsActive = False
        self.dockwidget = None
        
        #Implemento alcune azioni sui miei pulsanti
        #Scelgo che punto voglio associare e faccio partire in qualche modo il controllo sulla selezione sulla mappa:
        '''self.dlg = qgis2dbDockWidget()
        self.dlg.scala_giunto_btn.clicked.connect(self.associa_scala_giunto)
        self.dlg.scala_pd_btn.clicked.connect(self.associa_scala_pd)
        self.dlg.scala_pfs_btn.clicked.connect(self.associa_scala_pfs)
        self.dlg.giunto_giunto_btn.clicked.connect(self.associa_giunto_giunto)
        self.dlg.giunto_pd_btn.clicked.connect(self.associa_giunto_pd)
        self.dlg.pd_pfs_btn.clicked.connect(self.associa_pd_pfs)
        self.dlg.pfs_pfp_btn.clicked.connect(self.associa_pfs_pfp)
        self.dlg.solid_btn_aree.clicked.connect(self.lancia_consolida_aree_dlg)'''
        
        #self.dlg_compare.comboBoxFromPoint.clear()
        #self.dlg_compare.fileBrowse_btn.clicked.connect(self.controlla_connessioni)
        
        #SELEZIONA CARTELLA
        self.dlg_config.dirBrowse_txt.clear()
        self.dlg_config.dirBrowse_txt_parziale.clear()
        self.dlg_config.dirBrowse_btn.clicked.connect(self.select_output_dir)
        self.dlg_config.dirBrowse_btn_parziale.clicked.connect(self.select_output_dir_parziale)
        #Seleziono layer SCALA per inizializza un nuovo progetto da zero:
        #self.dlg_config.shpBrowse_btn.clicked.connect(self.select_shp_scala)
        #self.dlg_config.cavoBrowse_btn.clicked.connect(self.select_shp_cavo)
        #Ad ogni nuova riapertura del pannello di configurazione del progetto disabilito alcuni pannelli:
        self.dlg_config.import_DB.setEnabled(False);
        #self.dlg_config.variabili_DB.setEnabled(False);
        #Verifico se i dati sono o meno gia' importati sul DB escludendo la doppia scelta:
        self.dlg_config.no_import.clicked.connect(self.toggle_no_import)
        self.dlg_config.si_import.clicked.connect(self.toggle_si_import)
        self.dlg_config.si_import_parziale.clicked.connect(self.toggle_si_import_parziale)
        #che tipo di dati sto caricando e come vanno associati gli shp alle tabelle standard del PNI?
        #self.dlg_config.buttonGroup.buttonClicked.connect(self.toggle_ced_element)
        
        #self.dlg_config.si_inizializza.clicked.connect(self.toggle_si_inizializza)
        #Azioni sul tasto import per spostare gli shp su DB:
        self.dlg_config.import_shp.clicked.connect(self.import_shp2db)
        self.dlg_config.import_shp_parziale.clicked.connect(self.import_shp2db_parziale)
        #Azioni sul tasto import_scala per inizializzare un nuovo progetto:
        #self.dlg_config.import_scala.clicked.connect(self.inizializza_DB)
        
        #self.dlg_export.dirBrowse_btn.clicked.connect(self.select_output_dir_export)
        #self.dlg_export.exportBtn.clicked.connect(self.exportDB)
        
        #self.dlg_cloneschema.cloneschemaBtn.clicked.connect(self.cloneschemaDB)
        
        #self.dlg_append.shpBrowse_btn.clicked.connect(self.select_shp_scala_append)
        #self.dlg_append.importBtn.clicked.connect(self.append_scala)
        #self.dlg_append.importBtn_DbManager.clicked.connect(self.append_scala_DbManager)
        
        #AZIONO PULSANTE PERSONALIZZATO:
        #self.dlg_config.aggiorna_variabiliBtn.clicked.connect(self.inizializzaDB)
        #self.dlg_config.importBtn.clicked.connect(self.load_layers_from_db)
        self.dlg_config.createBtn.clicked.connect(self.load_project_from_db)
        
        #AZIONO pulsante per TESTARE CONNESSIONE AL DB:
        self.dlg_config.testBtn.clicked.connect(self.test_connection)
        self.dlg_config.testBtn_schema.clicked.connect(self.test_schema)
        
        #AZIONO i vari pulsanti della maschera dlg_solid:
        #self.dlg_solid.calcola_fibre_btn.clicked.connect(self.lancia_calcola_fibre)
        #self.dlg_solid.calcola_route_btn.clicked.connect(self.lancia_calcola_route)
        #
        #self.dlg_solid.start_routing_btn.clicked.connect(self.lancia_inizializza_routing)
        #self.dlg_solid.associa_scale.clicked.connect(self.lancia_scale_routing)
        #self.dlg_solid.associa_pta.clicked.connect(self.lancia_pta_routing)
        #self.dlg_solid.associa_giunti.clicked.connect(self.lancia_giunti_routing)
        #self.dlg_solid.associa_pd.clicked.connect(self.lancia_pd_routing)
        #self.dlg_solid.associa_pfs.clicked.connect(self.lancia_pfs_routing)
        #self.dlg_solid.associa_pfp.clicked.connect(self.lancia_pfp_routing)
        
        #Nella versione 4.4 riporto la funzione consolida_aree sotto il routing:
        #self.dlg_solid.solid_btn_aree.clicked.connect(self.lancia_consolida_aree)
        #Nella versione 4.3 sostituisco questo pulsante con quello che verifica che tutti i nodi della rete siano associati:
        #self.dlg_solid.solid_btn_aree.clicked.connect(self.check_grouping_from_user)
        
        #self.dlg_solid.reset_fibre_btn.clicked.connect(self.lancia_reset_all)
        #self.dlg_solid.popola_cavo_btn.clicked.connect(self.lancia_popola_cavo)
        
        #Apro un link esterno per l'help - come si fa ad interagire con i pulsanti di default di QT? Mistero..
        help_button = QDialogButtonBox.Help #16777216
        Utils.logMessage('help'+str(help_button))
        #QObject.connect(self.dlg_help.help_button, SIGNAL("clicked()"), self.help_open)
        #self.dlg_help.help_button.connect(self.help_open)
        #self.dlg_help.connect(help_button, SIGNAL("clicked()"), self.help_open)
        #Richiesta di Andrea del 17/10/2017 da GitHub: rimuovo il pulsante che rimanda ad un sito esterno:
        #self.dlg_help.help_btn.clicked.connect(self.help_open)
        
        #Popolo il menu a tendina con i layer da associare:
        #for frompoint in self.FROM_POINT:
        #    self.dlg_compare.comboBoxFromPoint.addItem(frompoint)
        #Disabilito la prima opzione - come??
        #idx = self.dlg_compare.comboBoxFromPoint.findText(self.FROM_POINT[0])
        #self.dlg_compare.comboBoxFromPoint.setCurrentIndex(idx)
        
        #Proviamo a disabilitare/nascondere un item:
        #self.dlg.comboBoxToPoint.setItemData(2, False, -1); #niente...
        
    def pageProcessed(self, progressBar):
        """Increment the page progressbar."""
        progressBar.setValue(progressBar.value() + 1)
    
    '''Richiesta di Andrea del 17/10/2017 da GitHub: rimuovo il pulsante che rimanda ad un sito esterno:
    def help_open(self):
        #QMessageBox.information(self.dlg_help, self.dlg_help.windowTitle(), "Ciao help!")
        url = "http://webgis.map-hosting.it/enel/Help%20Qgis%20App.pdf"
        webbrowser.open(url, new=0, autoraise=True)
    '''
    
    #def toggle_ced_element(self):
    #    tab_attivo = self.dlg_config.ced_radioButton.isChecked()
    #    if (tab_attivo==True):
    #        self.dlg_config.el_stackedWidget.setCurrentIndex(0)
    #    else:
    #        self.dlg_config.el_stackedWidget.setCurrentIndex(1)
    
    def toggle_no_import(self):
        tab_attivo = self.dlg_config.no_import.isChecked()
        if (tab_attivo==True):
            self.dlg_config.si_import.setChecked(False)
            self.dlg_config.si_import_parziale.setChecked(False)
            #self.dlg_config.si_inizializza.setChecked(False)
            #self.dlg_config.variabili_DB.setEnabled(True) #attivo il toolbox delle variabili
            #self.dlg_config.importBtn.setEnabled(False) #attivo il pulsante di caricamento layer da DB sulla TOC
            self.dlg_config.createBtn.setEnabled(True) #attivo il pulsante di creazione e caricamento nuovo progetto con i dati da DB
        else:
            #self.dlg_config.si_import.setChecked(True) #insomma funziona alla stregua di un radio_button
            #self.dlg_config.si_import_parziale.setChecked(True)
            #self.dlg_config.variabili_DB.setEnabled(False)
            #self.dlg_config.importBtn.setEnabled(False)
            self.dlg_config.createBtn.setEnabled(False)
            
    def toggle_si_import(self):
        tab_attivo = self.dlg_config.si_import.isChecked()
        if (tab_attivo==True):
            self.dlg_config.no_import.setChecked(False)
            self.dlg_config.si_import_parziale.setChecked(False)
            #self.dlg_config.si_inizializza.setChecked(False)
            #self.dlg_config.variabili_DB.setEnabled(False)
            #self.dlg_config.importBtn.setEnabled(False)
            self.dlg_config.createBtn.setEnabled(False)
        else:
            #self.dlg_config.no_import.setChecked(True) #insomma funziona alla stregua di un radio_button
            #self.dlg_config.variabili_DB.setEnabled(True) #attivo il toolbox delle variabili
            #self.dlg_config.importBtn.setEnabled(False) #attivo il pulsante di caricamento layer da DB sulla TOC
            self.dlg_config.createBtn.setEnabled(True) #attivo il pulsante di creazione e caricamento nuovo progetto con i dati da DB
    
    def toggle_si_import_parziale(self):
        tab_attivo = self.dlg_config.si_import_parziale.isChecked()
        if (tab_attivo==True):
            self.dlg_config.no_import.setChecked(False)
            self.dlg_config.si_import.setChecked(False)
            self.dlg_config.createBtn.setEnabled(False)
        else:
            self.dlg_config.createBtn.setEnabled(True) #attivo il pulsante di creazione e caricamento nuovo progetto con i dati da DB
            
    def toggle_si_inizializza(self):
        tab_attivo = self.dlg_config.si_inizializza.isChecked()
        if (tab_attivo==True):
            self.dlg_config.no_import.setChecked(False)
            self.dlg_config.si_import.setChecked(False)
            self.dlg_config.si_import_parziale.setChecked(False)
            self.dlg_config.variabili_DB.setEnabled(False)
            #self.dlg_config.importBtn.setEnabled(False)
            self.dlg_config.createBtn.setEnabled(False)
        else:
            self.dlg_config.no_import.setChecked(False)
            self.dlg_config.si_import.setChecked(False)
            self.dlg_config.si_import_parziale.setChecked(False)
            self.dlg_config.variabili_DB.setEnabled(False) #attivo il toolbox delle variabili
            #self.dlg_config.importBtn.setEnabled(False) #attivo il pulsante di caricamento layer da DB sulla TOC
            self.dlg_config.createBtn.setEnabled(False)

    def tracking_sql(self, sql_track_file, schemaDB, cur, test_conn):
        with open(sql_track_file, 'r', encoding='utf-8-sig') as file:
            filedata = file.read()
        # Replace the target string
        filedata = filedata.replace('schemaDB', schemaDB)
        cur.execute( filedata )
        test_conn.commit()
    
    def crea_progetto_reindirizzando_il_template(self, layers_from_project_template, ced_checked, layer_on_DB, project, dirname_text):
        for layer_imported in layers_from_project_template.values():
            #new_uri = "%s key=gidd table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, layer_imported.name().lower())
            #mappa_valori non la ricarico perche' e' comune a tutti i progetti --> ricarico questo controllo perche' su QGis 2.x da errore se lo lascio dopo
            if ('mappa_valori' in layer_imported.name()):
                continue
            elif ('elenco_prezzi' in layer_imported.name()):
                continue
            #sul progetto qgis i nomi dei layer sono in italiano. Uso il dizionario LAYER_NAME_PNI_aib per accoppiare i layer con la corretta tavola su DB:
            chiave_da_ricercare = 'PNI_' + layer_imported.name().upper()
            Utils.logMessage( 'layer_da_ricercare sul DB: %s' % str(chiave_da_ricercare) )
            if (ced_checked == True):
                tabella_da_importare = self.LAYER_NAME_PNI_ced[chiave_da_ricercare]
            else:
                #aggiungo queste tabelle che creo ad hoc per ogni nuovo progetto, cosi da non ricevere errori
                if ('punto_ripristino' in layer_imported.name()):
                    tabella_da_importare = 'punto_ripristino'
                elif ('nodo_virtuale' in layer_imported.name()):
                    tabella_da_importare = 'nodo_virtuale'
                elif ('user_log_map' in layer_imported.name()):
                    tabella_da_importare = 'user_log_map'
                else:
                    tabella_da_importare = self.LAYER_NAME_PNI_aib[chiave_da_ricercare]
            #2-confronto la lista delle tabelle su DB con la lista dei layer mappati e via via li sostituisco. Se il layer del progetto template NON E' PRESENTE  sul DB, salto e passo al successivo e TOLGO questo layer dal progetto:
            if (tabella_da_importare not in layer_on_DB):
                if (int(qgis_version[0]) >= 3):
                    QgsProject.instance().removeMapLayer(layer_imported.id())
                else:
                    QgsMapLayerRegistry.instance().removeMapLayer(layer_imported.id())
                continue
            else:
                #tolgo il layer da layer_on_DB:
                layer_on_DB.remove(tabella_da_importare)
            
            #mappa_valori non la ricarico perche' e' comune a tutti i progetti
            if ('mappa_valori' in layer_imported.name()):
                continue
            elif ('elenco_prezzi' in layer_imported.name()):
                continue
            elif (layer_imported.name() in self.sciape_error): #se lo shp non e' stato importato su DB poiche' non presente salto il suo reindirizzamento sul progetto QGis -- in realta' duplica l'azione precedente di ricerca del layer sul DB
                #se questa funzione viene richiamata senza caricare gli shp su DB, cioe creando un progetto da dati gia presenti su DB, allora sciape_error POTREBBE NON ESISTERE! per cui e' fondamentale la parte precedente in cui si recuperano effettivamente le tavole da DB
                continue
            else:
                new_uri = "%s key=gidd table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, tabella_da_importare)
            layer_imported.setDataSource(new_uri, layer_imported.name(), 'postgres')
            layer_imported.updateExtents()
            layer_imported.reload()

        Utils.logMessage( 'layer_on_DB dopo scrematura: %s' % str(layer_on_DB) )

        #3-quelle tavole che restano sul DB e che non sono state mappate, le aggiungo al progetto qgis con una visualizzazione di default
        for table in layer_on_DB:
            #NON carico eventuali tabelle _history nel caso fossero presenti sullo schema poiche' sono le tabelle in cui tengo traccia delle modifiche sui layer:
            if ('_history' in table):
                continue
            uri = "%s key=gidd table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, table.lower())
            layer_to_add = QgsVectorLayer(uri, table, "postgres")
            if (int(qgis_version[0]) >= 3):
                QgsProject.instance().addMapLayer(layer_to_add)
            else:
                QgsMapLayerRegistry.instance().addMapLayer(layer_to_add)
        
        #refresh del canvas e zoommo sull'estensione del progetto:
        iface.mapCanvas().refresh()
        iface.mapCanvas().zoomToFullExtent()
        #SALVO il nuovo progetto:
        if (int(qgis_version[0]) >= 3):
            project.write(dirname_text+"/"+schemaDB+'.qgs')
        else:
            project.write( QFileInfo(dirname_text+"/"+schemaDB+'.qgs') )
        
    def import_shp2db_parziale(self):
        self.import_shp2db(1)
    
    def import_shp2db(self, parziale=0):
        #dest_dir #percorso del DB SENZA lo schema pero'
        #bisogna prima importare gli shp sulla TOC di QGis...o almeno per semplificarsi la vita. Vedi:
        # http://ssrebelious.blogspot.it/2015/06/how-to-import-layer-into-postgis.html
        '''Se questo comando funziona potresti
        1-finestra in cui chiedi che andrai a svuotare la TOC
        2-svuoti la TOC
        3-carichi sulla TOC i vari shp
        4-li converti
        5-risvuoti la TOC
        '''
        #altrimenti devi importarti nel plugin l'eseguibile di shp2pgsql.exe. Pero a questo punto il plugin diventa piattaforma dipendente...
        
        shp_to_load = []
        self.dlg_config.import_progressBar.setValue(0)
        #self.dlg_config.import_progressBar.setMaximum(len(self.LAYER_NAME_PNI))
        
        #in base al tipo di progetto recupero i nomi dei layer da caricare:
        global tipo_progetto
        ced_checked = self.dlg_config.ced_radioButton.isChecked()
        if ced_checked:
            tipo_progetto = 'cd'
        else:
            tipo_progetto = 'ab'
        
        self.dlg_config.txtFeedback_import.setText("Sto caricando i dati, non interrompere, il processo potrebbe richiedere alcuni minuti...")
        global epsg_srid
        global sciape_error
        self.sciape_error = []
        #importo gli shp su db. Controllo che tutti i campi siano compilati prima di procedere:
        msg = QMessageBox()
        try:
            #schemaDB = self.dlg_config.schemaDB.text()
            #recupero lo schema dalla variabile globale definita sotto la funzione test_schema
            if (parziale==1): #cioe' carico solo alcuni dati su DB per creare poi il progetto col pulsante C funzione load_project_from_db
                dirname_text = self.dlg_config.dirBrowse_txt_parziale.text()
            else:
                dirname_text = self.dlg_config.dirBrowse_txt.text()
            
            if ( (dirname_text is None) or (dirname_text=='') ):
                raise NameError('Specificare il percorso di origine da cui prelevare gli shp!')
            #posso scegliere di caricare qualsiasi shp si trovi nella directory indicata:
            shp_counter = 0
            for file in os.listdir(dirname_text):
                if file.endswith(".shp"):
                    shp_to_load.append(file)
                    shp_counter += 1
            #Utils.logMessage( str(shp_to_load) )
            self.dlg_config.import_progressBar.setMaximum( shp_counter )
            
            #devo verificare che, in base al tipo di progetto scelto, siano presenti gli shp necessari per costruire il progetto
            if ced_checked:
                for sciape in self.LAYER_NAME_PNI_ced.values():
                    if sciape+'.shp' not in shp_to_load:
                        self.sciape_error.append(sciape)
            else:
                for sciape in self.LAYER_NAME_PNI_aib.values():
                    if sciape+'.shp' not in shp_to_load:
                        self.sciape_error.append(sciape)
            Utils.logMessage( 'shp NON presenti nella directory ma necessari alla composizione del progetto indicato: '+str(self.sciape_error) )
            
            #se ho scelto di caricare solo alcuni dati su DB per creare poi il progetto col pulsante C funzione load_project_from_db SALTO questo controllo
            if (parziale==1):
                self.sciape_error = []
            if len(self.sciape_error)>0:
                #SE nella lista sciape_error non ci sono solo layer opzionali, allora BLOCCO le successive operazioni. Altrimenti faccio scegliere all'utente:
                sciape_essenziali = []
                if ced_checked:
                    for sciape_mancanti in self.sciape_error:
                        if sciape_mancanti not in self.LAYER_OPZIONALI_ced:
                            sciape_essenziali.append(sciape_mancanti)
                else:
                    for sciape_mancanti in self.sciape_error:
                        if sciape_mancanti not in self.LAYER_OPZIONALI_aib:
                            sciape_essenziali.append(sciape_mancanti)
                if len(sciape_essenziali)>0:
                    raise NameError("Nella cartella di origine specificata non sono presenti alcuni layer fondamentali per la creazione del progetto: %s\nNon e' possibile continuare" % (str(sciape_essenziali)))
                msg.setText("ATTENZIONE!\nNella cartella di origine mancano degli shape che potrebbero servire alla composizione del progetto indicato. Cio' potrebbe causare degli errori nella generazione del progetto QGis. I dati verranno in ogni caso caricati nel DB nello schema specificato.\nGli shape mancanti risultano essere '%s'\nSicuro di aver indicato il progetto A&B o C&D correttamente?" % ( str(self.sciape_error) ))
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("incoerenza shape presenti e progetto indicato")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                retval = msg.exec_()
                if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
                    self.dlg_config.txtFeedback_import.setText("incoerenza shape presenti e progetto indicato. Abbandono dell'operazione di import per scelta dell'utente")
                    Utils.logMessage("incoerenza shape presenti e progetto indicato. Abbandono dell'operazione di import per scelta dell'utente")
                    return 0
        
        except NameError as err:
            msg.setText(err.args[0])
            msg.setIcon(QMessageBox.Critical)
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            self.dlg_config.txtFeedback_import.setText(err.args[0])
            return 0
        except ValueError:
            self.dlg_config.txtFeedback_import.setText('Specificare TUTTE le variabili')
            return 0
        except SystemError as e:
            Utils.logMessage('Errore di sistema!')
            self.dlg_config.txtFeedback_import.setText('Errore di sistema!')
            return 0
        else: #...se tutto ok proseguo:
            #Recupero i layers dalla TOC per svuotarla:
            msg.setText("ATTENZIONE! Con questa azione svuoterai la TOC di QGis per caricare temporaneamente i nuovi shp, e se gli shp esistono gia' nello schema selezionato verranno SOVRASCRITTI con gli shp selezionati: procedere?")
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Svuotare la TOC e lo schema dai layers attuali?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            retval = msg.exec_()
            if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
                return 0
            elif (retval == 16384): #l'utente HA CLICCATO YES. Svuoto la TOC
                #recupero layer in ordine dalla TOC
                if (int(qgis_version[0]) >= 3):
                    layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
                else:
                    layers = self.iface.legendInterface().layers()
                #tolgo i layer dalla TOC
                for layer in layers:
                    if (int(qgis_version[0]) >= 3):
                        QgsProject.instance().removeMapLayer(layer.id())
                    else:
                        QgsMapLayerRegistry.instance().removeMapLayer(layer.id())
                
            
            #ciclo dentro gli shp trovati nella cartella e li carico su QGis:
            lista_layer_to_load = []
            shp_name_to_load = []
            for shps in shp_to_load:
                qgs_shp = QgsVectorLayer(dirname_text+"/"+shps, shps[:-4], "ogr")
                lista_layer_to_load.append( qgs_shp )
                shp_name_to_load.append( shps[:-4].lower() )
            if (int(qgis_version[0]) >= 3):
                QgsProject.instance().addMapLayers(lista_layer_to_load)
            else:
                QgsMapLayerRegistry.instance().addMapLayers(lista_layer_to_load)
            
            #Li spengo di default e li importo direttamente sul DB:
            crs = None
            test_conn = None
            options = {}
            options['lowercaseFieldNames'] = True
            options['overwrite'] = True
            options['forceSinglePartGeometryType'] = True
            try:
                self.dlg_config.txtFeedback_import.setText("Sto importando i dati...")
                for layer_loaded in lista_layer_to_load:
                    #self.iface.legendInterface().setLayerVisible(layer_loaded, False) #tralascio in QGis3
                    layer_loaded_geom = layer_loaded.wkbType()
                    
                    '''
                    #PNI: in alcuni casi lo shp ha colonna gid ma non e' ben compilata. Elimino il campo-ma come?
                    gid_esistente = layer_loaded.fieldNameIndex('gid')
                    gid_idx_List = list()
                    if (gid_esistente>-1):
                        Utils.logMessage("campo gid su shp gia' esistente, lo elimino")
                        gid_idx_List.append(gid_esistente)
                        #layer_loaded.dataProvider().deleteAttributes(gid_idx_List) #lo elimina proprio dallo shp!
                        #altra opzione: lo rinomino, ma lo shp deve entrare in editmode:
                        #layer_loaded.renameAttribute(gid_esistente, 'gid_old')
                    else:
                        Utils.logMessage("campo gid su shp non esistente: continuo")
                    '''

                    uri = None
                    '''
                    if layer_loaded_geom==4:
                        uri = "%s key=gid type=POINT table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, layer_loaded.name().lower())
                    elif layer_loaded_geom==1:
                        uri = "%s key=gid type=MULTIPOINT table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, layer_loaded.name().lower())
                    elif layer_loaded_geom==3:
                        uri = "%s key=gid type=MULTIPOLYGON table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, layer_loaded.name().lower())
                    elif layer_loaded_geom==2:
                        uri = "%s key=gid type=MULTILINESTRING table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, layer_loaded.name().lower())
                    '''
                    uri = "%s key=gidd table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, layer_loaded.name().lower())
                    Utils.logMessage('WKB: ' + str(layer_loaded_geom) + '; DEST_DIR: ' + str(dest_dir))
                    crs = layer_loaded.crs()
                    if (int(qgis_version[0]) >= 3):
                        error = QgsVectorLayerExporter.exportLayer(layer_loaded, uri, "postgres", crs, False, options=options)
                    else:
                        error = QgsVectorLayerImport.importLayer(layer_loaded, uri, "postgres", crs, False, False, options)
                    #recupero il codice EPSG dei layer importati, per creare le successive tabelle geometriche:
                    codice_srid = crs.postgisSrid()
                    
                    #my_layer is some QgsVectorLayer
                    #con_string = """dbname='postgres' host='some IP adress' port='5432' user='postgres' password='thepassword' key=my_id type=MULTIPOLYGON table="myschema"."mytable" (geom)"""
                    #err = QgsVectorLayerExporter.exportLayer(my_layer, con_string, 'postgres', QgsCoordinateReferenceSystem(epsg_no), False)
                    
                    if error[0] != 0:
                        #iface.messageBar().pushMessage(u'Error', error[1], QgsMessageBar.CRITICAL, 5)
                        #iface.messageBar().pushMessage(u'Error', error[1], Qgs.Critical, 5)
                        msg.setText("Errore nell'importazione. Vedere il dettaglio dell'errore, contattare l'amministratore")
                        msg.setDetailedText(error[1])
                        msg.setIcon(QMessageBox.Critical)
                        msg.setStandardButtons(QMessageBox.Ok)
                        msg.setWindowTitle("Errore nell'importazione!")
                        retval = msg.exec_()
                        self.dlg_config.txtFeedback_import.setText(error[1])
                        return 0
                    self.pageProcessed(self.dlg_config.import_progressBar) #increase progressbar
                
                #apro il cursore per leggere/scrivere sul DB:
                test_conn = psycopg2.connect(dest_dir)
                cur = test_conn.cursor()
                
                #Risetto il search_path originario perche forse se lo tiene in pancia quello vecchio:
                query_path = 'SET search_path = public;'
                cur.execute(query_path)
                # Make the changes to the database persistent
                test_conn.commit()
                
                #devo assegnare tutte le tavole di questo schema al nuovo gruppo operatore_r
                query_grant = "GRANT ALL ON ALL TABLES IN SCHEMA %s TO operatore_r;" % (schemaDB)
                Utils.logMessage('query_grant '+str(query_grant))
                cur.execute(query_grant)
                test_conn.commit()
                
                #compilo tabella public.tipo_progetti:
                query_tipo = """INSERT INTO public.tipo_progetti (nomeschema, tipo_progetto, creator) SELECT '%s', '%s', '%s' WHERE NOT EXISTS (SELECT nomeschema, tipo_progetto FROM public.tipo_progetti WHERE nomeschema='%s' AND tipo_progetto='%s');""" % (schemaDB, tipo_progetto, userDB, schemaDB, tipo_progetto)
                cur.execute(query_tipo)
                test_conn.commit()
                
                #SPATIAL INDEX
                #creo lo SPATIAL INDEX sugli shp appena caricati
                for shp_geoidx in shp_name_to_load:
                    query_spatial = "CREATE INDEX ON %s.%s USING gist (geom);" % (schemaDB, shp_geoidx)
                    cur.execute(query_spatial)
                    #il VACUUM sarebbe bene metterlo sulla macchina a crontab come operazione giornaliera
                    #query_vacuum = "VACUUM FULL ANALYZE %s.%s" % (schemaDB, row[0])
                    #cur.execute(query_vacuum)
                test_conn.commit() #committo la creazione dell'indice spaziale
                
                #Creo tabella vuota come da mail di Mocco del 31 marzo 2020:
                if (parziale==0):
                    query_ftth_cluster = """DROP TABLE IF EXISTS %s.ftth_cluster; CREATE TABLE %s.ftth_cluster (
                        identificativo integer,
                        oggetto character varying(100),
                        qta_min double precision,
                        unita character varying(100),
                        prezzo_unita_euro double precision,
                        qta_as_built double precision,
                        qta_in_costruzione double precision,
                        qta_progettato double precision,
                        qta_realizzato double precision,
                        totale double precision,
                        vertice_uno character varying(100),
                        vertice_due character varying(100),
                        largh_ripristino_cm double precision,
                        sup_ripristino_mq double precision
                        );
                    GRANT ALL ON TABLE %s.ftth_cluster TO operatore_r;""" % (schemaDB, schemaDB, schemaDB)
                    cur.execute(query_ftth_cluster)
                    test_conn.commit()
                    query_nodi_punti = """DROP TABLE IF EXISTS %s.punto_ripristino; CREATE TABLE %s.punto_ripristino (
                        gidd serial PRIMARY KEY,
                        geom geometry(Point, %s),
                        id_tratta character varying(200),
                        listino character varying(20) DEFAULT 'OF- INF-9.3',
                        foto character varying(200));
                    GRANT ALL ON TABLE %s.punto_ripristino TO operatore_r;
                        DROP TABLE IF EXISTS %s.nodo_virtuale; CREATE TABLE %s.nodo_virtuale (
                        gidd serial PRIMARY KEY,
                        geom geometry(Point, %s),
                        id_tratta character varying(200),
                        listino character varying(200),
                        data date);
                    GRANT ALL ON TABLE %s.nodo_virtuale TO operatore_r;
                        DROP TABLE IF EXISTS %s.user_log_map; CREATE TABLE %s.user_log_map (
                        gidd serial PRIMARY KEY,
                        layer varchar(20) NOT NULL,
                        gid_feature int4,
                        id_user int4,
                        user_log varchar(50) NOT NULL,
                        azione varchar(30) NOT NULL,
                        progetto varchar(100) NOT NULL,
                        data timestamp(6) DEFAULT now(),
                        fid varchar(100) COLLATE pg_catalog.default);
                    GRANT ALL ON TABLE %s.user_log_map TO operatore_r;""" % (schemaDB, schemaDB, codice_srid, schemaDB, schemaDB, schemaDB, codice_srid, schemaDB, schemaDB, schemaDB, schemaDB)
                    cur.execute(query_nodi_punti)
                    test_conn.commit()
                
                #TRACKING modifiche sui layer
                #devo attivare gli script in base ai layer effettivamente caricati
                Utils.logMessage('shp_name_to_load, per i quali ho anche creato indice spaziale '+str(shp_name_to_load))
                query_path = "SET search_path = %s, pg_catalog;" % (schemaDB)
                Utils.logMessage('Adesso se il caso creo il tracking sulle tabelle nello schema ' + str(schemaDB))
                cur.execute(query_path)
                
                #PROGETTI A&B
                if ('underground_route' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_tratta.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('aerial_route' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_tratta_aerea.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('mit_terminal_enclosure' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_colonnine.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('uub' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_pozzetti.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('sheat_splice' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_giunti.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('sheat_with_loc' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_cavi.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('sheath_splice' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_giunti_sheath.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('sheath_with_loc' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_cavi_sheath.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('mit_bay' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_mit_bay.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                
                #PROGETTI C&D
                if ('ebw_cavo' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_ebw_cavo.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('ebw_route' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_ebw_route.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                if ('ebw_location' in shp_name_to_load):
                    sql_track_file = self.plugin_dir + '/tracking_edit_postgis_ebw_location.sql'
                    self.tracking_sql(sql_track_file, schemaDB, cur, test_conn)
                
                #se sto caricando solo alcuni dati su DB per creare poi il progetto col pulsante C funzione load_project_from_db, allora salto la creazione del progetto ed esco da questa funzione
                if (parziale==1):
                    self.dlg_config.txtFeedback_import.setText("Dati importati con successo! Puoi passare alla creazione del progetto col pulsante C")
                    return 1
                
                self.dlg_config.txtFeedback_import.setText("Dati importati con successo! Passiamo alla creazione del progetto...")
                #a questo punto dovrei importare il progetto template in base al tipo di dati importati
                project = QgsProject.instance()
                #in base al tipo di progetto recupero il progetto da caricare:
                ced_checked = self.dlg_config.ced_radioButton.isChecked()
                if (ced_checked == True):
                    if (int(qgis_version[0]) >= 3):
                        project.read(self.plugin_dir + "/pni2_CeD_db.qgs")
                    else:
                        project.read( QFileInfo(self.plugin_dir + "/pni2_CeD_db.qgs") )
                else:
                    if (int(qgis_version[0]) >= 3):
                        project.read(self.plugin_dir + "/pni2_AiB_db.qgs")
                    else:
                        project.read( QFileInfo(self.plugin_dir + "/pni2_AiB_db.qgs") )
                #ora modifico i dataSource di questi progetti puntandoli allo schema appena creato:
                #layers_from_project_template = iface.mapCanvas().layers()
                #ATTENZIONE!!! iface.mapCanvas().layers() recupera solo i layers visibili, per questo motivo nel template li ho messi tutti visibili
                #per ovviare a questo limite posso provare questa chiamata:
                if (int(qgis_version[0]) >= 3):
                    layers_from_project_template = QgsProject.instance().mapLayers()
                else:
                    layers_from_project_template = QgsMapLayerRegistry.instance().mapLayers()
                #ATTENZIONE!!! Se non dovesse esserci una tabella corrispondente su postgres QGis crasha direttamente e anche con try/except non si riesce a intercettare questo errore!!
                #per ovviare a questo limite, nel caso in cui vi siano effettivamente questi layer sul DB:
                #1-scarico la lista delle tavole con the_geom dal DB
                layer_on_DB = list()
                #cur.execute( "SELECT table_name FROM information_schema.tables WHERE table_schema = '%s' AND table_type = 'BASE TABLE';" % (schemaDB) )
                cur.execute( "SELECT f_table_name FROM public.geometry_columns WHERE f_table_schema='%s';" % (schemaDB) )
                dataDB = cur.fetchall()
                for row in dataDB:
                    Utils.logMessage( 'Tabella sul DB: %s' % (row[0]) )
                    layer_on_DB.append(row[0]) #avendo il risultato una sola colonna cioe' [0]
                Utils.logMessage( 'layer_on_DB: %s' % str(layer_on_DB) )
                
                cur.close()
                #test_conn.commit() #committo la creazione dell'indice spaziale
                test_conn.close()
                
                self.crea_progetto_reindirizzando_il_template(layers_from_project_template, ced_checked, layer_on_DB, project, dirname_text)

            except psycopg2.Error as e:
                Utils.logMessage(e.pgerror)
                self.dlg_config.txtFeedback_import.setText("Errore su DB, vedere il log o contattare l'amministratore")
                test_conn.rollback()
                return 0
            except SystemError as e:
                Utils.logMessage('Errore di sistema!')
                self.dlg_config.txtFeedback_import.setText('Errore di sistema!')
                test_conn.rollback()
                return 0
            else:
                self.dlg_config.txtFeedback_import.setText("Dati importati e progetto creato con successo in " + dirname_text+"/"+schemaDB+".qgs")
                #Abilito le restanti sezioni e pulsanti
                self.dlg_config.chkDB.setEnabled(False)
                self.dlg_config.import_DB.setEnabled(False)
                #self.dlg_config.importBtn.setEnabled(True) #questo pulsante NON dovrebbe piu' servire

            finally:
                if test_conn is not None:
                    try:
                        test_conn.close()
                    except:
                        msg.setText("La procedura e' andata a buon fine oppure la connessione al server si e' chiusa inaspettatamente: controlla il messaggio nella casella 'controllo'")
                        msg.setIcon(QMessageBox.Warning)
                        msg.setStandardButtons(QMessageBox.Ok)
                        retval = msg.exec_()
    
    def load_project_from_db(self):
        #creo questa funzione a parte nel caso voglia staccare la fase in cui carico gli shp su DB da quella in cui creo il progetto
        #questa funzione puo' risultare utile nel caso in cui abbia gia' caricato i layer su DB, ma abbia apportato delle modifiche ai progetti qgs_template oppure abbia caricato un nuovo layer su DB e non voglia ripetere la fase di caricamento, ma solo la fase di creazione del progetto
        #schemaDB = self.dlg_config.schemaDB.text() #recupero lo schema da cui prelevare le tabelle
        #ma lo recupero dalla variabile globale definita sotto la funzione test_schema
        nameDB = self.dlg_config.nameDB.text()
        dirname_text = self.dlg_config.dirBrowse_txt.text()
        if ( (dirname_text is None) or (dirname_text=='') ):
            dirname_text = os.getenv("HOME")
        global epsg_srid
        
        try:
            #a questo punto dovrei importare il progetto template in base al tipo di dati importati
            project = QgsProject.instance()
            #in base al tipo di progetto recupero il progetto da caricare:
            ced_checked = self.dlg_config.ced_radioButton.isChecked()
            if (ced_checked == True):
                if (int(qgis_version[0]) >= 3):
                    project.read(self.plugin_dir + "/pni2_CeD_db.qgs")
                else:
                    project.read( QFileInfo(self.plugin_dir + "/pni2_CeD_db.qgs") )
            else:
                if (int(qgis_version[0]) >= 3):
                    project.read(self.plugin_dir + "/pni2_AiB_db.qgs")
                else:
                    project.read( QFileInfo(self.plugin_dir + "/pni2_AiB_db.qgs") )
            #ora modifico i dataSource di questi progetti puntandoli allo schema appena creato:
            #layers_from_project_template = iface.mapCanvas().layers()
            #ATTENZIONE!!! iface.mapCanvas().layers() recupera solo i layers visibili, per questo motivo nel template li ho messi tutti visibili
            #per ovviare a questo limite posso provare questa chiamata:
            if (int(qgis_version[0]) >= 3):
                layers_from_project_template = QgsProject.instance().mapLayers()
            else:
                layers_from_project_template = QgsMapLayerRegistry.instance().mapLayers()
            #ATTENZIONE!!! Se non dovesse esserci una tabella corrispondente su postgres QGis crasha direttamente e anche con try/except non si riesce a intercettare questo errore!!
            #per ovviare a questo limite, nel caso in cui vi siano effettivamente questi layer sul DB:
            #apro il cursore per leggere/scrivere sul DB:
            test_conn = psycopg2.connect(dest_dir)
            cur = test_conn.cursor()
            #1-scarico la lista delle tavole con the_geom dal DB
            layer_on_DB = list()
            cur.execute( "SELECT table_name FROM information_schema.tables WHERE table_schema = '%s' AND table_type = 'BASE TABLE';" % (schemaDB) )
            dataDB = cur.fetchall()
            for row in dataDB:
                Utils.logMessage( 'Tabella sul DB: %s' % (row[0]) )
                layer_on_DB.append(row[0]) #avendo il risultato una sola colonna cioe' [0]
            Utils.logMessage( 'layer_on_DB: %s' % str(layer_on_DB) )
            cur.close()
            test_conn.close()
            
            self.crea_progetto_reindirizzando_il_template(layers_from_project_template, ced_checked, layer_on_DB, project, dirname_text)
        
        except SystemError as e:
            debug_text = "Qualcosa e' andata storta nel caricare i layer da DB. Forse il servizio per il DB indicato non esiste? Rivedere i dati e riprovare"
            #in realta' questo errore non viene gestito, inizia a chiedere la pwd del servizio prima!
            self.dlg_config.txtFeedback.setText(debug_text)
            return 0
        else:
            self.dlg_config.txtFeedback.setText('Creazione e caricamento del progetto riusciti. Progetto salvato in' + dirname_text+'/'+schemaDB+'.qgs')
            return 1
    
    def load_layers_from_db(self):
        #carica i layer mappati in LAYER_NAME_PNI_xxx con il loro stile ma in ordine casuale cioe' senza seguire i progetti template
        #direi che per il momento questa funzione si puo' disattivare
        schemaDB = self.dlg_config.schemaDB.text() #recupero lo schema da cui prelevare le tabelle
        nameDB = self.dlg_config.nameDB.text()
        global epsg_srid
        #recupero layer in ordine dalla TOC
        if (int(qgis_version[0]) >= 3):
            layers = [tree_layer.layer() for tree_layer in QgsProject.instance().layerTreeRoot().findLayers()]
        else:
            layers = self.iface.legendInterface().layers()
        #tolgo i layer dalla TOC
        for layer in layers:
            if (int(qgis_version[0]) >= 3):
                QgsProject.instance().removeMapLayer(layer.id())
            else:
                QgsMapLayerRegistry.instance().removeMapLayer(layer.id())
        
        #in base al tipo di progetto recupero i nomi dei layer da caricare:
        ced_checked = self.dlg_config.ced_radioButton.isChecked()
        
        try:
            #ciclo dentro la variabile LAYER_NAME e carico i layer da DB:
            #for key, value in sorted(self.LAYER_NAME_PNI.items()): #casualmente l'ordine alfabetico ci piace...altrimenti devi usare "from collections import OrderedDict, LAYER_NAME_PNI=OrderedDict(), LAYER_NAME_PNI['SCALA']='Scala'" etc..
            #nel caso del progetto PNI provo a non ordinare il dict ma uso l'orderedDict:
            '''
            for key, value in self.LAYER_NAME_PNI.items():
                if ( (key=="GIUNTO_F_dev") | (key=="PTA") | (key=="SCALA_F") | (key=="PD_F") | (key=="SCALA_append") ):
                    continue #evito di caricare 2/3 volte il layer GIUNTO
                Utils.logMessage('nome layerDB da caricare: ' + value)
                uri = "%s key=gidd table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, value.lower())
                #provo a caricare il layer da un service:
                #uri = "dbname='%s' service='%s_service_operatore' user='operatore' sslmode=disable key=gid table=\"%s\".\"%s\" (geom) sql=" % (nameDB, nameDB, schemaDB, value.lower())
                layer = QgsVectorLayer(uri, value, "postgres")
                QgsMapLayerRegistry.instance().addMapLayer(layer)
                layer.loadNamedStyle(os.getenv("HOME")+'/.qgis2/python/plugins/qgis2db/qml_base/%s.qml' % (value))
                crs = layer.crs()
            '''
            
            if (ced_checked == True):
                for key, value in self.LAYER_NAME_PNI_ced.items():
                    Utils.logMessage('nome layerDB da caricare: ' + value)
                    uri = "%s key=gidd table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, value.lower())
                    #provo a caricare il layer da un service:
                    #uri = "dbname='%s' service='%s_service_operatore' user='operatore' sslmode=disable key=gid table=\"%s\".\"%s\" (geom) sql=" % (nameDB, nameDB, schemaDB, value.lower())
                    layer = QgsVectorLayer(uri, value, "postgres")
                    if (int(qgis_version[0]) >= 3):
                        QgsProject.instance().addMapLayer(layer)
                    else:
                        QgsMapLayerRegistry.instance().addMapLayer(layer)
                    #layer.loadNamedStyle(os.getenv("HOME")+'/.qgis2/python/plugins/qgis2db/qml_base/%s.qml' % (value))
                    layer.loadNamedStyle( self.plugin_dir + '/qml_base/ced/%s.qml' % (value))
                    crs = layer.crs()
            else:
                for key, value in self.LAYER_NAME_PNI_aib.items():
                    Utils.logMessage('nome layerDB da caricare: ' + value)
                    uri = "%s key=gidd table=\"%s\".\"%s\" (geom) sql=" % (dest_dir, schemaDB, value.lower())
                    #provo a caricare il layer da un service:
                    #uri = "dbname='%s' service='%s_service_operatore' user='operatore' sslmode=disable key=gid table=\"%s\".\"%s\" (geom) sql=" % (nameDB, nameDB, schemaDB, value.lower())
                    layer = QgsVectorLayer(uri, value, "postgres")
                    if (int(qgis_version[0]) >= 3):
                        QgsProject.instance().addMapLayer(layer)
                    else:
                        QgsMapLayerRegistry.instance().addMapLayer(layer)
                    #layer.loadNamedStyle(os.getenv("HOME")+'/.qgis2/python/plugins/qgis2db/qml_base/%s.qml' % (value))
                    layer.loadNamedStyle( self.plugin_dir + '/qml_base/aib/%s.qml' % (value))
                    crs = layer.crs()
            
            #ridefinisco la variabile SRID per il progetto:
            epsg_srid = int(crs.postgisSrid())
            self.epsg_srid = epsg_srid
        
        except SystemError as e:
            debug_text = "Qualcosa e' andata storta nel caricare i layer da DB. Forse il servizio per il DB indicato non esiste? Rivedere i dati e riprovare"
            #in realta' questo errore non viene gestito, inizia a chiedere la pwd del servizio prima!
            self.dlg_config.txtFeedback.setText(debug_text)
            return 0
        else:
            self.dlg_config.txtFeedback.setText('Caricamento layer da DB riuscito!')
            return 1
    
    
    #--------------------------------------------------------------------------
    #PARTE SUL ROUTING
    def check_grouping_from_user(self):
        #Richiamo la stessa funzione sotto "lancia_popola_cavo", ma qui la faccio lanciare all'utente quando vuole per controllare quali elementi ancora necessitano di un'associazione:
        connInfo = SCALE_layer.source()
        result_check_grouping = db_solid.check_grouping(self, connInfo, theSchema)
        if (result_check_grouping==0):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Alcuni punti della rete non risultano associati a PFS o nel caso di PFS a PFP. Controllare i log di QGis per maggiori dettagli')
            return 0
        else:
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Controllo grouping effettuato: nessuna anomalia')
            return
         
    '''
    #Nella versione 4.4 lancio la funzione "lancia_consolida_aree". questa sarebeb quella lanciata dal core_widget, la commento
    def lancia_consolida_aree_dlg(self):
        connInfo = SCALE_layer.source()
        dest_dir = self.estrai_param_connessione(connInfo)
        #lancio la funzione aggiungendo la finestra sulla quale riportare le info in modo tale da poter provare anche il bottone da un'altra GUI.
        #result_calcolo = db_solid.consolida_aree(self, connInfo, theSchema, self.dlg)
        result_calcolo = db_solid.consolida_aree(self, connInfo, theSchema, self.dockwidget)
        if (result_calcolo < 100 and result_calcolo > 0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFS con tanti punti")
        elif (result_calcolo >= 100 and result_calcolo < 1000):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFS senza punti")
        elif (result_calcolo >= 1000 and result_calcolo < 10000):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFP con tanti punti")
        elif (result_calcolo >= 10000):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFP senza punti")
        elif (result_calcolo == 0):
            QMessageBox.information(self.dock, self.dock.windowTitle(), "Aree PFS e PFP aggiornate con successo senza alcun eccezione!")
        elif (result_calcolo == -1):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), "Aree PFS e PFP aggiornate con successo! Qualche area PFS ha pero' superato le UI massime consentite. Vedere il messaggio nella finestra")
        elif (result_calcolo == -2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), "Aree PFS e PFP aggiornate con successo!\n Qualche area PFP ha pero' superato il numero di PD massimo consentito. Vedere il messaggio nella finestra")
    '''
            
    def lancia_consolida_aree(self):
        connInfo = SCALE_layer.source()
        #lancio la funzione aggiungendo la finestra sulla quale riportare le info in modo tale da poter provare anche il bottone da un'altra GUI.
        continuo_coi_pozzetti = 0
        result_calcolo = db_solid.consolida_aree(self, connInfo, theSchema, self.dlg_solid)
        if (result_calcolo < 100 and result_calcolo > 0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFS con tanti punti")
        elif (result_calcolo >= 100 and result_calcolo < 1000):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFS senza punti")
        elif (result_calcolo >= 1000 and result_calcolo < 10000):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFP con tanti punti")
        elif (result_calcolo >= 10000):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, trovata area PFP senza punti")
        elif (result_calcolo == 0):
            QMessageBox.information(self.dock, self.dock.windowTitle(), "Aree PFS e PFP aggiornate con successo senza alcun eccezione!")
            continuo_coi_pozzetti = 1
        elif (result_calcolo == -1):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), "Aree PFS e PFP aggiornate con successo! Qualche area PFS ha pero' superato le UI massime consentite. Vedere il messaggio nella finestra")
            continuo_coi_pozzetti = 1
        elif (result_calcolo == -2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), "Aree PFS e PFP aggiornate con successo!\n Qualche area PFP ha pero' superato il numero di PD massimo consentito. Vedere il messaggio nella finestra")
            continuo_coi_pozzetti = 1
        #Continuo con il popolamento del layer "pozzetti"?
        #Secondo mail di Gatti del 16 Gennaio 2018 questa fase la salto
        '''
        if (continuo_coi_pozzetti==1):
            result_pozzetti = db_solid.popola_pozzetti(self, connInfo, theSchema, self.dlg_solid)
            if (result_pozzetti==0):
                QMessageBox.critical(self.dock, self.dock.windowTitle(), "Attenzione, qualcosa e' andato storto nel popolare il layer pozzetto. Consultare i log di QGis.")
            elif (result_pozzetti==1):
                QMessageBox.information(self.dock, self.dock.windowTitle(), "Layer pozzetto popolato correttamente!")
        else:
            QMessageBox.warning(self.dock, self.dock.windowTitle(), "Layer 'pozzetti' NON popolato in quanto sono state riscontrate delle anomalie sulle aree PFS e PFP.")
        '''
        
    
    def lancia_calcola_fibre(self):
        #step intermedio per passare alcune variabili alla funzione finale:
        #Inizializzo un layer di QGis giusto solo per prendermi i parametri di connessione:
        #self.inizializza_layer();
        connInfo = SCALE_layer.source()
        self.dlg_solid.txtFeedback.setText("Elaborazione in corso NON chiudere il programma...")
        #QMessageBox.information(self.dock, self.dock.windowTitle(), "Il programma impieghera' un po' di tempo ad eseguire il routing: non chiudere il programma, e avere pazienza...")
        result_calcolo = db_solid.calcola_fibre(self, connInfo, theSchema, self.epsg_srid)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Routing non eseguito!')
            self.dlg_solid.txtFeedback.setText('Errore di sistema! Routing non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing avvenuto con successo!')
            self.dlg_solid.txtFeedback.setText('Routing avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), "Routing effettuato ma qualche punto della rete non e' stato associato al cavo: possibile errore nella geometria del cavo. Vedere log per sintesi delle coppie sorgente-obiettivo non correttamente abbinate")
            self.dlg_solid.txtFeedback.setText("Routing effettuato ma qualche punto della rete non e' stato associato al cavo: possibile errore nella geometria del cavo. Vedere log per sintesi delle coppie sorgente-obiettivo non correttamente abbinate")
        elif (result_calcolo==3):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Calcolo delle fibre per i cavi NON eseguito! Uno o piu' elementi del layer SCALA hanno n_ui<=0")
            self.dlg_solid.txtFeedback.setText("Calcolo delle fibre per i cavi NON eseguito! Uno o piu' elementi del layer SCALA hanno n_ui<=0")
        elif (result_calcolo==4):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Calcolo delle fibre per i cavi NON eseguito! Uno o piu' elementi del layer SCALA hanno n_ui NULL")
            self.dlg_solid.txtFeedback.setText("Calcolo delle fibre per i cavi NON eseguito! Uno o piu' elementi del layer SCALA hanno n_ui NULL")
            
    def lancia_calcola_route(self):
        connInfo = SCALE_layer.source()
        self.dlg_solid.txtFeedback.setText("Elaborazione in corso NON chiudere il programma...")
        result_calcolo = db_solid.calcola_route(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), "Errore di sistema! Cavoroute non calcolato! Probabilmente e' gia' stato calcolato oppure il layer cavo non e' stato inizializzato con successo. Vedere il log di sistema per maggiori informazioni. Nel caso provare a resettare tutto e ripetere la procedura dall'inizio.")
            self.dlg_solid.txtFeedback.setText("Errore di sistema! Cavoroute non calcolato! Forse esiste gia'? Vedere log, o resettare per ripetere daccapo l'operazione.")
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Cavoroute calcolato con successo!')
            self.dlg_solid.txtFeedback.setText('Cavoroute calcolato con successo!')

    def lancia_reset_all(self):
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.reset_all(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Reset del routing non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Reset del routing avvenuto con successo!')
    
    def lancia_popola_cavo(self):
        #popolo il layer cavo prendendo le geometrie da sottotratta. Svuoto e riempio ogni volta, elimino le colonne di troppo e di conseguenza resetto prima tutto:
        connInfo = SCALE_layer.source()
        
        msg = QMessageBox()
        msg.setText("Attenzione con questa operazione si procede al reset di tutto il routing!")
        msg.setInformativeText("Il layer CAVO viene svuotato e poi popolato prendendo le geometrie dal layer SOTTOTRATTA. Si desidera realmente continuare?")
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Reset completo del routing: continuare?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        retval = msg.exec_()
        if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
            self.dlg_solid.txtFeedback.setText("Creazione del layer cavo non effettuata per scelta dell'utente")
            Utils.logMessage("Creazione del layer cavo non effettuata per scelta dell'utente")
            return 0
        #Prima di resettare il layer cavo faccio un controllo per verificare che tutti i punti della rete siano stati associati - controllo BLOCCANTE:
        result_check_grouping = db_solid.check_grouping(self, connInfo, theSchema)
        if (result_check_grouping==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Trovata anomalia! Creazione del cavo non eseguita - alcuni punti della rete non risultano associati a PFS o nel caso di PFS a PFP. Controllare i log di QGis.')
            return 0
        
        #adesso popolo il layer:
        result_popolo = db_solid.popola_cavo(self, connInfo, theSchema)
        if (result_popolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Creazione del cavo non eseguita - errore a livello di copia delle geometrie!')
        elif (result_popolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Creazione del cavo avvenuta con successo!')
            self.dlg_solid.txtFeedback.setText("Creazione del cavo avvenuta con successo!")
        
        #Resetto il layer cavo:
        result_calcolo = db_solid.reset_all(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Creazione del cavo non eseguita - errore a livello di reset!')
            return 0
        elif (result_calcolo==1):
            #QMessageBox.information(self.dock, self.dock.windowTitle(), 'Reset del routing avvenuto con successo!')
            Utils.logMessage("Reset del routing avvenuto con successo!")

    def lancia_inizializza_routing(self):
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.inizializza_routing(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Inizializzazione al routing non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Inizializzazione al routing avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), "Inizializzazione al routing avvenuto con successo ma con qualche eccezione!\nSono stati ritrovati dei cavi il cui vertice d'origine coincide con la destinazione!\nQuesto puo' essere dovuto ad una errata vettorializzazione della linea.\nVedere il log di QGis per i dettagli.")
    
    def lancia_scale_routing(self):
        #Associo SCALA ai vertici pgr: in questo caso UN nodo pgr == UN nodo scala
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.scale_routing(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Routing su SCALA non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su SCALA avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Routing su SCALA NON effettuato. Controllare il layer e rilanciare.')
        elif (result_calcolo==3):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su SCALA effettuato ma con qualche reticenza')
            
    def lancia_pta_routing(self):
        #Associo PTA ai vertici pgr: in questo caso ci possono essere più vertici pgr coincidenti con lo stesso PTA, penso come il caso dei GIUNTI
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.pta_routing(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Routing su PTA non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PTA avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Routing su PTA NON effettuato. Controllare il layer e rilanciare.')
        elif (result_calcolo==3):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PTA effettuato ma con qualche reticenza')
       
    def lancia_giunti_routing(self):
        #Associo GIUNTO ai vertici pgr: in questo caso ci possono essere più vertici pgr coincidenti con lo stesso GIUNTO.
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.giunti_routing(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Routing su GIUNTO non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su GIUNTO avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Routing su GIUNTO NON effettuato. Controllare il layer e rilanciare.')
        elif (result_calcolo==3):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su GIUNTO effettuato ma con qualche reticenza')
            
    def lancia_pd_routing(self):
        #Associo PD ai vertici pgr: in questo caso ci possono essere più vertici pgr coincidenti con lo stesso PD.
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.pd_routing(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Routing su PD non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PD avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Routing su PD NON effettuato. Controllare il layer e rilanciare.')
        elif (result_calcolo==3):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PD effettuato ma con qualche reticenza')
            
    def lancia_pfs_routing(self):
        #Associo PFS ai vertici pgr: in questo caso ci possono essere più vertici pgr coincidenti con lo stesso PFS.
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.pfs_routing(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Routing su PFS non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PFS avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Routing su PFS NON effettuato. Controllare il layer e rilanciare.')
        elif (result_calcolo==3):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PFS effettuato ma con qualche reticenza')
            
    def lancia_pfp_routing(self):
        #Associo PFP ai vertici pgr: in questo caso ci possono essere più vertici pgr coincidenti con lo stesso PFP.
        connInfo = SCALE_layer.source()
        result_calcolo = db_solid.pfp_routing(self, connInfo, theSchema)
        if (result_calcolo==0):
            QMessageBox.critical(self.dock, self.dock.windowTitle(), 'Errore di sistema! Routing su PFP non eseguito!')
        elif (result_calcolo==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PFP avvenuto con successo!')
        elif (result_calcolo==2):
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Routing su PFP NON effettuato. Controllare il layer e rilanciare.')
        elif (result_calcolo==3):
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Routing su PFP effettuato ma con qualche reticenza')
        
    #--------------------------------------------------------------------------
    
    def select_output_dir(self):
        dirname = QFileDialog.getExistingDirectory(self.dlg_config, "Open source directory","", QFileDialog.ShowDirsOnly)
        self.dlg_config.dirBrowse_txt.setText(dirname)
        #Verifico di avere tutte le informazioni necessarie per decidere se abilitare o meno il pulsante IMPORT
        #self.activate_import()
    
    def select_output_dir_parziale(self):
        dirname = QFileDialog.getExistingDirectory(self.dlg_config, "Open source directory","", QFileDialog.ShowDirsOnly)
        self.dlg_config.dirBrowse_txt_parziale.setText(dirname)
        #Verifico di avere tutte le informazioni necessarie per decidere se abilitare o meno il pulsante IMPORT
        #self.activate_import()
        
    def select_shp_scala(self):
        filename = QFileDialog.getOpenFileName(self.dlg_config, "Load SCALA layer","", '*.shp')
        self.dlg_config.shpBrowse_txt.setText(filename)
        #Verifico di avere tutte le informazioni necessarie per decidere se abilitare o meno il pulsante IMPORT
        filename_check = self.dlg_config.shpBrowse_txt.text()
        if (filename_check):
            self.dlg_config.import_scala.setEnabled(True);
        else:
            self.dlg_config.import_scala.setEnabled(False);
        
    def select_shp_cavo(self):
        filename = QFileDialog.getOpenFileName(self.dlg_config, "Load CAVO layer","", '*.shp')
        self.dlg_config.cavoBrowse_txt.setText(filename)
        #Verifico di avere tutte le informazioni necessarie per decidere se abilitare o meno il pulsante IMPORT
        filename_check = self.dlg_config.cavoBrowse_txt.text()
        if (filename_check):
            self.dlg_config.import_scala.setEnabled(True);
        else:
            self.dlg_config.import_scala.setEnabled(False);
    
    def select_output_dir_export(self):
        dirname = QFileDialog.getExistingDirectory(self.dlg_export, "Open source directory","", QFileDialog.ShowDirsOnly)
        self.dlg_export.dirBrowse_txt.setText(dirname)
        
    def exportDB(self):
        dirname_text = self.dlg_export.dirBrowse_txt.text()
        home = expanduser("~")
        if (dirname_text): #salvo il progetto nella directory indicata dall'utente
            home = dirname_text
            dst="%s/%s/" % (home, theSchema)
        else: #salvo sotto $HOME
            dst="%s/%s/" % (home, theSchema)
        try:
            if not os.path.exists(dst):
                os.makedirs(dst)
            
            #Prima di esportare i layers li ricarico dal DB, in modo tale da ricaricare i dati ed eventuali nuovi campi aggiunti ai vari layers.
            #svuoto e ricarico tutta la TOC:
            layers = self.iface.legendInterface().layers()
            for layer in reversed(layers): #reversed order cosi mantengo l'ordine originale
                URI = layer.source()
                nome = layer.name()
                QgsMapLayerRegistry.instance().removeMapLayer(layer.id())
                #ricarico:
                re_layer = QgsVectorLayer(URI, nome, "postgres")
                QgsMapLayerRegistry.instance().addMapLayer(re_layer)
                re_layer.loadNamedStyle( os.getenv("HOME")+'/.qgis2/python/plugins/qgis2db/qml_base/%s.qml' % (nome) )
                _writer = QgsVectorFileWriter.writeAsVectorFormat(re_layer, dst+nome+'.shp', "utf-8", None, "ESRI Shapefile")

            '''
            #Esporto i vari layers:
            _writer = QgsVectorFileWriter.writeAsVectorFormat(SCALE_layer, dst+SCALE_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(GIUNTO_layer, dst+GIUNTO_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(PD_layer, dst+PD_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(PFS_layer, dst+PFS_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(PFP_layer, dst+PFP_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(CAVO_layer, dst+CAVO_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(CAVOROUTE_layer, dst+CAVOROUTE_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(APFS_layer, dst+APFS_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            _writer = QgsVectorFileWriter.writeAsVectorFormat(APFP_layer, dst+APFP_layer.name()+'.shp',"utf-8",None,"ESRI Shapefile")
            #per ultimo estraggo il "nuovo" layer cavoroute_labels, se esiste in mappa altrimenti niente:
            try:
                LABELS_layer = QgsMapLayerRegistry.instance().mapLayersByName('cavoroute_labels')[0]
                _writer = QgsVectorFileWriter.writeAsVectorFormat(LABELS_layer, dst+LABELS_layer.name()+'.shp', "utf-8", None, "ESRI Shapefile")
            except:
                Utils.logMessage('Layer cavoroute_labels non trovato vado avanti')
            '''
        except SystemError as e:
            Utils.logMessage('Errore di sistema!')
            self.dlg_export.txtFeedback.setText('Errore di sistema! Esportazione fallita')
            return 0
        else:
            Utils.logMessage('Estrazione avvenuta in ' + dst)
            self.dlg_export.txtFeedback.setText('Estrazione avvenuta in ' + dst)
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Estrazione avvenuta con successo!')
            return 1

    
    def cloneschemaDB(self):
        Utils.logMessage('CLONESCHEMA: inizio...')
        msg = QMessageBox()
        #recupero le info di connex al DB da un qualunque dei layer:
        connInfo = SCALE_layer.source()
        dest_dir = self.estrai_param_connessione(connInfo)
        #schemaDB = theSchema
        #recupero il nome indicato dall'utente per il nuovo schema da creare:
        cloneschema_name_text = self.dlg_cloneschema.cloneschema_txt.text()
        
        test_conn = None
        try:
            test_conn = psycopg2.connect(dest_dir)
            cur = test_conn.cursor()
            cur.execute( "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = '%s');" % (cloneschema_name_text) )
            msg = QMessageBox()
            if cur.fetchone()[0]==True:
                msg.setText("ATTENZIONE! Lo schema indicato e' gia' esistente, eventuali tabelle gia' presenti al suo interno verranno sovrascritte: si desidera continuare?")
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Schema gia' esistente! Sovrascrivere dati con stesso nome?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                retval = msg.exec_()
                if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
                    return False
                elif (retval == 16384): #l'utente HA CLICCATO YES.
                    #dovrei ELIMINARE il vecchio schema e creare quello nuovo:
                    #cur.execute( "DROP SCHEMA %s CASCADE; CREATE SCHEMA IF NOT EXISTS %s AUTHORIZATION operatore;"  % (cloneschema_name_text, cloneschema_name_text) )
                    cur.execute( "DROP SCHEMA %s CASCADE;"  % (cloneschema_name_text) )
                    test_conn.commit()
                    
                    #in realta il nuovo schema NON lo creo io ma devo farlo creare dal DUMP!!
                    #ALTER SCHEMA ac03w OWNER TO operatore;
                    
                    Utils.logMessage('CLONESCHEMA: eliminato vecchio schema con lo stesso nome del nuovo schema clonato indicato dall utente')
            else:
                msg.setText("ATTENZIONE! Lo schema indicato non e' presente sul DB: si conferma la sua creazione?")
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Schema non esistente: crearlo?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                retval = msg.exec_()
                if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
                    return False
                elif (retval == 16384): #l'utente HA CLICCATO YES. Posso continuare
                    #in realta il nuovo schema NON lo creo io ma devo farlo creare dal DUMP!!
                    Utils.logMessage('CLONESCHEMA: posso creare da zero il nuovo schema clone indicato dall utente')
            
            #DEVO CREARE IL NUOVO SCHEMA DAL DUMP DI QUELLO IN USO - prove per il momento NON funzionanti
            import subprocess
            #batcmd = "pg_dump -h %s -p %s -U %s --schema='%s' %s | sed 's/%s/%s/g' | psql -h %s -p %s -U %s -d %s" % (theHost, thePort, theUser, theSchema, theDbName, theSchema, cloneschema_name_text, theHost, thePort, theUser, theDbName)
            batcmd = "pg_dump -h %s -p %s -U %s --schema='%s' %s " % (theHost, thePort, theUser, theSchema, theDbName)
            Utils.logMessage( batcmd )
            #result_cmd = subprocess.Popen([batcmd], shell=True)
            #Utils.logMessage( str(dir(result_cmd) ) )
            
            batcmd = "pg_dump -h localhost -p 5433 -U operatore --schema='pc_ac02e' Enel_Test"
            homedir = os.getenv("HOME")
            schema='primo'
            outdump = os.path.join(homedir, "dump_primo.sql")
            
            #os.system( "%s > %s" % (batcmd, outdump) )
            
            #os.system("pg_dump -U operatore --schema='%s' %s | sed 's/%s/%s/g' | psql -U operatore -d %s" % (theSchema, theDbName, theSchema, cloneschema_name_text, theDbName))
            
            #NON POSSO USARE IL METODO DUMP! DEVO:
            # 0-creo il nuovo schema!
            # A-listare tutte le tabelle del vecchio schema
            # B-lanciare la funzione che crea i trigger, senza associarli alle tabelle, oppure non so cosa succede nella copia?
            # C-creare le tabelle nel nuovo schema prendendole dal vecchiio: si porta dietro le primary key e le sequences??
            # EXECUTE 'CREATE TABLE cavo_corretto ( LIKE cavo INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES )';
            # ma con questo comando le creo vuote o piene??
            #le crea VUOTE ma non va bene perche' punta alle stesse SEQUENCE dello schema vecchio!!
            #ma se ci sono viste o funzioni?? Certo sarebbe meglio un DUMP ma come ho detto non si riesce a fare da utente...
            
            # 0:
            #cur.execute( "CREATE SCHEMA IF NOT EXISTS %s AUTHORIZATION operatore; ALTER SCHEMA %s OWNER TO operatore;"  % (cloneschema_name_text,cloneschema_name_text) )
            
            
            # A:
            cur.execute( "SELECT table_name FROM information_schema.tables WHERE table_schema = '%s' AND table_type = 'BASE TABLE';" % (theSchema) )
            #cur.fetchall()
            for row in cur:
                Utils.logMessage( 'Copio tabella %s' % (row) )
                #CREATE TABLE IF NOT EXISTS ac06e.prova_clone2 ( LIKE pc_ac02e.cavo INCLUDING ALL )

            
            
            #DEVI AGGIORANRE ORA LE TABELLE SECONDO L'ULTIMA VERSIONE DEL PLUGIN, E RIPORTARE LA VERSIONE DEL PLUGIN NEL COMMENTO DEL NUOVO SCHEMA

            
            
            Utils.logMessage('ma se clicchi no esce fuori o fa comunque vedere questo messaggio??')
            debug_text = "OK! Clonazione schema avvenuta con successo"
            self.dlg_cloneschema.txtFeedback.setText(debug_text)
                    
        
        except psycopg2.Error as e:
            Utils.logMessage(str(e.pgcode) + str(e.pgerror)) #ERRORE: unsupported operand type(s) for +: 'NoneType' and 'NoneType'
            debug_text = "Connessione al DB fallita!! Rivedere i dati e riprovare"
            self.dlg_cloneschema.txtFeedback.setText(debug_text)
            return 0
        except SystemError as e:
            debug_text = "Connessione al DB fallita!! Rivedere i dati e riprovare"
            self.dlg_cloneschema.txtFeedback.setText(debug_text)
            return 0
        else:
            Utils.logMessage('Clonazione dello schema ' + theSchema + ' in ' + cloneschema_name_text + ' avvenuta con successo')
            QMessageBox.information(self.dock, self.dock.windowTitle(), 'Clonazione avvenuta con successo!')
            return 1
        finally:
            if test_conn:
                test_conn.close()


    def inizializza_layer_PNI(self):
        #Iniziamo col definire i layer che mi interessano andandoli a cercare nella legenda, visto che altrimenti non saprei come definirli:
        global PNI_SCORTA_layer
        global PNI_GIUNTO_layer
        global PNI_GRAFO_layer
        global PNI_LOCATION_layer
        global PNI_ROUTE_layer
        global PNI_CAVO_layer
        global PNI_PFS_layer
        global PNI_PFP_layer
        #layers_caricati = iface.legendInterface().layers()
        #ERRORE! Appena si avvia QGis non sa quali layer ha caricati, dunque da un errore perche queste LISTE sono VUOTE. Per questo motivo le richiamo all'interno di una funzione.
        msg = QMessageBox()
        msg.setWindowTitle("Aggiungere il layer mancante alla TOC di QGis")
        try:
            PNI_SCORTA_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_SCORTA'])[0]
            crs = PNI_SCORTA_layer.crs()
            epsg_srid = int(crs.postgisSrid())
            self.epsg_srid = epsg_srid
            #Utils.logMessage("Layer Scale: " + PNI_SCORTA_layer.name())
            PNI_GIUNTO_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_GIUNTO'])[0]
            PNI_GRAFO_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_GRAFO'])[0]
            PNI_LOCATION_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_LOCATION'])[0]
            PNI_ROUTE_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_ROUTE'])[0]
            PNI_CAVO_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_CAVO'])[0]
            PNI_PFS_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_PFS'])[0]
            PNI_PFP_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME_PNI['PNI_PFP'])[0]
        
        except IndexError as err:
            Utils.logMessage(err.args[0])
            msg.setText("Un layer fondamentale per il plugin manca nella TOC")
            msg.setDetailedText("I layer che servono al plugin sono elencati di seguito. Notare che le lettere maiuscole-minuscole devono essere rispettate nel nome del layer nella TOC, mentre invece l'ordine non ha importanza: ebw_scorta, ebw_giunto, ebw_grafo, ebw_location, ebw_route, ebw_cavo, ebw_pfs, ebw_pfp.")
            msg.setIcon(QMessageBox.Critical)
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 0
        
        else:
            Utils.logMessage("I layers necessari sono presenti sulla TOC di QGis. Posso proseguire")
            return 1
    
    def inizializza_layer(self):
        #Iniziamo col definire i layer che mi interessano andandoli a cercare nella legenda, visto che altrimenti non saprei come definirli:
        global SCALE_layer
        global PD_layer
        global GIUNTO_layer
        global GIUNTO_F_dev_layer
        global PFS_layer
        global PFP_layer
        global CAVO_layer
        global CAVOROUTE_layer
        global APFS_layer
        global APFP_layer
        global epsg_srid
        #layers_caricati = iface.legendInterface().layers()
        #ERRORE! Appena si avvia QGis non sa quali layer ha caricati, dunque da un errore perche queste LISTE sono VUOTE. Per questo motivo le richiamo all'interno di una funzione.
        msg = QMessageBox()
        msg.setWindowTitle("Aggiungere il layer mancante alla TOC di QGis")
        try:
            SCALE_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['SCALA'])[0]
            crs = SCALE_layer.crs()
            epsg_srid = int(crs.postgisSrid())
            self.epsg_srid = epsg_srid
            #Utils.logMessage("Layer Scale: " + SCALE_layer.name())
            GIUNTO_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['GIUNTO'])[0]
            #Utils.logMessage("Layer Giunto: " + GIUNTO_layer.name())
            GIUNTO_F_dev_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['GIUNTO_F_dev'])[0]
            PD_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['PD'])[0]
            #Utils.logMessage("Layer PD: " + PD_layer.name())
            PFS_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['PFS'])[0]
            #Utils.logMessage("Layer PFS: " + PFS_layer.name())
            PFP_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['PFP'])[0]
            #Utils.logMessage("Layer PFP: " + PFP_layer.name())
            
            #Altri layers che mi saranno utili per l'esportazione:
            CAVO_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['CAVO'])[0]
            CAVOROUTE_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['CAVOROUTE'])[0]
            APFS_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['Area_PFS'])[0]
            APFP_layer = QgsMapLayerRegistry.instance().mapLayersByName(self.LAYER_NAME['Area_PFP'])[0]
        
        except IndexError as err:
            Utils.logMessage(err.args[0])
            msg.setText("Un layer fondamentale per il plugin manca nella TOC")
            msg.setDetailedText("I layer che servono al plugin sono elencati di seguito. Notare che le lettere maiuscole-minuscole devono essere rispettate nel nome del layer nella TOC, mentre invece l'ordine non ha importanza: Scala, Giunti, PD, PFS, PFP, Area_PFS, Area_PFP, Cavo, Cavoroute.")
            msg.setIcon(QMessageBox.Critical)
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 0
        
        else:
            Utils.logMessage("I layers necessari sono presenti sulla TOC di QGis. Posso proseguire")
            return 1
        
    '''def attivo_associazione(self):
        if (check_origine+check_dest==2):
            QMessageBox.information(self.dock, self.dock.windowTitle(),
                'I vincoli sembrano essere rispettati. Si puo\' procedere con l\'associazione di ' + str(TOT_UI_origine) + 'UI dai punti di origine con le ' + str(TOT_UI_dest) + 'UI del punto di destinazione')
            self.dlg.importBtn.setEnabled(True)
        elif (check_origine==1 and check_dest==0):
            QMessageBox.information(self.dock, self.dock.windowTitle(),
                "Per poter procedere con l'associazione occorre selezionare UN punto di destinazione valido")
            self.dlg.importBtn.setEnabled(False)
        elif (check_origine==0 and check_dest==1):
            QMessageBox.information(self.dock, self.dock.windowTitle(),
                "Per poter procedere con l'associazione occorre selezionare dei punti di origine validi")
            self.dlg.importBtn.setEnabled(False)
        else:
            self.dlg.importBtn.setEnabled(False)'''

    def casistica_layer(self, layer_da_attivare):
        if (layer_da_attivare == SCALE_layer.name()):
            iface.setActiveLayer(SCALE_layer)
            return SCALE_layer, 'SCALA'
        elif (layer_da_attivare == GIUNTO_layer.name()):
            iface.setActiveLayer(GIUNTO_layer)
            return GIUNTO_layer, 'GIUNTO'
        elif (layer_da_attivare == GIUNTO_F_dev_layer.name()):
            iface.setActiveLayer(GIUNTO_F_dev_layer)
            return GIUNTO_F_dev_layer, 'GIUNTO_F_dev'
        elif (layer_da_attivare == PD_layer.name()):
            iface.setActiveLayer(PD_layer)
            return PD_layer, 'PD'
        elif (layer_da_attivare == PFS_layer.name()):
            iface.setActiveLayer(PFS_layer)
            return PFS_layer, 'PFS'
        elif (layer_da_attivare == PFP_layer.name()):
            iface.setActiveLayer(PFP_layer)
            return PFP_layer, 'PFP'
    
    def updateFromSelection_compare(self):
        result_init = self.inizializza_layer()
        if (result_init==0):
            return 0
        layer_da_attivare = self.dlg_compare.comboBoxFromPoint.currentText()
        if (layer_da_attivare != self.FROM_POINT[0]):
            self.dlg_compare.fileBrowse_btn.setEnabled(True)
            Utils.logMessage("Layer origine da attivare: " + layer_da_attivare)
            chiave = self.casistica_layer(layer_da_attivare)[1]
        else:
            self.dlg_compare.fileBrowse_btn.setEnabled(False)

    
    #--------------------------------------------------------------------------

    def test_connection(self):
        self.dlg_config.testAnswer.clear()
        self.dlg_config.txtFeedback.clear()
        self.dlg_config.chkDB.setEnabled(True);
        global userDB
        userDB = self.dlg_config.usrDB.text()
        pwdDB = self.dlg_config.pwdDB.text()
        hostDB = self.dlg_config.hostDB.text()
        portDB = self.dlg_config.portDB.text()
        nameDB = self.dlg_config.nameDB.text()
        global dest_dir
        dest_dir = "dbname=%s host=%s port=%s user=%s password=%s" % (nameDB, hostDB, portDB, userDB, pwdDB)
        #open DB with psycopg2
        global test_conn, cur
        test_conn = None
        cur = None
        
        #Primo passo: testo la connessione al DB
        try:
            test_conn = psycopg2.connect(dest_dir)
            cur = test_conn.cursor()
        except psycopg2.Error as e:
            Utils.logMessage(str(e.pgcode) + str(e.pgerror))
            debug_text = "Connessione al DB fallita!! Rivedere i dati e riprovare"
            self.dlg_config.txtFeedback.setText(debug_text)
            self.dlg_config.testAnswer.setText("FAIL! Inserisci dei dati corretti e continua")
            self.dlg_config.testBtn_schema.setEnabled(False)
            self.dlg_config.createBtn.setEnabled(False)
            return 0
        else:
            debug_text = "Connessione al DB avvenuta con successo"
            self.dlg_config.testAnswer.setText(debug_text)
            self.dlg_config.createBtn.setEnabled(False)
            self.dlg_config.testBtn_schema.setEnabled(True)
            self.dlg_config.schemaDB_combo.setEnabled(True)
            self.dlg_config.schemaDB.setEnabled(True)
            
            #Secondo passo: recupero gli schemi esistenti
            self.dlg_config.schemaDB_combo.clear() #pulisco la combo
            self.dlg_config.schemaDB.clear()
            #query_get_schema = """SELECT DISTINCT table_schema FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'tiger', 'public', 'topology') AND table_type='BASE TABLE' AND table_schema not like '%_topo' AND table_schema not like '%_template' ORDER BY table_schema;"""
            #creando una TAVOLA DI APPOGGIO interrogo quella tavola per recuperare le info necessarie
            query_get_schema = """SELECT nomeschema || ' (' || CASE WHEN tipo_progetto='ab' THEN 'A&B' WHEN tipo_progetto='cd' THEN 'C&D' END || ')' FROM tipo_progetti;"""
            cur.execute( query_get_schema )
            results_schema = cur.fetchall()
            schema_ins=['--']
            for schema_in in results_schema:
                schema_ins.append(schema_in[0])
            if ( len(results_schema)==0 ):
                schema_ins=['nessun schema PNI su DB']
            self.dlg_config.schemaDB_combo.addItems(schema_ins)
        finally:
            if test_conn:
                test_conn.close()
        
    def test_schema(self):
        global test_conn, cur, schemaDB, tipo_progetto
        test_conn = None
        cur = None
        schemaDB = None
        tipo_progetto = None
        import string
        invalidChars = set(string.punctuation.replace("_", " ")) #cioe' considero valido il carattere _ ma invalido lo spazio
        self.dlg_config.txtFeedback.clear()
        #Terzo passo: confermo lo schema
        schemaDB_old = self.dlg_config.schemaDB_combo.currentText()
        schemaDB_new = self.dlg_config.schemaDB.text()
        #ATTENZIONE! In questa versione lo schema, se OLD, contiene anche il tipo di progetto
        Utils.logMessage(schemaDB_old)
        msg = QMessageBox()
        if ( (schemaDB_old=='--') or (schemaDB_old=='nessun schema PNI su DB') ):
            if ( (schemaDB_new=='') or (schemaDB_new is None) or (any(x.isupper() for x in schemaDB_new)) or (any(char in invalidChars for char in schemaDB_new)) ):
                msg.setText("ATTENZIONE! Occorre indicare uno schema valido, senza spazi, caratteri speciali e lettere maiuscole")
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Indicare uno schema valido")
                msg.setStandardButtons(QMessageBox.Ok)
                retval = msg.exec_()
                return 0
            else:
                schemaDB = schemaDB_new
                self.dlg_config.schemaDB_combo.setCurrentIndex(0)
        else:
            schemaDB = schemaDB_old.split(" ", 1)[0]
            tipo_progetto = schemaDB_old.split(" ", 1)[1][1:4] #tolgo anche le parentesi cosi mi resta  C&D o A&B
            if (tipo_progetto=='C&D'):
                self.dlg_config.ced_radioButton.setChecked(True)
                self.dlg_config.aib_radioButton.setEnabled(False)
                self.dlg_config.ced_radioButton.setEnabled(False)
                tipo_progetto = 'cd' #lo ridefinisco cosi uso la stessa variabile per inserirlo nel DB nel caso di nuovo prgetto/schema
            elif (tipo_progetto=='A&B'):
                self.dlg_config.aib_radioButton.setChecked(True)
                self.dlg_config.aib_radioButton.setEnabled(False)
                self.dlg_config.ced_radioButton.setEnabled(False)
                tipo_progetto = 'ab'
            self.dlg_config.schemaDB.clear()
        Utils.logMessage( str(dest_dir) )
        try:
            test_conn = psycopg2.connect(dest_dir)
            cur = test_conn.cursor()
            cur.execute( "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = '%s');" % (schemaDB) )
            if cur.fetchone()[0]==True:
                msg.setText("ATTENZIONE! Lo schema indicato e' gia' esistente, eventuali tabelle gia' presenti al suo interno verranno sovrascritte: si desidera continuare?\nN.B.: Le tabelle verranno eventualmente sovrascritte se si decidera' di importare nuovi dati nella sezione B.")
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Schema gia' esistente! Sovrascrivere dati con stesso nome?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                retval = msg.exec_()
                if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
                    return 0
                elif (retval == 16384): #l'utente HA CLICCATO YES. Posso continuare
                    debug_text = "OK! Puoi passare alla successiva sezione B"
                    self.dlg_config.testAnswer.setText(debug_text)
                    #Verifico di avere tutte le informazioni necessarie per decidere se abilitare o meno il pulsante INIZIALIZZA
                    #self.dlg_config.importBtn.setEnabled(True)
                    self.dlg_config.chkDB.setEnabled(False)
                    self.dlg_config.import_DB.setEnabled(True)
                    return retval
            else:
                msg.setText("ATTENZIONE! Lo schema indicato non e' presente sul DB: si desidera crearlo?")
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Schema non esistente: crearlo?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                retval = msg.exec_()
                if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
                    return False
                elif (retval == 16384): #l'utente HA CLICCATO YES. Posso continuare
                    cur.execute( "CREATE SCHEMA IF NOT EXISTS %s AUTHORIZATION operatore_r;" % (schemaDB) )
                    test_conn.commit()
                    debug_text = "OK! Puoi passare alla successiva sezione B"
                    self.dlg_config.testAnswer.setText(debug_text)
                    #Verifico di avere tutte le informazioni necessarie per decidere se abilitare o meno il pulsante INIZIALIZZA
                    #self.dlg_config.importBtn.setEnabled(True)
                    self.dlg_config.chkDB.setEnabled(False)
                    self.dlg_config.import_DB.setEnabled(True)
                    return retval
        except psycopg2.Error as e:
            Utils.logMessage(str(e.pgcode) + str(e.pgerror)) #ERRORE: unsupported operand type(s) for +: 'NoneType' and 'NoneType'
            debug_text = "Connessione al DB fallita!! Rivedere i dati e riprovare"
            self.dlg_config.txtFeedback.setText(debug_text)
            #self.dlg_config.testAnswer.setText("FAIL! Inserisci dei dati corretti e continua")
            #self.dlg_config.importBtn.setEnabled(False)
            self.dlg_config.createBtn.setEnabled(False)
            return 0
            '''except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)
            debug_text = "Connessione al DB fallita!! Rivedere i dati e riprovare"
            self.dlg_config.txtFeedback.setText(debug_text)'''
        except SystemError as e:
            debug_text = "Connessione al DB fallita!! Rivedere i dati e riprovare"
            self.dlg_config.txtFeedback.setText(debug_text)
            #self.dlg_config.testAnswer.setText('FAIL!')
            #self.dlg_config.importBtn.setEnabled(False)
            self.dlg_config.createBtn.setEnabled(False)
            return 0
        finally:
            if test_conn:
                test_conn.close()
        

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
        return QCoreApplication.translate('qgis2db', message)

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
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        #TEST: carico solo un primo pannello di prova da mostrare ad ANDREA:
        icon_path = ':/plugins/qgis2db/download_CCCC00.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Importa i dati da SHP sul DB e inizializza il nuovo progetto QGis'),
            callback=self.run_config,
            parent=self.iface.mainWindow())
        
        """        
        icon_path = ':/plugins/qgis2db/grouping_C83737.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Associa i punti tra loro: grouping'),
            callback=self.run_core,
            parent=self.iface.mainWindow())
        
        icon_path = ':/plugins/qgis2db/compare_C83737.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Verifica le connessioni'),
            callback=self.run_compare,
            parent=self.iface.mainWindow())
        
        icon_path = ':/plugins/qgis2db/export.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Esporta il progetto in shp'),
            callback=self.run_export,
            parent=self.iface.mainWindow())
        
        icon_path = ':/plugins/qgis2db/update.png'
        self.add_action(
            icon_path,
            text=self.tr(u'aggiorna le funzioni a livello di DB'),
            callback=self.run_updatedb,
            parent=self.iface.mainWindow())
        
        icon_path = ':/plugins/qgis2db/cloneschema_C83737.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Clona il progetto creando un altro schema nel DB'),
            callback=self.run_cloneschema,
            parent=self.iface.mainWindow())
            
        icon_path = ':/plugins/qgis2db/overlap_C83737.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Controlla sovrapposizione tra cavi'),
            callback=self.run_controlla_cavi_sovrapposti,
            parent=self.iface.mainWindow())
            
        icon_path = ':/plugins/qgis2db/update_C83737.png'
        self.add_action(
            icon_path,
            text=self.tr(u'aggiorna le funzioni a livello di DB'),
            callback=self.run_updatedb,
            parent=self.iface.mainWindow())
        """
        
        icon_path = ':/plugins/qgis2db/help_CCCC00.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Informazioni'),
            callback=self.run_help,
            parent=self.iface.mainWindow())


        #load the form
        path = os.path.dirname(os.path.abspath(__file__))
        self.dock = uic.loadUi(os.path.join(path, "qgis2db_dockwidget_base.ui")) #OK
        #self.dock_compare = uic.loadUi(os.path.join(path, "qgis2db_compare_dockwidget_base.ui"))
        
        #se modifico il drop down faccio partire un'azione:
        #QObject.connect(self.dlg_compare.comboBoxFromPoint, SIGNAL("currentIndexChanged(const QString&)"), self.updateFromSelection_compare)
        
        #----------------------------------------------------
        #TEST: aggiungo DockWidget: ridefinisco qui perche' dal run_core non sembrava prenderlo
        if self.dockwidget == None:
            # Create the dockwidget (after translation) and keep reference
            self.dockwidget = CoreDockWidget()
        #Per non riscrivere tutto il codice precedente, avendo eliminato il QDialog per sostituirlo con questo DockWidget, equiparo le 2 variaibli:
        self.dlg = self.dockwidget

        #Nella versione 4.4 metto qui il pulsante per la verifica delle associazioni:
        #QObject.connect(self.dockwidget.solid_btn_aree, SIGNAL("clicked()"), self.lancia_consolida_aree_dlg)
        #QObject.connect(self.dockwidget.solid_btn_aree, SIGNAL("clicked()"), self.check_grouping_from_user)
        #
        ##Scelgo che punto voglio associare e faccio partire in qualche modo il controllo sulla selezione sulla mappa:
        #QObject.connect(self.dockwidget.scala_scala_btn, SIGNAL("clicked()"), self.associa_scala_scala)
        ##QObject.connect(self.dockwidget.scala_giunto_btn, SIGNAL("clicked()"), self.associa_scala_giunto)
        #QObject.connect(self.dockwidget.scala_giunto_btn, SIGNAL("clicked()"), self.associa_scala_muffola)
        #QObject.connect(self.dockwidget.scala_pta_btn, SIGNAL("clicked()"), self.associa_scala_pta)
        #QObject.connect(self.dockwidget.scala_pd_btn, SIGNAL("clicked()"), self.associa_scala_pd)
        #QObject.connect(self.dockwidget.scala_pfs_btn, SIGNAL("clicked()"), self.associa_scala_pfs)
        ##QObject.connect(self.dockwidget.giunto_giunto_btn, SIGNAL("clicked()"), self.associa_giunto_giunto)
        #QObject.connect(self.dockwidget.giunto_giunto_dev_btn, SIGNAL("clicked()"), self.associa_giunto_giunto_dev)
        ##QObject.connect(self.dockwidget.giunto_pd_btn, SIGNAL("clicked()"), self.associa_giunto_pd)
        #QObject.connect(self.dockwidget.pta_pfs_btn, SIGNAL("clicked()"), self.associa_pta_pfs)
        #QObject.connect(self.dockwidget.pd_pd_btn, SIGNAL("clicked()"), self.associa_pd_pd)
        #QObject.connect(self.dockwidget.pd_pfs_btn, SIGNAL("clicked()"), self.associa_pd_pfs)
        #QObject.connect(self.dockwidget.pfs_pfp_btn, SIGNAL("clicked()"), self.associa_pfs_pfp)
        
        
        global check_origine #variabile booleana che mi dice se e' tutto ok lato origine
        check_origine = 0
        global check_dest #variabile booleana che mi dice se e' tutto ok lato destinazione
        check_dest = 0
        global selected_features_origine
        global selected_features_ids_origine
        global selected_features_dest
        global selected_features_ids_dest
        global TOT_UI_origine
        global TOT_UI_dest
        global TOT_giunti_dest
        global TOT_pd_dest
        global TOT_pfs_dest
        global TOT_ncont_dest
        global TOT_ncont_origine
        
        #ripulisco tutte le selezioni in mappa - NON FUNZIONA!
        #lg = iface.mainWindow().findChild(QTreeWidget, 'theMapLegend')
        #lg.selectionModel().clear()  # clear just selection
        #lg.setCurrentItem(None)  # clear selection and active layer

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Progetto ENEL'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

        '''for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Core'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar'''

    def run_config(self):
        # show the dialog
        self.dlg_config.show()
        # Run the dialog event loop
        result = self.dlg_config.exec_()
        self.dlg_config.txtFeedback.clear()
        self.dlg_config.txtFeedback_import.clear()
        self.dlg_config.dirBrowse_txt.clear()
        self.dlg_config.dirBrowse_txt_parziale.clear()
        self.dlg_config.import_progressBar.setValue(0)
        #self.dlg_config.usrDB.clear()
        #self.dlg_config.pwdDB.clear()
        #self.dlg_config.hostDB.clear()
        #self.dlg_config.portDB.clear()
        #self.dlg_config.nameDB.clear()
        #self.dlg_config.schemaDB.clear()
        #self.dlg_config.comuneDB.clear()
        #self.dlg_config.codpopDB.clear()
        self.dlg_config.testAnswer.clear()
        self.dlg_config.chkDB.setEnabled(True);
        #self.dlg_config.importBtn.setEnabled(False);
        self.dlg_config.createBtn.setEnabled(False)
        
        self.dlg_config.import_DB.setEnabled(False);
        #self.dlg_config.variabili_DB.setEnabled(False);
        self.dlg_config.si_import.setChecked(False)
        self.dlg_config.no_import.setChecked(False)
        self.dlg_config.si_import_parziale.setChecked(False)
        #self.dlg_config.modifica_variabili.setChecked(False)
        
        #self.dlg_config.shpBrowse_txt.clear()
        #self.dlg_config.cavoBrowse_txt.clear()
        #self.dlg_config.si_inizializza.setChecked(False)
        #self.dlg_config.txtFeedback_inizializza.clear()
        
        
    def run_compare(self):
        # show the dialog
        self.dlg_compare.show()
        # Run the dialog event loop
        result = self.dlg_compare.exec_()
        self.dlg_compare.txtFeedback.clear()
        idx_1 = self.dlg_compare.comboBoxFromPoint.findText(self.FROM_POINT[0])
        self.dlg_compare.comboBoxFromPoint.setCurrentIndex(idx_1)
        
    def run_export(self):
        result_init = self.inizializza_layer_PNI()
        if (result_init==0):
            return 0
        #recupero le info di connex al DB da un qualunque dei layer:
        connInfo = PNI_SCORTA_layer.source()
        db_dir = self.estrai_param_connessione(connInfo)
        #per evitare di esportare il progetto che contiene PNI_SCORTA come shp e non da DB:
        if (db_dir.find("dbname=None") > -1) or (db_dir.find("host=None") > -1):
            msg = QMessageBox()
            msg.setWindowTitle("Stringa di connessione al DB non presente")
            Utils.logMessage("db_dir: " + db_dir)
            msg.setText("Per l'esportazione dei layer da DB tutti i layer presenti nella TOC devono essere presenti sul medesimo DB del layer ebw_scorta")
            msg.setIcon(QMessageBox.Critical)
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 0
        # show the dialog
        self.dlg_export.show()
        # Run the dialog event loop
        result = self.dlg_export.exec_()
        self.dlg_export.txtFeedback.clear()
        
    def run_cloneschema(self):
        result_init = self.inizializza_layer()
        if (result_init==0):
            return 0
        #recupero le info di connex al DB da un qualunque dei layer:
        connInfo = SCALE_layer.source()
        db_dir = self.estrai_param_connessione(connInfo)
        # show the dialog
        self.dlg_cloneschema.show()
        # Run the dialog event loop
        result = self.dlg_cloneschema.exec_()
        self.dlg_cloneschema.txtFeedback.clear()
    
    def run_updatedb(self):
        result_init = self.inizializza_layer_PNI()
        if (result_init==0):
            return 0
        msg = QMessageBox()
        #recupero le info di connex al DB da un qualunque dei layer:
        connInfo = PNI_SCORTA_layer.source()
        db_dir = self.estrai_param_connessione(connInfo)
        #apro il cursore per leggere/scrivere sul DB:
        conn_updatedb = psycopg2.connect(db_dir)
        cur_updatedb = conn_updatedb.cursor()
        Utils.logMessage('UPDATEDB: inizio la procedura')
        try:
            #per il progetto PNi al momento queste funzioni non esistono
            '''
            sql_file = os.getenv("HOME") + '/.qgis2/python/plugins/qgis2db/creazione_funzione_scodificacable.sql'
            cur_updatedb.execute(open(sql_file, "r").read())
            conn_updatedb.commit()
            #In questo caso lancio la funzione per creare la tabella di decodifica:
            query_codifica_cable = "SELECT public.s_codifica_cable('%s', %i);" % (theSchema, self.epsg_srid)
            cur_updatedb.execute(query_codifica_cable)
            conn_updatedb.commit()
            
            sql_file = os.getenv("HOME") + '/.qgis2/python/plugins/qgis2db/creazione_funzione_scalcable.sql'
            cur_updatedb.execute(open(sql_file, "r").read())
            conn_updatedb.commit()
            
            sql_file = os.getenv("HOME") + '/.qgis2/python/plugins/qgis2db/creazione_funzione_salterscala.sql'
            cur_updatedb.execute(open(sql_file, "r").read())
            conn_updatedb.commit()
            
            sql_file = os.getenv("HOME") + '/.qgis2/python/plugins/qgis2db/creazione_funzione_saltertable.sql'
            cur_updatedb.execute(open(sql_file, "r").read())
            conn_updatedb.commit()
            '''
            
            sql_file = os.getenv("HOME") + '/.qgis2/python/plugins/qgis2db/creazione_funzione_splitlines.sql'
            cur_updatedb.execute(open(sql_file, "r").read())
            conn_updatedb.commit()
            
        except psycopg2.Error as e:
            Utils.logMessage("Errore UPDATEDB: " + e.pgerror)
            conn_updatedb.rollback()
            msg.setText("Errore UPDATEDB: " + e.pgerror)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Errore!")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 0
        except SystemError as e:
            Utils.logMessage("Errore UPDATEDB. Contattare l'amministratore." + str(e))
            conn_updatedb.rollback()
            msg.setText("Errore UPDATEDB. Contattare l'amministratore. " + str(e))
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Errore!")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 0
        else:
            Utils.logMessage('UPDATEDB: fine della procedura con successo')
            msg.setText("UPDATEDB: effettuato con successo!")
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("UPDATEDB: effettuato con successo!")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 1
        finally:
            if conn_updatedb:
                conn_updatedb.close()
    
    def run_controlla_cavi_sovrapposti(self):
        result_init = self.inizializza_layer()
        if (result_init==0):
            return 0
        #recupero le info di connex al DB da un qualunque dei layer:
        connInfo = SCALE_layer.source()
        db_dir = self.estrai_param_connessione(connInfo)
        
        overlapped_cavi = 0
        conn_cutcable = None
        cur_cutcable = None
        
        msg = QMessageBox()
        msg.setText("Questo controllo cerchera' di individuare eventuali linee sovrapposte sul layer CAVO che la funzione CUTCABLE non e' stata in grado di spezzare per via di una scorretta geometria del cavo. Cliccando su OK verra' lanciato questo controllo, che potrebbe impiegare qualche minuto. Al termine dell'elaborazione verrete informati sul risultato")
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Controllo layer cavo")
        msg.setStandardButtons(QMessageBox.Ok)
        retval = msg.exec_()
        
        try:
            conn_cutcable = psycopg2.connect(db_dir)
            cur_cutcable = conn_cutcable.cursor()
            Utils.logMessage('Controllo CAVI sovrapposti: inizio la procedura')
            
            #creo prima la tabella dei buffer:
            query_buffer = 'DROP TABLE IF EXISTS %s.cavo_buffer; CREATE TABLE %s.cavo_buffer AS SELECT *, ST_Buffer(geom, 0.1)::geometry(POLYGON, %s) AS buffered_geom FROM %s.cavo; ALTER TABLE %s.cavo_buffer OWNER TO operatore;' % (theSchema, theSchema, self.epsg_srid, theSchema, theSchema)
            cur_cutcable.execute(query_buffer)
            conn_cutcable.commit()
            
            
            overlapped_cavi = self.controlla_cavi_sovrapposti(theSchema, cur_cutcable)
        
        except psycopg2.Error as e:
            Utils.logMessage("Errore cavi sovrapposti: " + e.pgerror)
            conn_cutcable.rollback()
            msg.setText("Errore cavi sovrapposti: " + e.pgerror)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Errore!")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 0
        except SystemError as e:
            Utils.logMessage("Errore cavi sovrapposti. Contattare l'amministratore." + str(e))
            conn_cutcable.rollback()
            msg.setText("Errore pulizia cavi sovrapposti. Contattare l'amministratore. " + str(e))
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Errore!")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 0
        else:
            Utils.logMessage('CAVI sovrapposti: fine della procedura')
            msg.setText("Sono state trovate %s coppie di CAVI parzialmente sovrapposti. Analizzate i log di QGis per i dettagli." % (overlapped_cavi))
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("cavi sovrapposti: risultato")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec_()
            return 1
        finally:
            if conn_cutcable:
                conn_cutcable.close()
        
    
    def controlla_cavi_sovrapposti(self, theSchema, cursore):
        query_controllo = """SELECT gid_a, gid_b FROM (
        SELECT t1.gid AS gid_a, t2.gid AS gid_b,
        ST_StartPoint((st_dump(t1.geom)).geom) AS start_point_a,
        ST_EndPoint((st_dump(t1.geom)).geom) AS end_point_a,
        ST_StartPoint((st_dump(t2.geom)).geom) AS start_point_b,
        ST_EndPoint((st_dump(t2.geom)).geom) AS end_point_b
        FROM %s.cavo_buffer t1, %s.cavo_buffer t2
        WHERE t1.gid <> t2.gid
        AND ST_Intersects(t1.buffered_geom, t2.buffered_geom) 
        AND t1.gid < t2.gid
        AND ST_Area(ST_Intersection(t1.buffered_geom, t2.buffered_geom)) > 0.1
        ORDER BY t1.gid
        ) AS foo
        WHERE 
        abs( (ST_Azimuth(start_point_a, end_point_a))/(2*pi())*360 - (ST_Azimuth(start_point_b, end_point_b))/(2*pi())*360 ) < 2.2;""" % (theSchema, theSchema)

        cursore.execute(query_controllo)
        rows = cursore.fetchall()
        overlapped_cavi = len(rows)
        Utils.logMessage( 'Numero di coppie di gid di cavo sovrapposte trovate = %s' % (str(overlapped_cavi)) )
        for row in rows:
            Utils.logMessage( 'Coppie di gid di cavo sovrapposti: %s' % (str(row)) )
        
        return overlapped_cavi
    
    def run_help(self):
        #Prelevo il numero di versione dal file metadata.txt:
        #nome_file = os.getenv("HOME")+'/.qgis2/python/plugins/qgis2db/metadata.txt'
        nome_file = self.plugin_dir + '/metadata.txt'
        searchfile = open(nome_file, "r")
        for line in searchfile:
            if "version=" in line:
                version = str(line[8:13])
                #Utils.logMessage(str(line[8:]))
            if "release_date=" in line:
                release_date = str(line[13:23])
        searchfile.close()
        self.dlg_help.label_version.clear()
        self.dlg_help.label_version.setText("Versione: " + version + " - " + release_date)
        # show the dialog
        self.dlg_help.show()
        # Run the dialog event loop
        result = self.dlg_help.exec_()

    def estrai_param_connessione(self, connInfo):
        global theSchema
        global theDbName
        global theHost
        global thePort
        global theUser
        theSchema = None
        theDbName = None
        theHost = None
        thePort = None
        theUser = None
        thePassword = None
        kvp = connInfo.split(" ")
        for kv in kvp:
            if kv.startswith("password"):
                thePassword = kv.split("=")[1][1:-1]
            elif kv.startswith("host"):
                theHost = kv.split("=")[1]
            elif kv.startswith("port"):
                thePort = kv.split("=")[1]
            elif kv.startswith("dbname"):
                theDbName = kv.split("=")[1][1:-1]
            elif kv.startswith("user"):
                theUser = kv.split("=")[1][1:-1]
            elif kv.startswith("table"):
                theTable_raw = kv.split("=")[1]
                theSchema = theTable_raw.split(".")[0][1:-1]
                theTable = theTable_raw.split(".")[1][1:-1]
        test_conn = None
        cur = None
        dest_dir = "dbname=%s host=%s port=%s user=%s password=%s" % (theDbName, theHost, thePort, theUser, thePassword)
        return dest_dir
            
##########################################################################
    # TEST DOCKWIDGET
        
    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        #print "** CLOSING Core"

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False

    #--------------------------------------------------------------------------

    def run_core(self):
        """Run method that loads and starts the plugin"""
        global FROM_TO_RULES
        global COD_POP
        global epsg_srid
        result_init = self.inizializza_layer()
        if (result_init==0):
            return 0
        #recupero le info di connex al DB da un qualunque dei layer:
        connInfo = SCALE_layer.source()
        #A questo punto finalmente mi connetto al DB per recuperare le variabili di progetto:
        db_dir = self.estrai_param_connessione(connInfo)
        test_conn = None
        try:
            test_conn = psycopg2.connect(db_dir)
            dict_cur = test_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            query_var = """SELECT pta_ui_min, pta_ui_max, pta_cont_max,
                giunto_ui_min, giunto_ui_max, giunto_cont_max, 
                pd_ui_min, pd_ui_max, pd_cont_max,
                pfs_ui_min, pfs_ui_max, pfs_pd_max, 
                pfp_ui_min, pfp_ui_max, pfp_pfs_max, id_pop, srid
                FROM %s.variabili_progetto; """ % (theSchema)
       
            dict_cur.execute(query_var)
            results_var = dict_cur.fetchone()
            epsg_srid = results_var['srid']
            self.epsg_srid = epsg_srid
            #Recupero la variabile COD_POP e controllo se e' settata:
            COD_POP = results_var['id_pop']
            if not COD_POP:
                cippa = QInputDialog()
                cippa.setIntValue(0) #se non dovesse essere intero usa "setTextValue()"
                cippa.setWindowTitle('POP non settato!')
                cippa.setLabelText('POP nullo, settarlo ora per il progetto e poter proseguire')
                retval = cippa.exec_()
                COD_POP = str(cippa.intValue())
                #a questo punto lo inserirei nella tabella di progetto:
                query_pop = "UPDATE %s.variabili_progetto SET id_pop=%s;" % (theSchema, COD_POP)
                dict_cur.execute(query_pop)
                test_conn.commit()
    
            #Ricostruisco il dict con le variabili:
            FROM_TO_RULES = {
                'PTA': {'MIN_UI': results_var['pta_ui_min'], 'MAX_UI': results_var['pta_ui_max'], 'MAX_CONT': results_var['pta_cont_max']},
                'GIUNTO': {'MIN_UI': results_var['giunto_ui_min'], 'MAX_UI': results_var['giunto_ui_max'], 'MAX_CONT': results_var['giunto_cont_max']},
                'GIUNTO_F_dev': {'MIN_UI': results_var['giunto_ui_min'], 'MAX_UI': results_var['giunto_ui_max'], 'MAX_CONT': results_var['giunto_cont_max']},
                'PD': {'MIN_UI': results_var['pd_ui_min'], 'MAX_UI': results_var['pd_ui_max'], 'MAX_CONT': results_var['pd_cont_max']},
                'PFS': {'MIN_UI': results_var['pfs_ui_min'], 'MAX_UI': results_var['pfs_ui_max'], 'MAX_CONT': results_var['pfs_pd_max']},
                'PFP': {'MIN_UI': results_var['pfp_ui_min'], 'MAX_UI': results_var['pfp_ui_max'], 'MAX_CONT': results_var['pfp_pfs_max']}
            }
            FROM_TO_RULES['SCALA'] = FROM_TO_RULES['GIUNTO']
            #Utils.logMessage(str(FROM_TO_RULES['GIUNTO']))
        
            dict_cur.close()
        except psycopg2.Error as e:
            Utils.logMessage(e.pgerror)
            #self.dlg_compare.txtFeedback.setText(e.pgerror)
            FROM_TO_RULES = self.FROM_TO_RULES
            COD_POP = self.COD_POP
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Non sono riuscito a scaricare correttamente dal DB le variabili del progetto in uso. Carico quelle di default')
            return 0;
        except SystemError as e:
            Utils.logMessage('Errore di sistema!')
            #self.dlg_compare.txtFeedback.setText('Errore di sistema!')
            FROM_TO_RULES = self.FROM_TO_RULES
            COD_POP = self.COD_POP
            QMessageBox.warning(self.dock, self.dock.windowTitle(), 'Non sono riuscito a scaricare correttamente dal DB le variabili del progetto in uso. Carico quelle di default')
            return 0
        else:
            self.FROM_TO_RULES = FROM_TO_RULES
            self.COD_POP = COD_POP
            #Utils.logMessage('Variabili del progetto importate con successo! '+str(sys.version)+" - QGIS Version: " + self.Qgis_sw_version)
            Utils.logMessage('Variabili del progetto importate con successo!')
            #self.dlg_compare.txtFeedback.setText('Variabili del progetto importate con successo!')
        finally:
            if test_conn:
                test_conn.close()
        
        global check_origine #variabile booleana che mi dice se e' tutto ok lato origine
        check_origine = 0
        global check_dest #variabile booleana che mi dice se e' tutto ok lato destinazione
        check_dest = 0

        if not self.pluginIsActive:
            self.pluginIsActive = True

            #print "** STARTING Core"

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget == None:
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = CoreDockWidget()

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            # show the dockwidget
            # TODO: fix to allow choice of dock location        
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)
            self.dockwidget.show()
