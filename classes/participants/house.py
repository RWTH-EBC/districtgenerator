import gurobipy as gp
from .device import Device


class House(Device):
    """ House model """

    def __init__(self, model, ident, buildingData, site, cluster):
        """
        Constructor of House class.

        Parameters
        ----------
        model : gurobipy.Model
            Gurobi model of the optimization problem.
        ident : integer
            ID of the current building.
        buildingData : dictionary
            Data of the current building.
        site : dictionary
            Information about of the site of the district.
        cluster : integer
            ID of the currently considered cluster.

        Returns
        -------
        None.
        """

        super().__init__(model)

        # load building and cluster information
        self.id = ident
        self.data = buildingData
        self.cluster = cluster
        # add house variables and constrains to the optimization problem
        self.initializeParameters(site)
        self.setVariables()
        self.m.update()
        self.setConstraints()

    def initializeParameters(self, site):
        """
        Initialize global parameters and sets of energy conversion systems.

        Parameters
        ----------
        site : dictionary
            Information about of the site of the district.

        Returns
        -------
        None.
        """

        # Global parameters
        self.T_e = site["T_e_cluster"][self.cluster]  # ambient temperature [°C]
        self.Q_DHW = self.data["user"].dhw_cluster[self.cluster]  # DHW (domestic hot water) demand [W]
        self.Q_heating = self.data["user"].heat_cluster[self.cluster]  # space heating [W]
        self.generationPV = self.data["generationPV_cluster"][self.cluster]  # electricity generation of PV [W]
        self.generationSTC = self.data["generationSTC_cluster"][self.cluster]  # electricity generation of PV [W]
        self.occupants = self.data["user"].occ_cluster[self.cluster]  # number of occupants (active?) at home [-]
        self.demand_EV = self.data["user"].car_cluster[self.cluster]  # electricity demand electric vehicle (EV) [Wh]
        # electricity demand for appliances and lighting [W]
        self.elec_demand = self.data["user"].elec_cluster[self.cluster]

        # %% Sets of energy conversion systems
        # (simplifies creation of variables and constraints)
        # heat generation devices (heat pump (HP), electric heating (EH), combined heat and power (CHP), fuel cell (FC),
        #   boiler (BOI), solar thermal collector (STC))
        self.ecs_heat = ("HP", "EH", "CHP", "FC", "BOI", "STC")
        # power consuming/producing devices (photovoltaic (PV))
        self.ecs_power = ("HP", "EH", "CHP", "FC", "PV")
        # gas consuming devices
        self.ecs_gas = ("CHP", "FC", "BOI")
        self.ecs_storage = ("BAT", "TES", "EV")  # battery (BAT), thermal energy storage (TES), electric vehicle (EV)
        self.hp_modi = ("HP35", "HP55")  # modi of the HP with different HP supply temperatures in °C

    def setVariables(self):
        """
        Add the variables of the current house to the optimization problem.

        Returns
        -------
        None.
        """

        # %% Device specific variables:
        # Thermal power of devices
        self.heat = self.m.addVars(
            self.ecs_heat, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="Q_th_" + str(self.id)
        )

        # Electrical power of devices
        self.power = self.m.addVars(
            self.ecs_power, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="P_el_" + str(self.id)
        )

        # Chemical power of gas
        self.gas = self.m.addVars(
            self.ecs_gas, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="P_gas_" + str(self.id)
        )

        # Storage charging
        self.ch = self.m.addVars(
            self.ecs_storage, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="ch_" + str(self.id)
        )

        # Storage discharging
        self.dch = self.m.addVars(
            self.ecs_storage, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="dch_" + str(self.id)
        )

        # Storage SoC (state of charge)
        self.soc = self.m.addVars(
            self.ecs_storage, range(len(self.timesteps)+1),
            vtype=gp.GRB.CONTINUOUS, name="soc_" + str(self.id)
        )

        # %% Modus specific variables: Split HP in mode for HP35 and HP55
        # Thermal power in HP mode
        self.heat_mode = self.m.addVars(
            self.hp_modi, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="Q_th_" + str(self.id)
        )

        # Electrical power in HP mode
        self.power_mode = self.m.addVars(
            self.hp_modi, self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="P_el_" + str(self.id)
        )

        # %% Building specific variables:
        # Residual electricity load
        self.res_load = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="res_load_" + str(self.id)
        )

        # Residual electricity injection
        self.res_inj = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="res_inj_" + str(self.id)
        )

        # Residual gas demand
        self.res_gas = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS, name="res_gas_" + str(self.id)
        )

    def setConstraints(self):
        """
        Add the constraints of the current house to the optimization problem.

        Returns
        -------
        None.
        """

        # Maximum heating power of devices
        self.m.addConstrs(
            (self.heat[dev, t] <= self.data["capacities"][dev]
             for t in self.timesteps
             for dev in ("HP", "EH", "CHP", "FC", "BOI")),
            name="Max_heating_" + str(self.id))

        # Energy balances heat pump
        self.m.addConstrs(
            (self.heat["HP", t] == self.heat_mode["HP35", t] + self.heat_mode["HP55", t]
             for t in self.timesteps),
            name="Conversion_heat_" + str(self.id))

        self.m.addConstrs(
            (self.power["HP", t] == self.power_mode["HP35", t] + self.power_mode["HP55", t]
             for t in self.timesteps),
            name="Conversion_power_" + str(self.id))

        # Energy conversion heat pump modus
        self.m.addConstrs(
            (self.heat_mode["HP35", t] ==
             (self.power_mode["HP35", t] * self.devs["HP"]["grade"] * (273.15 + 40) / (40 - (self.T_e[t] - 5)))
             for t in self.timesteps),
            name="Conversion_HP35_" + str(self.id))

        # Energy conversion heat pump modus
        self.m.addConstrs(
            (self.heat_mode["HP55", t] ==
             (self.power_mode["HP55", t] * self.devs["HP"]["grade"] * (273.15 + 60) / (60 - (self.T_e[t] - 5)))
             for t in self.timesteps),
            name="Conversion_HP55_" + str(self.id))

        # Activity of HP modus: HP can only produce heat if modus is activated
        self.m.addConstrs(
            (self.heat_mode[dev, t] <= self.data["capacities"]["HP"]
             for t in self.timesteps
             for dev in self.hp_modi),
            name="Activity_mode_" + str(self.id))

        # Minimal EH for different HP modi concerning domestic hot water (DHW) temperature
        if self.data["envelope"].construction_year >= 1995 and self.data["capacities"]["HP"] > 0:

            # HP can only run in HP35 mode if building is new enough
            self.m.addConstrs(
                (self.heat_mode["HP55", t] == 0
                 for t in self.timesteps),
                name="Activity_mode_" + str(self.id))

            # If there's only 35 degree within TES, EH has to lift up temperature for DHW
            # todo: Speicher werden mit X l/kW auf T_max=60 ausgelegt. Vergleichbarkeit: X kWh/kW ?
            # cold water temperature of 10 °C; heatpump supply temperature of 35 °C; DHW temperature of 60 °C
            self.m.addConstrs(
                (self.heat["EH", t] >= (60 - 35) / (60 - 10) * self.Q_DHW[t]
                 for t in self.timesteps),
                name="DHW_EH_minimum_" + str(self.id))

        elif self.data["envelope"].construction_year < 1995 and self.data["capacities"]["HP"] > 0:

            # HP can only run in HP55 mode if building is too old
            self.m.addConstrs(
                (self.heat_mode["HP35", t] == 0
                 for t in self.timesteps),
                name="Activity_mode_" + str(self.id))

            # If there's only 35 degree within TES, EH has to lift up temperature for DHW
            # cold water temperature of 10 °C; heatpump supply temperature of 55 °C; DHW temperature of 60 °C
            self.m.addConstrs(
                (self.heat["EH", t] >= (60 - 55) / (60 - 10) * self.Q_DHW[t]
                 # * self.heat_mode["HP55", t] + (60 - 35) / (60 - 10) * self.heat_mode["HP35", t]
                 for t in self.timesteps),
                name="DHW_EH_minimum_" + str(self.id))

        # Energy conversion EH
        self.m.addConstrs(
            (self.power["EH", t] == self.heat["EH", t]
             for t in self.timesteps),
            name="Conversion_EH_" + str(self.id))

        # Energy conversion CHP
        self.m.addConstrs(
            (self.power["CHP", t] == self.gas["CHP", t] * self.devs["CHP"]["eta_el"]
             for t in self.timesteps),
            name="Conversion_CHP_el_" + str(self.id))

        self.m.addConstrs(
            (self.heat["CHP", t] == self.gas["CHP", t] * self.devs["CHP"]["eta_th"]
             for t in self.timesteps),
            name="Conversion_CHP_th_" + str(self.id))

        # Energy conversion BOI
        self.m.addConstrs(
            (self.heat["BOI", t] == self.gas["BOI", t] * self.devs["BOI"]["eta_th"]
             for t in self.timesteps),
            name="Conversion_BOI_" + str(self.id))

        # Energy conversion FC
        self.m.addConstrs(
            (self.power["FC", t] == self.gas["FC", t] * self.devs["FC"]["eta_el"]
             for t in self.timesteps),
            name="Conversion_BZ_el_" + str(self.id))

        self.m.addConstrs(
            (self.heat["FC", t] == self.gas["FC", t] * self.devs["FC"]["eta_th"]
             for t in self.timesteps),
            name="Conversion_BZ_th_" + str(self.id))

        # Maximum power PV
        self.m.addConstrs(
            (self.power["PV", t] <= self.generationPV[t]
             for t in self.timesteps),
            name="Max_power_PV_" + str(self.id))

        # Maximum heat STC
        self.m.addConstrs(
            (self.heat["STC", t] <= self.generationSTC[t]
             for t in self.timesteps),
            name="Max_heat_STC_" + str(self.id))

        # Maximum state of charge
        self.m.addConstrs(
            (self.soc[dev, t] <= self.data["capacities"][dev] * self.devs[dev]["soc_max"]
             for t in range(len(self.timesteps)+1)
             for dev in self.ecs_storage),
            name="Max_soc_" + str(self.id))

        # Minimum state of charge
        self.m.addConstrs(
            (self.soc[dev, t] >= self.data["capacities"][dev] * self.devs[dev]["soc_min"]
             for t in range(len(self.timesteps)+1)
             for dev in self.ecs_storage),
            name="Min_soc_" + str(self.id))

        # Maximum dis/charging power
        self.m.addConstrs(
            (self.ch[dev, t] <= self.data["capacities"][dev] * self.devs[dev]["coeff_ch"]
             for t in self.timesteps
             for dev in ("TES", "BAT")),
            name="Max_charging_" + str(self.id))

        self.m.addConstrs(
            (self.dch[dev, t] <= self.data["capacities"][dev] * self.devs[dev]["coeff_ch"]
             for t in self.timesteps
             for dev in ("TES", "BAT")),
            name="Max_discharging_" + str(self.id))

        # EV charging is only possible with defined power and if somebody is at home ;)
        occ = {}
        for t in self.timesteps:
            occ[t] = min(1, self.occupants[t])

        self.m.addConstrs(
            (self.ch["EV", t] <= self.devs["EV"]["ch_max"] * occ[t]
             for t in self.timesteps),
            name="Max_charging_EV_" + str(self.id))

        # EV is discharged by driving (demand in Wh)
        self.m.addConstrs(
            (self.dch["EV", t] == self.demand_EV[t] / self.dt
             for t in self.timesteps),
            name="Max_discharging_EV_" + str(self.id))

        # Initial SoC (for clustering last SOC equals initial SOC)
        self.m.addConstrs(
            (self.soc[dev, 0] == self.devs[dev]["init"] * self.data["capacities"][dev]
             for dev in self.ecs_storage),
            name="Storage_initial_" + str(self.id))

        # Storage at the end of period is the same as at the beginning
        self.m.addConstrs(
            (self.soc[dev, len(self.timesteps)] == self.soc[dev, 0]
             for dev in self.ecs_storage),
            name="Storage_cycle_" + str(self.id))

        # Storage balances
        self.m.addConstrs(
            (self.soc[dev, t + 1] == self.soc[dev, t]
             - (self.soc[dev, t] + self.soc[dev, t + 1]) / 2 * (1 - self.devs[dev]["eta_standby"])
             + self.dt * (self.ch[dev, t] * self.devs[dev]["eta_ch"] - self.dch[dev, t] / self.devs[dev]["eta_ch"])
             for t in self.timesteps
             for dev in self.ecs_storage),
            name="Storage_balance_" + str(self.id))

        # Heat balances
        self.m.addConstrs(
            (self.dch["TES", t] == self.Q_heating[t] + self.Q_DHW[t]
             for t in self.timesteps),
            name="Heat_balance_1_" + str(self.id))

        self.m.addConstrs(
            (sum(self.heat[dev, t] for dev in self.ecs_heat) == self.ch["TES", t]
             for t in self.timesteps),
            name="Heat_balance_2_" + str(self.id))

        # Electricity balance
        self.m.addConstrs(
            (self.res_load[t] + self.power["PV", t] + self.power["FC", t] + self.power["CHP", t] + self.dch["BAT", t]
             == self.res_inj[t] + self.elec_demand[t] + self.ch["BAT", t] + self.power["HP", t] + self.power["EH", t]
             + self.ch["EV", t]
             for t in self.timesteps),
            name="Power_balance_" + str(self.id))

        # Injection only from PV, CHP, FC, BAT
        # Todo: Check regulatory aspects of assumption
        self.m.addConstrs(
            (self.res_inj[t] <= self.power["PV", t] + self.power["CHP", t] + self.power["FC", t] + self.dch["BAT", t]
             for t in self.timesteps),
            name="Injection_limit_" + str(self.id))

        # Gas balance
        self.m.addConstrs(
            (self.res_gas[t] == self.gas["CHP", t] + self.gas["FC", t] + self.gas["BOI", t]
             for t in self.timesteps),
            name="Gas_balance_" + str(self.id))