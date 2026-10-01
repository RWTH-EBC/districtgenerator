"""Discover and analyse ~40-building OSM districts in StaedteRegion Aachen.

Requires osmnx, geopandas, shapely, scipy, pyproj, openpyxl and folium. Download once with
--download; cached GeoParquet/GeoJSON are reused for offline runs. The input
workbook is opened read-only and verified by SHA-256 before/after each run.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import math
import heapq
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Optional fallback dependencies installed for the desktop pilot. Keep them
# behind the active environment so compiled packages such as NumPy, pandas and
# GeoPandas are never mixed across installations.
LOCAL_DEPS = ROOT / '.codex_tmp/aachen_deps'
if LOCAL_DEPS.exists():
    sys.path.append(str(LOCAL_DEPS))

import geopandas as gpd
import numpy as np
import openpyxl
import pandas as pd
import shapely
try:
    import folium
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "The Aachen review map requires Folium. Install it in the selected "
        "Python environment with: python -m pip install folium"
    ) from exc
from shapely.geometry import LineString, Point
from shapely.ops import polygonize, split, substring, unary_union


POI_TAGS = {
    'shop': True,
    'amenity': True,
    'office': True,
    'craft': True,
    'building': True,
    'building:flats': True,
    'building:use': True,
    'landuse': True,
    'leisure': True,
    'tourism': True,
    'healthcare': True,
    'industrial': True,
    'sport': True,
    'man_made': True,
    'railway': True,
    'public_transport': True,
}
GROCERY_SHOPS = {
    'supermarket', 'convenience', 'grocery', 'greengrocer', 'bakery',
    'butcher', 'deli', 'beverages', 'alcohol', 'seafood', 'frozen_food',
    'health_food'}
FOOD_AMENITIES = {
    'restaurant', 'cafe', 'fast_food', 'bar', 'pub', 'biergarten',
    'food_court', 'ice_cream'}
RESIDENTIAL_BUILDINGS = {
    'residential', 'apartments', 'bungalow', 'farm', 'house', 'detached',
    'semidetached_house', 'terrace', 'dormitory'}
OFFICE_BUILDINGS = {'office', 'government'}
SCHOOL_BUILDINGS = {'school', 'college'}
UNIVERSITY_BUILDINGS = {'university', 'college'}
HOSPITAL_BUILDINGS = {'hospital', 'clinic'}
CULTURE_BUILDINGS = {
    'theatre', 'cinema', 'museum', 'library', 'community_centre'}
SPORT_BUILDINGS = {
    'sports_hall', 'stadium', 'grandstand', 'pavilion', 'sports_centre',
    'riding_hall'}
WORKSHOP_BUILDINGS = {
    'industrial', 'warehouse', 'workshop', 'manufacture', 'factory'}
RETAIL_BUILDINGS = {'retail', 'supermarket', 'kiosk'}
CULTURE_AMENITIES = {
    'theatre', 'cinema', 'arts_centre', 'community_centre', 'library',
    'events_venue', 'conference_centre', 'exhibition_centre', 'music_venue',
    'planetarium'}
CULTURE_TOURISM = {
    'museum', 'gallery', 'artwork', 'conference_centre',
    'exhibition_centre', 'music_venue', 'planetarium'}
SPORT_LEISURE = {
    'sports_centre', 'fitness_centre', 'stadium', 'pitch', 'swimming_pool',
    'sports_hall'}
HOSPITAL_AMENITIES = {'hospital', 'clinic', 'doctors', 'dentist'}
HOSPITAL_HEALTHCARE = {
    'hospital', 'clinic', 'doctor', 'dentist', 'dialysis', 'medical_imaging',
    'rehabilitation'}
OFFICE_AMENITIES = {'townhall', 'courthouse'}
OTHER_NRB_AMENITIES = {
    'place_of_worship', 'police', 'fire_station', 'social_facility',
    'nursing_home', 'post_office', 'bus_station', 'language_school', 'training'}
OTHER_NRB_BUILDINGS = {
    'hotel', 'hostel', 'church', 'chapel', 'cathedral', 'mosque', 'synagogue',
    'temple', 'religious', 'police', 'fire_station', 'social_facility',
    'nursing_home', 'post_office', 'train_station', 'transportation', 'barn',
    'stable', 'cowshed', 'sty', 'farm_auxiliary', 'healthcare'}
NONRES_BUILDINGS = {
    'commercial', 'retail', 'office', 'industrial', 'warehouse', 'school',
    'kindergarten', 'university', 'hospital', 'public', 'civic', 'government',
    'sports_hall', 'stadium', 'theatre', 'cinema', 'museum', 'library',
    'supermarket', 'kiosk', 'restaurant', 'cafe', 'pub'} | (
        OTHER_NRB_BUILDINGS | HOSPITAL_BUILDINGS | CULTURE_BUILDINGS |
        SPORT_BUILDINGS | WORKSHOP_BUILDINGS | SCHOOL_BUILDINGS)
MODEL_CATEGORIES = [
    'OB', 'SC', 'RE', 'GS', 'UNI', 'HOSPITAL', 'CULTURE', 'SPORT', 'RETAIL',
    'WORKSHOP']
ANALYSIS_CATEGORIES = MODEL_CATEGORIES + ['OTHER_NRB']
CLASSIFICATION_PRIORITY = [
    'HOSPITAL', 'UNI', 'SC', 'GS', 'RE', 'SPORT', 'CULTURE', 'WORKSHOP',
    'RETAIL', 'OB', 'OTHER_NRB']

OSM_COLUMNS = sorted(set(POI_TAGS) | {
    'highway', 'service', 'building:levels', 'geometry'})
EXCLUDED_CLUSTERING_SERVICE_TYPES = {
    'driveway', 'parking_aisle', 'drive-through'}
SFH_LIKE_BUILDING_TAGS = {
    'house', 'detached', 'semidetached_house', 'terrace', 'bungalow', 'farm'}
MFH_LIKE_BUILDING_TAGS = {'apartments', 'dormitory'}
AMBIGUOUS_RESIDENTIAL_BUILDING_TAGS = {'residential'}
SFH_REQUIRED_TYPES = {'B', 'E'}
MFH_REQUIRED_TYPES = {'F', 'G', 'H'}
RESIDENTIAL_TYPOLOGY_DOMINANCE_THRESHOLD_PCT = 80.0
RESIDENTIAL_TYPOLOGY_SCORE_TOLERANCE_PP = 15.0
RESIDENTIAL_TYPOLOGY_MINIMUM_COVERAGE_PCT = 20.0
INFERRED_SFH_MAXIMUM_FOOTPRINT_AREA_M2 = 120.0
INFERRED_MFH_MINIMUM_FOOTPRINT_AREA_M2 = 220.0
MAXIMUM_ASSIGNED_RANGE_SCORE = 1.0
ATTACHED_TYPES = {'E', 'F', 'H', 'I'}
ATTACHED_BUILDING_THRESHOLD_PCT = 50.0
A_ATTACHED_BUILDING_THRESHOLD_PCT = 35.0
MINIMUM_BUILDING_FOOTPRINT_AREA_M2 = 20.0
BLOCK_FRONTAGE_TYPES = {'H', 'I'}
BLOCK_FRONTAGE_THRESHOLD_PCT = 50.0
MAXIMUM_BLOCK_FRONTAGE_GAP_PCT = 35.0
MAXIMUM_BLOCK_FRONTAGE_DISTANCE_M = 20.0
AB_FRONTAGE_CONTINUITY_THRESHOLD_PCT = 50.0
AB_FRONTAGE_MAXIMUM_GAP_M = 55.0
AB_FRONTAGE_MINIMUM_RUN_BUILDINGS = 3
COMPACT_HULL_SPACING_M = 20.0
SPARSE_HULL_SPACING_M = 55.0
ROW_ANGLE_STEP_DEG = 5
ROW_BAND_TOLERANCE_M = 5.0
ROW_MAXIMUM_ALONG_GAP_M = 55.0
ROW_MINIMUM_BUILDINGS = 4
ROW_MINIMUM_ROWS = 2
ROW_MINIMUM_OVERLAP_FRACTION = 0.50
ROW_STRUCTURE_THRESHOLD_PCT = 60.0
MORPHOLOGY_SPLIT_MINIMUM_ACCURACY = 0.70
MORPHOLOGY_SPLIT_MINIMUM_ROW_SHARE_DIFFERENCE = 0.40
BOUNDARY_BAY_RADIUS_SPACING_FACTOR = 1.25
REVIEW_NEARBY_BUILDING_DISTANCE_M = 30.0
QUICK_TEST_CENTER_LON_LAT = (6.0839, 50.7753)
QUICK_TEST_RADIUS_M = 7000.0
SETTLEMENT_CONTEXT_BUFFER_M = 500.0
RURAL_CONTEXT_MAXIMUM_DENSITY = 10.0
RURAL_CONTEXT_MAXIMUM_BCR = 0.10
URBAN_CONTEXT_COMBINED_MINIMUM_DENSITY = 15.0
URBAN_CONTEXT_COMBINED_MINIMUM_BCR = 0.15
URBAN_CONTEXT_MINIMUM_DENSITY = 20.0
URBAN_CONTEXT_MINIMUM_BCR = 0.20
CONTEXT_ALLOWED_TYPES = {
    'RURAL': set('ABCDEFG'),
    'URBAN': set('CDEFGHI'),
}


def _osm_tag(row, key):
    value = row.get(key, '')
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    if value is None:
        return ''
    return str(value).strip().lower()


def classify_osm_object(row):
    """Map one OSM object to one mutually exclusive NRB category."""
    amenity = _osm_tag(row, 'amenity')
    shop = _osm_tag(row, 'shop')
    office = _osm_tag(row, 'office')
    craft = _osm_tag(row, 'craft')
    building = _osm_tag(row, 'building')
    leisure = _osm_tag(row, 'leisure')
    tourism = _osm_tag(row, 'tourism')
    healthcare = _osm_tag(row, 'healthcare')
    industrial = _osm_tag(row, 'industrial')
    sport = _osm_tag(row, 'sport')

    office = office if office not in {'no', 'none', 'vacant'} else ''
    shop = shop if shop not in {'no', 'none', 'vacant'} else ''
    healthcare = healthcare if healthcare not in {'no', 'none'} else ''
    building_use = _osm_tag(row, 'building:use')
    if building_use:
        building = building_use

    if healthcare:
        if healthcare == 'pharmacy':
            return 'RETAIL'
        return 'HOSPITAL' if healthcare in HOSPITAL_HEALTHCARE else 'OTHER_NRB'
    if amenity == 'pharmacy':
        return 'RETAIL'
    if amenity in HOSPITAL_AMENITIES or building in HOSPITAL_BUILDINGS:
        return 'HOSPITAL'
    if amenity in {'university', 'college'} or building in UNIVERSITY_BUILDINGS:
        return 'UNI'
    if (amenity in {'school', 'kindergarten', 'childcare', 'music_school'}
            or building in {'school', 'kindergarten', 'college'}):
        return 'SC'
    if shop in GROCERY_SHOPS or building == 'supermarket':
        return 'GS'
    if amenity in FOOD_AMENITIES or building in {'restaurant', 'cafe', 'pub'}:
        return 'RE'
    if leisure in SPORT_LEISURE or sport or building in SPORT_BUILDINGS:
        return 'SPORT'
    if (amenity in CULTURE_AMENITIES or tourism in CULTURE_TOURISM
            or building in CULTURE_BUILDINGS):
        return 'CULTURE'
    if (craft or industrial or building in WORKSHOP_BUILDINGS
            or _osm_tag(row, 'man_made') == 'works'):
        return 'WORKSHOP'
    if shop or building in RETAIL_BUILDINGS:
        return 'RETAIL'
    if office or building in OFFICE_BUILDINGS or amenity in OFFICE_AMENITIES:
        return 'OB'
    if (building in NONRES_BUILDINGS or amenity in OTHER_NRB_AMENITIES
            or tourism in {'hotel', 'hostel', 'motel', 'guest_house'}
            or _osm_tag(row, 'railway') == 'station'
            or _osm_tag(row, 'public_transport') == 'station'):
        return 'OTHER_NRB'
    return None


def _is_polygonal(geometry):
    return geometry is not None and geometry.geom_type in {'Polygon', 'MultiPolygon'}


def classify_building_split(building_tag, final_category,
                            building_use_tag='', building_flats_tag=None):
    """Classify a footprint as residential, mixed, non-residential or unknown."""
    has_category = (
        isinstance(final_category, str) and final_category in ANALYSIS_CATEGORIES)
    try:
        has_flats = float(building_flats_tag) >= 1
    except (TypeError, ValueError):
        has_flats = False
    if has_flats:
        return 'mixed' if has_category else 'residential'
    if building_use_tag in RESIDENTIAL_BUILDINGS:
        return 'mixed' if has_category else 'residential'
    if building_use_tag in NONRES_BUILDINGS:
        return 'nonres'
    if building_tag in RESIDENTIAL_BUILDINGS:
        return 'mixed' if has_category else 'residential'
    if building_tag in NONRES_BUILDINGS or has_category:
        return 'nonres'
    return 'unknown'


def classify_nrb_buildings(features):
    """Return mutually exclusive NRB counts and main-use diagnostics."""
    counts = {category: 0 for category in ANALYSIS_CATEGORIES}
    diagnostics = {
        'classified_nrb_building_count': 0,
        'building_footprint_count': 0,
        'residential_building_split_count': 0,
        'mixed_building_split_count': 0,
        'nonres_building_split_count': 0,
        'unknown_building_split_count': 0,
        'building_footprints_with_direct_nrb_tag_count': 0,
        'building_footprints_classified_from_poi_count': 0,
        'classified_poi_count': 0,
        'classified_poi_without_building_count': 0,
    }
    if features is None or features.empty:
        return counts, diagnostics

    features = features.copy()
    features['model_category'] = features.apply(classify_osm_object, axis=1)
    building_mask = (
        features.get('building', pd.Series(index=features.index, dtype=object))
        .fillna('').astype(str).str.strip() != '')
    polygon_mask = features.geometry.apply(_is_polygonal)
    buildings = features[building_mask & polygon_mask].copy()
    diagnostics['building_footprint_count'] = int(len(buildings))
    if buildings.empty:
        poi_count = int(features['model_category'].notna().sum())
        diagnostics['classified_poi_count'] = poi_count
        diagnostics['classified_poi_without_building_count'] = poi_count
        return counts, diagnostics

    buildings = buildings.reset_index(drop=True)
    buildings['building_id'] = buildings.index
    buildings['final_category'] = buildings['model_category']
    diagnostics['building_footprints_with_direct_nrb_tag_count'] = int(
        buildings['final_category'].notna().sum())

    poi_features = features[features['model_category'].notna()].copy()
    diagnostics['classified_poi_count'] = int(len(poi_features))
    building_or_polygon_feature = building_mask & polygon_mask
    poi_features = poi_features.loc[
        ~building_or_polygon_feature.loc[poi_features.index]].copy()
    assigned_poi_indices = set()
    if not poi_features.empty:
        poi_points = poi_features.copy()
        poi_points.geometry = poi_points.geometry.representative_point()
        try:
            joined = gpd.sjoin(
                poi_points[['model_category', 'geometry']],
                buildings[['building_id', 'geometry']], how='left',
                predicate='within')
        except Exception:
            joined = gpd.sjoin(
                poi_points[['model_category', 'geometry']],
                buildings[['building_id', 'geometry']], how='left', op='within')
        joined = joined.dropna(subset=['building_id']).copy()
        assigned_poi_indices = set(joined.index)
        if not joined.empty:
            priority = {
                category: index
                for index, category in enumerate(CLASSIFICATION_PRIORITY)}
            joined['priority'] = joined['model_category'].map(priority)
            joined = joined.sort_values('priority')
            best = joined.groupby('building_id')['model_category'].first()
            for building_id, category in best.items():
                building_id = int(building_id)
                direct = buildings.at[building_id, 'final_category']
                if pd.isna(direct):
                    buildings.at[building_id, 'final_category'] = category
                elif priority.get(category, len(priority)) < priority.get(
                        direct, len(priority)):
                    buildings.at[building_id, 'final_category'] = category

    diagnostics['building_footprints_classified_from_poi_count'] = int(
        buildings['final_category'].notna().sum()
        - diagnostics['building_footprints_with_direct_nrb_tag_count'])
    diagnostics['classified_poi_without_building_count'] = int(
        len(poi_features) - len(assigned_poi_indices))
    classified = buildings.dropna(subset=['final_category'])
    for category in ANALYSIS_CATEGORIES:
        counts[category] = int((classified['final_category'] == category).sum())
    diagnostics['classified_nrb_building_count'] = int(len(classified))
    buildings['building_split'] = buildings.apply(
        lambda row: classify_building_split(
            _osm_tag(row, 'building'), row['final_category'],
            _osm_tag(row, 'building:use'), _osm_tag(row, 'building:flats')),
        axis=1)
    for split_name in ('residential', 'mixed', 'nonres', 'unknown'):
        diagnostics[f'{split_name}_building_split_count'] = int(
            (buildings['building_split'] == split_name).sum())
    return counts, diagnostics


def choose_analysis_scope(requested_scope):
    """Ask interactive runs whether to analyse a quick subset or all Aachen."""
    if requested_scope != 'ask':
        return requested_scope
    prompt = (
        '\nChoose the analysis extent:\n'
        '  1 - Quick test: 7 km around central Aachen (recommended)\n'
        '  2 - Full StädteRegion Aachen\n'
        'Selection [1]: ')
    while True:
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            print('No interactive input available; using the full region.',
                  flush=True)
            return 'full'
        if answer in {'', '1', 'q', 'quick', 'test'}:
            return 'quick'
        if answer in {'2', 'f', 'full', 'aachen'}:
            return 'full'
        print('Please enter 1 for the quick test or 2 for full Aachen.',
              flush=True)


def apply_analysis_scope(boundary, features, scope):
    """Clip inputs early for a fast central-Aachen development run."""
    if scope == 'full':
        return boundary, features, {
            'analysis_scope': 'full_staedteregion_aachen'}
    if scope != 'quick':
        raise ValueError(f'Unknown analysis scope: {scope}')

    longitude, latitude = QUICK_TEST_CENTER_LON_LAT
    centre = gpd.GeoSeries(
        [Point(longitude, latitude)], crs=4326).to_crs(25832).iloc[0]
    full_metric = boundary.to_crs(25832)
    quick_geometry = full_metric.geometry.union_all().intersection(
        centre.buffer(QUICK_TEST_RADIUS_M))
    if quick_geometry.is_empty:
        raise RuntimeError('Quick-test area does not intersect the study region.')
    quick_boundary_metric = gpd.GeoDataFrame(
        {'display_name': ['Central Aachen quick-test area']},
        geometry=[quick_geometry], crs=25832)
    quick_boundary = quick_boundary_metric.to_crs(boundary.crs)

    query_geometry = quick_boundary.to_crs(features.crs).geometry.union_all()
    indices = features.sindex.query(query_geometry, predicate='intersects')
    quick_features = features.iloc[np.unique(indices)].copy()
    return quick_boundary, quick_features, {
        'analysis_scope': 'quick_central_aachen',
        'quick_test_center_lon': longitude,
        'quick_test_center_lat': latitude,
        'quick_test_radius_m': QUICK_TEST_RADIUS_M,
        'quick_test_source_features': int(len(quick_features)),
    }


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_ranges(path):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = iter(book.worksheets[0].values)
    headers = next(rows)
    result = {}
    columns = {
        'bcr': ('Min Grund-flächenzahl', 'Max Grund-flächenzahl'),
        'density': ('Min Gebäude pro ha', 'Max Gebäude pro ha'),
        'far': ('Min Geschoss-flächenzahl', 'Max Geschoss-flächenzahl'),
        'building_spacing_median_m': (
            'Min Abstand benachbarter Hausanschlüsse  (m)',
            'Max Abstand benachbarter Hausanschlüsse  (m)'),
    }
    for raw in rows:
        if raw[0] not in tuple('ABCDEFGHI'):
            continue
        row = dict(zip(headers, raw))
        result[raw[0]] = {'name': row['Siedlungstyp'], 'bounds': {
            key: [float(row[low]), float(row[high])] for key, (low, high) in columns.items()}}
        target = float(row['MFH Anteil (%)'])
        if not 0 <= target <= 100:
            raise ValueError(f'Invalid MFH percentage for type {raw[0]}: {target}')
        result[raw[0]]['residential_mfh_target_pct'] = target
        result[raw[0]]['bounds']['mfh_share_known_pct'] = [
            max(0.0, target - RESIDENTIAL_TYPOLOGY_SCORE_TOLERANCE_PP),
            min(100.0, target + RESIDENTIAL_TYPOLOGY_SCORE_TOLERANCE_PP)]
    book.close()
    if len(result) != 9:
        raise ValueError('Expected nine source types A-I in workbook; do not infer a remapping.')
    for typ in result:
        if typ in ATTACHED_TYPES:
            result[typ]['bounds']['attached_building_pct'] = [
                ATTACHED_BUILDING_THRESHOLD_PCT, 100.0]
        elif typ == 'A':
            result[typ]['bounds']['attached_building_pct'] = [
                0.0, A_ATTACHED_BUILDING_THRESHOLD_PCT]
        else:
            result[typ]['bounds']['attached_building_pct'] = [
                0.0, ATTACHED_BUILDING_THRESHOLD_PCT]
        if typ in BLOCK_FRONTAGE_TYPES:
            result[typ]['requirements'] = {
                'block_frontage_structure_pct': [
                    BLOCK_FRONTAGE_THRESHOLD_PCT, 100.0]}
        result[typ]['bounds']['row_structure_pct'] = (
            [ROW_STRUCTURE_THRESHOLD_PCT, 100.0]
            if typ in {'E', 'F'}
            else [0.0, ROW_STRUCTURE_THRESHOLD_PCT])
    result['A']['exclusive_upper_requirements'] = {
        'row_structure_pct': ROW_STRUCTURE_THRESHOLD_PCT}
    result['A'].setdefault('requirements', {})[
        'continuous_road_frontage_pct'] = [
            0.0, AB_FRONTAGE_CONTINUITY_THRESHOLD_PCT]
    result['B'].setdefault('requirements', {})[
        'continuous_road_frontage_pct'] = [
            AB_FRONTAGE_CONTINUITY_THRESHOLD_PCT, 100.0]
    return result


def download(out, refresh=False):
    import osmnx as ox
    out.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = out / 'http_cache'
    ox.settings.use_cache = not refresh
    ox.settings.requests_timeout = 240
    ox.settings.log_console = True
    boundary_file = out / 'boundary.geojson'
    if boundary_file.exists():
        boundary = gpd.read_file(boundary_file)
    else:
        boundary = ox.geocode_to_gdf('Städteregion Aachen, Nordrhein-Westfalen, Deutschland')
        boundary.to_file(boundary_file, driver='GeoJSON')
    print('Boundary:', boundary.get('display_name', pd.Series(['cached'])).iloc[0], flush=True)
    cache = out / 'osm_features_slim.pkl'
    if refresh or not cache.exists():
        tags = dict(POI_TAGS)
        tags['highway'] = True
        features = ox.features_from_polygon(boundary.geometry.union_all(), tags)
        features = features[[column for column in OSM_COLUMNS if column in features.columns]].copy()
        for column in OSM_COLUMNS:
            if column not in features.columns and column != 'geometry':
                features[column] = None
        # Prepare the replacement before touching the currently usable cache.
        if features.empty or 'building' not in features.columns:
            raise RuntimeError('Downloaded OSM data contain no usable building data.')
        pending = out / 'osm_features_slim.pending.pkl'
        features.to_pickle(pending)
        metadata = {
            'retrieved_utc': datetime.now(timezone.utc).isoformat(),
            'boundary': 'Städteregion Aachen', 'source': 'OpenStreetMap via OSMnx/Overpass',
            'osm_attribution': '© OpenStreetMap contributors, ODbL',
            'pandas_version': pd.__version__,
            'numpy_version': np.__version__,
            'tags': tags, 'features': len(features),
            'retained_columns': list(features.columns),
            'nonempty_tag_counts': {
                column: int(features[column].notna().sum())
                for column in OSM_COLUMNS if column != 'geometry'},
        }
        if cache.exists():
            backup = out / 'cache_backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup.mkdir(parents=True)
            for name in ('osm_features_slim.pkl', 'download.json', 'boundary.geojson'):
                if (out / name).exists():
                    shutil.copy2(out / name, backup / name)
            print(f'Previous source data backed up to {backup}', flush=True)
        pending.replace(cache)
        (out / 'download.json').write_text(
            json.dumps(metadata, indent=2), encoding='utf-8')
    return boundary, pd.read_pickle(cache)


def extract(features, boundary):
    features = features.to_crs(25832)
    boundary = boundary.to_crs(25832).geometry.union_all()
    features.geometry = features.geometry.make_valid()
    polygonal = features.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])
    landuse = features.get(
        'landuse', pd.Series('', index=features.index)).fillna('').astype(str)
    industrial_sites = features[
        polygonal & landuse.str.lower().eq('industrial')].copy()
    industrial_sites.geometry = industrial_sites.geometry.intersection(boundary)
    industrial_sites = industrial_sites[
        ~industrial_sites.geometry.is_empty].copy()
    industrial_sites['osm_key'] = [
        f'{a}/{b}' for a, b in industrial_sites.index]
    industrial_sites['excluded_area_ha'] = (
        industrial_sites.geometry.area / 10000)
    industrial_mask = _normalize_polygonal(
        industrial_sites.geometry.union_all()) if len(industrial_sites) \
        else shapely.Polygon()
    analysis_boundary = _normalize_polygonal(
        boundary.difference(industrial_mask))

    building_tags = features.get('building', pd.Series('', index=features.index)).fillna('').astype(str)
    excluded = {'garage', 'garages', 'shed', 'roof', 'carport', 'greenhouse', 'construction', 'ruins', 'no'}
    buildings = features[polygonal & (building_tags != '') & ~building_tags.isin(excluded)].copy()
    # Retain generic building=yes; missing use must not exclude a district.
    buildings = buildings[buildings.geometry.representative_point().within(boundary)].copy()
    buildings['osm_key'] = [f'{a}/{b}' for a, b in buildings.index]
    buildings = buildings.drop_duplicates(subset='geometry').reset_index(drop=True)
    # Remove member-way duplicates covered by a larger polygon representation.
    tree = shapely.STRtree(buildings.geometry.to_numpy())
    drop = set()
    for i, geometry in enumerate(buildings.geometry):
        for j in tree.query(geometry, predicate='intersects'):
            if i == j or buildings.geometry.iloc[j].area <= geometry.area * 1.01:
                continue
            if geometry.intersection(buildings.geometry.iloc[j]).area / geometry.area > .98:
                drop.add(i)
                break
    buildings = buildings.drop(index=list(drop)).reset_index(drop=True)
    eligible_before_footprint_filter = len(buildings)
    buildings = buildings[
        buildings.geometry.area >= MINIMUM_BUILDING_FOOTPRINT_AREA_M2
    ].copy().reset_index(drop=True)
    small_footprint_excluded_buildings = (
        eligible_before_footprint_filter - len(buildings))
    eligible_before_industrial_exclusion = len(buildings)
    if not industrial_mask.is_empty:
        buildings = buildings[
            ~buildings.geometry.intersects(industrial_mask)].copy()
    buildings = buildings.reset_index(drop=True)
    excluded_industrial_buildings = (
        eligible_before_industrial_exclusion - len(buildings))
    highway = features.get('highway', pd.Series('', index=features.index)).fillna('')
    road_types = {'primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'living_street', 'service', 'pedestrian'}
    roads = features[highway.isin(road_types) & features.geometry.geom_type.isin(['LineString','MultiLineString'])].copy()
    roads.geometry = roads.geometry.intersection(analysis_boundary)
    roads = roads[
        ~roads.geometry.is_empty &
        roads.geometry.geom_type.isin(['LineString', 'MultiLineString'])
    ].drop_duplicates(subset='geometry')
    exclusion_summary = {
        'industrial_site_polygons': int(len(industrial_sites)),
        'industrial_exclusion_area_ha': float(industrial_mask.area / 10000),
        'industrial_excluded_buildings': int(excluded_industrial_buildings),
        'minimum_building_footprint_area_m2':
            MINIMUM_BUILDING_FOOTPRINT_AREA_M2,
        'small_footprint_excluded_buildings': int(
            small_footprint_excluded_buildings),
        'eligible_buildings_before_footprint_filter': int(
            eligible_before_footprint_filter),
        'eligible_buildings_before_industrial_exclusion': int(
            eligible_before_industrial_exclusion),
    }
    return (features, analysis_boundary, buildings, roads,
            industrial_sites, exclusion_summary)


def _prune_small_remote_building_groups(ids, points, minimum,
                                        maximum_remote_buildings=4):
    """Remove a small spatially disconnected tail from a block candidate."""
    ids = set(map(int, ids))
    if len(ids) <= minimum:
        return ids

    ordered = sorted(ids)
    nearest_distances = []
    for index in ordered:
        nearest_distances.append(min(
            points[index].distance(points[other])
            for other in ordered if other != index))
    gap_threshold = _exceptional_gap_threshold(nearest_distances)
    if gap_threshold is None:
        return ids

    # At most 70 buildings enter this operation, so the explicit pairwise graph
    # is both transparent and inexpensive. Buildings belong to the same spatial
    # component when they can be linked through point-to-point gaps that do not
    # exceed the candidate-specific exceptional-gap threshold.
    adjacency = {index: set() for index in ordered}
    for position, left in enumerate(ordered):
        for right in ordered[position + 1:]:
            if points[left].distance(points[right]) <= gap_threshold:
                adjacency[left].add(right)
                adjacency[right].add(left)

    components = []
    unseen = set(ordered)
    while unseen:
        start = min(unseen)
        component, frontier = set(), {start}
        while frontier:
            current = frontier.pop()
            if current not in unseen:
                continue
            unseen.remove(current)
            component.add(current)
            frontier.update(adjacency[current] & unseen)
        components.append(component)

    if len(components) == 1:
        return ids
    core = max(components, key=lambda component: (len(component), -min(component)))
    remote = ids - core
    if len(core) < minimum or len(remote) > maximum_remote_buildings:
        return ids
    return core


def block_candidates(buildings, roads, boundary, target, seed,
                     minimum=10, maximum=70, maximum_block_area=4e6):
    """Generate candidates from complete connected road blocks."""
    points = buildings.geometry.representative_point().to_numpy()
    point_tree = shapely.STRtree(points)
    footprint_tree = shapely.STRtree(buildings.geometry.to_numpy())
    blocks = list(polygonize(unary_union(list(roads.geometry) + [boundary.boundary])))
    blocks = [b for b in blocks if boundary.covers(b.representative_point())]
    block_tree = shapely.STRtree(blocks)
    members = [set(map(int, point_tree.query(b, predicate='contains'))) for b in blocks]
    order = list(range(len(blocks)))
    rng = random.Random(seed)
    rng.shuffle(order)
    used_buildings, used_blocks, results = set(), set(), []
    registry = _SpatialRegistry()
    for start in order:
        if (start in used_blocks or not members[start]
                or members[start] & used_buildings
                or blocks[start].area > maximum_block_area):
            continue
        # An individual closed road block is already a natural morphological
        # unit. Blocks above the upper limit remain available to the later
        # street-component stage, where they can be divided at internal spatial
        # breaks instead of being cut arbitrarily here.
        if len(members[start]) > maximum:
            continue
        group, ids, geom = {start}, set(members[start]), blocks[start]
        # Merge blocks only when the natural starting block is too small.
        # The target of 40 ranks otherwise admissible merges but does not cause
        # an already acceptable complete block to absorb its neighbour.
        while len(ids) < minimum:
            adjacent = set(map(int, block_tree.query(geom, predicate='intersects'))) - group - used_blocks
            options = [j for j in adjacent
                       if members[j]
                       and not members[j] & used_buildings
                       and len(ids | members[j]) <= maximum
                       and geom.union(blocks[j]).area <= maximum_block_area
                       and geom.boundary.intersection(blocks[j].boundary).length > 1]
            if not options:
                break
            j = min(options, key=lambda k: (abs(target-len(ids | members[k])), blocks[k].area, k))
            group.add(j)
            ids |= members[j]
            geom = geom.union(blocks[j])
        ids = _prune_small_remote_building_groups(
            ids, points, minimum,
            maximum_remote_buildings=max(1, math.ceil(target / 10)))
        if not minimum <= len(ids) <= maximum or ids & used_buildings:
            continue
        built = _building_envelope(ids, buildings, points, point_tree,
                                   footprint_tree, used_buildings, boundary,
                                   minimum, maximum)
        if not built:
            continue
        accepted_component = False
        for envelope, closed_ids, _ in built:
            if registry.intersects(envelope):
                continue
            results.append((envelope, closed_ids, 'road_block_cluster'))
            registry.add(envelope)
            used_buildings.update(closed_ids)
            accepted_component = True
        if accepted_component:
            used_blocks.update(group)
    print(f'{len(results)} accepted road-block clusters', flush=True)
    return results


class _SpatialRegistry:
    """Small grid index used to prevent accepted candidate envelopes overlapping."""

    def __init__(self, cell_size=500.0):
        self.cell_size = float(cell_size)
        self.geometries = []
        self.cells = defaultdict(set)

    def _keys(self, geometry):
        xmin, ymin, xmax, ymax = geometry.bounds
        for x in range(math.floor(xmin / self.cell_size), math.floor(xmax / self.cell_size) + 1):
            for y in range(math.floor(ymin / self.cell_size), math.floor(ymax / self.cell_size) + 1):
                yield x, y

    def intersects(self, geometry):
        indices = set()
        for key in self._keys(geometry):
            indices.update(self.cells.get(key, ()))
        return any(geometry.intersects(self.geometries[index]) for index in indices)

    def add(self, geometry):
        index = len(self.geometries)
        self.geometries.append(geometry)
        for key in self._keys(geometry):
            self.cells[key].add(index)


def _clustering_road_mask(roads):
    """Select ordinary roads and meaningful service roads for clustering."""
    highway = roads.get(
        'highway', pd.Series('', index=roads.index)).fillna('').astype(str)
    ordinary = ~highway.isin(['service', 'pedestrian'])
    if 'service' not in roads:
        # A legacy slim cache does not retain the OSM service subtype. It is
        # unsafe to interpret every cached service road as shared access.
        return ordinary
    service_type = roads['service'].fillna('').astype(str).str.lower()
    shared_service = (
        highway.eq('service') &
        ~service_type.isin(EXCLUDED_CLUSTERING_SERVICE_TYPES))
    return ordinary | shared_service


def _noded_grouping_roads(roads):
    """Return clustering roads split only at geometric intersections."""
    grouping_roads = roads.loc[_clustering_road_mask(roads)].copy()
    noded = unary_union(list(grouping_roads.geometry))
    return [line for line in shapely.get_parts(noded)
            if line.geom_type == 'LineString' and line.length > 0.1]


def _exceptional_gap_threshold(values, minimum_observations=5):
    """Return an adaptive upper-outlier threshold, or None for small samples."""
    values = np.asarray([
        float(value) for value in values
        if value is not None and np.isfinite(value) and value >= 0], dtype=float)
    if len(values) < minimum_observations:
        return None
    q1, q3 = np.quantile(values, [0.25, 0.75])
    iqr = float(q3 - q1)
    if iqr <= 1e-9:
        # Identical or nearly identical observations provide no useful IQR.
        # Require a threefold increase over the typical gap in this case.
        return float(3 * np.median(values))
    return float(q3 + 3 * iqr)


def _building_defined_street_sections(roads, points, maximum_road_distance=150.0,
                                      position_precision=1,
                                      maximum_buildings_per_section=4):
    """Split noded roads halfway between projected building positions.

    Each building is first associated with its nearest noded road. Buildings
    whose projected positions coincide at the chosen numerical precision form
    one two-sided street station. Consecutive stations are grouped without
    exceeding ``maximum_buildings_per_section`` where possible, and section
    boundaries are placed midway between groups. Consequently, dense
    development creates short clustering units and sparse development creates
    long units without a fixed maximum road-edge length. Road continuity is
    interrupted at statistically exceptional gaps between consecutive building
    stations, using Q3 + 3 IQR when at least five gaps are available.
    """
    noded_roads = _noded_grouping_roads(roads)
    if not noded_roads:
        return [], []
    road_tree = shapely.STRtree(noded_roads)
    nearest_roads = np.asarray(road_tree.nearest(points), dtype=int)
    road_memberships = [list() for _ in noded_roads]
    for building_index, road_index in enumerate(nearest_roads):
        road_index = int(road_index)
        if points[building_index].distance(noded_roads[road_index]) <= maximum_road_distance:
            road_memberships[road_index].append(building_index)

    sections, memberships = [], []
    for line, building_ids in zip(noded_roads, road_memberships):
        if not building_ids:
            sections.append(line)
            memberships.append(set())
            continue

        stations = defaultdict(set)
        for building_index in building_ids:
            position = round(float(line.project(points[building_index])), position_precision)
            stations[position].add(int(building_index))
        ordered = sorted(stations.items())
        station_gaps = np.diff([position for position, _ in ordered])
        gap_threshold = _exceptional_gap_threshold(station_gaps)
        groups = []
        current_positions, current_members = [], set()
        current_break_before = False
        for station_index, (position, station_members) in enumerate(ordered):
            exceptional_break = (
                station_index > 0 and gap_threshold is not None and
                position - ordered[station_index - 1][0] > gap_threshold)
            if (current_members and
                    (exceptional_break or
                     len(current_members | station_members) >
                     maximum_buildings_per_section)):
                groups.append((current_positions, current_members,
                               current_break_before))
                current_positions, current_members = [], set()
                current_break_before = exceptional_break
            current_positions.append(position)
            current_members.update(station_members)
        if current_members:
            groups.append((current_positions, current_members,
                           current_break_before))

        starts = [0.0] * len(groups)
        ends = [float(line.length)] * len(groups)
        for group_index, (left, right) in enumerate(
                zip(groups[:-1], groups[1:])):
            left_positions = left[0]
            right_positions, _, right_break_before = right
            if right_break_before:
                # Leave the exceptional empty road interval out of the
                # clustering graph so growth cannot bridge it.
                ends[group_index] = left_positions[-1]
                starts[group_index + 1] = right_positions[0]
            else:
                midpoint = (left_positions[-1] + right_positions[0]) / 2
                ends[group_index] = midpoint
                starts[group_index + 1] = midpoint

        first_section_index = len(sections)
        pending_members = set()
        for group_index, (_, group_members, _) in enumerate(groups):
            start = min(max(starts[group_index], 0.0), float(line.length))
            end = min(max(ends[group_index], 0.0), float(line.length))
            if end - start <= 0.1:
                # Numerical edge case at a road endpoint: retain the membership
                # in the nearest non-degenerate neighbouring section.
                if len(sections) > first_section_index:
                    memberships[-1].update(group_members)
                else:
                    pending_members.update(group_members)
                continue
            section = substring(line, start, end)
            if section.geom_type == 'LineString' and section.length > 0.1:
                sections.append(section)
                memberships.append(set(group_members) | pending_members)
                pending_members = set()
        if pending_members:
            if len(sections) > first_section_index:
                memberships[-1].update(pending_members)
            else:
                sections.append(line)
                memberships.append(set(building_ids))
    return sections, memberships


def _segment_adjacency(segments, precision=1):
    nodes = defaultdict(list)
    for index, line in enumerate(segments):
        start, end = line.coords[0], line.coords[-1]
        nodes[(round(start[0], precision), round(start[1], precision))].append(index)
        nodes[(round(end[0], precision), round(end[1], precision))].append(index)
    adjacency = [set() for _ in segments]
    for indices in nodes.values():
        for index in indices:
            adjacency[index].update(other for other in indices if other != index)
    return adjacency


def _prune_exceptional_terminal_branches(group, memberships, adjacency, points,
                                          used_buildings, minimum,
                                          maximum_branch_buildings=4):
    """Remove small terminal branches separated from the core by an outlier gap."""
    group = set(group)
    used_buildings = set(used_buildings)
    while True:
        ids = set().union(*(memberships[index] for index in group)) - used_buildings
        if len(ids) <= minimum:
            break
        coordinates = np.asarray([
            [points[index].x, points[index].y] for index in sorted(ids)])
        differences = coordinates[:, None, :] - coordinates[None, :, :]
        distances = np.sqrt(np.sum(differences * differences, axis=2))
        np.fill_diagonal(distances, np.inf)
        nearest_distances = distances.min(axis=1)
        gap_threshold = _exceptional_gap_threshold(nearest_distances)
        if gap_threshold is None:
            break

        removable = []
        for segment_index in group:
            degree = len(adjacency[segment_index] & group)
            if degree > 1:
                continue
            branch_ids = (memberships[segment_index] - used_buildings) & ids
            core_ids = ids - branch_ids
            if (not branch_ids or
                    len(branch_ids) > maximum_branch_buildings or
                    len(core_ids) < minimum):
                continue
            branch_points = [points[index] for index in branch_ids]
            core_points = [points[index] for index in core_ids]
            connection_gap = min(
                branch_point.distance(core_point)
                for branch_point in branch_points for core_point in core_points)
            if connection_gap > gap_threshold:
                removable.append((connection_gap, segment_index))
        if not removable:
            break
        _, selected = max(removable)
        group.remove(selected)

    ids = set().union(*(memberships[index] for index in group)) - used_buildings
    return group, ids


def _fill_empty_enclosed_areas(envelope, footprint_tree, member_ids):
    """Fill polygon holes unless they contain another eligible footprint."""
    member_ids = set(map(int, member_ids))
    polygons = []
    for part in shapely.get_parts(envelope):
        if part.geom_type != 'Polygon':
            continue
        retained_holes = []
        for ring in part.interiors:
            hole = shapely.Polygon(ring)
            intersecting = map(int, footprint_tree.query(hole, predicate='intersects'))
            if any(index not in member_ids for index in intersecting):
                retained_holes.append(ring.coords)
        polygons.append(shapely.Polygon(part.exterior.coords, holes=retained_holes))
    return unary_union(polygons) if polygons else envelope


def _normalize_polygonal(geometry):
    """Return a valid polygonal geometry, discarding non-area remnants."""
    polygons = []

    def collect(item):
        if item.geom_type == 'Polygon' and not item.is_empty:
            polygons.append(item)
        elif item.geom_type in {'MultiPolygon', 'GeometryCollection'}:
            for part in shapely.get_parts(item):
                collect(part)

    collect(shapely.make_valid(geometry))
    return unary_union(polygons) if polygons else shapely.Polygon()


def _close_empty_boundary_bays(envelope, radius, footprint_tree, member_ids,
                               boundary, blocked_ids=None,
                               maximum_new_buildings=None):
    """Fill open bays and return unassigned buildings absorbed from them."""
    if envelope.is_empty or radius <= 0:
        return envelope, set()
    member_ids = set(map(int, member_ids))
    blocked_ids = set(map(int, blocked_ids or ()))
    envelope = _normalize_polygonal(envelope)

    # A morphological closing fills boundary indentations narrower than roughly
    # twice the radius. Reusing the candidate's adaptive margin avoids adding a
    # separate universal distance threshold.
    closed = _normalize_polygonal(
        envelope.buffer(radius, join_style='mitre').buffer(
            -radius, join_style='mitre'))
    additions = _normalize_polygonal(
        closed.difference(envelope).intersection(boundary))
    accepted = []
    absorbed = set()
    for component in shapely.get_parts(additions):
        if component.geom_type != 'Polygon' or component.is_empty:
            continue
        intersecting = set(map(
            int, footprint_tree.query(component, predicate='intersects')))
        external = intersecting - member_ids
        if external & blocked_ids:
            continue
        proposed = absorbed | external
        if (maximum_new_buildings is not None and
                len(proposed) > maximum_new_buildings):
            continue
        accepted.append(component)
        absorbed = proposed
    if not accepted:
        return envelope, set()
    return (_normalize_polygonal(
        envelope.union(unary_union(accepted)).intersection(boundary)),
        absorbed)


def _nearest_point_distances(selected_points):
    """Return the nearest-neighbour distance for every selected point."""
    selected_points = list(selected_points)
    if len(selected_points) < 2:
        return []
    tree = shapely.STRtree(selected_points)
    distances = []
    for point in selected_points:
        nearest = tree.query_nearest(
            point, exclusive=True, all_matches=False)
        if len(nearest):
            distances.append(float(point.distance(
                selected_points[int(nearest[0])])))
    return distances


def _adaptive_hull_ratio(selected_points, base_ratio=.30,
                         compact_spacing=COMPACT_HULL_SPACING_M,
                         sparse_spacing=SPARSE_HULL_SPACING_M):
    """Use a progressively less concave envelope for spatially sparse groups."""
    distances = _nearest_point_distances(selected_points)
    if not distances:
        return float(base_ratio)
    median_distance = float(np.median(distances))
    fraction = np.clip(
        (median_distance - compact_spacing) /
        (sparse_spacing - compact_spacing), 0.0, 1.0)
    return float(base_ratio + (1.0 - base_ratio) * fraction)


def _spatial_coherence_components(ids, points):
    """Split a candidate at exceptional bridges in its building-point MST."""
    ids = set(map(int, ids))
    if len(ids) < 2:
        return [ids]

    # Prim's algorithm is explicit and inexpensive for the maximum candidate
    # size of 70 buildings. The MST retains the shortest connections required
    # to join all buildings, so one long edge exposes an otherwise hidden empty
    # spatial bridge between compact groups.
    connected = {min(ids)}
    remaining = ids - connected
    mst_edges = []
    while remaining:
        distance, left, right = min(
            (float(points[left].distance(points[right])), left, right)
            for left in connected for right in remaining)
        mst_edges.append((distance, left, right))
        connected.add(right)
        remaining.remove(right)

    threshold = _exceptional_gap_threshold(
        [distance for distance, _, _ in mst_edges])
    if threshold is None or not any(
            distance > threshold for distance, _, _ in mst_edges):
        return [ids]

    adjacency = {index: set() for index in ids}
    for distance, left, right in mst_edges:
        if distance <= threshold:
            adjacency[left].add(right)
            adjacency[right].add(left)

    components = []
    unseen = set(ids)
    while unseen:
        start = min(unseen)
        component, frontier = set(), {start}
        while frontier:
            current = frontier.pop()
            if current not in unseen:
                continue
            unseen.remove(current)
            component.add(current)
            frontier.update(adjacency[current] & unseen)
        components.append(component)
    return sorted(components, key=lambda component: (-len(component), min(component)))


def _building_envelope(ids, buildings, points, point_tree, footprint_tree,
                       used_buildings, boundary,
                       minimum, maximum, concave_ratio=.30,
                       minimum_margin=5.0, maximum_margin=30.0,
                       excluded_buildings=None):
    """Close membership, split incoherent groups and create final envelopes."""
    ids = set(map(int, ids))
    excluded_buildings = set(map(int, excluded_buildings or ()))
    for _ in range(10):
        if not minimum <= len(ids) <= maximum or ids & used_buildings:
            return []
        footprints = buildings.geometry.iloc[sorted(ids)].to_numpy()
        gaps = []
        if len(footprints) > 1:
            local_tree = shapely.STRtree(footprints)
            for index, footprint in enumerate(footprints):
                nearest = [int(other) for other in local_tree.query_nearest(
                    footprint, exclusive=True, all_matches=False)]
                if nearest:
                    gaps.append(footprint.distance(footprints[nearest[0]]))
        median_gap = float(np.median(gaps)) if gaps else minimum_margin * 2
        margin = float(np.clip(median_gap / 2, minimum_margin, maximum_margin))

        # The preliminary envelope is deliberately generated from one interior
        # representative point per building. It determines membership without
        # allowing a large footprint to pull the preliminary boundary outwards.
        selected_points = [points[index] for index in sorted(ids)]
        hull_ratio = _adaptive_hull_ratio(
            selected_points, base_ratio=concave_ratio)
        point_base = shapely.concave_hull(
            unary_union(selected_points), ratio=hull_ratio, allow_holes=False)
        preliminary = point_base.buffer(margin, join_style='mitre').intersection(boundary)
        if preliminary.is_empty:
            return []
        enclosed = (set(map(int, point_tree.query(
            preliminary, predicate='contains'))) - excluded_buildings)
        updated = ids | enclosed
        if updated == ids:
            components = _spatial_coherence_components(ids, points)
            if len(components) > 1:
                # Only coherent components satisfying the common minimum are
                # allowed to proceed. Small fragments are discarded; when all
                # components are too small, the complete candidate is rejected.
                valid_components = [
                    component for component in components
                    if minimum <= len(component) <= maximum]
                rebuilt = []
                for component in valid_components:
                    rebuilt.extend(_building_envelope(
                        component, buildings, points, point_tree,
                        footprint_tree, used_buildings, boundary,
                        minimum, maximum, concave_ratio,
                        minimum_margin, maximum_margin,
                        excluded_buildings | (ids - component)))
                return rebuilt
            # Once membership is stable, reconstruct the physical envelope from
            # the complete member footprints and the same adaptive margin.
            selected_union = unary_union(list(footprints))
            footprint_base = shapely.concave_hull(
                selected_union, ratio=hull_ratio, allow_holes=False)
            envelope = footprint_base.buffer(
                margin, join_style='mitre').intersection(boundary)

            # Prevent the margin from covering another eligible footprint. For
            # each nearby non-member building, the exclusion zone extends by
            # half its clear distance to the selected footprints. The resulting
            # local boundary therefore lies approximately midway between them.
            nearby = footprint_tree.query(
                envelope.buffer(maximum_margin), predicate='intersects')
            exclusion_zones = []
            for external_index in map(int, nearby):
                if external_index in ids:
                    continue
                external = buildings.geometry.iloc[external_index]
                clear_gap = float(selected_union.distance(external))
                exclusion = external.buffer(clear_gap / 2, join_style='mitre')
                if envelope.intersects(exclusion):
                    exclusion_zones.append(exclusion)
            if exclusion_zones:
                envelope = envelope.difference(
                    unary_union(exclusion_zones)).intersection(boundary)
                # Numerical overlay operations must never remove a selected
                # building footprint from its own candidate.
                envelope = envelope.union(selected_union).intersection(boundary)
            # A fully enclosed area belongs to the district when it is empty.
            # Holes containing an unassigned eligible footprint are retained so
            # that the envelope still respects the external-building constraint.
            envelope = _fill_empty_enclosed_areas(
                envelope, footprint_tree, ids).intersection(boundary)
            # Also close narrow three-sided boundary bays. If a bay contains
            # an as-yet-unassigned eligible building, absorb that building and
            # rebuild the complete boundary; never close a bay across a
            # building that is already assigned or deliberately excluded.
            nearest_point_distances = _nearest_point_distances(selected_points)
            bay_radius = margin
            if nearest_point_distances:
                bay_radius = float(np.clip(
                    BOUNDARY_BAY_RADIUS_SPACING_FACTOR *
                    np.median(nearest_point_distances),
                    margin, maximum_margin))
            envelope, absorbed_bay_ids = _close_empty_boundary_bays(
                envelope, bay_radius, footprint_tree, ids, boundary,
                blocked_ids=used_buildings | excluded_buildings,
                maximum_new_buildings=maximum - len(ids))
            if absorbed_bay_ids:
                ids |= absorbed_bay_ids
                continue
            # Overlay, hole filling and closing can leave self-touching rings.
            # Normalize the result and retain only polygonal components.
            envelope = _normalize_polygonal(envelope)
            if envelope.is_empty:
                return []
            return [(envelope, sorted(ids), margin)]
        ids = updated
    return []


def _street_growth_priority(segment, additions, current_count, target):
    """Rank alternatives when a large natural component must be divided."""
    additions = set(additions)
    return (
        float(segment.length) / len(additions),
        abs(target - (current_count + len(additions))),
        -len(additions),
    )


def _connected_segment_components(indices, adjacency):
    """Return connected components of the selected street-section indices."""
    unseen = set(indices)
    components = []
    while unseen:
        start = min(unseen)
        component, frontier = set(), {start}
        while frontier:
            current = frontier.pop()
            if current not in unseen:
                continue
            unseen.remove(current)
            component.add(current)
            frontier.update(adjacency[current] & unseen)
        components.append(component)
    return components


def _partition_natural_street_component(component, memberships, adjacency,
                                        segments, used_buildings, minimum,
                                        maximum, target, seed_order):
    """Retain a natural component or divide an oversized one near natural gaps."""
    used_buildings = set(used_buildings)
    order_rank = {segment: rank for rank, segment in enumerate(seed_order)}

    def building_ids(group):
        return (set().union(*(memberships[index] for index in group))
                - used_buildings)

    def divide(group):
        ids = building_ids(group)
        if len(ids) < minimum:
            return []
        if len(ids) <= maximum:
            return [(set(group), ids)]

        # Only oversized natural components are divided. The randomized seed
        # provides a reproducible starting point; growth then prefers the least
        # added road length per new building. Reaching the target is a preferred
        # split size, not a stopping rule for components that already fit.
        start = min(group, key=lambda index: (
            order_rank.get(index, math.inf), index))
        selected = {start}
        selected_ids = memberships[start] - used_buildings
        while len(selected_ids) < target:
            frontier = (set().union(*(adjacency[index] for index in selected))
                        & group) - selected
            options = []
            for candidate in frontier:
                additions = memberships[candidate] - used_buildings - selected_ids
                if not additions or len(selected_ids | additions) > maximum:
                    continue
                options.append((
                    *_street_growth_priority(
                        segments[candidate], additions,
                        len(selected_ids), target),
                    order_rank.get(candidate, math.inf), candidate, additions))
            if not options:
                break
            *_, chosen, additions = min(options)
            selected.add(chosen)
            selected_ids |= additions

        if len(selected_ids) < minimum:
            return []

        partitions = [(selected, selected_ids)]
        remaining = set(group) - selected
        for remainder in _connected_segment_components(remaining, adjacency):
            partitions.extend(divide(remainder))
        return partitions

    return divide(set(component))


def street_candidates(buildings, roads, boundary, target, seed,
                      minimum=10, maximum=70, maximum_road_distance=150.0,
                      initial_used_buildings=None, initial_envelopes=None):
    """Generate candidates from natural two-sided street components."""
    if not minimum <= target <= maximum:
        raise ValueError('Expected minimum <= target <= maximum.')
    points = buildings.geometry.representative_point().to_numpy()
    point_tree = shapely.STRtree(points)
    footprint_tree = shapely.STRtree(buildings.geometry.to_numpy())
    segments, memberships = _building_defined_street_sections(
        roads, points, maximum_road_distance=maximum_road_distance,
        maximum_buildings_per_section=max(1, math.ceil(target / 10)))
    if not segments:
        raise RuntimeError('No usable road segments for street clustering.')
    adjacency = _segment_adjacency(segments)
    rng = random.Random(seed)
    order = [index for index, member_ids in enumerate(memberships) if member_ids]
    rng.shuffle(order)
    used_buildings = set(map(int, initial_used_buildings or ()))
    available_segments = {
        index for index in order
        if memberships[index] - used_buildings}
    natural_components = _connected_segment_components(
        available_segments, adjacency)
    component_order = list(range(len(natural_components)))
    rng.shuffle(component_order)
    partitions = []
    for component_index in component_order:
        partitions.extend(_partition_natural_street_component(
            natural_components[component_index], memberships, adjacency,
            segments, used_buildings, minimum, maximum, target, order))

    results = []
    registry = _SpatialRegistry()
    for envelope in initial_envelopes or ():
        registry.add(envelope)
    print(f'{len(segments)} building-defined street sections; '
          f'{len(order)} occupied sections; '
          f'{len(natural_components)} natural components', flush=True)

    for group, ids in partitions:
        ids = ids - used_buildings
        group, ids = _prune_exceptional_terminal_branches(
            group, memberships, adjacency, points, used_buildings, minimum,
            maximum_branch_buildings=max(1, math.ceil(target / 10)))
        if len(ids) < minimum:
            continue
        built = _building_envelope(ids, buildings, points, point_tree,
                                   footprint_tree, used_buildings, boundary,
                                   minimum, maximum)
        if not built:
            continue
        for envelope, closed_ids, _ in built:
            if registry.intersects(envelope):
                continue
            results.append((envelope, closed_ids,
                            'two_sided_street_cluster'))
            registry.add(envelope)
            used_buildings.update(closed_ids)

    print(f'{len(results)} accepted two-sided street clusters', flush=True)
    return results


def hybrid_candidates(buildings, roads, boundary, target, seed,
                      minimum=10, maximum=70, maximum_road_distance=150.0):
    """Use complete road blocks first and street growth for remaining buildings."""
    block_results = block_candidates(
        buildings, roads, boundary, target, seed,
        minimum=minimum, maximum=maximum)
    block_buildings = {index for _, members, _ in block_results for index in members}
    block_envelopes = [geometry for geometry, _, _ in block_results]
    street_results = street_candidates(
        buildings, roads, boundary, target, seed,
        minimum=minimum, maximum=maximum,
        maximum_road_distance=maximum_road_distance,
        initial_used_buildings=block_buildings,
        initial_envelopes=block_envelopes)
    return _split_morphologically_heterogeneous_candidates(
        block_results + street_results, buildings, roads,
        minimum=minimum, maximum=maximum)


def _merged_intervals(intervals):
    """Return the union of one-dimensional intervals."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    start, end = ordered[0]
    merged = []
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            merged.append((start, end))
            start, end = next_start, next_end
    merged.append((start, end))
    return merged


