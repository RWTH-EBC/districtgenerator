#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Electricity-profile generation for non-residential buildings.
The module combines the stochastic non-residential lighting model with
zone-specific appliance and ventilation profiles. It provides daily
ten-minute lighting demand and annual appliance/ventilation electricity
profiles at a user-defined temporal resolution.
"""
from __future__ import division

import numpy as np
import districtgenerator.classes.lighting_non_residential as lighting_model

class ElectricityProfile(object):
    """Generate non-residential lighting and appliance electricity profiles.

    Parameters
    ----------
    lightbulbs : array_like
        Rated electrical powers of the modeled light bulbs in W.
    building : str
        Non-residential building-use identifier used to initialize the
        lighting behavior configuration.

    Attributes
    ----------
    lighting_config : LightingModelConfiguration
        Building-specific stochastic lighting configuration.
    lightbulbs : array_like
        Bulb ratings passed during initialization.
    """

    def __init__(self, lightbulbs, building):
        """
        Initialize the non-residential electricity-profile model.
        """
        # Create lighting configuration
        self.lighting_config = lighting_model.LightingModelConfiguration(building)
        self.lightbulbs = lightbulbs

    def _get_leap_year(self, leap_year=False):
        """
        Parameters
        ----------
        leap_year : bool, optional
            Boolean to define leap year (default: False). If True, uses leap year

        Returns
        -------
        day : int
            Day number

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
        occupancy : Array-like
            Occupancy for one day (10 minute resolution)

        Returns
        -------
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
        Calculate one day of non-residential lighting power demand.

        Parameters
        ----------
        irradiation : array_like
            External irradiance in W/m² for one day at ten-minute
            resolution. The upstream profile generation interpolates
            irradiance to 144 values before calling this method.
        occupancy : array_like
            Number of active occupants for one day at ten-minute
            resolution (144 values).

        Returns
        -------
        power_el_light : numpy.ndarray
            Total lighting electrical power in W for each ten-minute time
            step. Individual bulb profiles are summed element-wise.
        """

        days_in_month = self._get_leap_year()
        power_el_app = [0] * int(8760 * 3600/time_resolution)
        for zones in building_profiles.values():
            for zone_name, profiles in zones.items():
                if annual_demand_app[zone_name] != 0:
                    # annual_el_zone_demand: Zone annual electricity demand for appliances and ventilation in kWh
                    annual_el_zone_demand = annual_demand_app[zone_name]
                    # monthly_el_zone_demand: monthly electricity demand for appliances and ventilation in kWh
                    monthly_el_zone_demand = None
                    if 'profile_month_zone' in profiles:
                        profile_month_zone = profiles['profile_month_zone']
                        monthly_el_zone_demand = [(a / sum(profile_month_zone)) * annual_el_zone_demand for a in
                                                  profile_month_zone]

                    if 'profile_devices_zone' in profiles:
                        profile_devices_zone = profiles['profile_devices_zone']
                        # el_zone_demand: Zone electricity demand profile for appliances and ventilation in W
                        el_zone_demand = []

                        start = 0
                        for month_index, days in enumerate(days_in_month):
                            time_steps = int(days * 24 * 3600/time_resolution)
                            # profile_devices_zone_month: Zone appliances and ventilation profile in a month in W
                            profile_devices_zone_month = profile_devices_zone[start:start + time_steps]
                            start += time_steps

                            if monthly_el_zone_demand:
                                # monthly_el_zone_total_demand: Zone Appliances and ventilation electricity demand in a month in Wh
                                monthly_el_zone_total_demand = monthly_el_zone_demand[month_index] * 1000
                                # el_zone_month_demand: Zone electricity demand profile for appliances and ventilation in a month in W
                                el_zone_month_demand = [(a / sum(profile_devices_zone_month)) * monthly_el_zone_total_demand / (time_resolution/3600)
                                    for a in profile_devices_zone_month]

                                el_zone_demand.extend(el_zone_month_demand)
                        power_el_app = [total + daily for total, daily in zip(power_el_app, el_zone_demand)]
        return power_el_app




