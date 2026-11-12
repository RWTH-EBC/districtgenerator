# Version History

## v1.0.1

- Added project description, project links and classifiers for PyPI
- Fixed relative links in README for display on PyPI

## v1.0.0

### Restructuring

- Restructured the package by scientific workflow: `environment`, `buildings`, `energy_systems`, `time_series`,
  `economics`, `optimization`, `analysis`, `file_io`, `config` and `utilities` replace `classes`, `functions` and
  `data_handling`
- Removed the old packages `classes`, `functions` and `data_handling` without aliases; imports and pickled districts
  with old module paths have to be updated
- Lean `Datahandler` that delegates each workflow step to its package; its public methods are unchanged
- One thermal model registry, one demand worker for threads and processes, one annuity implementation
- Split the certificate generator into submodules
- Input data in `districtgenerator/data` sorted into subfolders by topic (`config`, `scenarios`, `site`, `weather`,
  `buildings`, `energy_systems`, `report`); source data that is not read at runtime moved to `data/raw`
- Input and result paths centralized in `utilities.paths` (`DATA_DIR`, `RESULTS_DIR`); the Datahandler parameters
  `filePath` and `srcPath` are deprecated and ignored
- The example configuration uses the open-source solver HiGHS instead of Gurobi
- Fixed the averaging of the CO2 tax, the cooling losses of the heat grid and the wind generation
- Fixed the paths to the wind turbine power curves and the heat pump COP file after the data restructuring
- Regression tests of the example results, structure tests and further unit tests
- Updated documentation: workflow diagram, examples 7 to 10 and tests

### Building models and thermal calculation

