"""
Site conditions of the district: weather station, holidays and design temperatures.
"""
import os

import holidays as hol
import openpyxl
import pandas as pd


def select_plz_data(data):
    """
    Select the closest TRY weather station for the location of the postal code.

    Returns
    -------
    None.
    """

    # Try to find the location of the postal code and matched TRY weather station
    try:
        workbook = openpyxl.load_workbook(data.filePath + "/plz_geocoord_matched.xlsx")
        sheet = workbook.active

        for row in sheet.iter_rows(values_only=True):
            if data.site["zip"] == str(row[0]):
                weatherdatafile = row[3]
                data.site["Location"] = weatherdatafile[8:-9]
                break
        else:
            # If postal code cannot be found: Message and select weather data file from Aachen
            raise ValueError("Postal code cannot be found")


    except Exception as e:
        # If postal code cannot be found: Message and select weathter data file from Aachen
        print("Postal code cannot be found, location changed to Aachen")
        data.site["zip"] = "52064"
        data.site["Location"] = 507755060854


def get_holidays(country_code: str, year: int, state: str = None):
    """
    Get the Julian day (day of the year) for holidays in a specific country, year, and state.

    Parameters
    ----------
        country_code : string
            The country's ISO 3166-1 alpha-2 code (e.g., 'DE' for Germany).
        year : integer
            The year for which to retrieve holidays.
        state : string
            The state or region subdivision code (e.g., 'NW' for North Rhine-Westphalia in Germany).

    Returns
    -------
        julian_holidays : list
            A list of tuples containing the Julian day of the holiday.
    """
    try:
        # Initialize the holidays object for the given country, year, and state
        holidays = hol.country_holidays(country_code, years=year, subdiv=state)

        # Get the Julian day for each holiday
        julian_holidays = [holiday_date.timetuple().tm_yday for holiday_date in holidays.keys()]

        return julian_holidays
    except KeyError:
        return f"Invalid country or state code '{country_code}', '{state}'. Please provide valid codes."


def load_site_conditions(data):
    """
    Load altitude, location and design temperatures of the site.

    Values are based on DIN/TS 12831-1:2020-04 and the cooling load zones of VDI 2078-2015.

    Parameters
    ----------
    data : Datahandler
        Datahandler with the zip code of the site in ``data.site``.

    Returns
    -------
    None.
    """
    # Load other site-dependent values based on DIN/TS 12831-1:2020-04 and VDI 2078-2015 (KLZ)
    filePath = os.path.join(data.filePath, 'site_data_with_KLZ.txt')
    site_data = pd.read_csv(filePath, delimiter='\t', dtype={'Zip': str})

    # Filter data for the specific zip code
    filtered_data = site_data[site_data['Zip'] == data.site["zip"]]

    # extract the needed values
    data.site["altitude"] = filtered_data.iloc[0]['Altitude']
    data.site["location"] = [filtered_data.iloc[0]['Latitude'],filtered_data.iloc[0]['Longitude']]
    data.site["T_ne"] = filtered_data.iloc[0]['T_ne'] # norm outside temperature for calculating the design heat load
    data.site["T_me"] = filtered_data.iloc[0]['T_me'] # mean annual temperature for calculating the design heat load

    # KLZ added to site_data based on nearest VDI station (generate_klz_site_data.py)
    klz = filtered_data.iloc[0]['KLZ']
    # Cooling limit temperatures based on Cooling Laod Zones (Kühllastzonen)
    # Calculated based on estimated amplitude based on VDI 2078 p. 117
    # To account for thermal mass and avoid outliers, T_me is used as average plus amplitude
    vdi_climate_data = {
        1: (23.3, 6.7),  # Zone 1 (Cool)
        2: (24.1, 7.4),  # Zone 2 (Moderate)
        3: (25, 8.0),  # Zone 3 (Warm)
        4: (26.1, 8.4),  # Zone 4 (Hot)
    }

    # Calculation: T_max = T_me + Amplitude
    if klz in vdi_climate_data:
        t_mean, amplitude = vdi_climate_data[klz]
        data.site["T_design_cooling"] = t_mean + amplitude
    else:
        # Fallback (Standard Zone 3)
        t_mean, amplitude = vdi_climate_data[3]
        data.site["T_design_cooling"] = t_mean + amplitude
