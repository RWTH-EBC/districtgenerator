from typing import Any, Dict, List
from districtgenerator.data_handling.config import GurobiConfig

class GurobiGenerator:
    def __init__(self, gurobi_config: GurobiConfig):
        self.config = gurobi_config

    def generate_optimization_data(self) -> List[Dict[str, Any]]:
        return {
            "ModelName": self.config.ModelName,
            "TimeLimit": self.config.TimeLimit,
            "MIPGap": self.config.MIPGap,
            "MIPFocus": self.config.MIPFocus,
            "NonConvex": self.config.NonConvex,
            "NumericFocus": self.config.NumericFocus,
            "PoolSolution": self.config.PoolSolution,
            "DualReductions": self.config.DualReductions,
        }
