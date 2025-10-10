import pyomo.environ as pyo
from districtgenerator.functions import opti_central


class Optimizer:
    """
    A class to set up, solve, and manage a Pyomo optimization model.
    """

    def __init__(self, data, cluster):
        
        self.data = data
        self.cluster = cluster
        self.model = self._initialize_pyomo_model()

    def _initialize_pyomo_model(self):
        """
        Initializes an empty Pyomo ConcreteModel.
        Add specific model solving settings here if needed.
        """
        model_name = f"Central_Optimization_Model"
        return pyo.ConcreteModel(name=model_name)


    def run_cen_opti(self):
        """
        High-level method to run the entire central optimization process for one cluster.
        """
        results_dict = opti_central.run_opti_central(model=self.model, data=self.data, cluster=self.cluster)
        return results_dict
