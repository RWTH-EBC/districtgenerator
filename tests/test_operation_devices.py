# -*- coding: utf-8 -*-
"""
Checks that every device of the central operation optimization is completely integrated into the model.

Part 1 compares the device lists at the top of operation.py with each other. Part 2 builds the model
with small mock data and checks every device in the model and in the result extraction. The model is
not solved, so no solver is needed.

The device lists are read from operation.py, so new devices are checked automatically. If a new device
needs new parameters, they have to be added to the mock data below.
"""
import tempfile
import types
import unittest
import warnings
from unittest import mock

import numpy as np
import pyomo.environ as pyo
from pyomo.contrib.fbbt.fbbt import fbbt
from pyomo.repn import generate_standard_repn

import districtgenerator.optimization.operation as op

# Some devices list the same carrier under two names ("biomass" in the buildings, "biom" in the energy hub)
CARRIER_ALIASES = {"biom": "biomass"}
EH_CARRIER_NAMES = {"biomass": "biom"}

DOM_CARRIER_SETS = {"heat": op.ECS_HEAT, "power": op.ECS_POWER, "cool": op.ECS_COOL, "gas": op.ECS_GAS,
                    "biomass": op.ECS_BIOMASS, "hydrogen": op.ECS_HYDROGEN, "oil": op.ECS_OIL}
EH_CARRIER_SETS = {"heat": op.EH_ECS_HEAT, "power": op.EH_ECS_POWER, "cool": op.EH_ECS_COOL, "gas": op.EH_ECS_GAS,
                   "biomass": op.EH_ECS_BIOMASS, "hydrogen": op.EH_ECS_HYDROGEN, "oil": op.EH_ECS_OIL,
                   "waste": op.EH_ECS_WASTE}

EH_CONVERTERS = [dev for dev in op.EH_DEVS if dev not in op.EH_ECS_STORAGE]
DOM_CONVERTERS = [dev for dev in op.DOM_DEVS if dev not in op.ECS_STORAGE]

# Devices with a known missing capacity limit, see test_sab_has_capacity_limit
KNOWN_UNBOUNDED = {("eh", "SAB")}

NUM_STEPS = 24  # one day in hourly resolution
ZERO_CAPACITY_STEPS = 4  # shorter horizon for the bound propagation in TestZeroCapacity


def _carriers(dev):
    """Energy carriers of a device from DEVICE_MAPPING as {carrier: 'gen' or 'cons'}, aliases merged."""
    return {CARRIER_ALIASES.get(carrier, carrier): target
            for target, carriers in op.DEVICE_MAPPING[dev].items() for carrier in carriers}


def make_mock_data(num_steps=NUM_STEPS):
    """
    Small district with two buildings and an energy hub, in which every device has a capacity.

    Building 0 uses the main heater for DHW, building 1 has a separate DHW heater (EH_DHW).
    """
    rng = np.random.default_rng(0)

    def profile(scale):
        return [rng.random(num_steps) * scale]

    def building(dhw_heater):
        user = types.SimpleNamespace(dhw_cluster=profile(500), heat_cluster=profile(3000), cooling_cluster=profile(500),
                                     elec_cluster=profile(800), occ_cluster=profile(1),
                                     generationPV_cluster=profile(2000), generationSTC_cluster=profile(1000))
        envelope = types.SimpleNamespace(heating_curve={"clustered": {"low_temp_measures_binding": False,
                                                                      "Ts_curve": np.full((1, num_steps), 45.0)}})
        capacities = {dev: 5000 for dev in set(op.DOM_DEVS) | set(op.DEVICE_MAPPING)}
        capacities["heat_grid"] = 1
        return {"user": user, "envelope": envelope, "capacities": capacities,
                "buildingFeatures": {"dhw_heater": dhw_heater, "heater": "HP", "cooler": "CC", "cooling": True,
                                     "ev_charging": "on_demand"}}

    storage = {"init": 0.5, "eta_standby": 0.99, "eta_ch": 0.95, "coeff_ch": 1.0, "soc_max": 1.0, "soc_min": 0.0}
    decentral = {"HP": {"grade": 0.4}, "TES": dict(storage), "TES_DHW": dict(storage, T_DHW_needed=55),
                 "BAT": dict(storage), "EV": dict(storage), "EH": {"eta_th": 1.0}, "EH_DHW": {"eta_th": 1.0},
                 "CHP": {"eta_th": 0.6, "eta_el": 0.3}, "BOI": {"eta_th": 0.95}, "BBOI": {"eta_th": 0.9},
                 "OBOI": {"eta_th": 0.9}, "H2BOI": {"eta_th": 0.9}, "DH": {"eta_th": 1.0},
                 "FC": {"eta_th": 0.4, "eta_el": 0.5}, "CC": {"grade": 0.3}}
    central = {dev: {"eta_th": 0.9, "eta_el": 0.3, "COP": 1.5, "eta": 0.8, "sto_loss": 0.01} for dev in op.EH_DEVS}

    cop = {dev: {"COP": [[np.full(num_steps, 3.0)]]} for dev in ("HP", "GroundHP", "CC")}
    eh_capacities = {dev: {"cap": 100} for dev in op.EH_DEVS + ["from_grid", "to_grid"]}
    eh_capacities["devs"] = cop
    energy_hub = {"capacities": eh_capacities,
                  "generation": {"PV_cluster": profile(50), "STC_cluster": profile(50), "Wind_cluster": profile(50)}}
    heat_grid = {"total_losses_heating_network_cluster": [np.zeros(num_steps)],
                 "total_losses_cooling_network_cluster": [np.zeros(num_steps)],
                 "pump_power_cluster": [np.zeros(num_steps)]}

    return types.SimpleNamespace(time={"clusterLength": num_steps * 3600, "timeResolution": 3600, "dataResolution": 3600},
                                 site={"T_e_cluster": [rng.random(num_steps) * 10], "trafoMax_W": 1e6,
                                       "enable_trafoMax_W": True, "buildingMax_W": 1e5, "enable_buildingMax_W": True},
                                 decentral_device_data=decentral, central_device_data=central,
                                 district=[building(None), building("EH_DHW")], centralDevices=energy_hub,
                                 heat_grid_data=heat_grid, pyomo_config={})


