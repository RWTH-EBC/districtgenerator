"""
Central energy system: dimensioning of the energy hub devices of the district.
"""
import os

import numpy as np

import districtgenerator.optimization.central.dimensioning as opti_dimensioning_central_devices
import districtgenerator.optimization.central.parameters as get_params_central_devices


class CES:
    """
    Abstract class for design of the central energy system.
    """

    def __init__(self):
        """
        Constructor of central energy system (CES) class.

        Returns
        -------
        None.
        """


    def designCES(self, data):
        """
        Dimensioning of central devices with EHDO

        Parameters
        ----------

        Returns
        -------
        capacities_centralDevices : dictionary
            The capacities of the central devices.
        """

        # Load parameters of the energy hub
        param, devs, dem, result_dict = get_params_central_devices.get_params(data)

        # Run optimization
        capacities_centralDevices = opti_dimensioning_central_devices.run_optim(data, devs, param, dem, result_dict)

        return capacities_centralDevices


def design_central_devices(data, saveGenerationProfiles):
    """
    Calculate capacities and generation profiles of renewable energies for central devices.

    Parameters
    ----------
    saveGenerationProfiles : bool, optional
        True: save central PV, STC and WT profiles as CSV-file.
        False: don't save central PV, STC and WT profiles as CSV-file.
        The default is True.


    Returns
    -------
    None.
    """
    # initialization
    data.centralDevices = {}

    # initialize central energy system object
    data.centralDevices["ces_obj"] = CES()

    # dimensioning of central devices
    data.centralDevices["capacities"] = data.centralDevices["ces_obj"].designCES(data)

    # calculate theoretical PV, STC and Wind generation
    data.centralDevices["generation"] = {}
    data.centralDevices["generation"]["PV"] = data.centralDevices["capacities"]["PV_generation_uncl"]
    data.centralDevices["generation"]["STC"] = data.centralDevices["capacities"]["STC_generation_uncl"]
    data.centralDevices["generation"]["Wind"] = data.centralDevices["capacities"]["WT_generation_uncl"]

    # optionally save generation profiles
    if saveGenerationProfiles == True:
        np.savetxt(os.path.join(data.resultPath, 'generation', 'centralPV.csv'),
                   data.centralDevices["generation"]["PV"],
                   delimiter=';',
                   fmt='%.2f')
        np.savetxt(os.path.join(data.resultPath, 'generation', 'centralSTC.csv'),
                   data.centralDevices["generation"]["STC"],
                   delimiter=';',
                   fmt='%.2f')
        np.savetxt(os.path.join(data.resultPath, 'generation', 'centralWind.csv'),
                   data.centralDevices["generation"]["Wind"],
                   delimiter=';',
                   fmt='%.2f')
