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
import functions.change_resolution as chres
import pylightxl as xl

def load_profiles(filename):
    """
    Load domestic hot water profiles from an Excel file.

    Parameters
    ----------
    filename : str
        Path to the Excel file containing the profiles.

    Returns
    -------
    dict
        A dictionary containing the loaded profiles with the following structure:
        {
            'we': {
                1: np.array(...),  # Weekend profile for 1 person
                2: np.array(...),  # Weekend profile for 2 people
                ...
            },
            'wd': {
                1: np.array(...),  # Weekday profile for 1 person
                2: np.array(...),  # Weekday profile for 2 people
                ...
            },
            'we_mw': np.array(...),  # Weekend mean profile
            'wd_mw': np.array(...)   # Weekday mean profile
        }

    Notes
    -----
    The Excel file should have sheets named 'we_mw', 'wd_mw', 'we1', 'we2', ..., 'wd1', 'wd2', ...
    Each sheet should contain 1440 values (one for each minute of the day).
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
