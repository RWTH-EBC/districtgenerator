"""
Assignment of postal codes in Germany to data records of the test reference years
"""

import os
import openpyxl
from geopy import distance
from pyproj import Proj, transform, CRS, transformer
import pandas as pd



def extract_coordinates(filename):
    parts = filename.split('_')
    easting = int(parts[1][:7])
    northing = int(parts[1][7:])
    latitude, longitude = lambert_to_wgs84(easting, northing)

    return easting, northing, latitude, longitude

def read_folder(directory, start_filename):
    # Öffne die Excel-Datei nur einmal außerhalb der Schleife
    workbook = openpyxl.load_workbook("D:/Script/districtgenerator/data/geodata_TRY_10.xlsx")
    sheet = workbook.active

    # Setze den Startpunkt erreicht auf False, bis wir den Startdateinamen erreichen
    start_reached = False

    for filename in os.listdir(directory):
        if filename == start_filename:
            start_reached = True

        if start_reached:
            if filename.endswith('.dat'):
                filepath = os.path.join(directory, filename)
                easting, northing, latitude, longitude = extract_coordinates(filename)
                # Neue Zeile hinzufügen
                new_row = [filename, easting, northing, latitude, longitude]
                sheet.append(new_row)

    # Excel-Datei speichern, nachdem alle Dateien verarbeitet wurden
    workbook.save("D:/Script/districtgenerator/data/geodata_TRY_10.xlsx")


def lambert_to_wgs84(easting, northing):
    # Definiere das Lambert-Koordinatensystem (EPSG:3034)
    lambert = Proj(init='epsg:3034')

    # Definiere das WGS84-Koordinatensystem
    wgs84 = Proj(init='epsg:4326')

    # Transformiere die Koordinaten von Lambert nach WGS84
    longitude, latitude = transformer.transform(lambert, wgs84, easting, northing)

    return latitude, longitude

def match_points():
    # Lese die Daten aus der Excel-Datei für list1 ein
    # Hier den Dateinamen ändern
    df_list1 = pd.read_excel('D:\Script\districtgenerator\data\plz_geocoord_500.xlsx', header=None, names=['PLZ', 'Latitude', 'Longitude'], skiprows=1, dtype={'PLZ': str})

    # Lese die Daten aus der Excel-Datei für list2 ein
    df_list2 = pd.read_excel('D:\Script\districtgenerator\data\geodata_TRY_all.xlsx', usecols=[3,4], names=['Latitude', 'Longitude'], skiprows=1)

    matched_points = {}

    for index1, point1 in df_list1.iterrows():
        min_distance = float('inf')
        closest_point = None

        for index2, point2 in df_list2.iterrows():
            dist = distance.distance((point1[1], point1[2]), (point2[0], point2[1])).km
            if dist < min_distance:
                min_distance = dist
                closest_point = point2

        matched_points[index1] = closest_point
        print(point1[0])

    # Füge die Punkte mit dem kürzesten Abstand zu list1 hinzu
    for index, closest_point in matched_points.items():
        df_list1.at[index, 'Closest_Latitude'] = closest_point['Latitude']
        df_list1.at[index, 'Closest_Longitude'] = closest_point['Longitude']

    # Speichere die aktualisierten Daten zurück in die Excel-Datei für list1
    # Hier den Dateinamen ändern
    df_list1.to_excel('D:\Script\districtgenerator\data\plz_geocoord_matched_500.xlsx', index=False)

    return matched_points


#read_folder('D:\Script\districtgenerator\data\TRY_2015_mittel.tar\mittel', 'TRY2015_38615002933500_Jahr.dat')

match_points()



