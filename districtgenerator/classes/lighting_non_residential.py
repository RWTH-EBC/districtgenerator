#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Thu May 21 21:24:29 2015

@author: Thomas
"""
from __future__ import division

import random
import math
from districtgenerator.classes.non_residential import GenericNonResidential

class LightingModelConfiguration():
    """
    Store building-specific parameters for the lighting model.

    Parameters
    ----------
    building : str
        Non-residential building-use identifier understood by
        :class:`~districtgenerator.classes.non_residential.GenericNonResidential`.
    external_irradiance_threshold : sequence of float, optional
        Fallback mean and standard deviation of the external global
        irradiance threshold in W/m². The default is ``[60, 30]``.

    Attributes
    ----------
    nwg_config : GenericNonResidential
        Behavior configuration for the selected non-residential
        building type.
    ext_irr_threshold_mean : float
        Mean global-irradiance threshold in W/m² below which artificial
        lighting is likely to be switched on.
    ext_irr_threshold_std_dev : float
        Standard deviation of the irradiance threshold in W/m².
    """

    def __init__(self, building, external_irradiance_threshold=[60, 30]):
        """
        Initialize the non-residential lighting configuration.

        Parameters
        ----------
        building : str
            Non-residential building-use identifier used to load the
            corresponding behavior configuration.
        external_irradiance_threshold : sequence of float, optional
            Two-element fallback sequence ``[mean, standard_deviation]`` in
            W/m². The default is ``[60, 30]``.
        """
        self.nwg_config = GenericNonResidential(building)

        # External global irradiance threshold
        self.ext_irr_threshold_mean, self.ext_irr_threshold_std_dev = self.nwg_config.get_lighting_irradiance_threshold()

        if self.ext_irr_threshold_mean is None or self.ext_irr_threshold_std_dev is None:
            # Give warning if one of the two threshold values is specified but not the other one
            if self.ext_irr_threshold_mean is None and self.ext_irr_threshold_std_dev is not None:
                print(f"Warning: Mean value of the external irradiance threshold for lighting is not specified. Using default value of {external_irradiance_threshold[0]} W/m2.")
                self.ext_irr_threshold_mean = external_irradiance_threshold[0]

            elif self.ext_irr_threshold_mean is not None and self.ext_irr_threshold_std_dev is None:
                print(f"Warning: Standard deviation of the external irradiance threshold for lighting is not specified. Using default value of {external_irradiance_threshold[1]} W/m2.")
                self.ext_irr_threshold_std_dev = external_irradiance_threshold[1]

            # If neither of the two threshold values is specified, use the default values
            else:
                self.ext_irr_threshold_mean = external_irradiance_threshold[0]
                self.ext_irr_threshold_std_dev = external_irradiance_threshold[1]

    def relative_bulb_use_weighting(self):
        """
        This represents the concept that some bulbs are used more
        frequently than others in a building.

        The return value is [-ln(random_variable)]

        Returns
        -------
        - math.log(random.random())
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

            # Draw a threshold for this timestep
            iIrradianceThreshold = max(0,random.gauss(
                light_mod_config.ext_irr_threshold_mean,
                light_mod_config.ext_irr_threshold_std_dev
                ))

            # Determine if the bulb switch-on condition is passed
            # ie. Insuffient irradiance and at least one active occupant
            # There is a 10% chance of switch on event if the irradiance is above the threshold
            bLowIrradiance = ((iIrradiance < iIrradianceThreshold) or (
                    random.random() < 0.1))

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
