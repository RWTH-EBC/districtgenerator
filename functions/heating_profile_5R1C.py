# -*- coding: utf-8 -*-
"""
Script to generate heating and cooling demands sccording to DIN EN ISO 13790.
"""

from __future__ import division
import numpy as np
import numpy.linalg as linalg

def _solve(A, b):
    return linalg.solve(A,b)

def _calculateNoHeat(self, zone, zoneParameters, zoneInputs, T_m_init, timestep=0):
    """
    Calculate the temperatures (T_op, T_m, T_air, T_s) if neither heating nor
    cooling devices are activated. 
    This is necessary to enable a deadband between cooling and heating mode.
    
    Parameters
    ----------
    zoneParameters : ZoneParameters
        Resistances and capacity
    zoneInputs : ZoneInputs
        External inputs (solar, internal gains, set temperatures)
    T_m_init : float
        Initial temperature of the thermal mass in degree Celsius.
    timestep : integer, optional
        Define which index is relevant (zoneInputs, H_ve)
        
    Returns
    -------
    T_op : float
        .
    T_m : float
        .
    T_air : float
        .
    T_s : float
        .
    """
    
    # Note: If not stated differently, all equations, pages and sections
    # refer to DIN EN ISO 13790:2008 (the official German version of 
    # ISO 13790:2008).
    
    # Extract parameters
    A_m     = zoneParameters.A_m            # in m2
    A_t     = zoneParameters.A_t            # in m2
    H_tr_is = zoneParameters.H_tr_is        # in W/K
    H_tr_ms = zoneParameters.H_tr_ms        # in W/K
    H_tr_w  = zoneParameters.H_tr_w         # in W/K
    H_ve    = zoneParameters.H_ve[timestep] # in W/K
    C_m     = zoneParameters.C_m            # in J/K
    if np.size(zoneParameters.H_tr_em) > 1:
        H_tr_em = zoneParameters.H_tr_em [timestep] # in W/K
    else:
        H_tr_em = zoneParameters.H_tr_em            # in W/K

    dt      = zoneParameters.samplingRate # in s
    
    Phi_int = zoneInputs.Phi_int[timestep]
    Phi_sol = zoneInputs.Phi_sol[timestep]
    T_e     = zoneInputs.T_e[timestep]
    T_sup   = zoneInputs.T_sup[timestep]
    
    # Compute internal and solar heat sources
    # Equations C1-C3, section C2, page 110
    Phi_ia = 0.5 * Phi_int
    Phi_m  = A_m / A_t * (0.5 * Phi_int + Phi_sol)
    Phi_st = (1 - A_m / A_t - H_tr_w / (9.1 * A_t)) * (0.5 * Phi_int + Phi_sol)
    
    # Initialize A*x = b
    # x: T_m, T_s, T_air (T_i), Q_HC
    A = np.zeros((3,3))
    b = np.zeros(3)
    
    # Row wise entering
    A[0,0] = H_tr_em + H_tr_ms + C_m / dt
    A[0,1] = - H_tr_ms
    A[1,0] = - H_tr_ms
    A[1,1] = H_tr_ms + H_tr_is + H_tr_w
    A[1,2] = - H_tr_is
    A[2,1] = - H_tr_is
    A[2,2] = H_ve + H_tr_is
    
    b[0] = Phi_m + H_tr_em * T_e + C_m * T_m_init / dt
    b[1] = Phi_st + H_tr_w * T_e
    b[2] = Phi_ia + H_ve * T_sup

    # Solve for "x"
    x = _solve(A, b)
    
    T_i = x[2]
    T_s = x[1]
    T_m = x[0]
        
    weight = 0.3
    T_op = weight * T_i + (1 - weight) * T_s
    return (T_op, T_m, T_i, T_s)
    
    
