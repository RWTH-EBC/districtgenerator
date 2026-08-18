![E.ON EBC RWTH Aachen University](./img/EBC_Logo.png)

# DistrictGenerator

[![License](http://img.shields.io/:license-mit-blue.svg)](http://doge.mit-license.org)
[![Documentation](https://rwth-ebc.github.io/districtgenerator/master/docs/doc.svg)](https://rwth-ebc.github.io/districtgenerator/master/docs/README.html)

With the DistrictGenerator, we present an python-based open-source tool aimed at urban planners, energy suppliers,
housing associations, engineering firms, architectural professionals, as well as academic and research institutions.
Starting from a small set of building and scenario information, DistrictGenerator creates archetype-based
building models, generates time-resolved demand and generation profiles, sizes decentralized and central energy-system 
technologies, optimizes their operation, and evaluates district scenarios using technical, economic, and environmental
key performance indicators. Consequently, users can discern actionable measures to harmonize energy supply.

The DistrictGenerator is being developed at [RWTH Aachen University, E.ON Energy
Research Center, Institute for Energy Efficient Buildings and Indoor
Climate](https://www.ebc.eonerc.rwth-aachen.de/cms/~dmzz/E-ON-ERC-EBC/?lidx=1).

## General Motivation

In the early stages of neighborhood planning, crucial data such as demand profiles of electricity, heating, 
domestic hot water, and occupancy profiles are often not available. The absence of this data hampers 
accurate evaluations of energy systems in districts. The DistrictGenerator seeks to advance the applicability 
of sustainable, cross-sectoral energy systems in neighborhoods, with a specific emphasis on exploiting synergy 
potentials among buildings of diverse usage structures through integrated concepts. We summarize the key contributions 
of the DistrictGenerator as follows:

- An open-source tool with minimal input requirements. Leveraging pre-set elements and default values of temporally 
  resolved demand profiles, as well as decentralized heat generator sizing conforming to DIN standards.

- The tool enables the bottom-up representation of entire urban structures through neighborhood models, affording a 
  sufficiently detailed analysis foundation.

- Facilitation of central operational optimization and presentation of analytical results and key performance 
  indicators. This supports the examination of various neighborhood types and supply scenarios concerning technology 
  selection and penetrations. We thereby create a platform for early-stage comparison of neighborhood concepts 
  with the flexibility of selecting different variants, given the tool's rapid recalculations.

## Overview

DistrictGenerator combines building archetypes, stochastic user behavior, reduced-order thermal building models, 
renewable generation models, energy-system sizing, time-series aggregation, mathematical optimization, and 
post-processing in one reproducible Python workflow.

Typical applications include:
- Generation of a bottom-up representation of neighborhoods with synthetic building data,
- Generation of synthetic building specific energy-demand and generation time series for entire neighborhoods 
  with different building types and usage structures,
- Analysis of heat pumps, photovoltaic systems, storage systems, electric vehicles, and district heating,
- Investigation of decentralized and centralized energy-supply concepts,
- Sizing of energy technologies and evaluation of energy-system operation and its technologies.

DistrictGenerator covers four main parts of a district energy-system study:
1. DistrictGenerator creates building-level representations from basic information such as building type,
construction year, retrofit state, construction type, floor area, and selected energy technologies. Residential 
building archetypes are enriched using TEASER and building-stock information based on TABULA. Non-residential 
buildings are represented using dedicated archetype data and use-specific assumptions, including data derived from 
SIA 2024.
2. DistrictGenerator generates building-specific profiles for space heating, space cooling,
domestic hot water, household electricity, occupancy, internal heat gains, photovoltaic generation,
solar-thermal generation, and electric-vehicle availability and charging.
3. DistrictGenerator models and evaluates decentralized building energy systems as well as central district 
energy systems. Technologies include heat pumps, electric heaters, boilers, biomass boilers, oil boilers,
hydrogen boilers, combined heat and power units, fuel cells, district heating, photovoltaic systems, 
solar-thermal collectors, batteries, thermal energy storage, electric vehicles, compression chillers, and wind turbines.
Representative time periods are generated using k-medoids clustering to reduce the computational effort of annual 
optimization. Optimization is formulated with Pyomo. The example configuration currently uses Gurobi as the solver but
also open source solvers like HiGHS can be used.
4. Simulation and optimization results are evaluated using technical, economic, and environmental key performance 
indicators. They include annual energy demands, grid imports and exports, renewable generation, peak loads,
self-consumption and coverage indicators, energy-carrier consumption, investment and annualized costs,
operation costs, CO₂ emissions, and technology-specific energy balances. Results are additionally summarized in 
a configurable PDF district energy certificate.

## Getting started

### Install the DistrictGenerator

To install, first clone this repository with
```
git clone https://github.com/RWTH-EBC/districtgenerator
```
and secondly run:
```
pip install -e districtgenerator
```
Editable installation is recommended for researchers who want to inspect, extend, or modify the source code.

Once you have installed the DistrictGenerator, you can check the [examples](EXAMPLES.md) 
to learn how to use the different components.

### Minimum manual required input data

To generate your district, you need to know some information about its buildings. 
The minimal input data set was defined following the [TABULA archetype approach](https://webtool.building-typology.eu/#bm):

- id: building ID (just numerate the buildings)
- building: building type (SFH = single family house, TH = terraced house, MFH = multi family house, AB = apartment block, OB = office building, SC = school, GS = grocery store, RE = restaurant, MFH+GR = multi family house + grocery store, AB+GR = apartment block + grocery store, MFH+RE = multi family house + restaurant, AB+RE = apartment block + restaurant)
- year: construction year (the calendar year in which the building was constructed)
- construction_type: building thermal mass (0 = lightweight construction, 1 = medium construction, 2 = heavyweight construction)
- retrofit: retrofit state according to TABULA (0: existing state, 1: usual refurbishment, 2: advanced refurbishment)
- area: reference floor area (given in square meters)
- night_setback: night temperature setback (0 = no night setback, 1 = with night setback)
- heater: selected heat generator type (HP = heat pump, CHP = combined heat and power, FC = fuel cell, BOI = boiler, heat_grid = district heating)
- dhw_heater: selected domestic hot water generator type (0: no decentral domestic hot water generator, EH_DHW = electric heater)
- cooling: calculation of cooling demand (0 = no cooling, 1 = with cooling)
- EV: electric vehicle share - fraction between 0 and 1 representing the proportion of electric vehicles in the building's total vehicle inventory
- fTES: thermal energy storage size in liters per kW heating capacity of the heat generation system
- fBAT: battery storage size in Wh per W of PV system power (Wh/W_PV)
- fPV1: fraction of total roof area covered with photovoltaics (the side with azimuth angle gammaPV, based on TABULA building typology roof area data)
- fPV2: other side of the roof
- fSTC: fraction of roof area equipped with solar thermal collectors (based on TABULA building typology roof area data)
- gammaPV: azimuth angle of roof side 1 in degrees (0° = south-facing orientation)
- EV_charging: electric vehicle charging behavior (bidirectional = charging and discharging with use as electricity storage, on-demand = charging as needed, intelligent = optimized charging)

The example_decentral.csv file can be used as [template](https://github.com/RWTH-EBC/districtgenerator/blob/develop/districtgenerator/data/scenarios/example_decentral.csv).

### Additional configuration categories and input data

In the [file](https://github.com/RWTH-EBC/districtgenerator/blob/develop/districtgenerator/data_handling/config.py) 
further data can be found. Default values are already stored there. General modeling assumptions are managed through 
Pydantic-based configuration classes and will be overwritten through an .env configuration file if the Datahandler 
is initialized with it. This .env file can be found
in the directory [data](https://github.com/RWTH-EBC/districtgenerator/tree/develop/districtgenerator/data).

The configuration includes assumptions and parameters related to location and weather, temporal resolution, 
heating and cooling periods, building design conditions, thermal building model, economic parameters, energy prices, 
emission factors, heating networks, central and decentralized technologies, optimization, solver settings, and
report generation.

## Workflow of the DistrictGenerator

The district generator integrates multiple open-source tools and databases. 
The figure below visualizes the dependencies of external tools and data with internal 
functions. The user input for the parameterization of a neighborhood consists 
of a minimum of data. First, the user enters the number of buildings and basic 
information about each building, namely the building type, year of construction, 
retrofit level, and net floor area. The number of buildings to be calculated is 
not limited by the program. Optionally, the site of the district, the time 
resolution of the profiles and the test reference year (TRY) for weather data 
can be modified.

![Library Structure](img/Workflow_DistrictGenerator.png)

To obtain a fully parameterized building model, the [TEASER tool](https://rwth-ebc.github.io/TEASER/main/docs/index.html) 
performs a data enrichment with data from the [TABULA WebTool](https://webtool.building-typology.eu/#bm) 
that provides statistical and normative information about the building stock. 
Finally, the TEASER python package determines the geometry and material properties of the buildings. 
As the TABULA WebTool defines archetypal building properties for type, age class and retrofit level, the 
generated districts are composed of representative buildings, making them ideal 
for representative analyses or scalability studies. The number of occupants within a dwelling is randomly determined, 
but within defined limits (1 to 4 occupants for each flat in multi-family houses and apartment block, 
2-5 occupants in single-family houses and terraced houses), and serves as input data 
for the [richardsonpy tool](https://github.com/RWTH-EBC/richardsonpy) to calculate stochastically the time-resolved occupancy profiles. 
Furthermore, the [Stromspiegel](https://www.stromspiegel.de/fileadmin/ssi/stromspiegel/Downloads/Stromspiegel-2019-web.pdf) 
provides statistical data on annual electricity consumption in German dwellings. Annual consumption
is assigned to each dwelling with a possible standard deviation of 10%, upon which the time-resolved electricity profile is
created using the stochastic profile generator richardsonpy again. The electricity and occupancy
profiles serve as input for a time-resolved internal gain calculation. Additionally, the occupancy
profiles are needed for domestic hot water profile generation, for which functions from the
[openDHW tool](https://github.com/RWTH-EBC/OpenDHW) 
are utilized. Finally, the static building data, as well as the time-resolved weather and internal gain data, 
are included in the space heating profile generation. These are computed by means of a 5R1C- or 7R2C-substitution model 
according to VDI 6007-1 using the simplified hourly method.

## Final output of the DistrictGenerator

DistrictGenerator stores generated profiles and optimization results in the configured [results](https://github.com/RWTH-EBC/districtgenerator/tree/develop/districtgenerator/results) 
directory. The directory separates building demand profiles, renewable generation profiles, and optimization results 
so that intermediate results can be reused independently for post-processing or subsequent simulations. The exact 
number of building-specific files depends on the investigated district and the selected configuration.

The time-series file contains the main time-dependent profiles:
- heating: space heating demand
- cooling: space cooling demand
- dhw: domestic hot water demand
- elec: electricity demand for lighting and electric household devices
- gains: internal gains from persons, lighting and electric household devices
- occ: occupancy profile
- EV_carcharging_ondemand: electric vehicle charging profile for on-demand charging behavior

The static file contains values that describe the building or its users but do not vary over time:
- nb_units: number of residential units or non-residential building units
- nb_occ: number of occupants per unit
- heatload: design heating load
- bivalent: heating load at the bivalent temoperature
- ev_capacity: selected ev battery capacities

The generation directory contains renewable generation profiles calculated during device sizing. For decentralized 
systems, DistrictGenerator creates separate files for every building:The PV and solar-thermal profiles are calculated 
using the building's roof area, roof orientation, input technology parameters, and available solar radiation. 

The optimization directory contains the detailed solutions of the energy-system optimization. DistrictGenerator 
reduces the full annual time series to representative periods using k-medoids clustering. 
A separate optimization problem is solved for every representative cluster. Consequently, the result directory 
contains one solution file per cluster. They contain the raw decision-variable values of the optimization model 
depending on the technologies present in the scenario.

Finally, the DistrictGenerator generates a PDF report summarizing the results of the energy-system optimization 
by various key performance indicators.

## Running examples for functional testing

Once you have installed the DistrictGenerator, you can check the [examples](EXAMPLES.md) 
to learn how to use the different components. 

To test the tool's executability, run [test_examples.py](https://github.com/RWTH-EBC/districtgenerator/blob/develop/tests)  in the tests folder. 
This functional testing checks the entire chain of the tool, from data input and 
initialization to the output of the calculated profiles. It does not correspond to a 
test of the functional units of the entire process. This  functional testing is based 
on the examples automatically executed one after another.

## How to contribute

The documentation and examples should be understandable and the code bug-free. 
As all users have different backgrounds, you may not understand everything or encounter bugs.
If you have questions, want to contribute new features or fix bugs yourself,
please [raise an issue here](https://github.com/RWTH-EBC/districtgenerator/issues/new).

If you wrote a new feature, create a pull request and assign 
a reviewer before merging. Once review is finished, you can merge.

## Authors

* [Joel Schölzel](https://www.ebc.eonerc.rwth-aachen.de/cms/e-on-erc-ebc/das-institut/mitarbeiter/digitale-energie-quartiere/~obome/schoelzel-joel/?allou=1) (corresponding)
* [Carla Wüller](https://www.ebc.eonerc.rwth-aachen.de/cms/e-on-erc-ebc/Das-Institut/Mitarbeiter/Copy-of-Digitale-Energiequartiere/~beoyus/Wueller-Carla/)
* [Rawad Hamze](https://www.ebc.eonerc.rwth-aachen.de/cms/e-on-erc-ebc/Das-Institut/Mitarbeiter/Team6/~birwyf/Hamze-Rawad/)
* [Hannah Görigk](https://www.ebc.eonerc.rwth-aachen.de/cms/e-on-erc-ebc/das-institut/mitarbeiter/copy-of-digitale-energiequartiere/~bhtapd/hannah-goerigk/?allou=1)

## Alumni

* Sarah Henn
* Tobias Beckhölter

## Reference

We presented or applied the library in the following publications:

- S. Henn, J. Schölzel, T. Beckhölter, C.Wüller, R. Hamze, D. Müller. Districtgenerator: Generating building-specific load
  profiles for residential districts. Journal of Open Source Software. https://joss.theoj.org/papers/10.21105/joss.07657

- J. Schölzel, S. Henn, R. Streblow, D. Müller. Evaluation of Energy Sharing on a 
  Local Energy Market Through Comparison of Energy Management Techniques. 36th International 
  Conference on Efficiency, Cost, Optimization, Simulation and Environmental Impact of Energy Systems.
  https://doi.org/10.52202/069564-0307

- J. Schölzel, T. Beckhölter, S. Henn, C.Wüller, R. Streblow, D. Müller.
  Districtgenerator: A Novel Open-Source Webtool to Generate Building-Specific Load 
  Profiles and Evaluate Energy Systems of Residential Districts. 37th International 
  Conference on Efficiency, Cost, Optimization, Simulation and Environmental Impact of 
  Energy Systems.
  
- C. Wüller, J. Schölzel, R. Streblow, D. Müller. Optimizing Local Energy Trading in Residential Neighborhoods:A Price Signal Approach 
  in Local Energy Markets. 37th International Conference on Efficiency, Cost, Optimization, 
  Simulation and Environmental Impact of Energy Systems.

## License

The DistrictGenerator is released by RWTH Aachen University, E.ON Energy
Research Center, Institute for Energy Efficient Buildings and Indoor Climate,
under the [MIT License](about/LICENSE.md).

## Acknowledgements

The districtgenerator has been developed within the public funded project 
"BF2020 Begleitforschung ENERGIEWENDEBAUEN - Modul Quartiere" (promotional reference: 03EWB003B) 
and with financial support by BMWK (German Federal Ministry for Economic Affairs and Climate Action).

<img src="https://www.innovation-beratung-foerderung.de/INNO/Redaktion/DE/Bilder/Titelbilder/titel_foerderlogo_bmwi.jpg?__blob=normal" width="200">