def _cyclic_projection_intervals(footprint, boundary):
    """Project a footprint onto the shortest covering arc of a closed boundary."""
    perimeter = float(boundary.length)
    if perimeter <= 0:
        return []
    positions = sorted({
        float(boundary.project(Point(x, y))) % perimeter
        for x, y in shapely.get_coordinates(footprint)
    })
    if len(positions) < 2:
        return []
    gaps = [positions[index + 1] - positions[index]
            for index in range(len(positions) - 1)]
    gaps.append(positions[0] + perimeter - positions[-1])
    largest_gap_index = int(np.argmax(gaps))
    start = positions[(largest_gap_index + 1) % len(positions)]
    end = positions[largest_gap_index]
    if start <= end:
        return [(start, end)]
    return [(start, perimeter), (0.0, end)]


def _block_frontage_metrics(footprints, block_roads):
    """Measure frontage around closed blocks formed by ordinary roads."""
    empty = {
        'closed_road_block_count': 0,
        'block_frontage_coverage_max_pct': None,
        'block_frontage_largest_gap_min_pct': None,
        'block_frontage_structure_pct': None,
    }
    if not len(block_roads):
        return empty
    roads = block_roads.copy()
    if 'highway' in roads:
        roads = roads[~roads.highway.isin(['service', 'pedestrian'])]
    if not len(roads):
        return empty
    noded = unary_union(list(roads.geometry))
    blocks = list(polygonize(noded))
    if not blocks:
        return empty

    centres = [footprint.representative_point() for footprint in footprints]
    evaluated = []
    for block in blocks:
        building_ids = [index for index, centre in enumerate(centres)
                        if block.covers(centre)]
        if not building_ids:
            continue
        boundary = block.exterior
        perimeter = float(boundary.length)
        if perimeter <= 0:
            continue

        frontage_intervals = []
        for building_index in building_ids:
            footprint = footprints[building_index]
            if footprint.distance(boundary) > MAXIMUM_BLOCK_FRONTAGE_DISTANCE_M:
                continue
            frontage_intervals.extend(
                _cyclic_projection_intervals(footprint, boundary))

        merged = _merged_intervals(frontage_intervals)
        covered_length = min(sum(end - start for start, end in merged), perimeter)
        coverage = 100.0 * covered_length / perimeter
        if merged:
            uncovered_gaps = [merged[index + 1][0] - merged[index][1]
                              for index in range(len(merged) - 1)]
            uncovered_gaps.append(merged[0][0] + perimeter - merged[-1][1])
            largest_gap_pct = 100.0 * max(uncovered_gaps) / perimeter
        else:
            largest_gap_pct = 100.0
        structure = coverage if (
            coverage >= BLOCK_FRONTAGE_THRESHOLD_PCT and
            largest_gap_pct <= MAXIMUM_BLOCK_FRONTAGE_GAP_PCT
        ) else 0.0
        evaluated.append((structure, coverage, largest_gap_pct))

    if not evaluated:
        return empty
    return {
        'closed_road_block_count': len(evaluated),
        'block_frontage_coverage_max_pct': max(item[1] for item in evaluated),
        'block_frontage_largest_gap_min_pct': min(item[2] for item in evaluated),
        'block_frontage_structure_pct': max(item[0] for item in evaluated),
    }


