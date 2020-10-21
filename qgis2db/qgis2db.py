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
NUOVE NOTE plugin qgis2db:

- a list of provider keys can be obtained by:
QgsProviderRegistry.instance().providerList()

- alcuni shp in caricamento possono gia' avere il campo gid, ma non e' univoco, e la procedura di caricamento su DB da errore. Non sono riuscito a omettere questo campo nel caso esista, ma solo ad eliminarlo, anche se ha un comportamento strano. Dunque carico gli shp su DB usando come PK il campo gidd, sperando che cosi scritto non esista gia sugli shp. Funzione import_shp2db

- esegui vacuum dello schema dopo l'import da shp2db, funzione import_shp2db, oppure guarda anche il python ImportIntoPostGIS recuperato da web, che sfrutta la libreria di cui non ho ancora trovato documentazione pero:
    from processing.tools import dataobjects, postgis

- le eccezioni al caricamento dei layer per la creazione di un nuovo progetto sono nella funzione crea_progetto_reindirizzando_il_template


OTTIMIZZAZIONI/DUBBI:
- ATTENZIONE!! nel cambio di datasource del progetto template devo omettere quei layer che non trovano esatto riscontro nel nome sul DB altrimenti QGis crasha. Vedi funzione import_shp2db

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
        #self.dlg_config.dirBrowse_txt.clear()
        #self.dlg_config.dirBrowse_txt_parziale.clear()
        #self.dlg_config.dirBrowse_btn.clicked.connect(self.select_output_dir)
        #self.dlg_config.dirBrowse_btn_parziale.clicked.connect(self.select_output_dir_parziale)
        #Seleziono layer SCALA per inizializza un nuovo progetto da zero:
        #self.dlg_config.shpBrowse_btn.clicked.connect(self.select_shp_scala)
        #self.dlg_config.cavoBrowse_btn.clicked.connect(self.select_shp_cavo)
        #Ad ogni nuova riapertura del pannello di configurazione del progetto disabilito alcuni pannelli:
        #self.dlg_config.import_DB.setEnabled(False);
        #self.dlg_config.variabili_DB.setEnabled(False);
        #Verifico se i dati sono o meno gia' importati sul DB escludendo la doppia scelta:
        #self.dlg_config.no_import.clicked.connect(self.toggle_no_import)
        #self.dlg_config.si_import.clicked.connect(self.toggle_si_import)
        #self.dlg_config.si_import_parziale.clicked.connect(self.toggle_si_import_parziale)
        #che tipo di dati sto caricando e come vanno associati gli shp alle tabelle standard del PNI?
        #self.dlg_config.buttonGroup.buttonClicked.connect(self.toggle_ced_element)
        
        #self.dlg_config.si_inizializza.clicked.connect(self.toggle_si_inizializza)
        #Azioni sul tasto import per spostare gli shp su DB:
        self.dlg_config.import_shp.clicked.connect(self.import_shp2db)
        #self.dlg_config.import_shp_parziale.clicked.connect(self.import_shp2db_parziale)
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
        
        self.dlg_config.txtFeedback_import.setText("Sto caricando i dati, non interrompere, il processo potrebbe richiedere alcuni minuti...")
        global epsg_srid
        global sciape_error
        self.sciape_error = []
        #importo gli shp su db. Controllo che tutti i campi siano compilati prima di procedere:
        msg = QMessageBox()
        
        
        msg.setText("ATTENZIONE! Con questa azione carichi gli shp presenti come layer sulla TOC di QGis sul DB, e se gli shp esistono gia' nello schema selezionato verranno SOVRASCRITTI con gli shp selezionati: procedere?")
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Caricare i layers della TOC sul DB?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        retval = msg.exec_()
        if (retval != 16384): #l'utente NON ha cliccato yes: sceglie di fermarsi, esco
            return 0
        elif (retval == 16384): #l'utente HA CLICCATO YES.
            #Recupero i layers dalla TOC
            #ATTENZIONE!!! iface.mapCanvas().layers() recupera solo i layers visibili, per questo motivo nel template li ho messi tutti visibili
            #per ovviare a questo limite posso provare questa chiamata:
            if (int(qgis_version[0]) >= 3):
                lista_layer_to_load = QgsProject.instance().mapLayers()
            else:
                lista_layer_to_load = QgsMapLayerRegistry.instance().mapLayers()
                
            #Li spengo di default e li importo direttamente sul DB:
            shp_name_to_load = []
            self.dlg_config.import_progressBar.setMaximum( len(lista_layer_to_load) )
            crs = None
            test_conn = None
            options = {}
            options['lowercaseFieldNames'] = True
            options['overwrite'] = True
            options['forceSinglePartGeometryType'] = True
            try:
                self.dlg_config.txtFeedback_import.setText("Sto importando i dati...")
                for layer_loaded in lista_layer_to_load.values():
                    #self.iface.legendInterface().setLayerVisible(layer_loaded, False) #tralascio in QGis3
                    shp_name_to_load.append(layer_loaded.name().lower())
                    layer_loaded_geom = layer_loaded.wkbType()
                    uri = None
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
                        
                    #salvo anche los tile sul DB
                    #ATTENZIONE! forse lo stile viene salvato su DB se proviene da un layer caricato da DB
                    #dunque provare a salvare lo stile dello shp in una variabile python, ricaricare il progetto con i layer presi da DB, riassegnare a ciascuno di questio nuovi layer lo stile dello shp di origine, infine provare a lancaire questo saveStyleToDatabase....
                    layer_style_name = "%s_style" % (layer_loaded.name().lower())
                    layer_style_description = "stile per il layer %s" % (layer_loaded.name().lower())
                    layer_loaded.saveStyleToDatabase(layer_style_name, layer_style_description, True, "uiFileContent" )

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
                cur.execute(query_grant)
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
                
                #TRACKING modifiche sui layer
                #devo attivare gli script in base ai layer effettivamente caricati
                Utils.logMessage('shp_name_to_load, per i quali ho anche creato indice spaziale '+str(shp_name_to_load))
                query_path = "SET search_path = %s, pg_catalog;" % (schemaDB)
                Utils.logMessage('Adesso se il caso creo il tracking sulle tabelle nello schema ' + str(schemaDB))
                cur.execute(query_path)
                
                self.dlg_config.txtFeedback_import.setText("Dati importati con successo! Passiamo alla creazione del progetto...")
                #a questo punto dovrei importare il progetto template in base al tipo di dati importati
                project = QgsProject.instance()
                #dovrei ricaricare i layer prendendoli dal DB
                #ora modifico i dataSource di questi progetti puntandoli allo schema appena creato:
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
                test_conn.close()
                
                ### DA SVILUPPARE!!! ###
                #self.crea_progetto_reindirizzando_il_template(lista_layer_to_load, ced_checked, layer_on_DB, project, dirname_text)

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
                self.dlg_config.txtFeedback_import.setText("Dati importati con successo sul DB")
                #Abilito le restanti sezioni e pulsanti
                #self.dlg_config.chkDB.setEnabled(False)
                #self.dlg_config.import_DB.setEnabled(False)
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
            '''
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
            '''
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
    
    #--------------------------------------------------------------------------
    
    #--------------------------------------------------------------------------

    def test_connection(self):
        self.dlg_config.testAnswer.clear()
        self.dlg_config.txtFeedback.clear()
        #self.dlg_config.chkDB.setEnabled(True);
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
            #recupero TUTTI gli schemi del DB tranne quelli di sistema:
            query_get_schema = """SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'public', 'topology') AND schema_name not like '%_topo' AND schema_name not like '%_template' AND schema_name not like '%pg_temp%' AND schema_name not like '%pg_toast%' AND schema_name not like '%tiger%'"""
            #creando una TAVOLA DI APPOGGIO interrogo quella tavola per recuperare le info necessarie
            #query_get_schema = """SELECT nomeschema || ' (' || CASE WHEN tipo_progetto='ab' THEN 'A&B' WHEN tipo_progetto='cd' THEN 'C&D' END || ')' FROM tipo_progetti;"""
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
            #controllo se ho selezionato uno schema esistente valido, altrimenti cerco se ne e' stato indicato uno nuovo
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
            #ho selezionato uno schema gia' esistente valido
            schemaDB = schemaDB_old
            self.dlg_config.schemaDB.clear()
        Utils.logMessage( str(dest_dir) )
        try:
            test_conn = psycopg2.connect(dest_dir)
            cur = test_conn.cursor()
            cur.execute( "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = '%s');" % (schemaDB) )
            if cur.fetchone()[0]==True:
                msg.setText("ATTENZIONE! Lo schema indicato e' gia' esistente, eventuali tabelle gia' presenti al suo interno verranno sovrascritte: si desidera continuare?")
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
                    #self.dlg_config.chkDB.setEnabled(False)
                    self.dlg_config.import_shp.setEnabled(True)
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
                    #self.dlg_config.chkDB.setEnabled(False)
                    self.dlg_config.import_shp.setEnabled(True)
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
        
        icon_path = ':/plugins/qgis2db/help_CCCC00.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Informazioni'),
            callback=self.run_help,
            parent=self.iface.mainWindow())


        #load the form
        path = os.path.dirname(os.path.abspath(__file__))
        #self.dock = uic.loadUi(os.path.join(path, "qgis2db_dockwidget_base.ui")) #OK
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
        #self.dlg_config.dirBrowse_txt.clear()
        #self.dlg_config.dirBrowse_txt_parziale.clear()
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
        #self.dlg_config.chkDB.setEnabled(True);
        #self.dlg_config.importBtn.setEnabled(False);
        self.dlg_config.createBtn.setEnabled(False)
        
        #self.dlg_config.import_DB.setEnabled(False);
        #self.dlg_config.variabili_DB.setEnabled(False);
        #self.dlg_config.si_import.setChecked(False)
        #self.dlg_config.no_import.setChecked(False)
        #self.dlg_config.si_import_parziale.setChecked(False)
        #self.dlg_config.modifica_variabili.setChecked(False)
        
        #self.dlg_config.shpBrowse_txt.clear()
        #self.dlg_config.cavoBrowse_txt.clear()
        #self.dlg_config.si_inizializza.setChecked(False)
        #self.dlg_config.txtFeedback_inizializza.clear()

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
