# -*- coding: utf-8 -*-
"""Dynamic 7R2C thermal-zone solver based on VDI 6007.

The model represents the thermal zone using five temperature nodes:

* indoor air,
* internal-wall surface,
* internal-wall thermal mass,
* external-wall surface, and
* external-wall thermal mass.

The thermal network is solved using a backward-Euler time integration
scheme.

Notes
-----
The solver requires an initialized envelope for which the VDI 6007
thermal parameters and equivalent outdoor temperatures have already
been calculated.

Solar radiation and internal gains are not passed directly to the
solver. Their effects are represented through quantities previously
calculated and stored in the envelope object.

The current implementation assumes infiltration-based ventilation.
Heating and cooling can be distributed between the indoor-air and
surface nodes, and temperature control is based on operative
temperature.
"""

from typing import Dict, Optional, Tuple
import numpy as np

RES_BUILDING_TYPES = {"SFH", "TH", "MFH", "AB"}

def _area_fraction_aw(envelope) -> float:
    """Return the external-surface fraction of the room-side area.

    Parameters
    ----------
    envelope : object
        Envelope-like object providing ``Aaw_tot`` and ``Araum_tot`` in square
        metres. Missing attributes are interpreted as zero.

    Returns
    -------
    float
        Ratio of external-wall area to total room-side area, clipped to
        the interval [0, 1].
    """
    Araum = max(float(getattr(envelope, "Araum_tot", 0.0)), 1e-12)
    Aaw   = float(getattr(envelope, "Aaw_tot", 0.0))
    return float(np.clip(Aaw / Araum, 0.0, 1.0))

def _radiative_split_weights(envelope) -> float:
    """
    Return the fraction of radiant gains assigned to external surfaces.

    Parameters
    ----------
    envelope : object
        Envelope-like object that may provide a ``_surface_list`` containing
        surface objects with ``surface_type``, ``rad_heat_trans_coef``,
        ``_opaque_area``, and ``_glazed_area`` attributes.

    Returns
    -------
    float: Fraction of radiant gains assigned to external surfaces. The complementary fraction ``1 - f_aw``
            is assigned to internal surfaces.
    """
    try:
        surfaces = getattr(envelope, "_surface_list", [])
    except Exception:
        surfaces = []

    AW_TYPES = {"ExtWall", "Roof", "GroundFloor"}
    IW_TYPES = {"IntWall", "IntCeiling", "IntFloor"}

    aw_eff = 0.0
    iw_eff = 0.0

    for s in surfaces:
        hr = float(getattr(s, "rad_heat_trans_coef", 0.0))
        st = getattr(s, "surface_type", "")
        if st in AW_TYPES:
            # interior-facing area = opaque + glazing on the facade
            aw_eff += hr * (float(getattr(s, "_opaque_area", 0.0))
                            + float(getattr(s, "_glazed_area", 0.0)))
        elif st in IW_TYPES:
            iw_eff += hr * float(getattr(s, "_opaque_area", 0.0))

    total = aw_eff + iw_eff
    if total <= 0.0:
        # fall back to geometric fraction if anything is missing
        return _area_fraction_aw(envelope)
    return aw_eff / total