def _road_side_position_groups(centres, roads,
                               maximum_road_distance=150.0):
    """Group projected building positions by noded road and road side."""
    lines = _noded_grouping_roads(roads)
    if not lines:
        return {}
    road_tree = shapely.STRtree(lines)
    positions = defaultdict(list)
    for building_index, centre in enumerate(centres):
        road_index = int(road_tree.nearest(centre))
        line = lines[road_index]
        if centre.distance(line) > maximum_road_distance:
            continue
        position = float(line.project(centre))
        projected = line.interpolate(position)
        epsilon = min(0.1, line.length / 2)
        before = line.interpolate(max(0.0, position - epsilon))
        after = line.interpolate(min(line.length, position + epsilon))
        dx, dy = after.x - before.x, after.y - before.y
        if dx == 0 and dy == 0:
            continue
        cross_product = (
            dx * (centre.y - projected.y) -
            dy * (centre.x - projected.x))
        side = 1 if cross_product >= 0 else -1
        positions[(road_index, side)].append((position, building_index))
    return positions


def _same_road_side_centroid_spacings(centres, roads,
                                      maximum_road_distance=150.0):
    """Return consecutive along-road centroid spacings on each road side."""
    positions = _road_side_position_groups(
        centres, roads, maximum_road_distance)
    spacings = []
    for values in positions.values():
        ordered = [position for position, _ in sorted(values)]
        spacings.extend(np.diff(ordered).tolist())
    return spacings


