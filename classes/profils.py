# -*- coding: utf-8 -*-

import os
import random as rd
import json
import math
import numpy as np
import pylightxl as xl
import richardsonpy.classes.occupancy as occ_residential
import richardsonpy.functions.change_resolution as cr
import OpenDHW
import districtgenerator.functions.change_resolution as chres
import districtgenerator.functions.SIA as SIA


class Profiles:
    """
    Profile class.
    Calculating user related profiles of a building or flat.

    Parameters
    ----------
    number_occupants : integer
        Number of occupants who live in the house or flat.
    number_occupants_building : integer
        Number of occupants who live in the building.
    initial_day : integer
        Day of the week with which the generation starts.
        1-7 for monday-sunday.
    nb_days : integer
        Number of days for which a stochastic profile is generated.
    time_resolution : integer
        resolution of time steps of output array in seconds.

    Attributes
    ----------
    activity_profile : array-like
        Numpy-array with active occupants 10-minutes-wise.
    occ_profile : array-like
        Stochastic occupancy profile.
    app_load : array-like
        Electric load profile of appliances in W.
    light_load : array-like
        Electric load profile of lighting in W.
    """

    def __init__(self, number_occupants,number_occupants_building, initial_day, nb_days, time_resolution, building):
        """
        Constructor of Profiles class.

        Returns
        -------
        None.
        """

        self.number_occupants = number_occupants
        self.number_occupants_building = number_occupants_building
        self.initial_day = initial_day
        self.nb_days = nb_days
        self.time_resolution = time_resolution

        # Initialize SIA class and read data
        self.SIA2024 = SIA.read_SIA_data()
        self.building = building
        if self.building in {"OB", "School", "Grocery_store"}:     #Non-residential buildings are divided in different zones on the basis of SIA data
            self.building_zones = self.SIA2024[self.building]

        self.activity_profile = []
        self.occ_profile = []
        self.occ_profile_building = []
        self.building_profiles = {}
        self.temperature_difference = []
        self.light_load = []
        self.app_load = []


        self.generate_activity_profile_residential()
        self.loadProbabilitiesDhw()  # wurde nicht genutzt

    def generate_activity_profile_residential(self):
        """
        Generate a stochastic activity profile
        (on base of ridchardsonpy).

        Parameters
        ----------
        number_occupants : integer
            Number of occupants who live in the house or flat.
        initial_day : integer
            Day of the week with which the generation starts
            1-7 for monday-sunday.
        nb_days : integer
            Number of days for which a stochastic profile is generated.

        Returns
        -------
        None.
        """
        if self.building in {"SFH", "TH", "MFH", "AB"}:
            activity = occ_residential.Occupancy(self.number_occupants, self.initial_day, self.nb_days)
            self.activity_profile = activity.occupancy

    def generate_occupancy_profiles_residential(self):
        """
        Generate stochastic occupancy profiles for a district for calculating internal gains.
        Change time resolution of 10 min profiles to required resolution.

        Parameters
        ----------
        time_resolution : integer
            Resolution of time steps of output array in seconds.
        activity_profile : array-like
            Numpy-arry with active occupants 10-minutes-wise.

        Returns
        -------
        self.occ_profile : array-like
            Number of present occupants.
        """
        #RH: Warum kombinieren wir SIA-Profile und die Richardson-Profile?
        tr_min = int(self.time_resolution/60)
        sia_profile_daily_min = np.concatenate((np.ones(60*8),
                                                np.zeros(60*13),
                                                np.ones(60*3)),
                                                axis=None)           # Warum gehen wir davon aus, dass es nur Nullen und Einsen gibt? In der Quelle ist das nicht so

        # generate array for minutely profile
        activity_profile_min = np.zeros(len(self.activity_profile) * 10)
        # generate array for time adjusted profile
        self.occ_profile = np.zeros(int(len(self.activity_profile) * 10 / tr_min))

        # append minutely sia profiles until nb_days is reached
        sia_profile = []
        while len(sia_profile) < len(activity_profile_min):
            sia_profile = np.concatenate((sia_profile, sia_profile_daily_min), axis=None)
        sia_profile = sia_profile * max(self.activity_profile)

        # calculate minutely profile
        for t in range(len(activity_profile_min)):
            activity_profile_min[t] = max(self.activity_profile[int(t/10)], sia_profile[t])
        for t in range(len(self.occ_profile)):
            self.occ_profile[t] = np.round(np.mean(activity_profile_min[(t * tr_min):(t * tr_min + tr_min)]))

        return self.occ_profile

    def generate_profiles_non_residential(self,holidays):
        """
         Generate stochastic peaople profiles, devices profiles and month profiles
         for every zone of the non-residential building

         """

        zone_profiles = {}
        total_hours = 365 * 24

        for number, data in self.SIA2024.items():
            zone_name = data.get('Zone_name_GER')
            if not zone_name:
                continue

            sia_week_profile_people_zone = []
            sia_week_profile_devices_zone = []

            for i in range(7):
                if self.building == "Grocery_store":
                    is_not_working_day = (i + self.initial_day) % 7 in [6]
                else:
                    is_not_working_day = (i + self.initial_day) % 7 in [0, 6]

                sia_day_profile_people_zone = [0] * 24 if is_not_working_day else data['profile_people']
                sia_day_profile_devices_zone = [min(data['profile_devices'])] * 24 if is_not_working_day else data['profile_devices']
                sia_week_profile_people_zone.extend(sia_day_profile_people_zone)
                sia_week_profile_devices_zone.extend(sia_day_profile_devices_zone)

            repetitions = total_hours // len(sia_week_profile_people_zone)
            remaining_hours = total_hours % len(sia_week_profile_people_zone)

            # Repeat the weekly pattern to cover the entire year
            sia_profile_people_zone = sia_week_profile_people_zone * repetitions + sia_week_profile_people_zone[:remaining_hours]
            sia_profile_devices_zone = sia_week_profile_devices_zone * repetitions + sia_week_profile_devices_zone[:remaining_hours]

            # Consider holidays
            for day in range(self.nb_days):
                if (day + self.initial_day) in holidays:
                    sia_profile_people_zone[24 * day: 24 * (day + 1)] = [0] * 24
                    sia_profile_devices_zone[24 * day: 24 * (day + 1)] = [min(data['profile_devices'])] * 24

            # Apply random variation to the people and devices profiles
            profile_people_zone = [min(max(np.random.normal(value, value * 0.1), 0), 1) for value in sia_profile_people_zone]
            profile_devices_zone = [min(max(np.random.normal(value, value * 0.1), 0), 1) for value in sia_profile_devices_zone]

            # Apply random variation to the monthly profile
            profile_month_zone = [min(max(np.random.normal(value, value * 0.07), 0), 1) for value in data['profile_month']]

            # Adjust the people profile to 0 for the months there is no occupation of the corresponding building
            days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            profile_people_zone_real = []
            hour_index = 0
            for month in range(12):
                factor = profile_month_zone[month]
                hours_in_month = days_in_month[month] * 24
                if factor == 0:
                    for hour in range(hours_in_month):
                        # Multiply the original occupant profile by the factor and store in the new profile
                        profile_people_zone_real.append(profile_people_zone[hour_index] * factor)
                        hour_index += 1  # Move to the next hour
                else:
                    for hour in range(hours_in_month):
                        profile_people_zone_real.append(profile_people_zone[hour_index])
                        hour_index += 1  # Move to the next hour

            # Change resolution
            profile_people_zone_real = chres.changeResolution(profile_people_zone_real, 3600, self.time_resolution, "mean")
            profile_devices_zone = chres.changeResolution(profile_devices_zone, 3600, self.time_resolution, "mean")



            zone_profiles[zone_name] = {'profile_people_zone': profile_people_zone_real,
                                        'profile_devices_zone': profile_devices_zone,
                                        'profile_month_zone': profile_month_zone}

            self.building_profiles[self.building] = zone_profiles
        if self.building == "OB":
            self.occ_profile = np.array([math.ceil(a * self.number_occupants) for a in                          # self.number_occupants is the mean number of occupants in a main room
                                self.building_profiles['OB']['Einzel-, Gruppenbüro']['profile_people_zone']])   # self.occ_profile is the occupancy profile in an office room of the many existing in the building
            occ_profile_building_main_part = np.array([math.ceil(a * self.number_occupants_building) for a in
                                         self.building_profiles['OB']['Einzel-, Gruppenbüro']['profile_people_zone']])

        elif self.building == "School":
            self.occ_profile = np.array([math.ceil(a * self.number_occupants) for a in                     # self.number_occupants is the mean number of occupants in a main room
                                self.building_profiles['School']["Schulzimmer"]['profile_people_zone']])   # self.occ_profile is the occupancy profile in a classroom of the many existing in the building
            occ_profile_building_main_part = np.array([math.ceil(a * self.number_occupants_building) for a in
                                         self.building_profiles['School']["Schulzimmer"]['profile_people_zone']])

        elif self.building == "Grocery_store":
            self.occ_profile = np.array([math.ceil(a * self.number_occupants) for a in                                    # self.number_occupants is the mean number of occupants in a main room
                                self.building_profiles['Grocery_store']["Lebensmittelverkauf"]['profile_people_zone']])
            occ_profile_building_main_part = np.array([math.ceil(a * self.number_occupants_building) for a in
                                         self.building_profiles['Grocery_store']["Lebensmittelverkauf"]['profile_people_zone']])

        self.occ_profile_building = occ_profile_building_main_part
        max_value = max(occ_profile_building_main_part)
        timesteps_per_Day = int(86400 / self.time_resolution)
        # Assume that from 10:00 to 15:00, the occupancy in  the building is equal to the maximum number of occupants
        # in occ_profile_building_main_part, since occ_profile_building_main_part only considers people in main rooms.
        # If the occupants are not in the main room,they may be in the toilet or kitchen, i.e. they are still in the building.

        for day in range(self.nb_days):
            start_index = int(day * timesteps_per_Day + 10 * timesteps_per_Day / 24)  # 10 AM
            end_index = int(day * timesteps_per_Day + 15 * timesteps_per_Day / 24)  # 3 PM
            for i in range(start_index, end_index):
                if self.occ_profile_building[i] != 0:
                    self.occ_profile_building[i] = max_value

        return self.occ_profile, self.occ_profile_building, self.building_profiles

    def loadProbabilitiesDhw(self):   # wurde nicht genutzt
        """
        Load probabilities of dhw usage.

        Returns
        -------
        None.
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

    def generate_dhw_profile(self, building, holidays):
        """
        Generate a stochastic dhw profile
        (on base of DHWclac).
        https://www.uni-kassel.de/maschinenbau/institute/thermische-energietechnik/fachgebiete/solar-und-anlagentechnik/downloads
        https://github.com/RWTH-EBC/OpenDHW

        Parameters
        ----------
        s_step : integer
            Resolution of time steps of output array in seconds.
        Categories: 1 or 4
            Either one or four categories with different mean volume rates, tapping times and frequencies can be defined.
        occupancy: integer
            Maximum number of occupants in this building.
        mean_drawoff_vol_per_day : array-like
            Total mean daily draw-off volume per person per day in liter.
        temp_dT : array-like
        The temperature difference (ΔT) between the cold water and the water at the tapping point (mixed water).

        Returns
        -------
        dhw_heat : array-like
            Numpy-array with heat demand of dhw consumption in W.
        """

        temperatur_mixed_water = []
        temperatur_cold_water = []
        for day in range(365):
            temperatur_mixed_water.append(45 + (3 * np.cos(math.pi * (2 / 365 * (day) - 2 * 355 / 365))))
            #This formula introduces a seasonal fluctuation to take account of the fluctuations in the desired water temperature throughout the year.
            #The amplitude is ±3°C, reflecting higher hot water temperature requirements during colder months (winter) and lower during warmer months (summer).

            temperatur_cold_water.append(10 + (5 * np.cos(math.pi * (2 / 365 * (day) - 2 * 172 / 365))))
            #This formula introduces a seasonal fluctuation to take account of the fluctuations in the cold water temperature throughout the year.
            #The amplitude is ±5°C, reflecting lower cold water temperatures during colder months (winter) and higher during warmer months (summer).

        temperature_difference_day = [T_out - T_in for T_out, T_in in zip(temperatur_mixed_water, temperatur_cold_water)]

        temperature_difference = [T for T in temperature_difference_day for _ in range(24)]
        self.temperature_difference = chres.changeResolution(temperature_difference, 3600, self.time_resolution, "mean")

        dhw_profile = OpenDHW.generate_dhw_profile(
            s_step=60,
            categories=1,
            occupancy=self.number_occupants if self.building in {"SFH", "TH", "MFH", "AB"} else self.number_occupants_building,
            building_type=self.building,
            weekend_weekday_factor=1.2 if self.building in {"SFH", "TH", "MFH", "AB"} else 1,
            holidays = holidays,
            mean_drawoff_vol_per_day=building["buildingFeatures"]["mean_drawoff_dhw"]
        )

        dhw_timeseries = OpenDHW.resample_water_series(dhw_profile, self.time_resolution)
        dhw_heat = OpenDHW.compute_heat(timeseries_df=dhw_timeseries, temp_dT=self.temperature_difference)

        return dhw_heat["Heat_W"].values

    def generate_el_profile_residential(self, holidays, irradiance, el_wrapper, annual_demand, do_normalization=True):
        """
        Generate electric load profile for one household

        Parameters
        -------
        irradiance : array-like
            If none is given default weather data (TRY 2015 Potsdam) is used.
        el_wrapper : object
            This objects holds information about the lighting and appliance configuration.
        annual_demand : integer
            Annual electricity demand in kWh.
        do_normalization : boolean, optional
            Normalize el. load profile to annual_demand. The default is True.

        Returns
        -------
        loadcurve : array-like
            Total electric load profile in W.
        """

        # Make simulation over x days
        demand = []

        #  Check if irradiance timestep is identical with param. timestep
        timesteps_irr = int(self.nb_days * 3600 * 24 / len(irradiance))

        if self.time_resolution != timesteps_irr:  # pragma: no cover
            msg = 'Time discretization of irradiance is different from timestep ' \
                  + str(self.time_resolution) \
                  + 'seconds . You need to change the resolution, first!'
            raise AssertionError(msg)

        _timestep_rich = 60  # timesteps in seconds

        # number of timesteps per day for given time resolution
        timesteps_per_Day = int(86400 / self.time_resolution)

        # Array holding index of timesteps (60 second timesteps)
        # Irradiance is needed for every minute of the day
        required_timestamp = np.arange(1440)

        # Array holding each timestep in seconds
        # the timesteps of the irradiance array in minutes
        given_timestamp = self.time_resolution / _timestep_rich * np.arange(timesteps_per_Day)

        #  Loop over all days
        for i in range(self.nb_days):

            # Define if the day is a working day or not
            if (i + self.initial_day) % 7 in (0, 6) or (i + self.initial_day) in holidays:
                not_working_day = True
            else:
                not_working_day = False

            #  Extract array with radiation for each timestep of day
            irrad_day = irradiance[timesteps_per_Day * i: timesteps_per_Day * (i + 1)]

            #  Interpolate radiation values for required timestep of 60 seconds
            irrad_day_minutewise = np.interp(required_timestamp, given_timestamp, irrad_day)

            # Extract current occupancy profile for current day
            # (10-minutes-timestep assumed)
            current_occupancy = self.activity_profile[144 * i: 144 * (i + 1)]

            day_of_the_year = 0 # only necessary for electric heating
            # Perform lighting and appliance usage simulation for one day
            (el_p_curve, light_p_curve, app_p_curve) = el_wrapper.power_sim(irradiation=irrad_day_minutewise,
                                                                            weekend=not_working_day,
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
        self.light_load = cr.change_resolution(self.light_load, _timestep_rich, self.time_resolution)
        self.app_load = cr.change_resolution(self.app_load, _timestep_rich, self.time_resolution)

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
            # for comparison with annual demand:
            # -> if factor > 1: current demand for one year would be beneath annual demand
            factor_compare_annual_demand = annual_demand * (self.nb_days / 365) / curr_el_dem
            factor_compare_annual_lighting = 0.1 * annual_demand * (self.nb_days / 365) / curr_lighting_dem
            factor_compare_annual_app = 0.9 * annual_demand * (self.nb_days / 365) / curr_app_dem

            #  Rescale load curves
            self.light_load *= factor_compare_annual_lighting
            self.app_load *= factor_compare_annual_app
            loadcurve = self.light_load + self.app_load

        return loadcurve

    def generate_el_profile_non_residential(self, irradiance, el_wrapper,annual_demand_app):
        """
        Generate electric load profile for one household

        Parameters
        -------
        irradiance : array-like
            If none is given default weather data (TRY 2015 Potsdam) is used.
        el_wrapper : object
            This objects holds information about the lighting configuration.

        Returns
        -------
        light_p_curve : array-like
            Electric load profile for lighting in W.
        """

        #  Check if irradiance timestep is identical with param. timestep
        timesteps_irr = int(self.nb_days * 3600 * 24 / len(irradiance))

        if self.time_resolution != timesteps_irr:  # pragma: no cover
            msg = 'Time discretization of irradiance is different from timestep ' \
                  + str(self.time_resolution) \
                  + 'seconds . You need to change the resolution, first!'
            raise AssertionError(msg)

        _timestep_rich = 60  # timesteps in seconds

        # number of timesteps per day for given time resolution
        timesteps_per_Day = int(86400 / self.time_resolution)

        # Array holding index of timesteps (60 second timesteps)
        # Irradiance is needed for every minute of the day
        required_timestamp = np.arange(1440)

        # Array holding each timestep in seconds
        # the timesteps of the irradiance array in minutes
        given_timestamp = self.time_resolution / _timestep_rich * np.arange(timesteps_per_Day)

        #  Loop over all days
        for i in range(self.nb_days):

            #  Extract array with radiation for each timestep of day
            irrad_day = irradiance[timesteps_per_Day * i: timesteps_per_Day * (i + 1)]

            #  Interpolate radiation values for required timestep of 60 seconds
            irrad_day_minutewise = np.interp(required_timestamp, given_timestamp, irrad_day)

            # Extract current occupancy profile for current day
            # We assume occupancy for a single main room, as each main room operates independently.
            # Considering the entire building's occupancy could result in unrealistic big numbers of occupants,
            # which wouldn't accurately represent the effective occupancy in the independent main room.
            # The number of occupants in a specific main room is important because they share control of the same lighting,
            # unlike occupants in other main rooms who do not influence the lighting in this part of the buildings
            # where the assumed main room lies.
            occ_profile = self.occ_profile[timesteps_per_Day * i: timesteps_per_Day * (i + 1)]

            max_value = max(occ_profile)

            occ_profile_building_part = occ_profile

            # Assume that from 10:00 to 15:00, the occupancy in the assumed part of the building is equal to the maximum number of occupants
            # in occ_profile, since occ_profile only considers people in main rooms. If people are not in the main room,
            # they may be in the toilet or kitchen, i.e. they are still in this part of the building.
            occ_profile_building_part[int(10*timesteps_per_Day/24) : int(15*timesteps_per_Day/24)] = [max_value] * int(5*timesteps_per_Day/24)

            # Extract current occupancy profile for current day
            # (10-minutes-timestep assumed)
            current_occupancy = np.round(np.interp(np.arange(144), given_timestamp/10, occ_profile_building_part)).astype(int)

            day_of_the_year = 0 # only necessary for electric heating
            # Perform lighting usage simulation for one day
            light_p_curve = el_wrapper.power_sim_lighting(irradiation=irrad_day_minutewise, occupancy=current_occupancy)

            # Append results
            self.light_load.append(light_p_curve)

        # Perform appliance usage simulation for one year
        app_p_curve = el_wrapper.power_sim_app(annual_demand_app=annual_demand_app,building_profiles=self.building_profiles, time_resolution=self.time_resolution)
        self.app_load.append(app_p_curve)

        # Convert to nd-arrays
        self.light_load = np.array(self.light_load)
        self.app_load = np.array(self.app_load)

        # Reshape arrays (nd-array structure to 1d structure)
        self.light_load = np.reshape(self.light_load, self.light_load.size)
        self.app_load = np.reshape(self.app_load, self.app_load.size)

        # Change time resolution to timestep defined by user
        self.light_load = cr.change_resolution(self.light_load, _timestep_rich, self.time_resolution)

        loadcurve = self.light_load + self.app_load

        return loadcurve

    def generate_gain_profile_residential(self):
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
            62 (2014), January, 32–41.
        appGain :
            share of waste heat (assumed)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), January, 32–41.
        occ_profile : float
             stochastic occupancy profiles for a district.
        app_load : array-like
            Electric load profile of appliances in W.
        light_load : array-like
            Electric load profile of lighting in W.

        Returns
        -------
        gains : array-like
            Internal gain of each flat.
        """

        personGain = 70.0  # [Watt]
        lightGain = 0.65
        appGain = 0.33

        gains = self.occ_profile * personGain + self.light_load * lightGain + self.app_load * appGain

        return gains

    def generate_gain_profile_non_residential(self):
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
            62 (2014), January, 32–41.
        appGain :
            share of waste heat (assumed)
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), January, 32–41.
        occ_profile : float
             stochastic occupancy profiles for a district.
        app_load : array-like
            Electric load profile of appliances in W.
        light_load : array-like
            Electric load profile of lighting in W.

        Returns
        -------
        gains : array-like
            Internal gain of each flat.
        """
        personGain = 70.0  # [Watt]
        lightGain = 0.65
        appGain = 0.33

        gains_persons = self.occ_profile_building * personGain
        gains_others = self.light_load * lightGain + self.app_load * appGain

        return gains_persons, gains_others

    def generate_EV_profile(self, occ):
        """
        Generate profile for an electric vehicle (EV)

        Returns
        -------
        car_demand_total : list
            Electricity demand of the EV in [Wh].
        """

        # determine how long one day is (in number of steps)
        array = int(len(occ) / self.nb_days)
        # initialize empty list for all days
        car_demand_total = []
        # loop over all days
        for day in range(self.nb_days):
            # slice occupancy profile for current day
            occ_day = occ[day * array:(day + 1) * array]
            # initialize electricity demand of EV for current day
            car_demand_day = np.zeros(len(occ_day))

            # Check if there is no occupancy for the entire day
            if np.all(occ_day == 0.0):
                # If the entire day's occupancy profile is zero, set demand to 0 for the day
                car_demand_total[day * array:(day + 1) * array] = car_demand_day
                continue  # Skip to the next day

            # identify time steps where nobody is home
            nobody_home = np.where(occ_day == 0.0)
            try:
                # assumption: car returns shortly after the last time step when nobody is home
                car_almost_arrives = nobody_home[0][-1]
            except:
                # if all day at least one occupant is at home, assume that EV returns circa at 18:00 pm
                car_almost_arrives = array - int(array / 4)
            # calculate electricity demand of current day [Wh]
            demand = max(0, rd.gauss(5000, 0.5 * 5000))
            # demand for the energy system at home just relevant with return of EV
            # assumption: just last return of the day is relevant, because EV is not connected at home between
            # first leave and last return of the day
            car_demand_day[car_almost_arrives] = demand
            # add current day to demand for all days
            car_demand_total[day * array:(day + 1) * array] = car_demand_day

        return car_demand_total