def build_params_from_envelope(envelope, dt_s: float) -> Dict[str, float]:
    """
    Build the numerical 7R2C parameter dictionary from an envelope.

    Parameters
    ----------
    envelope : object
        Parameterized Envelope-like object. It must provide the VDI 6007 thermal
        parameters ``R1AW``, ``R1IW``, ``C1AW``, ``C1IW``, ``RrestAW``,
        ``RalphaStarAW``, ``RalphaStarIW``, ``UA_tot``, ``Aaw_tot``, and
        ``Araum_tot``. It must also provide ``rho_air``, ``c_p_air``, ``V_dot``,
        ``V_dot_infiltration``, ``eta_temp_vent``, and ``V`` for the air and
        ventilation terms.
    dt_s : float
        Simulation time step in seconds.

    Returns
    -------
    dict of str to float
        Solver parameters with the following entries:

        ``C1IW``, ``C1AW``, ``C_air``
            Thermal capacitances in J/K.
        ``RalphaStarIW``, ``RalphaStarAW``, ``R1IW``, ``R1AW``, ``RrestAW``
            Thermal resistances in K/W.
        ``H_ve``, ``UA_tot``
            Heat-transfer coefficients in W/K.
        ``Aaw_tot``, ``Araum_tot``
            Areas in m².
        ``dt``
            Time step in seconds.

    """
    # Sanity checks for attributes created by _VDI6007_params
    needed = ["R1AW", "R1IW", "C1AW", "C1IW", "RrestAW",
              "RalphaStarAW", "RalphaStarIW",
              "UA_tot", "Aaw_tot", "Araum_tot"]
    missing = [k for k in needed if not hasattr(envelope, k)]
    if missing:
        raise AttributeError(
            f"Envelope is missing attributes {missing}. "
            "Run envelope._VDI6007_params(SunRad, internal_gains) first."
        )

    # Ventilation conductance (W/K)
    # Accounting for heat recovery in mechanical ventilation, but not in infiltration
    H_ve = float(envelope.rho_air) * float(envelope.c_p_air) / 3600.0 * (float(envelope.V_dot) * (1.0 - float(envelope.eta_temp_vent)) + float(envelope.V_dot_infiltration))

    # A tiny air capacity for numerical stability (or scale with volume)
    # Rule of thumb: ~ 1.2 kJ/K per m² zone floor area
    C_air = float(envelope.rho_air) * float(envelope.c_p_air) * float(envelope.V)  # J/K

    return dict(C1IW=float(envelope.C1IW),  C1AW=float(envelope.C1AW), C_air=float(C_air),
                RalphaStarIW=float(envelope.RalphaStarIW), RalphaStarAW=float(envelope.RalphaStarAW),
                R1IW=float(envelope.R1IW), R1AW=float(envelope.R1AW), RrestAW=float(envelope.RrestAW),
                H_ve=float(H_ve), UA_tot=float(envelope.UA_tot),
                Aaw_tot=float(envelope.Aaw_tot), Araum_tot=float(envelope.Araum_tot), dt=float(dt_s))

def prepare_gains_from_envelope(envelope, rad_frac: float = 0.60) -> Dict[str, np.ndarray]:
    """
    Prepare convective and radiative gain time series for the 7R2C solver.

    Parameters
    ----------
    envelope : object
        Envelope-like object containing solar gain series ``Q_il_kon`` and
        ``Q_il_str`` generated by the equivalent-temperature calculation, and an
        ``internal_gains`` time series for non-solar internal gains. If the solar
        gain attributes are absent, zero-valued solar gains are created using the
        length of ``theta_eq_tot`` when available.
    rad_frac : float, default 0.60
        Fraction of ``envelope.internal_gains`` treated as radiative. The
        remaining fraction is assigned directly to the zone-air node as a
        convective gain. Values are not clipped to [0, 1].

    Returns
    -------
    dict of str to numpy.ndarray
        Dictionary containing equally sized power time series in watts:

        ``Q_il_kon_I``
            Total convective gains applied to the zone-air node.
        ``Q_il_str_iw``
            Total radiant gains assigned to internal-wall surfaces.
        ``Q_il_str_aw``
            Total radiant gains assigned to external-envelope surfaces.

    """
    # --- solar (from theta_eq precomp) ---
    try:
        Q_sol_kon = np.asarray(envelope.Q_il_kon, dtype=float).reshape(-1)
        Q_sol_str = np.asarray(envelope.Q_il_str, dtype=float).reshape(-1)
    except AttributeError:
        n = len(getattr(envelope, "theta_eq_tot", [])) or 0
        Q_sol_kon = np.zeros(n, dtype=float)
        Q_sol_str = np.zeros(n, dtype=float)

    n = len(Q_sol_kon)
    Q_int_kon = np.zeros(n, dtype=float)
    Q_int_str = np.zeros(n, dtype=float)

    # pick source of non-solar internal gains (total array)
    gains_src = envelope.internal_gains
    if gains_src is not None:
        v = np.asarray(gains_src, dtype=float).reshape(-1)[:n]
        Q_int_str[:len(v)] += rad_frac * v
        Q_int_kon[:len(v)] += (1.0 - rad_frac) * v

    # totals
    Q_kon_total = Q_sol_kon + Q_int_kon
    Q_str_total = Q_sol_str + Q_int_str

    # --- split radiant to BOTH IW and AW (physically realistic) ---
    f_aw = _radiative_split_weights(envelope)
    f_iw = 1.0 - f_aw
    Q_il_str_aw = f_aw * Q_str_total
    Q_il_str_iw = f_iw * Q_str_total

    return dict(Q_il_kon_I=Q_kon_total, Q_il_str_iw=Q_il_str_iw, Q_il_str_aw=Q_il_str_aw)