def _continuous_road_frontage_pct(
        centres, roads, maximum_gap=AB_FRONTAGE_MAXIMUM_GAP_M,
        minimum_run=AB_FRONTAGE_MINIMUM_RUN_BUILDINGS,
        maximum_road_distance=150.0):
    """Return buildings belonging to a continuous same-side road sequence."""
    if not centres:
        return None
    positions = _road_side_position_groups(
        centres, roads, maximum_road_distance)
    continuous = set()
    for values in positions.values():
        ordered = sorted(values)
        run = []
        for item in ordered:
            if run and item[0] - run[-1][0] > maximum_gap:
                if len(run) >= minimum_run:
                    continuous.update(index for _, index in run)
                run = []
            run.append(item)
        if len(run) >= minimum_run:
            continuous.update(index for _, index in run)
    return 100.0 * len(continuous) / len(centres)


def _local_line_direction_deg(line, point):
    """Return the axial direction of a line near the projection of a point."""
    if line is None or line.is_empty or line.length <= 0:
        return None
    position = float(line.project(point))
    epsilon = min(1.0, line.length / 2)
    before = line.interpolate(max(0.0, position - epsilon))
    after = line.interpolate(min(line.length, position + epsilon))
    dx, dy = after.x - before.x, after.y - before.y
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dy, dx)) % 180.0


def _axial_angle_difference_deg(first, second):
    difference = abs(first - second) % 180.0
    return min(difference, 180.0 - difference)


def _building_row_metrics(
        centres, roads, angle_step=ROW_ANGLE_STEP_DEG,
        band_tolerance=ROW_BAND_TOLERANCE_M,
        maximum_along_gap=ROW_MAXIMUM_ALONG_GAP_M,
        minimum_buildings=ROW_MINIMUM_BUILDINGS,
        minimum_rows=ROW_MINIMUM_ROWS,
        minimum_overlap_fraction=ROW_MINIMUM_OVERLAP_FRACTION,
        maximum_road_distance=150.0):
    """Detect repeated centroid rows regardless of their road orientation."""
    centres = list(centres)
    empty = {
        'row_structure_pct': 0.0,
        'row_count': 0,
        'row_building_count': 0,
        'row_direction_deg': None,
        'row_road_angle_deg': None,
        '_row_member_indices': [],
    }
    if len(centres) < minimum_buildings * minimum_rows:
        return empty
    lines = _noded_grouping_roads(roads)
    road_tree = shapely.STRtree(lines) if lines else None
    coordinates = np.asarray([(point.x, point.y) for point in centres],
                             dtype=float)
    best = None
    for angle_deg in range(0, 180, angle_step):
        angle = math.radians(angle_deg)
        along = (coordinates[:, 0] * math.cos(angle) +
                 coordinates[:, 1] * math.sin(angle))
        across = (-coordinates[:, 0] * math.sin(angle) +
                  coordinates[:, 1] * math.cos(angle))

        # Form narrow bands perpendicular to the tested row direction. A band
        # centre is updated as points are added so the tolerance cannot expand
        # indefinitely through single-linkage chaining.
        bands = []
        for index in np.argsort(across):
            choices = [
                (abs(float(across[index]) - band['mean']), band_index)
                for band_index, band in enumerate(bands)
                if abs(float(across[index]) - band['mean']) <=
                band_tolerance and
                (max(band['values'] + [float(across[index])]) -
                 min(band['values'] + [float(across[index])])) <=
                band_tolerance]
            if choices:
                _, band_index = min(choices)
                bands[band_index]['indices'].append(int(index))
                bands[band_index]['values'].append(float(across[index]))
                values = across[bands[band_index]['indices']]
                bands[band_index]['mean'] = float(np.mean(values))
            else:
                bands.append({'mean': float(across[index]),
                              'indices': [int(index)],
                              'values': [float(across[index])]})

        valid_rows = []
        for band in bands:
            ordered = sorted(band['indices'], key=lambda index: along[index])
            run = []
            for index in ordered:
                if (run and
                        float(along[index] - along[run[-1]]) >
                        maximum_along_gap):
                    if len(run) >= minimum_buildings:
                        valid_rows.append(run)
                    run = []
                run.append(index)
            if len(run) >= minimum_buildings:
                valid_rows.append(run)

        # Count a row only when another parallel row lies alongside at least
        # half of its shorter longitudinal span. Disjoint runs cannot qualify.
        qualifying_rows = set()
        intervals = [(float(along[row[0]]), float(along[row[-1]]))
                     for row in valid_rows]
        for first, (start, end) in enumerate(intervals):
            for second in range(first + 1, len(intervals)):
                other_start, other_end = intervals[second]
                shorter_length = min(end - start, other_end - other_start)
                overlap = max(0.0, min(end, other_end) -
                              max(start, other_start))
                if (shorter_length > 0 and
                        overlap >= minimum_overlap_fraction * shorter_length):
                    qualifying_rows.update((first, second))
        valid_rows = [row for index, row in enumerate(valid_rows)
                      if index in qualifying_rows]

        road_angles = []
        for row in valid_rows:
            if road_tree is None:
                continue
            row_centre = Point(
                float(np.mean(coordinates[row, 0])),
                float(np.mean(coordinates[row, 1])))
            road_index = int(road_tree.nearest(row_centre))
            road = lines[road_index]
            if row_centre.distance(road) > maximum_road_distance:
                continue
            road_direction = _local_line_direction_deg(road, row_centre)
            if road_direction is None:
                continue
            road_angle = _axial_angle_difference_deg(
                float(angle_deg), road_direction)
            road_angles.append(road_angle)

        members = {index for row in valid_rows for index in row}
        row_count = len(valid_rows)
        qualified_count = len(members) if row_count >= minimum_rows else 0
        coverage = 100.0 * qualified_count / len(centres)
        median_road_angle = (
            float(np.median(road_angles))
            if qualified_count and road_angles else None)
        candidate = (qualified_count, row_count, coverage, angle_deg,
                     median_road_angle, sorted(members))
        if best is None or candidate[:3] > best[:3]:
            best = candidate

    if best is None or best[0] == 0:
        return empty
    (qualified_count, row_count, coverage, angle_deg, road_angle,
     member_indices) = best
    return {
        'row_structure_pct': float(coverage),
        'row_count': int(row_count),
        'row_building_count': int(qualified_count),
        'row_direction_deg': float(angle_deg),
        'row_road_angle_deg': road_angle,
        '_row_member_indices': member_indices,
    }


def _split_row_morphology_candidate(candidate, buildings, roads,
                                    minimum=10, maximum=70):
    """Split a spatially ordered row subarea from a contrasting subarea."""
    envelope, member_ids, method = candidate
    ordered_ids = sorted(map(int, member_ids))
    if len(ordered_ids) < 2 * minimum or len(ordered_ids) > maximum:
        return [candidate]

    centres = [buildings.geometry.iloc[index].representative_point()
               for index in ordered_ids]
    road_tree = shapely.STRtree(roads.geometry.to_numpy())
    road_indices = road_tree.query(
        envelope.buffer(REVIEW_NEARBY_BUILDING_DISTANCE_M),
        predicate='intersects')
    if len(road_indices) == 0:
        return [candidate]
    local_roads = roads.iloc[np.unique(road_indices)].copy()
    row_metrics = _building_row_metrics(centres, local_roads)
    row_members = set(row_metrics['_row_member_indices'])
    if (len(row_members) < minimum or
            len(ordered_ids) - len(row_members) < minimum):
        return [candidate]

    coordinates = np.asarray([(point.x, point.y) for point in centres],
                             dtype=float)
    origin = coordinates.mean(axis=0)
    _, singular_values, axes = np.linalg.svd(
        coordinates - origin, full_matrices=False)
    if not len(singular_values) or singular_values[0] <= 1e-9:
        return [candidate]
    axis = axes[0]
    projections = (coordinates - origin) @ axis
    order = np.argsort(projections)
    projection_gaps = np.diff(projections[order])
    if not len(projection_gaps):
        return [candidate]
    q1, q3 = np.quantile(projection_gaps, [0.25, 0.75])
    iqr = float(q3 - q1)
    split_gap_threshold = float(
        q3 + 1.5 * iqr if iqr > 1e-9
        else 3 * np.median(projection_gaps))
    labels = np.asarray([index in row_members
                         for index in range(len(ordered_ids))], dtype=bool)
    span = max(
        envelope.bounds[2] - envelope.bounds[0],
        envelope.bounds[3] - envelope.bounds[1]) * 4 + 100
    perpendicular = np.asarray([-axis[1], axis[0]])
    footprints = buildings.geometry.iloc[ordered_ids].to_numpy()
    options = []

    for cut in range(minimum, len(ordered_ids) - minimum + 1):
        left_local = order[:cut]
        right_local = order[cut:]
        left_share = float(labels[left_local].mean())
        right_share = float(labels[right_local].mean())
        share_difference = abs(left_share - right_share)
        correct = max(
            int(labels[left_local].sum()) + int((~labels[right_local]).sum()),
            int((~labels[left_local]).sum()) + int(labels[right_local].sum()))
        accuracy = correct / len(ordered_ids)
        if (accuracy < MORPHOLOGY_SPLIT_MINIMUM_ACCURACY or
                share_difference <
                MORPHOLOGY_SPLIT_MINIMUM_ROW_SHARE_DIFFERENCE):
            continue
        gap = float(projections[order[cut]] - projections[order[cut - 1]])
        if gap <= split_gap_threshold:
            continue
        cut_position = float(
            (projections[order[cut]] + projections[order[cut - 1]]) / 2)
        divider_centre = origin + axis * cut_position
        divider = LineString([
            divider_centre - perpendicular * span,
            divider_centre + perpendicular * span])
        if any(divider.intersects(footprint) for footprint in footprints):
            continue
        options.append((accuracy, share_difference, gap, cut_position,
                        divider, left_local, right_local))

    if not options:
        return [candidate]
    _, _, _, cut_position, divider, left_local, right_local = max(
        options, key=lambda option: option[:3])
    pieces = [part for part in shapely.get_parts(split(envelope, divider))
              if part.geom_type == 'Polygon' and not part.is_empty]
    if len(pieces) < 2:
        return [candidate]

    left_parts, right_parts = [], []
    for part in pieces:
        point = part.representative_point()
        projection = np.dot(
            np.asarray([point.x, point.y]) - origin, axis)
        (left_parts if projection <= cut_position else right_parts).append(part)
    if not left_parts or not right_parts:
        return [candidate]
    left_envelope = _normalize_polygonal(unary_union(left_parts))
    right_envelope = _normalize_polygonal(unary_union(right_parts))
    left_ids = [ordered_ids[index] for index in left_local]
    right_ids = [ordered_ids[index] for index in right_local]
    left_footprints = unary_union(
        list(buildings.geometry.iloc[left_ids]))
    right_footprints = unary_union(
        list(buildings.geometry.iloc[right_ids]))
    if (not left_envelope.covers(left_footprints) or
            not right_envelope.covers(right_footprints)):
        return [candidate]

    left_share = float(labels[left_local].mean())
    right_share = float(labels[right_local].mean())
    left_role = ('row' if left_share > right_share else 'nonrow')
    right_role = ('row' if right_share > left_share else 'nonrow')
    return [
        (left_envelope, left_ids,
         f'{method}_morphology_{left_role}_split'),
        (right_envelope, right_ids,
         f'{method}_morphology_{right_role}_split'),
    ]


def _split_morphologically_heterogeneous_candidates(
        candidates, buildings, roads, minimum=10, maximum=70):
    """Apply one conservative row/non-row split to each candidate."""
    refined = []
    for candidate in candidates:
        refined.extend(_split_row_morphology_candidate(
            candidate, buildings, roads, minimum, maximum))
    return refined


def _settlement_context_from_metrics(density, bcr):
    """Classify the surrounding building stock as rural or urban."""
    if density is None or bcr is None:
        return 'RURAL'
    if (density >= URBAN_CONTEXT_MINIMUM_DENSITY or
            bcr >= URBAN_CONTEXT_MINIMUM_BCR or
            (density >= URBAN_CONTEXT_COMBINED_MINIMUM_DENSITY and
             bcr >= URBAN_CONTEXT_COMBINED_MINIMUM_BCR)):
        return 'URBAN'
    return 'RURAL'


def _rural_boundary_eligible(density, bcr):
    """Return whether the original surroundings justify a rural boundary."""
    return (density is not None and bcr is not None and
            density < RURAL_CONTEXT_MAXIMUM_DENSITY and
            bcr < RURAL_CONTEXT_MAXIMUM_BCR)


def _settlement_context_metrics(candidates, buildings, analysis_boundary,
                                buffer_distance=SETTLEMENT_CONTEXT_BUFFER_M):
    """Describe the eligible building stock around, but outside, candidates."""
    footprints = buildings.geometry.to_numpy()
    points = buildings.geometry.representative_point().to_numpy()
    point_tree = shapely.STRtree(points)
    results = []
    for geometry, _, _ in candidates:
        context_zone = _normalize_polygonal(
            geometry.buffer(buffer_distance)
            .intersection(analysis_boundary)
            .difference(geometry))
        if context_zone.is_empty or context_zone.area <= 0:
            results.append({
                'settlement_context': 'RURAL',
                'context_area_ha': 0.0,
                'context_building_count': 0,
                'context_building_density_per_ha': None,
                'context_bcr': None,
            })
            continue
        indices = np.unique(point_tree.query(
            context_zone, predicate='contains')).astype(int)
        covered_area = 0.0
        if len(indices):
            covered_area = float(unary_union(
                list(footprints[indices])).intersection(context_zone).area)
        area_ha = float(context_zone.area / 10000)
        density = float(len(indices) / area_ha)
        bcr = float(covered_area / context_zone.area)
        context = _settlement_context_from_metrics(density, bcr)
        results.append({
            'settlement_context': context,
            'context_area_ha': area_ha,
            'context_building_count': int(len(indices)),
            'context_building_density_per_ha': density,
            'context_bcr': bcr,
        })
    return results


def _apply_rural_influence_boundaries(candidates, contexts, buildings,
                                       analysis_boundary):
    """Replace clearly rural envelopes by building influence areas.

    A Voronoi cell assigns every location to its nearest eligible building.
    Consequently, a cell boundary lies halfway between neighbouring building
    points.  For a clearly rural candidate, the union of its member cells
    retains open land associated with those buildings while stopping at
    unselected buildings, industrial exclusions and the study boundary.
    """
    apply_indices = {
        index for index, context in enumerate(contexts)
        if _rural_boundary_eligible(
            context['context_building_density_per_ha'],
            context['context_bcr'])}
    if not apply_indices:
        return list(candidates), set(), {}

    points = list(buildings.geometry.representative_point().to_numpy())
    unique_points = []
    coordinate_to_unique = {}
    building_to_unique = []
    for point in points:
        coordinate = (float(point.x), float(point.y))
        unique_index = coordinate_to_unique.get(coordinate)
        if unique_index is None:
            unique_index = len(unique_points)
            coordinate_to_unique[coordinate] = unique_index
            unique_points.append(point)
        building_to_unique.append(unique_index)

    cells_geometry = shapely.voronoi_polygons(
        shapely.MultiPoint(unique_points),
        extend_to=analysis_boundary.envelope,
        ordered=True)
    cells = list(shapely.get_parts(cells_geometry))
    if len(cells) != len(unique_points):
        raise RuntimeError(
            'Building influence-cell count does not match unique points.')

    original_geometries = [candidate[0] for candidate in candidates]
    original_tree = shapely.STRtree(original_geometries)
    footprints = list(buildings.geometry.to_numpy())
    footprint_tree = shapely.STRtree(footprints)
    non_rural_indices = set(range(len(candidates))) - apply_indices
    results = []
    reaches = {}
    for candidate_index, (geometry, member_ids, method) in enumerate(candidates):
        if candidate_index not in apply_indices:
            results.append((geometry, member_ids, method))
            continue

        cell_indices = sorted({
            building_to_unique[int(building_index)]
            for building_index in member_ids})
        influence = _normalize_polygonal(
            unary_union([cells[index] for index in cell_indices])
            .intersection(analysis_boundary))

        selected_points = [points[int(index)] for index in member_ids]
        nearest_distances = _nearest_point_distances(selected_points)
        if nearest_distances:
            q1, q3 = np.quantile(nearest_distances, [0.25, 0.75])
            iqr = float(q3 - q1)
            reach = (float(q3 + 1.5 * iqr) if iqr > 1e-9 else
                     float(1.5 * np.median(nearest_distances)))
        else:
            # Production candidates contain at least the configured minimum
            # number of buildings. Keep the helper defined for a one-building
            # diagnostic fixture as well.
            reach = 30.0
        reaches[candidate_index] = reach
        selected_footprints = unary_union(list(
            buildings.geometry.iloc[sorted(member_ids)].to_numpy()))
        hull_ratio = _adaptive_hull_ratio(selected_points)
        rural_base = shapely.concave_hull(
            selected_footprints, ratio=hull_ratio, allow_holes=False)
        influence = _normalize_polygonal(
            influence.intersection(
                rural_base.buffer(reach, join_style='mitre'))
            .intersection(analysis_boundary))

        # The Voronoi partition prevents overlap between rural candidates.
        # Existing non-rural envelopes are additionally retained as obstacles.
        blocker_indices = set(map(int, original_tree.query(
            influence, predicate='intersects'))) & non_rural_indices
        if blocker_indices:
            blockers = unary_union([
                original_geometries[index] for index in blocker_indices])
            influence = _normalize_polygonal(
                influence.difference(blockers).intersection(
                    analysis_boundary))

        # A Voronoi cell is defined by building points, so the complete
        # footprint of an external building can cross the point bisector.
        # Remove every such external footprint before restoring the selected
        # member footprints. This keeps the review boundary consistent with
        # exact building membership and prevents neighbouring rural candidate
        # envelopes from overlapping at large footprints.
        external_footprint_indices = (
            set(map(int, footprint_tree.query(
                influence, predicate='intersects'))) -
            set(map(int, member_ids)))
        if external_footprint_indices:
            influence = _normalize_polygonal(influence.difference(
                unary_union([
                    footprints[index]
                    for index in external_footprint_indices])))

        influence = _normalize_polygonal(
            influence.union(selected_footprints).intersection(
                analysis_boundary))
        if influence.is_empty:
            raise RuntimeError(
                f'Rural influence boundary {candidate_index} is empty.')
        results.append((
            influence, member_ids,
            f'{method}_rural_influence_boundary'))
    return results, apply_indices, reaches


