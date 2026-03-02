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
        0-6 for monday-sunday.
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

    def __init__(self, number_occupants, number_occupants_building, initial_day, nb_days, time_resolution, building,SIA2024=None):
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
        self.SIA2024 = SIA2024
        self.building = building
        if self.building in {"OB", "SC", "GS", "RE"}:     #Non-residential buildings are divided in different zones on the basis of SIA data
            self.building_zones = self.SIA2024[self.building]

        self.activity_profile = []
        self.occ_profile = []
        self.occ_profile_building = []
        self.building_profiles = {}
        self.temperature_difference = []
        self.light_load = []
        self.app_load = []

        self.generate_activity_profile_residential()

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
            0-6 for monday-sunday.
        nb_days : integer
            Number of days for which a stochastic profile is generated.

        Returns
        -------
        None.
        """

        if self.building in {"SFH", "TH", "MFH", "AB"}:
            activity = occ_residential.Occupancy(self.number_occupants, self.initial_day, self.nb_days)
            self.activity_profile = activity.occupancy

    def load_occupancy_profiles_residential(self, prof):
        self.occ_profile = prof

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

        tr_min = int(self.time_resolution/60)
        sia_profile_daily_min = np.concatenate((np.ones(60*8),
                                                np.zeros(60*13),
                                                np.ones(60*3)),
                                                axis=None)

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

    def loadProbabilitiesDhw(self):
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
                if self.building in ["GS"]:
                    is_not_working_day = (i + self.initial_day) % 7 in [6]
                elif self.building in ["SC", "OB"]:
                    is_not_working_day = (i + self.initial_day) % 7 in [5, 6]
                elif self.building == "RE":
                    is_not_working_day = False  # RE is always working

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
                if (day+1 in holidays and self.building in ["SC", "OB", "GS"]):
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

        elif self.building == "SC":
            self.occ_profile = np.array([math.ceil(a * self.number_occupants) for a in                     # self.number_occupants is the mean number of occupants in a main room
                                self.building_profiles['SC']["Schulzimmer"]['profile_people_zone']])   # self.occ_profile is the occupancy profile in a classroom of the many existing in the building
            occ_profile_building_main_part = np.array([math.ceil(a * self.number_occupants_building) for a in
                                         self.building_profiles['SC']["Schulzimmer"]['profile_people_zone']])

        elif self.building == "GS":
            self.occ_profile = np.array([math.ceil(a * self.number_occupants) for a in                                    # self.number_occupants is the mean number of occupants in a main room
                                self.building_profiles['GS']["Lebensmittelverkauf"]['profile_people_zone']])
            occ_profile_building_main_part = np.array([math.ceil(a * self.number_occupants_building) for a in
                                         self.building_profiles['GS']["Lebensmittelverkauf"]['profile_people_zone']])

        elif self.building == "RE":
            self.occ_profile = np.array([math.ceil(a * self.number_occupants) for a in                                    # self.number_occupants is the mean number of occupants in a main room
                                self.building_profiles['RE']["Restaurant"]['profile_people_zone']])
            occ_profile_building_main_part = np.array([math.ceil(a * self.number_occupants_building) for a in
                                         self.building_profiles['RE']["Restaurant"]['profile_people_zone']])

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
            # This formula introduces a seasonal fluctuation to take account of the fluctuations in the desired water temperature throughout the year.
            # The amplitude is ±3°C, reflecting higher hot water temperature requirements during colder months (winter) and lower during warmer months (summer).

            temperatur_cold_water.append(10 + (7 * np.cos(math.pi * (2 / 365 * (day) - 2 * 225 / 365))))
            # This formula introduces a seasonal fluctuation to take account of the fluctuations in the cold water temperature throughout the year.
            # The water temperature is assumed to be equal to the ground temperature at a depth of 1.5 m.
            # Source: M. Böhme, F. Böttcher. Bodentemperaturen im Klimawandel: Auswertungen der Messreihe der Säkularstation Potsdam
            #         https://www.dwd.de/DE/leistungen/klimastatusbericht/publikationen/ksb2011_pdf/ksb2011_art2.pdf?__blob=publicationFile&v=1

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
            mean_drawoff_vol_per_day=building["buildingFeatures"]["mean_drawoff_dhw"],
            initial_day = self.initial_day
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
            if (i + self.initial_day) % 7 in (5, 6) or i + 1 in holidays:
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

        _timestep_rich = 600  # timesteps in seconds

        # number of timesteps per day for given time resolution
        timesteps_per_Day = int(86400 / self.time_resolution)

        # Array holding index of timesteps (600 second timesteps)
        # Irradiance is needed for every 10 minutes of the day
        required_timestamp = np.arange(144)

        # Array holding each timestep in seconds
        # the timesteps of the irradiance array in 10minutes
        given_timestamp = self.time_resolution / _timestep_rich * np.arange(timesteps_per_Day)

        #  Loop over all days
        for i in range(self.nb_days):

            #  Extract array with radiation for each timestep of day
            irrad_day = irradiance[timesteps_per_Day * i: timesteps_per_Day * (i + 1)]

            #  Interpolate radiation values for required timestep of 600 seconds
            irrad_day_10minutewise = np.interp(required_timestamp, given_timestamp, irrad_day)

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
            current_occupancy = np.round(np.interp(np.arange(144), given_timestamp, occ_profile_building_part)).astype(int)

            # Perform lighting usage simulation for one day
            light_p_curve = el_wrapper.power_sim_lighting(irradiation=irrad_day_10minutewise, occupancy=current_occupancy)

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
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), January, 32–41.
        lightGain : float
            share of waste heat
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), January, 32–41.
        appGain :
            share of waste heat
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), January, 32–41.
            Note: Appliances have an 80% internal gain factor (Elsland et al.). However, dishwashers
            and washing machines only have a factor of around 25% (Elsland et al.), since a large part
            of the energy is lost as hot water drainage. According to BDEW
            (https://www.bdew.de/presse/pressemappen/faq-energieeffizienz/), these two categories
            account for approximately 25% of the electricity consumption (excluding lighting and
            electricity for hot water). Hence, the weighted average internal gain factor for appliances is:
                appGain = 0.75 * 0.80 + 0.25 * 0.25 = 0.66
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
        lightGain = 0.80
        appGain = 0.66

        gains = self.occ_profile * personGain + self.light_load * lightGain + self.app_load * appGain

        return gains

    def generate_gain_profile_non_residential(self):
        """
        Generate profile of internal gains

        Parameters
        -------
        personGain : float
            Heat dissipation of one person
            Source: Elsland, Rainer ; Peksen, Ilhan ; Wietschel, Martin: Are Internal Heat
            Gains Underestimated in Thermal Performance Evaluation of Buildings? In: Energy Procedia
            62 (2014), January, 32–41.
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
        lightGain = 0.80
        if self.building == "GS":
            appGain = 0.25
        else:
            appGain = 0.80

        gains_persons = self.occ_profile_building * personGain
        gains_others = self.light_load * lightGain + self.app_load * appGain

        return gains_persons, gains_others

    def generate_car_profile(self, building, building_devices_data, holidays, srcPath, start_index_car=0):
        """
            Generate daily EV charging demand and ICE fuel consumption profiles (distinguishing between workdays and non-workdays).

            Returns
            -------
            all_EV_cars_demand_total : np.array
                Total EV electricity demand curve (in Wh).
            on_demand_all_EV_cars_charging : np.array
                Total EV charging power profile (in W).
            ev_capacity : list
                EV battery capacities (Wh).
            ice_fuel_profile : np.array
                Fuel consumption of gasoline cars (in liters per timestep).
        """

        if self.building in {"SFH", "TH", "MFH", "AB"}:
            occ_profile = self.occ_profile
        elif self.building in {"OB"}:
            occ_profile = self.occ_profile_building

        steps_per_day = int(len(occ_profile) / self.nb_days)
        total_steps = int(len(occ_profile))
        dt = self.time_resolution / (60 * 60) # time step in hours

        # Initialize totals
        all_EV_cars_demand_total = np.zeros(total_steps)
        on_demand_all_EV_cars_charging = np.zeros(total_steps)
        ice_fuel_profile = np.zeros(total_steps)

        # Determine the charging type for the building
        charging_type = building["buildingFeatures"]["ev_charging"]

        # Profiles consumption_profiles for each car
        individual_car_profiles = []

        # Define the possible total driving distances per day (in km)
        # https://bmdv.bund.de/SharedDocs/DE/Anlage/G/mid-2017-tabellenband.pdf?__blob=publicationFile
        # Table A A10.2
        distance_intervals = [(0, 5), (5, 10), (10, 20), (20, 30), (30, 50), (50, 100), (100, 200)] # 0-5 km; Assumption: No use beyond 200 km

        # Define the corresponding probabilities for each distance
        weekday_distance_probs = np.array([0.08, 0.11, 0.19, 0.14, 0.20, 0.19, 0.06])
        not_working_day_probs = np.array([0.13, 0.12, 0.19, 0.11, 0.15, 0.16, 0.10])
        weekday_distance_probs /= weekday_distance_probs.sum()
        not_working_day_probs /= not_working_day_probs.sum()

        # Define the possible one-way driving distances to work per day (in km) (not including the return trip)
        # https://www.destatis.de/DE/Themen/Arbeit/Arbeitsmarkt/Erwerbstaetigkeit/Tabellen/pendler1.html
        distance_work = [(0, 5), (5, 10), (10, 25), (25, 50)]       # 0-5 km
        distance_work_probs = np.array([26.6, 21.8, 29.1, 14.1])
        distance_work_probs /= distance_work_probs.sum()

        # Define Car Segment
        # https://ev-database.org/cheatsheet/range-electric-car
        srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(srcPath, 'data', 'car_segment.json')) as json_file:
            segments = json.load(json_file)
        segment_names = list(segments.keys())
        # Source of the proportions: https://www.kba.de/DE/Statistik/Fahrzeuge/Bestand/Segmente/segmente_node.html
        segment_names_probs = [segments[name]["proportion"] for name in segment_names]

        # Normalize proportions (ensure sum equals 1)
        total_prob = sum(segment_names_probs)
        normalized_probs = [p / total_prob for p in segment_names_probs]

        # generate number of cars for every flat
        def generate_nb_ev(number_of_occupancy):

            ev_ratio = building["buildingFeatures"]["EV"]  # the ratio between EV and total cars
            if self.building in {"SFH", "TH", "MFH", "AB"}:
                # Car distribution probabilities (excluding the case of 0 cars)
                # https://bmdv.bund.de/SharedDocs/DE/Anlage/G/mid-2017-tabellenband.pdf?__blob=publicationFile
                # Table A H8
                car_distribution = {
                    1: [0.57, 0.02, 0.00],  # 1-person household
                    2: [0.61, 0.27, 0.01],  # 2-person household
                    3: [0.40, 0.41, 0.10],  # 3-person household
                    4: [0.35, 0.48, 0.11],  # 4-person household
                    5: [0.36, 0.41, 0.15]  # 5+ person household
                }

                household_size = min(number_of_occupancy, 5)  # 5+ household treated as 5

                # Normalize the distribution to ensure the sum equals 1
                probabilities = np.array(car_distribution[household_size])
                probabilities /= probabilities.sum()

                # Define car count categories (1, 2, or 3 cars)
                car_interval = np.arange(1, 4)

                # Perform random sampling based on probabilities(ICE-cars and EV)
                total_car = np.random.choice(car_interval, p=probabilities)

                # Number of EV: based on ratio between EV and all cars in input
                nb_ev = sum(1 for car in range(total_car) if np.random.rand() < ev_ratio)

            elif self.building in {"OB"}:
                # https://www.destatis.de/DE/Themen/Arbeit/Arbeitsmarkt/Erwerbstaetigkeit/Tabellen/pendler1.html
                total_car = int(np.round(number_of_occupancy * 0.68))        # 68% of people commute to work by car.

                nb_ev = int(np.round(ev_ratio * number_of_occupancy * 0.68)) # 68% of people commute to work by car.

            return nb_ev, total_car

        number_of_ev, total_cars = generate_nb_ev(max(occ_profile))
        number_of_ice = total_cars - number_of_ev
        denom = max(total_cars, 1) # avoid zero division if somehow total_cars==0

        def _generate_ev_charging_profile_from_consumption(ev_demand, availability_profile, battery_capacity, building_devices_data, total_steps, dt):
            ev_charging_profile = np.zeros(total_steps)
            target_soc = battery_capacity * 0.95 # Wh
            current_soc = target_soc # Wh
            eta_standby = building_devices_data["EV"]["eta_standby"]
            max_charging_power = battery_capacity * building_devices_data["EV"]["coeff_ch"]
            max_energy_per_step = max_charging_power * building_devices_data["EV"]["eta_ch"] * dt

            for t in range(total_steps):
                # Update current SoC considering standby losses
                if t > 0: current_soc *= eta_standby ** dt

                # Subtract consumption if any occured at this timestep
                current_soc -= ev_demand[t]

                # Start charging if the car is parked and below target SoC
                if availability_profile[t] and current_soc < target_soc:
                    energy_needed = target_soc - current_soc
                    energy_to_charge = min(energy_needed, max_energy_per_step)

                    # Convert energy to required charging power
                    charging_power = energy_to_charge / (building_devices_data["EV"]["eta_ch"] * dt)

                    ev_charging_profile[t] = charging_power

                    # Update current SoC after charging
                    current_soc += energy_to_charge

                else:
                    # No charging when driving or already at target SoC
                    ev_charging_profile[t] = 0.0

            return ev_charging_profile

        # --- Residential Buildings ---
        if self.building in {"SFH", "TH", "MFH", "AB"}:

            # --- EV CARS ---
            for car_idx in range(number_of_ev):
                segment_data = segments[rd.choices(segment_names, weights=normalized_probs, k=1)[0]]
                # Limit random values to within ±1 standard deviation to avoid extreme outliers.
                consumption_per_km = np.clip(
                    np.random.normal(segment_data["energy_mean_Wh_per_km"], segment_data["energy_std_Wh_per_km"]),
                    segment_data["energy_mean_Wh_per_km"] - segment_data["energy_std_Wh_per_km"],
                    segment_data["energy_mean_Wh_per_km"] + segment_data["energy_std_Wh_per_km"]
                )
                battery_capacity = float(1000 * np.clip(
                    np.random.normal(segment_data["battery_mean_kWh"], segment_data["battery_std_kWh"]),
                    segment_data["battery_mean_kWh"] - segment_data["battery_std_kWh"],
                    segment_data["battery_mean_kWh"] + segment_data["battery_std_kWh"]
                )) # Wh

                ev_demand = np.zeros(total_steps)
                availability_profile = np.ones(total_steps, dtype=bool)  # Initially at home (available)

                # Iterate through all days, distinguishing workdays and non-workdays
                for day in range(self.nb_days):
                    # Determine if it's a non-working day: Saturday (5), Sunday (6), or a holiday
                    if (day + self.initial_day) % 7 in (5, 6) or day + 1 in holidays:
                        not_working_day = True
                    else:
                        not_working_day = False

                    # slice occupancy profile for current day
                    start_idx = day * steps_per_day
                    end_idx = (day + 1) * steps_per_day
                    occ_day = occ_profile[start_idx:end_idx]
                    daily_demand = np.zeros(steps_per_day)

                    # Number of occupants that day
                    max_occ_day = max(occ_day)

                    # Find timesteps when not all occupants are at home.
                    not_all_home = np.where(occ_day < max_occ_day)

                    # Select the driving distance distribution for the day
                    distance_probs = not_working_day_probs if not_working_day else weekday_distance_probs

                    # calculate how many people go out maximum in the same time in one day.
                    mobile_person = max(occ_profile) - min(occ_day)

                    try:
                        # Estimate potential car travel window from occupancy (first leave → last return)
                        car_leave = not_all_home[0][0]
                        # assumption: car returns when the last person arrives at home. This is the next timestep after the last timestep where not all are home
                        car_arrive = not_all_home[0][-1] + 1

                        # Car use is probabilistic: even if someone leaves, the car might not be used that day.
                        # 48% = share of people using a car for daily for travel.
                        # https://bmdv.bund.de/SharedDocs/DE/Anlage/G/mid-ergebnisbericht.pdf?__blob=publicationFile
                        # Table 7
                        prob_car_not_used = (1 - (0.48 / denom)) ** mobile_person

                        # Sample daily distance if the car is used; otherwise, set to 0 km.
                        daily_dist = np.random.uniform(*distance_intervals[np.random.choice(len(distance_intervals), p=distance_probs)]) if np.random.rand() > prob_car_not_used else 0
                    except IndexError:
                        # No one left home → no valid leave/arrive → car unused
                        daily_dist = 0
                        car_leave = 0
                        car_arrive = 0

                    # Compute daily charging demand (Wh), capping it at 90% of the battery capacity (minSoC = 5% and maxSoC = 95%)
                    # The commuting one-way driving distance to work accounts for 21%/2 of the total daily distance.
                    # https://bmdv.bund.de/SharedDocs/DE/Anlage/G/mid-ergebnisbericht.pdf?__blob=publicationFile
                    # Table 8
                    consumption = min(daily_dist * consumption_per_km * (1 - 0.105), battery_capacity * 0.9)

                    # Spread the consumption over the driving period
                    if consumption > 0: # Only if there is consumption the time of it is relevant
                        if car_arrive > car_leave:
                            driving_period = car_arrive - car_leave
                            consumption_per_timestep = consumption / driving_period
                            for t in range(car_leave, car_arrive):
                                daily_demand[t] = consumption_per_timestep
                                #  Mark as unavailable (away from home) during driving
                                availability_profile[start_idx + t] = False # Not at charging location
                        else:
                            daily_demand[car_arrive] = consumption
                            availability_profile[start_idx + car_arrive] = False

                    # Add the day's demand to the EV's overall profile.
                    ev_demand[start_idx:end_idx] += daily_demand


                all_EV_cars_demand_total += ev_demand

                # charging profile calculation
                ev_charging_profile = _generate_ev_charging_profile_from_consumption(ev_demand, availability_profile, battery_capacity, building_devices_data, total_steps, dt)
                on_demand_all_EV_cars_charging += ev_charging_profile

                # Save individual car profile
                individual_car_profiles.append({
                    "car_id": f"Car_{start_index_car + car_idx}",
                    "type": "EV",
                    "location": "Residential",
                    "battery_capacity_wh": battery_capacity,
                    "availability_profile": availability_profile,
                    "consumption_profile_wh": ev_demand,
                    "on_demand_charging_profile_w": ev_charging_profile,
                    "fuel_profile_l": None
                })

            # --- GASOLINE CARS ---
            for car_idx in range(number_of_ice):
                segment_data = segments[rd.choices(segment_names, weights=normalized_probs, k=1)[0]]
                fuel_consumption_l_per_100km = segment_data["consumption_gasoline_l_per_100km"]

                ice_car_availability = np.ones(total_steps, dtype=bool) # True = zuhause
                ice_car_fuel_profile = np.zeros(total_steps)

                for day in range(self.nb_days):
                    if (day + self.initial_day) % 7 in (5, 6) or day + 1 in holidays:
                        not_working_day = True
                    else:
                        not_working_day = False

                    start_idx = day * steps_per_day
                    end_idx = (day + 1) * steps_per_day
                    occ_day = occ_profile[start_idx:end_idx]
                    distance_probs = not_working_day_probs if not_working_day else weekday_distance_probs

                    max_occ_day = max(occ_day)
                    not_all_home = np.where(occ_day < max_occ_day)
                    mobile_person = max(occ_profile) - min(occ_day)

                    try:
                        car_leave = not_all_home[0][0]
                        car_arrive = not_all_home[0][-1] + 1
                        # Random daily distance
                        # use TOTAL cars (EV+ICE), not EVs only
                        prob_car_not_used = (1 - (0.48 / denom)) ** mobile_person
                        daily_dist = np.random.uniform(*distance_intervals[np.random.choice(len(distance_intervals), p=distance_probs)]) if np.random.rand() > prob_car_not_used else 0
                    except IndexError:
                        daily_dist = 0
                        car_leave = 0
                        car_arrive = 0

                    # Fuel consumption in liters
                    fuel_used_liters = daily_dist * (fuel_consumption_l_per_100km / 100.0)

                    # Spread the fuel consumption over the driving period
                    if fuel_used_liters > 0:
                        if car_arrive > car_leave:
                            driving_period = car_arrive - car_leave
                            fuel_per_step = fuel_used_liters / driving_period
                            for t in range(car_leave, car_arrive):
                                ice_car_fuel_profile[start_idx + t] = fuel_per_step
                                ice_car_availability[start_idx + t] = False # "Not at home"
                        else:
                            ice_car_fuel_profile[start_idx + car_arrive] = fuel_used_liters
                            ice_car_availability[start_idx + car_arrive] = False # "Not at home"

                # Store in fuel profile
                ice_fuel_profile += ice_car_fuel_profile

                # Save individual car profile
                individual_car_profiles.append({
                    "car_id": f"Car_{start_index_car + car_idx + number_of_ev}", # continue numbering after EVs
                    "type": "ICE",
                    "location": "Residential",
                    "battery_capacity_wh": 0,
                    "availability_profile": ice_car_availability,
                    "consumption_profile_wh": None,
                    "on_demand_charging_profile_w": None,
                    "fuel_profile_l": ice_car_fuel_profile
                })


        # --- Non-Residential Buildings ---
        elif self.building in {"OB"}:

            # Helper fuction to nudge the arrival time a little each workday so it’s not always the exact first non-zero occupancy index
            def jitter_after(idx, steps_per_day, max_delay_steps=1):
                if idx is None:
                    return None
                delay = np.random.randint(0, max_delay_steps + 1)  # 0,1,...,max_delay_steps
                return min(idx + delay, steps_per_day - 1)

            # Only the consumption related to commuting is charged in the workplace.
            # Find the first time index where occ_day is not 0 (i.e., the first person arrives at work)
            for car_idx in range(number_of_ev):
                segment_data = segments[rd.choices(segment_names, weights=normalized_probs, k=1)[0]]

                # Limit random values to within ±1 standard deviation to avoid extreme outliers.
                consumption_per_km = np.clip(
                    np.random.normal(segment_data["energy_mean_Wh_per_km"], segment_data["energy_std_Wh_per_km"]),
                    segment_data["energy_mean_Wh_per_km"] - segment_data["energy_std_Wh_per_km"],
                    segment_data["energy_mean_Wh_per_km"] + segment_data["energy_std_Wh_per_km"]
                )
                battery_capacity = float(1000 * np.clip(
                    np.random.normal(segment_data["battery_mean_kWh"], segment_data["battery_std_kWh"]),
                    segment_data["battery_mean_kWh"] - segment_data["battery_std_kWh"],
                    segment_data["battery_mean_kWh"] + segment_data["battery_std_kWh"]
                ))  # Wh

                # Initialize the EV's demand profile (in Wh) over the entire simulation period
                ev_demand = np.zeros(total_steps)
                availability_profile = np.zeros(total_steps, dtype=bool)  # Initially not available

                for day in range(self.nb_days):
                    # Determine if it's a non-working day: Saturday (5), Sunday (6), or a holiday
                    if (day + self.initial_day) % 7 in (5, 6) or (day + 1) in holidays:
                        continue

                    # slice occupancy profile for current day
                    start_idx = day * steps_per_day
                    end_idx = (day + 1) * steps_per_day
                    occ_day = occ_profile[start_idx:end_idx]

                    # If the building is empty all day, skip (no commute / no charging at work)
                    if not np.any(occ_day != 0.0):
                        continue

                    work_idx = np.where(occ_day > 0.0)[0]
                    arr_idx = jitter_after(work_idx[0], steps_per_day, max_delay_steps=2) # First person arrives at work

                    # One-way commute distance (sampled once per car)
                    dist_OB = np.random.uniform(
                        *distance_work[np.random.choice(len(distance_work), p=distance_work_probs)])

                    # Energy to recharge at work (cap at 90% SoC window)
                    consumption = min(dist_OB * consumption_per_km,
                                      battery_capacity * 0.9)  # Wh; Capping it at 90% of the battery capacity (minSoC = 5% and maxSoC = 95%)

                    # Assumption the drive to work takes 1 hour
                    commute_duration_steps = int(1/dt)
                    drive_start = max(arr_idx - commute_duration_steps, 0)
                    drive_end = arr_idx

                    # Spread the consumption equally over the driving period
                    if drive_end > drive_start:
                        consumption_per_timestep = consumption / (drive_end - drive_start)
                        for t in range(drive_start, drive_end):
                            ev_demand[start_idx + t] += consumption_per_timestep

                    else:
                        ev_demand[arr_idx] += consumption

                    # Charging only possible while at the office
                    departure_idx = work_idx[-1] + 1 # Last person leaves work
                    for t in range(arr_idx, departure_idx):
                        availability_profile[start_idx + t] = True


                # Accumulate the EV's profiles into the total profiles.
                all_EV_cars_demand_total += ev_demand

                # charging profile calculation
                ev_charging_profile = _generate_ev_charging_profile_from_consumption(ev_demand, availability_profile, battery_capacity, building_devices_data, total_steps, dt)
                on_demand_all_EV_cars_charging += ev_charging_profile


                # Save individual car profile
                individual_car_profiles.append({
                    "car_id": f"Car_{start_index_car + car_idx}",
                    "type": "EV",
                    "location": "Office",
                    "battery_capacity_wh": battery_capacity,
                    "availability_profile": availability_profile,
                    "consumption_profile_wh": ev_demand,
                    "on_demand_charging_profile_w": ev_charging_profile,
                    "fuel_profile_l": None
                })

            # --- ICE gasoline cars in offices: log one-way fuel at arrival to work ---
            for car_idx in range(number_of_ice):
                segment_data = segments[rd.choices(segment_names, weights=normalized_probs, k=1)[0]]
                fuel_consumption_l_per_100km = segment_data["consumption_gasoline_l_per_100km"]

                ice_car_availability = np.zeros(total_steps, dtype=bool)
                ice_car_fuel_profile = np.zeros(total_steps)

                for day in range(self.nb_days):
                    # Workdays only
                    if (day + self.initial_day) % 7 in (5, 6) or (day + 1) in holidays:
                        continue

                    start_idx = day * steps_per_day
                    end_idx = (day + 1) * steps_per_day
                    occ_day = occ_profile[start_idx:end_idx]

                    # skip if building empty that day
                    if not np.any(occ_day != 0.0):
                        continue

                    work_idx = np.where(occ_day>0)[0]
                    base_arrival_idx = np.where(occ_day != 0.0)[0][0]
                    arrive_idx = jitter_after(base_arrival_idx, steps_per_day, max_delay_steps=2)

                    # One-way commute distance (sampled once per car)
                    dist_OB = np.random.uniform(
                        *distance_work[np.random.choice(len(distance_work), p=distance_work_probs)])
                    fuel_one_way_l = dist_OB * (fuel_consumption_l_per_100km / 100.0)

                    if arrive_idx is not None:
                        ice_car_fuel_profile[start_idx + arrive_idx] += fuel_one_way_l

                        departure_idx = work_idx[-1]+1
                        for t in range(arrive_idx,departure_idx):
                            ice_car_availability[start_idx+t] = True

                ice_fuel_profile += ice_car_fuel_profile

                # Save individual car profile
                individual_car_profiles.append({
                    "car_id": f"Car_{start_index_car + car_idx + number_of_ev}", # continue numbering after EVs
                    "type": "ICE",
                    "location": "Office",
                    "battery_capacity_wh": 0,
                    "availability_profile": ice_car_availability,
                    "consumption_profile_wh": None,
                    "on_demand_charging_profile_w": None,
                    "fuel_profile_l": ice_car_fuel_profile
                })

        ev_capacity = [car["battery_capacity_wh"] for car in individual_car_profiles if car["type"] == "EV"]
        return all_EV_cars_demand_total, on_demand_all_EV_cars_charging, ev_capacity, ice_fuel_profile, individual_car_profiles

