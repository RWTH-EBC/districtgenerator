# -*- coding: utf-8 -*-

# This class can generate a network with several districts.
# Import classes of the districtgenerator to be able to use the district generator.
# Import the Datahandler class to use the district generator.
from districtgenerator.classes import Datahandler
from pathlib import Path
from .system import CES
from districtgenerator.data_handling.config import GlobalConfig, load_global_config, LocationConfig, TimeConfig, DesignBuildingConfig, EcoConfig, PhysicsConfig, EHDOConfig, GurobiConfig, HeatGridConfig, CalendarConfig
import districtgenerator.functions.heating_network as heating_network
import districtgenerator.functions.load_params_central_devices as load_params_central_devices
import districtgenerator.functions.opti_dimensioning_central_devices_connect as opti_dimensioning_central_devices_connect

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


       # Check if the interconnected districts use a heat grid as heating system
        if all(data.district[0]["buildingFeatures"]["heater"] == "heat_grid" for data in self.interconnected_districts):
            self.designCentralDevsConnected() 
        else:
            print("The interconnected districts do not use a heat grid as heating system.")


        
        # for i, data in enumerate(self.interconnected_districts):
        #     print(f"Scenario Name: {data.scenario_name}")
        #     print(f"Site Data: {data.site}") 
    def designCentralDevsConnected(self):
        """
        This function designs the central devices for interconnected districts all togeether in the network.

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        """
        
        for district in self.interconnected_districts:
            # Initialize central devices dictionary
            district.centralDevices = {}
            # Load parameters of the heating network
            district = heating_network.heating_network(data=district)
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

        for district in self.interconnected_districts:
            # Check if 'params' key exists in centralDevices
            if "params" in district.centralDevices:
                # Add the params of each district to the combined dictionary
                paramCon[district.scenario_name] = district.centralDevices["params"]
                devsCon[district.scenario_name] = district.centralDevices["devs"]
                demCon[district.scenario_name] = district.centralDevices["dem"]
                result_dictCon[district.scenario_name] = district.centralDevices["result_dict"]
            else:
                print(f"No 'params' data found for district: {district.scenario_name}")


        
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
        for district in self.interconnected_districts:
            scenario_name = district.scenario_name
            if scenario_name in result_dictCon:
                district.centralDevices["capacities"] = result_dictCon[scenario_name]
            else:
                print(f"No results found for district: {scenario_name}")
        
        #self.interconnected_districts[0].centralDevices["capacities"] = opti_dimensioning_central_devices_connect.run_optim_connect(dataCon, devsCon, paramCon, demCon, result_dictCon)
        


         



        
 