def _remaining_scattered_groups(buildings, roads, used, minimum=10, maximum=70):
    """Connect unused street stations across empty roads, then cut local gaps."""
    import networkx as nx

    points = buildings.geometry.representative_point().to_numpy()
    lines = _noded_grouping_roads(roads)
    if not lines:
        return []
    road_tree = shapely.STRtree(lines)
    stations = defaultdict(lambda: defaultdict(set))
    for index, road_index in enumerate(road_tree.nearest(points)):
        line = lines[int(road_index)]
        if points[index].distance(line) <= 150.0:
            stations[int(road_index)][round(line.project(points[index]), 1)].add(index)

    network = nx.Graph()
    occupants = defaultdict(set)
    for road_index, line in enumerate(lines):
        start = ('junction', *[round(v, 1) for v in line.coords[0][:2]])
        end = ('junction', *[round(v, 1) for v in line.coords[-1][:2]])
        positions = [(0.0, start), (float(line.length), end)]
        for position, ids in sorted(stations[road_index].items()):
            position = min(float(line.length), max(0.0, position))
            node = (start if position == 0 else end if position == line.length
                    else ('station', road_index, position))
            occupants[node].update(ids)
            positions.append((position, node))
        positions.sort(key=lambda item: item[0])
        network.add_nodes_from(node for _, node in positions)
        for (left_pos, left), (right_pos, right) in zip(positions, positions[1:]):
            if left == right:
                continue
            distance = right_pos - left_pos
            if not network.has_edge(left, right) or distance < network[left][right]['weight']:
                network.add_edge(left, right, weight=distance)

    # Assigned buildings are barriers: the extra pass never grows through them.
    available = {node for node, ids in occupants.items() if not ids & used}
    station_graph = nx.Graph()
    station_graph.add_nodes_from(sorted(available))
    for source in sorted(available):
        queue, distances, serial = [(0.0, 0, source)], {source: 0.0}, 0
        while queue:
            distance, _, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            if node != source and node in occupants:
                if node in available:
                    station_graph.add_edge(source, node, weight=distance)
                continue
            for other, data in network[node].items():
                next_distance = distance + data['weight']
                if next_distance < distances.get(other, math.inf):
                    distances[other] = next_distance
                    serial += 1
                    heapq.heappush(queue, (next_distance, serial, other))

    # Derive each station's gap limit from nearest-station distances in its
    # two-hop neighbourhood. Compact groups do not justify a long empty bridge.
    limits = {}
    for node in station_graph:
        neighbourhood = {node} | set(station_graph[node])
        neighbourhood |= {other for neighbour in list(neighbourhood)
                          for other in station_graph[neighbour]}
        nearest = [min(data['weight'] for data in station_graph[n].values())
                   for n in neighbourhood if station_graph[n]]
        nearest = [value for value in nearest if value > 0]
        threshold = _exceptional_gap_threshold(nearest)
        limits[node] = (threshold if threshold is not None else
                        3 * float(np.median(nearest)) if nearest else 0.0)
    station_graph.remove_edges_from([
        (left, right) for left, right, data in station_graph.edges(data=True)
        if data['weight'] > min(limits[left], limits[right])])

    def divide(nodes):
        ids = set().union(*(occupants[node] for node in nodes))
        if len(ids) < minimum:
            return []
        if len(ids) <= maximum:
            return [ids]
        tree = nx.minimum_spanning_tree(station_graph.subgraph(nodes))
        if not tree.edges:
            return []
        left, right, _ = max(tree.edges(data=True),
                             key=lambda edge: (edge[2]['weight'], edge[0], edge[1]))
        tree.remove_edge(left, right)
        return [group for component in nx.connected_components(tree)
                for group in divide(component)]

    return [group for component in sorted(
        nx.connected_components(station_graph), key=lambda nodes: min(nodes))
            for group in divide(component)]


def _additional_scattered_candidates(existing, buildings, roads, boundary, ranges,
                                    minimum=10, maximum=70):
    """Append only acceptable A candidates; preserve every existing envelope."""
    used = {index for _, ids, _ in existing for index in ids}
    points = buildings.geometry.representative_point().to_numpy()
    point_tree = shapely.STRtree(points)
    footprint_tree = shapely.STRtree(buildings.geometry.to_numpy())
    road_tree = shapely.STRtree(roads.geometry.to_numpy())
    registry = _SpatialRegistry()
    for geometry, _, _ in existing:
        registry.add(geometry)
    proposals = []
    for ids in _remaining_scattered_groups(buildings, roads, used, minimum, maximum):
        for geometry, members, _ in _building_envelope(
                ids, buildings, points, point_tree, footprint_tree, used,
                boundary, minimum, maximum):
            if not registry.intersects(geometry):
                proposals.append((geometry, members, 'additional_scattered_A'))
    initial = _settlement_context_metrics(proposals, buildings, boundary)
    sparse = [(candidate, context) for candidate, context in zip(proposals, initial)
              if _rural_boundary_eligible(context['context_building_density_per_ha'],
                                          context['context_bcr'])]
    if not sparse:
        return [], [], [], {}
    proposals, initial = map(list, zip(*sparse))
    # Existing candidates are passed as immutable obstacles, with rural
    # expansion disabled for them. Only additional envelopes can change.
    blockers = [{'context_building_density_per_ha': None, 'context_bcr': None}
                for _ in existing]
    expanded, _, reaches = _apply_rural_influence_boundaries(
        list(existing) + proposals, blockers + initial, buildings, boundary)
    proposals = expanded[len(existing):]
    final_contexts = _settlement_context_metrics(proposals, buildings, boundary)
    scales = common_indicator_scales(ranges)
    accepted, accepted_initial, accepted_contexts, accepted_reaches = [], [], [], {}
    for index, (candidate, context) in enumerate(zip(proposals, final_contexts)):
        geometry, ids, method = candidate
        if set(ids) & used or registry.intersects(geometry):
            continue
        selected = buildings.iloc[ids]
        local_roads = roads.iloc[road_tree.query(geometry, predicate='intersects')]
        block_roads = roads.iloc[road_tree.query(
            geometry.buffer(math.sqrt(geometry.area)), predicate='intersects')]
        metrics = geometry_metrics(selected, local_roads, geometry, block_roads)
        levels = pd.to_numeric(selected.get(
            'building:levels', pd.Series(index=selected.index, dtype=float)), errors='coerce')
        levels = levels.where((levels > 0) & (levels <= 100))
        metrics.update({
            'bcr': float(selected.geometry.area.sum() / geometry.area),
            'density': len(selected) / geometry.area * 10000,
            'far': (float((selected.geometry.area * levels.fillna(levels.mean())).sum()
                          / geometry.area) if levels.notna().mean() >= .66 else None)})
        allowed = {'A'} & CONTEXT_ALLOWED_TYPES[context['settlement_context']]
        score = next(item for item in range_scores(metrics, ranges, scales, allowed)
                     if item['type'] == 'A')
        if not score['eligible'] or classification_quality(score['range_score']) == 'unclassified':
            continue
        accepted_reaches[len(accepted)] = reaches.get(len(existing) + index)
        accepted.append(candidate)
        accepted_initial.append(initial[index])
        accepted_contexts.append(context)
        used.update(ids)
        registry.add(geometry)
    return accepted, accepted_initial, accepted_contexts, accepted_reaches


def _residential_typology_metrics(buildings):
    """Return hierarchical explicit and area-inferred SFH/MFH evidence."""
    tags = buildings.get(
        'building', pd.Series('', index=buildings.index)
    ).fillna('').astype(str).str.strip().str.lower()
    building_uses = buildings.get(
        'building:use', pd.Series('', index=buildings.index)
    ).fillna('').astype(str).str.strip().str.lower()
    flats = pd.to_numeric(
        buildings.get(
            'building:flats', pd.Series(np.nan, index=buildings.index)),
        errors='coerce')
    areas = buildings.geometry.area

    # Evidence is deliberately resolved in this order. Once a more specific
    # source resolves a footprint, less specific sources cannot overwrite it.
    sfh_from_flats = flats.eq(1)
    mfh_from_flats = flats.ge(2)
    resolved = sfh_from_flats | mfh_from_flats

    sfh_from_use = (~resolved) & building_uses.isin(
        SFH_LIKE_BUILDING_TAGS)
    mfh_from_use = (~resolved) & building_uses.isin(
        MFH_LIKE_BUILDING_TAGS)
    nonres_from_use = (~resolved) & building_uses.isin(
        NONRES_BUILDINGS)
    resolved = resolved | sfh_from_use | mfh_from_use | nonres_from_use

    sfh_from_tag = (~resolved) & tags.isin(SFH_LIKE_BUILDING_TAGS)
    mfh_from_tag = (~resolved) & tags.isin(MFH_LIKE_BUILDING_TAGS)
    resolved = resolved | sfh_from_tag | mfh_from_tag

    explicit_sfh = sfh_from_flats | sfh_from_use | sfh_from_tag
    explicit_mfh = mfh_from_flats | mfh_from_use | mfh_from_tag
    ambiguous_residential = (~resolved) & (
        tags.isin(AMBIGUOUS_RESIDENTIAL_BUILDING_TAGS) |
        building_uses.isin(AMBIGUOUS_RESIDENTIAL_BUILDING_TAGS))
    inferred_sfh = (
        ambiguous_residential &
        (areas < INFERRED_SFH_MAXIMUM_FOOTPRINT_AREA_M2))
    inferred_mfh = (
        ambiguous_residential &
        (areas > INFERRED_MFH_MINIMUM_FOOTPRINT_AREA_M2))
    explicit_sfh_count = int(explicit_sfh.sum())
    explicit_mfh_count = int(explicit_mfh.sum())
    inferred_sfh_count = int(inferred_sfh.sum())
    inferred_mfh_count = int(inferred_mfh.sum())
    sfh_count = explicit_sfh_count + inferred_sfh_count
    mfh_count = explicit_mfh_count + inferred_mfh_count
    known_count = sfh_count + mfh_count
    residential_population = (
        explicit_sfh | explicit_mfh | ambiguous_residential)
    residential_count = int(residential_population.sum())
    coverage = (
        100.0 * known_count / residential_count
        if residential_count else 0.0)
    requirement_applied = (
        coverage >= RESIDENTIAL_TYPOLOGY_MINIMUM_COVERAGE_PCT)
    return {
        'sfh_like_count': sfh_count,
        'mfh_like_count': mfh_count,
        'explicit_sfh_like_count': explicit_sfh_count,
        'explicit_mfh_like_count': explicit_mfh_count,
        'inferred_sfh_like_count': inferred_sfh_count,
        'inferred_mfh_like_count': inferred_mfh_count,
        'typology_from_building_flats_count': int(
            (sfh_from_flats | mfh_from_flats).sum()),
        'typology_from_building_use_count': int(
            (sfh_from_use | mfh_from_use).sum()),
        'typology_from_building_tag_count': int(
            (sfh_from_tag | mfh_from_tag).sum()),
        'aggregate_terrace_footprint_count': int(tags.eq('terrace').sum()),
        'residential_building_count_for_typology': residential_count,
        'known_residential_typology_count': known_count,
        'unknown_residential_typology_count': (
            residential_count - known_count),
        'residential_typology_coverage_pct': coverage,
        'sfh_share_known_pct': (
            100.0 * sfh_count / known_count if known_count else None),
        'mfh_share_known_pct': (
            100.0 * mfh_count / known_count if known_count else None),
        'residential_typology_requirement_applied': requirement_applied,
    }


def geometry_metrics(b, local_roads, geom, block_roads=None):
    """Descriptive metrics for review; do not use use-tags to infer morphology."""
    footprints = b.geometry.to_numpy()
    tree = shapely.STRtree(footprints)
    attached = []
    centers = [footprint.centroid for footprint in footprints]
    road_side_spacings = _same_road_side_centroid_spacings(
        centers, local_roads)
    nearest_centroid_distances = _nearest_point_distances(centers)
    for i, footprint in enumerate(footprints):
        attached.append(any(j != i and footprint.boundary.intersection(footprints[j].boundary).length > 1
                            for j in tree.query(footprint, predicate='intersects')))
    result = {'attached_building_pct':100*sum(attached)/len(attached)}
    result.update(_residential_typology_metrics(b))
    result['road_side_longitudinal_spacing_count'] = len(road_side_spacings)
    result['road_side_spacing_count'] = len(road_side_spacings)
    result['nearest_building_centroid_distance_count'] = len(
        nearest_centroid_distances)
    if road_side_spacings:
        result['building_spacing_median_m'] = float(
            np.median(road_side_spacings))
        result['building_spacing_source'] = 'same_road_side'
    elif nearest_centroid_distances:
        result['building_spacing_median_m'] = float(
            np.median(nearest_centroid_distances))
        result['building_spacing_source'] = 'nearest_neighbour_fallback'
    else:
        result['building_spacing_median_m'] = None
        result['building_spacing_source'] = 'missing'
    result['continuous_road_frontage_pct'] = (
        _continuous_road_frontage_pct(centers, local_roads))
    row_metrics = _building_row_metrics(centers, local_roads)
    row_metrics.pop('_row_member_indices', None)
    result.update(row_metrics)
    result['boundary_hull_ratio'] = _adaptive_hull_ratio(centers)
    result.update(_block_frontage_metrics(
        footprints, local_roads if block_roads is None else block_roads))
    for key, values in [
            ('road_side_longitudinal_spacing', road_side_spacings),
            ('nearest_building_centroid_distance',
             nearest_centroid_distances)]:
        for stat, function in [('min',min),('max',max),('mean',np.mean),('median',np.median)]:
            result[f'{key}_{stat}_m'] = float(function(values)) if values else None
        result[f'{key}_q1_m'] = (
            float(np.quantile(values, 0.25)) if values else None)
        result[f'{key}_q3_m'] = (
            float(np.quantile(values, 0.75)) if values else None)
        result[f'{key}_iqr_m'] = (
            result[f'{key}_q3_m'] - result[f'{key}_q1_m']
            if values else None)
        median = result[f'{key}_median_m']
        result[f'{key}_maximum_to_median_ratio'] = (
            result[f'{key}_max_m'] / median
            if median is not None and median > 0 else None)
    return result


def common_indicator_scales(ranges):
    """Return one type-independent normalization scale per scored indicator."""
    keys = sorted({
        key for config in ranges.values() for key in config['bounds']})
    scales = {}
    for key in keys:
        widths = [
            config['bounds'][key][1] - config['bounds'][key][0]
            for config in ranges.values() if key in config['bounds']]
        scale = float(np.median(widths))
        if scale <= 0:
            raise ValueError(f'Expected a positive common scale for {key}.')
        scales[key] = scale
    return scales


def range_scores(metrics, ranges, common_scales=None, allowed_types=None):
    common_scales = common_scales or common_indicator_scales(ranges)
    scores = []
    for typ, config in ranges.items():
        penalties, midpoint_distances, hits = {}, {}, 0
        requirement_results = {}
        for key, (lo, hi) in config.get('requirements', {}).items():
            value = metrics.get(key)
            requirement_results[key] = (
                value is not None and lo <= value <= hi)
        for key, upper in config.get('exclusive_upper_requirements', {}).items():
            value = metrics.get(key)
            requirement_results[key] = value is not None and value < upper
        for key, requirement in config.get(
                'conditional_requirements', {}).items():
            if not metrics.get(requirement['when'], False):
                requirement_results[key] = None
                continue
            lo, hi = requirement['bounds']
            value = metrics.get(key)
            requirement_results[key] = (
                value is not None and lo <= value <= hi)
        context_eligible = (
            allowed_types is None or typ in set(allowed_types))
        requirement_results['settlement_context'] = context_eligible
        eligible = all(
            value is not False for value in requirement_results.values())
        for key, (lo, hi) in config['bounds'].items():
            value = metrics.get(key)
            if key == 'mfh_share_known_pct' and not metrics.get(
                    'residential_typology_requirement_applied', False):
                value = None
            if value is None:
                penalties[key] = None
                midpoint_distances[key] = None
                continue
            scale = common_scales[key]
            penalty = max(lo-value, value-hi, 0) / scale
            midpoint_target = (config.get('residential_mfh_target_pct', (lo + hi) / 2)
                               if key == 'mfh_share_known_pct' else (lo + hi) / 2)
            midpoint_distance = abs(value - midpoint_target) / scale
            penalties[key] = penalty
            midpoint_distances[key] = midpoint_distance
            hits += int(lo <= value <= hi)
        available_penalties = [value for value in penalties.values()
                               if value is not None]
        available_midpoints = [value for value in midpoint_distances.values()
                               if value is not None]
        scores.append({
            'type': typ,
            'eligible': eligible,
            'requirement_results': requirement_results,
            'range_score': (sum(value * value for value in available_penalties) /
                            len(available_penalties) if eligible else math.inf),
            'midpoint_score': (sum(value * value for value in available_midpoints) /
                               len(available_midpoints) if eligible else math.inf),
            'hits': hits,
            'penalties': penalties,
            'midpoint_distances': midpoint_distances,
            'indicator_count': len(available_penalties),
        })
    return sorted(scores, key=lambda item: (
        not item['eligible'], item['range_score'], item['midpoint_score'],
        item['type']))


def assign_type(scores):
    """Assign every candidate and retain how the assignment was obtained."""
    compatible = [score for score in scores
                  if score['eligible'] and score['range_score'] == 0]
    if len(compatible) == 1:
        return compatible[0], compatible, 'unique_compatible'
    if len(compatible) > 1:
        selected = min(compatible, key=lambda item: (
            item['midpoint_score'], item['type']))
        return selected, compatible, 'midpoint_tiebreak'
    return scores[0], compatible, 'nearest_outside_ranges'


def classification_quality(range_score):
    """Convert the selected range score into the final result category."""
    if not math.isfinite(range_score) or range_score > MAXIMUM_ASSIGNED_RANGE_SCORE:
        return 'unclassified'
    if range_score == 0:
        return 'exact'
    return 'approximate'


