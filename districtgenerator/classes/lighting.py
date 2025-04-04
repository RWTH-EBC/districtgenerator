#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Thu May 21 21:24:29 2015

@author: Thomas
"""
from __future__ import division

import random
import math
import csv


# The Excel Sheet has a fairly complicated configuration file
# (which I suppose most people have ignored so far)
# This class provides the standard inputs.
# If required, other values can be entered.
class LightingModelConfiguration():

    def __init__(self,
                 external_irradiance_threshold=[60, 10]):
        """
        Constructor of lighting class object instance

        Parameters
        ----------
        external_irradiance_threshold : list, optional
            List holding building external global irradiance threshold values
            in W/m2 [index 0: mean value; index 1: standard deviation value]
            (default: [60, 10])
        """

        # External global irradiance threshold
        self.ext_irr_threshold_mean = external_irradiance_threshold[0]
        self.ext_irr_threshold_std_dev = external_irradiance_threshold[1]

    def relative_bulb_use_weighting(self):
        """
        This represents the concept that some bulbs are used more
        frequently than others in a building.

        The return value is [-ln(random_variable)]

        Returns
        -------
        -math.log(random.random())
        """
        return -math.log(random.random())

def run_lighting_simulation(vOccupancyArray, vBulbArray, vIrradianceArray,
                            light_mod_config):
    """

    Parameters
    ----------
    vOccupancyArray : array-like
        Occupancy for one day (10 minute resolution)
    vBulbArray : array-like
        Bulb data
    vIrradianceArray : array-like
        Irradiance data
    light_mod_config : object
        LightingModelConfiguration object instance

    Returns
    -------
    result : float
        Power in Watt
    """

    # Determine the irradiance threshold of this Building
    iIrradianceThreshold = random.gauss(
        light_mod_config.ext_irr_threshold_mean,
        light_mod_config.ext_irr_threshold_std_dev)

    # "Clear the target area"
    result = []

    # For each bulb
    for i in range(len(vBulbArray)):
        # Reset counter for current light bulb
        consumption = []

        # Get the bulb rating
        iRating = vBulbArray[i]


        iTime = 0  # Counter variable
        # Calculate the bulb usage at each 10 minutes of the day (24*6 timesteps per day)
        while iTime < 24 * 6:

            # Get the irradiance for this timestep
            iIrradiance = vIrradianceArray[iTime]

            # Get the number of current active occupants for this timestep
            iActiveOccupants = vOccupancyArray[iTime]

            # Determine if the bulb switch-on condition is passed
            # ie. Insuffient irradiance and at least one active occupant
            # There is a 5% chance of switch on event if the irradiance is above the threshold
            bLowIrradiance = ((iIrradiance < iIrradianceThreshold) or (
                    random.random() < 0.05))

            # Check the probability of a switch on at this time
            if bLowIrradiance and iActiveOccupants > 0:

                # Store the demand
                consumption.append(iRating)

                # Increment the time
                iTime += 1


            else:
                # The bulb remains off
                consumption.append(0)

                # Increase counter
                iTime += 1

        result.append(consumption)

    return result
