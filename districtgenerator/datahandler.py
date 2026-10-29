# -*- coding: utf-8 -*-
"""
The Datahandler runs the workflow of the districtgenerator step by step.

It holds the configuration and the district, and delegates each step to its domain package:

1. ``environment``: weather, site conditions, solar irradiance and soil temperature
2. ``buildings``: typology, thermal models and occupant-dependent demand profiles
3. ``energy_systems``: decentral and central devices, heat grid
4. ``time_series``: typical periods for the optimizations
5. ``optimization``: dimensioning and operation of the energy systems
6. ``analysis``: KPIs, plots and the certificate
"""
import json
import os

from districtgenerator.analysis.kpis import KPIs
from districtgenerator.analysis import plots
from districtgenerator.buildings import district as district_buildings
from districtgenerator.buildings.district import parse_position  # noqa: F401, kept for existing imports
from districtgenerator.buildings.profiles import demand_generation
from districtgenerator.buildings.typology import mixed_use, sia2024
from districtgenerator.config.settings import GlobalConfig, load_global_config
from districtgenerator.economics import price_paths
from districtgenerator.energy_systems import building_energy_system, central_energy_system, heating_network
from districtgenerator.environment import site as site_conditions
from districtgenerator.environment import soil, solar, weather
from districtgenerator.optimization.central import operation
from districtgenerator.storage import district_store, profile_store
from districtgenerator.time_series import clustering
from districtgenerator.utilities.paths import PACKAGE_DIR