def add_use_percentage_columns(row, counts, nrb_counts, diagnostics):
    total_nrb = diagnostics['classified_nrb_building_count']
    for category, value in nrb_counts.items():
        row[f'nrb_{category}_building_count'] = value
        row[f'nrb_{category}_building_percentage'] = (
            100.0 * value / total_nrb if total_nrb else 0.0)
    total_buildings = diagnostics['building_footprint_count']
    known = sum(diagnostics[f'{name}_building_split_count']
                for name in ('residential', 'mixed', 'nonres'))
    for split_name in ('residential', 'mixed', 'nonres', 'unknown'):
        value = diagnostics[f'{split_name}_building_split_count']
        row[f'{split_name}_building_percentage_of_all'] = (
            100.0 * value / total_buildings if total_buildings else 0.0)
        if split_name != 'unknown':
            row[f'{split_name}_building_percentage_of_known'] = (
                100.0 * value / known if known else 0.0)
    for name, value in counts.items():
        if name.endswith('_count') or name == 'osm_objects_total':
            row[f'{name}_per_ha'] = (
                value / row['area_ha'] if row['area_ha'] > 0 else 0.0)


def write_use_outputs(rows, output_dir):
    by_district = pd.DataFrame(rows)
    by_district_path = output_dir / 'osm_use_counts_by_district.csv'
    by_district.to_csv(by_district_path, index=False)
    success_mask = by_district['query_success'].astype(str).str.lower().isin(
        {'true', '1'})
    if 'included_in_type_results' in by_district.columns:
        success_mask &= by_district['included_in_type_results'].astype(
            str).str.lower().isin({'true', '1'})
    successful = by_district[success_mask].copy()
    summary_path = output_dir / 'osm_use_summary_by_type.csv'
    nrb_path = output_dir / 'osm_nrb_building_percentages_by_type.csv'
    split_path = output_dir / 'osm_building_split_percentages_by_type.csv'
    if successful.empty:
        for path in (summary_path, nrb_path, split_path):
            pd.DataFrame().to_csv(path, index=False)
        return by_district_path, summary_path, nrb_path, split_path

    excluded = {'district_id', 'typ', 'region', 'query_error'}
    numeric = [name for name in successful.columns
               if name not in excluded
               and pd.api.types.is_numeric_dtype(successful[name])]
    summary = successful.groupby('typ')[numeric].agg(
        ['count', 'mean', 'median', 'min', 'max'])
    summary.columns = ['_'.join(column).strip('_')
                       for column in summary.columns.to_flat_index()]
    summary.reset_index().to_csv(summary_path, index=False)

    nrb_rows = []
    split_rows = []
    for typ, group in successful.groupby('typ'):
        total_nrb = int(group['classified_nrb_building_count'].sum())
        nrb_row = {
            'typ': typ,
            'successful_district_count': int(len(group)),
            'area_ha_total': float(group['area_ha'].sum()),
            'classified_nrb_building_count': total_nrb,
            'building_footprint_count': int(group['building_footprint_count'].sum()),
            'building_footprints_with_direct_nrb_tag_count': int(
                group['building_footprints_with_direct_nrb_tag_count'].sum()),
            'building_footprints_classified_from_poi_count': int(
                group['building_footprints_classified_from_poi_count'].sum()),
            'classified_poi_without_building_count': int(
                group['classified_poi_without_building_count'].sum()),
        }
        for category in ANALYSIS_CATEGORIES:
            count = int(group[f'nrb_{category}_building_count'].sum())
            nrb_row[f'nrb_{category}_building_count'] = count
            nrb_row[f'nrb_{category}_building_percentage'] = (
                100.0 * count / total_nrb if total_nrb else 0.0)
        nrb_rows.append(nrb_row)

        total = int(group['building_footprint_count'].sum())
        residential = int(group['residential_building_split_count'].sum())
        mixed = int(group['mixed_building_split_count'].sum())
        nonres = int(group['nonres_building_split_count'].sum())
        unknown = int(group['unknown_building_split_count'].sum())
        known = residential + mixed + nonres
        split_rows.append({
            'typ': typ,
            'successful_district_count': int(len(group)),
            'building_footprint_count': total,
            'residential_building_count': residential,
            'mixed_building_count': mixed,
            'nonres_building_count': nonres,
            'unknown_building_count': unknown,
            'residential_building_percentage_of_all': (
                100.0 * residential / total if total else 0.0),
            'mixed_building_percentage_of_all': (
                100.0 * mixed / total if total else 0.0),
            'nonres_building_percentage_of_all': (
                100.0 * nonres / total if total else 0.0),
            'unknown_building_percentage_of_all': (
                100.0 * unknown / total if total else 0.0),
            'residential_building_percentage_of_known': (
                100.0 * residential / known if known else 0.0),
            'mixed_building_percentage_of_known': (
                100.0 * mixed / known if known else 0.0),
            'nonres_building_percentage_of_known': (
                100.0 * nonres / known if known else 0.0),
        })
    pd.DataFrame(nrb_rows).to_csv(nrb_path, index=False)
    pd.DataFrame(split_rows).to_csv(split_path, index=False)
    return by_district_path, summary_path, nrb_path, split_path


def analyse(out, boundary, features, ranges, target, seed, minimum=None, maximum=None,
            candidate_method='hybrid', analysis_scope='unspecified'):
    (features, area, buildings, roads, industrial_sites,
     industrial_exclusion) = extract(features, boundary)
    print(f'{len(buildings)} eligible footprints; {len(roads)} road features', flush=True)
    print(
        f"Excluded {industrial_exclusion['small_footprint_excluded_buildings']} "
        f"building footprints below "
        f"{MINIMUM_BUILDING_FOOTPRINT_AREA_M2:g} m²",
        flush=True)
    print(
        f"Excluded {industrial_exclusion['industrial_excluded_buildings']} "
        f"buildings in {industrial_exclusion['industrial_site_polygons']} "
        f"industrial land-use polygons "
        f"({industrial_exclusion['industrial_exclusion_area_ha']:.1f} ha)",
        flush=True)
    if candidate_method == 'hybrid':
        groups = hybrid_candidates(buildings, roads, area, target, seed,
                                   minimum=minimum, maximum=maximum)
    elif candidate_method == 'street_clusters':
        groups = street_candidates(buildings, roads, area, target, seed,
                                   minimum=minimum, maximum=maximum)
    elif candidate_method == 'road_blocks':
        groups = block_candidates(buildings, roads, area, target, seed,
                                  minimum=minimum, maximum=maximum)
    else:
        raise ValueError(f'Unknown candidate method: {candidate_method}')
    print(f'{len(groups)} non-overlapping candidates', flush=True)
    initial_context_metrics = _settlement_context_metrics(
        groups, buildings, area)
    (groups, rural_boundary_indices,
     rural_boundary_reaches) = _apply_rural_influence_boundaries(
        groups, initial_context_metrics, buildings, area)
    if rural_boundary_indices:
        print(
            f'Applied rural building-influence boundaries to '
            f'{len(rural_boundary_indices)} candidates', flush=True)
    context_metrics = _settlement_context_metrics(groups, buildings, area)
    for index, context in enumerate(context_metrics):
        initial = initial_context_metrics[index]
        context['rural_influence_boundary_applied'] = (
            index in rural_boundary_indices)
        context['rural_boundary_reach_m'] = rural_boundary_reaches.get(index)
        context['initial_context_building_density_per_ha'] = (
            initial['context_building_density_per_ha'])
        context['initial_context_bcr'] = initial['context_bcr']
    additional, additional_initial, additional_contexts, additional_reaches = (
        _additional_scattered_candidates(
            groups, buildings, roads, area, ranges,
            minimum=minimum or 10, maximum=maximum or 70))
    for index, context in enumerate(additional_contexts):
        context['rural_influence_boundary_applied'] = True
        context['rural_boundary_reach_m'] = additional_reaches.get(index)
        context['initial_context_building_density_per_ha'] = (
            additional_initial[index]['context_building_density_per_ha'])
        context['initial_context_bcr'] = additional_initial[index]['context_bcr']
    groups.extend(additional)
    context_metrics.extend(additional_contexts)
    print(f'{len(additional)} additional scattered A candidates accepted', flush=True)
    feature_tree = shapely.STRtree(features.geometry.to_numpy())
    road_tree = shapely.STRtree(roads.geometry.to_numpy())
    rows, geoms, use_rows, membership = [], [], [], []
    common_scales = common_indicator_scales(ranges)
    for number, ((geom, ids, method), context) in enumerate(
            zip(groups, context_metrics), 1):
        identifier = f'AC{number:04d}'
        b = buildings.iloc[ids].copy()
        levels = pd.to_numeric(b.get('building:levels', pd.Series(index=b.index, dtype=float)), errors='coerce')
        levels = levels.where((levels > 0) & (levels <= 100))
        coverage = float(levels.notna().mean())
        footprint_area = b.geometry.area
        far = float((footprint_area * levels.fillna(levels.mean())).sum()/geom.area) if coverage >= .66 else None
        local_roads = roads.iloc[road_tree.query(geom, predicate='intersects')].copy()
        block_context = geom.buffer(math.sqrt(geom.area))
        block_roads = roads.iloc[
            road_tree.query(block_context, predicate='intersects')].copy()
        morphology = geometry_metrics(b, local_roads, geom, block_roads)
        metrics = {
            'bcr': float(footprint_area.sum()/geom.area),
            'density': len(b)/geom.area*10000,
            'far': far,
            'attached_building_pct': morphology['attached_building_pct'],
            'building_spacing_median_m':
                morphology['building_spacing_median_m'],
            'road_side_spacing_count':
                morphology['road_side_spacing_count'],
            'sfh_share_known_pct': morphology['sfh_share_known_pct'],
            'mfh_share_known_pct': morphology['mfh_share_known_pct'],
            'residential_typology_requirement_applied':
                morphology['residential_typology_requirement_applied'],
            'continuous_road_frontage_pct':
                morphology['continuous_road_frontage_pct'],
            'row_structure_pct': morphology['row_structure_pct'],
            'block_frontage_structure_pct':
                morphology['block_frontage_structure_pct'],
        }
        unrestricted_scores = range_scores(
            metrics, ranges, common_scales)
        unrestricted_selected, _, _ = assign_type(unrestricted_scores)
        allowed_context_types = CONTEXT_ALLOWED_TYPES[
            context['settlement_context']]
        if method.startswith('additional_scattered_A'):
            allowed_context_types = allowed_context_types & {'A'}
        scores = range_scores(
            metrics, ranges, common_scales,
            allowed_types=allowed_context_types)
        selected, compatible, assignment_reason = assign_type(scores)
        quality = classification_quality(selected['range_score'])
        assigned_type = (
            selected['type'] if quality != 'unclassified'
            else 'UNCLASSIFIED')
        final_assignment_reason = (
            assignment_reason if quality != 'unclassified'
            else 'range_score_above_threshold')
        matches = [score['type'] for score in compatible]
        penalty_names = {
            'bcr': 'bcr',
            'density': 'density',
            'far': 'far',
            'building_spacing_median_m': 'building_spacing',
            'attached_building_pct': 'attachment',
            'row_structure_pct': 'rows',
            'mfh_share_known_pct': 'residential_typology',
        }
        selected_penalties = {
            f'penalty_{penalty_names[key]}': selected['penalties'].get(key)
            for key in penalty_names}
        selected_midpoints = {
            f'midpoint_distance_{penalty_names[key]}':
                selected['midpoint_distances'].get(key)
            for key in penalty_names}
        format_scores = lambda field: '; '.join(
            f"{score['type']}=" +
            ('excluded' if not score['eligible'] else f"{score[field]:.6f}")
            for score in scores)
        format_indicators = lambda values: '; '.join(
            f"{penalty_names[key]}=" +
            ('n.a.' if values.get(key) is None else f"{values[key]:.6f}")
            for key in penalty_names)
        format_requirements = lambda: '; '.join(
            f"{score['type']}[" + ','.join(
                f"{key}=" + (
                    'n.a.' if value is None else
                    ('pass' if value else 'fail'))
                for key, value in score['requirement_results'].items()) + ']'
            for score in scores)
        row = {'district_id': identifier, 'typ': assigned_type,
               'assigned_type': assigned_type,
               'proposed_source_type': selected['type'],
               'assignment_reason': final_assignment_reason,
               'proposed_assignment_reason': assignment_reason,
               'classification_quality': quality,
               'included_in_type_results': quality != 'unclassified',
               'compatible_types': ';'.join(matches),
               'nearest_source_type': scores[0]['type'],
               'unrestricted_assigned_type': unrestricted_selected['type'],
               'context_changed_assignment': (
                   unrestricted_selected['type'] != selected['type']),
               'context_allowed_types': ';'.join(
                   sorted(allowed_context_types)),
               'range_score': selected['range_score'],
               'midpoint_score': selected['midpoint_score'],
               'matching_indicator_count': selected['indicator_count'],
               'eligible_types': ';'.join(
                   score['type'] for score in scores if score['eligible']),
               'block_frontage_requirement_met': (
                   metrics['block_frontage_structure_pct'] is not None and
                   metrics['block_frontage_structure_pct'] >=
                   BLOCK_FRONTAGE_THRESHOLD_PCT),
               'all_type_range_scores': format_scores('range_score'),
               'all_type_midpoint_scores': format_scores('midpoint_score'),
               'all_type_requirement_checks': format_requirements(),
               'indicator_penalties': format_indicators(selected['penalties']),
               'indicator_midpoint_distances': format_indicators(
                   selected['midpoint_distances']),
               **selected_penalties, **selected_midpoints,
               'review_status': 'manual_morphology_review_required',
               'boundary_method': method, 'building_count': len(b), 'area_ha': geom.area/10000,
               **metrics, **context, 'levels_coverage_pct': coverage*100,
               **morphology}
        # Preserve the existing use-classification implementation, but apply the
        # same eligible-building population as the district-size calculation.
        candidate_features = features.iloc[
            feature_tree.query(geom, predicate='intersects')].copy()
        tags = candidate_features.get(
            'building', pd.Series('', index=candidate_features.index)).fillna('').astype(str)
        is_building = ((tags != '') &
                       candidate_features.geometry.geom_type.isin(['Polygon','MultiPolygon']))
        contained_nonbuilding_features = candidate_features[
            ~is_building & candidate_features.geometry.representative_point().within(geom)]
        # Use the exact deduplicated candidate-building records instead of
        # reconstructing them from all intersecting source features. This keeps
        # morphology, membership and use-classification populations identical.
        subset = gpd.GeoDataFrame(
            pd.concat([b, contained_nonbuilding_features], ignore_index=True, sort=False),
            geometry='geometry', crs=features.crs)
        nrb, diagnostics = classify_nrb_buildings(subset)
        use_row = {'district_id': identifier, 'typ': row['typ'],
                   'proposed_source_type': selected['type'],
                   'classification_quality': quality,
                   'included_in_type_results': quality != 'unclassified',
                   'region': 'StädteRegion Aachen',
                   'area_ha': row['area_ha'], 'query_success': True, 'query_error': '', **diagnostics}
        add_use_percentage_columns(use_row, {}, nrb, diagnostics)
        row['unknown_use_pct'] = use_row['unknown_building_percentage_of_all']
        if diagnostics['building_footprint_count'] != len(b):
            raise AssertionError(f'{identifier}: inconsistent building population')
        rows.append(row)
        geoms.append(geom)
        use_rows.append(use_row)
        membership.extend({'district_id': identifier, 'osm_key': key} for key in b.osm_key)
        if number % 50 == 0:
            print(f'Analysed {number}/{len(groups)}', flush=True)
    if not rows:
        raise RuntimeError('No candidates generated.')
    pd.DataFrame(rows).to_csv(out/'candidate_metrics.csv', index=False)
    membership_table = pd.DataFrame(membership)
    membership_table.to_csv(out/'building_membership.csv', index=False)
    write_use_outputs(use_rows, out)
    districts = gpd.GeoDataFrame(rows, geometry=geoms, crs=25832).to_crs(4326)
    districts.geometry = districts.geometry.apply(_normalize_polygonal)
    # Nine decimal degrees retain sub-millimetre coordinate resolution while
    # avoiding numerical self-intersections from excessive decimal precision.
    districts.to_file(
        out/'candidate_districts.geojson', driver='GeoJSON',
        coordinate_precision=9)
    if len(industrial_sites):
        industrial_sites.to_crs(4326).to_file(
            out/'industrial_exclusion_sites.geojson', driver='GeoJSON',
            coordinate_precision=9)
    write_map(
        out, districts, buildings, roads, membership_table,
        industrial_sites=industrial_sites)
    included_use_rows = [
        use_row for use_row in use_rows
        if use_row['included_in_type_results']]
    included_use_frame = pd.DataFrame(included_use_rows)
    summaries = (included_use_frame.groupby('typ')
                 if not included_use_frame.empty else [])
    quality_counts = Counter(row['classification_quality'] for row in rows)
    context_counts = Counter(row['settlement_context'] for row in rows)
    context_changed_count = sum(
        bool(row['context_changed_assignment']) for row in rows)
    report = ['# Aachen OSM discovery pilot', '',
              f'Generated {len(rows)} candidate districts from {len(buildings)} eligible building footprints.', '',
              f'Analysis scope: {analysis_scope}.', '',
              'These are automatically generated candidates awaiting visual review, not validated reference districts.', '',
              '| Proposed source type | Districts | Buildings | Unknown use (%) |',
              '|---|---:|---:|---:|']
    for typ, group in summaries:
        count = int(group.building_footprint_count.sum())
        unknown = int(group.unknown_building_split_count.sum())
        report.append(f'| {typ} | {len(group)} | {count} | {100*unknown/count:.1f} |')
    report += ['', f"Classification quality: exact={quality_counts.get('exact', 0)}, approximate={quality_counts.get('approximate', 0)}, unclassified={quality_counts.get('unclassified', 0)}. Candidates with a selected total range score above {MAXIMUM_ASSIGNED_RANGE_SCORE:g} are retained for review but excluded from type-specific results.", '',
               'All A-I labels retain the spreadsheet definitions. Spatially separated row-dominated and contrasting subareas are both classified by the ordinary rules. Unique compatible matches are retained, overlapping compatible matches use the smallest midpoint score, and candidates outside every range use the smallest range score. General row structure supports both E and F. Residential MFH share enters the score for all types when typology coverage is sufficient; attachment and the remaining numerical indicators also distinguish them. A and B retain their structural frontage requirements. A proposal is assigned only when its total range score is no greater than 1; poorer proposals are marked UNCLASSIFIED. All numerical scores and requirement checks remain exported. All scored indicators use type-independent normalization scales based on the median source-range width. Types H and I are eligible only when the block-frontage requirement is satisfied.', '',
               f"Industrial exclusion: {industrial_exclusion['industrial_site_polygons']} OSM landuse=industrial polygons covering {industrial_exclusion['industrial_exclusion_area_ha']:.1f} ha; {industrial_exclusion['industrial_excluded_buildings']} otherwise eligible buildings were excluded before candidate construction.", '',
               f"Footprint-area exclusion: {industrial_exclusion['small_footprint_excluded_buildings']} building footprints smaller than {MINIMUM_BUILDING_FOOTPRINT_AREA_M2:g} m² were excluded before candidate construction.", '',
               ('Settlement-context restriction: ' +
                ', '.join(f'{key}={context_counts.get(key, 0)}'
                          for key in ('RURAL', 'URBAN')) +
                f'; changed {context_changed_count} assignments compared with unrestricted scoring.'), '',
               'Open review_map.html to inspect boundaries and morphology. Read candidate_metrics.csv for compatible types, boundary methods and missing-storey information.', '',
               'Building-use tables preserve unknowns and report known-use and all-building denominators. More candidates do not remove systematic missing-use bias.', '',
               f'The candidate method is {candidate_method}. Natural components containing {minimum}–{maximum} buildings are retained complete; the target of {target} is used only when an oversized component must be divided or an undersized road block must be merged.', '',
               'The parameter workbook was opened read-only and its hash remained unchanged.', '',
               'Data: © OpenStreetMap contributors, ODbL. https://www.openstreetmap.org/copyright', '']
    (out/'report.md').write_text('\n'.join(report), encoding='utf-8')
    return {'eligible_buildings': len(buildings), 'candidates': len(rows),
            'source_type_proposals': dict(Counter(r['typ'] for r in rows)),
            'nearest_source_type_proposals': dict(Counter(
                r['proposed_source_type'] for r in rows)),
            'classification_quality': dict(quality_counts),
            'included_in_type_results': int(len(included_use_rows)),
            'boundary_methods': dict(Counter(r['boundary_method'] for r in rows)),
            'assignment_reasons': dict(Counter(
                r['assignment_reason'] for r in rows)),
            'settlement_contexts': dict(context_counts),
            'context_changed_assignments': int(context_changed_count),
            'rural_influence_boundaries': int(len(rural_boundary_indices) + len(additional)),
            'additional_scattered_a_candidates': len(additional),
            **industrial_exclusion,
            'classification_common_scales': common_scales,
            'building_count_min': min(r['building_count'] for r in rows),
            'building_count_max': max(r['building_count'] for r in rows)}


