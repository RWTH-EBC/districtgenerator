import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('pilot', Path(__file__).resolve().parents[1]/'examples/aachen_osm_pilot.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
from shapely.geometry import box, LineString, Polygon


class PilotTests(unittest.TestCase):
    def test_selective_service_roads_enter_clustering_graph(self):
        roads = p.gpd.GeoDataFrame(
            {
                'highway': [
                    'residential', 'service', 'service', 'service',
                    'service', 'pedestrian'],
                'service': [
                    None, None, 'driveway', 'parking_aisle',
                    'drive-through', None],
            },
            geometry=[LineString([(0, y), (10, y)]) for y in range(6)],
            crs=25832)
        retained = roads.loc[p._clustering_road_mask(roads)]
        self.assertEqual(retained.index.tolist(), [0, 1])
        self.assertIn('service', p.OSM_COLUMNS)

    def test_legacy_cache_excludes_service_roads_without_subtype_column(self):
        roads = p.gpd.GeoDataFrame(
            {'highway': ['residential', 'service']},
            geometry=[LineString([(0, 0), (10, 0)]),
                      LineString([(0, 1), (10, 1)])],
            crs=25832)
        retained = roads.loc[p._clustering_road_mask(roads)]
        self.assertEqual(retained.index.tolist(), [0])

    def test_residential_typology_combines_explicit_and_area_inference(self):
        buildings = p.gpd.GeoDataFrame(
            {'building': [
                'house', 'detached', 'semidetached_house', 'terrace',
                'apartments', 'yes', 'residential', 'residential',
                'residential', 'school']},
            geometry=[
                box(0, 0, 10, 8), box(20, 0, 30, 8),
                box(40, 0, 50, 8), box(60, 0, 70, 8),
                box(80, 0, 95, 10), box(100, 0, 110, 8),
                box(120, 0, 130, 10),   # 100 m²: inferred SFH
                box(140, 0, 155, 10),   # 150 m²: remains unknown
                box(170, 0, 195, 10),   # 250 m²: inferred MFH
                box(210, 0, 220, 8)],
            crs=25832)
        result = p._residential_typology_metrics(buildings)
        self.assertEqual(result['sfh_like_count'], 5)
        self.assertEqual(result['mfh_like_count'], 2)
        self.assertEqual(result['explicit_sfh_like_count'], 4)
        self.assertEqual(result['explicit_mfh_like_count'], 1)
        self.assertEqual(result['inferred_sfh_like_count'], 1)
        self.assertEqual(result['inferred_mfh_like_count'], 1)
        self.assertEqual(
            result['residential_building_count_for_typology'], 8)
        self.assertEqual(result['unknown_residential_typology_count'], 1)
        self.assertAlmostEqual(
            result['residential_typology_coverage_pct'], 100 * 7 / 8)
        self.assertAlmostEqual(result['sfh_share_known_pct'], 100 * 5 / 7)
        self.assertTrue(result['residential_typology_requirement_applied'])

    def test_residential_typology_requires_coverage_but_no_minimum_count(self):
        buildings = p.gpd.GeoDataFrame(
            {'building': [
                'house', 'apartments',
                'residential', 'residential', 'residential', 'residential',
                'residential', 'residential', 'residential', 'residential']},
            geometry=[box(20 * i, 0, 20 * i + 15, 10)
                      for i in range(10)],
            crs=25832)
        result = p._residential_typology_metrics(buildings)
        self.assertEqual(result['known_residential_typology_count'], 2)
        self.assertEqual(result['residential_typology_coverage_pct'], 20.0)
        self.assertTrue(result['residential_typology_requirement_applied'])

    def test_residential_typology_area_boundaries_remain_unknown(self):
        buildings = p.gpd.GeoDataFrame(
            {'building': ['residential', 'residential']},
            geometry=[box(0, 0, 12, 10), box(20, 0, 42, 10)],
            crs=25832)
        result = p._residential_typology_metrics(buildings)
        self.assertEqual(result['inferred_sfh_like_count'], 0)
        self.assertEqual(result['inferred_mfh_like_count'], 0)
        self.assertEqual(result['unknown_residential_typology_count'], 2)

    def test_residential_typology_uses_specific_evidence_precedence(self):
        buildings = p.gpd.GeoDataFrame(
            {
                'building': [
                    'house', 'apartments', 'house', 'apartments', 'yes',
                    'yes', 'dormitory', 'bungalow', 'farm', 'terrace'],
                'building:use': [
                    '', '', 'apartments', 'house', 'residential',
                    'residential', '', '', '', ''],
                'building:flats': [3, 1, None, None, None,
                                   None, None, None, None, None],
            },
            geometry=[
                box(30 * i, 0, 30 * i + width, 10)
                for i, width in enumerate(
                    [10, 10, 10, 10, 10, 15, 10, 10, 10, 10])],
            crs=25832)
        result = p._residential_typology_metrics(buildings)
        self.assertEqual(result['sfh_like_count'], 6)
        self.assertEqual(result['mfh_like_count'], 3)
        self.assertEqual(result['unknown_residential_typology_count'], 1)
        self.assertEqual(result['typology_from_building_flats_count'], 2)
        self.assertEqual(result['typology_from_building_use_count'], 2)
        self.assertEqual(result['typology_from_building_tag_count'], 4)
        self.assertEqual(result['aggregate_terrace_footprint_count'], 1)

    def test_residential_typology_requirement_is_conditional(self):
        ranges = {
            'B': {
                'bounds': {'bcr': [0.1, 0.2]},
                'conditional_requirements': {
                    'sfh_share_known_pct': {
                        'bounds': [80, 100],
                        'when': 'residential_typology_requirement_applied'}}},
        }
        unavailable = p.range_scores(
            {'bcr': 0.15, 'sfh_share_known_pct': 0,
             'residential_typology_requirement_applied': False}, ranges)[0]
        self.assertTrue(unavailable['eligible'])
        self.assertIsNone(
            unavailable['requirement_results']['sfh_share_known_pct'])
        failed = p.range_scores(
            {'bcr': 0.15, 'sfh_share_known_pct': 60,
             'residential_typology_requirement_applied': True}, ranges)[0]
        self.assertFalse(failed['eligible'])

    def test_fixed_settlement_context_thresholds(self):
        self.assertEqual(
            p._settlement_context_from_metrics(5.0, 0.05), 'RURAL')
        self.assertEqual(
            p._settlement_context_from_metrics(15.0, 0.12), 'RURAL')
        self.assertEqual(
            p._settlement_context_from_metrics(15.0, 0.15), 'URBAN')
        self.assertEqual(
            p._settlement_context_from_metrics(21.0, 0.12), 'URBAN')
        self.assertEqual(
            p._settlement_context_from_metrics(8.0, 0.21), 'URBAN')

    def test_rural_influence_boundary_stops_halfway_to_external_building(self):
        buildings = p.gpd.GeoDataFrame(
            {'osm_key': ['way/1', 'way/2']},
            geometry=[box(-1, -1, 1, 1), box(9, -1, 11, 1)],
            crs=25832)
        candidates = [(box(-2, -2, 2, 2), [0], 'street_cluster')]
        contexts = [{
            'context_building_density_per_ha': 5.0,
            'context_bcr': 0.05,
        }]
        updated, applied, reaches = p._apply_rural_influence_boundaries(
            candidates, contexts, buildings, box(-20, -10, 20, 10))
        self.assertEqual(applied, {0})
        self.assertEqual(reaches, {0: 30.0})
        self.assertAlmostEqual(updated[0][0].bounds[2], 5.0, places=6)
        self.assertIn('rural_influence_boundary', updated[0][2])

    def test_rural_influence_boundary_excludes_external_footprint(self):
        buildings = p.gpd.GeoDataFrame(
            {'osm_key': ['way/1', 'way/2']},
            geometry=[box(-1, -1, 1, 1), box(4, -4, 16, 4)],
            crs=25832)
        candidates = [(box(-2, -2, 2, 2), [0], 'street_cluster')]
        contexts = [{
            'context_building_density_per_ha': 5.0,
            'context_bcr': 0.05,
        }]
        updated, _, _ = p._apply_rural_influence_boundaries(
            candidates, contexts, buildings, box(-20, -10, 20, 10))
        self.assertAlmostEqual(
            updated[0][0].intersection(buildings.geometry.iloc[1]).area,
            0.0, places=6)

    def test_rural_influence_boundary_is_capped_by_local_member_spacing(self):
        buildings = p.gpd.GeoDataFrame(
            {'osm_key': ['way/1', 'way/2', 'way/3', 'way/4']},
            geometry=[box(-1, -1, 1, 1), box(9, -1, 11, 1),
                      box(19, -1, 21, 1), box(999, -1, 1001, 1)],
            crs=25832)
        candidates = [(box(-2, -2, 22, 2), [0, 1, 2], 'street_cluster')]
        contexts = [{
            'context_building_density_per_ha': 5.0,
            'context_bcr': 0.05,
        }]
        updated, applied, reaches = p._apply_rural_influence_boundaries(
            candidates, contexts, buildings, box(-100, -100, 1100, 100))
        self.assertEqual(applied, {0})
        self.assertAlmostEqual(reaches[0], 15.0)
        self.assertLessEqual(updated[0][0].bounds[2], 36.000001)

    def test_a_and_b_require_positive_morphological_evidence(self):
        ranges = p.load_ranges(
            Path(__file__).resolve().parents[1] /
            'districtgenerator/data/typdistrict_parameters.xlsx')
        self.assertIn('building_spacing_median_m',
                      ranges['A']['requirements'])
        self.assertIn('continuous_road_frontage_pct',
                      ranges['A']['requirements'])
        self.assertEqual(
            ranges['B']['requirements']['road_side_spacing_count'][0], 3)

    def test_context_directly_restricts_type_eligibility(self):
        ranges = {
            'A': {'bounds': {'bcr': [0.1, 0.2]}},
            'H': {'bounds': {'bcr': [0.1, 0.2]}},
        }
        scores = p.range_scores(
            {'bcr': 0.15}, ranges, allowed_types={'A'})
        selected, _, _ = p.assign_type(scores)
        self.assertEqual(selected['type'], 'A')
        h_score = next(score for score in scores if score['type'] == 'H')
        self.assertFalse(h_score['eligible'])
        self.assertFalse(
            h_score['requirement_results']['settlement_context'])

    def test_quick_scope_filters_source_features_before_analysis(self):
        boundary = p.gpd.GeoDataFrame(
            geometry=[box(5.8, 50.6, 6.6, 51.0)], crs=4326)
        features = p.gpd.GeoDataFrame(
            {'building': ['yes', 'yes']},
            geometry=[p.Point(6.0839, 50.7753),
                      p.Point(6.50, 50.90)], crs=4326)
        quick_boundary, quick_features, metadata = p.apply_analysis_scope(
            boundary, features, 'quick')
        self.assertEqual(len(quick_features), 1)
        self.assertEqual(metadata['analysis_scope'], 'quick_central_aachen')
        self.assertEqual(
            metadata['quick_test_radius_m'], p.QUICK_TEST_RADIUS_M)
        self.assertTrue(quick_boundary.to_crs(25832).geometry.area.iloc[0]
                        < boundary.to_crs(25832).geometry.area.iloc[0])

    def test_ambiguous_b_c_ranges_use_ordinary_midpoint_tiebreak(self):
        ranges = {
            'B': {'bounds': {'bcr': [.1, .3]}},
            'C': {'bounds': {'bcr': [.2, .4]}},
        }
        scores = p.range_scores({'bcr': .28}, ranges)
        self.assertEqual([score['range_score'] for score in scores], [0,0])
        selected, compatible, reason = p.assign_type(scores)
        self.assertEqual(selected['type'], 'C')
        self.assertEqual(len(compatible), 2)
        self.assertEqual(reason, 'midpoint_tiebreak')

    def test_midpoint_tiebreak_and_nearest_outside_assignment(self):
        ranges = {
            'B': {'bounds': {'bcr': [0.1, 0.3]}},
            'C': {'bounds': {'bcr': [0.2, 0.4]}},
        }
        scores = p.range_scores({'bcr': 0.22}, ranges)
        selected, compatible, reason = p.assign_type(scores)
        self.assertEqual(selected['type'], 'B')
        self.assertEqual({item['type'] for item in compatible}, {'B', 'C'})
        self.assertEqual(reason, 'midpoint_tiebreak')

        scores = p.range_scores({'bcr': 0.5}, ranges)
        selected, compatible, reason = p.assign_type(scores)
        self.assertEqual(selected['type'], 'C')
        self.assertEqual(compatible, [])
        self.assertEqual(reason, 'nearest_outside_ranges')
        self.assertAlmostEqual(selected['penalties']['bcr'], 0.5)

    def test_range_score_quality_threshold(self):
        self.assertEqual(p.classification_quality(0.0), 'exact')
        self.assertEqual(p.classification_quality(0.25), 'approximate')
        self.assertEqual(p.classification_quality(1.0), 'approximate')
        self.assertEqual(p.classification_quality(1.000001), 'unclassified')

    def test_common_scale_removes_wide_range_advantage(self):
        ranges = {
            'E': {'bounds': {'spacing': [8.0, 12.0]}},
            'I': {'bounds': {'spacing': [8.0, 20.5]}},
        }
        scores = {item['type']: item for item in
                  p.range_scores({'spacing': 5.0}, ranges)}
        self.assertAlmostEqual(
            scores['E']['penalties']['spacing'],
            scores['I']['penalties']['spacing'])
        self.assertAlmostEqual(
            p.common_indicator_scales(ranges)['spacing'], 8.25)

    def test_block_frontage_is_requirement_not_score_term(self):
        ranges = {
            'E': {'bounds': {'bcr': [0.2, 0.3]}},
            'H': {
                'bounds': {'bcr': [0.3, 0.4]},
                'requirements': {'block_frontage_structure_pct': [50, 100]},
            },
        }
        scores = {item['type']: item for item in p.range_scores(
            {'bcr': 0.35, 'block_frontage_structure_pct': 40}, ranges)}
        self.assertFalse(scores['H']['eligible'])
        self.assertEqual(scores['H']['range_score'], float('inf'))
        self.assertNotIn(
            'block_frontage_structure_pct', scores['H']['penalties'])

        scores = {item['type']: item for item in p.range_scores(
            {'bcr': 0.35, 'block_frontage_structure_pct': 60}, ranges)}
        self.assertTrue(scores['H']['eligible'])
        self.assertEqual(scores['H']['range_score'], 0)
        self.assertEqual(scores['H']['indicator_count'], 1)

    def test_candidates_have_unique_members_and_bounded_size(self):
        buildings = p.gpd.GeoDataFrame(geometry=[box(x*20+3,y*20+3,x*20+8,y*20+8)
                                                 for x in range(20) for y in range(20)], crs=25832)
        roads = p.gpd.GeoDataFrame(geometry=[LineString([(x,0),(x,400)]) for x in range(0,401,100)] +
                                            [LineString([(0,y),(400,y)]) for y in range(0,401,100)], crs=25832)
        result = p.hybrid_candidates(
            buildings, roads, box(0,0,400,400), 40, 2026,
            minimum=30, maximum=70)
        self.assertTrue(result)
        ids = [i for _, members,_ in result for i in members]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(30 <= len(members) <= 70 for _,members,_ in result))
        for i,(a,_,_) in enumerate(result):
            for b,_,_ in result[i+1:]:
                self.assertLess(a.intersection(b).area,1e-6)

    def test_touching_buildings_and_same_road_side_spacing(self):
        buildings = p.gpd.GeoDataFrame(geometry=[box(0,10,10,20),box(10,10,20,20)],crs=25832)
        roads = p.gpd.GeoDataFrame(geometry=[LineString([(-10,0),(30,0)])],crs=25832)
        result = p.geometry_metrics(buildings,roads,box(-10,-10,30,30))
        self.assertEqual(result['attached_building_pct'],100)
        self.assertEqual(result['road_side_longitudinal_spacing_median_m'],10)
        self.assertEqual(result['road_side_longitudinal_spacing_count'],1)
        self.assertEqual(result['road_side_spacing_count'], 1)
        self.assertNotIn('median_footprint_aspect_ratio', result)
        self.assertNotIn('orientation_alignment_0_1', result)
        self.assertNotIn('building_gap_median_m', result)
        self.assertNotIn('footprint_mean_m2', result)
        self.assertNotIn('road_parallel_building_pct', result)
        self.assertNotIn('road_perpendicular_building_pct', result)
        self.assertNotIn('centroid_to_road_distance_mean_m', result)

    def test_spacing_separates_opposite_road_sides(self):
        buildings = p.gpd.GeoDataFrame(
            geometry=[box(0,10,10,20), box(10,10,20,20),
                      box(0,-20,10,-10), box(10,-20,20,-10)], crs=25832)
        roads = p.gpd.GeoDataFrame(
            geometry=[LineString([(-10,0),(30,0)])], crs=25832)
        result = p.geometry_metrics(buildings, roads, box(-10,-30,30,30))
        self.assertEqual(result['road_side_longitudinal_spacing_median_m'], 10)
        self.assertEqual(result['road_side_longitudinal_spacing_count'], 2)

    def test_same_side_spacing_ignores_close_buildings_across_road(self):
        buildings = p.gpd.GeoDataFrame(
            geometry=[box(0, 10, 2, 12), box(20, 10, 22, 12),
                      box(0, -12, 2, -10), box(20, -12, 22, -10)],
            crs=25832)
        roads = p.gpd.GeoDataFrame(
            geometry=[LineString([(-10, 0), (40, 0)])], crs=25832)
        result = p.geometry_metrics(buildings, roads, box(-10, -20, 40, 20))
        self.assertEqual(result['road_side_longitudinal_spacing_median_m'], 20)
        self.assertEqual(result['road_side_longitudinal_spacing_count'], 2)

    def test_nearest_neighbour_spacing_is_used_when_road_spacing_is_missing(self):
        buildings = p.gpd.GeoDataFrame(
            geometry=[box(0, 0, 2, 2), box(30, 0, 32, 2),
                      box(70, 0, 72, 2)], crs=25832)
        roads = p.gpd.GeoDataFrame(
            geometry=[LineString([(0, 200), (100, 200)])], crs=25832)
        result = p.geometry_metrics(
            buildings, roads, box(-10, -10, 110, 210))
        self.assertEqual(result['road_side_longitudinal_spacing_count'], 0)
        self.assertEqual(
            result['building_spacing_source'],
            'nearest_neighbour_fallback')
        self.assertAlmostEqual(result['building_spacing_median_m'], 30)

    def test_continuous_frontage_identifies_same_side_building_run(self):
        centres = [p.Point(x, 10) for x in (0, 20, 40, 200)]
        roads = p.gpd.GeoDataFrame(
            geometry=[LineString([(-10, 0), (220, 0)])], crs=25832)
        self.assertEqual(
            p._continuous_road_frontage_pct(centres, roads), 75)

    def test_sparse_points_receive_less_concave_boundary_ratio(self):
        compact = [p.Point(x, 0) for x in (0, 10, 20, 30)]
        sparse = [p.Point(x, 0) for x in (0, 60, 120, 180)]
        self.assertAlmostEqual(p._adaptive_hull_ratio(compact), 0.30)
        self.assertAlmostEqual(p._adaptive_hull_ratio(sparse), 1.0)

    def test_final_coherence_splits_exceptionally_separated_small_groups(self):
        points = ([p.Point(x * 10, 0) for x in range(6)] +
                  [p.Point(1000 + x * 10, 0) for x in range(6)])
        components = p._spatial_coherence_components(range(12), points)
        self.assertEqual([len(component) for component in components], [6, 6])
        self.assertEqual(
            [component for component in components if len(component) >= 10],
            [])

    def test_final_coherence_retains_large_core_not_remote_fragment(self):
        points = ([p.Point(x * 10, 0) for x in range(10)] +
                  [p.Point(1000 + x * 10, 0) for x in range(3)])
        components = p._spatial_coherence_components(range(13), points)
        self.assertEqual([len(component) for component in components], [10, 3])
        self.assertEqual(
            [len(component) for component in components
             if len(component) >= 10], [10])

    def test_general_row_indicator_detects_rows_across_a_road(self):
        centres = [
            p.Point(x, y)
            for x, values in [(0, (0, 20, 40, 60)),
                              (20, (3, 24, 45, 66)),
                              (40, (7, 29, 51, 73))]
            for y in values]
        roads = p.gpd.GeoDataFrame(
            {'highway': ['residential']},
            geometry=[LineString([(-20, -10), (60, -10)])], crs=25832)
        result = p._building_row_metrics(centres, roads)
        self.assertEqual(result['row_structure_pct'], 100)
        self.assertGreaterEqual(result['row_count'], 2)
        self.assertEqual(result['row_building_count'], 12)
        self.assertIsNotNone(result['row_road_angle_deg'])

    def test_rows_following_a_road_count_as_general_row_structure(self):
        centres = [
            p.Point(x, y)
            for y in (0, 20)
            for x in (0, 20, 40, 60)]
        roads = p.gpd.GeoDataFrame(
            {'highway': ['residential']},
            geometry=[LineString([(-20, -10), (80, -10)])], crs=25832)
        result = p._building_row_metrics(centres, roads)
        self.assertEqual(result['row_structure_pct'], 100)
        self.assertLessEqual(result['row_road_angle_deg'], 15)

    def test_review_layers_show_exact_members_and_nearby_unassigned_buildings(self):
        buildings = p.gpd.GeoDataFrame(
            {'osm_key': ['way/1', 'way/2', 'way/3'],
             'building': ['yes', 'yes', 'yes']},
            geometry=[box(0, 0, 10, 10), box(15, 0, 25, 10),
                      box(100, 0, 110, 10)], crs=25832)
        districts = p.gpd.GeoDataFrame(
            {'district_id': ['AC0001'], 'building_count': [1], 'typ': ['F']},
            geometry=[box(-5, -5, 12, 15)], crs=25832).to_crs(4326)
        roads = p.gpd.GeoDataFrame(
            {'highway': ['residential', 'service']},
            geometry=[LineString([(-10, -2), (40, -2)]),
                      LineString([(-10, 12), (40, 12)])], crs=25832)
        membership = p.pd.DataFrame(
            [{'district_id': 'AC0001', 'osm_key': 'way/1'}])

        selected, nearby, review_roads = p._review_map_layers(
            districts, buildings, roads, membership, nearby_distance=30)

        self.assertEqual(selected.osm_key.tolist(), ['way/1'])
        self.assertEqual(selected.typ.tolist(), ['F'])
        self.assertEqual(nearby.osm_key.tolist(), ['way/2'])
        self.assertEqual(len(review_roads), 1)
        self.assertEqual(review_roads.highway.iloc[0], 'residential')

    def test_review_map_contains_settlement_type_filter(self):
        row = {
            'district_id': 'AC0001', 'building_count': 1, 'typ': 'F',
            'classification_quality': 'approximate',
            'included_in_type_results': True,
            'assignment_reason': 'unique_compatible',
            'proposed_assignment_reason': 'unique_compatible',
            'proposed_source_type': 'F',
            'settlement_context': 'RURAL', 'context_area_ha': 1.0,
            'context_building_count': 10,
            'context_building_density_per_ha': 10.0,
            'context_bcr': 0.1,
            'rural_influence_boundary_applied': False,
            'rural_boundary_reach_m': None,
            'initial_context_building_density_per_ha': 10.0,
            'initial_context_bcr': 0.1,
            'context_allowed_types': 'A;B;C;D;E;F;G',
            'unrestricted_assigned_type': 'F',
            'context_changed_assignment': False,
            'range_score': 1.0, 'midpoint_score': 1.0,
            'compatible_types': '', 'nearest_source_type': 'E',
            'matching_indicator_count': 5, 'eligible_types': 'A;B;C;D;E;F;G',
            'block_frontage_requirement_met': False,
            'indicator_penalties': '', 'indicator_midpoint_distances': '',
            'all_type_requirement_checks': '',
            'all_type_range_scores': '', 'all_type_midpoint_scores': '',
            'building_spacing_median_m': 10.0,
            'building_spacing_source': 'same_road_side',
            'road_side_spacing_count': 3,
            'sfh_like_count': 0,
            'mfh_like_count': 5,
            'residential_building_count_for_typology': 5,
            'known_residential_typology_count': 5,
            'unknown_residential_typology_count': 0,
            'residential_typology_coverage_pct': 100.0,
            'sfh_share_known_pct': 0.0,
            'mfh_share_known_pct': 100.0,
            'residential_typology_requirement_applied': True,
            'continuous_road_frontage_pct': 50.0,
            'row_structure_pct': 100.0,
            'row_count': 2,
            'row_building_count': 1,
            'row_direction_deg': 90.0,
            'row_road_angle_deg': 90.0,
            'boundary_hull_ratio': 0.3,
            'boundary_method': 'road_block_cluster_morphology_row_split',
            'unknown_use_pct': 0.0,
        }
        districts = p.gpd.GeoDataFrame(
            [row], geometry=[box(-5, -5, 12, 15)], crs=25832).to_crs(4326)
        buildings = p.gpd.GeoDataFrame(
            {'osm_key': ['way/1', 'way/2'],
             'building': ['yes', 'yes']},
            geometry=[box(0, 0, 10, 10), box(18, 0, 28, 10)], crs=25832)
        roads = p.gpd.GeoDataFrame(
            {'highway': ['residential']},
            geometry=[LineString([(-10, -2), (40, -2)])], crs=25832)
        membership = p.pd.DataFrame(
            [{'district_id': 'AC0001', 'osm_key': 'way/1'}])
        industrial_sites = p.gpd.GeoDataFrame(
            {'osm_key': ['relation/9'], 'landuse': ['industrial'],
             'excluded_area_ha': [0.01]},
            geometry=[box(35, 0, 45, 10)], crs=25832)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            p.write_map(
                output, districts, buildings, roads, membership,
                industrial_sites=industrial_sites)
            html = (output / 'review_map.html').read_text(encoding='utf-8')
        self.assertIn('Map legend and filters', html)
        self.assertIn('Settlement types', html)
        self.assertIn('data-type="F"', html)
        self.assertIn('data-quality="exact"', html)
        self.assertIn('data-quality="approximate"', html)
        self.assertIn('data-quality="unclassified"', html)
        self.assertIn('Exact: score = 0', html)
        self.assertIn('Approximate: 0–1', html)
        self.assertIn('Unclassified: &gt; 1', html)
        self.assertIn('Visible districts:', html)
        self.assertIn('activeTypes', html)
        self.assertIn('activeQualities', html)
        self.assertIn('Excluded industrial land-use sites', html)
        self.assertIn('Industrial area', html)
        self.assertIn('OSM landuse=industrial', html)
        self.assertIn('dg-industrial-button', html)
        self.assertIn('#000000', html)

    def test_matching_uses_general_row_structure_for_e_and_f(self):
        workbook = Path(__file__).resolve().parents[1] / 'districtgenerator/data/typdistrict_parameters.xlsx'
        ranges = p.load_ranges(workbook)
        self.assertEqual(
            set(ranges['A']['bounds']),
            {'bcr', 'density', 'far',
             'building_spacing_median_m',
             'attached_building_pct',
             'row_structure_pct'})
        self.assertEqual(
            ranges['A']['bounds']['building_spacing_median_m'],
            [25, 110])
        self.assertEqual(
            ranges['I']['bounds']['building_spacing_median_m'],
            [8, 20.5])
        self.assertEqual(ranges['A']['bounds']['attached_building_pct'], [0, 35])
        self.assertEqual(ranges['E']['bounds']['attached_building_pct'], [50, 100])
        self.assertEqual(ranges['F']['bounds']['attached_building_pct'], [50, 100])
        self.assertEqual(ranges['H']['bounds']['attached_building_pct'], [50, 100])
        self.assertEqual(ranges['I']['bounds']['attached_building_pct'], [50, 100])
        self.assertEqual(
            ranges['E']['bounds']['row_structure_pct'], [60, 100])
        self.assertEqual(
            ranges['F']['bounds']['row_structure_pct'], [60, 100])
        for typ in 'ABCDGHI':
            self.assertEqual(
                ranges[typ]['bounds']['row_structure_pct'], [0, 60])
        for typ in 'ABCDEFGHI':
            self.assertNotIn('road_parallel_building_pct', ranges[typ]['bounds'])
            self.assertNotIn('road_perpendicular_building_pct', ranges[typ]['bounds'])
        self.assertEqual(
            ranges['H']['requirements']['block_frontage_structure_pct'],
            [50, 100])
        self.assertEqual(
            ranges['I']['requirements']['block_frontage_structure_pct'],
            [50, 100])
        self.assertEqual(
            ranges['A']['requirements']['continuous_road_frontage_pct'],
            [0, 50])
        self.assertEqual(
            ranges['A']['requirements']['attached_building_pct'],
            [0, 35])
        self.assertEqual(
            ranges['B']['requirements']['continuous_road_frontage_pct'],
            [50, 100])
        self.assertEqual(
            ranges['B']['requirements']['attached_building_pct'],
            [0, 50])
        self.assertNotIn('block_frontage_structure_pct', ranges['E']['bounds'])
        self.assertNotIn('block_frontage_structure_pct', ranges['H']['bounds'])
        self.assertNotIn('block_frontage_structure_pct', ranges['I']['bounds'])

    def test_closed_block_frontage_requires_coverage_and_continuity(self):
        roads = p.gpd.GeoDataFrame(
            {'highway':['residential'] * 4},
            geometry=[LineString([(0,0),(100,0)]),
                      LineString([(100,0),(100,100)]),
                      LineString([(100,100),(0,100)]),
                      LineString([(0,100),(0,0)])], crs=25832)
        distributed_frontage = p.gpd.GeoDataFrame(
            geometry=[box(5,82,45,98), box(55,82,95,98),
                      box(82,5,98,45), box(82,55,98,95),
                      box(2,5,18,45), box(2,55,18,95)], crs=25832)
        concentrated_frontage = distributed_frontage.iloc[:4].copy()
        distributed_result = p.geometry_metrics(
            distributed_frontage, roads, box(-10,-10,110,110))
        concentrated_result = p.geometry_metrics(
            concentrated_frontage, roads, box(-10,-10,110,110))
        self.assertGreaterEqual(
            distributed_result['block_frontage_structure_pct'], 50)
        self.assertLessEqual(
            distributed_result['block_frontage_largest_gap_min_pct'], 35)
        self.assertEqual(
            concentrated_result['block_frontage_structure_pct'], 0)

    def test_use_population_retains_unknowns(self):
        index = p.pd.MultiIndex.from_tuples([('way',1),('way',2),('way',3),('node',4)])
        features = p.gpd.GeoDataFrame({'building':['house','yes','garage',None],
                                      'shop':[None,None,None,'supermarket']}, index=index,
            geometry=[box(0,0,10,10),box(20,0,30,10),box(40,0,50,10),p.Point(5,5)],crs=25832)
        boundary = p.gpd.GeoDataFrame(geometry=[box(-10,-10,60,60)],crs=25832)
        _, _, buildings, _, _, _ = p.extract(features, boundary)
        self.assertEqual(len(buildings),2)
        self.assertIn('yes',set(buildings.building))
        counts,diagnostics = p.classify_nrb_buildings(features.drop(index=('way',3)))
        self.assertEqual(diagnostics['mixed_building_split_count'],1)
        self.assertEqual(diagnostics['unknown_building_split_count'],1)
        self.assertEqual(counts['GS'],1)

    def test_industrial_landuse_excludes_complete_site(self):
        index = p.pd.MultiIndex.from_tuples([
            ('relation', 1), ('way', 2), ('way', 3), ('way', 4),
            ('way', 5)])
        features = p.gpd.GeoDataFrame(
            {
                'landuse': ['industrial', None, None, None, None],
                'building': [None, 'yes', 'yes', None, 'yes'],
                'highway': [None, None, None, 'residential', None],
            },
            index=index,
            geometry=[box(0, 0, 100, 100), box(20, 20, 30, 30),
                      box(130, 20, 140, 30),
                      LineString([(-20, 50), (160, 50)]),
                      box(150, 80, 153, 83)],
            crs=25832)
        boundary = p.gpd.GeoDataFrame(
            geometry=[box(-50, -50, 200, 150)], crs=25832)

        (_, analysis_boundary, buildings, roads, industrial_sites,
         summary) = p.extract(features, boundary)

        self.assertEqual(buildings.osm_key.tolist(), ['way/3'])
        self.assertEqual(len(industrial_sites), 1)
        self.assertEqual(summary['industrial_excluded_buildings'], 1)
        self.assertEqual(summary['small_footprint_excluded_buildings'], 1)
        self.assertEqual(summary['minimum_building_footprint_area_m2'], 20)
        self.assertAlmostEqual(
            summary['industrial_exclusion_area_ha'], 1.0)
        self.assertFalse(analysis_boundary.covers(p.Point(50, 50)))
        industrial_interior = box(0.01, 0.01, 99.99, 99.99)
        self.assertTrue(all(
            road.intersection(industrial_interior).is_empty
            for road in roads.geometry))

    def test_two_sided_street_clusters_and_building_envelopes(self):
        buildings = p.gpd.GeoDataFrame(
            geometry=[box(x*20+2,8,x*20+10,16) for x in range(60)] +
                     [box(x*20+2,-16,x*20+10,-8) for x in range(60)], crs=25832)
        roads = p.gpd.GeoDataFrame({'highway':['residential']},
            geometry=[LineString([(0,0),(1200,0)])], crs=25832)
        result = p.street_candidates(buildings, roads, box(-50,-100,1250,100),
                                     target=40, seed=2026, minimum=30, maximum=70)
        street = [(geometry, members) for geometry, members, method in result
                  if method == 'two_sided_street_cluster']
        self.assertTrue(street)
        self.assertTrue(all(30 <= len(members) <= 70 for _, members in street))
        for geometry, members in street:
            y = [buildings.geometry.iloc[index].centroid.y for index in members]
            self.assertLess(min(y), 0)
            self.assertGreater(max(y), 0)
            self.assertTrue(all(geometry.covers(buildings.geometry.iloc[index].representative_point())
                                for index in members))
        for index, (left, _) in enumerate(street):
            for right, _ in street[index+1:]:
                self.assertLess(left.intersection(right).area, 1e-6)

    def test_street_sections_follow_building_positions_not_fixed_length(self):
        points = [p.Point(x, 10) for x in (100, 400, 900)]
        roads = p.gpd.GeoDataFrame({'highway':['residential']},
            geometry=[LineString([(0,0),(1000,0)])], crs=25832)
        sections, memberships = p._building_defined_street_sections(
            roads, points, maximum_road_distance=150,
            maximum_buildings_per_section=1)
        occupied = [(section, members) for section, members in zip(sections, memberships)
                    if members]
        self.assertEqual(len(occupied), 3)
        self.assertEqual([members for _, members in occupied], [{0}, {1}, {2}])
        self.assertAlmostEqual(occupied[0][0].length, 250)
        self.assertAlmostEqual(occupied[1][0].length, 400)
        self.assertAlmostEqual(occupied[2][0].length, 350)

    def test_exceptional_building_gap_breaks_road_continuity(self):
        points = [p.Point(x, 10) for x in (10, 20, 30, 40, 50, 60, 300)]
        roads = p.gpd.GeoDataFrame(
            {'highway':['residential']},
            geometry=[LineString([(0,0),(400,0)])], crs=25832)
        sections, memberships = p._building_defined_street_sections(
            roads, points, maximum_road_distance=150,
            maximum_buildings_per_section=1)
        adjacency = p._segment_adjacency(sections)
        left = next(index for index, members in enumerate(memberships)
                    if 5 in members)
        right = next(index for index, members in enumerate(memberships)
                     if 6 in members)
        self.assertNotIn(right, adjacency[left])
        self.assertAlmostEqual(sections[left].coords[-1][0], 60)
        self.assertAlmostEqual(sections[right].coords[0][0], 300)

    def test_street_growth_prefers_shorter_length_per_new_building(self):
        long_exact_target = p._street_growth_priority(
            LineString([(0, 0), (300, 0)]), range(6), 34, 40)
        short_below_target = p._street_growth_priority(
            LineString([(0, 0), (60, 0)]), range(3), 34, 40)
        self.assertLess(short_below_target, long_exact_target)

    def test_natural_component_below_target_is_retained_complete(self):
        segments = [LineString([(index, 0), (index + 1, 0)])
                    for index in range(23)]
        memberships = [{index} for index in range(23)]
        adjacency = p._segment_adjacency(segments)
        partitions = p._partition_natural_street_component(
            set(range(23)), memberships, adjacency, segments, set(),
            minimum=15, maximum=70, target=40,
            seed_order=list(range(23)))
        self.assertEqual(len(partitions), 1)
        self.assertEqual(partitions[0][1], set(range(23)))

    def test_oversized_natural_component_is_divided_near_target(self):
        segments = [LineString([(index, 0), (index + 1, 0)])
                    for index in range(80)]
        memberships = [{index} for index in range(80)]
        adjacency = p._segment_adjacency(segments)
        partitions = p._partition_natural_street_component(
            set(range(80)), memberships, adjacency, segments, set(),
            minimum=15, maximum=70, target=40,
            seed_order=list(range(80)))
        sizes = sorted(len(ids) for _, ids in partitions)
        self.assertEqual(sizes, [40, 40])
        self.assertEqual(
            set().union(*(ids for _, ids in partitions)), set(range(80)))

    def test_small_remote_terminal_branch_is_pruned(self):
        segments = [LineString([(index * 10, 0), ((index + 1) * 10, 0)])
                    for index in range(8)]
        segments.append(LineString([(80, 0), (300, 0)]))
        memberships, points = [], []
        for segment_index in range(8):
            members = set()
            for offset in range(4):
                members.add(len(points))
                points.append(p.Point(segment_index * 10 + offset + 1, 5))
            memberships.append(members)
        remote = set()
        for x in (290, 295):
            remote.add(len(points))
            points.append(p.Point(x, 5))
        memberships.append(remote)
        adjacency = p._segment_adjacency(segments)
        group, ids = p._prune_exceptional_terminal_branches(
            set(range(9)), memberships, adjacency, points, set(), minimum=30,
            maximum_branch_buildings=4)
        self.assertNotIn(8, group)
        self.assertEqual(len(ids), 32)

    def test_small_remote_group_is_pruned_from_block_candidate(self):
        points = [p.Point((index % 8) * 10, (index // 8) * 10)
                  for index in range(32)]
        points.extend([p.Point(1000, 0), p.Point(1010, 0)])
        retained = p._prune_small_remote_building_groups(
            set(range(34)), points, minimum=30,
            maximum_remote_buildings=4)
        self.assertEqual(retained, set(range(32)))

    def test_large_remote_group_is_not_silently_removed(self):
        points = [p.Point((index % 8) * 10, (index // 8) * 10)
                  for index in range(32)]
        points.extend([p.Point(1000 + index * 10, 0) for index in range(5)])
        retained = p._prune_small_remote_building_groups(
            set(range(37)), points, minimum=30,
            maximum_remote_buildings=4)
        self.assertEqual(retained, set(range(37)))

    def test_empty_enclosed_area_is_filled_but_external_building_hole_remains(self):
        empty_hole = box(20,20,35,35)
        occupied_hole = box(60,60,80,80)
        envelope = Polygon(
            box(0,0,100,100).exterior.coords,
            holes=[empty_hole.exterior.coords, occupied_hole.exterior.coords])
        footprints = [box(5,5,10,10), box(65,65,70,70)]
        tree = p.shapely.STRtree(footprints)
        filled = p._fill_empty_enclosed_areas(envelope, tree, {0})
        self.assertTrue(filled.covers(p.Point(25,25)))
        self.assertFalse(filled.covers(p.Point(67,67)))

    def test_empty_boundary_bay_is_closed(self):
        # A 20 m wide indentation is open to the exterior at its lower end.
        envelope = box(0, 0, 100, 100).difference(box(40, 0, 60, 70))
        footprints = [box(5, 5, 10, 10)]
        tree = p.shapely.STRtree(footprints)
        closed, absorbed = p._close_empty_boundary_bays(
            envelope, 15, tree, {0}, box(-50, -50, 150, 150))
        self.assertGreater(closed.area, envelope.area)
        self.assertTrue(closed.covers(p.Point(50, 60)))
        self.assertEqual(absorbed, set())

    def test_boundary_bay_absorbs_unassigned_building(self):
        envelope = box(0, 0, 100, 100).difference(box(40, 0, 60, 70))
        footprints = [box(5, 5, 10, 10), box(47, 55, 53, 65)]
        tree = p.shapely.STRtree(footprints)
        closed, absorbed = p._close_empty_boundary_bays(
            envelope, 15, tree, {0}, box(-50, -50, 150, 150),
            maximum_new_buildings=1)
        self.assertGreater(closed.area, envelope.area)
        self.assertEqual(absorbed, {1})

    def test_boundary_bay_does_not_absorb_blocked_building(self):
        envelope = box(0, 0, 100, 100).difference(box(40, 0, 60, 70))
        footprints = [box(5, 5, 10, 10), box(47, 55, 53, 65)]
        tree = p.shapely.STRtree(footprints)
        closed, absorbed = p._close_empty_boundary_bays(
            envelope, 15, tree, {0}, box(-50, -50, 150, 150),
            blocked_ids={1}, maximum_new_buildings=1)
        self.assertAlmostEqual(closed.area, envelope.area)
        self.assertFalse(closed.intersects(footprints[1]))
        self.assertEqual(absorbed, set())

    def test_morphology_split_separates_row_and_nonrow_subareas(self):
        row_points = [(x, y) for x in (0, 15, 30)
                      for y in (0, 15, 30, 45)]
        other_points = [
            (90, 2), (103, 17), (119, 6), (137, 28), (151, 11),
            (94, 43), (110, 35), (126, 49), (143, 42), (156, 52),
            (122, 23), (150, 32), (170, 4), (181, 19), (193, 39),
            (207, 8), (218, 28), (231, 47), (245, 15), (258, 35)]
        footprints = [box(x - 2, y - 2, x + 2, y + 2)
                      for x, y in row_points + other_points]
        buildings = p.gpd.GeoDataFrame(
            {'osm_key': [f'way/{index}' for index in range(len(footprints))],
             'building': ['yes'] * len(footprints)},
            geometry=footprints, crs=25832)
        roads = p.gpd.GeoDataFrame(
            {'highway': ['residential']},
            geometry=[LineString([(-20, -10), (175, -10)])], crs=25832)
        candidate = (
            box(-10, -15, 270, 60), list(range(len(footprints))),
            'road_block_cluster')

        refined = p._split_row_morphology_candidate(
            candidate, buildings, roads, minimum=10, maximum=70)

        self.assertEqual(len(refined), 2)
        self.assertEqual(sorted(len(ids) for _, ids, _ in refined), [12, 20])
        methods = {method for _, _, method in refined}
        self.assertTrue(any(method.endswith('_morphology_row_split')
                            for method in methods))
        self.assertTrue(any(method.endswith('_morphology_nonrow_split')
                            for method in methods))

    def test_morphology_row_split_is_classified_by_ordinary_scores(self):
        scores = [
            {'type': 'E', 'eligible': True, 'range_score': 0.1},
            {'type': 'F', 'eligible': True, 'range_score': 1.2},
        ]
        selected, compatible, reason = p.assign_type(scores)
        self.assertEqual(selected['type'], 'E')
        self.assertEqual(compatible, [])
        self.assertEqual(reason, 'nearest_outside_ranges')


if __name__ == '__main__':
    unittest.main()
