"""
Fast (numba-compiled) drop-in for richardsonpy's household electricity simulation.

FastElectricityProfile replaces richardsonpy.classes.stochastic_el_load_wrapper.ElectricityProfile.power_sim
with numba kernels that follow run_lighting_simulation (lighting.py) and run_application_simulation
(appliance.py) of richardsonpy 0.2.x step by step. The stochastic model is unchanged; random numbers come
from numba's own generator, seeded per call from Python's `random` module. Results are therefore
statistically equivalent to the original, but not bit-identical.

If numba is missing or richardsonpy is not 0.2.x, FAST_AVAILABLE is False and callers should use the
original ElectricityProfile (see FAST_UNAVAILABLE_REASON).
"""

import math
import random
from importlib import metadata

import numpy as np
import richardsonpy.classes.stochastic_el_load_wrapper as wrap

FAST_AVAILABLE = True
FAST_UNAVAILABLE_REASON = ""

try:
    from numba import njit
except ImportError:
    FAST_AVAILABLE = False
    FAST_UNAVAILABLE_REASON = "numba is not installed (pip install districtgenerator[fast])"

    def njit(*args, **kwargs):
        """Stand-in decorator so this module can still be imported without numba."""
        return lambda function: function

try:
    _RICHARDSONPY_VERSION = metadata.version("richardsonpy")
except metadata.PackageNotFoundError:
    _RICHARDSONPY_VERSION = "unknown"
if FAST_AVAILABLE and not _RICHARDSONPY_VERSION.startswith("0.2."):
    FAST_AVAILABLE = False
    FAST_UNAVAILABLE_REASON = (f"richardsonpy {_RICHARDSONPY_VERSION} found; the fast kernels mirror "
                               f"richardsonpy 0.2.x")

# Number of appliances simulated by run_application_simulation (loop over range(33))
N_APPLIANCES = 33
MINUTES_PER_DAY = 24 * 60

# Relative monthly temperatures for electric space heating (appliance.py, run_application_simulation)
MONTHLY_RELATIVE_TEMPERATURE_MODIFIER = np.array([1.63, 1.821, 1.595, 0.867, 0.763, 0.191, 0.156, 0.087,
                                                  0.399, 0.936, 1.561, 1.994])


@njit(cache=True)
def _power_usage(cycle_time_left, appliance_type, standby_power, rated_power):
    """Port of appliance.get_power_usage (custom profiles for washing machine / washer dryer)."""
    result = rated_power
    if appliance_type == 26 or appliance_type == 27:
        if appliance_type == 26:
            total_cycle_time = 138
        else:
            total_cycle_time = 198
        temp = total_cycle_time - cycle_time_left + 1
        if 0 < temp <= 8:
            result = 73.0
        elif 8 < temp <= 29:
            result = 2056.0
        elif 29 < temp <= 81:
            result = 73.0
        elif 81 < temp <= 92:
            result = 73.0
        elif 92 < temp <= 94:
            result = 250.0
        elif 94 < temp <= 105:
            result = 73.0
        elif 105 < temp <= 107:
            result = 250.0
        elif 107 < temp <= 118:
            result = 73.0
        elif 118 < temp <= 120:
            result = 250.0
        elif 120 < temp <= 131:
            result = 73.0
        elif 131 < temp <= 133:
            result = 250.0
        elif 133 < temp <= 138:
            result = 568.0
        elif 138 < temp <= 198:
            result = 2500.0
        else:
            result = standby_power
    return result


@njit(cache=True)
def _cycle_length(mean_cycle_length, appliance_type):
    """Port of appliance.cycle_length."""
    if appliance_type == 14 or appliance_type == 15 or appliance_type == 16:
        # TV watching length approximation (mean viewing time approx. 73 minutes)
        return float(np.round(70.0 * (-math.log(1.0 - np.random.random())) ** 1.1))
    elif appliance_type == 31 or appliance_type == 32:
        # Some variation on the cycle length of heating appliances
        return np.random.normal(mean_cycle_length, mean_cycle_length / 10.0)
    return mean_cycle_length


