from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsRectangle
)
import numpy as np

# Load your vector and raster layers (make sure they're already in your QGIS project)
vector_layer = QgsProject.instance().mapLayersByName("testing")[0]
raster_layer = QgsProject.instance().mapLayersByName("Coppers_field_LIDAR-2024-08-01")[0]

if not vector_layer or not raster_layer:
    raise Exception("Ensure both the vector and raster layers are loaded in the project and have correct names.")

# Get CRS of the raster layer
raster_crs = raster_layer.crs()

# Set up a CRS transformer
transformer = QgsCoordinateTransform(vector_layer.crs(), raster_crs, QgsProject.instance())

# Get raster data provider
raster_provider = raster_layer.dataProvider()

# Loop through each feature (polygon) in the vector layer
for feature in vector_layer.getFeatures():
    geom = feature.geometry()

    # Transform the polygon to the raster CRS
    geom.transform(transformer)

    # Get the bounding box of the polygon in the raster CRS
    bbox = geom.boundingBox()

    # Calculate pixel resolution
    raster_extent = raster_layer.extent()
    raster_width = raster_layer.width()
    raster_height = raster_layer.height()
    pixel_width = raster_extent.width() / raster_width
    pixel_height = raster_extent.height() / raster_height

    # Determine raster block dimensions
    xmin = bbox.xMinimum()
    xmax = bbox.xMaximum()
    ymin = bbox.yMinimum()
    ymax = bbox.yMaximum()

    cols = int((xmax - xmin) / pixel_width)
    rows = int((ymax - ymin) / pixel_height)

    if cols <= 0 or rows <= 0:
        print(f"Feature {feature.id()} results in zero-sized raster block. Skipping.")
        continue

    # Fetch raster block for the polygon's bounding box
    raster_block = raster_provider.block(1, bbox, cols, rows)

    if raster_block is None:
        print(f"Failed to fetch raster block for feature {feature.id()}. Skipping.")
        continue

    # Convert raster block values to a NumPy array
    raster_values = np.array([
        [raster_block.value(x, y) for x in range(raster_block.width())] for y in range(raster_block.height())
    ])

    # Mask values outside the polygon
    mask = np.ones(raster_values.shape, dtype=bool)
    for y in range(raster_values.shape[0]):
        for x in range(raster_values.shape[1]):
            x_coord = xmin + x * pixel_width
            y_coord = ymax - y * pixel_height  # Reverse y for raster row order
            point = QgsGeometry.fromPointXY(QgsPointXY(x_coord, y_coord))
            if geom.contains(point):
                mask[y, x] = False

    masked_array = np.ma.array(raster_values, mask=mask)
    quartile = np.percentile(masked_array.compressed(), 99)
    print(quartile)