ECO_DATA = {"price_supply_el": 0.3, "revenue_feed_in_el": 0.08, "price_supply_el_eh": 0.16, "revenue_feed_in_el_eh": 0.08,
            "price_supply_gas": 0.12, "price_supply_gas_eh": 0.08, "revenue_feed_in_gas": 0.02, "price_hydrogen": 0.1,
            "price_biomass": 0.05, "price_waste": 0.1, "price_oil": 0.9, "price_district_heat": 0.16,
            "co2_el_grid": 0.4, "co2_gas": 0.2, "co2_hydrogen": 0.04, "co2_biom": 0.02, "co2_waste": 0.1,
            "co2_oil": 0.27, "co2_district_heat": 0.2, "optimization_focus": 0}


class TestDeviceLists(unittest.TestCase):
    """The device lists at the top of operation.py fit together."""

    def test_converters_have_mapping(self):
        """Every device that is not a storage has an entry in DEVICE_MAPPING (otherwise it is missing in the results)."""
        for dev in sorted(set(EH_CONVERTERS + DOM_CONVERTERS)):
            with self.subTest(device=dev):
                self.assertIn(dev, op.DEVICE_MAPPING)

    def test_mapping_devices_are_used(self):
        """Every device in DEVICE_MAPPING is a device of the energy hub or the buildings."""
        for dev in op.DEVICE_MAPPING:
            with self.subTest(device=dev):
                self.assertTrue(dev in op.EH_DEVS or dev in op.DOM_DEVS, f"{dev} is neither in EH_DEVS nor in DOM_DEVS")

    def test_storages_are_devices(self):
        """The storage lists are part of the device lists."""
        self.assertLessEqual(set(op.ECS_STORAGE), set(op.DOM_DEVS))
        self.assertLessEqual(set(op.EH_ECS_STORAGE), set(op.EH_DEVS))

    def test_carrier_sets(self):
        """Every device is in the carrier sets (ECS_*, EH_ECS_*) of all carriers it generates or consumes."""
        for location, devices, carrier_sets in (("dom", DOM_CONVERTERS, DOM_CARRIER_SETS),
                                                ("eh", EH_CONVERTERS, EH_CARRIER_SETS)):
            for dev in devices:
                if dev not in op.DEVICE_MAPPING:  # checked in test_converters_have_mapping
                    continue
                for carrier in _carriers(dev):
                    with self.subTest(location=location, device=dev, carrier=carrier):
                        self.assertIn(dev, carrier_sets[carrier])


