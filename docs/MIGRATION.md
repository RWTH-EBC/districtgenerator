# Migration from v0.1.2

The package was restructured by the steps of the scientific workflow. The packages `districtgenerator.classes`,
`districtgenerator.functions` and `districtgenerator.data_handling` were removed without aliases, so imports, pickled
districts and own data files have to be updated.

## Imports

Import the Datahandler directly from the package:

```python
from districtgenerator import Datahandler
```

The old modules moved to the following new modules:

| Old module | New module |
|---|---|
| `districtgenerator.classes.datahandler` | `districtgenerator.datahandler` |
| `districtgenerator.classes.envelope_5R1C` | `districtgenerator.buildings.thermal.model_5r1c.envelope` |
| `districtgenerator.classes.envelope_7R2C` | `districtgenerator.buildings.thermal.model_7r2c.envelope` |
| `districtgenerator.classes.envelope_FourElements` | `districtgenerator.buildings.thermal.model_four_elements.envelope` |
| `districtgenerator.classes.solar` | `districtgenerator.environment.solar` |
| `districtgenerator.classes.users` | `districtgenerator.buildings.profiles.users` |
| `districtgenerator.classes.profiles` | `districtgenerator.buildings.profiles.profiles` |
| `districtgenerator.classes.non_residential` | `districtgenerator.buildings.typology.non_residential` |
| `districtgenerator.classes.lighting_non_residential` | `districtgenerator.buildings.profiles.lighting` |
| `districtgenerator.classes.power_simulation_non_residential` | `districtgenerator.buildings.profiles.non_residential_electricity` |
| `districtgenerator.classes.system` | `districtgenerator.energy_systems` (`BES` and `CES`) |
| `districtgenerator.classes.KPIs` | `districtgenerator.analysis.kpis` |
| `districtgenerator.classes.plots` | `districtgenerator.analysis.plots` |
| `districtgenerator.classes.certificate_generator` | `districtgenerator.analysis.certificate` |
| `districtgenerator.functions.SIA` | `districtgenerator.buildings.typology.sia2024` |
| `districtgenerator.functions._5R1C` | `districtgenerator.buildings.thermal.model_5r1c.simulation` |
| `districtgenerator.functions._7R2C` | `districtgenerator.buildings.thermal.model_7r2c.simulation` |
| `districtgenerator.functions._FourElements` | `districtgenerator.buildings.thermal.model_four_elements.simulation` |
| `districtgenerator.functions.change_resolution` | `districtgenerator.time_series.resolution` |
| `districtgenerator.functions.clustering_medoid` | `districtgenerator.time_series.medoid` |
| `districtgenerator.functions.clustering_processing` | `districtgenerator.time_series.clustering` |
| `districtgenerator.functions.get_params_central_devices` | `districtgenerator.optimization.energy_hub_parameters` |
| `districtgenerator.functions.heating_network_simple` | `districtgenerator.energy_systems.heating_network` |
| `districtgenerator.functions.opti_central` | `districtgenerator.optimization.operation` |
| `districtgenerator.functions.opti_dimensioning_central_devices` | `districtgenerator.optimization.energy_hub_sizing` |
| `districtgenerator.functions.opti_dimensioning_decentral_devices` | `districtgenerator.optimization.heating_concept` |
| `districtgenerator.functions.randomness` | `districtgenerator.utilities.randomness` |
| `districtgenerator.functions.solver_config` | `districtgenerator.optimization.solver` |
| `districtgenerator.functions.wind_turbines` | `districtgenerator.energy_systems.wind_turbine` |
| `districtgenerator.data_handling.config` | `districtgenerator.config.settings` |

Saving and loading of profiles and districts is now in `districtgenerator.file_io`.

## Pickled districts

Districts saved with `Datahandler.saveDistrict` before the restructuring reference the old module paths and cannot be
loaded with `Datahandler.loadDistrict` anymore. Generate them again, or load them once with an unpickler that maps the
old module paths to the new ones and save them again:

```python
import pickle

OLD_TO_NEW = {
    "districtgenerator.classes.solar": "districtgenerator.environment.solar",
    "districtgenerator.classes.users": "districtgenerator.buildings.profiles.users",
    # ... further entries from the table above
}


class MigrationUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        return super().find_class(OLD_TO_NEW.get(module, module), name)


with open("old_district.p", "rb") as file:
    district = MigrationUnpickler(file).load()
```

## Data files

The input data in `districtgenerator/data` is sorted into subfolders by topic. If you added own files to the data
folder, move them as well:

| Old location in `data/` | New location in `data/` |
|---|---|
| `.env.CONFIG.EXAMPLE`, `.env.CONFIG.FREIBURG` | `config/` |
| `SIA2024.xlsx`, `LightBulbs_nonresidential.json`, `car_segment.json` | `buildings/` |
| `non_residential/*.json` | `buildings/` |
| `non_residential/info.txt` | `buildings/non_residential_info.txt` |
| `pipe/pipe_specifications_*.csv` | `energy_systems/` |
| `wind_turbine_models/WT_*.csv` | `energy_systems/` |
| `coefficient_of_performance.txt` | `energy_systems/` |
| `plz_geocoord_matched.xlsx`, `site_data_with_KLZ.txt` | `site/` |
| `report_translations.json` | `report/` |

The folder `data/raw` holds source data and scripts that were used to create the data files; the districtgenerator
does not read it.

## Datahandler parameters

- `Datahandler(env_path=".env.NAME")` looks for the configuration file in `data/config`, an absolute path is used as
  given.
- Own scenario files can be placed in another folder with `Datahandler(scenario_file_path=...)`.
- The parameters `filePath` and `srcPath` are deprecated and ignored. Input data is always read from
  `districtgenerator/data`.

## Solver

The example configuration `.env.CONFIG.EXAMPLE` now uses the open-source solver HiGHS instead of Gurobi. Set
`SOLVER_NAME=gurobi` in your `.env` file to keep using Gurobi.