class Datahandler:
    """
    Runs the workflow of the districtgenerator and holds the configuration and the district.

    Each public method is one workflow step and delegates the work to its domain package.

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

    def __init__(self, scenario_name = None, resultPath = None,  scenario_file_path = None,
                 srcPath = PACKAGE_DIR, filePath = None,
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

        if filePath is None:
            filePath = os.path.join(srcPath, 'data')

        self.initial_day = None
        self.district = []
        self.scenario_name = None
        self.scenario = None
        self.total_building_area = None
        # Config data
        self.site = {}
        self.time = {}
        self.design_building_data = {}
        self.physics = {}
        self.decentral_device_data = {}
        self.params_ehdo_technical = {}
        self.params_ehdo_model = {}
        self.central_device_data = {}
        self.centralDevices = {}
        self.calendar = {}
        self.ecoData = {}
        self.all_sim_ecoData = {} # Later overwriten with the calculated economic data for the simulated years
        self.heat_grid_data = {}
        self.pipe_data = {}
        self.pyomo_config = {}
        self.report_config = {}
        # Additional attributes
        self.counter = {}
        self.building_dict = {} # Dictionary to store Residential Building IDs
        self.srcPath = srcPath
        self.filePath = filePath

        if scenario_file_path is not None:
            self.scenario_file_path = scenario_file_path
        else:
            self.scenario_file_path = os.path.join(self.filePath, 'scenarios')

        if resultPath is not None:
            self.resultPath = resultPath
        else:
            self.resultPath = os.path.join(self.srcPath, 'results')

        self.load_all_data(env_path=env_path, scenario_name=scenario_name)

        self.KPIs = None
        self.buildings_completed = 0
        self.buildings_total = 0
        self.progress_file = os.path.join(self.resultPath, 'progress.json')

    def get_progress(self):
        return {
            'completed': self.buildings_completed,
            'total': self.buildings_total,
            'percentage': (self.buildings_completed / max(self.buildings_total, 1)) * 100,
        }

    def save_progress(self):
        if self.progress_file:
            progress_data = self.get_progress()

            try:
                with open(self.progress_file, 'w') as f:
                    json.dump(progress_data, f)
            except Exception as e:
                print(f"Couldn't save calculation progress: {e}")

    def load_all_data(self, env_path, scenario_name):
        """
        Load all data needed for district generation from configuration files.

        Parameters
        ----------
        env_path : str, optional
            Path to the environment configuration file. If None, it defaults to the global configuration file.
        scenario_name : str, optional
            Name of the scenario file

        Returns
        -------
        None.
        """
        # --- 1. Load all configs into the dictionaries of the Datahandler ---
        global_config: GlobalConfig = load_global_config(env_file=env_path)
        sections = (
            (self.site, global_config.location),                        # site and weather
            (self.time, global_config.time),                            # time resolution and clustering
            (self.design_building_data, global_config.design_building), # buildings, envelopes and systems
            (self.physics, global_config.physics),                      # building physics
            (self.decentral_device_data, global_config.decentral),      # decentral devices
            (self.params_ehdo_model, global_config.ehdo),               # energy hub model
            (self.ecoData, global_config.eco),                          # prices and CO2 factors
            (self.central_device_data, global_config.central),          # central devices
            (self.calendar, global_config.calendar),                    # holidays and calendar
            (self.pyomo_config, global_config.pyomo),                   # solver settings
            (self.report_config, global_config.report),                 # KPI and certificate output
            (self.heat_grid_data, global_config.heatgrid),              # heat grid design
        )
        for target, section in sections:
            target.update(section.__dict__)

        self.scenario_name = scenario_name or global_config.scenario.scenario_name or "example_decentral"
        self.parallelization = global_config.scenario.parallelization
        self.random_seed = global_config.scenario.random_seed
        self.flat_parallelization = global_config.scenario.flat_parallelization
        self.flat_max_workers = global_config.scenario.flat_max_workers
        self.design_energy_hub = global_config.scenario.design_energy_hub

        # --- 2. Load the scenario file with one row per building ---
        self.scenario = district_buildings.load_scenario(self.scenario_file_path, self.scenario_name)

        # --- 3. Load the pipe catalogue of the selected heat grid generation ---
        self.pipe_file_path = os.path.join(self.filePath, 'pipe')
        self.pipe_data = heating_network.load_pipe_data(self.heat_grid_data["generation"], self.pipe_file_path)

        # Prices and CO2 factors for each simulated year used in the optimizations
        self.all_sim_ecoData = self.calculate_ecoData_per_cluster()

        self.SIA2024 = sia2024.read_SIA_data()

    def select_plz_data(self):
        """
        Select the closest TRY weather station for the location of the postal code.

        Returns
        -------
        None.
        """
        site_conditions.select_plz_data(self)

    def get_holidays(self, country_code: str, year: int, state: str = None):
        """
        Get the Julian day (day of the year) for holidays in a specific country, year, and state.

        Parameters
        ----------
            country_code : string
                The country's ISO 3166-1 alpha-2 code (e.g., 'DE' for Germany).
            year : integer
                The year for which to retrieve holidays.
            state : string
                The state or region subdivision code (e.g., 'NW' for North Rhine-Westphalia in Germany).

        Returns
        -------
            julian_holidays : list
                A list of tuples containing the Julian day of the holiday.
        """
        return site_conditions.get_holidays(country_code, year, state)

    def generateEnvironment(self):
        """
        Load physical district environment - site and weather.

        Returns
        -------
        None.
        """
        weather.load_weather(self)
        site_conditions.load_site_conditions(self)
        solar.calculate_surface_irradiance(self)

        # calculate the soil temperature profile
        dt = self.time["timeResolution"] / self.time["dataResolution"]
        soil.calculate_soil_temperature(self, dt)

    def is_mixed_building(self, building_type):
        """
        Check if a building type is a mixed-use building (contains "+").

        Parameters
        ----------
        building_type : str
            The building type string (e.g., "MFH+RETAIL").

        Returns
        -------
        bool
            True if the building type contains "+", False otherwise.
        """
        return mixed_use.is_mixed_building(building_type)

    def combine_mixed_building_demands(self, saveUserProfiles):
        """
        Combine demand profiles from split mixed-use buildings back into a single building.
        This should be called after generateDemands() but before designDecentralDevices().

        Creates a new combined building with summed demand profiles.
        Both main and secondary buildings are deleted, replaced by the combined building.
        An Excel file is created for each combined building showing all demand profiles.

        Returns
        -------
        None
        """
        mixed_use.combine_mixed_building_demands(self, saveUserProfiles)

    def initializeBuildings(self):
        """
        Fill district with buildings from scenario file.

        Parameters
        ----------
        scenario_name: string, optional
            Name of scenario file to be read. The default is 'example'.

        Returns
        -------
        None.
        """
        district_buildings.initialize_buildings(self)

    def split_mixed_buildings(self):
        """
        Splits mixed-use buildings into main and secondary building parts.
        """
        mixed_use.split_mixed_buildings(self)

    def generateBuildings(self):
        """
        Load building envelope and user data.

        Returns
        -------
        None.
        """
        district_buildings.generate_buildings(self)

    def generateDemands(self, calcUserProfiles=True, saveUserProfiles=True, max_workers=8, gen_cars=True):
        """
        Generate demand profiles for all buildings.

        Parameters
        ----------
        calcUserProfiles : bool, optional
            Whether user profiles should be calculated.
        saveUserProfiles : bool, optional
            Whether generated user profiles should be saved.
        max_workers : int, optional
            Maximum number of parallel workers.
        gen_cars : bool, optional
            Whether car profiles should be generated.
        use_multiprocessing : str
            ProcessPoolExecutor or ThreadPoolExecutor is used.
        """
        demand_generation.generate_demands(self, calcUserProfiles=calcUserProfiles, saveUserProfiles=saveUserProfiles,
                                           max_workers=max_workers, gen_cars=gen_cars)

    def generate_demands_worker(self, building, calcUserProfiles, saveUserProfiles, gen_cars = True):
        """
        :param building:
        :param calcUserProfiles: bool
            True: calculate new user profiles.
            False: load user profiles from file.
            The default is True.
        :param saveUserProfiles: bool
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True).
            The default is True.
        """
        return demand_generation.run_demand_worker(demand_generation.demand_context(self), building,
                                                   calcUserProfiles, saveUserProfiles, gen_cars)

    def generateDistrictComplete(self, calcUserProfiles=True, saveUserProfiles=True, gen_cars=True, designEnergyhub=None):
        """
        All in one solution for district and demand generation.
        Within a clustered time series, data points are aggregated across different time periods
        based on the k-medoids method.

        Parameters
        ----------

        calcUserProfiles: bool, optional
            True: calculate new user profiles.
            False: load user profiles from file.
            The default is True.
        saveUserProfiles: bool, optional
            True for saving calculated user profiles in workspace (Only taken into account if calcUserProfile is True).
            The default is True.
        gen_cars: bool, optional
            True for generating car profiles, False to skip this step (Only taken into account if calcUserProfile is True).
        designEnergyhub: bool or None, optional
            Request energy-hub design without a thermal network. None uses
            DESIGN_ENERGY_HUB from the configuration (default False).
            An explicit True or False overrides the configuration; a heat-grid
            connection always triggers energy-hub design.
        
        Returns
        -------
        None.
        """
        if designEnergyhub is None:
            designEnergyhub = self.design_energy_hub

        self.generateEnvironment()
        self.initializeBuildings()
        self.generateBuildings()
        self.generateDemands(calcUserProfiles, saveUserProfiles, gen_cars=gen_cars)
        self.designDecentralDevices(saveGenerationProfiles=True)

        # Central energy supply: a thermal network, an energy hub, or both
        if heating_network.has_thermal_grid(self.district) or designEnergyhub:
            heating_network.design_thermal_network(self)
            self.designCentralDevices(saveGenerationProfiles=True)
            self.applyCentralDesignClusteringToOperationProfiles()
        else:
            print("No thermal network detected and no energy hub requested — skipping thermal network design.")
            self.centralDevices = {}
            self.prepareClusteringInputs()

    def saveProfiles(self, name, elec, dhw, dhw_minutely, occ, gains, EV_carcharging_ondemand,
                     EV_carprofile, ev_capacity, ice_carprofile, nb_units,
                     nb_occ, heatload, bivalent, heatlimit, path,
                     individual_car_profiles=None): #TODO: Check why coolingload is not saved here. Similary about dhwpower
        """
        Save profiles to csv.

        Parameters
        ----------
        name : string
            Unique building name.
        elec : list
            Hourly electricity demand in W.
        dhw : list
            Hourly domestic hot water demand in W.
        dhw_minutely : list
            Minutely domestic hot water demand in W.
        occ : list
            Hourly occupancy of persons.
        gains : list
            Hourly internal gains in W.
        car : list
            Hourly electricity demand of EV in W.
        nb_flats : int
            Number of flats in the building.
        nb_occ : list
            Number of occupants in the building.
        heatload : float
            Design heat load in W.
        bivalent : float
            Bivalent heat load in W.
        heatlimit : float
            Heat limit heat load in W.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        profile_store.save_profiles(name=name, elec=elec, dhw=dhw, dhw_minutely=dhw_minutely, occ=occ, gains=gains,
                                    EV_carcharging_ondemand=EV_carcharging_ondemand, EV_carprofile=EV_carprofile,
                                    ev_capacity=ev_capacity, ice_carprofile=ice_carprofile, nb_units=nb_units,
                                    nb_occ=nb_occ, heatload=heatload, bivalent=bivalent, heatlimit=heatlimit,
                                    path=path, time_cfg=self.time, individual_car_profiles=individual_car_profiles)

    def saveHeatingProfile(self, heat, cooling, name, path):
        """
        Save heating demand to csv.

        Parameters
        ----------
        heat: list
            Hourly heating demand in W.
        cooling: list
            Hourly cooling demand in W.
        name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        profile_store.save_heating_profile(heat=heat, cooling=cooling, name=name, path=path)

    def loadProfiles(self, name, path, gen_cars=True):
        """
        Load profiles from csv.

        Parameters
        ----------
        name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        return profile_store.load_profiles(name, path, self.time, gen_cars=gen_cars)

    def loadHeatingProfiles(self, name, path):
        """
        Load profiles from csv.

        Parameters
        ----------
        name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """
        return profile_store.load_heating_profiles(name=name, path=path)

    def designDecentralDevices(self, saveGenerationProfiles=True):
        """
        Calculate capacities, generation profiles of renewable energies and EV load profiles for decentral devices.

        Parameters
        ----------
        saveGenerationProfiles : bool, optional
            True: save decentral PV and STC profiles as CSV-file.
            False: don't save decentral PV and STC profiles as CSV-file.
            The default is True.

        Returns
        -------
        None.
        """
        building_energy_system.design_decentral_devices(self, saveGenerationProfiles=saveGenerationProfiles)

    def designCentralDevices(self, saveGenerationProfiles):
        """
        Calculate capacities and generation profiles of renewable energies for central devices.

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
        central_energy_system.design_central_devices(self, saveGenerationProfiles)

    def prepareClusteringInputs(self):
        """
        Prepare and cluster building-level demand and environmental data.
        """
        print("Preparing initial clustering (pre-optimization)...")
        self.clusterProfiles(centralEnergySupply=False)

    def finalizeClusterProfiles(self):
        """
        Perform final clustering including central generation and
        heating network losses after optimization.
        """
        print("Finalizing clustering (post-optimization)...")
        self.clusterProfiles(centralEnergySupply=True)

    def applyCentralDesignClusteringToOperationProfiles(self):
        """
        Reuse the design-stage clustering (already computed while dimensioning the
        central devices) as the operational clustering, instead of independently
        re-clustering the per-building profiles a second time.
        """
        clustering.apply_design_clustering(self)

    def clusterProfiles(self, centralEnergySupply):
        """
        Perform time series aggregation for profiles by using the k-medoids clustering algorithm.

        Returns
        -------
        None.
        """

        (self.clusters, self.clusterAssignments, self.clusterWeights,
         self.site, self.district, self.heat_grid_data) = (clustering.clustering_processing(self.time, self.site, self.district,
                                                                                            self.heat_grid_data, self.centralDevices,
                                                                                            self.pyomo_config, centralEnergySupply))

        for building in self.district:
            envelope = building.get("envelope")
            if envelope is not None and hasattr(envelope, "compute_heating_curve"):
                envelope.compute_heating_curve(self.site, mode="clustered")

    def saveDistrict(self):
        """
        Save district dict as pickle file.

        Returns
        -------
        None.
        """
        district_store.save_district(self)

    def loadDistrict(self, scenario_name='example'):
        """
        Load district dict from pickle file.

        Parameters
        ----------
        scenario_name : string, optional
            Name of district file to be read. The default is 'example'.

        Returns
        -------
        None.
        """
        district_store.load_district(self, scenario_name=scenario_name)

    def plot(self, mode='default', initialTime=0, timeHorizon=31536000, savePlots=True, timeStamp=False, show=False):
        """
        Create plots of the energy consumption and generation.

        Parameters
        ----------
        mode : string, optional
            Choose a single plot or show all of them as default. The default is 'default'.
            Possible modes are:
            ['elec', 'dhw', 'gains', 'occ', 'car', 'heating', 'pv', 'stc', 'electricityDemand', 'heatDemand'].
        initialTime : integer, optional
            Start of the plot in seconds from the beginning of the year. The default is 0.
        timeHorizon : integer, optional
            Length of the time horizon that is plotted in seconds. The default is 31536000 (what equals one year).
        savePlots : boolean, optional
            Decision if plots are saved under results/plots/. The default is True.
        timeStamp : boolean, optional
            Decision if saved plots get a unique name by adding a time stamp. The default is False.
        show : boolean, optional
            Decision if saved plots are presented directly to the user. The default is False.

        Returns
        -------
        None.
        """
        plots.plot_district(self, mode=mode, initialTime=initialTime, timeHorizon=timeHorizon, savePlots=savePlots,
                            timeStamp=timeStamp, show=show)

    def optimizationClusters(self):
        """
        Optimize the operation costs for each cluster.

        Returns
        -------
        None.
        """
        operation.optimize_all_clusters(self)

    def calculate_ecoData_per_cluster(self):
        """Prices and CO2 factors for each simulated year, see economics.price_paths."""
        return price_paths.calculate_eco_data_per_simulated_year(self.ecoData)

    def calculateKPIs(self):
        """
        Calculate key performance indicators (KPIs).

        Returns
        -------
        None.
        """

        # initialize KPI class
        self.KPIs = KPIs(self)
        # calculate KPIs
        self.KPIs.calculateAllKPIs(self)
