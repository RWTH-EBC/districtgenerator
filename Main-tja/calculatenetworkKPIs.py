from districtgenerator.classes import KPIs

def calculatenetworkKPIs(self):
    """
    Calculate key performance indicators (KPIs).

    Returns
    -------
    None.
     """

    # initialize KPI class
    self.KPIs = KPIs(self)
    # calculate KPIs
    self.KPIs.calculateAllKPIs(self)