# ---------------------------------------------------------------------------
# 7R2C zone solver (Backward Euler)
# Nodes:
#   T_il : air node (IL)     [°C]  (small capacity C_air)
#   T_iw : internal wall     [°C]  (capacity C1IW)
#   T_aw : external wall     [°C]  (capacity C1AW)
#
# Resistances/Conductances:
#   Air ↔ IW      : RalphaStarIW
#   Air ↔ AW      : RalphaStarAW
#   Air ↔ Outside : 1/H_ve   (ventilation)
#   AW  ↔ Outside : R1AW (dynamic path to θ_eq)  +  RrestAW (residual to T_ext)
#
# Gains:
#   Convective to Air: Q_il_kon_I
#   Radiant to IW   : Q_il_str_iw
#   Radiant to AW   : Q_il_str_aw
# HVAC:
#   Q_HC applied at air node (positive = heating, negative = cooling)
# ---------------------------------------------------------------------------

def _step5_free_float(params, state5, T_ext, theta_eq, gains_t):
    """
    Advance the five-node thermal model by one free-floating time step.

    Parameters
    ----------
    params : dict
        Solver parameter dictionary as returned by
        :func:`build_params_from_envelope`.
    state5 : array_like of float
        Previous thermal state ordered as ``[T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw]`` in °C.
    T_ext : float
        Outdoor air temperature in °C.
    theta_eq : float
        Equivalent external-envelope temperature in °C.
    gains_t : dict
        Heat gains for the current time step in watts. Required keys are ``Q_il_kon_I``, ``Q_il_str_iw``, and ``Q_il_str_aw``.

    Returns
    -------
    numpy.ndarray
        Updated state with shape ``(5,)`` and ordering ``[T_air, T_s_iw,
        T_m_iw, T_s_aw, T_m_aw]`` in °C.

    """
    dt    = params["dt"]
    C_air = params["C_air"];   C1IW = params["C1IW"];   C1AW = params["C1AW"]
    G_aiw = 1.0/params["RalphaStarIW"]
    G_aaw = 1.0/params["RalphaStarAW"]
    G_1iw = 1.0/params["R1IW"]
    G_1aw = 1.0/params["R1AW"]
    G_rest= 1.0/params["RrestAW"]
    H_inf = params["H_ve"]  # treat H_ve as infiltration only

    T_air_p, T_s_iw_p, T_m_iw_p, T_s_aw_p, T_m_aw_p = state5  # surfaces have no C, prev only for completeness

    Q_kon_I  = gains_t["Q_il_kon_I"]
    Q_str_iw = gains_t["Q_il_str_iw"]
    Q_str_aw = gains_t["Q_il_str_aw"]

    A = np.zeros((5,5)); b = np.zeros(5)

    # Air
    A[0,0] = C_air/dt + G_aiw + G_aaw + H_inf
    A[0,1] = -G_aiw
    A[0,3] = -G_aaw
    b[0]   = (C_air/dt)*T_air_p + Q_kon_I + H_inf*T_ext

    # IW surface
    A[1,0] = -G_aiw
    A[1,1] = G_aiw + G_1iw
    A[1,2] = -G_1iw
    b[1]   = Q_str_iw

    # IW mass
    A[2,1] = -G_1iw
    A[2,2] = C1IW/dt + G_1iw
    b[2]   = (C1IW/dt)*T_m_iw_p

    # AW surface
    A[3,0] = -G_aaw
    A[3,3] = G_aaw + G_1aw
    A[3,4] = -G_1aw
    b[3]   = Q_str_aw

    # AW mass  (dynamic link to surface + residual to θ_eq)
    A[4,3] = -G_1aw
    A[4,4] = C1AW/dt + G_1aw + G_rest
    b[4]   = (C1AW/dt)*T_m_aw_p + G_rest*theta_eq

    return np.linalg.solve(A, b)


