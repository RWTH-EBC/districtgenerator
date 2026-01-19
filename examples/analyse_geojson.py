import osmnx as ox
import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from shapely.geometry import Point
import warnings

warnings.filterwarnings('ignore')

# OSMnx Config
ox.settings.use_cache = True  # use cache to speed up repeated queries
ox.settings.log_console = False  # disable logging in order to keep output clean


def load_quartiere(geojson_path):
    """
    Load all districts from GeoJSON
    """
    gdf = gpd.read_file(geojson_path)  # load GeoJSON
    # Ensure CRS is WGS84
    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    return gdf


def extract_osm_data(polygon, district_name):
    """
    To be called for each district to extract OSM data.
    Arguments:
        polygon: shapely Polygon of the district
        district_name: Name/ID of the district (for logging)
    Returns:
        buildings: GeoDataFrame of buildings
        street_edges: GeoDataFrame of street edges (edge meaning street segments between intersections)
    """
    try:
        print(f"  Extract data for {district_name}...")
        # Buildings
        buildings = ox.features_from_polygon(polygon, tags={"building": True})
        if buildings.empty:
            print(f"    Warning: No building data found for {district_name}")
            return None, None

        # log level data, if available
        if 'building:levels' in buildings.columns:
            n_levels = buildings['building:levels'].notna().sum()
            print(f"    Found building level data for {n_levels} buildings.")
        else:
            print(f"    No building level data available.")

        # Street Network
        try:
            streets = ox.graph_from_polygon(polygon, network_type="drive")
            street_edges = ox.graph_to_gdfs(streets, nodes=False)  # extract edges only
        except:
            print(f"    Warning: Could not extract street network for {district_name}")
            street_edges = None
        return buildings, street_edges

    except Exception as e:
        print(f"Error at {district_name}: {e}")
        return None, None


