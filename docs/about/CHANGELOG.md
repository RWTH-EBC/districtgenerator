# Version History

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