def _calculateHeat(self, zone, zoneParameters, zoneInputs, T_m_init, T_set, timestep=0):
    """
    Calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s) that result when
    reaching a given set temperature T_set. 
    
    Parameters
    ----------
    zoneParameters : ZoneParameters
        Resistances and capacity
    zoneInputs : ZoneInputs
        External inputs (solar, internal gains, set temperatures)
    T_m_init : float
        Initial temperature of the thermal mass in degree Celsius.
    T_set : float
        Set temperature in degree Celsius.
    timestep : integer, optional
        Define which index is relevant (zoneInputs, H_ve)
        
    Returns
    -------
    Q_HC : float
        Heating (positive) or cooling (negative) load for the current time 
        step in Watt.
    T_op : float
        .
    T_m : float
        .
    T_air : float
        .
    T_s : float
        .
    """
    
    # Note: If not stated differently, all equations, pages and sections
    # refer to DIN EN ISO 13790:2008 (the official German version of 
    # ISO 13790:2008).
    
    # Extract parameters
    A_m     = zoneParameters.A_m            # in m2
    A_t     = zoneParameters.A_t            # in m2
    H_tr_is = zoneParameters.H_tr_is        # in W/K
    H_tr_ms = zoneParameters.H_tr_ms        # in W/K
    H_tr_w  = zoneParameters.H_tr_w         # in W/K
    H_ve    = zoneParameters.H_ve[timestep] # in W/K
    C_m     = zoneParameters.C_m            # in J/K
    if np.size(zoneParameters.H_tr_em) > 1:
        H_tr_em = zoneParameters.H_tr_em [timestep] # in W/K
    else:
        H_tr_em = zoneParameters.H_tr_em            # in W/K

    dt      = zoneParameters.samplingRate # in s
    
    Phi_int = zoneInputs.Phi_int[timestep]
    Phi_sol = zoneInputs.Phi_sol[timestep]
    T_e     = zoneInputs.T_e[timestep]
    T_sup   = zoneInputs.T_sup[timestep]
    
    # Compute internal and solar heat sources
    # Equations C1-C3, section C2, page 110
    Phi_ia = 0.5 * Phi_int
    Phi_m  = A_m / A_t * (0.5 * Phi_int + Phi_sol)
    Phi_st = (1 - A_m / A_t - H_tr_w / (9.1 * A_t)) * (0.5 * Phi_int + Phi_sol)

    # Initialize A*x = b
    # x: T_m, T_s, T_air (T_i), Q_HC
    A = np.zeros((4,4))
    b = np.zeros(4)
    
    # Row wise entering
    A[0,0] = H_tr_em + H_tr_ms + C_m / dt
    A[0,1] = - H_tr_ms
    A[1,0] = - H_tr_ms
    A[1,1] = H_tr_ms + H_tr_is + H_tr_w
    A[1,2] = - H_tr_is
    A[2,1] = - H_tr_is
    A[2,2] = H_ve + H_tr_is
    A[2,3] = -1
    A[3,2] = 0.3
    A[3,1] = 1 - A[3,2]  
    
    b[0] = Phi_m + H_tr_em * T_e + C_m * T_m_init / dt
    b[1] = Phi_st + H_tr_w * T_e
    b[2] = Phi_ia + H_ve * T_sup
    b[3] = T_set

    # Solve for "x"
    x = _solve(A, b)

    # Linear system of equations to determine T_i, T_s, T_m, Q_HC (in kW)
    # compare (Michalak - 2014 - The simple hourly method of EN ISO 13790)
    # Using T_i instead of T_op for temperature control

    T_i  = x[2]
    T_s  = x[1]
    T_m  = x[0]
    Q_HC = x[3]
        
    weight = 0.3
    T_op = weight * T_i + (1 - weight) * T_s
    return (Q_HC, T_op, T_m, T_i, T_s)
   
   
def calc(zoneParameters, zoneInputs, T_m_init, TCoolingSet, THeatingSet,
         beQuiet=False):
    """
    """
    numberTimesteps = len(zoneInputs.T_e)

    # Initialize results
    T_i  = np.zeros(numberTimesteps)
    T_s  = np.zeros(numberTimesteps)
    T_m  = np.zeros(numberTimesteps)
    Q_H = np.zeros(numberTimesteps)
    Q_C = np.zeros(numberTimesteps)
    
    for t in range(numberTimesteps):

        if t == 0:
            t_previous = T_m_init
        else:
            t_previous = T_m[t-1]
        
        # Compute what happens without heating (deadband)
        (t_op, t_m, t_i, t_s) = _calculateNoHeat(zoneParameters,
                                                 zoneInputs, 
                                                 t_previous,
                                                  timestep=t)
        
        
        ##Original
        
        if t_op < THeatingSet[t]:
            # Compute heat demand
            (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                          zoneInputs, 
                                                          t_previous, 
                                                          THeatingSet[t], 
                                                          timestep=t)
        elif t_op > TCoolingSet[t]:
            # Compute cooling demand
            (q_hc, t_op, t_m, t_i, t_s) = _calculateHeat(zoneParameters,
                                                          zoneInputs, 
                                                          t_previous, 
                                                          TCoolingSet[t], 
                                                          timestep=t)
        else:
            # Nothing to do
            q_hc = 0
    
        # Insert results for current time step
        if q_hc >=0:
            Q_H[t] = q_hc
            Q_C[t] = 0
        elif q_hc <0:
            Q_C[t] = q_hc
            Q_H[t] = 0
        T_m[t]  = t_m
        T_i[t]  = t_i
        T_s[t]  = t_s
    
    T_op = 0.3 * T_i + 0.7 * T_s
    
    return (Q_H, Q_C, T_op, T_m, T_i, T_s)


