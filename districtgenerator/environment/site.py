"""
Site conditions of the district: weather station, holidays and design temperatures.
"""
import os
import warnings

import holidays as hol
import openpyxl
import pandas as pd

from districtgenerator.config.settings import LocationConfig
from districtgenerator.utilities.paths import DATA_DIR


def select_plz_data(data):
    """
    Select the closest TRY weather station for the location of the postal code.

    Sets ``data.site["weather_station"]``, the ID of the TRY weather station. If the zip code is not
    in ``plz_geocoord_matched.xlsx``, a warning is issued and the fallback of ``LocationConfig``
    (Aachen) is used. In that case ``data.site["zip"]`` is changed as well.

    Parameters
    ----------
    data : Datahandler
        Datahandler with the zip code of the site in ``data.site["zip"]``.

    Returns
    -------
    None.

    Raises
    ------
    FileNotFoundError
        If ``plz_geocoord_matched.xlsx`` is missing in the data folder.
    """
    plz_file_path = os.path.join(DATA_DIR, "site", "plz_geocoord_matched.xlsx")
    workbook = openpyxl.load_workbook(plz_file_path)
    sheet = workbook.active

    # Find the postal code and its matched TRY weather station
    for row in sheet.iter_rows(values_only=True):
        if data.site["zip"] == str(row[0]):
            weatherdatafile = row[3]
            # Cut the station ID out of the file name, e.g. "TRY2015_<station>_Jahr.dat":
            # 8 characters prefix ("TRY2015_") and 9 characters suffix ("_Jahr.dat")
            data.site["weather_station"] = weatherdatafile[8:-9]
            break
    else:
        # Postal code not found: use the weather station of the fallback location
        warnings.warn(f"Postal code '{data.site['zip']}' not found in {plz_file_path}, "
                      f"using fallback '{LocationConfig.FALLBACK_ZIP}' (Aachen).", stacklevel=2)
        data.site["zip"] = LocationConfig.FALLBACK_ZIP
        data.site["weather_station"] = LocationConfig.FALLBACK_WEATHER_STATION


def get_holidays(country_code: str, year: int, state: str = None):
    """
    Get the day of the year of all holidays in a specific country, year, and state.

    Parameters
    ----------
    country_code : str
        The country's ISO 3166-1 alpha-2 code (e.g., 'DE' for Germany).
    year : int
        The year for which to retrieve holidays.
    state : str, optional
        The state or region subdivision code (e.g., 'NW' for North Rhine-Westphalia in Germany).
        If None, only nationwide holidays are returned.

    Returns
    -------
    list of int
        Day of the year (1 = January 1st) of each holiday.

    Raises
    ------
    ValueError
        If the country or state code is invalid.
    """
    try:
        # Initialize the holidays object for the given country, year, and state
        holidays = hol.country_holidays(country_code, years=year, subdiv=state)
    except (KeyError, NotImplementedError) as e:
        raise ValueError(f"Invalid country or state code '{country_code}', '{state}'. "
                         f"Please provide valid codes.") from e

    # Get the day of the year for each holiday
    return [holiday_date.timetuple().tm_yday for holiday_date in holidays.keys()]


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

    Raises
    ------
    ValueError
        If the zip code is missing in ``site_data_with_KLZ.txt``.
    """
    # Load other site-dependent values based on DIN/TS 12831-1:2020-04 and VDI 2078-2015 (KLZ)
    site_data_path = os.path.join(DATA_DIR, "site", "site_data_with_KLZ.txt")
    site_data = pd.read_csv(site_data_path, delimiter='\t', dtype={'Zip': str})

    # Filter data for the specific zip code
    filtered_data = site_data[site_data['Zip'] == data.site["zip"]]
    if filtered_data.empty:
        raise ValueError(f"Postal code '{data.site['zip']}' not found in {site_data_path}. "
                         f"The site data and plz_geocoord_matched.xlsx are inconsistent.")
    site_row = filtered_data.iloc[0]

    # extract the needed values
    data.site["altitude"] = site_row['Altitude']
    data.site["location"] = [site_row['Latitude'], site_row['Longitude']]
    data.site["T_ne"] = site_row['T_ne'] # norm outside temperature for calculating the design heat load
    data.site["T_me"] = site_row['T_me'] # mean annual temperature for calculating the design heat load

    # KLZ added to site_data based on nearest VDI station (generate_klz_site_data.py)
    klz = site_row['KLZ']

    # Design temperature for the cooling load (Kühllastzonen, VDI 2078 p. 117):
    # mean summer temperature of the cooling load zone plus its daily amplitude
    zones = LocationConfig.COOLING_LOAD_ZONES
    if klz not in zones:
        warnings.warn(f"Unknown cooling load zone '{klz}' for postal code '{data.site['zip']}', "
                      f"using zone {LocationConfig.DEFAULT_COOLING_LOAD_ZONE}.", stacklevel=2)
        klz = LocationConfig.DEFAULT_COOLING_LOAD_ZONE
    t_mean, amplitude = zones[klz]
    data.site["T_design_cooling"] = t_mean + amplitude