- New building model 7R2C according to VDI 6007-1; the former `envelope.py` was renamed to the 5R1C envelope
- New building model FourElements, which inherits from the 7R2C envelope
- Heating curve per building in the 5R1C and 7R2C envelopes, used for the COPs of decentralized heat pumps in the
  operation optimization and the KPIs (#152). Renamed configuration parameters: `HP__enable_measures` to
  `HP__enable_low_temp_measures`, `HP__measures_inv_fix` to `HP__low_temp_measures_inv_fix`;
  `hp_sink_temp_measures_cap` was replaced by `low_temp_measures_supply_nom` / `low_temp_measures_return_nom`
  (50/40 °C)
- Fixed errors in the 5R1C method and in the calculation of the standard heating load (#25)
- Heating set temperature of residential buildings depends on the insulation standard and the user behavior
- Heating period and calendar: `CalendarConfig` (public holidays, start dates, heating period) and
  `consider_heating_period` in the 5R1C calculation
- Cooling load calculation (`calcCoolingLoad`) in the envelope, the 5R1C heating profile and the Datahandler;
  `design_cooling_load` in the operation optimization, the energy systems and the KPIs; postal codes are mapped to
  climate zones (`site_data_with_KLZ.txt`)
- Building geometry: ratio of gross to net floor area added, number of flats in multi-family houses adjusted (#27)

### Building types, occupants and load profiles

- DHW profiles generated with OpenDHW instead of precalculated profiles; the embedded code was later replaced by the
  installable package (OpenDHW >= 0.2.9). Draw-off times are taken from the occupancy profile of the districtgenerator
  (#141). Seasonal set and cold water temperatures (#28)
- New method to determine the number of occupants in residential buildings (#23); household electricity based on a
  probabilistic approach (#31)
- Non-residential buildings: office, school, restaurant and supermarket based on SIA 2024, including lighting and
  electricity simulation; corrected U-values and exterior wall areas; new example e9
- Additional non-residential and mixed-use building types (e.g., hospital, culture, sports, retail, workshop,
  university) with their own data directory
- Electric mobility: several cars per building (`car_segment.json`), charging optimization with availability and
  self-discharge

### Energy systems, heating and cooling networks

- Design of energy devices and a central energy system for the district, wind turbines, and extension of the operation
  optimization by the EnergyHub
- Decentralized DHW heating: electric instantaneous water heater (`EH_DHW`, `dhw_heater = 1`) and DHW storage
  (`TES_DHW`) as decentralized devices; separate energy balances for DHW and space heating; minutely DHW profiles are
  saved
- Optimal selection of decentralized heating concepts (#148): `heater=opt` or a candidate list such as
  `opt:[HP,BOI]` selects the cheapest feasible concept
- Heating and cooling networks: empirical sizing, constant temperatures, costs, soil temperature and losses; 2-pipe
  models (4th generation and 5th generation (bidirectional)); pipe data (KMR, PE, PMR)
- Optional calculation with heating curve and time-dependent supply temperature for heating networks:
  `temperature_mode = "constant"` or `"heating_curve"` (supply and return temperature depending on the outdoor
  temperature, per network generation 3G/4G/5G)
- Fixed the network design with building positions
- Cooling option for districts: decentralized chillers or central supply via a second pipe network
- Independent heating and cooling supply (#144): new parameter `cooler` (`CC` = local chiller, `cooling_grid` = network
  cooling). Without it, `heater=heat_grid` uses network cooling, otherwise a local chiller is used
- EnergyHub without heating network and selectable design (#146): a purely electric EnergyHub is possible,
  `DESIGN_ENERGY_HUB=True` creates a hub without heating network, technologies can be enabled individually, and heating
  networks trigger the hub design automatically
- Ground source and air source heat pumps can be combined in the EnergyHub; fixed the cluster length bug

### Optimization and performance

- Optimization and EHDO integration: optimization of the central energy system and the device sizing, examples e7 and
  e8; EHDO was integrated into the districtgenerator
- All optimizations migrated to Pyomo, solver configuration and fix for the abort at `maxTimeLimit`
- Clustering: peaks and sums are preserved; the own k-medoids implementation was replaced by the package tsam, and the
  clustering is performed only once
- Parallelization: demands are calculated in parallel with a choice between multiprocessing and threading and a process
  limit

### Results and evaluation

- Restructured KPI output (#140): `calculate_per_building_kpis`, annual values per year, rounded CSV and xlsx output;
  removed `t_reduction_measures`
- Further KPI changes: `save_KPIs()`, generation and consumption per device, kWp instead of kW, NaN fix for coverage
  ratios, cost calculation adapted to the new configuration
- Certificate / report: certificate generator, multi-year optimization, translations (`report_translations.json`) and
  file name parameter for the webtool

### Data, configuration and infrastructure

- Site and weather data from the postal code: weather data depends on the postal code (examples for 10 cities), old TRY
  data can be selected, runtime forecast, corrected names of the weather stations
- Configuration with pydantic: static parameters are read from the pydantic configuration and the `.env.CONFIG` file
  instead of JSON, with docstrings
- The example CSV can be renamed to a free scenario name, which is used for the output
- Datahandler functions: "load all data", exchangeable weather data, `scenario_path`, progress tracking (JSON) and
  postal code environment
- Installation: `setup.py` reads `requirements.txt` dynamically, installation bugfix
- Examples e1 to e10 restructured (decentralized, central, non-residential, multiple scenarios), `tests/test_examples.py`
  and CI pipeline

## v0.1.2

- 7R2C building modeling according to VDI 6007-1
- Peaks and sums of time series are preserved during clustering
- All optimizations migrated to Pyomo
- Additional heat generators and local heating networks with simplified design and consideration of waste heat
- 2-pipe models for heating networks (4th generation and 5th generation (bidirectional))
- Expansion of the building types to include non-residential buildings (e.g., office buildings, schools, restaurants,
  supermarkets)
- Reworked structure of loading (static) data such as parameters using pydantic
- Enabled the usage of config files (.env) to change (static) parameters
- Renaming of example.csv to a specified scenario name (used for output as well)

## v0.1.1
- Reworked the structure of the library
- Added documentation  
- Added test file for functional testing

## v0.1.0
- Configuration via environment variables, json or local
- Moved to github.com/RWTH-EBC
- Bugfix