def _review_map_layers(districts, buildings, roads, membership,
                       nearby_distance=REVIEW_NEARBY_BUILDING_DISTANCE_M):
    """Prepare exact analytical geometries for visual membership review."""
    projected_districts = districts.to_crs(buildings.crs)
    membership_lookup = dict(zip(
        membership['osm_key'].astype(str),
        membership['district_id'].astype(str)))
    selected_mask = buildings['osm_key'].astype(str).isin(membership_lookup)
    selected = buildings.loc[selected_mask, ['osm_key', 'building', 'geometry']].copy()
    selected['district_id'] = selected['osm_key'].astype(str).map(
        membership_lookup)
    district_type_lookup = dict(zip(
        districts['district_id'].astype(str), districts['typ'].astype(str)))
    selected['typ'] = selected['district_id'].map(district_type_lookup)
    district_quality_lookup = dict(zip(
        districts['district_id'].astype(str),
        districts.get(
            'classification_quality',
            pd.Series('approximate', index=districts.index)).astype(str)))
    selected['classification_quality'] = selected['district_id'].map(
        district_quality_lookup)
    selected['footprint_area_m2'] = selected.geometry.area.round(2)
    selected['membership'] = 'selected'

    expected_counts = membership.groupby('district_id').size().to_dict()
    visible_counts = selected.groupby('district_id').size().to_dict()
    if expected_counts != visible_counts:
        raise AssertionError(
            'Review-map building layer does not reproduce candidate membership.')

    building_tree = shapely.STRtree(buildings.geometry.to_numpy())
    context_buffers = projected_districts.geometry.buffer(
        nearby_distance).to_numpy()
    nearby_pairs = building_tree.query(context_buffers, predicate='intersects')
    nearby_indices = (np.unique(nearby_pairs[1])
                      if nearby_pairs.size else np.asarray([], dtype=int))
    nearby = buildings.iloc[nearby_indices]
    nearby = nearby.loc[
        ~nearby['osm_key'].astype(str).isin(membership_lookup),
        ['osm_key', 'building', 'geometry']].copy()
    nearby['district_id'] = ''
    nearby['typ'] = ''
    nearby['classification_quality'] = ''
    nearby['footprint_area_m2'] = nearby.geometry.area.round(2)
    nearby['membership'] = 'nearby eligible but unassigned'

    grouping_roads = roads.loc[_clustering_road_mask(roads)].copy()
    road_tree = shapely.STRtree(grouping_roads.geometry.to_numpy())
    road_pairs = road_tree.query(context_buffers, predicate='intersects')
    road_indices = (np.unique(road_pairs[1])
                    if road_pairs.size else np.asarray([], dtype=int))
    review_road_columns = [
        column for column in ('highway', 'service', 'geometry')
        if column in grouping_roads.columns]
    review_roads = grouping_roads.iloc[road_indices][
        review_road_columns].copy()

    columns = [
        'osm_key', 'district_id', 'typ', 'classification_quality',
        'membership', 'building', 'footprint_area_m2', 'geometry']
    return (selected[columns].to_crs(4326),
            nearby[columns].to_crs(4326),
            review_roads.to_crs(4326))


