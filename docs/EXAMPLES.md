# Examples

The [examples](https://github.com/RWTH-EBC/districtgenerator/tree/develop/examples) folder contains examples to support you how to use the 
DistrictGenerator. Each example is executable separately.
Within the given examples we give a detailed description of the 
required input, its format and how the output looks like. The 
order of the examples represents the workflow of the DistrictGenerator.

## How to initialize the datahandler

Within this example we explain how the user initializes the datahandler.

- [Initialize Datahandler](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e1_initialize_datahandler.py) 

## Generate environment for the district
    
Within this example we generate the environment of the district.
This includes data respectively time series on solar radiation 
and outdoor temperature for a given location and test reference year.
- [Generate Environment](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e2_generate_environment.py) 


## Initialize buildings of the district

Within this example we initialize the buildings by the building type,
the construction year, the retrofit level and the floor area.
- [Initialize Buildings](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e3_initialize_buildings.py)


## Extension of the building models

Within this example we add more detailed information of the building components 
and their materials to the building models.
- [Extension Building Models](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e4_generate_buildings.py)


## Generation and plotting of demand profiles

Within this example we generate the (demand) profiles and exemplary plot the monthly space heat
demand of the district.

- [Demand Profiles](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e5_generate_demands.py)


## Customisation of specific assumptions for individual districts

Within this example we change specific assumptions like the location of the district,
the minimal indoor temperature of the buildings, the weather test reference year and
the time resolution.

- [Specify Assumptions](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e6_individual_district.py)

## Evaluation of a decentralized supply scenario

Within this example we generate a complete district with `generateDistrictComplete` and size the decentral devices
of each building, e.g. heat pumps, boilers, PV, batteries and thermal energy storages. The scenario file
`example_decentral.csv` defines the heat generator, the storage sizes, the PV and solar thermal roof shares and the
share of electric vehicles of each building. The operation of the devices is then optimized for typical periods,
the key performance indicators are calculated and a PDF certificate summarizes the results.

- [Decentral Scenario Evaluation](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e7_decentral_scenario_evaluation.py)


## Evaluation of a central supply scenario

Within this example most buildings of `example_central.csv` are connected to a heat grid. In addition to the
decentral devices, the heat grid and the devices of the central energy hub are designed with an optimization. The
operation of all devices is optimized for typical periods and evaluated with key performance indicators and a
PDF certificate.

- [Central Scenario Evaluation](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e8_central_scenario_evaluation.py)


## Evaluation of a scenario with non-residential buildings

Within this example the district contains residential, non-residential and mixed-use buildings, e.g. offices,
schools, restaurants, grocery stores and multi-family houses with a grocery store on the ground floor. The
non-residential buildings use archetype data and usage profiles of SIA 2024. The evaluation follows the examples
7 and 8.

- [Non-Residential Scenario Evaluation](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e9_non_residential_scenario_evaluation.py)


## Execution of multiple scenarios

Within this example the districtgenerator runs one after another for all configuration files in a folder whose
names start with `.env`, by default `districtgenerator/data/config`. Each configuration file describes one scenario
with its own assumptions, so different scenarios can be compared and the configuration files can be reused or shared.

- [Multiple Scenarios](https://github.com/RWTH-EBC/districtgenerator/blob/develop/examples/e10_exec_multiple_scenarios.py)