def _step5_with_setpoint(params, state5, T_ext, theta_eq, gains_t,
                         T_set, w_op, f_aw, sigma=(0.,0.,1.), Q_limit=None,
                         Q_limit_cool=None):
    """
    Advance one time step while enforcing an operative-temperature setpoint.

    Parameters
    ----------
    params : dict
        Solver parameter dictionary as returned by
        :func:`build_params_from_envelope`.
    state5 : array_like of float
        Previous state ordered as ``[T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw]``
        in °C.
    T_ext : float
        Outdoor air temperature in °C.
    theta_eq : float
        Equivalent external-envelope temperature in °C.
    gains_t : dict
        Current convective and radiative gains in watts. Required keys are
        ``Q_il_kon_I``, ``Q_il_str_iw``, and ``Q_il_str_aw``.
    T_set : float
        Target operative temperature in °C.
    w_op : float
        Weight of zone-air temperature in the operative-temperature equation.
        The surface-temperature contribution receives weight ``1 - w_op``.
    f_aw : float
        Fraction of the mean room-side surface temperature represented by the
        external-envelope surface temperature.
    sigma : tuple of float, default (0.0, 0.0, 1.0)
        Fractions of HVAC power assigned to the internal-wall surface,
        external-envelope surface, and zone-air node, respectively. The values
        are used directly and are not normalized.
    Q_limit : float, optional
        Maximum positive heating power in W. ``None`` disables the heating limit.
    Q_limit_cool : float, optional
        Maximum cooling-power magnitude in W. Cooling is represented internally by
        negative ``Q_HC``; ``None`` disables the cooling limit.

    Returns
    -------
    T_air : float
        Zone-air temperature in °C.
    T_s_iw : float
        Internal-wall surface temperature in °C.
    T_m_iw : float
        Internal-wall mass temperature in °C.
    T_s_aw : float
        External-envelope surface temperature in °C.
    T_m_aw : float
        External-envelope mass temperature in °C.
    Q_HC : float
        HVAC power in W; positive values denote heating and negative values denote
        cooling.
    """
    dt    = params["dt"]
    C_air = params["C_air"];   C1IW = params["C1IW"];   C1AW = params["C1AW"]
    G_aiw = 1.0/params["RalphaStarIW"]
    G_aaw = 1.0/params["RalphaStarAW"]
    G_1iw = 1.0/params["R1IW"]
    G_1aw = 1.0/params["R1AW"]
    G_rest= 1.0/params["RrestAW"]
    H_inf = params["H_ve"]  # infiltration only

    T_air_p, _, T_m_iw_p, _, T_m_aw_p = state5

    Q_kon_I  = gains_t["Q_il_kon_I"]
    Q_str_iw = gains_t["Q_il_str_iw"]
    Q_str_aw = gains_t["Q_il_str_aw"]

    A = np.zeros((6,6)); b = np.zeros(6)

    # Air (include −σ_conv*Q_HC on LHS)
    A[0,0] = C_air/dt + G_aiw + G_aaw + H_inf
    A[0,1] = -G_aiw
    A[0,3] = -G_aaw
    A[0,5] = -sigma[2]
    b[0]   = (C_air/dt)*T_air_p + Q_kon_I + H_inf*T_ext

    # IW surface (−σ_iw*Q_HC on LHS)
    A[1,0] = -G_aiw
    A[1,1] = G_aiw + G_1iw
    A[1,2] = -G_1iw
    A[1,5] = -sigma[0]
    b[1]   = Q_str_iw

    # IW mass
    A[2,1] = -G_1iw
    A[2,2] = C1IW/dt + G_1iw
    b[2]   = (C1IW/dt)*T_m_iw_p

    # AW surface (−σ_aw*Q_HC on LHS)
    A[3,0] = -G_aaw
    A[3,3] = G_aaw + G_1aw
    A[3,4] = -G_1aw
    A[3,5] = -sigma[1]
    b[3]   = Q_str_aw

    # AW mass
    A[4,3] = -G_1aw
    A[4,4] = C1AW/dt + G_1aw + G_rest
    b[4]   = (C1AW/dt)*T_m_aw_p + G_rest*theta_eq

    # Operative temperature constraint:
    # T_op = w_op * T_air + (1-w_op) * [ (1-f_aw)*T_s_iw + f_aw*T_s_aw ] = T_set
    A[5,0] = w_op
    A[5,1] = (1.0 - w_op) * (1.0 - f_aw)
    A[5,2] = 0.0
    A[5,3] = (1.0 - w_op) * f_aw
    A[5,4] = 0.0
    A[5,5] = 0.0
    b[5]   = T_set

    sol = np.linalg.solve(A, b)
    T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw, Q_HC = sol

    # Optional clamp (heating)
    if Q_limit is not None and Q_HC > Q_limit:
        Qc = float(Q_limit)  # cap only the positive (heating) side
        # Re-solve with Q_HC fixed
        A3 = A[:5, :5].copy();
        b3 = b[:5].copy()
        # Move Q terms to RHS
        b3[0] += sigma[2] * Qc
        b3[1] += sigma[0] * Qc
        b3[3] += sigma[1] * Qc
        T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw = np.linalg.solve(A3, b3)
        Q_HC = Qc

    # Optional clamp (cooling)
    if Q_limit_cool is not None and Q_HC < -float(Q_limit_cool):
        Qc = -float(Q_limit_cool)  # ADDED: cap negative (cooling) side
        A3 = A[:5, :5].copy()
        b3 = b[:5].copy()
        b3[0] += sigma[2] * Qc
        b3[1] += sigma[0] * Qc
        b3[3] += sigma[1] * Qc
        T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw = np.linalg.solve(A3, b3)
        Q_HC = Qc

    return T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw, Q_HC

