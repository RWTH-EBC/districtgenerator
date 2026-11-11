# -*- coding: utf-8 -*-
"""
Tests of the clustering of the time_series package.

TestMedoidCluster solves the k-medoids clustering with tsam and HiGHS on small synthetic profiles,
so the expected assignment of the periods is known. TestProfileMapping checks that every clustered
profile of the district ends up in the right attribute.
"""
import types
import unittest
import warnings

import numpy as np
import pyomo.environ as pyo

from districtgenerator.time_series import clustering, medoid

HIGHS = {"solver_name": "highs"}
STEPS = 24  # time steps per period

BUILDING_PROFILE_NAMES = ("elec", "dhw", "heat", "cooling", "occ", "EV_carcharging_ondemand", "EV_carprofile",
                          "generationPV", "generationSTC")
CAR_PROFILE_NAMES = ("availability_profile", "consumption_profile_wh", "on_demand_charging_profile_w",
                     "fuel_profile_l")


def two_pattern_profile():
    """Six periods with two patterns: A in the even periods (0, 2, 4), B in the odd periods (1, 3, 5)."""
    pattern_a = np.sin(np.linspace(0, 3, STEPS))
    pattern_b = np.cos(np.linspace(0, 3, STEPS))
    periods = [pattern_a, pattern_b, pattern_a + 0.01, pattern_b + 0.02, pattern_a - 0.01, pattern_b]
    return np.concatenate(periods)


