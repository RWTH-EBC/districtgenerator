import os
import pandas as pd

current_file_path = os.path.abspath(__file__)
base_path = os.path.dirname(os.path.dirname(current_file_path))

def getBuildingType(term, kind):
    """
    Retrieve the value from a specified column based on a match in the 'districtgenerator' column.
    
    Parameters:
    term (str): The term to match in the 'districtgenerator' column.
    kind (str): The column name from which to retrieve the value.
    
    Returns:
    str: The value from the specified column if a match is found; otherwise, None.
    """
    building_types_file  = os.path.join(base_path, 'data', 'building_types.csv')
    df = pd.read_csv(building_types_file, sep=';')
    # Check if the kind column exists
    if kind not in df.columns:
        raise ValueError(f"Column '{kind}' does not exist in the table.")
    
    # Find the row that matches the term in 'districtgenerator'
    match = df[df['districtgenerator'] == term]
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

    #scheduleName = type_assignment.get(building_type)
    scheduleName = getBuildingType(term=building_type, kind="SIA")
    if scheduleName is None:
        print(f"No schedule for building type {building_type}")
        return None, None
    
    data_path = os.path.join(base_path, 'data', 'occupancy_schedules', f'{scheduleName}.csv')

    try:
        data_schedule = pd.read_csv(data_path, sep=',')
        return data_schedule, scheduleName
    except FileNotFoundError:
        print(f"File not found: {data_path}")
        return None, None

def adjust_schedule(initial_day, schedule, nb_days):
    """
    Adjusts and expands a schedule based on an initial day and a specified number of days.

    This function performs the following operations:
    1. Rotates the days of the week to start from the specified initial day.
    2. Creates a copy of the input schedule to avoid modifying the original.
    3. Converts the 'DAY' column to a categorical type with the rotated order.
    4. Sorts the schedule by the new day order and hour.
    5. Expands the schedule to cover the specified number of days.

    Parameters:
    initial_day (int): The day of the week to start the schedule (0-6, where 0 is Monday).
    schedule (pd.DataFrame): The original schedule DataFrame with 'DAY' and 'HOUR' columns.
    nb_days (int): The total number of days the schedule should cover.

    Returns:
    pd.DataFrame: An adjusted and expanded copy of the input schedule.
    """
    # Create a custom sorter index
    sorter = rotate_list(initial_day=initial_day)

    # Create a copy of the schedule DataFrame
    schedule_copy = schedule.copy()

    # Use the copy for modifications
    schedule_copy['DAY'] = pd.Categorical(schedule_copy['DAY'], categories=sorter, ordered=True)
    schedule_copy = schedule_copy.sort_values(by=['DAY', 'HOUR'])
    schedule_copy = expand_dataframe(schedule_copy, total_days=nb_days)
    return schedule_copy

def rotate_list(initial_day):
    # Number of days in the schedule
    lst = [0, 1, 2, 3, 4, 5, 6]
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

    All data (not only the ones used) are in: data/TEKs/TEK_NWG_Vergleichswerte.csv

    returns dataframe and schedule name
    :return: df_schedule, schedule_name
    :rtype: DataFrame (with floats), string
    """
    #tek_name = tek_assignment.get(building_type)
    tek_name = getBuildingType(kind="TEK", term=building_type)
    if tek_name is None:
        print(f"No schedule for building type {building_type}")
        return None, None

    data_path = os.path.join(base_path, 'data', 'TEKs', 'TEK_districtgenerator.csv')

    try:
        data_schedule = pd.read_csv(data_path, sep=',',)
        warm_water_value = data_schedule[data_schedule["TEK"] == tek_name]["TEK Warmwasser"].iloc[0]
        return warm_water_value, tek_name
    except FileNotFoundError:
        print(f"File not found: {data_path}")
        return None, None
    except IndexError:
        print(f"No data about TEK available for {tek_name}")
        return None, None
    

def get_multi_zone_average(building_type):
    """
    Retrieves multi-zone average usage profiles for non-domestic buildings in Germany.

    This function fetches person and appliance gains data for a given building type
    from a CSV file containing multi-zone average usage profiles.

    Parameters:
    building_type (str): The type of building for which to retrieve data.

    Returns:
    tuple: A tuple containing three elements:
        - person_gains (float or None): The average person gains (q_I_p) for the building type.
        - app_gains (float or None): The average appliance gains (q_I_fac) for the building type.
        - multi_zone_name (str or None): The standardized name of the building type used in the dataset.

    If the building type is not found or there's an error reading the data, all returned values will be None.

    Raises:
    FileNotFoundError: If the CSV file containing the data is not found.
    IndexError: If no data is available for the specified building type.
    """
    multi_zone_name = getBuildingType(kind="MULTI_ZONE", term=building_type)
    if multi_zone_name is None:
        print(f"No schedule for building type {building_type}")
        return None, None, None

    data_path = os.path.join(base_path, 'data', 'multi_zone_average', 
                             'Non-domestic-multi-zone-average-usage-profiles-for-Germany.csv')
    
    try:
        data_schedule = pd.read_csv(data_path, sep=';', index_col=0)
        person_gains = data_schedule[data_schedule["Bez_HK_Enob_Eng"] == multi_zone_name]["q_I_p"].iloc[0]
        app_gains = data_schedule[data_schedule["Bez_HK_Enob_Eng"] == multi_zone_name]["q_I_fac"].iloc[0]
        return person_gains, app_gains, multi_zone_name
    except FileNotFoundError:
        print(f"File not found: {data_path}")
        return None, None, multi_zone_name
    except IndexError:
        print(f"No data about multi-zone average available for {building_type}")
        return None, None, multi_zone_name


def get_lightning_control(building_type):
    """
    Get Lichtausnutzungsgrad der Verglasung (lighting_control), 
    Lux threshold at which the light turns on
    Map 'E_m' from data_18599_10_4 to building_data
    """
    data_type = getBuildingType(kind='18599_lightning', term=building_type)
    

    # data_type = _assignment.get(building_type)
    if data_type is None:
        print(f"No schedule for building type {building_type}")
        return None, None

    maintenance_data_path = os.path.join(base_path, 'data', 'norm_profiles', '18599_10_4_data.csv')


    try:
        maintenance_data_schedule = pd.read_csv(maintenance_data_path, sep=';')
        lighntning_control = maintenance_data_schedule[maintenance_data_schedule["typ_18599"] == data_type]["E_m"].iloc[0]

        return  lighntning_control
    except FileNotFoundError:
        print(f"File not found: {maintenance_data_path}")
        return None
    except IndexError:
        print(f"No data about lighntning control available for {building_type} and data type {data_type}")
        return None


if __name__ == '__main__':
    person_gains, app_gains, name = get_multi_zone_average('IWU Trade Buildings')
    if person_gains is not None:
        print(f"Loaded schedule {person_gains}")
        print(person_gains)
