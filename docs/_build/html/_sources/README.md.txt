![E.ON EBC RWTH Aachen University](./img/EBC_Logo.png)

# DistrictGenerator

[![License](http://img.shields.io/:license-mit-blue.svg)](http://doge.mit-license.org)
[![Documentation](https://rwth-ebc.github.io/FiLiP/master/docs/doc.svg)](https://rwth-ebc.github.io/FiLiP/master/docs/index.html)

Through the DistrictGenerator, we introduce an python-based open-source tool aimed at urban planners, energy suppliers,
housing associations, engineering firms, architectural professionals, as well as academic and research institutions. 
This tool furnishes crucial insights into energy demands, pivotal for the effective design and operation of 
neighborhoods energy systems. Consequently, users can discern actionable measures to harmonize energy supply.
The DistrictGenerator offers a pioneering approach by mapping entire urban 
building stocks in neighborhood models for automated load profile calculations and dimensioning of distributed 
energy resources. By integrating several open-source data bases and tools like [TEASER](https://github.com/RWTH-EBC/TEASER) 
and [richardsonpy](https://github.com/RWTH-EBC/richardsonpy).

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

Once you have installed the DistrictGenerator, you can check the [examples](EXAMPLES.md) 
to learn how to use the different components.

### Minimum required input data

To generate your district, you need to know some information about its buildings. 
The minimal input data set was defined following the [TABULA archetype approach](https://webtool.building-typology.eu/#bm):

- id: building ID (just numerate the buildings)
- building: residential building type (single family house, terraced house, multi family house or apartment block)
- year: construction year (the calendar year in which the building was constructed)
- retrofit: retrofit state according to TABULA (0: existing state, 1: usual refurbishment, 2: advanced refurbishment)
- area: reference floor area (given in square meters)

The example.csv file can be used as [template](../districtgenerator/data/scenarios/example.csv).

### What you get

After executing district generation you can find building-specific and time-dependent profiles in 
the .csv format in folder results/demands. The results contain: 

- heat: space heating demand
- dhw: domestic hot water demand
- elec: electricity demand for lighting and electric household devices
- occ: number of persons present
- gains: internal gains from persons, lighting and electric household devices

## Structure of the DistrictGenerator

![Library Structure](./img/Struktur_Quartiersgenerator.png)

## Running examples for functional testing

Once you have installed the DistrictGenerator, you can check the [examples](EXAMPLES.md) 
to learn how to use the different components. 

To test the tool's executability, run [test_examples.py](https://github.com/RWTH-EBC/districtgenerator/tree/15-joss-documentation/tests)  in the tests folder. 
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
* [Tobias Beckhölter](https://www.ebc.eonerc.rwth-aachen.de/cms/E-ON-ERC-EBC/Das-Institut/Mitarbeiter/Team6/~scaj/Beckhoelter-Tobias/)
* [Carla Wüller](https://www.ebc.eonerc.rwth-aachen.de/cms/E-ON-ERC-EBC/Das-Institut/Mitarbeiter/Digitale-Energie-Quartiere/~beoyus/Wueller-Carla/)

## Alumni

* Sarah Henn

## Reference

We presented or applied the library in the following publications:

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