@njit(cache=True, boundscheck=True)
def _appliances_day(occupancy, activity_statistics, month, has_appliance, mean_cycle_length, standby_power,
                    rated_power, calib_scalar, use_profile, restart_delay, out):
    """
    Port of appliance.run_application_simulation; adds the power of all appliances to `out` (1440 minutes).
    boundscheck=True keeps the IndexError of the original for out-of-range occupancy/statistics indices.
    """
    for i in range(N_APPLIANCES):
        # Appliances not installed contribute zero (not standby), as in the original
        if has_appliance[i] == 0:
            continue

        cycle_time_left = 0.0
        profile = use_profile[i]
        standby = standby_power[i]

        # Random start delay and normally distributed rated power (drawn once per day and appliance)
        restart_delay_left = np.random.random() * restart_delay[i] * 2
        rated = np.random.normal(rated_power[i], rated_power[i] / 10.0)

        for j in range(MINUTES_PER_DAY):
            power = standby
            ten_minute_count = j // 10
            active_occupants = occupancy[ten_minute_count]

            if cycle_time_left <= 0 and restart_delay_left > 0:
                # Off, restart delay running
                restart_delay_left = restart_delay_left - 1

            elif cycle_time_left <= 0:
                # Off: a start event needs active occupants (unless the profile is occupancy independent)
                if (active_occupants > 0 and profile != 8) or profile == 7:
                    activity_probability = 1.0
                    if profile < 6:
                        activity_probability = activity_statistics[int(5 * active_occupants + profile),
                                                                   ten_minute_count + 2]
                    elif i == 31:
                        # Electric space heating depends on the month
                        activity_probability = MONTHLY_RELATIVE_TEMPERATURE_MODIFIER[month - 1]

                    if np.random.random() < calib_scalar[i] * activity_probability:
                        # Start event (port of start_appliance)
                        cycle_time_left = _cycle_length(mean_cycle_length[i], i)
                        restart_delay_left = restart_delay[i]
                        power = _power_usage(cycle_time_left, i, standby, rated)
                        cycle_time_left = cycle_time_left - 1

            elif profile == 8:
                # Storage heater branch of the original. It is unreachable: profile 8 never passes the start
                # condition above, so its cycle time never becomes positive. (The original branch would also
                # fail in appliance.date_add, which adds an int to a list.) Not ported.
                pass

            else:
                # On: pause while no occupant is active, except for level, laundry and custom profiles
                if active_occupants == 0 and profile != 7 and profile != 2 and profile != 8:
                    pass
                else:
                    power = _power_usage(cycle_time_left, i, standby, rated)
                    cycle_time_left = cycle_time_left - 1

            out[j] += power


