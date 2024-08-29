import os
import pandas as pd

def getBuildingType(term, kind):
    """
    Retrieve the value from a specified column based on a match in the 'districtgenerator' column.
    
    Parameters:
    term (str): The term to match in the 'districtgenerator' column.
    kind (str): The column name from which to retrieve the value.
    
    Returns:
    str: The value from the specified column if a match is found; otherwise, None.
    """
    srcPath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    building_types_file  = os.path.join(srcPath, 'data', 'building_types.csv')
    df = pd.read_csv(building_types_file, sep=';')
    # Check if the kind column exists
    if kind not in df.columns:
        raise ValueError(f"Column '{kind}' does not exist in the table.")
    
    # Find the row that matches the term in 'districtgenerator'
    match = df[df['districtgenerator'] == term]
    print(f"Match: {match}")
    print(f"Kind: {kind}")
    print(f"Term: {term}")
    # If a match is found, return the value from the specified column
    if not match.empty:
        return match[kind].values[0]
    else:
        return None



def getSchedule(building_type):
    """
    Returns the schedules from SIA, according to the building type.

    All schedules (not only the ones used) are in: data\\occupancy_schedules

    returns dataframe and schedule name
    :return: df_schedule, schedule_name
    :rtype: DataFrame (with floats), string
    """
    typeAssignment = {
        "IWU Office, Administrative or Government Buildings": "office.csv",
        "IWU Research and University Teaching": "Hörsaal, Auditorium.csv",
        "IWU Health and Care": "Bettenzimmer.csv", 
        "IWU School, Day Nursery and other Care": "Schulzimmer_Hoersaal.csv",
        "IWU Culture and Leisure": "Ausstellungshalle.csv",
        "IWU Sports Facilities":  "Turnhalle.csv",
        "IWU Hotels, Boarding, Restaurants or Catering":  "Hotelzimmer.csv",
        "IWU Production, Workshop, Warehouse or Operations": "ProduktionGrob.csv",
        "IWU Trade Buildings": "Fachgeschaeft.csv", 
        "IWU Technical and Utility (supply and disposal)":  "Lagerhalle.csv",
        "IWU Transport": "Parkhaus.csv",
        "IWU Generalized (1) Services building": "office.csv",
        "IWU Generalized (2) Production buildings":  "Lagerhalle.csv"
        }

    #scheduleName = type_assignment.get(building_type)
    scheduleName = getBuildingType(term=building_type, kind="SIA")
    if scheduleName is None:
        print(f"No schedule for building type {building_type}")
        return None, None

    dataDirPath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    data_path = os.path.join(dataDirPath, 'data', 'occupancy_schedules', f'{scheduleName}.csv')

    try:
        data_schedule = pd.read_csv(data_path, sep=',')
        return data_schedule, scheduleName
    except FileNotFoundError:
        print(f"File not found: {data_path}")
        return None, None

def adjust_schedule(inital_day, schedule, nb_days):
    """
    Function returns the schedule, 
    adjusted to the initial_day and the last 
    """
    # Create a custom sorter index
    sorter = rotate_list(initial_day=inital_day)
    sorter_index = {day: index for index, day in enumerate(sorter)}

    # Create a copy of the schedule DataFrame
    schedule_copy = schedule.copy()

    # Use the copy for modifications
    schedule_copy['DAY'] = pd.Categorical(schedule_copy['DAY'], categories=sorter, ordered=True)
    schedule_copy = schedule_copy.sort_values(by=['DAY', 'HOUR'])
    schedule_copy = expand_dataframe(schedule_copy, total_days=nb_days)
    return schedule_copy


def rotate_list(initial_day):
    # Number of days in the schedule
    lst = [0 , 1, 2, 3, 4, 5, 6]
    # Find the index of the start day
    start_index = lst.index(initial_day)
    # Rotate the list from that index
    return lst[start_index:] + lst[:start_index]



def expand_dataframe(df, total_days):
    unique_days = df['DAY'].unique()
    num_days = len(unique_days)
    
    # Calculate the number of full weeks and extra days needed
    full_cycles = total_days // num_days
    extra_days = total_days % num_days
    
    # Replicate the DataFrame for the number of full cycles
    result_df = pd.concat([df] * full_cycles, ignore_index=True)
    
    # If there are extra days, append the needed days from a new cycle
    if extra_days > 0:
        extra_data = df[df['DAY'].isin(unique_days[:extra_days])]
        result_df = pd.concat([result_df, extra_data], ignore_index=True)
    
    return result_df

def get_tek(building_type):
    """
    Returns the TEK Values, according to the building type.

    All data (not only the ones used) are in: data\TEKs\TEK_NWG_Vergleichswerte.csv

    returns dataframe and schedule name
    :return: df_schedule, schedule_name
    :rtype: DataFrame (with floats), string
    """
    tek_assignment = {
        "oag": "Bürogebäude",
        "IWU Research and University Teaching": "Hochschule und Forschung (allgemein)",
        "IWU Health and Care": "Beherbergungsstätten (allgemein)",
        "IWU School, Day Nursery and other Care": "Schulen",
        "IWU Culture and Leisure": "Ausstellungsgebäude",
        "IWU Sports Facilities": "Sporthallen",
        "IWU Hotels, Boarding, Restaurants or Catering": "Hotels / Pensionen",
        "IWU Production, Workshop, Warehouse or Operations": "Gewerbliche und industrielle Gebäude – Mischung aus leichter u. schwerer Arbeit",
        "IWU Trade Buildings": "Verkaufsstätten (allgemein)",
        "IWU Generalized (1) Services building": "Verwaltungsgebäude (allgemein)",
        "IWU Generalized (2) Production buildings": "Gewerbliche und industrielle Gebäude – Mischung aus leichter u. schwerer Arbeit"
    }

    #tek_name = tek_assignment.get(building_type)
    tek_name = getBuildingType(kind="TEK", term=building_type)
    if tek_name is None:
        print(f"No schedule for building type {building_type}")
        return None, None

    data_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    data_path = os.path.join(data_dir_path, 'data', 'TEKs', 'TEK_districtgenerator.csv')

    try:
        data_schedule = pd.read_csv(data_path, sep=',',)
        warm_water_value = data_schedule[data_schedule["TEK"] == tek_name]["TEK Warmwasser"].iloc[0]
        print(f"Das ist der Wert {warm_water_value}")
        return warm_water_value, tek_name
    except FileNotFoundError:
        print(f"File not found: {data_path}")
        return None, None
    except IndexError:
        print(f"No data available for {tek_name}")
        return None, None
    

def get_multi_zone_average(building_type):
    """
    
    """
    multi_zone_name = getBuildingType(kind="TEK", term=building_type)
    if tek_name is None:
        print(f"No schedule for building type {building_type}")
        return None, None

    data_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    data_path = os.path.join(data_dir_path, 'data', 'TEKs', 'TEK_districtgenerator.csv')

    try:
        data_schedule = pd.read_csv(data_path, sep=',',)
        warm_water_value = data_schedule[data_schedule["TEK"] == tek_name]["TEK Warmwasser"].iloc[0]
        print(f"Das ist der Wert {warm_water_value}")
        return warm_water_value, tek_name
    except FileNotFoundError:
        print(f"File not found: {data_path}")
        return None, None
    except IndexError:
        print(f"No data available for {tek_name}")
        return None, None

if __name__ == '__main__':
    schedule, name = get_schedule('oag')
    if schedule is not None:
        print(f"Loaded schedule {name}")
        print(schedule)