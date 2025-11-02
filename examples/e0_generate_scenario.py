# -*- coding: utf-8 -*-

"""
This is the example to generate the district layout based on the input district type and number of buildings.

Typical district type includes:
A   "german": "Wohnplätze und Streusiedlungen",
    "english": "Residential places and scattered settlements"
B   "german": "Dörfer mit überwiegend Gehöften",
    "english": "Villages with mainly homesteads"
C   "german": "Ein- und Zweifamilienhaussiedlung niedriger Dichte",
    "english": "Single and two-family house settlements of low density"
D   "german": "Einfamilienhaussiedlung hoher Dichte und Dorfkern",
    "english": "Single-family house settlements with high density and village core"
E   "german": "Reihenhausbebauung",
    "english": "Row housing development"
F   "german": "Zeilenbebauung mittlerer Dichte",
    "english": "Row development with medium density"
G   "german": "Zeilenbebauung hoher Dichte und Hochhäuser",
    "english": "Row development of high density and high-rise buildings"
H   "german": "Blockbebauung",
    "english": "Block development"
I   "german": "Mittelalterliche Altstadt",
    "english": "Medieval old town"
"""

# Import classes of the districtgenerator to be able to use the district generator.
# from districtgenerator.classes import *
from districtgenerator.functions.typdistrict_postprocess_results import scenario_generation

def example0_generate_scenario():
    # To create a district we initialize the datahandler.
    # As input the name of a scenario file is required.
    # In this example we are generating the scenario file required for the datahandler.
    # The parameters of district and their source are listed in districtgenerator/data/typdistrict_parameters.xlsx

    scenario_generation()

    # Since the generated district layout is not very stable,
    # it is recommended to check the region reasonableness after running this example,
    # and then read the results with other examples to initialize the datahandler.

    ### =====================================  Output  ===================================== ###
    # This function outputs three files.
    # The output file is saved in districtgenerator/data/scenarios.

    # First is an image displaying the locations of buildings, roads, and Transformers, along with building attributes.

    # Second is a JSON file listing detailed parameters for numerous zones, buildings, and roads,
    # which can be used for pipeline structure optimization.

    # Third is a CSV file used for initializing the data handler.
    # f"district_{district_type}_buildings_{len(buildings)}" will be the scenario_name for the initialization of datahandler.
    # Following parameters of the buildings are provided in the CSV file:
    # id:               start from 0;
    # position:         (x,y);
    # building types:   School(SC), Office(OB), Supermarket(GS), Restaurant(RE),
    #                   Residential(Single-family house (SFH: total_area<200), multi-family house (MFH: total_area>200),
    #                               apartment block (AB), terraced house (TH));
    # year:             can be chosen between 1860 and 2024;
    # retrofit:         0 (original construction state),
    #                   1 (Retrofit according to EnEV 2016),
    #                   2 (Retrofit according to KfW 55);
    # construction_type: all set at 2;
    # night_setback;
    # area:             can be freely selected;
    # number_of_floors;
    # heater;
    # cooling;
    # EV;
    # f_TES;
    # f_BAT;
    # f_PV;
    # f_STC;
    # gamma_PV;
    # ev_charging

if __name__ == '__main__':
    example0_generate_scenario()