@njit(cache=True, boundscheck=True)
def _lighting_day(occupancy, irradiance, bulbs, threshold_mean, threshold_std, calib_scalar,
                  effective_occupancy, event_lower, event_upper, out):
    """Port of lighting.run_lighting_simulation; adds the power of all bulbs to `out` (1440 minutes)."""
    # Irradiance threshold of this house (drawn once per day)
    irradiance_threshold = np.random.normal(threshold_mean, threshold_std)

    for b in range(bulbs.shape[0]):
        rating = bulbs[b]
        # Random relative use weighting of this bulb, multiplied by the calibration scalar
        weighting = calib_scalar * (-math.log(np.random.random()))

        t = 0
        while t < MINUTES_PER_DAY:
            active_occupants = occupancy[t // 10]

            # Low irradiance, or a 5 % chance of a switch-on event above the threshold
            low_irradiance = irradiance[t] < irradiance_threshold or np.random.random() < 0.05

            if low_irradiance and np.random.random() < effective_occupancy[active_occupants] * weighting:
                # Switch-on event: choose one of 9 equally probable duration classes
                r1 = np.random.random()
                light_duration = 0.0
                for j in range(1, 10):
                    if r1 < j / 9:
                        r2 = np.random.random()
                        light_duration = r2 * (event_upper[j - 1] - event_lower[j - 1]) + event_lower[j - 1]
                        break

                t_start = t
                for _ in range(int(light_duration)):
                    if t > MINUTES_PER_DAY - 1:
                        break
                    # Turn off the light if there are no active occupants
                    if occupancy[t // 10] == 0:
                        break
                    out[t] += rating
                    t += 1
                if t == t_start:
                    # Cannot happen with the default configuration (switch-on needs active occupants and the
                    # shortest duration is 1 minute); the original would loop forever here.
                    t += 1
            else:
                # The bulb remains off
                t += 1


@njit(cache=True)
def _simulate_day(seed, occupancy, irradiance, month, activity_statistics,
                  has_appliance, mean_cycle_length, standby_power, rated_power, calib_scalar, use_profile,
                  restart_delay, bulbs, threshold_mean, threshold_std, light_calib_scalar, effective_occupancy,
                  event_lower, event_upper):
    """Simulate one day (lighting first, then appliances, as in power_sim). Returns minute sums (light, app)."""
    np.random.seed(seed)
    light = np.zeros(MINUTES_PER_DAY)
    app = np.zeros(MINUTES_PER_DAY)
    _lighting_day(occupancy, irradiance, bulbs, threshold_mean, threshold_std, light_calib_scalar,
                  effective_occupancy, event_lower, event_upper, light)
    _appliances_day(occupancy, activity_statistics, month, has_appliance, mean_cycle_length, standby_power,
                    rated_power, calib_scalar, use_profile, restart_delay, app)
    return light, app


class FastElectricityProfile(wrap.ElectricityProfile):
    """
    ElectricityProfile with a numba-compiled power_sim (same signature and return value).

    Appliance, bulb and lighting configuration arrays are built once per instance (i.e. per flat).
    """

    # numpy copies of ElectricityProfile.activity_statistics ('wd'/'we'), built lazily per process
    _activity_statistics_np = {}

    def __init__(self, appliances, lightbulbs):
        if not FAST_AVAILABLE:
            raise RuntimeError(f"FastElectricityProfile is not available: {FAST_UNAVAILABLE_REASON}")
        super().__init__(appliances, lightbulbs)

        if len(appliances.data) < N_APPLIANCES:
            raise ValueError(f"Expected at least {N_APPLIANCES} appliances, got {len(appliances.data)}.")

        # Column meaning see richardsonpy.classes.appliance.Appliances
        data = np.array([row[:11] for row in appliances.data[:N_APPLIANCES]], dtype=np.float64)
        self._has_appliance = np.ascontiguousarray(data[:, 0])
        self._mean_cycle_length = np.ascontiguousarray(data[:, 3])
        self._rated_power = np.ascontiguousarray(data[:, 4])
        self._standby_power = np.ascontiguousarray(data[:, 5])
        self._restart_delay = np.ascontiguousarray(data[:, 6])
        self._use_profile = np.ascontiguousarray(data[:, 8])
        self._calib_scalar = np.array(appliances.calib_scalar[:N_APPLIANCES], dtype=np.float64)

        self._bulbs = np.array(lightbulbs, dtype=np.float64)

        config = self.lighting_config
        self._threshold_mean = float(config.ext_irr_threshold_mean)
        self._threshold_std = float(config.ext_irr_threshold_std_dev)
        self._light_calib_scalar = float(config.calib_scalar)
        self._effective_occupancy = np.array(config.eff_occupancy, dtype=np.float64)
        self._event_lower = np.array(config.light_event_lower_value, dtype=np.float64)
        self._event_upper = np.array(config.light_event_upper_value, dtype=np.float64)

    @classmethod
    def _activity_statistics_array(cls, type_weekday):
        """numpy version of the class-level activity statistics (converted once per process)."""
        if type_weekday not in cls._activity_statistics_np:
            cls._activity_statistics_np[type_weekday] = np.ascontiguousarray(
                wrap.ElectricityProfile.activity_statistics[type_weekday], dtype=np.float64)
        return cls._activity_statistics_np[type_weekday]

    def power_sim(self, irradiation, weekend, day, occupancy):
        """
        Calculate electric power for lighting and appliance usage (see ElectricityProfile.power_sim).

        Returns
        -------
        tuple of arrays
            (power_el_total, power_el_light, power_el_app) in W, 1 minute resolution.
        """
        self._load_activity_statistics()
        month = self._get_month(day)
        activity_statistics = self._activity_statistics_array(self.type_weekday[weekend])

        occupancy = np.asarray(occupancy)
        occupancy_int = occupancy.astype(np.int64)
        if not np.array_equal(occupancy_int, occupancy):
            # The original uses occupancy as list index, which requires integer values
            raise ValueError("Occupancy must contain integer numbers of active occupants.")
        irradiance = np.ascontiguousarray(irradiation, dtype=np.float64)

        # Seed numba's generator from Python's random module (keeps runs reproducible with random.seed)
        seed = random.getrandbits(32)
        light, app = _simulate_day(seed, np.ascontiguousarray(occupancy_int), irradiance, month,
                                   activity_statistics, self._has_appliance, self._mean_cycle_length,
                                   self._standby_power, self._rated_power, self._calib_scalar, self._use_profile,
                                   self._restart_delay, self._bulbs, self._threshold_mean, self._threshold_std,
                                   self._light_calib_scalar, self._effective_occupancy, self._event_lower,
                                   self._event_upper)
        return (app + light, light, app)