class TestDeviceIntegration(unittest.TestCase):
    """Every device is completely integrated into the model of the operation optimization."""

    @classmethod
    def setUpClass(cls):
        cls.data = make_mock_data()
        cls.model = pyo.ConcreteModel()
        op.build_model(cls.model, cls.data, 0, 0, ECO_DATA)
        cls.buildings = list(cls.model.n)

        # Variables of every constraint and constraints of every variable
        cls.constraints_of = {}
        cls.variables_in = {}
        for con in cls.model.component_data_objects(pyo.Constraint, active=True, descend_into=True):
            variables = list(pyo.expr.identify_variables(con.body))
            cls.variables_in[con] = variables
            for var in variables:
                cls.constraints_of.setdefault(id(var), []).append(con)

    def _device_variables(self, location, dev):
        """All variables of a device in the energy hub ("eh") or in the buildings ("dom")."""
        variables = []
        for comp in self.model.component_objects(pyo.Var):
            if location == "eh":
                if comp.name.startswith("eh_") and comp.name.endswith(f"_{dev}"):
                    variables.extend(comp.values())
            elif not comp.name.startswith("eh_"):
                variables.extend(var for index, var in comp.items()
                                 if isinstance(index, tuple) and len(index) == 3 and index[0] == dev)
        return variables

    def _carrier_variables(self, location, dev, carrier):
        """
        Variables of one energy carrier of a device in the first time step.

        In the buildings there is one variable per building, split variables like heat_dom_SH of the heat pump
        are included.
        """
        if location == "eh":
            comp = getattr(self.model, f"eh_{EH_CARRIER_NAMES.get(carrier, carrier)}_{dev}", None)
            return [] if comp is None else [comp[0]]
        return [comp[dev, n, 0] for comp in self.model.component_objects(pyo.Var)
                if comp.name == f"{carrier}_dom" or comp.name.startswith(f"{carrier}_dom_")
                for n in self.buildings if (dev, n, 0) in comp]

    def _is_upper_limit(self, con):
        """True if the constraint limits a single variable with a constant from above (e.g. a capacity)."""
        repn = generate_standard_repn(con.body)
        if not repn.is_linear() or len(repn.linear_vars) != 1:
            return False
        coef = repn.linear_coefs[0]
        return (coef > 0 and con.has_ub()) or (coef < 0 and con.has_lb())

    def _all_devices(self):
        """All converting devices as (location, device)."""
        return [("eh", dev) for dev in EH_CONVERTERS] + [("dom", dev) for dev in DOM_CONVERTERS]

    def _is_coupled(self, var, own):
        """True if the variable appears in a constraint together with a variable that is not in own (e.g. a balance)."""
        return any(id(other) not in own
                   for con in self.constraints_of.get(id(var), [])
                   for other in self.variables_in[con])

    def _assert_bounded(self, location, dev):
        bounded = any(self._is_upper_limit(con)
                      for var in self._device_variables(location, dev)
                      for con in self.constraints_of.get(id(var), []))
        self.assertTrue(bounded, f"No capacity or generation limit found for {dev} ({location})")

    def test_carrier_variables_exist(self):
        """Every device has a variable for every energy carrier in DEVICE_MAPPING."""
        for location, dev in self._all_devices():
            for carrier in _carriers(dev):
                with self.subTest(location=location, device=dev, carrier=carrier):
                    self.assertTrue(self._carrier_variables(location, dev, carrier),
                                    f"No {carrier} variable found for {dev} ({location})")

    def test_carriers_in_energy_balances(self):
        """Every carrier variable is coupled to the rest of the system, i.e. it appears in a balance with other devices or the grid."""
        for location, dev in self._all_devices():
            own = {id(var) for var in self._device_variables(location, dev)}
            for carrier in _carriers(dev):
                with self.subTest(location=location, device=dev, carrier=carrier):
                    coupled = any(self._is_coupled(var, own) for var in self._carrier_variables(location, dev, carrier))
                    self.assertTrue(coupled, f"The {carrier} of {dev} ({location}) does not appear in an energy balance")

    def test_storages_in_energy_balances(self):
        """Charging and discharging of every storage appear in an energy balance."""
        storages = [("eh", dev, getattr(self.model, f"eh_{var_type}_{dev}")[0], var_type)
                    for dev in op.EH_ECS_STORAGE for var_type in ("ch", "dch")]
        storages += [("dom", dev, getattr(self.model, f"{var_type}_dom")[dev, 0, 0], var_type)
                     for dev in op.ECS_STORAGE for var_type in ("ch", "dch")]
        for location, dev, var, var_type in storages:
            with self.subTest(location=location, device=dev, variable=var_type):
                own = {id(own_var) for own_var in self._device_variables(location, dev)}
                self.assertTrue(self._is_coupled(var, own),
                                f"{var_type} of {dev} ({location}) does not appear in an energy balance")

    def test_devices_bounded(self):
        """Every device is limited by a capacity or a generation potential."""
        for location, dev in self._all_devices():
            if (location, dev) in KNOWN_UNBOUNDED:
                continue
            with self.subTest(location=location, device=dev):
                self._assert_bounded(location, dev)

    def test_storages_bounded(self):
        """The state of charge of every storage is limited by its capacity."""
        for location, dev in [("eh", dev) for dev in op.EH_ECS_STORAGE] + [("dom", dev) for dev in op.ECS_STORAGE]:
            with self.subTest(location=location, device=dev):
                self._assert_bounded(location, dev)

    @unittest.expectedFailure
    def test_sab_has_capacity_limit(self):
        """Known bug: the Sabatier reactor of the energy hub has no capacity limit (see open issue K)."""
        self._assert_bounded("eh", "SAB")

    def test_devices_in_results(self):
        """Every device appears with all its energy carriers in the extracted results."""
        model = self.model
        for var in model.component_data_objects(pyo.Var):
            var.value = 1
        solved = types.SimpleNamespace(solver=types.SimpleNamespace(termination_condition=pyo.TerminationCondition.optimal))
        with tempfile.TemporaryDirectory() as result_path, \
                mock.patch.object(op.solver_config, "execute_and_diagnose", return_value=solved), \
                mock.patch.object(op.solver_config, "write_solution_file"):
            results = op.solve_model_and_extract_results(model, self.data, 0, 0, result_path)

        device_results = [(location, dev, results["energy_hub"].get(dev)) for location, dev in self._all_devices()
                          if location == "eh"]
        device_results += [(location, dev, results[n].get(dev)) for location, dev in self._all_devices()
                           if location == "dom" for n in self.buildings]
        for location, dev, dev_results in device_results:
            with self.subTest(location=location, device=dev):
                self.assertIsNotNone(dev_results, f"{dev} ({location}) is missing in the results")
                for carrier, target in _carriers(dev).items():
                    names = {carrier} | {alias for alias, name in CARRIER_ALIASES.items() if name == carrier}
                    self.assertTrue(any(f"{target}_{name}" in dev_results for name in names),
                                    f"{target}_{carrier} of {dev} ({location}) is missing in the results")

        for dev in op.EH_ECS_STORAGE:
            with self.subTest(location="eh", device=dev):
                self.assertIn("ch", results["energy_hub"].get(dev, {}))
        for n in self.buildings:
            for dev in op.ECS_STORAGE:
                with self.subTest(location="dom", device=dev, building=n):
                    self.assertIn("ch", results[n].get(dev, {}))


