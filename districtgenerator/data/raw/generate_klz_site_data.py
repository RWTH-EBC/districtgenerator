import pandas as pd
import numpy as np

# 1. Laden der Site Data
file_path = 'site_data.txt'
# Datei wird als Tab-separated eingelesen (Annahme basierend auf .txt Struktur)
df = pd.read_csv(file_path, sep='\t')

df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')

# 2. Definition der VDI 2078 Referenzstationen (aus der Norm/PDF)
# Zone 1: Küste (Kühl)
# Zone 2: Norddeutsches Tiefland / Mittelgebirge (Gemäßigt)
# Zone 3: Östliches Binnenland / Stadtklima (Warm/Kontinental)
# Zone 4: Oberrheingraben / Südwest (Heiß)

vdi_stations = {
    # Name: (Lat, Lon, KLZ)
    "Rostock": (54.18, 12.08, 1),
    "Bremerhaven": (53.53, 8.58, 2), # Oft Zone 2 an der Nordseeübergang
    "Hamburg": (53.55, 9.99, 2),
    "Potsdam": (52.39, 13.06, 3),
    "Berlin": (52.52, 13.40, 3), # Großstadtzentrum oft 3 oder 4
    "Mannheim": (49.48, 8.46, 4),
    "Stuttgart": (48.77, 9.18, 4),
    "Frankfurt": (50.11, 8.68, 4),
    "Essen": (51.45, 7.01, 3), # Ruhrgebiet oft 3
    "Düsseldorf": (51.22, 6.77, 3),
    "Kassel": (51.31, 9.48, 2),
    "Braunlage": (51.72, 10.61, 3), # Harz
    "Chemnitz": (50.82, 12.92, 3),
    "Hof": (50.32, 11.92, 2), # Kälter
    "Fichtelberg": (50.43, 12.95, 1), # Hochlage -> Zone 1 (oder Sonderfall)
    "München": (48.13, 11.58, 2), # Oder 3 je nach Stadtlage, VDI oft 2 (Flughafen)
    "Passau": (48.57, 13.43, 3),
    "Freiburg": (47.99, 7.84, 4),
    "Trier": (49.75, 6.63, 4),
    "Würzburg": (49.79, 9.95, 4),
    "Ulm": (48.40, 9.99, 2),
    "Hannover": (52.37, 9.73, 2),
    "Leipzig": (51.33, 12.37, 3),
    "Dresden": (51.05, 13.73, 3),
    "Köln": (50.93, 6.96, 4), # Kölner Bucht oft Zone 4
    "Saarbrücken": (49.23, 6.99, 3),
}

# DataFrame der VDI Stationen erstellen
vdi_df = pd.DataFrame.from_dict(vdi_stations, orient='index', columns=['Lat', 'Lon', 'KLZ'])

def find_nearest_klz(row):
    """
    Findet die geographisch nächste VDI Station und gibt deren KLZ zurück.
    Nutzt vereinfachte euklidische Distanz (reicht für Zonen-Zuordnung in DE).
    """
    if pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
        return 3  # Default KLZ
    dists = np.sqrt((vdi_df['Lat'] - row['Latitude'])**2 + (vdi_df['Lon'] - row['Longitude'])**2)
    nearest_station = dists.idxmin()
    return vdi_df.loc[nearest_station, 'KLZ']

def find_nearest_city_name(row):
    if pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
        return "Default"
    dists = np.sqrt((vdi_df['Lat'] - row['Latitude'])**2 + (vdi_df['Lon'] - row['Longitude'])**2)
    return dists.idxmin()

# 3. Anwenden auf den Datensatz
df['KLZ'] = df.apply(find_nearest_klz, axis=1)
df['Ref_City'] = df.apply(find_nearest_city_name, axis=1)

# Sortieren für bessere Übersicht (optional)
df.sort_values(by='Zip', inplace=True)

# 4. Ergebnis anzeigen
print(df.head(10))

# Speichern (Optional)
df.to_csv('site_data_with_KLZ.txt', sep='\t', index=False)