# -*- coding: utf-8 -*-
"""
VDI 6007–inspired 5-node dynamic zone solver (Backward Euler).

Nodes: Air, IW_surface, IW_mass, AW_surface, AW_mass.
Resistances: Air↔IW (RalphaStarIW), Air↔AW (RalphaStarAW),
             IW_surface↔IW_mass (R1IW), AW_surface↔AW_mass (R1AW),
             AW_mass↔outside (RrestAW via θ_eq/T_ext).

Requirements:
- Provide an Envelope instance that has already run:
    envelope._VDI6007_params(...)
    envelope.calcNormativeProperties(...)
  so that R*, C*, θ_eq and gain time series are available on the Envelope.
- The solver itself does NOT take SunRad/internal_gains as arguments; those are
  already embedded in the Envelope (e.g., theta_eq_tot, Q_il_kon, Q_il_str).

Assumptions:
- No mechanical supply air; the air balance uses infiltration only (H_ve).
- Heating/cooling acts with an optional split (sigma) across air and surfaces.
- Control is by operative temperature unless otherwise noted.
"""

from typing import Dict, Optional, Tuple
import numpy as np


def _area_fraction_aw(envelope) -> float:
    Araum = max(float(getattr(envelope, "Araum_tot", 0.0)), 1e-12)
    Aaw   = float(getattr(envelope, "Aaw_tot", 0.0))
    return float(np.clip(Aaw / Araum, 0.0, 1.0))

def _radiative_split_weights(envelope) -> float:
    """
    Return f_aw = fraction of *radiant* internal gains that should hit AW.
    It uses area × h_rad on the room-side for each surface.
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
    Build the solver parameter dict from an Envelope instance.

    Parameters
    ----------
    envelope : Envelope
        Your Envelope instance (after calling _VDI6007_params and calcNormativeProperties).
    dt_s : float
        Timestep [s].

    Returns
    -------
    dict
        Keys:
        - C1IW, C1AW    [J/K] (zone heat capacities for IW and AW)
        - C_air         [J/K] (small air capacity; optional, derived)
        - RalphaStarIW, RalphaStarAW  [K/W]
        - R1IW, R1AW, RrestAW  [K/W]
        - H_ve          [W/K] (ventilation conductance)
        - UA_tot        [W/K]
        - areas: Aaw_tot, Araum_tot
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
    H_ve = float(envelope.rho_air) * float(envelope.c_p_air) * float(envelope.ventilationRate) * float(envelope.V) / 3600.0

    # A tiny air capacity for numerical stability (or scale with volume)
    # Rule of thumb: ~ 1.2 kJ/K per m² zone floor area
    C_air = float(envelope.rho_air) * float(envelope.c_p_air) * float(envelope.V)  # J/K

    return dict(
        C1IW=float(envelope.C1IW),
        C1AW=float(envelope.C1AW),
        C_air=float(C_air),

        RalphaStarIW=float(envelope.RalphaStarIW),
        RalphaStarAW=float(envelope.RalphaStarAW),

        R1IW=float(envelope.R1IW),
        R1AW=float(envelope.R1AW),
        RrestAW=float(envelope.RrestAW),

        H_ve=float(H_ve),
        UA_tot=float(envelope.UA_tot),

        Aaw_tot=float(envelope.Aaw_tot),
        Araum_tot=float(envelope.Araum_tot),

        dt=float(dt_s),
    )

def prepare_gains_from_envelope(envelope,
                                rad_frac: float = 0.60) -> Dict[str, np.ndarray]:
    """
      Build 7R2C gains time series:
      - Q_il_kon_I : convective to air [W]  (solar + non-solar)
      - Q_il_str_iw: radiant to IW [W]      (solar + non-solar, split)
      - Q_il_str_aw: radiant to AW [W]      (solar + non-solar, split)

    Uses solar gains from envelope.calc_theta_eq():
      envelope.Q_il_kon, envelope.Q_il_str

    Adds non-solar internal gains (people/equipment/lighting) either from:
      - 'internal_gains' argument, or
      - envelope.internal_gains (if argument is None)

    'internal_gains' can be:
      { "Q_int_str": array_like, "Q_int_kon": array_like }   # already split
      or
      { "Q_int": array_like, "rad_frac": float }             # total + split
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

    return dict(
        Q_il_kon_I=Q_kon_total,
        Q_il_str_iw=Q_il_str_iw,
        Q_il_str_aw=Q_il_str_aw,
    )


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
    5-node BE step without HVAC.
    Unknowns: [T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw]
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
    Enforce T_op = T_set, with HVAC split:
      sigma = (σ_iw_rad, σ_aw_rad, σ_conv_air)
    Unknowns: [T_air, T_s_iw, T_m_iw, T_s_aw, T_m_aw, Q_HC]
    NOTE: If you want AIR setpoint instead, replace the constraint row by:
          [1, 0, 0, 0, 0, 0] and RHS = T_set.
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

