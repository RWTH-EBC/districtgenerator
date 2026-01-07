from dataclasses import field
from pathlib import Path
import os

from typing import Any, Dict, Optional, Set, Tuple, Type, ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource

from dotenv import dotenv_values

class WasteHeatConfig(BaseSettings):
    """Configuration for waste heat sources in a district energy system.

    This class defines the default parameters for various waste heat sources such as
    data centers (DC), cold storages, wastewater treatment plants and various industry sources

    Each device has parameters such as feasibility, efficiency, lifetime, investment costs,
    and operational characteristics.
    """
    # DC parameters (data center)
    DC__feasible: bool = True             # Will be set to false if this waste heat source is not simulated
    DC__IT_Load: float = 100              # IT-Load in kW: possible values: ......
    DC__PUE: float = 1.4                  # Power Usage Effectivness (total load/ IT load): values for air-cooled DCs: ..., values for water-cooled DCs: ...
    DC__profile_type: str = "calc"        # will the load-profile be loaded or calculated?
    DC__wh_temperature: int = 35          # in celsius, depends on the cooling mechanism and the location for capturing waste heat: values for air-cooled DCs: ..., values for water-cooled DCs: ...
    DC: dict = {}

    # paper_industry parameters
    paper__feasible: bool = True          # Will be set to false if this waste heat source is not simulated
    paper__prod_quantity: float = 10000     # yearly production volume in t
    paper__spec_electricity: float = 5    # specific electricity consumption in kWh/t
    paper__spec_wh: float = 2             # specific waste heat generation in kWh/t
    paper__profile_type: str = "load"     # will the load-profile be loaded or calculated?
    paper__wh_temperature: int = 25       # waste heat temperature in celsius
    paper: dict = {}



    @model_validator(mode='after')
    def build_device_dicts(self) -> 'WasteHeatConfig':
        """Build all device dictionaries from individual parameters."""

        # Create a list of field names to avoid RuntimeError during iteration
        field_names = list(self.__dict__.keys())

        # Get all field names from the model
        for field_name in field_names:
            # Check if this is a dictionary field (uppercase device name)
            if isinstance(getattr(self, field_name), dict):
                # Only build if the dictionary is empty
                if getattr(self, field_name) == {}:
                    device_dict = {}
                    prefix = f"{field_name}__"
                    feasible_attr = f"{field_name}__feasible"

                    if hasattr(self, feasible_attr) and not getattr(self, feasible_attr):
                        delattr(self, field_name)
                    else:
                        # Find all attributes that start with this device prefix
                        for attr_name in field_names:  # Use the snapshot here too
                            if attr_name.startswith(prefix):
                                # Remove the prefix to get the dictionary key
                                dict_key = attr_name[len(prefix):]
                                device_dict[dict_key] = getattr(self, attr_name)

                        # Set the dictionary first
                        setattr(self, field_name, device_dict)


                    # Now delete the individual attributes
                    for attr_name in field_names:
                        if attr_name.startswith(prefix):
                            delattr(self, attr_name)

        return self

    model_config = SettingsConfigDict(
        env_prefix="WH_",
        env_file=".wasteheatconfig",
        extra="ignore"
    )


### Global Config Classes ###

class GlobalConfig(BaseModel):
    """
    GlobalConfig class to manage all configurations for the district generator.
    This class aggregates all individual configuration classes and provides a unified interface
    to access them. It is designed to be initialized with an environment file that contains
    configuration parameters for each component.
    Note: All parameters defined in this '.env.CONFIG.' will override the default values in config.py

    Attributes
    ----------
    location : LocationConfig
        Configuration parameters related to the location of the buildings.
    time : TimeConfig
        Configuration parameters related to time settings, such as time resolution and cluster length.
    design_building : DesignBuildingConfig
        Configuration parameters for design aspects of buildings in the district.
    eco : EcoConfig
        Economic parameters, including prices and CO2 emissions for various energy sources.
    physics : PhysicsConfig
        Physical constants and parameters used in the districtgenerator.
    pyomo : PyomoConfig
        Configuration parameters for the Pyomo optimization solver.
    heatgrid : HeatGridConfig
        Configuration parameters for the heat grid, including temperatures and heat transfer.
    ehdo : EHDOConfig
        Configuration parameters for the EHDO (Energy and Heat Distribution Optimization) system.
    decentral : DecentralDeviceConfig
        Configuration parameters for decentralized devices in the district.
    central : CentralDeviceConfig
        Configuration parameters for central devices in the district.
    calendar : CalendarConfig
        Configuration parameters for calendar settings, such as holidays and initial days.
    scenario_name : ScenarioName
        The name of the scenario being configured, used for identification and output purposes.

    """
    waste_heat: WasteHeatConfig

