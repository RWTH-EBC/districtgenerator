# -*- coding: utf-8 -*-

# This class can generate a network with several districts.
# Import classes of the districtgenerator to be able to use the district generator.
# Import the Datahandler class to use the district generator.
from districtgenerator.classes import Datahandler
from pathlib import Path
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, GurobiConfig, HeatGridConfig, CalendarConfig

class Network:
    def __init__(self):
        """
        Constructor of Network class.

        Parameters
        ----------
        network: List of districts

        Returns
        -------
        None.
        """
        self.district = []
        self.interconnected_districts = []
    
    def initializeDistricts(self,configs_dir: Path, calcUserProfiles=True, saveUserProfiles=True):
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
            model_param_eh = data.params_ehdo_model
            print(f"\nOptim_dimension of: {data.scenario_name} is {model_param_eh['optim_dimension']}")

            # Generate Environment for the District
            data.generateEnvironment()

            # Initialize Buildings to the District
            data.initializeBuildings()

            # Generate more detailed Building models
            data.generateBuildings()

            # Generate building specific demand profiles with the adjusted assumptions
            # Use calcUserProfiles=False to speed up the calculation if user profiles are already calculated
            data.generateDemands(calcUserProfiles, saveUserProfiles)

            self.district.append(data)

    def optimize_network(self):
        """
        This function optimizes the interconnected districts in the network togehter.

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        """
        # Filter interconnected districts (optim_dimension == 1)
        self.interconnected_districts = [data for data in self.district if data.params_ehdo_model['optim_dimension'] == 1]

        if not self.interconnected_districts:
            print("No interconnected districts found for optimization.")
            return
        
        # design decentral devices for each district
        for data in self.interconnected_districts:
            data.designDecentralDevices()
            for building in data.district:
                if "capacities" in building:
                    print(f"Building: {building['unique_name']}")
                    print("Capacities:")
                    for device, capacity in building["capacities"].items():
                        print(f"  {device}: {capacity}")
                else:
                    print(f"Building: {building['unique_name']} has no capacities defined.")
        
        # for i, data in enumerate(self.interconnected_districts):
        #     print(f"Scenario Name: {data.scenario_name}")
        #     print(f"Site Data: {data.site}") 



        
 