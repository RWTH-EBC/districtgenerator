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
        "IWU School, Day Nursery and other Care": "Klassenzimmer (Schule), Gruppenraum.csv",
        "IWU Culture and Leisure": "Ausstellungsräume und Museum.csv",
        "IWU Sports Facilities":  "Turnhalle.csv",
        "IWU Hotels, Boarding, Restaurants or Catering":  "Hotelzimmer.csv",
        "IWU Production, Workshop, Warehouse or Operations": "Gewerbliche und industrielle Hallen – mittel.csv",
        "IWU Trade Buildings": "Einzelhandel/Kaufhaus.csv", 
        "IWU Technical and Utility (supply and disposal)":  "Gewerbliche und industrielle Hallen – schwer.csv",
        "IWU Transport": "Parkhaus (Büro- und Privatnutzung).csv",
        "IWU Generalized (1) Services building": "office.csv",
        "IWU Generalized (2) Production buildings":  "Gewerbliche und industrielle Hallen – mittel.csv"
    }

    schedule_name = type_assignment.get(building_type)
    if schedule_name is None:
        print(f"No schedule for building type {building_type}")
        return None, None

    data_dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    data_path = os.path.join(data_dir_path, 'data', 'occupancy_schedules', schedule_name)

    try:
        data_schedule = pd.read_csv(data_path)
        return data_schedule, schedule_name
    except FileNotFoundError:
        print(f"File not found: {data_path}")
        return None, None

if __name__ == '__main__':
    schedule, name = get_schedule('oag')
    if schedule is not None:
        print(f"Loaded schedule {name}")
        print(schedule)