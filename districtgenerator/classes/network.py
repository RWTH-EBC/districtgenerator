# -*- coding: utf-8 -*-

# This class can generate a network with several districts.
# Import classes of the districtgenerator to be able to use the district generator.
# Import the Datahandler class to use the district generator.
from districtgenerator.classes import Datahandler
from pathlib import Path
from .system import CES
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, NetworkDistConfig, PhysicsConfig, EHDOConfig, HeatGridConfig, CalendarConfig
import districtgenerator.functions.load_params_central_devices as load_params_central_devices
import districtgenerator.functions.opti_dimensioning_central_devices_connect as opti_dimensioning_central_devices_connect
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
            print()
            data.generateDemands(calcUserProfiles=True, saveUserProfiles=True)

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
        # old: self.interconnected_districts = [data for data in self.district if data.params_networkdist['optim_dimension'] == 1]

        for data in self.district:
            if data.params_networkdist['optim_dimension'] == 1:
                self.interconnected_districts[data.scenario_name] = data

        if not self.interconnected_districts:
            print("No interconnected districts found for optimization.")
            return
        
        # Design decentral devices for each district
        for data in self.interconnected_districts.values():
            data.designDecentralDevices()

        # Print capacities of the decentral devices in all districts
        for data in self.interconnected_districts.values():
            for device, capacity in data.district[0]["capacities"].items():
                print(f"  {device}: {capacity}")
        
        # Design central devices for interconnected districts
        for data in self.interconnected_districts.values():
            # Check if district uses central energy supply (heat grid)
            # ToDo: This check only checks if the last district has a heat grid. It could be improved by checking all districts and only designing the central devices if at least one district has a heat grid.
            has_heat_grid = any(
                building["buildingFeatures"]["heater"] == "heat_grid"
                for building in data.district)
            if has_heat_grid:
                heating_network_simple.heating_network(data)
            else:
                print("No central heat grid detected — skipping heating network design.")
                self.centralDevices = {}
            
        if has_heat_grid:
            self.designCentralDevsConnected() 
        else:
            print("No central heat grid detected — skipping heating network design.")
            

        for data in self.interconnected_districts.values():
            data.finalizeClusterProfiles()        


        
        # for i, data in enumerate(self.interconnected_districts):
        #     print(f"Scenario Name: {data.scenario_name}")
        #     print(f"Site Data: {data.site}") 
    def designCentralDevsConnected(self):
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
            #district.centralDevices["capacities"] = opti_dimensioning_central_devices_connect.run_optim_connect(district, devs, param, dem, result_dict)

        # Run central optimization for one district
        # self.interconnected_districts[0].centralDevices["capacities"] = opti_dimensioning_central_devices_connect.run_optim_connect(self.interconnected_districts[0], devs, param, dem, result_dict)
        
        # # Print centralDevices["params"] for one district
        # print(f"Params of district 1: {self.interconnected_districts[0].centralDevices["params"]}")


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
        
        # Print paramCon:
        #print(f"ParamCon: {paramCon}")

        # Print first entry of paramCon
        #paramtest = paramCon[list(paramCon.keys())[0]]
        #print(f"Param test: {paramtest}")

        # Run central optimization for the interconnected districts
        # All parameters for all districts are passed to the optimization function
        result_dictCon = opti_dimensioning_central_devices_connect.run_optim_connect(
            dataCon, devsCon, paramCon, demCon, result_dictCon
            )
        
        # Assign results to each district
        for district in self.interconnected_districts.values():
            scenario_name = district.scenario_name
            district.centralDevices["capacities"] = result_dictCon[scenario_name]

        
        #self.interconnected_districts[0].centralDevices["capacities"] = opti_dimensioning_central_devices_connect.run_optim_connect(dataCon, devsCon, paramCon, demCon, result_dictCon)
        


         



        
 