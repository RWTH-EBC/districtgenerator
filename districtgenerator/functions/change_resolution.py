# -*- coding: utf-8 -*-
"""
Script to change resolution of timeseries values with constant
sampling rate.
"""

from __future__ import division
import numpy as np
import math


def changeResolution(values, oldResolution, newResolution, method="mean"):
    """
    Changes the temporal resolution of a time series with constant sampling intervals.

    Parameters
    ----------
    values : array_like
        Original time-series values.
    oldResolution : int
        Original temporal resolution in seconds.
    newResolution : int
        Target temporal resolution in seconds.
    method : {"mean", "sum"}, optional
        Aggregation method. ``"mean"`` is appropriate for quantities
        such as power, whereas ``"sum"`` is appropriate for quantities
        such as energy. The default is ``"mean"``.

    Returns
    -------
    numpy.ndarray
        Resampled time series.
    """
    # Compute original time indexes
    timeOld = np.arange(len(values)) * oldResolution

    # Compute new time indexes
    length = math.ceil(len(values) * oldResolution / newResolution)
    timeNew = np.arange(length) * newResolution

    if method == "mean":
        if newResolution < oldResolution:
            # Interpolate
            valuesResampled = np.interp(timeNew, timeOld, values)
            return valuesResampled
        else:
            # Use cumsum for averaging values
            # Repeat last value in old resolution for time values larger than
            # timesOld + oldResolution
            timeOld = np.concatenate((timeOld, [timeOld[-1] + oldResolution]))
            timeNew = np.concatenate((timeNew, [timeNew[-1] + newResolution]))
            while timeOld[-1] < timeNew[-1]:
                timeOld = np.append(timeOld, timeOld[-1] + oldResolution)
                values = np.append(values, values[-1])
            values = np.cumsum(np.concatenate(([0], values)))

            # Rescale values for averages
            values = values * oldResolution / newResolution
    elif method == "sum":
        # If values have to be summed up, use cumsum to modify the given data
        # Add one dummy value to later use diff (which reduces the number of
        # indexes by one)
        values = np.cumsum(np.concatenate(([0], values)))
        timeOld = np.concatenate((timeOld, [timeOld[-1] + oldResolution]))
        timeNew = np.concatenate((timeNew, [timeNew[-1] + newResolution]))
    else:
        raise ValueError("Unknown method selected.")
    # Interpolate
    valuesResampled = np.interp(timeNew, timeOld, values)

    # "Undo" the cumsum
    valuesResampled = np.diff(valuesResampled)

    return valuesResampled
