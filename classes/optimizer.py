import json, sys, os
import gurobipy as gp
from collections import defaultdict
from contextlib import contextmanager

import classes.participants

@contextmanager
def suppress_stdout():
    """
    

    Returns
    -------
    None.
    """
    
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:  
            yield
        finally:
            sys.stdout = old_stdout


class Optimizer:
    """
    Optimizer class for running the optimization.

    Attributes
    ----------
    optiSettings:
        Optimization settings for the gurobi model.
    model:
        Gurobi model to solve with the gurobi solver.
    results:
        Dictionary containing the results of the optimization.
    data:
        Datahandler object which contains all relevant information to perform the optimization.
    timesteps:
        Range over all time steps.
    cluster:
        Identifier of the currently regarded cluster.
    """

    def __init__(self, data, cluster, centralEnergySupply):
        """
        Constructor of Optimizer class.

        Parameters
        ----------
        data : Datahandler object
            Datahandler object which contains all relevant information to perform the optimization.
        cluster : integer
            Identifier of the currently regarded cluster.

        Returns
        -------
        None.
        """

        self.srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.filePath = os.path.join(self.srcPath, 'data')
        self.optiSettings = self.loadGurobiSettings()
        self.model = None
        self.results = None
        self.data = data
        self.timesteps = range(int(self.data.time["clusterLength"] / self.data.time["timeResolution"]))
        self.cluster = cluster
        self.initializeModel()
        self.loadDevices(centralEnergySupply)
        self.model.update()
        self.setParams()
        self.setObjective()

    def loadGurobiSettings(self):
        """
        Load the optimization settings for the gurobi solver.

        Returns
        -------
        optiSettings : dictionary
            Optimization settings for the gurobi solver.
        """

        gurobiSettings = json.load(open(os.path.join(self.filePath, 'gurobi_settings.json')))

        return gurobiSettings

    def initializeModel(self):
        """
        Initialize the gurobi model.

        Returns
        -------
        None.
        """
        
        self.model = gp.Model(self.optiSettings["ModelName"])

    def loadDevices(self, centralEnergySupply):
        """
        Load the variables and constrains into the model.

        Returns
        -------
        None.
        """

        if centralEnergySupply == True:
            # load the variables and constrains for the central energy unit of the district into the model
            classObject = getattr(classes.participants.centralEnergyUnit, "CentralEnergyUnit")
            globals()["centralEnergyUnit"] = classObject(self.model, len(self.data.district), self.data, self.cluster)
            self.model = globals()["centralEnergyUnit"].returnModel()
        else:
            # load the variables and constrains for all houses of the district into the model
            for id in range(len(self.data.district)):
                classObject = getattr(classes.participants.house, "House")
                globals()["house"] = classObject(self.model, id, self.data.district[id], self.data.site, self.cluster)
                self.model = globals()["house"].returnModel()

            # load the variables and constrains for the aggregator of the district into the model
            classObject = getattr(classes.participants.aggregator, "Aggregator")
            globals()["aggregator"] = classObject(self.model, len(self.data.district))
            self.model = globals()["aggregator"].returnModel()

    def setParams(self):
        """
        Set the parameters of the gurobi model.

        Returns
        -------
        None.
        """
        
        self.model.setParam("NonConvex", self.optiSettings["NonConvex"])
        self.model.setParam("MIPGap", self.optiSettings["MIPGap"])
        self.model.setParam("TimeLimit", self.optiSettings["TimeLimit"])
        self.model.setParam("DualReductions", self.optiSettings["DualReductions"])

    def setObjective(self):
        """
        Set the objective of the model for the optimization.

        Returns
        -------
        None.
        """

        # total central costs of the district for all time steps
        C_total = {}
        for t in self.timesteps:
            C_total[t] = self.model.getVarByName("Emission_total" + "[" + str(t) + "]")

        # total central costs of the district for all time steps
        #E_total = {}
        #for t in self.timesteps:
        #    E_total[t] = self.model.getVarByName("E_GCP" + "[" + str(t) + "]")

        # total electricity load of the district at the GNP for all time steps
        #P_dem_gcp = {}
        #for t in self.timesteps:
        #    P_dem_gcp[t] = self.model.getVarByName("P_dem_gcp" + "[" + str(t) + "]")


        # set the sum of the total central costs of the district over all time steps as objective
        self.model.setObjective(
            sum(C_total[t] for t in self.timesteps),
            gp.GRB.MINIMIZE
        )

    def runOptimization(self):
        """
        Run the optimization with the gurobi solver.

        Returns
        -------
        None.
        """

        self.model.optimize()

        # write debug file
        self.writeDebugFile()

    def getObjVal(self):
        """
        Return the object value in the optimum.

        Returns
        -------
        objectValue : float
            Object value in the optimum.
        """

        objectValue = self.model.getAttr("ObjVal")

        return objectValue

    def writeDebugFile(self):
        """
        Write a debug file and if errors appear also an error file.

        Returns
        -------
        None.
        """
        
        if self.model.status == gp.GRB.Status.INFEASIBLE:
            self.model.computeIIS()
            f = open('errorfile.txt', 'w')
            f.write('\nThe following constraint(s) cannot be satisfied:\n')
            for c in self.model.getConstrs():
                if c.IISConstr:
                    f.write('%s' % c.constrName)
                    f.write('\n')
            f.close()

        self.model.write("debug.lp")

    def getResultsOld(self):
        """
        An old function to get results of the optimization.

        Returns
        -------
        results : dictionary
            Contains results of the optimization.
        """
        
        results = defaultdict(list)
        prev = ""
        for v in self.model.getVars():
            print(v)
            variableName = v.varName.split("[")[0]
            if variableName != prev:
                prev = variableName
            results[variableName].append(v.x)

        return results

    def getResults(self, centralEnergySupply):
        """
        Create a dictionary with the results.

        Returns
        -------
        results : dictionary
            Contains the results of the optimization.
        """

        # load data of decentral devices
        devices = {}
        with open(self.filePath + "/decentral_device_data.json") as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                devices[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    devices[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        # load data of central devices
        centralDevices = {}
        with open(self.filePath + "/central_device_data.json") as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                centralDevices[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    centralDevices[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        # initialize dictionary for the results
        results = defaultdict(list)
        for id in range(len(self.data.district)):
            results[id] = defaultdict(list)
        results["centralDevices"] = defaultdict(list)

        # add results of the aggregator
        agg_var = ("P_dem_total", "P_inj_total", "P_dem_gcp", "P_inj_gcp", "P_gas_total",
                   "Cost_total", "Emission_total")
        for v in agg_var:
            for t in self.timesteps:
                results[v].append(round(self.model.getVarByName(v + "[" + str(t) + "]").x, 5))

        if centralEnergySupply == False:

            # add results of the buildings
            house_var = ("res_load", "res_inj", "res_gas")
            for v in house_var:
                for id in range(len(self.data.district)):
                    for t in self.timesteps:
                        results[id][v].append(
                            round(self.model.getVarByName(v + "_" + str(id) + "[" + str(t) + "]").x, 5))

            # add results of the decentral devices
            dev_var = ("Q_th", "P_el", "P_gas", "ch", "dch", "soc")
            for id in range(len(self.data.district)):  # loop over buildings
                for dev in devices.keys():
                    for v in dev_var:
                        if v == "soc":
                            # state of charge (soc) exists for POINTS IN TIME not TIME INTERVALS
                            rangeTimesteps = range(len(self.timesteps) + 1)
                        else:
                            rangeTimesteps = self.timesteps
                        for t in rangeTimesteps:
                            try:
                                results[id][str(dev) + "_" + v].append(
                                    round(self.model.getVarByName(v + "_" + str(id) + "[" + str(dev) + ","
                                                              + str(t) + "]").x, 5))
                            except:
                                del results[id][str(dev) + "_" + v]
                for t in self.timesteps:
                    results[id]["Q_th_Grid"].append(
                        round(self.model.getVarByName("Q_th_grid_" + str(id) + "[" + str(t) + "]").x, 5))

        # add results of the central devices
        central_dev_var = (
            "Q_th_centralDevices", "P_el_centralDevices", "P_gas_centralDevices", "ch_centralDevices",
            "dch_centralDevices", "soc_centralDevices")
        for dev in centralDevices.keys():
            for v in central_dev_var:
                if v == "soc_centralDevices":
                    # state of charge (soc) exists for POINTS IN TIME not TIME INTERVALS
                    rangeTimesteps = range(len(self.timesteps) + 1)
                else:
                    rangeTimesteps = self.timesteps
                for t in rangeTimesteps:
                    try:
                        results["centralDevices"][str(dev) + "_" + v[:-7]].append(
                            round(self.model.getVarByName(v + "[" + str(dev) + "," + str(t) + "]").x, 5))
                    except:
                        del results["centralDevices"][str(dev) + "_" + v[:-7]]

        Variablen = self.model.getVars()
        x=0

        return results


    def setResults(self):
        """
        Save results as attribute if it does not exist yet.

        Returns
        -------
        None.
        """
        
        if not self.results:
            self.results = self.getResults()