@unittest.skipUnless(pyo.SolverFactory("highs").available(exception_flag=False), "HiGHS (highspy) is not installed")
class TestMedoidCluster(unittest.TestCase):
    """medoid.cluster finds the expected clusters and returns them in the documented format."""

    @classmethod
    def setUpClass(cls):
        profile = two_pattern_profile()
        # Second input with half the values, a few time steps of an incomplete seventh period at the end
        cls.inputs = np.array([np.append(profile, [9, 9, 9]), np.append(profile / 2, [9, 9, 9])])
        cls.profiles, cls.nc, cls.y, cls.z, cls.transformed = medoid.cluster(
            cls.inputs, number_clusters=2, len_cluster=STEPS, pyomo_config=HIGHS)
        cls.medoids = list(np.flatnonzero(cls.y))

    def test_periods_grouped_by_pattern(self):
        """The periods with pattern A and pattern B form the two clusters."""
        groups = [set(np.flatnonzero(self.z[m])) for m in self.medoids]
        self.assertCountEqual(groups, [{0, 2, 4}, {1, 3, 5}])

    def test_assignment_consistent(self):
        """Every period belongs to exactly one cluster, each medoid represents itself and nc counts the periods."""
        self.assertEqual(len(self.medoids), 2)
        np.testing.assert_array_equal(self.z.sum(axis=0), np.ones(6))
        for m in self.medoids:
            self.assertEqual(self.z[m, m], 1)
        np.testing.assert_array_equal(self.nc, [self.z[m].sum() for m in self.medoids])
        self.assertEqual(self.nc.sum(), 6)

    def test_representatives_in_ascending_medoid_order(self):
        """The representative periods are the medoid periods, ordered by ascending medoid index (as callers expect)."""
        self.assertEqual(self.medoids, sorted(self.medoids))
        for i, profile in enumerate(self.profiles):
            self.assertEqual(profile.shape, (2, STEPS))
            for position, m in enumerate(self.medoids):
                np.testing.assert_allclose(profile[position], self.inputs[i, m * STEPS:(m + 1) * STEPS])

    def test_incomplete_period_ignored(self):
        """The time steps after the last complete period are not used."""
        self.assertEqual(self.z.shape, (6, 6))
        self.assertEqual(self.transformed[0].shape, (STEPS, 6))
        np.testing.assert_allclose(self.transformed[0][:, 1], self.inputs[0, STEPS:2 * STEPS])

    def test_invalid_weights_warn(self):
        """Weights with the wrong length give a warning and equal weights instead of an error."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = medoid.cluster(self.inputs, number_clusters=2, len_cluster=STEPS, weights=[1, 2, 3],
                                    pyomo_config=HIGHS)
        self.assertTrue(any("'weights' could not be processed" in str(w.message) for w in caught))
        self.assertEqual(result[1].sum(), 6)


class MockDistrict:
    """
    Small district in which every profile has its own value level.

    Each profile is level + a variation below 1, with the levels 10 apart. A clustered profile therefore
    belongs to the input profile whose level it has, so mixed up profiles are detected.
    """

    NUM_PERIODS = 10

    def __init__(self):
        self.rng = np.random.default_rng(1)
        self.next_level = 10
        self.levels = {}  # label -> level
        length = self.NUM_PERIODS * STEPS + 5  # with an incomplete last period

        self.district = []
        for b in range(2):
            user = types.SimpleNamespace()
            for name in BUILDING_PROFILE_NAMES:
                setattr(user, name, self.profile(f"building {b} {name}", length))
            # The first car has all profiles, the second one only some of them
            user.individual_car_profiles = []
            for c, missing in enumerate(((), ("consumption_profile_wh", "fuel_profile_l"))):
                car = {"car_id": f"car_{b}_{c}", "type": "EV", "location": b, "battery_capacity_wh": 50000 + c}
                for name in CAR_PROFILE_NAMES:
                    car[name] = None if name in missing else self.profile(f"building {b} car {c} {name}", length)
                user.individual_car_profiles.append(car)
            self.district.append({"user": user, "buildingFeatures": {"f_PV1": b, "f_PV2": 0, "f_STC": 0}})

        self.site = {name: self.profile(f"site {name}", length) for name in ("T_e", "wind_speed", "SunTotal")}
        self.heat_grid_data = {name: self.profile(f"heat grid {name}", length) for name in
                               ("T_soil", "total_losses_heating_network", "total_losses_cooling_network", "pump_power")}
        self.centralDevices = {
            "capacities": {dev: {"cap": 1} for dev in ("WT", "PV", "STC")},
            "generation": {name: self.profile(f"central {name}", length) for name in ("Wind", "PV", "STC")},
        }
        self.time = {"clusterLength": STEPS * 3600, "timeResolution": 3600, "clusterNumber": 3}

    def profile(self, label, length):
        """New profile with its own level."""
        self.levels[label] = self.next_level
        self.next_level += 10
        return self.next_level - 10 + self.rng.random(length)

    def clustered(self, central):
        """All clustered profiles as {label of the input profile: clustered profile}."""
        result = {}
        for b, building in enumerate(self.district):
            user = building["user"]
            for name in BUILDING_PROFILE_NAMES:
                result[f"building {b} {name}"] = getattr(user, f"{name}_cluster")
            for c, car in enumerate(user.individual_car_profiles_cluster):
                for name in CAR_PROFILE_NAMES:
                    result[f"building {b} car {c} {name}"] = car[f"{name}_cluster"]
        result["site T_e"] = self.site["T_e_cluster"]
        result["heat grid T_soil"] = self.heat_grid_data["T_soil_cluster"]
        if central:
            for name in ("total_losses_heating_network", "total_losses_cooling_network", "pump_power"):
                key = "pump_power_cluster" if name == "pump_power" else f"{name}_cluster"
                result[f"heat grid {name}"] = self.heat_grid_data[key]
            for name in ("Wind", "PV", "STC"):
                result[f"central {name}"] = self.centralDevices["generation"][f"{name}_cluster"]
        return result


class TestProfileMapping(unittest.TestCase):
    """Every clustered profile is saved in the attribute of its input profile."""

    def assert_mapping(self, mock, central):
        clustered = mock.clustered(central)
        for building in mock.district:
            for c, car in enumerate(building["user"].individual_car_profiles_cluster):
                original = building["user"].individual_car_profiles[c]
                for key in ("car_id", "type", "location", "battery_capacity_wh"):
                    self.assertEqual(car[key], original[key])
        for label, level in mock.levels.items():
            if not central and (label.startswith("central") or label.startswith("heat grid")) \
                    and label != "heat grid T_soil":
                continue
            if label in ("site wind_speed", "site SunTotal"):
                continue  # only used for the clustering, not saved
            with self.subTest(profile=label):
                profile = np.asarray(clustered[label])
                self.assertEqual(profile.shape, (3, STEPS))
                self.assertTrue(np.all((profile >= level) & (profile < level + 1)),
                                f"{label} contains values of another profile")
        # Missing car profiles stay missing
        for b in range(len(mock.district)):
            self.assertIsNone(clustered[f"building {b} car 1 consumption_profile_wh"])
            self.assertIsNone(clustered[f"building {b} car 1 fuel_profile_l"])

    def assert_clusters(self, clusters, assignments, weights):
        self.assertEqual(len(clusters), 3)
        self.assertEqual(sorted(p for periods in assignments.values() for p in periods), list(range(MockDistrict.NUM_PERIODS)))
        self.assertEqual(sum(weights.values()), MockDistrict.NUM_PERIODS)

    @unittest.skipUnless(pyo.SolverFactory("highs").available(exception_flag=False), "HiGHS (highspy) is not installed")
    def test_clustering_processing(self):
        """clustering_processing without and with central energy supply."""
        for central in (False, True):
            with self.subTest(centralEnergySupply=central):
                mock = MockDistrict()
                clusters, assignments, weights, _, _, _ = clustering.clustering_processing(
                    mock.time, mock.site, mock.district, mock.heat_grid_data, mock.centralDevices, HIGHS, central)
                self.assert_clusters(clusters, assignments, weights)
                self.assert_mapping(mock, central)

    def test_apply_design_clustering(self):
        """apply_design_clustering with the periods of a design clustering (no solver needed)."""
        mock = MockDistrict()
        typedays = [0, 4, 7]
        cluster_matrix = np.zeros((MockDistrict.NUM_PERIODS, MockDistrict.NUM_PERIODS))
        for period in range(MockDistrict.NUM_PERIODS):
            cluster_matrix[typedays[min(period // 4, 2)], period] = 1
        mock.centralDevices["capacities"]["cluster_meta"] = {
            "clusterLength": STEPS, "typedays": np.array(typedays), "clusterMatrix": cluster_matrix}
        clustering.apply_design_clustering(mock)
        self.assert_clusters(mock.clusters, mock.clusterAssignments, mock.clusterWeights)
        self.assertEqual(mock.clusterWeights, {0: 4, 4: 4, 7: 2})
        self.assert_mapping(mock, central=True)
        # The selected periods are exactly the design periods
        np.testing.assert_array_equal(mock.site["T_e_cluster"][1], mock.site["T_e"][4 * STEPS:5 * STEPS])


if __name__ == '__main__':
    unittest.main()
