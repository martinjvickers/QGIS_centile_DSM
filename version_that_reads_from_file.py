import numpy as np
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsField,
                       QgsCoordinateTransform, QgsVectorFileWriter)
from qgis.PyQt.QtCore import QVariant
from osgeo import gdal
import processing

# Get layers by name from QGIS project
def get_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        raise ValueError(f"Layer '{name}' not found in project!")
    return layers[0]

# User input - change these layer names to match your QGIS layers
RASTER_LAYER_NAME = "canopyp1_resized"
VECTOR_LAYER_NAME = "james_plots"
OUTPUT_SHP_PATH = "/Users/mvickers/result.shp"  # Change this to your desired output path

try:
    # Load layers from QGIS project
    raster_layer = get_layer(RASTER_LAYER_NAME)
    vector_layer = get_layer(VECTOR_LAYER_NAME)
    
    # Create output layer with new field
    output_layer = QgsVectorLayer("Polygon", "results", "memory")
    output_data = output_layer.dataProvider()
    
    # Copy fields from original vector and add new percentile field
    original_fields = vector_layer.fields()
    output_data.addAttributes(original_fields.toList() + [QgsField("pct_99", QVariant.Double)])
    output_layer.updateFields()
    
    # Get CRS information
    raster_crs = raster_layer.crs()
    vector_crs = vector_layer.crs()
    transform_context = QgsProject.instance().transformContext()
    
    # Main processing loop
    for idx, feature in enumerate(vector_layer.getFeatures()):
        geom = feature.geometry()
        original_attributes = feature.attributes()
        
        # Transform geometry if necessary
        if vector_crs != raster_crs:
            xform = QgsCoordinateTransform(vector_crs, raster_crs, transform_context)
            geom.transform(xform)
        
        # Create temporary layer for current feature
        temp_vector = QgsVectorLayer(f"Polygon?crs={raster_crs.authid()}", "temp", "memory")
        temp_data = temp_vector.dataProvider()
        temp_feature = QgsFeature()
        temp_feature.setGeometry(geom)
        temp_data.addFeatures([temp_feature])
        temp_vector.updateExtents()
        
        percentile = None  # Default value if calculation fails
        
        try:
            # Clip raster to polygon
            params = {
                'INPUT': raster_layer,
                'MASK': temp_vector,
                'CROP_TO_CUTLINE': True,
                'KEEP_RESOLUTION': True,
                'NODATA': None,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }
            clipped = processing.run("gdal:cliprasterbymasklayer", params)['OUTPUT']
            
            # Calculate percentile
            ds = gdal.Open(clipped)
            band = ds.GetRasterBand(1)
            nodata = band.GetNoDataValue()
            data = band.ReadAsArray()
            
            if data is not None:
                data_flat = data.flatten()
                if nodata is not None:
                    data_flat = data_flat[data_flat != nodata]
                if data_flat.size > 0:
                    percentile = np.percentile(data_flat, 99)
            
            ds = None  # Cleanup GDAL dataset
        
        except Exception as e:
            print(f"Error processing feature {idx}: {str(e)}")
        
        # Create new feature with results
        new_feature = QgsFeature(output_layer.fields())
        new_feature.setGeometry(feature.geometry())  # Original geometry
        new_feature.setAttributes(original_attributes + [percentile])
        output_data.addFeature(new_feature)
        
        print(f"Processed feature {idx+1} of {vector_layer.featureCount()}")

    # Save results to shapefile
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "ESRI Shapefile"
    options.fileEncoding = "UTF-8"
    
    writer = QgsVectorFileWriter.writeAsVectorFormatV2(
        output_layer,
        OUTPUT_SHP_PATH,
        transform_context,
        options
    )
    
    if writer[0] == QgsVectorFileWriter.NoError:
        # Load resulting layer to QGIS
        result_layer = QgsVectorLayer(OUTPUT_SHP_PATH, "Results", "ogr")
        QgsProject.instance().addMapLayer(result_layer)
        print(f"\nSuccess! Output saved to: {OUTPUT_SHP_PATH}")
    else:
        print("\nError saving output file!")

except Exception as e:
    print(f"Fatal error: {str(e)}")
