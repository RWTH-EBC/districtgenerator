import geopandas as gpd
import os

# Add your path here
gpkg_path = r""

# Heat cadastre consists of mutiple layers --> just lost ohne
gdf = gpd.read_file(gpkg_path)

# Extract coordinates and add them as separate columns
gdf['x'] = gdf.geometry.x
gdf['y'] = gdf.geometry.y

# Storage paths for CSV and Excel files in the same folder as the GPKG file
output_dir = os.path.dirname(gpkg_path)
csv_path = os.path.join(output_dir, ".csv")
excel_path = os.path.join(output_dir, ".xlsx")

# Save as csv
gdf.drop(columns=['geometry']).to_csv(csv_path, index=False)

# Save as xlsx
gdf.drop(columns=['geometry']).to_excel(excel_path, index=False)
