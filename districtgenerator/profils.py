# -*- coding: utf-8 -*-
"""
"""
import os
import numpy as np
import random as rd
import richardsonpy.classes.occupancy as occ
import richardsonpy.functions.change_resolution as cr
import functions.dhw_stochastical as dhw_profil
import functions.schedule_reader as schedule_reader 
import pylightxl as xl

class Profiles():
    """
    Profile class
    calculating user related profiles of a building or flat

    Parameters
    ----------
    number_occupants : integer
        Number of occupants who live in the house or flat.
    initial_day : integer
        Day of the week with which the generation starts
        1-7 for monday-sunday.
    nb_days : integer
        Number of days for which a stochastic profile is generated.
    time_resolution : integer
        resolution of time steps of output array in seconds.

    Attributes
    ----------
    activity_profile : array
        Numpy-arry with acctive occupants 10-minutes-wise.
    occ_profile : array
         stochastic occupancy profiles for a district
    app_load : Array-like
        Electric load profile of appliances in W.
    light_load : Array-like
        Electric load profile of lighting in W.
    """

    def __init__(self, number_occupants, initital_day, nb_days, time_resolution):

        """
        Constructor of Profiles Class
        """

        self.number_occupants = number_occupants
        self.initial_day = initital_day
        self.nb_days = nb_days
        self.time_resolution = time_resolution

        self.activity_profile = []
        self.occ_profile = []
        self.light_load = []
        self.app_load = []

        self.generate_activity_profile()
        self.loadProbabilitiesDhw()

    def generate_activity_profile(self):
        """
        Generate a stochastic activity profile
        (on base of ridchardsonpy)

        Parameters
        ----------
        number_occupants : integer
            Number of occupants who live in the house or flat.
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.
        nb_days : integer
            Number of days for which a stochastic profile is generated.

        """

        activity = occ.Occupancy(self.number_occupants, self.initial_day, self.nb_days)
        self.activity_profile = activity.occupancy


    def generate_occupancy_profiles(self):
        """
        Generate stochastic occupancy profiles for a district for calculating internal gains.
        Change time resolution of 10 min profiles to required resolution

        Parameters
        ----------
        time_resolution : integer
            resolution of time steps of output array in seconds.
        activity_profile : array
            Numpy-arry with acctive occupants 10-minutes-wise.

        """
        # To-Do: calculate the 
        # To-Do: Check wheter 10 min is really necessary 
        tr_min = int(self.time_resolution/60)
        sia_profile_daily_min = np.concatenate((np.ones(60*8),
                                                np.zeros(60*13),
                                                np.ones(60*3)),
                                                axis=None)


        # generate array for minutly profile
        activity_profile_min = np.zeros(len(self.activity_profile)*10)
        # generate array for time adjusted profile
        self.occ_profile = np.zeros(int(len(self.activity_profile)*10/tr_min))

        # append minutly sia profiles until nb_days is reached
        sia_profile = []
        while len(sia_profile) < len(activity_profile_min):
            sia_profile = np.concatenate((sia_profile,sia_profile_daily_min),axis=None)
        sia_profile = sia_profile * max(self.activity_profile)

        # calculate minutely profile
        for t in range(len(activity_profile_min)):
            activity_profile_min[t] = max(self.activity_profile[int(t/10)],sia_profile[t])
        for t in range(len(self.occ_profile)):
            self.occ_profile[t] = np.round(np.mean(activity_profile_min[(t*tr_min):(t*tr_min+tr_min)]))

        return self.occ_profile


    def loadProbabilitiesDhw(self):
        """
        Load probabilities of dhw usage
        """

        #  Define src path
        src_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        filename = 'dhw_stochastical.xlsx'
        path_DHW = os.path.join(src_path, 'districtgenerator', 'data', filename)


        # Initialization
        profiles = {"we": {}, "wd": {}}
        # book = xlrd.open_workbook(filename)
        book = xl.readxl(fn=path_DHW)
        sheetnames = book.ws_names

        # Iterate over all sheets
        for sheetname in sheetnames:
            # sheet = xl.readxl(fn=filename, ws=sheetname)

            # Read values
            values = [book.ws(ws=sheetname).index(row=i, col=1) for i in
                      range(1, 1441)]  # [sheet.cell_value(i,0) for i in range(1440)]

            # Store values in dictionary
            if sheetname in ("wd_mw", "we_mw"):
                profiles[sheetname] = np.array(values)
            elif sheetname[1] == "e":
                profiles["we"][int(sheetname[2])] = np.array(values)
            else:
                profiles["wd"][int(sheetname[2])] = np.array(values)

        # Load profiles
        self.prob_profiles_dhw = profiles


    def generate_dhw_profile(self):
        """
        Generate a stochastic dhw profile
        (on base of pycity_base)

        Parameters
        ----------
        time_resolution : integer
            resolution of time steps of output array in seconds.
        activity_profile : array
            Numpy-arry with acctive occupants 10-minutes-wise.
        prob_profiles_dhw: array
            probabilities of dhw usage
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.

        Returns
        -------
        dhw_heat : array
            Numpy-array with heat demand of dhw consumption in W.

        """

        # Run simulation
        # run the simulation for just x days
        # therefor occupancy has to have the length of x days
        (dhw_water, dhw_heat) = dhw_profil.full_year_computation(self.activity_profile,
                                                         self.prob_profiles_dhw,
                                                         self.time_resolution,
                                                         self.initial_day)

        return dhw_heat


    def generate_el_profile(self, irradiance, el_wrapper,
                            annual_demand, do_normalization = True):
        """
        Generate electric load profile for one household

        Parameters
        -------
        irradiance : array
            if none is given default weather data (TRY 2015 Potsdam) is used
        el_wrapper : object
            This objects holdes information about the lighting and appliance configuration.
        annual_demand : integer
            Annual elictricity demand in kWh.
        do_normalization : boolean
            Normalize el. load profile to annual_demand
        Returns
        -------
        loadcurve : Array-like
            Total electric load profile in W.

        """

        # Make simulation over x days
        demand = []

        #  Check if irradiance timestep is identical with param. timestep
        timesteps_irr = int(self.nb_days * 3600 * 24 / len(irradiance))

        if self.time_resolution != timesteps_irr:  # pragma: no cover
            msg = 'Time discretization of irradiance is different from ' \
                  'timestep ' \
                  + str(self.time_resolution) \
                  + 'seconds . You need to change the resolution, first!'
            raise AssertionError(msg)

        _timestep_rich = 60  # timesteps in seconds

        # number of timesteps per day for given time resolution
        timesteps_per_Day = int(86400 / self.time_resolution)

        # Array holding index of timesteps (60 second timesteps)
        ### Irradiance is needed for every minute of the day
        required_timestamp = np.arange(1440)

        # Array holding each timestep in seconds
        ### the timesteps of the irradiance array in minutes
        given_timestamp = self.time_resolution / _timestep_rich * np.arange(timesteps_per_Day)

        #  Loop over all days
        for i in range(self.nb_days):

            #  Define, if days is weekday or weekend
            if (i + self.initial_day) % 7 in (0, 6):
                weekend = True
            else:
                weekend = False

            #  Extract array with radiation for each timestep of day
            irrad_day = irradiance[timesteps_per_Day * i: timesteps_per_Day * (i + 1)]

            #  Interpolate radiation values for required timestep of 60 seconds
            irrad_day_minutewise = np.interp(required_timestamp,
                                            given_timestamp, irrad_day)

            # Extract current occupancy profile for current day
            # (10-minutes-timestep assumed)
            current_occupancy = self.activity_profile[144 * i: 144 * (i + 1)]

            day_of_the_year = 0 # only necessary for electric heating
            # Perform lighting and appliance usage simulation for one day
            (el_p_curve, light_p_curve, app_p_curve) = el_wrapper.power_sim(irradiation=irrad_day_minutewise,
                                                                            weekend=weekend,
                                                                            day=i+day_of_the_year,
                                                                            occupancy=current_occupancy)
            # Append results
            demand.append(el_p_curve)
            self.light_load.append(light_p_curve)
            self.app_load.append(app_p_curve)

        # Convert to nd-arrays
        res = np.array(demand)
        self.light_load = np.array(self.light_load)
        self.app_load = np.array(self.app_load)

        # Reshape arrays (nd-array structure to 1d structure)
        res = np.reshape(res, res.size)
        self.light_load = np.reshape(self.light_load, self.light_load.size)
        self.app_load = np.reshape(self.app_load, self.app_load.size)

        # Change time resolution to timestep defined by user
        loadcurve = cr.change_resolution(res, _timestep_rich, self.time_resolution)
        self.light_load = cr.change_resolution(self.light_load, _timestep_rich,
                                          self.time_resolution)
        self.app_load = cr.change_resolution(self.app_load, _timestep_rich,
                                        self.time_resolution)

        #  Normalize el. load profile to annual_demand
        if do_normalization:

            # Convert power to energy values
            energy_curve = loadcurve * self.time_resolution  # in Ws
            energy_lighting = self.light_load * self.time_resolution  # in Ws
            energy_app = self.app_load * self.time_resolution  # in Ws

            # Sum up energy values (plus conversion from Ws to kWh)
            curr_el_dem = sum(energy_curve) / (3600 * 1000)
            curr_lighting_dem = sum(energy_lighting) / (3600 * 1000)
            curr_app_dem = sum(energy_app) / (3600 * 1000)

            # these factor can be used for normalization or just to compare with annual demand
            # for comparison with annual demand-> if factor > 1: current demand for one year would be beneath annual demand
            factor_compare_annual_demand = annual_demand * (self.nb_days / 365) / curr_el_dem
            factor_compare_annual_lighting = 0.1 * annual_demand * (self.nb_days / 365) / curr_lighting_dem
            factor_compare_annual_app = 0.9 * annual_demand * (self.nb_days / 365) / curr_app_dem

            #  Rescale load curves
            self.light_load *= factor_compare_annual_lighting
            self.app_load *= factor_compare_annual_app
            loadcurve = self.light_load + self.app_load

        return loadcurve


    def generate_gain_profile(self, personGain=70.0):
        """
        Generate profile of internal gains

        Parameters
        -------
        personGain : float
            Heat dissipation of one person
            Source: SIA 2024/2015 D - Raumnutzungsdaten für Energie- und Gebäudetechnik
        lightGain : float
            share of waste heat (LED)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), Januar, 32–41.
        appGain :
            share of waste heat (assumed)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), Januar, 32–41.
        occ_profile : float
             stochastic occupancy profiles for a district
        app_load : Array-like
            Electric load profile of appliances in W.
        light_load : Array-like
            Electric load profile of lighting in W.

        Returns
        -------
        gains : array
            Internal gain of each flat

        """
        # To - Do adjust to personal heat gains depending on builiding type 
        personGain = 70.0  # [Watt]
        lightGain = 0.65
        appGain = 0.33

        gains = self.occ_profile * personGain + self.light_load * lightGain + self.app_load * appGain

        return gains


