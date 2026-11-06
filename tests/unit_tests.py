# -*- coding: utf-8 -*-
"""
Unit tests for single functions of the districtgenerator.

The expected values are calculated by hand, so the tests do not depend on data files or other modules.
"""
import unittest
from copy import deepcopy
from itertools import product
from types import SimpleNamespace

import numpy as np

from districtgenerator.time_series.resolution import changeResolution
from districtgenerator.economics.price_paths import calculate_eco_data_per_simulated_year
from districtgenerator.energy_systems.building_energy_system import BES
from districtgenerator.buildings import thermal
from districtgenerator.buildings.thermal.model_four_elements.simulation import (prepare_gains_from_envelope,
                                                                                simulate_4element)
from districtgenerator.time_series.clustering import select_profile_periods
from districtgenerator.optimization.energy_hub_sizing import _discount_factor
from districtgenerator.optimization.energy_hub_parameters import calc_monthly_dem


class TestChangeResolution(unittest.TestCase):
    """Unit tests for changeResolution of the time_series package."""

    def test_mean_downsampling(self):
        """Quarter-hourly values are averaged to hourly values."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
        result = changeResolution(values, 900, 3600, "mean")
        np.testing.assert_allclose(result, [2.5, 6.5])

    def test_sum_downsampling_keeps_energy(self):
        """Quarter-hourly values are summed to hourly values and the total stays the same."""
        values = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
        result = changeResolution(values, 900, 3600, "sum")
        np.testing.assert_allclose(result, [10, 26])
        self.assertAlmostEqual(result.sum(), values.sum())

    def test_mean_upsampling_interpolates(self):
        """Hourly values are linearly interpolated to half-hourly values, the last value is held."""
        values = np.array([0, 2], dtype=float)
        result = changeResolution(values, 3600, 1800, "mean")
        np.testing.assert_allclose(result, [0, 1, 2, 2])

    def test_mean_incomplete_last_step(self):
        """If the last new time step is not completely covered, the last old value is repeated."""
        values = np.array([1, 2, 3], dtype=float)
        result = changeResolution(values, 900, 1800, "mean")
        np.testing.assert_allclose(result, [1.5, 3])

    def test_same_resolution(self):
        """The values do not change if the old and new resolution are the same."""
        values = np.array([4, 1, 7, 3], dtype=float)
        for method in ("mean", "sum"):
            with self.subTest(method=method):
                np.testing.assert_allclose(changeResolution(values, 3600, 3600, method), values)

    def test_unknown_method(self):
        """An unknown aggregation method raises a ValueError."""
        with self.assertRaises(ValueError):
            changeResolution(np.ones(4), 900, 3600, "max")


class TestEconomicYearGroups(unittest.TestCase):
    """Check representative prices and emission factors against simple averages."""

    def setUp(self):
        self.eco_data = {
            "observation_time": 5,
            "interpolation_points": [0, 2],
            "num_interpolation_points": None,
            "interest_rate": 1.0,
            "optimization_focus": 0,
            "price_supply_el": [10, 40, 20, 80, 160],
            "co2_el_grid": [1, 3, 2, 4, 6],
        }

    def test_discounted_prices_and_undiscounted_emissions(self):
        """Group prices use discount weights while CO2 factors remain plain means."""
        original = deepcopy(self.eco_data)
        result = calculate_eco_data_per_simulated_year(self.eco_data)

        # A deliberately simple 100% rate gives weights 1, 1/2, 1/4.
        # Years 0–1: (10 + 20) / 1.5 = 20.
        # Years 2–4: (20 + 40 + 40) / 1.75 = 400/7.
        self.assertEqual(set(result), {0, 2})
        self.assertAlmostEqual(result[0]["price_supply_el"], 20)
        self.assertAlmostEqual(result[2]["price_supply_el"], 400 / 7)
        self.assertAlmostEqual(result[0]["co2_el_grid"], 2)
        self.assertAlmostEqual(result[2]["co2_el_grid"], 4)
        for year in (0, 2):
            self.assertEqual(result[year]["observation_time"], 5)
            self.assertEqual(result[year]["interpolation_points"], [0, 2])
        self.assertEqual(self.eco_data, original)

class TestBuildingDeviceSizing(unittest.TestCase):
    """Check heating and DHW capacities without profiles from external files."""

    def setUp(self):
        self.system = BES(
            physics={},
            decentral_device_data={
                code: {} for code in ("HP", "BOI", "EH", "TES_DHW", "EH_DHW")
            },
            design_building_data={"T_bivalent": 0, "T_heatlimit": 15},
        )
        self.site = {"T_ne": -10}
        self.building = {
            "buildingFeatures": {"heater": "BOI", "dhw_heater": None},
            "envelope": SimpleNamespace(
                heatload=10000, heatlimit=0, coolingload=0
            ),
            "user": SimpleNamespace(
                dhw_minutely=np.full(120, 1000.0)
            ),
        }

    def test_boiler_covers_space_heating_and_buffered_dhw(self):
        """Buffering a short DHW peak avoids sizing the boiler for that raw peak."""
        # One minute at 61 kW and 59 minutes at 1 kW average to 2 kW.
        self.building["user"].dhw_minutely[60] = 61000
        capacities = self.system.designECS(self.building, self.site)
        self.assertAlmostEqual(capacities["BOI"], 12000)
        self.assertAlmostEqual(capacities["TES_DHW"], 2000)
        self.assertEqual(capacities["HP"], 0)
        self.assertEqual(capacities["EH_DHW"], 0)

    def test_heat_pump_and_backup_cover_the_design_load(self):
        """The heat pump covers 6 kW; backup covers 4 kW plus 1 kW DHW."""
        self.building["buildingFeatures"]["heater"] = "HP"
        capacities = self.system.designECS(self.building, self.site)
        self.assertAlmostEqual(capacities["HP"], 6000)
        self.assertAlmostEqual(capacities["EH"], 5000)
        self.assertAlmostEqual(capacities["TES_DHW"], 1000)
        self.assertEqual(capacities["BOI"], 0)


class TestFourElementsGains(unittest.TestCase):
    """Check that solar and internal gains reach the four-element solver."""

    def setUp(self):
        self.envelope = SimpleNamespace(Q_il_kon=np.array([100.0, 200.0]),
                                        Q_il_str=np.array([10.0, 20.0]),
                                        internal_gains=np.array([1000.0, 500.0]))

    def test_default_split_of_internal_gains(self):
        """Internal gains are split into 60% radiative and 40% convective and added to the solar gains."""
        gains = prepare_gains_from_envelope(self.envelope)
        np.testing.assert_allclose(gains["Q_kon"], [100 + 400, 200 + 200])
        np.testing.assert_allclose(gains["Q_rad"], [10 + 600, 20 + 300])

    def test_custom_radiative_share(self):
        """The radiative share of the internal gains can be changed."""
        gains = prepare_gains_from_envelope(self.envelope, rad_frac=0.25)
        np.testing.assert_allclose(gains["Q_kon"], [100 + 750, 200 + 375])
        np.testing.assert_allclose(gains["Q_rad"], [10 + 250, 20 + 125])

    def test_different_lengths_raise_error(self):
        """Internal gains of a different length raise a ValueError instead of being cut or filled up."""
        for internal_gains in (np.ones(1), np.ones(3)):
            with self.subTest(length=len(internal_gains)):
                self.envelope.internal_gains = internal_gains
                with self.assertRaises(ValueError):
                    prepare_gains_from_envelope(self.envelope)

    def test_missing_internal_gains_raise_error(self):
        """An envelope without internal gains raises an error instead of simulating without them."""
        del self.envelope.internal_gains
        with self.assertRaises(AttributeError):
            prepare_gains_from_envelope(self.envelope)

    def test_simulation_includes_internal_gains(self):
        """Without heating and heat losses through the envelope, all gains must leave with the ventilation."""
        n = 3
        # Ventilation: 1 kg/m3 * 1000 J/(kgK) * 1 1/h * 36 m3 / 3600 s/h = 10 W/K
        envelope = SimpleNamespace(rho_air=1.0, c_p_air=1000.0, ventilationRate=1.0, V=36.0,
                                   T_set_min=20.0,
                                   Q_il_kon=np.full(n, 100.0),
                                   Q_il_str=np.full(n, 100.0),
                                   internal_gains=np.full(n, 800.0))
        for prefix in ("ew", "r", "f", "iw"):
            for attribute, value in (("C", 1e5), ("R1", 0.01), ("Rrest", 1e15), ("A", 10.0),
                                     ("h_conv", 2.0), ("h_rad", 5.0)):
                setattr(envelope, f"{attribute}_{prefix}", value)

        # With very long time steps, the zone reaches its steady state.
        result = simulate_4element(envelope, T_ext=np.full(n, 10.0), dt_s=1e9, T_set_heat=np.full(n, -1000.0),
                                   T_set_cool=np.full(n, 1000.0), calendar=None)

        # 100 W + 100 W + 800 W = 1000 W, so the air is 1000 W / 10 W/K = 100 K warmer than outside.
        self.assertAlmostEqual(result["T_air"][-1], 110.0, delta=0.01)
        # The radiative gains of 100 W + 60% * 800 W = 580 W flow to the air through the surfaces.
        # T_rad - T_air = 580 W * (1 / (4 * 50 W/K) + 1 / (4 * 20 W/K)) = 10.15 K, with T_op as the mean of both.
        self.assertAlmostEqual(result["T_op"][-1], 110.0 + 0.5 * 10.15, delta=0.01)
        self.assertEqual(result["Q_H"][-1], 0)
        self.assertEqual(result["Q_C"][-1], 0)


class TestThermalModelCalc(unittest.TestCase):
    """
    Check calc and calc_night_setback of all thermal models against hand-calculated steady states.

    The only heat loss of the zone is the ventilation with 100 W/K and the capacities are negligible,
    so a constant outside temperature T_e gives Q_H = 100 W/K * (T_set - T_e), for all thermal models.
    """
    MODELS = ("5R1C", "7R2C", "FourElements")
    FUNCTIONS = ("calc", "calc_night_setback")
    DT = 6.0  # A year of 1460 steps of 6 h, so the steps of a day are at 0, 6, 12 and 18 h
    STEPS = 1460

    @staticmethod
    def _envelope(model, heatload=1e6, coolingload=1e6, gain=0.0):
        """Minimal envelope of a thermal model. `gain` is a heat gain in W directly at the air node."""
        gains, zeros = np.full(TestThermalModelCalc.STEPS, gain), np.zeros(TestThermalModelCalc.STEPS)
        envelope = SimpleNamespace(T_set_min=20.0, T_set_min_night=17.0, T_set_min_free_day=15.0, T_set_max=26.0,
                                   T_set_max_night=28.0, heatload=heatload, coolingload=coolingload)
        if model == "5R1C":
            vars(envelope).update(H_ve=100.0, H_tr_is=1000.0, H_tr_ms=1000.0, H_tr_w=0.0, H_tr_em=[0.0], C_m=1.0,
                                  phi_ia=gains, phi_m=zeros, phi_st=zeros)
            return envelope
        # 1 kg/m3 * 1000 J/(kgK) * 360 m3/h / 3600 s/h = 100 W/K
        vars(envelope).update(rho_air=1.0, c_p_air=1000.0, V=1.0, Q_il_kon=gains, Q_il_str=zeros, internal_gains=zeros)
        if model == "7R2C":
            vars(envelope).update(V_dot=0.0, V_dot_infiltration=360.0, eta_temp_vent=0.0, C1IW=1.0, C1AW=1.0,
                                  R1IW=0.01, R1AW=0.01, RrestAW=1e15, RalphaStarIW=0.01, RalphaStarAW=0.01,
                                  UA_tot=0.0, Aaw_tot=1.0, Araum_tot=2.0, theta_eq_tot=zeros)
        else:
            envelope.ventilationRate = 360.0
            for prefix in ("ew", "r", "f", "iw"):
                vars(envelope).update({f"C_{prefix}": 1.0, f"R1_{prefix}": 0.01, f"Rrest_{prefix}": 1e15,
                                       f"A_{prefix}": 10.0, f"h_conv_{prefix}": 10.0, f"h_rad_{prefix}": 5.0})
        return envelope

    def _assert_step(self, model, function, T_e, step, Q_H, Q_C, T_op, building="SFH", **envelope_args):
        """Run a simulation with constant T_e, starting on a Monday, and check one time step."""
        calendar = {"heating_period_start": 259, "heating_period_end": 135, "cooling_period_start": 105,
                    "cooling_period_end": 273, "consider_heating_period": True, "consider_cooling_period": True,
                    "holidays": [2]}
        result = getattr(thermal.get_simulation(model), function)(
            self._envelope(model, **envelope_args), np.full(self.STEPS, float(T_e)), calendar, self.DT, 0, building)
        with self.subTest(model=model, function=function, T_e=T_e, step=step, building=building, **envelope_args):
            self.assertAlmostEqual(result[0][step], Q_H, delta=0.5)
            self.assertAlmostEqual(result[1][step], Q_C, delta=0.5)
            self.assertAlmostEqual(result[2][step], T_op, delta=0.01)

    def _cases(self):
        """All combinations of thermal model and function."""
        return product(self.MODELS, self.FUNCTIONS)

    @staticmethod
    def _noon(day):
        """Index of the time step at 12:00 of a day, counted from 0."""
        return day * 4 + 2

    def test_heating(self):
        """Heating holds the setpoint in the heating period, up to the heat load, and is off outside of it."""
        for model, function in self._cases():
            self._assert_step(model, function, 0, self._noon(10), 2000, 0, 20)
            self._assert_step(model, function, 0, self._noon(10), 500, 0, 5, heatload=500.0)
            self._assert_step(model, function, 0, self._noon(200), 0, 0, 0)

    def test_cooling(self):
        """Cooling holds the setpoint in the cooling period, up to the cooling load, and is off outside of it."""
        for model, function in self._cases():
            self._assert_step(model, function, 40, self._noon(150), 0, 1400, 26)
            self._assert_step(model, function, 40, self._noon(150), 0, 700, 33, coolingload=700.0)
            self._assert_step(model, function, 40, self._noon(10), 0, 0, 40)

    def test_deadband(self):
        """Between the setpoints, neither heating nor cooling is used, even if both periods are active."""
        for model, function in self._cases():
            self._assert_step(model, function, 22, self._noon(120), 0, 0, 22)

    def test_gains_reduce_heating(self):
        """A gain of 500 W replaces 500 W of the heating."""
        for model, function in self._cases():
            self._assert_step(model, function, 0, self._noon(10), 1500, 0, 20, gain=500.0)

    def test_night_setback_of_residential_buildings(self):
        """Only calc_night_setback lowers the setpoint at night, and neither lowers it during the day."""
        midnight = 10 * 4
        for model in self.MODELS:
            self._assert_step(model, "calc", 0, midnight, 2000, 0, 20)
            self._assert_step(model, "calc_night_setback", 0, midnight, 1700, 0, 17)
            self._assert_step(model, "calc_night_setback", 0, self._noon(10), 2000, 0, 20)



class TestSelectProfilePeriods(unittest.TestCase):
    """Unit tests for select_profile_periods of the time_series package."""

    # Three periods of four time steps (0-3, 4-7, 8-11) and an incomplete fourth period (12, 13)
    PROFILE = np.arange(14, dtype=float)

    def test_selects_periods_in_given_order(self):
        """The periods are returned as rows in the order of typedays."""
        result = select_profile_periods(self.PROFILE, [2, 0], 4, 12)
        np.testing.assert_array_equal(result, [[8, 9, 10, 11], [0, 1, 2, 3]])

    def test_ignores_incomplete_period(self):
        """Time steps after length_array are not used."""
        result = select_profile_periods(self.PROFILE, [0, 1, 2], 4, 12)
        self.assertEqual(result.shape, (3, 4))
        self.assertEqual(result.max(), 11)

    def test_none_profile(self):
        """A missing profile stays missing."""
        self.assertIsNone(select_profile_periods(None, [0], 4, 12))


class TestDiscountFactor(unittest.TestCase):
    """Unit tests for _discount_factor of the central dimensioning optimization."""

    def test_zero_interest_rate(self):
        """Without interest, the discount factor is the interval length."""
        self.assertEqual(_discount_factor(5, 5, 0), 5)

    def test_first_year_is_discounted(self):
        """Support year 0 refers to the first year of VDI 2067, so it is already discounted once."""
        self.assertAlmostEqual(_discount_factor(0, 1, 0.05), 1 / 1.05)

    def test_interval_from_first_year(self):
        """Interval of three years from support year 0: 1/1.1 + 1/1.1^2 + 1/1.1^3."""
        self.assertAlmostEqual(_discount_factor(0, 3, 0.1), 2.486851991, places=8)

    def test_interval_from_later_year(self):
        """Interval of two years from support year 5: 1/1.1^6 + 1/1.1^7."""
        self.assertAlmostEqual(_discount_factor(5, 2, 0.1), 1.077632048, places=8)

    def test_intervals_cover_observation_period(self):
        """The intervals of all support years add up to the present value factor of the whole period."""
        interest_rate = 0.05
        intervals = {0: 5, 5: 5, 10: 10}  # support years [0, 5, 10] and an observation period of 20 years
        total = sum(_discount_factor(year, length, interest_rate) for year, length in intervals.items())
        self.assertAlmostEqual(total, (1 - 1.05 ** -20) / 0.05)


class TestCalcMonthlyDem(unittest.TestCase):
    """Unit tests for calc_monthly_dem of the central parameter preparation."""

    @staticmethod
    def _demands(values):
        """Same profile for heat, cooling and power."""
        return {m: np.array(values, dtype=float) for m in ("heat", "cool", "power")}

    def test_constant_hourly(self):
        """Constant 1 kW in hourly resolution: 744 h in January, 672 h in February, 8760 h per year."""
        result = calc_monthly_dem(self._demands(np.ones(8760)), 3600, {})
        self.assertAlmostEqual(result["monthly_dem"]["heat"]["Jan"], 0.744)
        self.assertAlmostEqual(result["monthly_dem"]["heat"]["Feb"], 0.672)
        self.assertEqual(result["year_sum"]["heat"], 8)
        self.assertEqual(result["year_peak"]["heat"], 1)

    def test_constant_quarter_hourly(self):
        """The same constant demand in quarter-hourly resolution gives the same energy."""
        result = calc_monthly_dem(self._demands(np.ones(35040)), 900, {})
        self.assertAlmostEqual(result["monthly_dem"]["cool"]["Jan"], 0.744)
        self.assertAlmostEqual(result["monthly_dem"]["cool"]["Dec"], 0.744)
        self.assertEqual(result["year_sum"]["cool"], 8)

    def test_month_boundaries(self):
        """A demand only in January is completely assigned to January."""
        values = np.zeros(8760)
        values[:744] = 2
        result = calc_monthly_dem(self._demands(values), 3600, {})
        self.assertAlmostEqual(result["monthly_dem"]["power"]["Jan"], 1.488)
        self.assertAlmostEqual(sum(result["monthly_dem"]["power"].values()), 1.488)

    def test_peak(self):
        """The annual peak is the maximum demand value in kW."""
        values = np.ones(8760)
        values[4000] = 50
        result = calc_monthly_dem(self._demands(values), 3600, {})
        self.assertEqual(result["year_peak"]["heat"], 50)


if __name__ == '__main__':
    unittest.main()
