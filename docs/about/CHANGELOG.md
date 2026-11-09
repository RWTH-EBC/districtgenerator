# Version History

## Unreleased

- Restructured the package by scientific workflow: `environment`, `buildings`, `energy_systems`, `time_series`,
  `economics`, `optimization`, `analysis`, `file_io`, `config` and `utilities` replace `classes`, `functions` and
  `data_handling`
- Removed the old packages `classes`, `functions` and `data_handling` without aliases; imports and pickled districts
  with old module paths have to be updated (see the [migration guide](../MIGRATION.md))
- Import the Datahandler with `from districtgenerator import Datahandler`
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
- Updated documentation: workflow diagram, examples 7 to 10, migration guide and tests

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