class NonResidentialProfiles():
    """
    Profile class 
    calculating user related profiles for Non-Residential Buildings

    Parameters
    ----------
    number_occupants : integer
        Maxiumum Number of occupants who work in the building.
    initial_day : integer
        Day of the week with which the generation starts
        1-7 for monday-sunday.
    nb_days : integer
        Number of days for which a stochastic profile is generated.
    time_resolution : integer
        resolution of time steps of output array in seconds.

    Attributes
    ----------
    activity_profile : array
        Numpy-arry with acctive occupants 10-minutes-wise.
    occ_profile : array
         stochastic occupancy profiles for a district
    app_load : Array-like
        Electric load profile of appliances in W.
    light_load : Array-like
        Electric load profile of lighting in W.
    """

    def __init__(self, building_type, max_number_occupants, area,
                 initital_day, nb_days, time_resolution):

        """
        Constructor of Profiles Class
        """
        self.building_type = building_type 
        self.max_number_occupants = max_number_occupants
        self.area = area
        self.initial_day = initital_day
        self.nb_days = nb_days
        self.time_resolution = time_resolution

        self.activity_profile = []
        self.occ_profile = []
        self.light_load = []
        self.app_load = []
        self.appliance_demand = None
        self.lightning_demand = None 

        self.generate_activity_profile()
        #self.loadProbabilitiesDhw()

    # check for alternative

    def generate_activity_profile(self):
        """
        Generate a stochastic activity profile
        (on base of ridchardsonpy)

        Parameters
        ----------
        building_type : string
            Type of Non-Residential Building
        number_occupants : integer
            Number of occupants who live in the house or flat.
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.
        nb_days : integer
            Number of days for which a stochastic profile is generated.

        """
        # To-Do: Fix the coccupancy 
        # activity  = NonResidentialProfiles(building_type=self.building_type, 
        #                                   max_number_occupants=self.max_number_occupants,
        #                                   initital_day=self.initial_day,
        #                                   time_resolution=self.time_resolution)
        #activity = occ.Occupancy(self.number_occupants, self.initial_day, self.nb_days)
        #self.activity_profile = activity.occupancy
        # Write a Function, that checks based on the type, and initial day, 
        # generates a profile multiplicates it with the max_number_occupants 
        # and scales it to the time resolution using nump 
        # Data can be gathered from 
        df_schedules, schedule = schedule_reader.get_schedule(self.building_type)

        df_schedules = schedule_reader.adjust_schedule(inital_day=self.initial_day,
                                                                schedule=df_schedules,
                                                                nb_days=self.nb_days)
        self.activity_profile = df_schedules["OCCUPANCY"]
        

        # Generate a set, starting with the initital day, 
        # that has number of days as entries * 24 
        # That should be done in gerate occupancy


    def generate_occupancy_profiles(self):
        """
        Generate stochastic occupancy profiles for a district for calculating internal gains.
        Change time resolution of 10 min profiles to required resolution

        Parameters
        ----------
        time_resolution : integer
            resolution of time steps of output array in seconds.
        activity_profile : array
            Numpy-arry with acctive occupants 10-minutes-wise.

        """
        # To-Do: This needs to turn the activity profile into an occupancy profile
        # 
        tr_min = int(self.time_resolution/60)
        sia_profile_daily_min = np.concatenate((np.ones(60*8),
                                                np.zeros(60*13),
                                                np.ones(60*3)),
                                                axis=None)


        # generate array for minutly profile
        activity_profile_min = np.zeros(len(self.activity_profile)*10)
        # generate array for time adjusted profile
        self.occ_profile = np.zeros(int(len(self.activity_profile)*10/tr_min))

        # append minutly sia profiles until nb_days is reached
        sia_profile = []
        while len(sia_profile) < len(activity_profile_min):
            sia_profile = np.concatenate((sia_profile,sia_profile_daily_min),axis=None)
        sia_profile = sia_profile * max(self.activity_profile)

        # calculate minutely profile
        for t in range(len(activity_profile_min)):
            activity_profile_min[t] = max(self.activity_profile[int(t/10)],sia_profile[t])
        for t in range(len(self.occ_profile)):
            self.occ_profile[t] = np.round(np.mean(activity_profile_min[(t*tr_min):(t*tr_min+tr_min)]))
        return self.occ_profile


    def generate_dhw_profile(self):
        """
        Generates a dhw profile
        Based on the TEK Ansatz and DIBS. 

        Generate a stochastic dhw profile
        (on base of pycity_base)

        Parameters
        ----------
        time_resolution : integer
            resolution of time steps of output array in seconds.
        activity_profile : array
            Numpy-arry with acctive occupants 10-minutes-wise.
        prob_profiles_dhw: array
            probabilities of dhw usage
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.

        Returns
        -------
        dhw_heat : array
            Numpy-array with heat demand of dhw consumption in W.

        """

        # Run simulation
        # run the simulation for just x days
        # therefor occupancy has to have the length of x days
        # TEK for Water and heat? 
        TEK_dhw, TEK_name = schedule_reader.get_tek(self.building_type)  # TEK_dhw in kWh/m2*a
        # To-Do,  Figure whty there is a 1000 in the formula
        # Code taken from DIBS and adjusted for
        # style and attributes to fit districtgenerator
        occupancy_full_usage_hours = self.activity_profile.sum()  # in h/a
        TEK_dhw_per_Occupancy_Full_Usage_Hour = TEK_dhw / occupancy_full_usage_hours  # in kWh/m2*h

        dhw_water = self.occ_profile * TEK_dhw_per_Occupancy_Full_Usage_Hour * 1000 * self.area

        return dhw_water


    def generate_el_profile(self, irradiance, annual_demand, appliance_demand,
                             light_demand, do_normalization = True):
        """
        Generate electric load profile for one household

        Parameters
        -------
        irradiance : array
            if none is given default weather data (TRY 2015 Potsdam) is used
        el_wrapper : object
            This objects holdes information about the lighting and appliance configuration.
        annual_demand : integer
            Annual elictricity demand in kWh.
        do_normalization : boolean
            Normalize el. load profile to annual_demand
        Returns
        -------
        loadcurve : Array-like
            Total electric load profile in W.

        """

        # Make simulation over x days
        demand = []

        #  Check if irradiance timestep is identical with param. timestep
        timesteps_irr = int(self.nb_days * 3600 * 24 / len(irradiance))

        if self.time_resolution != timesteps_irr:  # pragma: no cover
            msg = 'Time discretization of irradiance is different from ' \
                  'timestep ' \
                  + str(self.time_resolution) \
                  + 'seconds . You need to change the resolution, first!'
            raise AssertionError(msg)

        _timestep_rich = 60  # timesteps in seconds

        # number of timesteps per day for given time resolution
        timesteps_per_Day = int(86400 / self.time_resolution)

        # Array holding index of timesteps (60 second timesteps)
        ### Irradiance is needed for every minute of the day
        required_timestamp = np.arange(1440)

        # Array holding each timestep in seconds
        ### the timesteps of the irradiance array in minutes
        given_timestamp = self.time_resolution / _timestep_rich * np.arange(timesteps_per_Day) 
        # To-Do: Get data to be turned into profiles
        # Occupancy based + Lightning + common electricity
        # 
        # Convert to nd-arrays
        res = np.array(demand)
        self.light_load = np.array(self.light_load)
        self.app_load = np.array(self.app_load)

        # Reshape arrays (nd-array structure to 1d structure)
        res = np.reshape(res, res.size)
        self.light_load = np.reshape(self.light_load, self.light_load.size)
        self.app_load = np.reshape(self.app_load, self.app_load.size)
        breakpoint()
        # Change time resolution to timestep defined by user
        loadcurve = cr.change_resolution(res, _timestep_rich, self.time_resolution)
        self.light_load = cr.change_resolution(self.light_load, _timestep_rich,
                                          self.time_resolution)
        self.app_load = cr.change_resolution(self.app_load, _timestep_rich,
                                        self.time_resolution)

        #  Normalize el. load profile to annual_demand
        if do_normalization:

            # Convert power to energy values
            energy_curve = loadcurve * self.time_resolution  # in Ws
            energy_lighting = self.light_load * self.time_resolution  # in Ws
            energy_app = self.app_load * self.time_resolution  # in Ws

            # Sum up energy values (plus conversion from Ws to kWh)
            curr_el_dem = sum(energy_curve) / (3600 * 1000)
            curr_lighting_dem = sum(energy_lighting) / (3600 * 1000)
            curr_app_dem = sum(energy_app) / (3600 * 1000)

            # these factor can be used for normalization or just to compare with annual demand
            # for comparison with annual demand-> if factor > 1: current demand for one year would be beneath annual demand
            factor_compare_annual_demand = annual_demand * (self.nb_days / 365) / curr_el_dem
            factor_compare_annual_lighting = 0.1 * annual_demand * (self.nb_days / 365) / curr_lighting_dem
            factor_compare_annual_app = 0.9 * annual_demand * (self.nb_days / 365) / curr_app_dem

            #  Rescale load curves
            self.light_load *= factor_compare_annual_lighting
            self.app_load *= factor_compare_annual_app
            loadcurve = self.light_load + self.app_load

        return loadcurve


    def generate_gain_profile(self):
        """
        Generate profile of internal gains

        Parameters
        -------
        personGain : float
            Heat dissipation of one person
            Source: SIA 2024/2015 D - Raumnutzungsdaten für Energie- und Gebäudetechnik
        lightGain : float
            share of waste heat (LED)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), Januar, 32–41.
        appGain :
            share of waste heat (assumed)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), Januar, 32–41.
        occ_profile : float
             stochastic occupancy profiles for a district
        app_load : Array-like
            Electric load profile of appliances in W.
        light_load : Array-like
            Electric load profile of lighting in W.

        Returns
        -------
        gains : array
            Internal gain of each flat

        """
        # To-Do: get Data from 19599 or CEA

        personGain = 70.0  # [Watt]
        lightGain = 0.65
        appGain = 0.33

        gains = self.occ_profile * personGain + self.light_load * lightGain + self.app_load * appGain

        return gains