def simulate_7r2c(envelope,
                  T_ext: np.ndarray,
                  dt_s: float,
                  theta_eq: Optional[np.ndarray] = None,
                  T_set_heat: Optional[np.ndarray] = None,
                  T_set_cool: Optional[np.ndarray] = None,
                  cooling_season_days: Tuple[int, int] = (145, 255),
                  w_op: float = 0.5,
                  night_setback: bool = False,
                  calendar: Optional[Dict] = None):
    """
Run a simulation with the 5-node model (Air + IW_s + IW_m + AW_s + AW_m).

Parameters
----------
envelope : Envelope
    Envelope with VDI-6007 parameters/gains already computed
    (R*, C*, theta_eq_tot, Q_il_kon, Q_il_str, setpoints, etc.).
T_ext : array_like [°C]
    Outdoor dry-bulb temperature time series.
dt_s : float
    Time step in seconds.
theta_eq : array_like [°C], optional
    Equivalent exterior temperature for AW (sol-air). If None, falls back to T_ext.
T_set_heat : array_like [°C], optional
    Heating setpoint (operative). Defaults to envelope.T_set_min if None.
T_set_cool : array_like [°C], optional
    Cooling setpoint (operative). Defaults to envelope.T_set_max if None.
cooling_season_days : tuple(int, int), default (145, 255)
    Inclusive DOY window when cooling is allowed.
w_op : float, default 0.5
    Operative weighting: T_op = w_op*T_air + (1-w_op)*T_s,
    where T_s is the area-weighted interior surface temperature.
night_setback : bool, default False
    If True, applies the envelope’s night setpoints to the setpoint arrays.
calendar : dict, optional  # ADDED
    If provided, overrides heating/cooling enable seasons using:
      heating_period_start, heating_period_end, consider_heating_period
      cooling_period_start, cooling_period_end, consider_cooling_period

Returns
-------
dict[str, np.ndarray]
    'Q_H'   [W]  heating (+),
    'Q_C'   [W]  cooling (+),
    'T_op'  [°C] operative temperature,
    'T_air' [°C] air node,
    'T_s_iw' [°C] IW surface, 'T_m_iw' [°C] IW mass,
    'T_s_aw' [°C] AW surface, 'T_m_aw' [°C] AW mass.
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
    dt_s = dt_h * 3600.0
    steps_per_day = int(round(86400.0 / dt_s))
    T_heat = np.full(n, float(envelope.T_set_min), dtype=float)
    T_cool = np.full(n, float(envelope.T_set_max), dtype=float)

    if building_type in {"SFH", "TH", "MFH", "AB"}:
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
    Returns (Q_H, Q_C, T_op, T_m, T_i, T_s).

    Parameters
    ----------
    initial_day : int
        Day-of-week index for the first time step (0=Monday, …, 6=Sunday).
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
    Returns (Q_H, Q_C, T_op, T_m, T_i, T_s).

    Parameters
    ----------
    initial_day : int
        Day-of-week index for the first time step (0=Monday, …, 6=Sunday).
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
