# Extentions by cwu-tja: Interconnected networks

# Structure of the code

The script run_interconnected_districts.py is the entry point for executing the code that handles interconnected districts. It uses the Network class defined in network.py.

A Network instance can call several functions from districtgenerator.py to create and initialise multiple districts in a single run. Unlike districtgenerator.py, the Network class can collect the parameters of all districts in connected dictionaries. The names of these dictionaries end with the suffix Con. For example, the dictionary paramCon merges the individual param dictionaries of each district into one combined dictionary.

By aggregating the data in this way, the complete set of parameters for every district can be passed to the function run_optim_connect in the script opti_dimensioning_central_devices_connect.py. This function behaves as follows:
             
OPTIM_DIMENSION:              
1: Optimises the design of the central devices jointly for all districts.
0: Optimises the central devices independently for each district.

The results of run_optim_connect are saved in several csv-files, which can be used in ths plotting scripts.

# Run_optim_connect

run_optim_connect is organised similarly compared to run_optim. However, it is able to optimise central devices jointly for several districts. To decrease the runtime compared to run_optim, the constraints are passed to the optimizer individually instead of listwise. Therefore, the following notation is used:     

def example_rule(param1):
        return m.variable[param1] <= m.varable2[param1]

model.example = pyo.Constraint(
        model.districts...,
        rule=example_rule
    ) 

New constraints used for the network are annotated with "# new for network". In the other scripts you might also find "new TJA" as an annotation for my changes. Detailed descriptions of these functions can be found in my master thesis.

# Plotting scripts

The following scripts can be used to create bar charts: plot_results_compare.py, plot_results_freecompare.py, plot_results_scenarios.py, plot_results.py and plots_presentation.py
To plot time series use the functions: plot_lines_timeseries.py, plot_timeseries.py and plot_heat_demand_timeseries.py

# Balance_gridflows

For the individual optimisation of the central devices for each district, you can take into account that grid flow are balanced on a local level. Use the script balance_gridflows.py to do so. The inputs required are the CSV-outputs of run_optim_connect: district_demand_power_timeseries.csv and district_network_results.py. Further inputs are set in the main-function of this script.

# Generate demands

This code uses an old version of Teaser. To generate demands for districts with Non-residential buildings use the script examples/e6_individual_district.py in the branch MA_cwu_tja_nrb. You might need to change the file-path to use it.
