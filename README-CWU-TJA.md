# Extentions by cwu-tja

# Structure of the code

The script run_networked_districts.py is the entry point for executing the code that handles interconnected districts. It relies on the Network class defined in network.py.

A Network instance can call several functions from districtgenerator.py to create and initialise multiple districts in a single run. Unlike districtgenerator.py, the Network class can collect the parameters of all districts in connected dictionaries. The names of thes dictionaries end with the suffix Con. For example, the dictionary paramCon merges the individual param dictionaries of each district into one combined dictionary.

By aggregating the data in this way, the complete set of parameters for every district can be passed to the function opti_dimensioning_central_devices_connect.py. This function behaves as follows:
             
OPTIM_DIMENSION:              
1: Optimises the design of the central devices jointly for all districts.
0: Optimises the central devices independently for each district.



# Plotting scripts