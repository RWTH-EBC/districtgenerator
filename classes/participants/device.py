import pandas as pd
import json


class Device:
    """ Abstract class for a device """

    def __init__(self, model):
        """
        Constructor of Device class.

        Parameters
        ----------
        model : gurobipy.Model
            Gurobi model of the optimization problem.

        Returns
        -------
        None.
        """
        
        self.m = model
        self.gurobiSettings = self.loadGurobiSettings()
        self.ecoData = self.loadData("eco")
        self.timeData = self.loadData("time")
        self.timesteps = range(int(self.timeData["clusterLength"] / self.timeData["timeResolution"]))
        self.dt = self.timeData["timeResolution"] / (60 * 60)
        self.devs = self.loadDeviceData()

    def returnModel(self):
        """
        Return the gurobi model of the optimization problem.

        Returns
        -------
        model : gurobipy.Model
            Gurobi model of the optimization problem.
        """

        model = self.m
        
        return model

    def loadGurobiSettings(self):
        """
        Return the loaded gurobi settings.

        Returns
        -------
        gurobiSettings : dictionary
            Gurobi settings as e.g. TimeLimit and MIPGap.
        """

        gurobiSettings = json.load(open('data/gurobi_settings.json'))
        
        return gurobiSettings

    def loadData(self, device=None):
        """
        Load data from a JSON-file.

        Parameters
        ----------
        device : string, optional
            Type of data that is wished to be loaded. The default is None.

        Returns
        -------
        data : dictionary
            Loaded data.
        """
        
        if not device:
            device = type(self).__name__.lower()
        data = {}
        with open("data/" + device + "_data.json") as json_file:
            jsonData = json.load(json_file, encoding='utf-8')
            for subData in jsonData:
                if subData["value"] == "file":
                    data[subData["name"]] = self.handleFileImport(subData["fileImport"])
                else:
                    data[subData["name"]] = subData["value"]

        return data

    def loadDeviceData(self):
        """
        Load data about energy conversion devices.

        Returns
        -------
        data : dictionary
            Data about energy conversion devices.
        """
        
        data = {}
        with open("data/device_data.json") as json_file:
            jsonData = json.load(json_file)
            for subData in jsonData:
                data[subData["abbreviation"]] = {}
                for subsubData in subData["specifications"]:
                    data[subData["abbreviation"]][subsubData["name"]] = subsubData["value"]

        return data

    def setConstraint(self, constraintFunctionName):
        """


        Parameters
        ----------
        constraintFunctionName : TYPE
            DESCRIPTION.

        Returns
        -------
        None.
        """

        getattr(self, constraintFunctionName)()

    def setVariable(self, variableFunctionName):
        """


        Parameters
        ----------
        variableFunctionName : TYPE
            DESCRIPTION.

        Returns
        -------
        None.
        """
        getattr(self, variableFunctionName)()

    def handleCSVImport(self, fileName, columnName):
        """
        Import data from CSV-file.

        Parameters
        ----------
        fileName : string
            Name of CSV-file.
        columnName : string
            Name of column with relevant data.

        Returns
        -------
        CSVImport : list
            Imported data from CSV-file.
        """

        df = pd.read_csv('data/files/' + fileName + ".csv", sep="\t")
        if columnName:
            CSVImport = df[columnName].tolist()
        else:
            CSVImport = df.tolist()

        return CSVImport

    def handleFileImport(self, fileImport):
        """
        Import data from file.

        Parameters
        ----------
        fileImport : dictionary
            Contains information about the data to import.

        Returns
        -------
        importedData : list
            Imported data from file.
        """

        fileName = fileImport["fileName"]
        try:
            columnName = str(fileImport["columnName"])
        except:
            columnName = None
        importedData = self.handleCSVImport(fileName, columnName)

        return importedData