class Settings(BaseSettings):
    """
    Settings class to manage global configuration parameters.
    This class is used to load configuration parameters from an environment file.
    """
    env_file: str = '.env.CONFIG.EXAMPLE'

    class Config:
        env_file = '.env.CONFIG.EXAMPLE'  # Default .env file if no env_file is provided
        env_file_encoding = 'utf-8'
        extra = 'ignore' # Ignores all other variables in the .env.CONFIG file


def load_global_config(env_file: Optional[str] = None) -> GlobalConfig:
    """
    Load the global configuration from the specified environment file.
    If no environment file is provided, it defaults to standard parameters defined in the config classes.
    For error handling, it prints the used environment file path.
    Note: All parameters defined in '.env.CONFIG.' will override the default values in config.py

    Parameters
    ----------
    env_file : Optional[str]
        The path to the environment file. If None, it uses the default from Settings.
        Place config in the data folder of the districtgenerator package to use ".env.NAME" or use
        absolute paths "c:/path/to/.env.CONFIG.EXAMPLE" or "/path/to/.env.CONFIG.EXAMPLE".

    Returns
    -------
    GlobalConfig
        An instance of GlobalConfig containing all configurations loaded from the environment file.

    """
    if env_file is None:
        settings = Settings()  # Load settings from the .env file
        env_file = settings.env_file

    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    env_file_path = str(project_root / "data" / env_file)

    if not os.path.exists(env_file_path):
        raise FileNotFoundError(
            f"Configuration file not found. \n"
            f"  - Looked for: {env_file_path}\n"
            f"  - Based on script location: {script_path}"
        )

    os.environ["ENV_FILE"] = env_file_path
    print(f'Using config: {os.environ["ENV_FILE"]}')

    return GlobalConfig(waste_heat=WasteHeatConfig(_env_file=env_file_path))



