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
    workbook = openpyxl.load_workbook("D:/Script/districtgenerator/data/plz_geocoord_matched_Test.xlsx")

    # Lese die Daten aus der Excel-Datei für list1 ein
    # Hier den Dateinamen ändern
    df_list1 = pd.read_excel('D:\Script\districtgenerator\data\plz_geocoord.xlsx', header=None, names=['PLZ', 'Latitude', 'Longitude'], skiprows=1, dtype={'PLZ': str})

    # Lese die Daten aus der Excel-Datei für list2 ein
    df_list2 = pd.read_excel('D:\Script\districtgenerator\data\geodata_TRY_all.xlsx', usecols=[0,3,4], names=['file_name', 'Latitude', 'Longitude'], skiprows=1)

    i=0
    for index1, point1 in df_list1.iterrows():
        min_distance = float('inf')
        closest_point = None

        for index2, point2 in df_list2.iterrows():
            dist = distance.distance((point1[1], point1[2]), (point2[1], point2[2])).km
            if dist < min_distance:
                min_distance = dist
                closest_point = point2

        sheet = workbook.active
        sheet.append([point1[0], point1[1], point1[2], closest_point[0], closest_point[1],closest_point[2]])
        print(point1[0])
        workbook.save("D:/Script/districtgenerator/data/plz_geocoord_matched_Test.xlsx")
        i += 1
        if i== 2: break


def delete_TRY_files():
    # DataFrame aus Excel-Datei lesen
    df_list1 = pd.read_excel('D:\Script\districtgenerator\data\plz_geocoord_matched.xlsx', usecols=[3], names=['filename'], skiprows=0)
    df_list1['filename'] = df_list1['filename'].str.slice(8, 22)
    df_list1['filename'] = "TRY2015_" + df_list1['filename'] + "_Wint.dat"

    # Pfad zum Ordner mit den Dateien
    folder_path = "D:\Script\districtgenerator\data\weather\TRY_2015_winterkalt.tar\winterkalt"

    # Dateinamen aus dem DataFrame in eine Liste konvertieren
    included_files = df_list1['filename'].tolist()

    # Durchsuchen des Ordners und Löschen nicht enthaltener Dateien
    for filename in os.listdir(folder_path):
        if filename not in included_files:
            file_path = os.path.join(folder_path, filename)
            os.remove(file_path)
            print(f"{filename} wurde gelöscht.")




#read_folder('D:\Script\districtgenerator\data\TRY_2015_mittel.tar\mittel', 'TRY2015_38615002933500_Jahr.dat')

#match_points()

delete_TRY_files()



