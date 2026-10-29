"""
Aliases for module paths from before the restructure by scientific workflow.

Old paths such as ``districtgenerator.classes.users`` resolve to their new
module on first import and emit a DeprecationWarning. This keeps old imports
and old pickled districts working.
"""
import importlib
import importlib.abc
import importlib.util
import sys
import warnings

OLD_TO_NEW = {
    "districtgenerator.classes.datahandler": "districtgenerator.datahandler",
    "districtgenerator.classes.envelope_5R1C": "districtgenerator.buildings.thermal.model_5r1c.envelope",
    "districtgenerator.classes.envelope_7R2C": "districtgenerator.buildings.thermal.model_7r2c.envelope",
    "districtgenerator.classes.envelope_FourElements": "districtgenerator.buildings.thermal.model_four_elements.envelope",
    "districtgenerator.classes.solar": "districtgenerator.environment.solar",
    "districtgenerator.classes.users": "districtgenerator.buildings.profiles.users",
    "districtgenerator.classes.profiles": "districtgenerator.buildings.profiles.profiles",
    "districtgenerator.classes.non_residential": "districtgenerator.buildings.typology.non_residential",
    "districtgenerator.classes.lighting_non_residential": "districtgenerator.buildings.profiles.lighting",
    "districtgenerator.classes.power_simulation_non_residential":
        "districtgenerator.buildings.profiles.non_residential_electricity",
    "districtgenerator.classes.system": "districtgenerator.energy_systems",
    "districtgenerator.classes.KPIs": "districtgenerator.analysis.kpis",
    "districtgenerator.classes.plots": "districtgenerator.analysis.plots",
    "districtgenerator.classes.certificate_generator": "districtgenerator.analysis.certificate",
    "districtgenerator.functions.SIA": "districtgenerator.buildings.typology.sia2024",
    "districtgenerator.functions._5R1C": "districtgenerator.buildings.thermal.model_5r1c.simulation",
    "districtgenerator.functions._7R2C": "districtgenerator.buildings.thermal.model_7r2c.simulation",
    "districtgenerator.functions._FourElements": "districtgenerator.buildings.thermal.model_four_elements.simulation",
    "districtgenerator.functions.change_resolution": "districtgenerator.time_series.resolution",
    "districtgenerator.functions.clustering_medoid": "districtgenerator.time_series.medoid",
    "districtgenerator.functions.clustering_processing": "districtgenerator.time_series.clustering",
    "districtgenerator.functions.get_params_central_devices": "districtgenerator.optimization.central.parameters",
    "districtgenerator.functions.heating_network_simple": "districtgenerator.energy_systems.heating_network",
    "districtgenerator.functions.opti_central": "districtgenerator.optimization.central.operation",
    "districtgenerator.functions.opti_dimensioning_central_devices":
        "districtgenerator.optimization.central.dimensioning",
    "districtgenerator.functions.opti_dimensioning_decentral_devices":
        "districtgenerator.optimization.decentral.heating_concept",
    "districtgenerator.functions.randomness": "districtgenerator.utilities.randomness",
    "districtgenerator.functions.solver_config": "districtgenerator.optimization.solver",
    "districtgenerator.functions.wind_turbines": "districtgenerator.energy_systems.wind_turbine",
    "districtgenerator.data_handling.config": "districtgenerator.config.settings",
}


class _AliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolve an old module name to the already importable new module."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname in OLD_TO_NEW:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        new_name = OLD_TO_NEW[spec.name]
        warnings.warn(f"'{spec.name}' is deprecated, use '{new_name}' instead.", DeprecationWarning,
                      stacklevel=2)
        # Returning the real module keeps a single module object for both names
        return importlib.import_module(new_name)

    def exec_module(self, module):
        pass


def install():
    """Register the alias finder once."""
    if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())