class WasteHeat:
    """
    Abstract class for data handling.
    Collects data from input files, TEASER, User and Envelope.

    Attributes
    ----------
    site:
        Dict for site data, e.g. weather.
    time:
        Dict for time settings.
    district:
        List of all buildings within district.
    scenario_name:
        Name of scenario file.
    scenario:
        Scenario data.
    counter:
        Dict for counting number of equal building types.
    srcPath:
        Source path.
    filePath:
        File path.
    """

    def __init__(self,
                 scenario_name = None,
                 resultPath = None,
                 scenario_file_path = None,
                 srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 filePath = None,
                 env_path = None):
        """
        Constructor of Datahandler class.

        Parameters
        ----------
        scenario_name : str, optional
            Name of the scenario file. If none given, takes scenario_name from globalConfig else "example".
        resultPath : str, optional
            Path to save results. If None, it defaults to 'srcPath/results'.
        scenario_file_path : str, optional
            Path to the scenario file. If None, it defaults to 'filePath/scenarios'.
        srcPath : str, optional
            Source path of the district generator. The default is the parent directory of this file.
        filePath : str, optional
            Path to the data directory. If None, it defaults to 'srcPath/data'.
        env_path : str, optional
            Path to the environment configuration file. If None, it defaults to the global configuration file.

        Returns
        -------
        None.
        """

        global_config: GlobalConfig = load_global_config(env_file=env_path)

        if filePath is None:
            filePath = os.path.join(srcPath, 'data')

        self.waste_heat_data = {}

        self.load_all_data(waste_heat_config=global_config.waste_heat)



    def load_all_data(self, waste_heat_config: WasteHeatConfig):
        """
        Load all data needed for district generation from configuration files.

        Parameters
        ----------
        site_config : LocationConfig
            Location configuration data.
        time_config : TimeConfig
            Time configuration data.
        design_building_config : DesignBuildingConfig
            Design building configuration data.
        physics_config : PhysicsConfig
            Physics configuration data.
        decentral_config : DecentralDeviceConfig
            Decentral device configuration data.
        ehdo_config : EHDOConfig
            EHDO model configuration data.
        eco_config : EcoConfig
            Economic configuration data.
        central_config : CentralDeviceConfig
            Central device configuration data.
        calendar_config : CalendarConfig
            Calendar configuration data.
        heat_grid_config : HeatGridConfig
            Heat grid configuration data.
        Returns
        -------
        None.
        """


        # load waste heat data (used in generate WHProfiles)
        for attr, value in waste_heat_config.__dict__.items():
            self.waste_heat_data[attr] = value

    def generateWHProfiles(self):

        json_path = os.path.join(self.scenario_file_path, "wh_source.json")

        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as json_file:
                jsonData = json.load(json_file)
                wh_source = jsonData[0]["type"]
                position = jsonData[0]["position"]

        key_waste_heat = [key for key, value in self.waste_heat_data.items()
                          # extracts key from all waste heat applications defined in the Config class
                          if isinstance(value, dict)]

        for i in key_waste_heat:
            if i != wh_source:
                del (self.waste_heat_data[i])

        self.waste_heat_data["position"] = position



        def loadProfile(name, path):

            # ratio between specific electricity and heat, and yearly energy consumption
            wh_to_elec = self.waste_heat_data[wh_source]["spec_wh"] / self.waste_heat_data[wh_source][
                "spec_electricity"]
            E_ges = self.waste_heat_data[wh_source]["spec_electricity"] * self.waste_heat_data[wh_source][
                "prod_quantity"]

            # create array with value from the csv file
            csv_file = os.path.join(path, name + '.csv')
            df = pd.read_csv(csv_file, usecols=["Mean_Value"], sep=";", decimal=",")
            profile = df["Mean_Value"].to_numpy()[1:]

            # adjust array with profile data, in case it is missing entries or has to many of them
            if len(profile) >= 35040:
                profile = profile[:35040]
            else:
                missing = 35040 - len(profile)
                profile = np.concatenate([profile, np.full(missing, profile[-1])])  #TODO add interpolation and adjust to match initial days and holidays

            # convert the profile to an hourly profile (original data consists of 15 min steps)
            hourly_profile = profile.reshape(-1, 4).mean(axis=1)

            # create electricity and waste heat profile
            elec_profile = hourly_profile * (E_ges / np.sum(hourly_profile))
            wh_profile = elec_profile * wh_to_elec

            return wh_profile

        def calcProfile(name, temperature, time_resolution, time_horizon):

            timesteps = int(time_horizon / time_resolution)

            if name == "DC":
                it_load = self.waste_heat_data[wh_source]["IT_Load"]
                pue = self.waste_heat_data[wh_source]["PUE"]
                profile = np.full(timesteps, it_load)
                # Cooling Degree Day Methode
                T_ref = 18                           #TODO change name of variable
                CDD_ges = 0
                CDD = []
                for i in range(timesteps):
                    if temperature[i] > T_ref:
                        CDD.append(temperature[i] - T_ref)
                        CDD_ges += temperature[i] - T_ref
                    else:
                        CDD.append(0)
                for i in range(timesteps):
                    profile[i] += it_load * (pue - 1) * (CDD[i] / CDD_ges) * timesteps

            return profile



        if self.waste_heat_data[wh_source]["profile_type"] == "load":
            self.waste_heat_data["profile"] = loadProfile(name=wh_source, path=os.path.join(self.resultPath, 'demands'))
        else:
            self.waste_heat_data["profile"] = calcProfile(wh_source, self.site["T_e"], self.time["timeResolution"],
                                                          self.time["dataLength"])

        waste_heat_profile = self.waste_heat_data["profile"]


        return waste_heat_profile




#TODO clusterprofiles, designnetworkwithnode und designnetworkwithroad, wenn möglich, hinzufügen


