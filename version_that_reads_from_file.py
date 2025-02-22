import numpy as np
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature,
                       QgsCoordinateTransform, QgsRasterLayer)
from osgeo import gdal
import processing

# Set your input paths here
raster_path = '/Users/mvickers/canopyp1_resized.tif'
shapefile_path = '/Users/mvickers/james_plots.shp'

# Load layers
raster_layer = QgsRasterLayer(raster_path, "raster")
vector_layer = QgsVectorLayer(shapefile_path, "vector", "ogr")

# Validate layers
if not raster_layer.isValid():
    print("Raster layer failed to load!")
    exit()

if not vector_layer.isValid():
    print("Vector layer failed to load!")
    exit()

# Get CRS information
raster_crs = raster_layer.crs()
vector_crs = vector_layer.crs()
transform_context = QgsProject.instance().transformContext()

# Dictionary to store results {feature_id: 99th_percentile}
results = {}

# Main processing loop
for feature in vector_layer.getFeatures():
    # Get and transform geometry if necessary
    geom = feature.geometry()
    if vector_crs != raster_crs:
        xform = QgsCoordinateTransform(vector_crs, raster_crs, transform_context)
        geom.transform(xform)
    
    # Create temporary vector layer for current feature
    temp_vector = QgsVectorLayer(f"Polygon?crs={raster_crs.authid()}", "temp", "memory")
    temp_data = temp_vector.dataProvider()
    temp_feature = QgsFeature()
    temp_feature.setGeometry(geom)
    temp_data.addFeatures([temp_feature])
    temp_vector.updateExtents()
    
    # Set up clip parameters
    params = {
        'INPUT': raster_layer,
        'MASK': temp_vector,
        'CROP_TO_CUTLINE': True,
        'KEEP_RESOLUTION': True,
        'NODATA': None,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    }
    
    try:
        # Execute clip
        clipped = processing.run("gdal:cliprasterbymasklayer", params)['OUTPUT']
        
        # Open clipped raster with GDAL
        ds = gdal.Open(clipped)
        band = ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        
        # Read raster data
        data = band.ReadAsArray()
        data_flat = data.flatten()
        
        # Filter out nodata values
        if nodata is not None:
            data_flat = data_flat[data_flat != nodata]
        
        # Calculate percentile
        if data_flat.size > 0:
            percentile = np.percentile(data_flat, 99)
        else:
            percentile = None
        
        # Store result
        results[feature.id()] = percentile
        
        # Cleanup
        del ds, clipped, data
    
    except Exception as e:
        print(f"Error processing feature {feature.id()}: {str(e)}")
        results[feature.id()] = None

# Print results
print("\nResults (Feature ID: 99th Percentile):")
for fid, val in results.items():
    print(f"Feature {fid}: {val if val is not None else 'N/A'}")