def write_map(out, districts, buildings, roads, membership,
              industrial_sites=None):
    import folium
    from branca.element import MacroElement, Template
    selected_buildings, nearby_unassigned, review_roads = _review_map_layers(
        districts, buildings, roads, membership)
    map_districts = districts.copy()
    for source, display in (
            ('all_type_range_scores', 'all_type_range_scores_map'),
            ('all_type_midpoint_scores', 'all_type_midpoint_scores_map')):
        map_districts[display] = map_districts[source].fillna('').astype(
            str).str.replace('; ', '<br>', regex=False)
    # Avoid requesting tiles directly from OpenStreetMap's volunteer-run tile
    # server, which can reject large interactive review maps with HTTP 403.
    m = folium.Map(
        location=[50.75, 6.15],
        zoom_start=10,
        prefer_canvas=True,
        tiles=('https://server.arcgisonline.com/ArcGIS/rest/services/'
               'World_Street_Map/MapServer/tile/{z}/{y}/{x}'),
        attr=('Tiles &copy; Esri; data &copy; OpenStreetMap contributors'),
        name='Esri World Street Map',
    )
    industrial_layer = None
    if industrial_sites is not None and len(industrial_sites):
        industrial_review = industrial_sites[
            ['osm_key', 'landuse', 'excluded_area_ha', 'geometry']
        ].to_crs(4326)
        industrial_layer = folium.GeoJson(
            json.loads(industrial_review.to_json()),
            name='Excluded industrial land-use sites',
            show=True,
            tooltip=folium.GeoJsonTooltip(
                fields=['osm_key', 'excluded_area_ha'],
                aliases=['OSM industrial site:', 'Area (ha):'],
                localize=True),
            popup=folium.GeoJsonPopup(
                fields=['osm_key', 'landuse', 'excluded_area_ha'],
                aliases=['OSM industrial site:', 'Land use:', 'Area (ha):'],
                localize=True, labels=True),
            style_function=lambda _: {
                'color': '#000000', 'weight': 1.5,
                'fillColor': '#000000', 'fillOpacity': 0.32},
        )
        industrial_layer.add_to(m)
    folium.GeoJson(
        json.loads(nearby_unassigned.to_json()),
        name=(f'Nearby eligible but unassigned buildings '
              f'(within {REVIEW_NEARBY_BUILDING_DISTANCE_M:g} m)'),
        show=False,
        tooltip=folium.GeoJsonTooltip(
            fields=['osm_key', 'footprint_area_m2'],
            aliases=['OSM building:', 'Footprint area (m²):']),
        popup=folium.GeoJsonPopup(
            fields=['osm_key', 'membership', 'building',
                    'footprint_area_m2'],
            aliases=['OSM building:', 'Membership:', 'Building tag:',
                     'Footprint area (m²):'],
            localize=True, labels=True),
        style_function=lambda _: {
            'color': '#666666', 'weight': 1,
            'fillColor': '#bdbdbd', 'fillOpacity': 0.35},
    ).add_to(m)
    folium.GeoJson(
        json.loads(review_roads.to_json()),
        name='Roads retained for clustering',
        show=False,
        tooltip=folium.GeoJsonTooltip(
            fields=['highway'], aliases=['Road type:']),
        style_function=lambda _: {
            'color': '#424242', 'weight': 1.5, 'opacity': 0.75},
    ).add_to(m)
    assigned_building_layer = folium.GeoJson(
        json.loads(selected_buildings.to_json()),
        name='Assigned OSM building footprints',
        show=True,
        tooltip=folium.GeoJsonTooltip(
            fields=['district_id', 'osm_key', 'footprint_area_m2'],
            aliases=['District:', 'OSM building:', 'Footprint area (m²):']),
        popup=folium.GeoJsonPopup(
            fields=['district_id', 'osm_key', 'membership', 'building',
                    'footprint_area_m2'],
            aliases=['District:', 'OSM building:', 'Membership:',
                     'Building tag:', 'Footprint area (m²):'],
            localize=True, labels=True),
        style_function=lambda f: {
            'color': {'exact': '#006d2c',
                      'approximate': '#084594',
                      'unclassified': '#99000d'}.get(
                          f['properties']['classification_quality'],
                          '#555555'),
            'fillColor': {'exact': '#41ab5d',
                          'approximate': '#4292c6',
                          'unclassified': '#ef3b2c'}.get(
                              f['properties']['classification_quality'],
                              '#969696'),
            'weight': 1, 'fillOpacity': 0.65},
    )
    assigned_building_layer.add_to(m)
    district_layer = folium.GeoJson(
        json.loads(map_districts.to_json()), name='Candidate districts',
        tooltip=folium.GeoJsonTooltip(
            fields=['district_id', 'building_count', 'typ',
                    'classification_quality',
                    'settlement_context', 'context_changed_assignment',
                    'assignment_reason', 'range_score', 'midpoint_score'],
            aliases=['District:', 'Buildings:', 'Assigned type:',
                     'Classification quality:',
                     'Settlement context:', 'Context changed type:',
                     'Assignment reason:', 'Total range score:',
                     'Total midpoint score:']),
        popup=folium.GeoJsonPopup(
            fields=['district_id', 'typ', 'classification_quality',
                    'assignment_reason',
                    'settlement_context',
                    'compatible_types', 'nearest_source_type',
                    'range_score', 'midpoint_score',
                    'matching_indicator_count', 'eligible_types',
                    'all_type_range_scores_map',
                    'all_type_midpoint_scores_map'],
            aliases=['District:', 'Assigned type:',
                     'Classification quality:', 'Assignment reason:',
                     'Settlement context:',
                     'Compatible types:', 'Nearest range type:',
                     'Total range score:', 'Total midpoint score:',
                     'Indicators used:', 'Eligible types:',
                     'All type range scores:', 'All type midpoint scores:'],
            localize=True, labels=True),
        style_function=lambda f: {
            'color': {'exact': '#238b45',
                      'approximate': '#2171b5',
                      'unclassified': '#cb181d'}.get(
                          f['properties']['classification_quality'],
                          '#555555'),
            'fillColor': {'exact': '#41ab5d',
                          'approximate': '#4292c6',
                          'unclassified': '#ef3b2c'}.get(
                              f['properties']['classification_quality'],
                              '#969696'),
            'weight': 2, 'fillOpacity': .20})
    district_layer.add_to(m)

    type_filter = MacroElement()
    type_filter._name = 'SettlementTypeFilter'
    type_filter.types = sorted(
        districts['typ'].dropna().astype(str).unique().tolist())
    type_filter.types_json = json.dumps(type_filter.types)
    type_filter.qualities = ['exact', 'approximate', 'unclassified']
    type_filter.qualities_json = json.dumps(type_filter.qualities)
    type_filter.map_name = m.get_name()
    type_filter.district_layer_name = district_layer.get_name()
    type_filter.building_layer_name = assigned_building_layer.get_name()
    type_filter.has_industrial = industrial_layer is not None
    type_filter.industrial_layer_name = (
        industrial_layer.get_name() if industrial_layer is not None else '')
    type_filter._template = Template(r"""
        {% macro html(this, kwargs) %}
        <div id="{{ this.get_name() }}" class="leaflet-bar dg-type-filter">
          <div class="dg-type-title">Map legend and filters</div>
          <div class="dg-filter-label">Settlement types</div>
          <div class="dg-type-buttons">
          {% for typ in this.types %}
            <button type="button" class="dg-type-button active"
                    data-type="{{ typ }}">{{ typ }}</button>
          {% endfor %}
          </div>
          <div class="dg-filter-label">Classification quality</div>
          <div class="dg-quality-buttons">
            <button type="button" class="dg-quality-button dg-exact active"
                    data-quality="exact"><span></span>Exact: score = 0</button>
            <button type="button" class="dg-quality-button dg-approximate active"
                    data-quality="approximate"><span></span>Approximate: 0–1</button>
            <button type="button" class="dg-quality-button dg-unclassified active"
                    data-quality="unclassified"><span></span>Unclassified: &gt; 1</button>
          </div>
          {% if this.has_industrial %}
          <div class="dg-filter-label">Excluded land</div>
          <button type="button" class="dg-industrial-button active"
                  data-industrial="toggle"><span></span>Industrial area — OSM landuse=industrial</button>
          {% endif %}
          <div class="dg-type-actions">
            <button type="button" data-action="all">All</button>
            <button type="button" data-action="none">None</button>
          </div>
          <div class="dg-type-count"></div>
        </div>
        <style>
          .dg-type-filter {
            position: absolute; top: 10px; left: 50px; z-index: 1000;
            background: white; padding: 8px; border-radius: 4px;
            box-shadow: 0 1px 5px rgba(0,0,0,.45);
            font: 13px/1.25 Arial, sans-serif;
          }
          .dg-type-title { font-weight: bold; margin-bottom: 6px; }
          .dg-filter-label { font-weight: bold; margin: 7px 0 4px; }
          .dg-type-buttons { display: flex; gap: 3px; flex-wrap: wrap; }
          .dg-quality-buttons { display: grid; gap: 3px; }
          .dg-type-filter button {
            min-width: 27px; padding: 3px 6px; border: 1px solid #777;
            border-radius: 3px; background: #f1f1f1; cursor: pointer;
          }
          .dg-type-filter button.active {
            color: white; background: #286090; border-color: #204d74;
          }
          .dg-quality-button, .dg-industrial-button {
            display: flex; align-items: center; gap: 6px; text-align: left;
          }
          .dg-quality-button span, .dg-industrial-button span {
            display: inline-block; width: 14px; height: 11px;
            border: 2px solid; box-sizing: border-box; flex: 0 0 auto;
          }
          .dg-exact span { border-color: #238b45; background: #41ab5d; }
          .dg-approximate span { border-color: #2171b5; background: #4292c6; }
          .dg-unclassified span { border-color: #cb181d; background: #ef3b2c; }
          .dg-industrial-button span { border-color: #000; background: #000; }
          .dg-quality-button.active, .dg-industrial-button.active {
            color: #111 !important; background: #e8e8e8 !important;
            border-color: #555 !important;
          }
          .dg-quality-button:not(.active), .dg-industrial-button:not(.active) {
            opacity: .45;
          }
          .dg-type-actions { display: flex; gap: 4px; margin-top: 6px; }
          .dg-type-actions button { flex: 1; }
          .dg-type-count { margin-top: 5px; color: #444; }
        </style>
        {% endmacro %}
        {% macro script(this, kwargs) %}
        (function() {
          const map = {{ this.map_name }};
          const districtGroup = {{ this.district_layer_name }};
          const buildingGroup = {{ this.building_layer_name }};
          const allTypes = {{ this.types_json | safe }};
          const allQualities = {{ this.qualities_json | safe }};
          const activeTypes = new Set(allTypes);
          const activeQualities = new Set(allQualities);
          const industrialGroup = {% if this.has_industrial %}
            {{ this.industrial_layer_name }}{% else %}null{% endif %};
          const districtFeatures = [];
          const buildingFeatures = [];
          districtGroup.eachLayer(layer => districtFeatures.push(layer));
          buildingGroup.eachLayer(layer => buildingFeatures.push(layer));
          const control = document.getElementById('{{ this.get_name() }}');
          L.DomEvent.disableClickPropagation(control);
          L.DomEvent.disableScrollPropagation(control);

          function applyToGroup(group, features) {
            features.forEach(layer => {
              const typ = String(layer.feature.properties.typ || '');
              const quality = String(
                layer.feature.properties.classification_quality || '');
              const visible = activeTypes.has(typ) &&
                activeQualities.has(quality);
              if (visible && !group.hasLayer(layer)) group.addLayer(layer);
              if (!visible && group.hasLayer(layer)) group.removeLayer(layer);
            });
          }

          function update() {
            applyToGroup(districtGroup, districtFeatures);
            applyToGroup(buildingGroup, buildingFeatures);
            control.querySelectorAll('[data-type]').forEach(button => {
              button.classList.toggle(
                'active', activeTypes.has(button.dataset.type));
            });
            control.querySelectorAll('[data-quality]').forEach(button => {
              button.classList.toggle(
                'active', activeQualities.has(button.dataset.quality));
            });
            const visible = districtFeatures.filter(layer =>
              activeTypes.has(String(layer.feature.properties.typ || '')) &&
              activeQualities.has(String(
                layer.feature.properties.classification_quality || ''))
            ).length;
            control.querySelector('.dg-type-count').textContent =
              'Visible districts: ' + visible + ' / ' + districtFeatures.length;
          }

          control.querySelectorAll('[data-type]').forEach(button => {
            button.addEventListener('click', function() {
              const typ = this.dataset.type;
              if (activeTypes.size === allTypes.length) {
                activeTypes.clear();
                activeTypes.add(typ);
              } else if (activeTypes.has(typ)) {
                activeTypes.delete(typ);
              } else {
                activeTypes.add(typ);
              }
              update();
            });
          });
          control.querySelectorAll('[data-quality]').forEach(button => {
            button.addEventListener('click', function() {
              const quality = this.dataset.quality;
              if (activeQualities.size === allQualities.length) {
                activeQualities.clear();
                activeQualities.add(quality);
              } else if (activeQualities.has(quality)) {
                activeQualities.delete(quality);
              } else {
                activeQualities.add(quality);
              }
              update();
            });
          });
          control.querySelector('[data-action="all"]').addEventListener(
            'click', function() {
              activeTypes.clear();
              allTypes.forEach(typ => activeTypes.add(typ));
              activeQualities.clear();
              allQualities.forEach(quality => activeQualities.add(quality));
              update();
            });
          control.querySelector('[data-action="none"]').addEventListener(
            'click', function() {
              activeTypes.clear();
              activeQualities.clear();
              update();
            });
          {% if this.has_industrial %}
          const industrialButton = control.querySelector('[data-industrial]');
          function syncIndustrialButton() {
            industrialButton.classList.toggle(
              'active', map.hasLayer(industrialGroup));
          }
          industrialButton.addEventListener('click', function() {
            if (map.hasLayer(industrialGroup)) {
              map.removeLayer(industrialGroup);
            } else {
              map.addLayer(industrialGroup);
            }
            syncIndustrialButton();
          });
          map.on('overlayadd', function(event) {
            if (event.layer === industrialGroup) syncIndustrialButton();
          });
          map.on('overlayremove', function(event) {
            if (event.layer === industrialGroup) syncIndustrialButton();
          });
          syncIndustrialButton();
          {% endif %}
          update();
        })();
        {% endmacro %}
    """)
    m.add_child(type_filter)
    min_lon, min_lat, max_lon, max_lat = districts.total_bounds
    m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])
    folium.LayerControl().add_to(m)
    m.save(str(out/'review_map.html'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--target-buildings', type=int, default=40)
    parser.add_argument('--min-buildings', type=int, default=10)
    parser.add_argument('--max-buildings', type=int, default=70)
    parser.add_argument('--candidate-method', choices=['hybrid', 'street_clusters', 'road_blocks'],
                        default='hybrid')
    parser.add_argument(
        '--scope', choices=['ask', 'quick', 'full'], default='ask',
        help=('Analysis extent. The default asks interactively; use quick or '
              'full to bypass the question.'))
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument(
        '--output', type=Path,
        default=None,
        help='Output directory; defaults to a separate directory per scope.')
    parser.add_argument('--source-cache', type=Path,
                        default=ROOT/'examples/results/aachen_osm_pilot_v2',
                        help='Directory containing boundary.geojson and osm_features_slim.pkl.')
    parser.add_argument('--parameters', type=Path, default=ROOT/'districtgenerator/data/typdistrict_parameters.xlsx')
    args = parser.parse_args()
    if not args.min_buildings <= args.target_buildings <= args.max_buildings:
        raise ValueError('Expected min-buildings <= target-buildings <= max-buildings.')
    args.scope = choose_analysis_scope(args.scope)
    if args.output is None:
        output_name = ('aachen_osm_building_sections_compact_v7_quick'
                       if args.scope == 'quick'
                       else 'aachen_osm_building_sections_compact_v7')
        args.output = ROOT / 'examples/results' / output_name
    args.output.mkdir(parents=True, exist_ok=True)
    before = sha(args.parameters)
    ranges = load_ranges(args.parameters)
    (args.output/'morphological_ranges.json').write_text(json.dumps(ranges, indent=2, ensure_ascii=False), encoding='utf-8')
    try:
        if args.download:
            source_dir = args.source_cache
            boundary, features = download(source_dir, refresh=True)
        else:
            source_dir = args.source_cache or args.output
            boundary = gpd.read_file(source_dir/'boundary.geojson')
            try:
                features = pd.read_pickle(source_dir/'osm_features_slim.pkl')
            except Exception as exc:
                raise RuntimeError(
                    'The saved Aachen OSM cache is incompatible with the '
                    'active pandas/NumPy environment. Run '
                    'examples/refresh_aachen_osm_data.py once, then run '
                    'aachen_osm_pilot.py again.') from exc
        service_subtype_available = 'service' in features.columns
        if not service_subtype_available:
            print(
                'Source cache has no OSM service subtype column; service '
                'roads remain excluded from clustering until the source '
                'cache is refreshed.', flush=True)
        boundary, features, scope_metadata = apply_analysis_scope(
            boundary, features, args.scope)
        print(
            f"Analysis scope: {scope_metadata['analysis_scope']} "
            f"({len(features)} source features)", flush=True)
        result = analyse(args.output, boundary, features, ranges, args.target_buildings, args.seed,
                         minimum=args.min_buildings, maximum=args.max_buildings,
                         candidate_method=args.candidate_method,
                         analysis_scope=scope_metadata['analysis_scope'])
        manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'parameters_sha256': before,
                    'parameters_unchanged': sha(args.parameters)==before,
                    'source_feature_cache_sha256': sha(source_dir/'osm_features_slim.pkl'),
                    'script_sha256': sha(Path(__file__)),
                    'use_classifier': 'embedded_in_aachen_osm_pilot',
                    'seed':args.seed,
                    'target_buildings':args.target_buildings,
                    'minimum_buildings':args.min_buildings,
                    'maximum_buildings':args.max_buildings,
                    'candidate_method':args.candidate_method,
                    'source_service_subtype_available':
                        service_subtype_available,
                    **scope_metadata,
                    'classification_settings': {
                        'scored_indicators': [
                            'bcr', 'density', 'far',
                            'building_spacing_median_m',
                            'attached_building_pct',
                            'row_structure_pct', 'mfh_share_known_pct'],
                        'normalization': 'median_source_interval_width',
                        'midpoint_normalization': 'same_common_indicator_scale',
                        'maximum_assigned_range_score':
                            MAXIMUM_ASSIGNED_RANGE_SCORE,
                        'classification_quality_categories': {
                            'exact': 'range_score_equal_to_0',
                            'approximate': 'range_score_above_0_to_1_inclusive',
                            'unclassified': 'range_score_above_1'},
                        'unclassified_result_role':
                            'retain_for_review_exclude_from_type_aggregates',
                        'block_frontage_role': 'eligibility_requirement',
                        'block_frontage_required_types': sorted(
                            BLOCK_FRONTAGE_TYPES),
                        'block_frontage_minimum_coverage_pct':
                            BLOCK_FRONTAGE_THRESHOLD_PCT,
                        'block_frontage_maximum_continuous_gap_pct':
                            MAXIMUM_BLOCK_FRONTAGE_GAP_PCT,
                        'a_b_frontage_continuity_role':
                            'eligibility_requirement',
                        'a_maximum_continuous_frontage_pct':
                            AB_FRONTAGE_CONTINUITY_THRESHOLD_PCT,
                        'a_maximum_attached_building_pct':
                            A_ATTACHED_BUILDING_THRESHOLD_PCT,
                        'b_minimum_continuous_frontage_pct':
                            AB_FRONTAGE_CONTINUITY_THRESHOLD_PCT,
                        'b_maximum_attached_building_pct':
                            ATTACHED_BUILDING_THRESHOLD_PCT,
                        'a_positive_evidence_requirements': [
                            'low_continuous_frontage',
                            'row_structure_below_threshold'],
                        'b_positive_evidence_requirements': [
                            'continuous_frontage'],
                        'a_b_spacing_attachment_role': 'scored_only',
                        'b_c_exact_overlap_rule':
                            'ordinary_midpoint_score',
                        'residential_typology_role':
                            'coverage_conditional_scored_indicator_all_types',
                        'residential_typology_score_tolerance_pp':
                            RESIDENTIAL_TYPOLOGY_SCORE_TOLERANCE_PP,
                        'sfh_like_building_tags': sorted(
                            SFH_LIKE_BUILDING_TAGS),
                        'mfh_like_building_tags': sorted(
                            MFH_LIKE_BUILDING_TAGS),
                        'ambiguous_residential_building_tags': sorted(
                            AMBIGUOUS_RESIDENTIAL_BUILDING_TAGS),
                        'residential_typology_evidence_precedence': [
                            'building:flats',
                            'building:use',
                            'building',
                            'ambiguous_residential_footprint_area'],
                        'building_flats_sfh_value': 1,
                        'building_flats_mfh_minimum': 2,
                        'aggregate_terrace_footprint_count_exported': True,
                        'sfh_required_types': [],
                        'mfh_required_types': [],
                        'residential_typology_dominance_threshold_pct':
                            RESIDENTIAL_TYPOLOGY_DOMINANCE_THRESHOLD_PCT,
                        'residential_typology_minimum_coverage_pct':
                            RESIDENTIAL_TYPOLOGY_MINIMUM_COVERAGE_PCT,
                        'inferred_sfh_maximum_footprint_area_m2':
                            INFERRED_SFH_MAXIMUM_FOOTPRINT_AREA_M2,
                        'inferred_mfh_minimum_footprint_area_m2':
                            INFERRED_MFH_MINIMUM_FOOTPRINT_AREA_M2,
                        'row_structure_indicator_role':
                            'shared_scored_indicator_for_E_and_F',
                        'morphology_row_split_assignment':
                            'ordinary_type_classification',
                        'settlement_context_role':
                            'direct_type_eligibility_restriction',
                        'settlement_context_buffer_m':
                            SETTLEMENT_CONTEXT_BUFFER_M,
                        'rural_context_maximum_density_buildings_per_ha':
                            RURAL_CONTEXT_MAXIMUM_DENSITY,
                        'rural_context_maximum_bcr':
                            RURAL_CONTEXT_MAXIMUM_BCR,
                        'rural_context_role':
                            'eligibility_for_building_influence_boundary',
                        'urban_context_combined_minimum_density_buildings_per_ha':
                            URBAN_CONTEXT_COMBINED_MINIMUM_DENSITY,
                        'urban_context_combined_minimum_bcr':
                            URBAN_CONTEXT_COMBINED_MINIMUM_BCR,
                        'urban_context_minimum_density_buildings_per_ha':
                            URBAN_CONTEXT_MINIMUM_DENSITY,
                        'urban_context_minimum_bcr':
                            URBAN_CONTEXT_MINIMUM_BCR,
                        'context_allowed_types': {
                            key: sorted(value)
                            for key, value in CONTEXT_ALLOWED_TYPES.items()},
                        'e_f_row_structure_minimum_coverage_pct':
                            ROW_STRUCTURE_THRESHOLD_PCT,
                        'a_row_structure_excluded_at_or_above_pct':
                            ROW_STRUCTURE_THRESHOLD_PCT,
                        'other_type_row_structure_maximum_coverage_pct':
                            ROW_STRUCTURE_THRESHOLD_PCT,
                    },
                    'review_map_settings': {
                        'assigned_building_geometry':
                            'exact_analytical_footprints',
                        'assigned_buildings_visible_by_default': True,
                        'nearby_unassigned_building_geometry':
                            'exact_analytical_footprints',
                        'nearby_unassigned_distance_m':
                            REVIEW_NEARBY_BUILDING_DISTANCE_M,
                        'clustering_roads_available_as_layer': True,
                        'industrial_exclusion_layer_available': True,
                        'industrial_exclusion_layer_visible_by_default': True,
                        'industrial_exclusion_legend':
                            'black_polygon_OSM_landuse_industrial',
                        'settlement_type_filter':
                            'multi_select_A_to_I_and_UNCLASSIFIED',
                        'settlement_type_filter_applies_to': [
                            'candidate_districts',
                            'assigned_building_footprints'],
                        'classification_quality_filter':
                            'clickable_exact_approximate_unclassified',
                        'classification_quality_colors': {
                            'exact': 'green',
                            'approximate': 'blue',
                            'unclassified': 'red'},
                        'industrial_layer_filter': 'clickable_black_legend_item',
                        'background_map_role': 'context_only',
                    },
                    'additional_scattered_a_settings': {
                        'enabled': True,
                        'population': 'unassigned_buildings_only',
                        'existing_candidates': 'fixed_membership_geometry_and_assignment',
                        'connections': 'nearest_occupied_stations_along_retained_roads',
                        'assigned_stations': 'barriers',
                        'maximum_building_to_road_distance_m': 150.0,
                        'local_gap_neighbourhood_hops': 2,
                        'gap_rule': 'Q3_plus_3_IQR_or_3_times_median',
                        'gap_must_pass_both_endpoints': True,
                        'minimum_buildings': args.min_buildings,
                        'maximum_buildings': args.max_buildings,
                        'oversized_groups': 'split_longest_road_distance_MST_edge',
                        'acceptance': 'existing_A_requirements_and_range_score_at_most_1',
                    },
                    'candidate_generation_settings': ({
                        'road_block_priority': args.candidate_method == 'hybrid',
                        'candidate_membership_principle':
                            'natural_components_before_building_count',
                        'industrial_site_exclusion':
                            'OSM_landuse_industrial_polygon_mask',
                        'minimum_building_footprint_area_m2':
                            MINIMUM_BUILDING_FOOTPRINT_AREA_M2,
                        'industrial_building_exclusion_rule':
                            'exclude_if_footprint_intersects_mask',
                        'industrial_road_exclusion_rule':
                            'subtract_mask_before_clustering',
                        'industrial_boundary_exclusion_rule':
                            'clip_all_candidate_envelopes_to_masked_study_area',
                        'target_building_role':
                            'preference_for_required_split_or_merge_only',
                        'natural_component_minimum_buildings':
                            args.min_buildings,
                        'natural_component_maximum_buildings':
                            args.max_buildings,
                        'oversized_component_partition':
                            'connected_growth_near_target_after_natural_gap_detection',
                        'road_block_remote_group_pruning':
                            'candidate_specific_exceptional_gap_components',
                        'maximum_remote_block_group_buildings':
                            max(1, math.ceil(args.target_buildings / 10)),
                        'minimum_block_core_buildings_after_pruning':
                            args.min_buildings,
                        'maximum_road_block_area_m2': 4000000.0,
                        'road_section_method': 'midpoints_between_projected_building_positions',
                        'clustering_service_road_rule':
                            'include_except_driveway_parking_aisle_drive-through',
                        'pedestrian_road_clustering_rule': 'exclude',
                        'projected_position_precision_m': 0.1,
                        'maximum_buildings_per_street_section': max(1, math.ceil(args.target_buildings / 10)),
                        'exceptional_building_gap_rule': 'q3_plus_3_iqr',
                        'minimum_gaps_for_exceptional_gap_rule': 5,
                        'zero_iqr_gap_fallback': 'three_times_median',
                        'street_growth_priority': 'minimum_added_road_length_per_new_building',
                        'terminal_branch_pruning': 'exceptional_gap_small_leaf',
                        'maximum_terminal_branch_buildings': max(1, math.ceil(args.target_buildings / 10)),
                        'minimum_core_buildings_after_pruning': args.min_buildings,
                        'maximum_building_to_road_distance_m': 150.0,
                        'minimum_concave_hull_ratio': 0.30,
                        'adaptive_hull_compact_spacing_m':
                            COMPACT_HULL_SPACING_M,
                        'adaptive_hull_convex_spacing_m':
                            SPARSE_HULL_SPACING_M,
                        'membership_envelope_geometry': 'interior_representative_points',
                        'final_envelope_geometry': 'complete_member_footprints',
                        'clearly_rural_final_boundary_geometry':
                            'locally_capped_union_of_member_building_voronoi_influence_cells',
                        'rural_influence_boundary_limits': [
                            'midpoint_to_all_eligible_unselected_building_points',
                            'adaptive_footprint_hull_buffered_by_local_spacing_reach',
                            'industrial_exclusion_mask',
                            'study_boundary'],
                        'rural_local_spacing_reach_rule':
                            'q3_plus_1.5_iqr_nearest_member_point_distances',
                        'rural_local_spacing_zero_iqr_fallback':
                            '1.5_times_median_nearest_member_point_distance',
                        'minimum_envelope_margin_m': 5.0,
                        'maximum_envelope_margin_m': 30.0,
                        'external_footprint_margin_constraint': 'half_clear_gap_midpoint',
                        'empty_enclosed_area_rule': 'fill_if_no_external_footprint_intersects',
                        'empty_boundary_bay_rule':
                            'adaptive_building_spacing_morphological_closing',
                        'boundary_bay_radius_spacing_factor':
                            BOUNDARY_BAY_RADIUS_SPACING_FACTOR,
                        'boundary_bay_external_footprint_rule':
                            'absorb_unassigned_reject_assigned_or_excluded',
                        'maximum_membership_closure_iterations': 10,
                        'final_spatial_coherence_method':
                            'building_representative_point_minimum_spanning_tree',
                        'final_spatial_bridge_rule': 'q3_plus_3_iqr',
                        'final_spatial_zero_iqr_fallback':
                            'three_times_median_mst_edge',
                        'final_spatial_component_policy':
                            'retain_each_component_meeting_building_limits_otherwise_reject',
                        'geojson_coordinate_precision_decimals': 9,
                        'building_spacing_metric':
                            'same_road_side_median_with_nearest_neighbour_fallback',
                        'building_spacing_fallback':
                            'median_nearest_building_centroid_distance',
                        'building_spacing_maximum_road_assignment_distance_m': 150.0,
                        'building_spacing_matching_status': 'active_with_workbook_minimum_and_maximum',
                        'continuous_frontage_method':
                            'same_road_side_runs',
                        'continuous_frontage_maximum_gap_m':
                            AB_FRONTAGE_MAXIMUM_GAP_M,
                        'continuous_frontage_minimum_run_buildings':
                            AB_FRONTAGE_MINIMUM_RUN_BUILDINGS,
                        'row_angle_step_deg': ROW_ANGLE_STEP_DEG,
                        'row_band_tolerance_m': ROW_BAND_TOLERANCE_M,
                        'row_maximum_along_gap_m':
                            ROW_MAXIMUM_ALONG_GAP_M,
                        'row_minimum_buildings_per_row':
                            ROW_MINIMUM_BUILDINGS,
                        'row_minimum_rows': ROW_MINIMUM_ROWS,
                        'row_minimum_overlap_fraction':
                            ROW_MINIMUM_OVERLAP_FRACTION,
                        'row_to_road_angle_role':
                            'descriptive_only_not_a_qualification_rule',
                        'row_morphology_split_role':
                            'separate_spatially_distinct_row_and_nonrow_subareas',
                        'row_morphology_split_minimum_accuracy':
                            MORPHOLOGY_SPLIT_MINIMUM_ACCURACY,
                        'row_morphology_split_minimum_row_share_difference':
                            MORPHOLOGY_SPLIT_MINIMUM_ROW_SHARE_DIFFERENCE,
                        'row_morphology_split_gap_rule': 'q3_plus_1.5_iqr',
                        'row_morphology_split_minimum_buildings_per_part':
                            args.min_buildings,
                        'block_frontage_method': 'cyclic_projected_footprint_intervals',
                        'block_frontage_maximum_building_distance_m': MAXIMUM_BLOCK_FRONTAGE_DISTANCE_M,
                        'block_frontage_minimum_coverage_pct': BLOCK_FRONTAGE_THRESHOLD_PCT,
                        'block_frontage_maximum_continuous_gap_pct': MAXIMUM_BLOCK_FRONTAGE_GAP_PCT,
                    } if args.candidate_method in {'hybrid', 'street_clusters'} else {
                        'road_block_priority': True,
                        'industrial_site_exclusion':
                            'OSM_landuse_industrial_polygon_mask',
                        'minimum_building_footprint_area_m2':
                            MINIMUM_BUILDING_FOOTPRINT_AREA_M2,
                        'industrial_building_exclusion_rule':
                            'exclude_if_footprint_intersects_mask',
                        'industrial_road_exclusion_rule':
                            'subtract_mask_before_clustering',
                        'industrial_boundary_exclusion_rule':
                            'clip_all_candidate_envelopes_to_masked_study_area',
                        'maximum_road_block_area_m2': 4000000.0,
                        'concave_hull_ratio': 0.30,
                        'membership_envelope_geometry': 'interior_representative_points',
                        'final_envelope_geometry': 'complete_member_footprints',
                        'clearly_rural_final_boundary_geometry':
                            'locally_capped_union_of_member_building_voronoi_influence_cells',
                        'rural_influence_boundary_limits': [
                            'midpoint_to_all_eligible_unselected_building_points',
                            'adaptive_footprint_hull_buffered_by_local_spacing_reach',
                            'industrial_exclusion_mask',
                            'study_boundary'],
                        'rural_local_spacing_reach_rule':
                            'q3_plus_1.5_iqr_nearest_member_point_distances',
                        'rural_local_spacing_zero_iqr_fallback':
                            '1.5_times_median_nearest_member_point_distance',
                        'minimum_envelope_margin_m': 5.0,
                        'maximum_envelope_margin_m': 30.0,
                        'external_footprint_margin_constraint': 'half_clear_gap_midpoint',
                        'empty_enclosed_area_rule': 'fill_if_no_external_footprint_intersects',
                        'empty_boundary_bay_rule':
                            'adaptive_building_spacing_morphological_closing',
                        'boundary_bay_radius_spacing_factor':
                            BOUNDARY_BAY_RADIUS_SPACING_FACTOR,
                        'boundary_bay_external_footprint_rule':
                            'absorb_unassigned_reject_assigned_or_excluded',
                        'maximum_membership_closure_iterations': 10,
                        'geojson_coordinate_precision_decimals': 9,
                        'building_spacing_metric': 'median_longitudinal_centroid_spacing_on_same_noded_road_side',
                        'building_spacing_maximum_road_assignment_distance_m': 150.0,
                        'building_spacing_matching_status': 'active_with_workbook_minimum_and_maximum',
                        'block_frontage_method': 'cyclic_projected_footprint_intervals',
                        'block_frontage_maximum_building_distance_m': MAXIMUM_BLOCK_FRONTAGE_DISTANCE_M,
                        'block_frontage_minimum_coverage_pct': BLOCK_FRONTAGE_THRESHOLD_PCT,
                        'block_frontage_maximum_continuous_gap_pct': MAXIMUM_BLOCK_FRONTAGE_GAP_PCT,
                    }),
                    'packages': {name:importlib.metadata.version(name) for name in ['osmnx','geopandas','shapely','scipy','pyproj','openpyxl','folium']},
                    **result}
        (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        from update_aachen_documentation_results import update_documentation_results
        from render_aachen_documentation import render as render_documentation
        documentation_path = update_documentation_results(args.output)
        html_path = render_documentation()
        print(f'Updated documentation results: {documentation_path}', flush=True)
        print(f'Updated documentation HTML: {html_path}', flush=True)
        print(json.dumps(manifest, indent=2), flush=True)
    finally:
        if sha(args.parameters) != before:
            raise RuntimeError('Parameter workbook changed during pilot.')


if __name__ == '__main__':
    main()
