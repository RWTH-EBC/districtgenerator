import gurobipy as gp
from .device import Device


class Aggregator(Device):
    """ Switch Unit model """

    def __init__(self, model, buildings):
        """
        Constructor of Aggregator class.

        Parameters
        ----------
        model : gurobipy.Model
            Gurobi model of the optimization problem.
        buildings : integer
            Number of buildings in the district.

        Returns
        -------
        None.
        """

        super().__init__(model)

        self.buildings = buildings
        self.initializeParameters()
        self.importVariables()
        self.setVariables()
        self.m.update()
        self.setConstraints()

    def initializeParameters(self):
        """
        Initialize parameters.

        Returns
        -------
        None.
        """
        
        self.C_feed_in_elec = self.ecoData["C_feed_electricity"]
        self.C_dem_elec = self.ecoData["C_dem_electricity"]
        self.C_dem_gas = self.ecoData["C_dem_gas"]
        self.Emission_factor_elec = self.ecoData["Emi_elec"]
        self.Emission_factor_gas = self.ecoData["Emi_gas"]

    def importVariables(self):
        """
        Import the variables of the houses to use them in the constraints of the aggregator.

        Returns
        -------
        None.
        """

        self.P_dem, self.P_inj, self.P_gas = {}, {}, {}
        for n in range(self.buildings):
            self.P_dem[n], self.P_inj[n], self.P_gas[n] = {}, {}, {}
            for t in self.timesteps:
                self.P_dem[n][t] = self.m.getVarByName("res_load_" + str(n) + "[" + str(t) + "]")
                self.P_inj[n][t] = self.m.getVarByName("res_inj_" + str(n) + "[" + str(t) + "]")
                self.P_gas[n][t] = self.m.getVarByName("res_gas_" + str(n) + "[" + str(t) + "]")

    def setVariables(self):
        """
        Add the variables of the aggregator to the optimization problem.

        Returns
        -------
        None.
        """

        # Cumulated electricity demand
        self.P_dem_total = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="P_dem_total"
        )

        # Cumulated electricity injection
        self.P_inj_total = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="P_inj_total"
        )

        # Cumulated gas demand
        self.P_gas_total = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="P_gas_total"
        )

        # District electricity demand at GCP (grid connection point)
        self.P_dem_gcp = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="P_dem_gcp"
        )

        # District electricity injection at GCP
        self.P_inj_gcp = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="P_inj_gcp"
        )

        # Total costs (profit - costs)
        self.C_total_central = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=-gp.GRB.INFINITY,
            name="C_total_central"
        )

        self.C_total_decentral = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=-gp.GRB.INFINITY,
            name="C_total_decentral"
        )

        # Building costs (profit - costs)
        self.C_building = self.m.addVars(
            self.buildings, self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=-gp.GRB.INFINITY,
            name="C_building"
        )

        # Total emissions (no revenue for feed in)
        self.Emi_total_central = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=-gp.GRB.INFINITY,
            name="Emi_total_central"
        )

        self.Emi_total_decentral = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=-gp.GRB.INFINITY,
            name="Emi_total_decentral"
        )

        # Total emissions (no revenue for feed in)
        self.Emi_building = self.m.addVars(
            self.buildings, self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=-gp.GRB.INFINITY,
            name="Emi_building"
        )

        # Positiv peak at GCP (demand)
        self.P_peak_pos = self.m.addVar(
            vtype=gp.GRB.CONTINUOUS,
            name="Peak_pos_gcp"
        )

        # Negative peak at GCP (injection)
        self.P_peak_neg = self.m.addVar(
            vtype=gp.GRB.CONTINUOUS,
            name="Peak_neg_gcp"
        )

    def setConstraints(self):
        """
        Add the constraints of the aggregator to the optimization problem.

        Returns
        -------
        None.
        """

        # Cumulated demand
        for t in self.timesteps:
            self.m.addConstr(
                self.P_dem_total[t],
                gp.GRB.EQUAL,
                sum(self.P_dem[n][t] for n in range(self.buildings)),
                name="Cumulated_dem" + str(t)
            )

        # Cumulated injection
        for t in self.timesteps:
            self.m.addConstr(
                self.P_inj_total[t],
                gp.GRB.EQUAL,
                sum(self.P_inj[n][t] for n in range(self.buildings)),
                name="Cumulated_inj" + str(t)
            )

        # Balance of total incoming and outgoing power
        for t in self.timesteps:
            self.m.addConstr(
                self.P_dem_gcp[t] - self.P_inj_gcp[t],
                gp.GRB.EQUAL,
                self.P_dem_total[t] - self.P_inj_total[t],
                name="District_balance" + str(t)
            )

        # Upper bound for demand
        for t in self.timesteps:
            self.m.addConstr(
                self.P_dem_gcp[t],
                gp.GRB.LESS_EQUAL,
                self.P_dem_total[t],
                name="Limit_district_dem" + str(t)
            )

        # Upper bound for injection
        for t in self.timesteps:
            self.m.addConstr(
                self.P_inj_gcp[t],
                gp.GRB.LESS_EQUAL,
                self.P_inj_total[t],
                name="Limit_district_inj" + str(t)
            )

        # Cumulated gas demand
        for t in self.timesteps:
            self.m.addConstr(
                self.P_gas_total[t],
                gp.GRB.EQUAL,
                sum(self.P_gas[n][t] for n in range(self.buildings)),
                name="Cumulated_dem_gas" + str(t)
            )

        # Total emissions
        for t in self.timesteps:
            self.m.addConstr(
                self.Emi_total_central[t],
                gp.GRB.EQUAL,
                self.dt * (self.P_dem_gcp[t] * self.Emission_factor_elec
                           - self.P_inj_gcp[t] * self.Emission_factor_elec
                           + self.P_gas_total[t] * self.Emission_factor_gas),
                name="P_total_emission_balance_" + str(t)
            )

        for n in range(self.buildings):
            for t in self.timesteps:
                self.m.addConstr(
                    self.Emi_building[n, t],
                    gp.GRB.EQUAL,
                    self.dt * (self.P_dem[n][t] * self.Emission_factor_elec
                               + self.P_gas[n][t] * self.Emission_factor_gas),
                    name="P_building_emission_balance_" + str(n) + "_" + str(t)
                )

        for t in self.timesteps:
            self.m.addConstr(
                self.Emi_total_decentral[t],
                gp.GRB.EQUAL,
                self.dt * (self.P_dem_total[t] * self.Emission_factor_elec
                           - self.P_inj_total[t] * self.Emission_factor_elec
                           + self.P_gas_total[t] * self.Emission_factor_gas),
                name="P_total_emission_balance_" + str(t)
            )

        # Total costs
        for t in self.timesteps:
            self.m.addConstr(
                self.C_total_central[t],
                gp.GRB.EQUAL,
                self.dt * (self.P_dem_gcp[t] * self.C_dem_elec
                           - self.P_inj_gcp[t] * self.C_feed_in_elec
                           + self.P_gas_total[t] * self.C_dem_gas),
                name="P_total_cost_balance_" + str(t)
            )

        for n in range(self.buildings):
            for t in self.timesteps:
                self.m.addConstr(
                    self.C_building[n, t],
                    gp.GRB.EQUAL,
                    self.dt * (self.P_dem[n][t] * self.C_dem_elec
                               - self.P_inj[n][t] * self.C_feed_in_elec
                               + self.P_gas[n][t] * self.C_dem_gas),
                    name="P_building_cost_balance_" + str(n) + "_" + str(t)
                )

        for t in self.timesteps:
            self.m.addConstr(
                self.C_total_decentral[t],
                gp.GRB.EQUAL,
                self.dt * (self.P_dem_total[t] * self.C_dem_elec
                           - self.P_inj_total[t] * self.C_feed_in_elec
                           + self.P_gas_total[t] * self.C_dem_gas),
                name="P_total_cost_balance_" + str(t)
            )