def calculate_all_metrics(buildings, street_edges, polygon):
    """
    Calculates all desired metrics for a district.
    Project once, then compute all metrics.
    Arguments:
        buildings: GeoDataFrame of buildings
        street_edges: GeoDataFrame of street edges
        polygon: shapely Polygon of the district
    Returns:
        metrics: dict with all calculated metrics
    """
    metrics = {}  # dict to hold all metrics

    # ===================================================
    # Projection
    # ===================================================
    polygon_proj = gpd.GeoSeries([polygon], crs="EPSG:4326").to_crs("EPSG:3857").iloc[
        0]  # project polygon to Web Mercator
    quartier_area = polygon_proj.area  # total district area [m²]
    quartier_area_ha = quartier_area / 10000  # total district area [ha]

    metrics['quartier_area'] = quartier_area / 100000  # store area in km² in metrics
    metrics['quartier_area_ha'] = quartier_area_ha  # store area in ha in metrics

    # ===================================================
    # Building Metrics
    # ===================================================

    if buildings is not None and len(buildings) > 0:
        # =================================================
        # Building Footprint Areas & Counts
        # =================================================
        buildings_proj = buildings.to_crs("EPSG:3857")  # project buildings to Web Mercator
        building_areas = buildings_proj.area  # get areas of buildings [m²]
        n_buildings = len(buildings)  # number of buildings
        total_building_area = building_areas.sum()  # total building area [m²]

        # Store "Grundflächenzahl" (GRZ) to metrics
        metrics['building_coverage_ratio'] = total_building_area / quartier_area

        # Store buildings per hektar to metrics
        metrics['buildings_per_hectare'] = n_buildings / quartier_area_ha

        # Further Metrics (optional)
        # metrics['n_buildings'] = n_buildings
        # metrics['mean_building_area'] = building_areas.mean()
        # metrics['median_building_area'] = building_areas.median()
        # metrics['std_building_area'] = building_areas.std()
        # metrics['total_building_area'] = total_building_area

        # =================================================
        # Building Levels
        # =================================================
        metrics['buildings_with_levels_count'] = 0
        metrics['buildings_with_levels_pct'] = 0.0
        metrics['gfz'] = np.nan

        if 'building:levels' in buildings.columns:
            levels = pd.to_numeric(buildings['building:levels'], errors='coerce')

            if not levels.empty:
                n_buildings = len(buildings)
                n_with_levels = len(levels)
                pct_with_levels = n_with_levels / n_buildings if n_buildings > 0 else 0

                # write to metrics
                metrics['buildings_with_levels_count'] = n_with_levels
                metrics['buildings_with_levels_pct'] = pct_with_levels

                mean_levels = levels.mean()
                metrics['building_levels_mean'] = mean_levels
                metrics['building_levels_min'] = levels.min()
                metrics['building_levels_max'] = levels.max()
                # metrics['building_levels_median'] = levels.median()

                    # calculate GFZ only if at least 66% of buildings have level data
                if pct_with_levels >= 0.66:
                    # sort buildings by level data availability
                    has_levels = buildings['building:levels'].notna()
                    no_levels = buildings['building:levels'].isna()

                    # real GFZ for buildings with known levels
                    # for each building with known levels: footprint area * number of levels
                    known_levels_numeric = pd.to_numeric(buildings.loc[has_levels, 'building:levels'], errors='coerce')
                    gross_floor_area_known = (buildings_proj.loc[has_levels].area * known_levels_numeric).sum()

                    # estimated GFZ for buildings without level data
                    # sum of footprint areas * mean number of levels
                    unknown_footprint_area = buildings_proj.loc[no_levels].area.sum()
                    gross_floor_area_estimated = unknown_footprint_area * mean_levels

                    # calculate GFZ
                    metrics['gfz'] = (gross_floor_area_known + gross_floor_area_estimated) / quartier_area

                    # alternative: use average number of levels for all buildings
                    # metrics['gfz'] = (total_building_area * mean_levels) / quartier_area

        # =================================================
        # Spacing between House Connections, measured along streets
        # =================================================
        """
        Calculates the spacing between neighboring buildings along streets. 
        This serves as a proxy for the spacing of house connection points.
        Arguments:
            buildings_proj: GeoDataFrame of buildings projected to a metric CRS
            street_edges: GeoDataFrame of street edges projected to a metric CRS
        Returns:
            house_spacings: list of spacings between neighboring buildings along streets
            min, max, mean stored in metrics
        """

        house_spacings = []

        if street_edges is not None and len(street_edges) > 0:
            streets_proj = street_edges.to_crs("EPSG:3857")  # project streets to Web Mercator

            # Assign buildings to nearest street segment
            building_to_street = {}
            for building_idx in buildings_proj.index:
                building_geom = buildings_proj.loc[building_idx, 'geometry']  # get building geometry
                distances = streets_proj.distance(building_geom)  # distances to all street segments
                nearest_street_idx = distances.idxmin()  # index of nearest street segment
                min_distance = distances.min()  # minimum distance

                # Only consider buildings within 20m of a street
                if min_distance < 20:
                    if nearest_street_idx not in building_to_street:
                        building_to_street[nearest_street_idx] = []
                    building_to_street[nearest_street_idx].append(building_idx)  # assign building to street segment

            # Calculate spacings along each street segment
            for street_idx, building_indices in building_to_street.items():
                if len(building_indices) < 2:  # need at least 2 buildings to calculate spacing
                    continue  # skip if less than 2 buildings assigned

                street = streets_proj.loc[street_idx]  # get street segment
                centroids = buildings_proj.loc[building_indices].centroid  # get centroids of assigned buildings

                # Calculate positions along the street
                positions = []
                for cent in centroids:  # iterate over centroids
                    pos = street.geometry.project(cent)  # position along the street
                    positions.append((pos, cent))  # store position and centroid

                # sort by position along the street
                positions.sort(key=lambda x: x[0])

                # Calculate spacings between consecutive buildings
                for i in range(len(positions) - 1):
                    spacing = positions[i + 1][1].distance(positions[i][1])
                    house_spacings.append(spacing)

        if house_spacings:
            # Store distance of neighboring house connections to metrics
            # metrics['list_of_house_connection_spacings'] = house_spacings  # store full list
            metrics['house_connection_spacing_min'] = np.min(house_spacings)
            metrics['house_connection_spacing_max'] = np.max(house_spacings)
            metrics['house_connection_spacing_mean'] = np.mean(house_spacings)
            # metrics['house_connection_spacing_median'] = np.median(house_spacings)
            # metrics['house_connection_spacing_std'] = np.std(house_spacings)

        # =================================================
        # Length of House Connection Lines
        # =================================================
        """
        Calculates the lengths of house connection lines from buildings to nearest street segment.
        Arguments:
            buildings_proj: GeoDataFrame of buildings projected to a metric CRS
            street_edges: GeoDataFrame of street edges projected to a metric CRS
        Returns:
            house_connection_lengths: list of lengths from buildings to nearest street segment
            min, max, mean stored in metrics
        """
        if street_edges is not None and len(street_edges) > 0:
            streets_proj = street_edges.to_crs("EPSG:3857")

            house_connection_lengths = []  # list to hold lengths
            for idx, building in buildings_proj.iterrows():  # iterate over buildings
                dists_to_streets = streets_proj.distance(building.geometry)  # distances to all street segments
                min_dist = dists_to_streets.min()  # minimum distance to nearest street
                house_connection_lengths.append(min_dist)  # store shortest distance as house connection length

            # Store length of house connection lines to metrics
            # metrics['list_of_house_connection_lengths'] = house_connection_lengths  # store full list
            metrics['house_connection_length_min'] = np.min(house_connection_lengths)
            metrics['house_connection_length_max'] = np.max(house_connection_lengths)
            metrics['house_connection_length_mean'] = np.mean(house_connection_lengths)
            # metrics['house_connection_length_median'] = np.median(house_connection_lengths)
            # metrics['house_connection_length_std'] = np.std(house_connection_lengths)

    # ===================================================
    # Street Network Metrics
    # ===================================================
    """
    Calculates metrics related to the street network.
    Arguments:
        street_edges: GeoDataFrame of street edges
    Returns:
        street segment lengths: min, max, mean stored in metrics
    """
    if street_edges is not None and len(street_edges) > 0:
        streets_proj = street_edges.to_crs("EPSG:3857")
        street_lengths = streets_proj.length

        # Length of street segments
        # metrics['list_of_street_segment_lengths'] = street_lengths.tolist()  # store full list
        metrics['street_segment_length_min'] = street_lengths.min()
        metrics['street_segment_length_max'] = street_lengths.max()
        metrics['street_segment_length_mean'] = street_lengths.mean()

        # Additional street metrics (optional)
        # metrics['n_streets'] = len(street_edges)
        # metrics['total_street_length'] = street_lengths.sum()
        # metrics['street_density'] = street_lengths.sum() / quartier_area  # m Straße / m² Quartier
        # metrics['median_street_length'] = street_lengths.median()
        # metrics['std_street_length'] = street_lengths.std()

    return metrics


