from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from qgis.core import QgsLayerTreeNode,QgsLayerTree,  QgsLayerTreeModel, QgsFeature, QgsPoint, QgsVector, QgsGeometry, QgsField, QgsWkbTypes, QgsProject, QgsMapToPixel, QgsLayerTreeLayer, QgsFeatureRequest, QgsVectorLayer,  QgsCoordinateReferenceSystem, QgsMapLayer, QgsExpression
from qgis.gui import *
from qgis.utils import *
from decimal import Decimal
import psycopg2 as pg
import os
import datetime
import tempfile
import re


class FreehandPolygonMaptool(QgsMapTool):

    geometryReady = pyqtSignal('QgsGeometry')
    def __init__(self, canvas):

        QgsMapTool.__init__(self,canvas)

        self.canvas = canvas
        self.cursor = QCursor(QPixmap(["16 16 3 1",
            "      c None",
            ".     c #FF0000",
            "+     c #FFFFFF",
            "                ",
            "       +.+      ",
            "      ++.++     ",
            "     +.....+    ",
            "    +.     .+   ",
            "   +.   .   .+  ",
            "  +.    .    .+ ",
            " ++.    .    .++",
            " ... ...+... ...",
            " ++.    .    .++",
            "  +.    .    .+ ",
            "   +.   .   .+  ",
            "   ++.     .+   ",
            "    ++.....+    ",
            "      ++.++     ",
            "       +.+      "]))
        self.iface = iface
        # init rubber band polygon
        self.rb = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self.rb.setColor(QColor(255, 0, 0, 50))
        self.proj = QgsProject.instance()
        self.nidl = QgsProject.instance().nonIdentifiableLayers()
        # print(self.nidl)

    def createResWriter(self):
        resPath = tempfile.gettempdir()
        resPrefix = 'Constraints_'
        resSuffix = '.csv'
        self.dateTimeStrSuff = str(datetime.datetime.now()).replace('-','').replace(':','').replace(' ','').replace('.','')[:17]
        self.resFileName = os.path.join(resPath,resPrefix +self.dateTimeStrSuff + resSuffix)
        try:
            self.writer = open(self.resFileName, 'w')
        finally:
            self.writer.close
        return self.writer

    def activate(self):
        self.canvas.setCursor(self.cursor)    
        self.rb.reset(QgsWkbTypes.PolygonGeometry)

    def deactivate(self):
        self.rb.reset(QgsWkbTypes.PolygonGeometry)

    def canvasMoveEvent(self, ev):
        
        worldPoint = QgsMapToPixel.toMapCoordinates(self.canvas.getCoordinateTransform(), 
                                                        ev.pos().x(),
                                                        ev.pos().y() )
        self.rb.movePoint(worldPoint)

    def canvasPressEvent(self, ev):
        
        geometryReady = pyqtSignal('QObject')
        
        if ev.button() == Qt.LeftButton:
            """ Add a new point to the rubber band """
            worldPoint = QgsMapToPixel.toMapCoordinates(    self.canvas.getCoordinateTransform(), 
                                                            ev.pos().x(),
                                                            ev.pos().y() )
            self.rb.addPoint( worldPoint , True)
        
        elif ev.button() == Qt.RightButton:
            """ Send back the geomertry to the calling class """
            self.rb.closePoints
            self.geometryReady.emit(self.rb.asGeometry())

    def handleFeature(self, geom, buff, selLyrs, emptyLyrs, openCSV):
        geomOrig = None

        try:
            buffSize = Decimal(buff.value()).quantize(Decimal('.01'), rounding=ROUND_DOWN)
        except:
            buffSize = 0
        
        self.selLayers = bool(selLyrs.isChecked())
        self.empLayers = bool(emptyLyrs.isChecked())

        include = False
        if buffSize != 0:
            geomOrig = geom
            geom = geom.buffer(buffSize, 20)
        resultWriter = self.createResWriter()
        resultWriter.write('"' + geom.asWkt() +'"')
        resultWriter.write('\n')
        # Create list object for complete result list
        res = []

        # Iterate through GUI layers and check against non-identifiable flags and plugin options
        tree = self.proj.layerTreeRoot()
        for node in tree.findLayers():
            if node.layer().type() == QgsMapLayer.VectorLayer:
                identifiable = bool(QgsMapLayer.LayerFlag(node.layer().flags()) & 1)
                print (identifiable)
                if not identifiable:
                    include = False
                    break
                elif not(node.isVisible()) and self.selLayers:
                    include = False
                    break
                else:
                    include = True 
                if include:
                    resultWriter.write("Layer Name : " + str(node.layer().name()) + '\n')
                    res.append(node.layer())
                    res.append(self.spatialSearch(node.layer(), geom, resultWriter))

        resultWriter.close()
        self.maskSelGeom(geom, geomOrig)
        openCSV.setEnabled(True)
        dockRes = self.resultsTreeDockWidget(res, geom)
        
    def maskSelGeom(self, geom, geomOrig):
        self.searchGeom = QgsGeometry(geom)
        self.geomOrig = QgsGeometry(geomOrig)
        self.MLayer = QgsVectorLayer("Polygon?crs=epsg:27700", "Query Polygon", "memory")
        self.MLayer.setCrs( QgsCoordinateReferenceSystem(27700, QgsCoordinateReferenceSystem.EpsgCrsId) )
        fet = QgsFeature()
        origFet = QgsFeature() 
        fet.setGeometry(self.searchGeom)
        origFet.setGeometry(self.geomOrig) 
        self.MLayer.dataProvider().addFeatures( [fet] )
        self.MLayer.dataProvider().addFeatures( [origFet] )  
        self.MLayer.updateExtents() 
        QgsProject.instance().addMapLayer(self.MLayer)
        self.plugin_dir = os.path.dirname(__file__)
        qmlFilePath = os.path.join(self.plugin_dir, 'invSelectedPoly.qml')
        self.MLayer.loadNamedStyle(qmlFilePath)
                
    def resultsTreeDockWidget(self, res, geom):
        self.idFldNameList = ["ogc_fid","fid", "orig_ogc_fid","objectid" , "featureid","lpikey", "uprn", "appnno" ,"nationaluprn",
                              "national_uprn","nationalup", "mi_prinx", "ocella_ref" ,"gid", "assetid", "id"]    
        self.bbox = geom.boundingBox()
        self.treeWidget = QTreeWidget()
        self.treeWidget.setAlternatingRowColors(True)
        header = QTreeWidgetItem(["Feature","Value"])
        self.treeWidget.setHeaderItem(header)
        self.treeWidget.setColumnWidth(0,200)
        self.treeWidget.setSortingEnabled(True)
        self.treeWidget.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.treeWidget.setColumnWidth(1,90)
        self.selmodel = self.treeWidget.selectionModel()
        self.idFldResLayers = {}

        for lyr in res:
            try:
                self.lyrFeatCount = len(lyr)
                lyrName = lyr.name()
                lyrDisplayAtt = lyr.displayField()
                # set rawAttribType for validation (lyr.dataProvider())
            except:
                self.lyrFeatCount = 0

            if lyr != [] or self.empLayers:
                if type(lyr) is list:
                    childResult = QTreeWidgetItem(self.treeWidget)
                    childResult.setText(0, str(lyrName))

                    self.rLayer = self.getLayerFromName(lyrName)
                    self.attFldNames = self.getAttNamesFromLayer(self.rLayer)
                    self.idFldResLayers[str(lyrName)] = self.getIdFldNames()
                    for feat in lyr:

                        attr=feat.attributes()
                        childLayer = QTreeWidgetItem(childResult)
                        try:
                            childLayer.setText(0, str(feat.attributes()[self.rLayer.fields().lookupField(lyrDisplayAtt)]))
                        except:
                            childLayer.setText(0, "Error")
                        i = 0
                        for fld in self.attFldNames:
                            try:
                                if isinstance(attr[i], QDate) and str(attr[i].toPyDate()) == "60823-01-01":
                                    att = NULL
                                elif isinstance(attr[i], QDate):
                                    att = attr[i].toPyDate()
                                else:
                                    att = attr[i]
                                att = "{}".format(att)
                            except:
                                att = "{}".format("Error")
                            # call validateAttributeAsAlphaNum(self, rawAttrib, rawAttribSourceType) 
                            childAtt = QTreeWidgetItem(childLayer, [str(fld), att])
                            i += 1

        self.selmodel.selectionChanged.connect(self.handleSelection)
        self.dw = QDockWidget("Identify Results")
        self.mgr = QWidget()
        
        tool_bar = QToolBar()
        tool_bar.setIconSize(QSize(28, 28))
        
        action_expand = QAction(QIcon(':/plugins/sw2LayerSearch//iDToolExpd.png'), self.tr('Expand All'), self.mgr)
        action_expand.triggered.connect(self.expandTree)
        
        action_collapse = QAction(QIcon(':/plugins/sw2LayerSearch//iDToolColp.png'), self.tr('Collapse All'), self.mgr)
        action_collapse.triggered.connect(self.collapseTree)
        
        tool_bar.addAction(action_expand)
        tool_bar.addAction(action_collapse)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(tool_bar)
        layout.addWidget(self.treeWidget)
        self.mgr.setLayout(layout)
        self.dw.setWidget(self.mgr)
  
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dw)
    

    def expandTree(self):
        self.treeWidget.expandToDepth(0)
        pass
    
    def collapseTree(self):
        self.treeWidget.collapseAll()
        pass
    
    def handleEntered(self, item):
        self.treeWidget.setCurrentItem(item)
        pass
     
    def spatialSearch(self, lyr, geom, writer):
        lyrFeats = lyr.getFeatures(QgsFeatureRequest().setFilterRect(geom.boundingBox()))
        lyrProv = lyr.dataProvider()
        if lyrProv.name() == 'postgres':
            #print(lyrProv.name())
            lstLyrDataSourceUri = lyrProv.dataSourceUri().split()
            #for i in lstLyrDataSourceUri:
                #print("    ", i.split("="))
        fldList = "" 
        for f in lyrProv.fields():
            fldList = fldList + '="' + f.name() + '",'
        writer.write(fldList)
        writer.write('\n')
        lyrFeatList = list()
        for feat in lyrFeats:
            if feat.geometry().intersects(geom):
                lyrFeatList.append(feat.id())
                attList = ""
                for att in feat.attributes():
                    if isinstance(att, QDate) and str(att.toPyDate()) == "60823-01-01":
                        att = NULL
                    elif isinstance(att, QDate):
                        att= att.toPyDate()
                    att = "{}".format(str(att).encode('utf8', 'ignore')).replace(',',' ')
                    attList = attList + '="' + att + '",'
                writer.write(attList)
                writer.write('\n')
        lyr.selectByIds(lyrFeatList) #setSelectedFeatures
        writer.write("Layer feature count : " + str(lyr.selectedFeatureCount()) + '\n\n')
        return lyr.selectedFeatures()

    def handleSelection(self,  selected, deselected):
        expr = ""
        zoomExprBuilt = False
        for a in iface.attributesToolBar().actions():
            if a.objectName() == 'mActionDeselectAll':
                a.trigger()
                break
        c =1
        index = selected.indexes()[0]
        item = self.treeWidget.itemFromIndex(index)
        if item.parent() == None:
            zoomExprBuilt = False
            print("zoomExprBuilt = False")
        
        elif item.childCount() == 0: #child
            self.zLayer = self.getLayerFromName(str(item.parent().parent().text(0)))
            self.selAttFldNames = self.getAttNamesFromLayer(self.zLayer)
            idFldName = str(self.idFldResLayers.get(self.zLayer.name()))

            for i in range(0 , item.parent().childCount()):
                if idFldName == item.parent().child(i).text(0):
                    #print(">", '"' + idFldName + '"' +" ='" + str(item.parent().child(i).text(1))+"'")
                    expr = QgsExpression('"' + idFldName + '"' +" ='" + str(item.parent().child(i).text(1))+"'")

                    zoomExprBuilt = True
        
        else: #Parent
            self.zLayer = self.getLayerFromName(str(item.parent().text(0)))
            self.selAttFldNames = self.getAttNamesFromLayer(self.zLayer)
            idFldName = str(self.idFldResLayers.get(self.zLayer.name()))

            for i in range(0 , item.childCount()):
                if idFldName == item.child(i).text(0):
                    #print(">", '"' + idFldName + '"' +" ='" + str(item.child(i).text(1))+"'")
                    expr = QgsExpression('"' + idFldName + '"' +" ='" + str(item.child(i).text(1))+"'")

                    zoomExprBuilt = True

        if zoomExprBuilt:
            try:
                request = QgsFeatureRequest( expr )
                it = self.zLayer.getFeatures( request )  #it = self.zLayer.selectByExpression(expr)
                c = 1
                for f in it:
                    hGeom = f.geometry()
                    c += 1
            
            except:
                print("Error: problem building Expression or Request for this feature")

            try:
                self.polygon.hide()
                self.polygon = None
            except:
                pass
            
            try:
                self.polygon = QgsRubberBand(iface.mapCanvas())
                self.polygon.setToGeometry(hGeom, None)
                self.polygon.setColor(QColor(255,0,0,127))
                self.polygon.setFillColor(QColor(255,0,0,108))
                self.polygon.setWidth(10)
                self.polygon.show()
            except:
                pass
                
    def getAttNamesFromLayer(self,lyr):
        attNames = []
        prov = lyr.dataProvider()
        attNames = [field.name().lower() for field in prov.fields()]
        return attNames
    
    def getLayerFromName(self, lyrName):
        vLayer = QgsMapLayer.VectorLayer
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.type() == QgsMapLayer.VectorLayer:
                if str(lyrName).lower() == str(lyr.name()).lower():
                    vLayer = lyr
                    break
        return vLayer
    
    def getIdFldNames(self):
        #self.idFldNameList = ["ogc_fid", "orig_ogc_fid","objectid" , "featureid","lpikey", "uprn", "appnno" ,"nationaluprn",
        #                      "national_uprn","nationalup", "mi_prinx", "ocella_ref" ,"gid", "assetid", "id"]  
        idxMatchCount = 0
        matchedAttIdx = 0
        self.idFieldName = ""
        for idFld in self.idFldNameList:
            for attFld in self.attFldNames:
                if str(attFld).lower() == str(idFld).lower():
                    self.idFieldName = str(attFld)
                    idxMatchCount += 1
                    if self.idFldNameList.index(str(attFld)) <= matchedAttIdx:
                        self.idFieldName = str(attFld)
        return self.idFieldName

    def resetProjectSearch(self):
        try:
            self.QLayer = self.getLayerFromName("Query Polygon")
            QgsProject.instance().removeMapLayers([self.QLayer.id()])
            iface.mainWindow().findChild(QAction, 'mActionDeselectAll').trigger()			
            self.iface.mapCanvas().refresh()
        except:
            pass
        try:
            self.polygon.hide()
            self.polygon = None
        except:
            pass

    def validateAttributeAsAlphaNum(self, rawAttrib, rawAttribSourceType):
        pass

    def getPGPKfromSchemaAndTable(self, pgSchName, pgTabName):
        try:
            conn = pg.connect("dbname='base_mapping' user='postgres' host='sw2-gis.wychavon.gov.uk' password='postgres..'")
            keySql =   "SELECT c.column_name, c.data_type FROM information_schema.table_constraints tc \
                        JOIN information_schema.constraint_column_usage AS ccu USING (constraint_schema, constraint_name) \
                        JOIN information_schema.columns AS c ON c.table_schema = tc.constraint_schema AND tc.table_name = \
                        c.table_name AND ccu.column_name = c.column_name WHERE constraint_type = 'PRIMARY KEY' \
                        and tc.table_name = '"+ pgTabName + "' and tc.table_schema = '"+ pgSchName + "';"
            curr = conn.cursor()
            curr.execute(keySql)
            res = curr.fetchall()
            print("Key Name:", res[0][0], "Key Type:",res[0][1])
            curr.close()
        except:
            print("I am unable to connect to the database")
        return res