# -*- coding: utf-8 -*-
"""
Script to generate domestic hot water demands.
This script is a copy of dhw_stochastical.py from pyCity.
https://github.com/RWTH-EBC/pyCity
"""

from __future__ import division

import os
import numpy as np
import math
import random
import districtgenerator.functions.change_resolution as chres
import pylightxl as xl

def load_profiles(filename):
    """
    Loads domestic hot water (DHW) usage profiles from an Excel file and structures them by day type and occupancy level.

    ----------

    Parameters
    ----------
    - filename: Path to the Excel file containing water demand profiles.
      The file must include sheets named for weekday (`wd`) and weekend (`we`) profiles, both average and probability-based.

    Returns
    ----------
    - profiles: Dictionary containing structured demand profiles.
      Includes:
        - 'wd': Weekday probability profiles by occupancy count.
        - 'we': Weekend probability profiles by occupancy count.
        - 'wd_mw' and 'we_mw': Average minute-wise water usage profiles for weekdays and weekends.
    """
    # Initialization
    profiles = {"we": {}, "wd": {}}
    #book = xlrd.open_workbook(filename)
    book = xl.readxl(fn=filename)
    sheetnames = book.ws_names

    
    # Iterate over all sheets    
    for sheetname in sheetnames:
        #sheet = xl.readxl(fn=filename, ws=sheetname)
        
        # Read values
        values = [book.ws(ws = sheetname).index(row=i, col=1) for i in range(1, 1441)] #[sheet.cell_value(i,0) for i in range(1440)]

        # Store values in dictionary
        if sheetname in ("wd_mw", "we_mw"):
            profiles[sheetname] = np.array(values)
        elif sheetname[1] == "e":
            profiles["we"][int(sheetname[2])] = np.array(values)
        else:
            profiles["wd"][int(sheetname[2])] = np.array(values)
    
    # Return results
    return profiles


def compute_daily_demand(probability_profiles, average_profile, occupancy,
                         current_day, temperature_difference=35):
    """
    Computes the daily domestic hot water (DHW) usage and corresponding heat demand
    based on occupancy and stochastic probability profiles.

    ----------

    Parameters
    ----------
    - probability_profiles: Dictionary of minute-wise sampled probability distributions
      for different occupancy levels.
    - average_profile: Array of average tap water demand (liters/hour) per minute of the day.
    - occupancy: Array of 10-minute sampled occupancy values for the building/apartment.
    - current_day: Integer representing the current day of the year (0 = Jan 1).
    - temperature_difference: Float or array indicating the temperature rise required [°C]
      (default is 35°C).

    Returns
    ----------
    - water: Array of minute-wise tap water volume flow in liters/hour.
    - heat: Array of minute-wise heat demand in Watts based on water usage.
    """
    # Initialization
    water = []
    timesteps = 1440
    time = np.arange(timesteps)
    
    # Compute seasonal factor
    # Introduce abbreviation to stay below 80 characters per line
    arg = math.pi * (2 / 365 * (current_day + time / timesteps) - 1 / 4)
    probability_season = 1 + 0.1 * np.cos(arg)
    
    # Iterate over all time steps
    for t in time:
        # Compute the product of occupancy and probability_profiles
        current_occupancy = occupancy[int(t/10)]
        if current_occupancy > 0:
            probability_profile = probability_profiles[current_occupancy][t]
        else:
            probability_profile = 0
    
        # Compute probability for tap water demand at time t
        probability = probability_profile * probability_season[t]

        # Check if tap water demand occurs at time t
        if random.random() < probability:
            # Compute amount of tap water consumption. This consumption has 
            # to be positive!
            water.append(abs(random.gauss(average_profile[t], sigma=114.33)))
        else:
            water.append(0)

    # Transform to array and compute resulting heat demand
    water = np.array(water)  # l/h
    c = 4180                 # J/(kg.K)
    rho = 980 / 1000         # kg/l
    sampling_time = 3600     # s
    heat = water * rho * c * temperature_difference / sampling_time  # W
    
    # Return results
    return (water, heat)