def main():
    # Load Districts
    print("Load Districts...")
    quartiere = load_quartiere("C:/Users/rha-jpa/Downloads/districts_complete.geojson")
    print(f"  {len(quartiere)} Finished loading districts.")
    print(f"  Types: {quartiere['Typ'].unique()}")

    # Extract OSM Data & Calculate Metrics
    results = []

    for idx, row in quartiere.iterrows():
        quartier_id = f"{row['Quartier ID']}_{row['Typ']}_{row['Bundeslang/Region']}"
        polygon = row.geometry

        print(f"\nProcessing district {quartier_id}...")

        # get OSM data
        buildings, streets = extract_osm_data(polygon, quartier_id)

        # calculate all metrics
        metrics = calculate_all_metrics(buildings, streets, polygon)

        # collect results
        result = {
            'quartier_id': quartier_id,
            'typ': row['Typ'],
            'ort': row['Bundeslang/Region'],
            **metrics
        }
        results.append(result)

    # put results into DataFrame
    df_results = pd.DataFrame(results)

    # save results to CSV
    df_results.to_csv("quartiere_metriken.csv", index=False)
    print("\n✓ Metriken gespeichert in 'quartiere_metriken.csv'")

    # # Summary of Metrics
    # print("\n" + "=" * 80)
    # print("ZUSAMMENFASSUNG DER METRIKEN (über alle Quartiere)")
    # print("=" * 80)
    #
    desired_metrics = [
        'building_coverage_ratio',  # Grundflächenzahl
        'buildings_per_hectare',  # Gebäude pro Hektar
        'street_segment_length_min',  # Länge Netzstraßenabschnitte
        'street_segment_length_max',
        'street_segment_length_mean',
        'house_connection_spacing_min',  # Abstand Hausanschlüsse
        'house_connection_spacing_max',
        'house_connection_spacing_mean',
        'house_connection_length_min',  # Länge Hausanschlussleitungen
        'house_connection_length_max',
        'quartier_area'  # Quartiersfläche
    ]
    #
    # summary = df_results[desired_metrics].describe()
    # print(summary)

    # ===================================================
    # Compare by District Type
    # ===================================================
    print("\n" + "=" * 80)
    print("STATISTICS BY DISTRICT TYPE")
    print("=" * 80)

    typ_statistics = []

    for typ in df_results['typ'].unique():
        typ_data = df_results[df_results['typ'] == typ]
        print(f"\n{'=' * 60}")
        print(f"Typ {typ} (n={len(typ_data)}):")
        print(f"{'=' * 60}")

        # Konsolidiere Metriken
        consolidated_metrics = {
            'building_coverage_ratio': typ_data['building_coverage_ratio'],
            'gfz': typ_data['gfz'],
            'buildings_per_hectare': typ_data['buildings_per_hectare'],
            'quartier_area': typ_data['quartier_area_ha'],
        }

        # Street segment length: nimm min von _min, max von _max, mean von _mean
        if 'street_segment_length_min' in typ_data.columns:
            consolidated_metrics['street_segment_length'] = pd.Series({
                'min': typ_data['street_segment_length_min'].min(),
                'max': typ_data['street_segment_length_max'].max(),
                'mean': typ_data['street_segment_length_mean'].mean()
            })

        # House connection spacing
        if 'house_connection_spacing_min' in typ_data.columns:
            consolidated_metrics['house_connection_spacing'] = pd.Series({
                'min': typ_data['house_connection_spacing_min'].min(),
                'max': typ_data['house_connection_spacing_max'].max(),
                'mean': typ_data['house_connection_spacing_mean'].mean()
            })

        # House connection length
        if 'house_connection_length_min' in typ_data.columns:
            consolidated_metrics['house_connection_length'] = pd.Series({
                'min': typ_data['house_connection_length_min'].min(),
                'max': typ_data['house_connection_length_max'].max(),
                'mean': typ_data['house_connection_length_mean'].mean()
            })

        # Berechne Statistiken
        for metric_name, metric_data in consolidated_metrics.items():
            if isinstance(metric_data, pd.Series) and 'min' in metric_data.index:
                # Bereits konsolidierte Metrik (hat min/max/mean)
                stats_row = {
                    'typ': typ,
                    'metric': metric_name,
                    'min': metric_data['min'],
                    'max': metric_data['max'],
                    'mean': metric_data['mean']
                }
            else:
                # Normale Metrik (berechne min/max/mean)
                stats_row = {
                    'typ': typ,
                    'metric': metric_name,
                    'min': metric_data.min(),
                    'max': metric_data.max(),
                    'mean': metric_data.mean()
                }

            typ_statistics.append(stats_row)
            print(
                f"  {metric_name}: min={stats_row['min']:.2f}, max={stats_row['max']:.2f}, mean={stats_row['mean']:.2f}")

    # Speichere Statistiken
    df_typ_stats = pd.DataFrame(typ_statistics)
    df_typ_stats.to_csv("quartiere_typen_statistik.csv", index=False)
    print("\n✓ Per-type statistics saved to 'quartiere_typen_statistik.csv'")

    return df_results


if __name__ == "__main__":
    df_results = main()