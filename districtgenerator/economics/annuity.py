"""
Annuity method for investments with replacements and residual values, based on VDI 2067-1.
"""
import math


def capital_recovery_factor(observation_time, interest_rate):
    """Convert a present value into equal annual payments.

    Parameters
    ----------
    observation_time : int or float
        Positive analysis period in years over which the present value is recovered.
    interest_rate : float
        Annual discount rate as a fraction, for example 0.05 for 5 percent.
        Zero gives straight-line recovery over the analysis period.

    Returns
    -------
    float
        Capital recovery factor in 1/year.
    """
    if interest_rate == 0:
        return 1 / observation_time
    q = 1 + interest_rate
    return ((q ** observation_time) * interest_rate) / ((q ** observation_time) - 1)


def annuity_factor(life_time, observation_time, interest_rate):
    """Annualize investment with replacements and a remaining-life credit.

    Uses the replacement and residual-value approach of VDI 2067-1.

    Parameters
    ----------
    life_time : float
        Positive technical service life in years. Replacements are assumed at
        multiples of this lifetime and at the same undiscounted investment cost.
    observation_time : int or float
        Positive analysis period in years, shared with other compared technologies.
    interest_rate : float
        Annual discount rate as a fraction, for example 0.05 for 5 percent.

    Returns
    -------
    float
        Investment annuity factor in 1/year.
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