def full_year_computation(occupancy, 
                          profiles, 
                          time_dis=3600,
                          initial_day=0, 
                          temperature_difference=35):
    """
    Computes a full year of domestic hot water (DHW) usage and heat demand based on occupancy and stochastic profiles.

    ----------

    Parameters
    ----------
    - occupancy: Array-like, 10-minute sampled occupancy values for the entire year.
    - profiles: Dictionary containing probability and average demand profiles for weekdays (`wd`) and weekends (`we`) by occupancy level.
    - time_dis: Integer, time discretization of the output data in seconds (default is 3600 seconds).
    - initial_day: Integer representing the first day of the year (0 = Monday, 6 = Sunday).
    - temperature_difference: Float or array indicating the temperature rise required [°C] (default is 35°C).

    Returns
    ----------
    - water: Array of tap water flow in liters/hour, resampled to the specified time resolution.
    - heat: Array of heat demand in Watts, resampled to the specified time resolution.
    """
    # Initialization
    number_days = int(len(occupancy) / 144)
    
    water = np.zeros(len(occupancy) * 10)
    heat = np.zeros(len(occupancy) * 10)
    
    for day in range(number_days):
        # Is the current day on a weekend?
        if (day + initial_day) % 7 >= 5:
            probability_profiles = profiles["we"]
            average_profile = profiles["we_mw"]
        else:
            probability_profiles = profiles["wd"]
            average_profile = profiles["wd_mw"]
        
        # Get water and heat demand for the current day
        res = compute_daily_demand(probability_profiles, 
                                   average_profile,
                                   occupancy[day*144:(day+1)*144],
                                   day, 
                                   temperature_difference)
        (current_water, current_heat) = res
        
        # Include current_water and current_heat in water and heat
        water[day*1440:(day+1)*1440] = current_water
        heat[day*1440:(day+1)*1440] = current_heat
    
    # Change sampling time to the given input
    water = chres.changeResolution(water, 60, time_dis, "sum") / time_dis * 60
    heat = chres.changeResolution(heat, 60, time_dis, "sum") / time_dis * 60

    # Return results
    return (water, heat)


if __name__ == "__main__":

    #  Define src path
    src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filename = 'dhw_stochastical.xlsx'
    input_path = os.path.join(src_path, 'inputs', filename)

    # Load profiles
    profiles = load_profiles(input_path)
    
    # Compute active occupants for one year
    # Max. occupancy is 5 people simultaneously
    occupancy = np.random.geometric(p=0.8, size=6*24*365)-1
    occupancy = np.minimum(5, occupancy)
    
    # Set initial_day
    initial_day = 0
    
    # Run simulation
    (water, heat) = full_year_computation(occupancy, profiles, 
                                          time_dis=60,
                                          initial_day=initial_day)
    
    # Change time resolution to 15 minutes
    dt = 15
    hd = chres.changeResolution(heat, 60, dt*60, "sum") / dt

    # Plot heat demand
    import matplotlib.pyplot as plt
    ax1=plt.subplot(2, 1, 1)
    plt.plot(np.arange(len(heat))/60, heat, color="b", linewidth=2)
    plt.step((np.arange(len(hd)) * dt+dt)/60, hd, color="r", linewidth=2)
    plt.ylabel("Heat demand in Watt")
    plt.xlim((0, 8760))
    
    plt.subplot(2, 1, 2, sharex=ax1)
    plt.step((np.arange(len(occupancy)) * 10+10)/60, occupancy, linewidth=2)
    plt.ylabel("Active occupants")
    offset = 0.2
    plt.ylim((-offset, max(occupancy)+offset))
    plt.yticks(list(range(int(max(occupancy)+1))))
    
    plt.show()
