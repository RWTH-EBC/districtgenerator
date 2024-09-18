#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 21 14:09:28 2015

@author: tsz
"""
from __future__ import division

import os
import numpy as np
import classes.lighting as lighting_model

class ElectricityProfile(object):
    """
    ElectricityProfile class
    """

    type_weekday = ["wd", "we"]  # weekday, weekend

    # Load statistics for appliances (transition probability matrix)
    activity_statistics = {}
    activity_statistics_loaded = False

    def __init__(self, lightbulbs):
        """
        This class loads all input data
        
        Parameters
        ----------
        ligthbulbs : list
            List of lightbulb configurations
        """


        # Create lighting configuration
        self.lighting_config = lighting_model.LightingModelConfiguration()
        self.lightbulbs = lightbulbs

    def _get_leap_year(self, leap_year=False):
        """

        Parameters
        ----------
        day : int
            Day number
        leap_year : bool, optional
            Boolean to define leap year (default: False). If True, uses
            leap year

        Returns
        -------

        """
        if leap_year:
            days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        else:
            days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

        return days

    def power_sim_lighting(self, irradiation, occupancy):
        """
        Calculate electric power for lighting.

        Parameters
        ----------
        irradiation : Array-like
            Solar irradiation on a horizontal plane for one day (1 minute res.)
        weekend : Boolean
            - True: Weekend
            - False: Monday - Friday
        day : Integer
            Day of the (computation) year.
        occupancy : Array-like
            Occupancy for one day (10 minute resolution)


        Returns
        -------
        tup_res : tuple (of arrays)
            Results tuple power_el_light
            power_el_light : array
                Array holding el. power values for light usage in Watt
        """

        # Lighting
        demand_lighting = lighting_model.run_lighting_simulation(
            vOccupancyArray=occupancy,
            vBulbArray=self.lightbulbs,
            vIrradianceArray=irradiation,
            light_mod_config=self.lighting_config)

        power_el_light = np.sum(demand_lighting, axis=0)
        return power_el_light

    def power_sim_app(self, annual_demand_app, building_profiles, time_resolution):
        """
                Calculate electric power for appliance usage and ventilation.

                Parameters
                ----------
                annual_demand_app: dict
                    Annual electricity demand for the appliances and ventilation for each zone of the building in kWh
                annual_el_zone_demand : float
                    Zone annual electricity demand for appliances and ventilation in kWh
                monthly_el_zone_demand : list
                    Zone monthly electricity demand for appliances and ventilation in kWh
                el_zone_demand : list
                    Zone electricity demand profile for appliances and ventilation in W
                profile_devices_zone_month : list
                    Zone appliances and ventilation profile in a month in W
                monthly_el_zone_total_demand : float
                    Zone Appliances and ventilation electricity demand in a month in Wh
                el_zone_month_demand : list
                    Zone electricity demand profile for appliances and ventilation in a month in W

                Returns
                -------
                tup_res : tuple (of arrays)
                    Results tuple power_el_app
                    power_el_app : array
                        Array holding el. power values for appliance usage in Watt
                """

        days_in_month = self._get_leap_year()

        power_el_app = [0] * int(8760 * 3600/time_resolution)

        for zones in building_profiles.values():
            for zone_name, profiles in zones.items():
                if annual_demand_app[zone_name] != 0:

                    annual_el_zone_demand = annual_demand_app[zone_name]
                    monthly_el_zone_demand = None

                    if 'profile_month_zone' in profiles:
                        profile_month_zone = profiles['profile_month_zone']
                        monthly_el_zone_demand = [(a / sum(profile_month_zone)) * annual_el_zone_demand for a in
                                                  profile_month_zone]

                    if 'profile_devices_zone' in profiles:
                        profile_devices_zone = profiles['profile_devices_zone']
                        el_zone_demand = []

                        start = 0
                        for month_index, days in enumerate(days_in_month):
                            time_steps = int(days * 24 * 3600/time_resolution)
                            profile_devices_zone_month = profile_devices_zone[start:start + time_steps]
                            start += time_steps

                            if monthly_el_zone_demand:
                                monthly_el_zone_total_demand = monthly_el_zone_demand[month_index] * 1000
                                el_zone_month_demand = [(a / sum(profile_devices_zone_month)) * monthly_el_zone_total_demand / (time_resolution/3600)
                                    for a in profile_devices_zone_month]
                                for i in range(len(el_zone_month_demand)):
                                    if el_zone_month_demand[i] == 0:
                                        el_zone_month_demand[i] = np.random.normal(el_zone_demand[-1],el_zone_demand[-1] * 0.1)   # If the demand is 0, it is changed to be equal to the demand in the last time step with a small variation
                                el_zone_demand.extend(el_zone_month_demand)
                        power_el_app = [total + daily for total, daily in zip(power_el_app, el_zone_demand)]
        return power_el_app




