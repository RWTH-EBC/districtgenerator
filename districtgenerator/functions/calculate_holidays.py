# Function to get the holidays for a given year and location
# Helper function to extract state and year from an .epw file
from typing import Optional
from holidays import country_holidays

from districtgenerator.functions import weather_handling

def get_holidays(file_path: Optional[str] = None, year: Optional[int] = None, location: Optional[str] = None) -> list:
    """
    Get the holidays for a given year and location.
    For documentation see: https://pypi.org/project/holidays/ 
    Options are on state level: 

    BB (Brandenburg),
    BE (Berlin),
    BW (Baden-Württemberg),
    BY (Bayern), HB (Bremen),
    HE (Hessen), HH (Hamburg),
    MV (Mecklenburg-Vorpommern), NI (Niedersachsen),
    NW (Nordrhein-Westfalen), RP (Rheinland-Pfalz),
    SH (Schleswig-Holstein), SL (Saarland), SN (Sachsen),
    ST (Sachsen-Anhalt), TH (Thüringen)

    Parameters
    ----------
    year : int
        The year to get holidays for
    location : str
        The German state code (e.g. "NW" for North Rhine-Westphalia)

    Returns
    -------
    list
        List of integers representing the day of year for each holiday
    """
    if file_path is not None:
        metadata = get_metadata(file_path)
        year = metadata["year"]
        location = metadata["state"]
    elif year is not None and location is not None:
        year = year
        location = location
    else:
        raise ValueError("Either file_path or year and location must be provided")
    holidays = country_holidays(years=year, country="DE", subdiv=location)
    return [date.timetuple().tm_yday for date in sorted(holidays.keys())]


def get_metadata(file_path: str) -> dict:
    """ 
    Based on an .epw file, this function extracts the metadata for the weather data. 
    Returns the year and the state.
    """
    # TODO: Calculate the state from the coordinates. 
    # Write a function that checks within which state the coordinates are and returns the state.
    weather_data = weather_handling.getEpwWeather(file_path)
    year = weather_data["Timestamp"].dt.year.unique()[0]
    return {"year": year,
            "state": "BE"
            }

if __name__ == "__main__":
    print(get_holidays(year=2025, location="NW"))
    print(get_holidays(file_path=r"C:\Users\felix\Programmieren\tecdm\src\districtgenerator\districtgenerator\data\weather\EPW\AMY_2010_2022_2020.epw"))
