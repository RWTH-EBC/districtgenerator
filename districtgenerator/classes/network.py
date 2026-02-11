# -*- coding: utf-8 -*-

# This class can generate a network with several districts.
# Import classes of the districtgenerator to be able to use the district generator.
# Import the Datahandler class to use the district generator.
from districtgenerator.classes import Datahandler
from pathlib import Path
from .system import CES
import numpy as np
import os
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, NetworkDistConfig, PhysicsConfig, EHDOConfig, HeatGridConfig, CalendarConfig
import districtgenerator.functions.load_params_central_devices as load_params_central_devices
import districtgenerator.functions.opti_dimensioning_central_devices_connect as opti_dimensioning_central_devices_connect
import districtgenerator.functions.opti_dimensioning_central_devices as opti_dimensioning_central_devices
import districtgenerator.functions.heating_network_simple as heating_network_simple

class Network:
    def __init__(self):
        """
        Constructor of Network class.

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        """
        self.district = []
        self.interconnected_districts = {}

    def initializeDistrictsWithDecentralDevs(self,configs_dir: Path, calcUserProfiles=False, saveUserProfiles=False):
        """
        This function initializes multiple districts in the network.
        It uses all files ending with .env in the given directory.

        Parameters
        ----------
        configs_dir : Path
            Path to the directory containing the .env configuration files.

        Returns
        -------
        None.
        """
        scenario_files = [f for f in configs_dir.iterdir() if f.is_file() and f.name.startswith(".env")]

        print(f"Found {len(scenario_files)} scenario files in {configs_dir}:")
        for f in scenario_files:
            print(f" - {f.name}")

        for scenario_file in scenario_files:

            # Initialize District for the current scenario.
            data = Datahandler(env_path=scenario_file)

            # Get topology option either node or road based from heat grid data
            topology_option = data.heat_grid_data["topology_option"]

            # Print optim_dimension for the current scenario
            model_param_eh = data.params_networkdist
            print(f"\nOptim_dimension of: {data.scenario_name} is {model_param_eh['optim_dimension']}")
            
            # Generate Environment for the District
            print(f"Generating environment for {data.scenario_name}...")
            data.generateEnvironment()

            # Initialize Buildings to the District
            print(f"Initializing buildings for {data.scenario_name}...")
            data.initializeBuildings()

            # Generate more detailed Building models
            print(f"Generating detailed building models for {data.scenario_name}...")
            data.generateBuildings()

            # Generate building specific demand profiles with the adjusted assumptions
            # Use calcUserProfiles=False to speed up the calculation if user profiles are already calculated
            data.generateDemands(calcUserProfiles=calcUserProfiles, saveUserProfiles=saveUserProfiles)
            # Design decentral devices for each district
            data.designDecentralDevices(saveGenerationProfiles=True)
            # Print capacities of the decentral devices in all districts
            print(f"Capacities of the decentral devices in {data.scenario_name}:")
            for device, capacity in data.district[0]["capacities"].items():
                print(f"  {device}: {capacity}")
            
            # Check if district uses central energy supply (heat grid)
            has_heat_grid = any(
                building["buildingFeatures"]["heater"] == "heat_grid"
                for building in data.district)
            
            if has_heat_grid:
                # Verify geometry data (district_parameters)
                # --- Check if building positions are available and valid ---
                missing_positions = (
                        "position" not in data.scenario.columns
                        or data.scenario["position"].isnull().any()
                        or any(
                    not isinstance(p, tuple) or len(p) != 2 or not all(isinstance(x, (int, float)) for x in p)
                    for p in data.scenario["position"]))
                if missing_positions:
                    print("No district geometry found — running simple heating network design.")
                    data=heating_network_simple.heating_network(data)
                    # Add data to district list for later use of central optimization
                    self.district.append(data)
                else:
                    print("Generating and optimizing heating network...")
                    data.generateNetwork(data, topology_option)
                    data.prepareClusteringInputs(data)
                    data.optimization_heatingnetwork(data)
                     # Add data to district list for later use of central optimization
                    self.district.append(data)

            else:
                print("No central heat grid detected — skipping heating network design.")
                data.centralDevices = {}
                data.prepareClusteringInputs()

    def optimize_network(self, saveGenerationProfiles=True):
        """
        This function optimizes the interconnected districts in the network togehter.

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        """

        # Filter interconnected districts (optim_dimension == 1) to be optimized together in the network and save them in a dictionary
        # Optimize central devices for non-interconnected districts (optim_dimension == 0) directly
        for data in self.district:
            if data.params_networkdist['optim_dimension'] == 1:
                self.interconnected_districts[data.scenario_name] = data
            elif data.params_networkdist['optim_dimension'] == 0:
                data.designCentralDevices(saveGenerationProfiles)
                data.finalizeClusterProfiles()
                print(f"Central devices of Scenario {data.scenario_name} are optimized independently with optim_dimension 0.")
            else:
                print(f"Warning: Scenario {data.scenario_name} has an invalid optim_dimension value ({data.params_networkdist['optim_dimension']}). It should be either 0 or 1. This scenario will be skipped in the optimization.")
        
            
        # Optimize central devices for interconnected districts together in the network
        if self.interconnected_districts:
            self.designCentralDevsConnected(saveGenerationProfiles) 

            # Finalize cluster profiles for all interconnected districts after optimization
            for data in self.interconnected_districts.values():
                data.finalizeClusterProfiles()
        else:
            print("No interconnected districts found (optim_dimension == 1). Skipping network optimization.")
        

    def designCentralDevsConnected(self, saveGenerationProfiles=True):
        """
        This function designs the central devices for interconnected districts all together in the network.

        Parameters
        ----------
        saveGenerationProfiles : bool, optional
            True: save central PV, STC and WT profiles as CSV-file.
            False: don't save central PV, STC and WT profiles as CSV-file.
            The default is True.
        Returns
        -------
        None.
        """

        # Get parameters of the energy hub for each district and save them in the centralDevices attribute of each district in the network
        for district in self.interconnected_districts.values():
            # Initialize central devices dictionary
            district.centralDevices = {}

            # Load parameters of the energy hub
            param, devs, dem, result_dict = load_params_central_devices.load_params(district)
            # Save parameters of the energy hub for each district
            district.centralDevices["params"] = param
            district.centralDevices["devs"] = devs
            district.centralDevices["dem"] = dem
            district.centralDevices["result_dict"] = result_dict

        # Prepare combined data for all interconnected districts
        # Initialize empty dictionary for combined parameters
        dataCon = self.interconnected_districts
        paramCon = {}
        devsCon = {}
        demCon = {}
        result_dictCon = {}  

        for district in self.interconnected_districts.values():
            # Add the params of each district to the combined dictionary
            paramCon[district.scenario_name] = district.centralDevices["params"]
            devsCon[district.scenario_name] = district.centralDevices["devs"]
            demCon[district.scenario_name] = district.centralDevices["dem"]
            result_dictCon[district.scenario_name] = district.centralDevices["result_dict"]

        # Run central optimization for the interconnected districts
        # All parameters for all districts are passed to the optimization function
        result_dictCon = opti_dimensioning_central_devices_connect.run_optim_connect(
            dataCon, devsCon, paramCon, demCon, result_dictCon
            )
        
        # Assign results to each district
        for district in self.interconnected_districts.values():
            scenario_name = district.scenario_name
            district.centralDevices["capacities"] = result_dictCon[scenario_name]
        


        for district in self.interconnected_districts.values():
            # calculate theoretical PV, STC and Wind generation
            district.centralDevices["generation"] = {}
            district.centralDevices["generation"]["PV"] = district.centralDevices["capacities"]["PV_generation_uncl"]
            district.centralDevices["generation"]["STC"] = district.centralDevices["capacities"]["STC_generation_uncl"]
            district.centralDevices["generation"]["Wind"] = district.centralDevices["capacities"]["WT_generation_uncl"]

            # optionally save generation profiles
            if saveGenerationProfiles == True:
                np.savetxt(os.path.join(district.resultPath, 'generation', f'centralPV_{district.scenario_name}.csv'),
                        district.centralDevices["generation"]["PV"],
                        delimiter=',')
                np.savetxt(os.path.join(district.resultPath, 'generation', f'centralSTC_{district.scenario_name}.csv'),
                        district.centralDevices["generation"]["STC"],
                        delimiter=',')
                np.savetxt(os.path.join(district.resultPath, 'generation', f'centralWind_{district.scenario_name}.csv'),
                        district.centralDevices["generation"]["Wind"],
                        delimiter=',')
        


         



        
 