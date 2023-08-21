# -*- coding: utf-8 -*-

import math
import os
import random as rd

import numpy as np
import richardsonpy
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
import richardsonpy.classes.stochastic_el_load_wrapper as wrap

import functions.heating_profile_5R1C as heating
from classes.profils import Profiles


class Users:
    """
    Building Users class describing the number of occupants and their configs.

    Parameters
    ----------
    building : string
        Building type according to TABULA database.
    area : integer
        Total floor area of the building [m²].

    Attributes
    ----------
    building : string
        Building type according to TABULA database.
    nb_flats : integer
        Number of flats in building.
    annual_el_demand : array-like
        Annual electricity consumption in dependency of the building type and the number of occupants.
    lighting_index : integer
        This index defines the lighting configuration of the household.
    el_wrapper : object
        This objects holds information about the lighting and appliance configuration.
    nc_occ : list
        List with the number of occupants for each flat of the current building.
    occ : array-like
        Occupancy profile for each flat of the current building.
    dhw : array-like
        Drinking hot water profile for each building.
    elec : array-like
        Electrical demand for each building.
    gains : array-like
        Internal gains for each building.
    heat : array-like
        Heat demand for each building.
    """

    def __init__(self, building, area):
        """
        Constructor of Users class.

        Returns
        -------
        None.
        """

        self.building = building
        self.nb_flats = None
        self.annual_el_demand = None
        self.lighting_index = []
        self.el_wrapper = []
        self.nb_occ = []
        self.occ = None
        self.dhw = None
        self.elec = None
        self.gains = None
        self.heat = None

        self.generate_number_flats()
        self.generate_number_occupants()
        self.generate_annual_el_consumption()
        self.generate_lighting_index()
        self.create_el_wrapper()

    def generate_number_flats(self):
        """
        Generate number of flats for different building types.
        Possible building types are:
            - single family house (SFH)
            - terraced house (TH)
            - multifamily house (MFH)
            - apartment block (AP)

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        """
        # SFH and TH have the same procedure
        if self.building == "SFH" or "TH":
            """
            The TABLUA building category "SFH" and "TH" are comprised of
            houses with one flat and two flats.
            The probability of having one or two flats is calculated from
            the german Zensus 2011 data.
            """
            prob = 0.793  # probability of a 1 flat SFH (2 flat = 1-0.793)
            random = np.random.uniform(low=0, high=1, size=None)
            if random <= prob:
                self.nb_flats = 1
            else:
                self.nb_flats = 2
        elif self.building == "MFH":
            """
            The TABLUA building category "MFH" is comprised of houses with
            three to 12 flats.
            The probability of occurence of the amount of flats is calculated
            from the german Zensus 2011 data. The number of flats per building
            is given in categories (3-6 flats, 7-12 flats) and only the
            category probability is known. Within the categories, a uniform
            distribution is assumed.
            """
            prob = 0.718  # probability of a 3-6 flat MFH
            random = np.random.uniform(low=0, high=1, size=None)  # get random value
            if (
                random <= prob
            ):  # if the probability says we are in the smaller group of MFH
                self.nb_flats = rd.randint(
                    3, 7
                )  # select value between 3 and 6 (inclusive) on random
            else:
                self.nb_flats = rd.randint(7, 13)
        elif self.building == "AB":
            """
            The TABULA building category "GMH" (given here as "AB") contains
            buildings with 13 or more flats.
            The range of flats per building and probability of occurence is not
            given. An exponential distribution with beta = 1 is assumed, the values
            are then scaled to be >=13.
            """
            self.nb_flats = np.random.exponential(scale=1) + 13

    def generate_number_occupants(self):
        """
        Generate number of occupants for different of building types.
        Number of inhabitants is always between 1 and 6, irrespective of
        building type. The probability of a certain number of inhabitants
        changes with building type, based on Zensus2011 data.

        Parameters
        ----------
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        if self.building in ("SFH", "TH"):
            # probability table, calculated from Zensus2011
            # k: number inhabitants
            # v: proportion of occurence (cumulative)
            prob = {
                1: (0, 0.223),
                2: (0.223, 0.581),
                3: (0.581, 0.770),
                4: (0.770, 0.927),
                5: (0.927, 0.977),
                6: (0.977, 1),
            }
            # loop over all flats of current building
            for flat in range(self.nb_flats):
                # get a random number
                random_nb = rd.random()
                for k, (lb, ub) in prob.items():
                    # if the random number is between the lb and ub
                    if random_nb > lb and random_nb < ub:
                        # the key gives the number of occupants
                        self.nb_occ.append(k)

        if self.building == "MFH":
            # probability table, calculated from Zensus2011
            # k: number inhabitants
            # v: proportion of occurence (cumulative)
            prob = {
                1: (0, 0.468),
                2: (0.468, 0.794),
                3: (0.794, 0.910),
                4: (0.910, 0.973),
                5: (0.973, 0.991),
                6: (0.991, 1),
            }
            # loop over all flats of current building
            for flat in range(self.nb_flats):
                # get a random number
                random_nb = rd.random()
                for k, (lb, ub) in prob.items():
                    # if the random number is between the lb and ub
                    if random_nb > lb and random_nb < ub:
                        # the key gives the number of occupants
                        self.nb_occ.append(k)

        if self.building == "AB":
            # probability table, calculated from Zensus2011
            # k: number inhabitants
            # v: proportion of occurence (cumulative)
            prob = {
                1: (0, 0.609),
                2: (0.609, 0.858),
                3: (0.858, 0.935),
                4: (0.935, 0.978),
                5: (0.978, 0.992),
                6: (0.992, 1),
            }
            # loop over all flats of current building
            for flat in range(self.nb_flats):
                # get a random number
                random_nb = rd.random()
                for k, (lb, ub) in prob.items():
                    # if the random number is between the lb and ub
                    if random_nb > lb and random_nb < ub:
                        # the key gives the number of occupants
                        self.nb_occ.append(k)

    def generate_annual_el_consumption(self):
        """
        Generate annual electricity consumption
        in dependency of the building type and the number of occupants.

        Parameters
        ----------
        standard_consumption : standard annual consumption in kWh (assumption).

        Returns
        -------
        None.
        """

        # source: https://www.stromspiegel.de/stromverbrauch-verstehen/stromverbrauch-im-haushalt/#c120951
        # method: https://www.stromspiegel.de/ueber-uns-partner/methodik-des-stromspiegels/
        standard_consumption = {
            "SFH": {1: 2300, 2: 3000, 3: 3500, 4: 4000, 5: 5000},
            "MFH": {1: 1300, 2: 2000, 3: 2500, 4: 2600, 5: 3000},
        }

        self.annual_el_demand = np.zeros(self.nb_flats)
        # assumption: standard deviation 10% of mean value
        for j in range(self.nb_flats):
            if self.building == "SFH":
                annual_el_demand_temp = standard_consumption["SFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(
                    annual_el_demand_temp, annual_el_demand_temp * 0.10
                )
            if self.building == "TH":
                annual_el_demand_temp = standard_consumption["SFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(
                    annual_el_demand_temp, annual_el_demand_temp * 0.10
                )
            if self.building == "MFH":
                annual_el_demand_temp = standard_consumption["MFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(
                    annual_el_demand_temp, annual_el_demand_temp * 0.10
                )
            if self.building == "AB":
                annual_el_demand_temp = standard_consumption["MFH"][self.nb_occ[j]]
                self.annual_el_demand[j] = rd.gauss(
                    annual_el_demand_temp, annual_el_demand_temp * 0.10
                )

    def generate_lighting_index(self):
        """
        Choose a random lighting index between 0 and 99.
        This index defines the lighting configuration of the household.
        There are 100 predefined lighting configurations.

        Assumptions: - All lighting configurations have the same probability.
                     - No differences between SFH, TH, MFH and AB.

        Parameters
        ----------
        random_nb : random number in [0,1).

        Returns
        -------
        None.
        """

        for j in range(self.nb_flats):
            random_nb = rd.random()
            self.lighting_index.append(int(random_nb * 100))

    def create_el_wrapper(self):
        """
        Create a wrapper-object
        holding information about the lighting and appliance configuration.

        Parameters
        ----------
        annual_demand : integer
            Annual electricity demand in kWh.
        light_config : integer
            This index defines the lighting configuration of the household.
            There are 100 predefined lighting configurations.

        Returns
        -------
        None.
        """

        src_path = os.path.dirname(richardsonpy.__file__)
        path_app = os.path.join(src_path, "inputs", "Appliances.csv")
        path_light = os.path.join(src_path, "inputs", "LightBulbs.csv")

        for j in range(self.nb_flats):
            # annual demand of the electric appliances (annual demand minus lighting)
            # source: https://www.umweltbundesamt.de/daten/private-haushalte-konsum/wohnen/energieverbrauch-privater-haushalte#stromverbrauch-mit-einem-anteil-von-rund-einem-funftel
            # values from diagram for 2018 without heating, dhw and cooling: 8,1 / 81,1 = 10,0%
            appliancesDemand = 0.9 * self.annual_el_demand[j]

            # Create and save appliances object
            appliances = app_model.Appliances(
                path_app,
                annual_consumption=appliancesDemand,
                randomize_appliances=True,
                max_iter=15,
                prev_heat_dev=True,
            )

            # Create and save light configuration object
            lights = light_model.load_lighting_profile(
                filename=path_light, index=self.lighting_index[j]
            )

            #  Create wrapper object
            self.el_wrapper.append(wrap.ElectricityProfile(appliances, lights))

    def calcProfiles(self, site, time_resolution, time_horizon, initial_day=1):
        """
        Calculate profiles for every flat and summarize them for the whole building

        Parameters
        ----------
        site: dict
            Site data, e.g. weather.
        time_resolution : integer
            Resolution of time steps of output array in seconds.
        time_horizon : integer
            Time horizon for which a stochastic profile is generated.
        initial_day : integer, optional
            Day of the week with which the generation starts.
            1-7 for monday-sunday. The default is 1.

        Returns
        -------
        None.
        """

        irradiation = site["SunTotal"]
        T_e = site["T_e"]

        time_day = 24 * 60 * 60
        nb_days = int(time_horizon / time_day)

        self.occ = np.zeros(int(time_horizon / time_resolution))
        self.dhw = np.zeros(int(time_horizon / time_resolution))
        self.elec = np.zeros(int(time_horizon / time_resolution))
        self.gains = np.zeros(int(time_horizon / time_resolution))
        self.car = np.zeros(int(time_horizon / time_resolution))
        for j in range(self.nb_flats):
            temp_obj = Profiles(self.nb_occ[j], initial_day, nb_days, time_resolution)
            self.occ = self.occ + temp_obj.generate_occupancy_profiles()
            self.dhw = self.dhw + temp_obj.generate_dhw_profile()
            self.elec = self.elec + temp_obj.generate_el_profile(
                irradiance=irradiation,
                el_wrapper=self.el_wrapper[j],
                annual_demand=self.annual_el_demand[j],
            )
            self.gains = self.gains + temp_obj.generate_gain_profile()
        # currently only one car per building possible
        self.car = self.car + temp_obj.generate_EV_profile()

    def calcHeatingProfile(self, site, envelope, time_resolution):
        """
        Calculate heat demand for each building.

        Parameters
        ----------
        site: dict
            Site data, e.g. weather.
        envelope: object
            Containing all physical data of the envelope.
        time_resolution : integer
            Resolution of time steps of output array in seconds.
        Q_HC : float
            Heating (positive) or cooling (negative) load for the current time
            step in Watt.

        Returns
        -------
        None.
        """

        dt = time_resolution / (60 * 60)
        # calculate the temperatures (Q_HC, T_op, T_m, T_air, T_s)
        (Q_HC, T_i, T_s, T_m, T_op) = heating.calculate(envelope, site["T_e"], dt)
        # heating  load for the current time step in Watt
        self.heat = np.zeros(len(Q_HC))
        for t in range(len(Q_HC)):
            self.heat[t] = max(0, Q_HC[t])

    def saveProfiles(self, unique_name, path):
        """
        Save profiles to csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        np.savetxt(
            path + "/elec_" + unique_name + ".csv",
            self.elec,
            fmt="%1.2f",
            delimiter=",",
        )
        np.savetxt(
            path + "/dhw_" + unique_name + ".csv", self.dhw, fmt="%1.2f", delimiter=","
        )
        np.savetxt(
            path + "/occ_" + unique_name + ".csv", self.occ, fmt="%1.2f", delimiter=","
        )
        np.savetxt(
            path + "/gains_" + unique_name + ".csv",
            self.gains,
            fmt="%1.2f",
            delimiter=",",
        )
        np.savetxt(
            path + "/car_" + unique_name + ".csv", self.car, fmt="%1.2f", delimiter=","
        )

        """
        fields = [name + "_" + str(id), str(sum(self.nb_occ))]
        with open(path + '/_nb_occupants.csv','a') as f :
            writer = csv.writer(f)
            writer.writerow(fields)
        """

    def saveHeatingProfile(self, unique_name, path):
        """
        Save heating demand to csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        np.savetxt(
            path + "/heating_" + unique_name + ".csv",
            self.heat,
            fmt="%1.2f",
            delimiter=",",
        )

    def loadProfiles(self, unique_name, path):
        """
        Load profiles from csv.

        Parameters
        ----------
        unique_name : string
            Unique building name.
        path : string
            Results path.

        Returns
        -------
        None.
        """

        self.elec = np.loadtxt(path + "/elec_" + unique_name + ".csv", delimiter=",")
        self.dhw = np.loadtxt(path + "/dhw_" + unique_name + ".csv", delimiter=",")
        self.occ = np.loadtxt(path + "/occ_" + unique_name + ".csv", delimiter=",")
        self.gains = np.loadtxt(path + "/gains_" + unique_name + ".csv", delimiter=",")
        self.car = np.loadtxt(path + "/car_" + unique_name + ".csv", delimiter=",")


if __name__ == "__main__":
    test = Users(building="SFH", area=1000)

    test.calcProfiles()