class TestZeroCapacity(unittest.TestCase):
    """A building device without capacity can neither generate nor consume energy."""

    # The cooling demand of the mock buildings can only be covered by the chiller
    SKIPPED = {"CC"}

    def test_all_variables_zero(self):
        """
        With capacity 0 in all buildings, bound propagation (FBBT) bounds every variable of the device to 0.

        A variable that is not bounded, e.g. the electricity of a heat pump without capacity, could be used
        by the optimization to consume energy without a device.
        """
        for dev in op.DOM_DEVS:
            if dev in self.SKIPPED:
                continue
            with self.subTest(device=dev):
                data = make_mock_data(num_steps=ZERO_CAPACITY_STEPS)
                for building in data.district:
                    building["capacities"][dev] = 0
                    if dev == "PV":
                        building["user"].generationPV_cluster = [np.zeros(ZERO_CAPACITY_STEPS)]
                    if dev == "STC":
                        building["user"].generationSTC_cluster = [np.zeros(ZERO_CAPACITY_STEPS)]
                model = pyo.ConcreteModel()
                op.build_model(model, data, 0, 0, ECO_DATA)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)  # inf * 0 in the interval arithmetic of FBBT
                    fbbt(model, deactivate_satisfied_constraints=False)
                not_zero = sorted({comp.name for comp in model.component_objects(pyo.Var)
                                   for index, var in comp.items()
                                   if isinstance(index, tuple) and len(index) == 3 and index[0] == dev
                                   and (var.ub is None or var.ub > 1e-6)})
                self.assertEqual(not_zero, [], f"Variables of {dev} are not bounded to 0 without capacity")


if __name__ == '__main__':
    unittest.main()
