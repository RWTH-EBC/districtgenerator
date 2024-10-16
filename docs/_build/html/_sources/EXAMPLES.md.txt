# Examples

This directory contains examples to support you how to use the 
DistrictGenerator. Each example is executable separately.
Within the given examples we give a detailed description of the 
required input, its format and how the output looks like. The 
order of the examples represents the workflow of the DistrictGenerator.

#### How to initialize the datahandler

Within this example we explain how the user initializes the datahandler.

- [Initialize Datahandler](https://github.com/RWTH-EBC/districtgenerator/blob/15-joss-documentation/examples/e1_initialize_datahandler.py) 

#### Generate environment for the district
    
Within this example we generate the environment of the district.
This includes data respectively time series on solar radiation 
and outdoor temperature for a given location and test reference year.
- [Generate Environment](https://github.com/RWTH-EBC/districtgenerator/blob/15-joss-documentation/examples/e2_generate_environment.py) 


#### Initialize buildings of the district

Within this example we initialize the buildings by the building type,
the construction year, the retrofit level and the floor area.
- [Initialize Buildings](https://github.com/RWTH-EBC/districtgenerator/blob/15-joss-documentation/examples/e3_initialize_buildings.py)


#### Extension of the building models

Within this example we add more detailed information of the building components 
and their materials to the building models.
- [Extension Buildung Models](https://github.com/RWTH-EBC/districtgenerator/blob/15-joss-documentation/examples/e4_generate_buildings.py)


#### Generation and plotting of demand profiles

Within this example we generate the (demand) profiles and exemplary plot the monthly space heat
demand of the district.

- [Demand Profiles](https://github.com/RWTH-EBC/districtgenerator/blob/15-joss-documentation/examples/e5_generate_demands.py)


#### Customisation of specific assumptions for individual districts

Within this example we change specific assumptions like the location of the district,
the minimal indoor temperature of the buildings, the weather test reference year and
the time resolution.

- [Specify Assumptions](https://github.com/RWTH-EBC/districtgenerator/blob/15-joss-documentation/examples/e6_individual_district.py)

