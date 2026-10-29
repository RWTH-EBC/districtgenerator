"""
Annuity method for investments with replacements and residual values, based on VDI 2067-1.
"""
import math


def capital_recovery_factor(observation_time, interest_rate):
    """
    Capital recovery factor of the observation period.

    Parameters
    ----------
    observation_time : int
        Observation period [a].
    interest_rate : float
        Interest rate [-].

    Returns
    -------
    float
        Capital recovery factor [1/a].
    """
    if interest_rate == 0:
        return 1 / observation_time
    q = 1 + interest_rate
    return ((q ** observation_time) * interest_rate) / ((q ** observation_time) - 1)


def annuity_factor(life_time, observation_time, interest_rate):
    """
    Annuity factor of an investment including replacements and the residual value (VDI 2067-1, pages 16-17).

    Parameters
    ----------
    life_time : float
        Technical life time of the device [a].
    observation_time : int
        Observation period [a].
    interest_rate : float
        Interest rate [-].

    Returns
    -------
    float
        Factor that converts the investment into annual costs [1/a].
    """
    q = 1 + interest_rate
    CRF = capital_recovery_factor(observation_time, interest_rate)

    # Number of required replacements
    n = int(math.floor(observation_time / life_time))

    # Investment for replacements
    invest_replacements = sum((q ** (-i * life_time)) for i in range(1, n + 1))

    # Residual value of final replacement
    res_value = ((n + 1) * life_time - observation_time) / life_time * (q ** (-observation_time))

    if life_time > observation_time:
        return (1 - res_value) * CRF
    return (1 + invest_replacements - res_value) * CRF