def calculate(zoneParameters, T_set, T_e, dt):
    """
    
    Parameters
    ----------
    zoneParameters : ZoneParameters
        Resistances and capacity
    zoneInputs : ZoneInputs
        External inputs (solar, internal gains, set temperatures)
    T_m_init : float
        Initial temperature of the thermal mass in degC
    """

    T_m_init = 20 #[°C]
    #T_set = zoneParameters.T_set_min

    
    # Note: If not stated differently, all equations, pages and sections
    # refer to DIN EN ISO 13790:2008 (the official German version of 
    # ISO 13790:2008).
    
    # Extract parameters
    H_tr_is = zoneParameters.H_tr_is    # in W/K
    H_tr_ms = zoneParameters.H_tr_ms    # in W/K
    H_tr_em = zoneParameters.H_tr_em[0]    # in W/K
    H_tr_w  = zoneParameters.H_tr_w     # in W/K
    H_ve    = zoneParameters.H_ve       # in W/K
    C_m     = zoneParameters.C_m        # in J/K

    T_sup   = T_e   #zoneInputs.T_sup
    
    numberTimesteps = len(T_e)
    
    # Compute internal and solar heat sources
    # Equations C1-C3, section C2, page 110
    Phi_ia = zoneParameters.phi_ia
    Phi_m  = zoneParameters.phi_m
    Phi_st = zoneParameters.phi_st
    
    # Initialize results
    T_i  = np.zeros(numberTimesteps)
    T_s  = np.zeros(numberTimesteps)
    T_m  = np.zeros(numberTimesteps)
    Q_HC = np.zeros(numberTimesteps)
    

    # Initialize A*x = b
    # x: T_m, T_s, T_air (T_i), Q_HC
    A = np.zeros((4,4))
    b = np.zeros(4)    
    
    # Row wise entering
    # Set the time-invariant components of A
    A[0,0] = H_tr_em + H_tr_ms + C_m / (3600 * dt)
    A[0,1] = - H_tr_ms
    A[1,0] = - H_tr_ms
    A[1,1] = H_tr_ms + H_tr_is + H_tr_w
    A[1,2] = - H_tr_is
    A[2,1] = - H_tr_is
    A[2,3] = -1
    # if A[3,2] = 1 T_i is used for temperature control. Otherwise T_e is used! -> check MA Dominik
    A[3,2] = 1 # 0.3
    A[3,1] = 1 - A[3,2]    
    
    # Only the right hand side (b) changes. This is done for each time step:
    for t in range(numberTimesteps):
        if t == 0:
            T_m_previous = T_m_init
        else:
            T_m_previous = T_m[t-1]
        
        # Set the time-variable components of A
        A[2,2] = H_ve + H_tr_is
        
        b[0] = Phi_m[t] + H_tr_em * T_e[t] + C_m * T_m_previous / (3600 * dt)
        b[1] = Phi_st[t] + H_tr_w * T_e[t]
        b[2] = Phi_ia[t] + H_ve * T_sup[t]
        b[3] = T_set
        
        # Solve for "x"
        x = _solve(A, b)
        
        T_i[t] = x[2]
        T_s[t] = x[1]
        T_m[t] = x[0]
        Q_HC[t] = x[3]
        
    T_op = A[3,2] * T_i + A[3,1] * T_s
    return (Q_HC, T_i, T_s, T_m, T_op)