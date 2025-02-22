import numpy as np
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsField,
                       QgsCoordinateTransform, QgsVectorFileWriter, QgsGeometry)
from qgis.PyQt.QtCore import QVariant
from osgeo import gdal
import processing

def get_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        raise ValueError(f"Layer '{name}' not found!")
    return layers[0]

# Configuration - UPDATE THESE VALUES
RASTER_LAYER_NAME = "your_raster_layer_name"
VECTOR_LAYER_NAME = "your_vector_layer_name"
OUTPUT_SHP_PATH = "C:/output/path/result.shp"  # Use forward slashes or double backslashes

try:
    # Load layers
    raster_layer = get_layer(RASTER_LAYER_NAME)
    vector_layer = get_layer(VECTOR_LAYER_NAME)
    original_crs = vector_layer.crs()

    # Create output layer with proper CRS
    output_layer = QgsVectorLayer(f"Polygon?crs={original_crs.authid()}", "temp_results", "memory")
    output_data = output_layer.dataProvider()

    # Add fields (original + new)
    new_fields = vector_layer.fields().toList() + [QgsField("pct_99", QVariant.Double)]
    output_data.addAttributes(new_fields)
    output_layer.updateFields()

    # CRS transformation setup
    raster_crs = raster_layer.crs()
    transform_context = QgsProject.instance().transformContext()

    # Processing loop
    for idx, feature in enumerate(vector_layer.getFeatures()):
        original_geom = feature.geometry()
        attributes = feature.attributes()
        
        # Create transformed geometry for raster processing
        processing_geom = QgsGeometry(original_geom)
        if original_crs != raster_crs:
            xform = QgsCoordinateTransform(original_crs, raster_crs, transform_context)
            processing_geom.transform(xform)

        # Create temporary layer for clipping
        temp_vector = QgsVectorLayer(f"Polygon?crs={raster_crs.authid()}", "temp", "memory")
        temp_data = temp_vector.dataProvider()
        temp_feature = QgsFeature()
        temp_feature.setGeometry(processing_geom)
        temp_data.addFeatures([temp_feature])
        temp_vector.updateExtents()

        percentile = None
        try:
            # Clip raster
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
            data = band.ReadAsArray()
            if data is not None:
                data_flat = data.flatten()
                nodata = band.GetNoDataValue()
                if nodata is not None:
                    data_flat = data_flat[data_flat != nodata]
                if data_flat.size > 0:
                    percentile = np.percentile(data_flat, 99)
            ds = None

        except Exception as e:
            print(f"Error processing feature {idx}: {str(e)}")

        # Create output feature with ORIGINAL geometry
        new_feature = QgsFeature(output_layer.fields())
        new_feature.setGeometry(original_geom)  # Use original untransformed geometry
        new_feature.setAttributes(attributes + [percentile])
        output_data.addFeature(new_feature)

        print(f"Processed {idx+1}/{vector_layer.featureCount()}")

    # Save to shapefile
    save_options = QgsVectorFileWriter.SaveVectorOptions()
    save_options.driverName = "ESRI Shapefile"
    save_options.fileEncoding = "UTF-8"

    writer = QgsVectorFileWriter.writeAsVectorFormatV2(
        output_layer,
        OUTPUT_SHP_PATH,
        transform_context,
        save_options
    )

    if writer[0] == QgsVectorFileWriter.NoError:
        # Load the result and zoom to it
        result_layer = QgsVectorLayer(OUTPUT_SHP_PATH, "Percentile Results", "ogr")
        QgsProject.instance().addMapLayer(result_layer)
        result_layer.triggerRepaint()
        print(f"Success! Layer loaded at: {OUTPUT_SHP_PATH}")
    else:
        print("Failed to save output file!")

except Exception as e:
    print(f"Error: {str(e)}")