def simulate_7r2c(envelope, T_ext: np.ndarray, dt_s: float, theta_eq: Optional[np.ndarray] = None,
                  T_set_heat: Optional[np.ndarray] = None, T_set_cool: Optional[np.ndarray] = None,
                  cooling_season_days: Tuple[int, int] = (145, 255), w_op: float = 0.5, night_setback: bool = False,
                  calendar: Optional[Dict] = None):
    """
    Simulate the VDI 6007-inspired five-node thermal model.

    Parameters
    ----------
    envelope : object
        Fully prepared Envelope-like object containing the VDI 6007 parameters,
        gain time series, temperature setpoints, and ``heatload``. If available,
        ``coolingload`` is used as the cooling-power limit.
    T_ext : numpy.ndarray
        Outdoor dry-bulb temperature time series in °C. Its length defines the
        number of simulation steps.
    dt_s : float
        Simulation time step in seconds.
    theta_eq : numpy.ndarray, optional
        Equivalent external-envelope temperature in °C. If ``None``, ``T_ext`` is
        used. The array must provide at least as many values as ``T_ext``.
    T_set_heat : array_like, optional
        Operative heating setpoint in °C for each time step. If ``None``, a
        constant series based on ``envelope.T_set_min`` is used.
    T_set_cool : array_like, optional
        Operative cooling setpoint in °C for each time step. If ``None``, a
        constant series based on ``envelope.T_set_max`` is used.
    cooling_season_days : tuple of int, default (145, 255)
        Inclusive 1-based day-of-year interval in which cooling is enabled when
        ``calendar`` is ``None``.
    w_op : float, default 0.5
        Weight of zone-air temperature in the operative-temperature calculation.
        The remaining weight is assigned to the area-weighted room-side surface
        temperature. Values are not clipped to [0, 1].
    night_setback : bool, default False
        If ``True``, replace heating and cooling setpoints from 22:00 to 05:59 by
        ``T_set_min_night`` and ``T_set_max_night`` respectively, with fallback
        offsets of -3 K and +1 K.
    calendar : dict, optional
        Calendar-based season definition. Required keys are
        ``heating_period_start``, ``heating_period_end``,
        ``cooling_period_start``, and ``cooling_period_end``. Optional Boolean keys
        ``consider_heating_period`` and ``consider_cooling_period`` default to
        ``True``. Calendar day indices are zero-based and interval end values are
        exclusive.

    Returns
    -------
    dict of str to numpy.ndarray
        Time series with the same length as ``T_ext``:

        ``Q_H``
            Heating demand in W, reported as non-negative values.
        ``Q_C``
            Cooling demand in W, reported as non-negative values.
        ``T_op``
            Operative zone temperature in °C.
        ``T_air``
            Zone-air temperature in °C.
        ``T_s_iw``, ``T_m_iw``
            Internal-wall surface and mass temperatures in °C.
        ``T_s_aw``, ``T_m_aw``
            External-envelope surface and mass temperatures in °C.
    """

    n = len(T_ext)

    if theta_eq is None:
        theta_eq = T_ext.copy()

    # Build parameters and gains
    params = build_params_from_envelope(envelope, dt_s)
    gains = prepare_gains_from_envelope(envelope, rad_frac=0.60)
    Q_il_kon_I = gains["Q_il_kon_I"][:n]
    Q_il_str_iw = gains["Q_il_str_iw"][:n]
    Q_il_str_aw = gains["Q_il_str_aw"][:n]

    # Setpoints
    if T_set_heat is None:
        T_set_heat = np.full(n, float(envelope.T_set_min), dtype=float)
    else:
        T_set_heat = np.asarray(T_set_heat, dtype=float).reshape(-1)[:n]
    if T_set_cool is None:
        T_set_cool = np.full(n, float(envelope.T_set_max), dtype=float)
    else:
        T_set_cool = np.asarray(T_set_cool, dtype=float).reshape(-1)[:n]

    if night_setback:
        # define night hours: 22:00-05:59
        steps_per_day = int(round(86400.0 / dt_s))
        for t in range(n):
            hod = (t % steps_per_day) * dt_s / 3600.0
            if hod >= 22 or hod < 6:
                T_set_heat[t] = float(getattr(envelope, "T_set_min_night", T_set_heat[t] - 3.0))
                T_set_cool[t] = float(getattr(envelope, "T_set_max_night", T_set_cool[t] + 1.0))

    # Cooling season mask
    steps_per_day = int(round(86400.0 / dt_s))
    day_of_year = np.arange(n) // steps_per_day + 1
    cool_on = (day_of_year >= cooling_season_days[0]) & (day_of_year <= cooling_season_days[1])

    # Calendar-based seasons
    if calendar is not None:
        heating_start = int(calendar["heating_period_start"])
        heating_end = int(calendar["heating_period_end"])
        cooling_start = int(calendar["cooling_period_start"])
        cooling_end = int(calendar["cooling_period_end"])

        consider_cooling = bool(calendar.get("consider_cooling_period", True))
        consider_heating = bool(calendar.get("consider_heating_period", True))

        day = (np.arange(n) // steps_per_day).astype(int)

        cool_on = (day >= cooling_start) & (day < cooling_end) & consider_cooling

        heat_on = (~((day >= heating_end) & (day < heating_start))) & consider_heating
    else:
        heat_on = np.ones(n, dtype=bool)

    f_aw = _area_fraction_aw(envelope)

    # Initialize arrays
    T_air = np.zeros(n); T_s_iw = np.zeros(n); T_m_iw = np.zeros(n)
    T_s_aw = np.zeros(n); T_m_aw = np.zeros(n); T_op = np.zeros(n)
    Q_H = np.zeros(n); Q_C = np.zeros(n)

    # Initial state (all nodes near heat setpoint)
    T0 = float(getattr(envelope, "T_set_min", 20.0) - 0.5)
    state5 = (T0, T0, T0, T0, T0)

    Q_lim = envelope.heatload
    Q_lim_cool = getattr(envelope, "coolingload", None)
    sigma = (0.0, 0.0, 1.0)  # default: all convective to air

    for t in range(n):
        g_t = dict(
            Q_il_kon_I=Q_il_kon_I[t],
            Q_il_str_iw=Q_il_str_iw[t],
            Q_il_str_aw=Q_il_str_aw[t],
        )

        # Free-float
        T_air_ff, T_s_iw_ff, T_m_iw_ff, T_s_aw_ff, T_m_aw_ff = _step5_free_float(
            params, state5, T_ext[t], theta_eq[t], g_t
        )
        T_op_ff = w_op * T_air_ff + (1.0 - w_op) * ((1.0 - f_aw) * T_s_iw_ff + f_aw * T_s_aw_ff)

        # Gate heating with heat_on; cooling with cool_on (calendar or default)
        need_heat = (T_op_ff < T_set_heat[t]) and heat_on[t]
        need_cool = (T_op_ff > T_set_cool[t]) and cool_on[t]

        if need_heat or need_cool:
            T_target = T_set_heat[t] if need_heat else T_set_cool[t]
            T_air_t, T_s_iw_t, T_m_iw_t, T_s_aw_t, T_m_aw_t, Q_HC = _step5_with_setpoint(
                params, state5, T_ext[t], theta_eq[t], g_t,
                T_set=T_target, w_op=w_op, f_aw=f_aw, sigma=sigma,
                Q_limit=Q_lim, Q_limit_cool=Q_lim_cool)
        else:
            T_air_t, T_s_iw_t, T_m_iw_t, T_s_aw_t, T_m_aw_t = \
                T_air_ff, T_s_iw_ff, T_m_iw_ff, T_s_aw_ff, T_m_aw_ff
            Q_HC = 0.0

        # Store & advance
        T_air[t], T_s_iw[t], T_m_iw[t], T_s_aw[t], T_m_aw[t] = \
            T_air_t, T_s_iw_t, T_m_iw_t, T_s_aw_t, T_m_aw_t
        T_op[t] = w_op * T_air_t + (1.0 - w_op) * ((1.0 - f_aw) * T_s_iw_t + f_aw * T_s_aw_t)
        if Q_HC >= 0:
            Q_H[t] = Q_HC
        else:
            Q_C[t] = -Q_HC

        state5 = (T_air_t, T_s_iw_t, T_m_iw_t, T_s_aw_t, T_m_aw_t)

    return dict(Q_H=Q_H, Q_C=Q_C, T_op=T_op,
                T_air=T_air,
                T_s_iw=T_s_iw, T_m_iw=T_m_iw,
                T_s_aw=T_s_aw, T_m_aw=T_m_aw)

def _build_setpoints_arrays(envelope, n, dt_h, building_type, night_setback, holidays, initial_day: int = 0):
    """
    Construct heating and cooling setpoint time series.

    Parameters
    ----------
    envelope : object
        Envelope-like object providing ``T_set_min`` and ``T_set_max``. Night and
        free-day setpoints are read from ``T_set_min_night``,
        ``T_set_max_night``, and ``T_set_min_free_day`` when available.
    n : int
        Number of time steps.
    dt_h : float
        Time-step duration in hours.
    building_type : str
        Building-type identifier. ``SFH``, ``TH``, ``MFH``, and ``AB`` are treated
        as residential; all other values follow the non-residential schedule.
    night_setback : bool
        For residential buildings, enable the 22:00--05:59 night setback. For
        non-residential buildings the implemented workday/night schedule is applied
        independently of this flag.
    holidays : iterable of int or None
        Zero-based simulation-day indices treated as holidays for non-residential
        buildings.
    initial_day : int, default 0
        Weekday index of simulation day zero, with Monday = 0 and Sunday = 6.

    Returns
    -------
    T_heat : numpy.ndarray
        Heating-setpoint series in °C with length ``n``.
    T_cool : numpy.ndarray
        Cooling-setpoint series in °C with length ``n``.

    """
    dt_s = dt_h * 3600.0
    steps_per_day = int(round(86400.0 / dt_s))
    T_heat = np.full(n, float(envelope.T_set_min), dtype=float)
    T_cool = np.full(n, float(envelope.T_set_max), dtype=float)

    if building_type in RES_BUILDING_TYPES:
        # Residential: night 22:00–05:59 only if night_setback requested
        if night_setback:
            for t in range(n):
                hod = (t % steps_per_day) * dt_s / 3600.0
                if hod >= 22 or hod < 6:
                    T_heat[t] = float(getattr(envelope, "T_set_min_night", envelope.T_set_min - 3.0))
                    T_cool[t] = float(getattr(envelope, "T_set_max_night", envelope.T_set_max + 1.0))
    else:
        # Non-residential: night 18:00–05:59, weekends/holidays = free day; disable cooling on free days
        holidays = set(holidays or [])
        for t in range(n):
            day = t // steps_per_day  # day index starting at 0
            hod = (t % steps_per_day) * dt_s / 3600.0
            weekday = (int(initial_day) + int(day)) % 7  # 0=Mon,...,6=Sun
            is_weekend = (weekday in (5, 6))
            is_holiday = (day in holidays)
            working_day = (not is_weekend) and (not is_holiday)

            if hod >= 18 or hod < 6:  # night
                T_heat[t] = float(getattr(envelope, "T_set_min_night", envelope.T_set_min - 3.0)) if working_day \
                            else float(getattr(envelope, "T_set_min_free_day", envelope.T_set_min - 3.0))
                T_cool[t] = float(getattr(envelope, "T_set_max_night", envelope.T_set_max + 1.0))
            else:
                T_heat[t] = float(envelope.T_set_min) if working_day \
                            else float(getattr(envelope, "T_set_min_free_day", envelope.T_set_min))
                # Cooling only on working hours of working days; otherwise set very high to turn it off
                T_cool[t] = float(envelope.T_set_max) if working_day else 100.0

    return T_heat, T_cool

def _map_states_for_legacy(envelope, T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw):
    """
    Map five-node temperatures to the legacy three-temperature interface.

    Parameters
    ----------
    envelope : object
        Envelope-like object providing ``C1IW``, ``C1AW``, ``Aaw_tot``, and
        ``Araum_tot``. Missing capacitances default to zero.
    T_air : array_like
        Zone-air temperature series in °C.
    T_s_iw : array_like
        Internal-wall surface temperature series in °C.
    T_m_iw : array_like
        Internal-wall mass temperature series in °C.
    T_s_aw : array_like
        External-envelope surface temperature series in °C.
    T_m_aw : array_like
        External-envelope mass temperature series in °C.

    Returns
    -------
    T_m : array_like
        Legacy mass temperature, calculated as a heat-capacity-weighted mean of
        ``T_m_iw`` and ``T_m_aw``.
    T_i : array_like
        Legacy indoor temperature, equal to ``T_air``.
    T_s : array_like
        Legacy surface temperature, calculated from internal and external surface
        temperatures using the external area fraction.

    """
    C1IW = float(getattr(envelope, "C1IW", 0.0))
    C1AW = float(getattr(envelope, "C1AW", 0.0))
    Csum = C1IW + C1AW if (C1IW + C1AW) > 0 else 1.0
    f_aw = _area_fraction_aw(envelope)

    T_m = (C1IW*T_m_iw + C1AW*T_m_aw) / Csum
    T_i = T_air
    T_s = (1.0 - f_aw)*T_s_iw + f_aw*T_s_aw
    return T_m, T_i, T_s


def calc(envelope, T_e, calendar, dt, initial_day, building_type):
    """
    Calculate heating/cooling demand using the legacy 7R2C wrapper interface.

    Parameters
    ----------
    envelope : object
        Prepared Envelope-like object required by :func:`simulate_7r2c`. It must
        additionally provide ``theta_eq_tot``.
    T_e : array_like
        Outdoor air temperature time series in °C.
    calendar : dict
        Calendar definition passed to :func:`simulate_7r2c`. The key ``holidays``
        must contain zero-based simulation-day indices. Heating and cooling period
        keys required by :func:`simulate_7r2c` must also be present.
    dt : float
        Simulation time step in hours.
    initial_day : int
        Weekday index of the first simulation day, with Monday = 0 and Sunday = 6.
    building_type : str
        Building-type identifier used to construct residential or
        non-residential setpoint schedules.

    Returns
    -------
    Q_H : numpy.ndarray
        Non-negative heating demand in W.
    Q_C : numpy.ndarray
        Non-negative cooling demand in W.
    T_op : numpy.ndarray
        Operative temperature in °C.
    T_m : numpy.ndarray
        Legacy aggregated mass temperature in °C.
    T_i : numpy.ndarray
        Legacy indoor-air temperature in °C.
    T_s : numpy.ndarray
        Legacy aggregated surface temperature in °C.
    """
    T_e = np.asarray(T_e, dtype=float)
    n = len(T_e)

    holidays = calendar["holidays"]

    # Build setpoints like the old logic (no night setback branch), honoring initial_day
    T_heat, T_cool = _build_setpoints_arrays(
        envelope=envelope, n=n, dt_h=dt,
        building_type=building_type, night_setback=False, holidays=holidays,
        initial_day=initial_day
    )
    # Use theta_eq
    theta_eq = envelope.theta_eq_tot

    out = simulate_7r2c(
        envelope=envelope,
        T_ext=T_e,
        dt_s=dt * 3600.0,
        theta_eq=theta_eq,
        T_set_heat=T_heat,
        T_set_cool=T_cool,
        night_setback=False,
        calendar=calendar)

    T_m, T_i, T_s = _map_states_for_legacy(
        envelope,
        out["T_air"],
        out["T_s_iw"], out["T_m_iw"],
        out["T_s_aw"], out["T_m_aw"],
    )
    return (out["Q_H"], out["Q_C"], out["T_op"], T_m, T_i, T_s)


def calc_night_setback(envelope, T_e, calendar, dt, initial_day, building_type):
    """
    Calculate demand with night-setback-aware setpoint schedules.

    Parameters
    ----------
    envelope : object
        Prepared Envelope-like object required by :func:`simulate_7r2c`.
    T_e : array_like
        Outdoor air temperature time series in °C.
    calendar : dict
        Calendar definition passed to :func:`simulate_7r2c`. The key ``holidays``
        must contain zero-based simulation-day indices. Heating and cooling period
        keys required by :func:`simulate_7r2c` must also be present.
    dt : float
        Simulation time step in hours.
    initial_day : int
        Weekday index of the first simulation day, with Monday = 0 and Sunday = 6.
    building_type : str
        Building-type identifier used to construct residential or
        non-residential setpoint schedules.

    Returns
    -------
    Q_H : numpy.ndarray
        Non-negative heating demand in W.
    Q_C : numpy.ndarray
        Non-negative cooling demand in W.
    T_op : numpy.ndarray
        Operative temperature in °C.
    T_m : numpy.ndarray
        Legacy aggregated mass temperature in °C.
    T_i : numpy.ndarray
        Legacy indoor-air temperature in °C.
    T_s : numpy.ndarray
        Legacy aggregated surface temperature in °C.

    """
    T_e = np.asarray(T_e, dtype=float)
    n = len(T_e)

    holidays = calendar["holidays"]

    # Build setpoints like the old night-setback logic, honoring initial_day
    T_heat, T_cool = _build_setpoints_arrays(
        envelope=envelope, n=n, dt_h=dt,
        building_type=building_type, night_setback=True, holidays=holidays,
        initial_day=initial_day
    )
    theta_eq = getattr(envelope, "theta_eq_tot", None)
    out = simulate_7r2c(
        envelope=envelope,
        T_ext=T_e,
        dt_s=dt * 3600.0,
        theta_eq=theta_eq,
        T_set_heat=T_heat,
        T_set_cool=T_cool,
        night_setback=False,  # we've already embedded the setback into arrays
        calendar=calendar)

    T_m, T_i, T_s = _map_states_for_legacy(
        envelope,
        out["T_air"],
        out["T_s_iw"], out["T_m_iw"],
        out["T_s_aw"], out["T_m_aw"],
    )
    return (out["Q_H"], out["Q_C"], out["T_op"], T_m, T_i, T_s)
