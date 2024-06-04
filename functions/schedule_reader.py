import os
import pandas as pd

def get_schedule(building_type):
    """
    Returns the schedules from SIA, according to the building type.

    All schedules (not only the ones used) are in: data\\occupancy_schedules

    returns dataframe and schedule name
    :return: df_schedule, schedule_name
    :rtype: DataFrame (with floats), string
    """
    type_assignment = {
        "oag": "office.csv",
        "IWU Research and University Teaching": "Hörsaal, Auditorium.csv",
        "IWU Health and Care": "Bettenzimmer.csv", 
        "IWU School, Day Nursery and other Care": "KSchulzimmer_Hoersaal.csv",
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

    schedule_name = type_assignment.get(building_type)
    if schedule_name is None:
        print(f"No schedule for building type {building_type}")
        return None, None

    data_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    data_path = os.path.join(data_dir_path, 'data', 'occupancy_schedules', schedule_name)

    try:
        data_schedule = pd.read_csv(data_path, sep=';')
        return data_schedule, schedule_name
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

    # Apply sorting
    schedule['DAY'] = pd.Categorical(schedule['DAY'], categories=sorter, ordered=True)
    schedule.sort_values(by=['DAY', 'HOUR'], inplace=True)
    schedule = expand_dataframe(schedule, total_days=nb_days)
    return schedule 


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



if __name__ == '__main__':
    schedule, name = get_schedule('oag')
    if schedule is not None:
        print(f"Loaded schedule {name}")
        print(schedule)