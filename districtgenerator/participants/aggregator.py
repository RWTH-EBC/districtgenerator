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
        Import the variables of the houses and the central energy unit to use them in the constraints of the aggregator.

        Returns
        -------
        None.
        """

        # variables of the houses
        self.P_dem, self.P_inj, self.P_gas,  = {}, {}, {}
        for n in range(self.buildings):
            self.P_dem[n], self.P_inj[n], self.P_gas[n] = {}, {}, {}
            for t in self.timesteps:
                self.P_dem[n][t] = self.m.getVarByName("res_load_" + str(n) + "[" + str(t) + "]")  # [W]
                self.P_inj[n][t] = self.m.getVarByName("res_inj_" + str(n) + "[" + str(t) + "]")  # [W]
                self.P_gas[n][t] = self.m.getVarByName("res_gas_" + str(n) + "[" + str(t) + "]")  # [W]

        # variables of the central energy unit
        #self.P_el_dem_centralUnit, self.P_el_inj_centralUnit, self.P_gas_dem_centralUnit, self.Heat_inj_centralUnit = {}, {}, {}, {}
        #for t in self.timesteps:
        #    self.P_el_dem_centralUnit[t] = self.m.getVarByName("P_el_dem_centralUnit" + "[" + str(t) + "]")  # [W]
        #    self.P_el_inj_centralUnit[t] = self.m.getVarByName("P_el_inj_centralUnit" + "[" + str(t) + "]")  # [W]
        #    self.P_gas_dem_centralUnit[t] = self.m.getVarByName("P_gas_dem_centralUnit" + "[" + str(t) + "]")  # [W]
        #    self.Heat_inj_centralUnit[t] = self.m.getVarByName("Heat_inj_centralUnit" + "[" + str(t) + "]")  # [W]

    def setVariables(self):
        """
        Add the variables of the aggregator to the optimization problem.

        Returns
        -------
        None.
        """

        # Cumulated electricity demand [W] from distribution grid
        self.P_dem_total = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="P_dem_total"
        )

        # Cumulated electricity injection [W] into distribution grid
        self.P_inj_total = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="P_inj_total"
        )

        # District electricity demand at GCP (grid connection point) [W]
        self.P_dem_gcp = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="P_dem_gcp"
        )

        # District electricity injection at GCP [W]
        self.P_inj_gcp = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="P_inj_gcp"
        )

        # Cumulated gas demand [W]
        self.P_gas_total = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="P_gas_total"
        )

        # Cost for energy demand of the district [W]
        self.C_GCP = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="Cost_total"
        )

        # Emission for energy demand of the district [W]
        self.E_GCP = self.m.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="Emission_total"
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

        # Cumulated demand
        #for t in self.timesteps:
        #    self.m.addConstr(
        #        self.P_dem_total[t],
        #        gp.GRB.EQUAL,
        #        sum(self.P_dem[n][t] for n in range(self.buildings)) + self.P_el_dem_centralUnit[t],
        #        name="Cumulated_dem" + str(t)
        #    )

        # Cumulated injection
        for t in self.timesteps:
            self.m.addConstr(
                self.P_inj_total[t],
                gp.GRB.EQUAL,
                sum(self.P_inj[n][t] for n in range(self.buildings)),
                name="Cumulated_inj" + str(t)
            )

        # Cumulated injection
        #for t in self.timesteps:
        #    self.m.addConstr(
        #        self.P_inj_total[t],
        #        gp.GRB.EQUAL,
        #        sum(self.P_inj[n][t] for n in range(self.buildings)) + self.P_el_inj_centralUnit[t],
        #        name="Cumulated_inj" + str(t)
        #    )

        # Balance of total incoming and outgoing power
        for t in self.timesteps:
            self.m.addConstr(
                self.P_dem_gcp[t] + self.P_inj_total[t],
                gp.GRB.EQUAL,
                self.P_dem_total[t] + self.P_inj_gcp[t],
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
                self.P_inj_gcp[t] <= self.P_inj_total[t],
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

        #
        self.m.addConstrs(
            (self.C_GCP[t] == self.P_gas_total[t] * self.C_dem_gas
             + self.P_dem_gcp[t] * self.C_dem_elec
             - self.P_inj_gcp[t] * self.C_feed_in_elec
             for t in self.timesteps),
            name="Cost_total")

        #
        self.m.addConstrs(
            (self.E_GCP[t] == self.P_dem_gcp[t] * self.Emission_factor_elec + self.P_gas_total[t] * self.Emission_factor_gas
             for t in self.timesteps),
            name="Emission_total")