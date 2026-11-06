"""
Central energy system: dimensioning of the energy hub devices of the district.
"""
import os

import numpy as np

import districtgenerator.optimization.energy_hub_sizing as opti_dimensioning_central_devices
import districtgenerator.optimization.energy_hub_parameters as get_params_central_devices


class CES:
    """Optimize the district energy hub using prepared demands and technology data."""

    def __init__(self):
        """Create an energy-hub sizing interface.

        Returns
        -------
        None
            No optimization is run until ``designCES`` is called.
        """


    def designCES(self, data):
        """Optimize central device capacities and energy-hub operation.

        Parameters
        ----------
        data : Prepared district with clustered demands, site/weather profiles, central
            technology settings, economics, and solver configuration required by the
            central parameter builder and dimensioning model.

        Returns
        -------
        dict
            Energy-hub optimization results.
        """

        # Load parameters of the energy hub
        param, devs, dem, result_dict = get_params_central_devices.get_params(data)

        # Run optimization
        capacities_centralDevices = opti_dimensioning_central_devices.run_optim(data, devs, param, dem, result_dict)

        return capacities_centralDevices


def design_central_devices(data, saveGenerationProfiles):
    """Optimize the energy hub and expose its renewable generation profiles.

    Parameters
    ----------
    data : District prepared for central sizing, including demands, clustering,
        economics, device data, and ``resultPath``. For CSV export the
        ``generation`` output directory must already exist.
    saveGenerationProfiles : bool
        Write PV, STC, and wind profiles to ``centralPV.csv``, ``centralSTC.csv``,
        and ``centralWind.csv`` under ``data.resultPath/generation`` when True.

    Returns
    -------
    None
        Replaces ``data.centralDevices`` with the CES object, optimization
        results under ``capacities``, and unclustered generation profiles under
        ``generation`` (``PV``, ``STC``, ``Wind``), in kW.
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
