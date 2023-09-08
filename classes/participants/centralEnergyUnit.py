import gurobipy as gp
from .device import Device


class CentralEnergyUnit(Device):
    """ Model of the central energy unit """

    def __init__(self, model, buildings, data, cluster):
        """
        Constructor of Central Energy Unit class.

        Parameters
        ----------
        model : gurobipy.Model
            Gurobi model of the optimization problem.
        buildings : integer
            Number of buildings in the district.
        data : data : Datahandler object
            Datahandler object which contains data.
        cluster : integer
            ID of the currently considered cluster.

        Returns
        -------
        None.
        """
        
        super().__init__(model)

        # load data
        self.buildings = buildings
        self.data = data
        self.cluster = cluster
        # add variables and constrains representing the central energy unit to the optimization problem
        self.initializeParameters()
        self.importVariables()
        self.setVariables()
        self.m.update()
        self.setConstraints()

    def initializeParameters(self):
        """
        Initialize parameters and sets of energy conversion systems.

        Returns
        -------
        None.
        """

        # %% Set of energy conversion systems
        # simplifies creation of variables and constraints
        # heat generation devices (heat pump with ambient air as source (HP_air),
        #   heat pump with earth as source (HP_air), electric heating (EH), combined heat and power (CHP),
        #   fuel cell (FC), boiler (BOI), solar thermal collector (STC))
        """
        self.ecs_heat = ("HP_air", "HP_geo", "EH", "CHP", "FC", "BOI", "STC")
        # power consuming/producing devices (photovoltaic (PV), wind turbine (WT))
        self.ecs_power = ("HP_air", "HP_geo", "EH", "CHP", "FC", "PV", "WT")
        # gas consuming devices
        self.ecs_gas = ("CHP", "FC", "BOI")
        # energy storages (battery (BAT), thermal energy storage (TES))
        self.ecs_storage = ("BAT", "TES")
        """
        self.ecs_heat = ("HP_air", "HP_geo", "EH", "CHP", "FC", "BOI")
        self.ecs_power = ("PV", "WT", "CHP", "FC", "HP_air", "HP_geo", "EH")
        self.ecs_gas = ("CHP", "FC", "BOI")
        self.ecs_storage = ("BAT", "TES")

        '''IDEAS:
        heat: solar-thermal energy
        storage: geo-thermal, hydrogen, central car park
        '''

        # Global parameters
        self.T_e = self.data.site["T_e_cluster"][self.cluster]  # ambient temperature [°C]

    def importVariables(self):
        """
        Import variables of the houses to use them in the constraints of the central energy unit.

        Returns
        -------
        None.

        """

        # heat demand of building connected to the local heat grid [W]
        self.Q_dem_heat = {}
        for n in range(self.buildings):
            self.Q_dem_heat[n] = {}
            for t in self.timesteps:
                self.Q_dem_heat[n][t] = self.m.getVarByName("Q_th_grid_" + str(n) + "[" + str(t) + "]")

    def setVariables(self):
        """
        Add the variables of the central energy unit to the optimization problem.

        Returns
        -------
        None.
        """
        
        # %% Specific variables for central devices:
        # Thermal power of central devices [W]
        self.heat = self.m.addVars(
            self.ecs_heat, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0, name="Q_th_centralDevices"
        )

        # Electrical power of central devices [W]
        self.power = self.m.addVars(
            self.ecs_power, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="P_el_centralDevices"
        )

        # Gas demand of central devices [W]
        self.gas = self.m.addVars(
            self.ecs_gas, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="P_gas_centralDevices"
        )

        # Charging of central storages [W]
        self.ch = self.m.addVars(
            self.ecs_storage, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="ch_centralDevices"
        )

        # Discharging of central storages [W]
        self.dch = self.m.addVars(
            self.ecs_storage, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="dch_centralDevices"
        )

        # State of charge of central storages [Wh]
        self.soc = self.m.addVars(
            self.ecs_storage, range(len(self.timesteps)+1),
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="soc_centralDevices"
        )

        # %% variables of central energy unit (all central devices)

        # Electricity demand of central energy unit [W]
        self.P_el_dem_centralUnit = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="P_el_dem_centralUnit"
        )

        # Electricity net injection of central energy unit [W]
        self.P_el_inj_centralUnit = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="P_el_inj_centralUnit"
        )

        # Gas demand of central energy unit [W]
        self.P_gas_dem_centralUnit = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="P_gas_dem_centralUnit"
        )

        # Heat supply of central energy unit [W]
        self.Heat_inj_centralUnit = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS, lb=0.0, name="Heat_inj_centralUnit"
        )

    def setConstraints(self):
        """
        Add the constraints of the central energy unit to the optimization problem.

        Returns
        -------
        None.
        """
        
        ##################################################################################
        # %% energy conversion of central devices

        # Maximum heating power of devices
        self.m.addConstrs(
            (self.heat[dev, t] <= self.data.centralDevices["capacities"][dev]
             for t in self.timesteps
             for dev in self.ecs_heat),
            name="Max_heating_centralDevices")

        self.m.addConstrs(
            (self.heat[dev, t] >= 0
             for t in self.timesteps
             for dev in self.ecs_heat),
            name="Min_heating_centralDevices")

        # HP air
        T_grid_flow = self.heatGrid["T_hot"]  # flow temperature of heat grid [K]
        delta_T = self.heatGrid["delta_T_heatTransfer"]  # minimal temperature difference of heat exchangers [K]
        self.m.addConstrs(
            (self.heat["HP_air", t] ==
             (self.power["HP_air", t] * self.data.centralDevices["data"]["HP_air"]["grade"]
              * (T_grid_flow + delta_T) / ((T_grid_flow + delta_T) - (273.15 + self.T_e[t] - delta_T)))
             for t in self.timesteps),
            name="Conversion_central_HP_air")

        # EH
        self.m.addConstrs(
            (self.heat["EH", t] == self.power["EH", t] * self.data.centralDevices["data"]["EH"]["eta_th"]
             for t in self.timesteps),
            name="Conversion_central_EH")

        # HP geo
        T_ground = self.data.centralDevices["data"]["HP_geo"]["T_geo"]  # constant temperature in the ground [°C]
        self.m.addConstrs(
            (self.heat["HP_geo", t] ==
             (self.power["HP_geo", t] * self.data.centralDevices["data"]["HP_geo"]["grade"]
              * (T_grid_flow + delta_T) / ((T_grid_flow + delta_T) - (273.15 + T_ground - delta_T)))
             for t in self.timesteps),
            name="Conversion_central_HP_geo")

        # CHP
        self.m.addConstrs(
            (self.heat["CHP", t] == self.gas["CHP", t] * self.data.centralDevices["data"]["CHP"]["eta_th"]
             for t in self.timesteps),
            name="Conversion_central_CHP_th")

        self.m.addConstrs(
            (self.power["CHP", t] == self.gas["CHP", t] * self.data.centralDevices["data"]["CHP"]["eta_el"]
             for t in self.timesteps),
            name="Conversion_central_CHP_el")

        # FC
        self.m.addConstrs(
            (self.heat["FC", t] == self.gas["FC", t] * self.data.centralDevices["data"]["FC"]["eta_th"]
             for t in self.timesteps),
            name="Conversion_central_FC_th")

        self.m.addConstrs(
            (self.power["FC", t] == self.gas["FC", t] * self.data.centralDevices["data"]["FC"]["eta_el"]
             for t in self.timesteps),
            name="Conversion_central_FC_el")

        # BOI
        self.m.addConstrs(
            (self.heat["BOI", t] == self.gas["BOI", t] * self.data.centralDevices["data"]["BOI"]["eta_th"]
             for t in self.timesteps),
            name="Conversion_central_BOI")

        # STC
        #self.m.addConstrs(
        #    (self.heat["STC", t] <=
        #     self.data.centralDevices["renewableGeneration"]["centralSTC_cluster"][self.cluster][t]
        #     for t in self.timesteps),
        #    name="Heat_STC_central")

        # PV
        self.m.addConstrs(
            (self.power["PV", t] <=
             self.data.centralDevices["renewableGeneration"]["centralPV_cluster"][self.cluster][t]
             for t in self.timesteps),
            name="Power_PV_central")

        # WT
        self.m.addConstrs(
            (self.power["WT", t] ==
             self.data.centralDevices["renewableGeneration"]["centralWT_cluster"][self.cluster][t]
             for t in self.timesteps),
            name="Power_WT_central")

        ##################################################################################
        # %% storage equations
        '''Added one extra value for SoC -> values for points in time NOT for each time interval'''

        # Maximum state of charge
        self.m.addConstrs(
            (self.soc[dev, t] <=
             self.data.centralDevices["capacities"][dev] * self.data.centralDevices["data"][dev]["soc_max"]
             for t in range(len(self.timesteps)+1)
             for dev in self.ecs_storage),
            name="Max_soc_centralUnit")

        # Minimum state of charge
        self.m.addConstrs(
            (self.soc[dev, t] >=
             self.data.centralDevices["capacities"][dev] * self.data.centralDevices["data"][dev]["soc_min"]
             for t in range(len(self.timesteps)+1)
             for dev in self.ecs_storage),
            name="Min_soc_centralUnit")

        # Maximum charging power for BAT
        self.m.addConstrs(
            (self.ch["BAT", t] <=
             self.data.centralDevices["capacities"]["BAT"] * self.data.centralDevices["data"]["BAT"]["coeff_ch"]
             for t in self.timesteps),
            name="Max_charging_centralUnit")

        # Maximum discharging power for BAT
        self.m.addConstrs(
            (self.dch["BAT", t] <=
             self.data.centralDevices["capacities"]["BAT"] * self.data.centralDevices["data"]["BAT"]["coeff_ch"]
             for t in self.timesteps),
            name="Max_discharging_centralUnit")

        # Initial SoC
        self.m.addConstrs(
            (self.soc[dev, 0] ==
             self.data.centralDevices["data"][dev]["init"] * self.data.centralDevices["capacities"][dev]
             for dev in self.ecs_storage),
            name="Storage_initial_centralUnit")

        # Storage at the end of period is the same as at the beginning (because of clustering)
        self.m.addConstrs(
            (self.soc[dev, len(self.timesteps)-1] == self.soc[dev, 0]
             for dev in self.ecs_storage),
            name="Storage_cycle_centralUnit")

        # Storage balances central energy unit
        # soc for len(self.timesteps)+1 POINTS IN TIME; ch and dch for len(self.timesteps) TIME INTERVALS
        #self.m.addConstrs(
        #    (self.soc[dev, t + 1] == self.soc[dev, t]
        #     - (self.soc[dev, t] + self.soc[dev, t + 1]) / 2 * (1 - self.data.centralDevices["data"][dev]["eta_standby"])
        #     + self.dt * (self.ch[dev, t] * self.data.centralDevices["data"][dev]["eta_ch"]
        #                  - self.dch[dev, t] / self.data.centralDevices["data"][dev]["eta_ch"])
        #     for t in self.timesteps
        #     for dev in self.ecs_storage),
        #    name="Storage_balance_centralUnit")

        # Energy balance central TES
        for t in self.timesteps:
            if t == 0:
                # Initial SoC
                soc_prev = self.data.centralDevices["data"]["TES"]["init"] * self.data.centralDevices["capacities"]["TES"]
            else:
                soc_prev =  self.soc["TES", t - 1]
            self.m.addConstr(
                self.soc["TES", t] == soc_prev * self.data.centralDevices["data"]["TES"]["eta_standby"]
                + self.dt * (self.ch["TES", t] * self.data.centralDevices["data"]["TES"]["eta_ch"]
                             - self.dch["TES", t] / self.data.centralDevices["data"]["TES"]["eta_ch"]),

            name="Storage_balance_centralTES")

        # Energy balance central BAT
        for t in self.timesteps:
            if t == 0:
                # Initial SoC
                soc_prev = self.data.centralDevices["data"]["BAT"]["init"] * self.data.centralDevices["capacities"]["BAT"]
            else:
                soc_prev = self.soc["BAT", t - 1]
            self.m.addConstr(
                self.soc["BAT", t] == soc_prev * self.data.centralDevices["data"]["BAT"]["eta_standby"]
                + self.dt * (self.ch["BAT", t] * self.data.centralDevices["data"]["BAT"]["eta_ch"]
                             - self.dch["BAT", t] / self.data.centralDevices["data"]["BAT"]["eta_ch"]),

                name="Storage_balance_centralBAT")

        ##################################################################################
        # %% central energy unit (all central devices)

        # Cumulated demand of heat grid
        #self.m.addConstrs(
        #    (self.Q_dem_heatGrid_total[t] == sum(self.Q_dem_heat[n][t] for n in range(self.buildings))
        #    for t in self.timesteps),
        #    name="Cumulated_heatGrid_dem")

        # Charging of central TES
        self.m.addConstrs(
            (sum(self.heat[dev, t] for dev in self.ecs_heat) == self.ch["TES", t]
             for t in self.timesteps),
            name="Charging_centralTES")

        # Discharging of central TES / Cummulated heat supply of central energy units
        self.m.addConstrs(
            (self.dch["TES", t] == self.Heat_inj_centralUnit[t]
             for t in self.timesteps),
            name="Discharging_centralTES")

        # Cummulated heat supply of central energy units
        #self.m.addConstrs(
        #    (self.Heat_inj_centralUnit[t] == sum(self.heat[dev, t] for dev in self.ecs_heat)
        #     for t in self.timesteps),
        #    name="Heat_inj_centralUnit")

        # Electricity balances of central energy unit
        self.m.addConstrs(
            (self.P_el_dem_centralUnit[t] + self.dch["BAT", t] + self.power["PV", t] + self.power["WT", t]
             + self.power["CHP", t] + self.power["FC", t]
             == self.P_el_inj_centralUnit[t] + self.ch["BAT", t] + self.power["HP_air", t] + self.power["HP_geo", t]
             + self.power["EH", t]
             for t in self.timesteps),
            name="Power_balance_centralUnit")
        #self.m.addConstrs(
        #    (self.P_el_dem_centralUnit[t] + self.power["PV", t] + self.power["WT", t] + self.power["CHP", t]
        #     + self.dch["BAT", t] ==
        #     self.P_el_inj_centralUnit[t] + self.ch["BAT", t] + self.power["HP_air", t] + self.power["HP_geo", t]
        #     + self.power["EH", t]
        #     for t in self.timesteps),
        #    name="Power_balance_centralUnit")

        # Gas balances of central energy unit
        self.m.addConstrs(
            (self.P_gas_dem_centralUnit[t] == self.gas["CHP", t] + self.gas["BOI", t] + self.gas["FC", t]
             for t in self.timesteps),
            name="Gas_dem_centralUnit")