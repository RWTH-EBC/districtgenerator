# Examples

This directory contains examples to support you how to use the 
DistrictGenerator. Each example is executable separately.
Within the given examples we give a detailed description of the 
required input, its format and how the output looks like. The 
order of the examples represents the workflow of the DistrictGenerator.

#### How to initialize the datahandler

Within this example we explain how the user initializes the datahandler.

- [Initialize Datahandler](https://github.com/RWTH-EBC/districtgenerator/blob/master/examples/e1.0_generate_first_district.py) 

#### Generate environment for the district
    
Within this example we generate the environment of the district.
This includes data respectively time series on solar radiation 
and outdoor temperature for a given location and test reference year.
- [Generate Environment](https://github.com/RWTH-EBC/districtgenerator/blob/master/examples/e1.1_generate_first_district.py) 


#### Initialize buildings of the district

Within this example we initialize the buildings by the building type,
the construction year, the retrofit level and the floor area.
- [Initialize Buildings](https://github.com/RWTH-EBC/districtgenerator/blob/master/examples/e1.2_generate_first_district.py)


#### Extension of the building models

Within this example we add more detailed information of the building components 
and their materials to the building models.
- [Extension Buildung Models](https://github.com/RWTH-EBC/districtgenerator/blob/master/examples/e1.3_generate_fist_district.py)


#### Generation and plotting of demand profiles

- [Demand Profiles](./ngsi_v2/e11_ngsi_v2_semantics)


#### Customisation of specific assumptions for individual districts

location, TRY
The location can be changed in the site_data.json file. You find it in \data.
The time resolution can be changed in time_data.json. You also find it in \data.



- [Semantics](./ngsi_v2/e11_ngsi_v2_semantics)
