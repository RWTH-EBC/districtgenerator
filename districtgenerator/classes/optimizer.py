import json, sys, os
import gurobipy as gp
from collections import defaultdict
from contextlib import contextmanager
import districtgenerator.functions.opti_central as opti_central


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
        self.data = data
        self.cluster = cluster
        self.initializeModel()

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
        # Set the parameters of the gurobi model.
        self.model.setParam("NonConvex", self.optiSettings["NonConvex"])
        self.model.setParam("MIPGap", self.optiSettings["MIPGap"])
        self.model.setParam("TimeLimit", self.optiSettings["TimeLimit"])
        self.model.setParam("DualReductions", self.optiSettings["DualReductions"])

    def run_cen_opti(self, optiData):
        """
        Load the variables and constrains into the model.

        Returns
        -------
        None.
        """

        results = opti_central.run_opti_central(self.model, self.data.district, self.data.centralDevices, self.data.site,
                                                self.cluster, self.srcPath, optiData)

        return results