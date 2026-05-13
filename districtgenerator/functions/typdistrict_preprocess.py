import pandas as pd
import numpy as np
import random
import os

random_seed = int(input("\nEnter random seed: "))
random.seed(random_seed)
np.random.seed(random_seed)

# Read the Excel File
current_dir = os.path.dirname(__file__)
excel_file = os.path.join(current_dir, "..", "data", "typdistrict_parameters.xlsx")

# Settlement type options with descriptions
settlement_types = {
    "A": {
        "german": "Wohnplätze und Streusiedlungen",
        "english": "Residential places and scattered settlements"
    },
    "B": {
        "german": "Dörfer mit überwiegend Gehöften",
        "english": "Villages with mainly homesteads"
    },
    "C": {
        "german": "Ein- und Zweifamilienhaussiedlung niedriger Dichte",
        "english": "Single and two-family house settlements of low density"
    },
    "D": {
        "german": "Bausiedlung hoher Dichte und Dorfkern",
        "english": "Settlements with high density and village core"
    },
    "E": {
        "german": "Reihenhausbebauung",
        "english": "Row housing development"
    },
    "F": {
        "german": "Zeilenbebauung mittlerer Dichte",
        "english": "Row development with medium density"
    },
    "G": {
        "german": "Zeilenbebauung hoher Dichte und Hochhäuser",
        "english": "Row development of high density and high-rise buildings"
    },
    "H": {
        "german": "Blockbebauung",
        "english": "Block development"
    },
    "I": {
        "german": "Mittelalterliche Altstadt",
        "english": "Medieval old town"
    }
}

# ------------------------------
# Step 1. Choose a Settlement Type
# ------------------------------
print("Available settlement types:")
for key, desc in settlement_types.items():
    print(f"  {key}: {desc['german']} ({desc['english']})")

district_type = input("\nEnter the settlement type (A-I): ").strip().upper()

if district_type not in settlement_types:
    print(f"Invalid settlement type '{district_type}'. Please choose a valid option (A-I).")
    exit(1)

settlement_name_german = settlement_types[district_type]["german"]

print(f"\nYou selected: {settlement_name_german} ({settlement_types[district_type]['english']})")

# ------------------------------
# Step 2. Read the Excel File and Filter Data
# ------------------------------
df = pd.read_excel(excel_file, sheet_name=0)

df["Siedlungstyp"] = df["Siedlungstyp"].astype(str).str.strip()

# Filter the DataFrame for the desired settlement type.
filtered_df = df[df["Siedlungstyp"].str.contains(settlement_name_german, case=False, na=False)]

if filtered_df.empty:
    print(f"No matching settlement type found for '{settlement_name_german}'.")
    exit(1)

# Use the first matching row.
row = filtered_df.iloc[0]

# ------------------------------
# Step 3. Extract Randomly Select Parameters
# ------------------------------

def random_between(min_val, max_val):
    """Return a random value between min and max with formatting rules."""
    value = random.uniform(min_val, max_val)
    if max_val > 1:
        return int(round(value))  # Round and convert to integer if the value range is greater than 1
    return round(value, 2)       # Otherwise, round to two decimal places

def random_with_mean(mean, min_val, max_val, std_dev=None):
    """Generate a random value around a mean"""
    if std_dev is None:
        std_dev = 0.5 * mean  # Default standard deviation is 50% of the mean

    value = np.random.normal(mean, std_dev)
    if max_val > 1:
        return int(round(max(min(value, max_val), min_val)))  # Round and convert to integer if the value range is greater than 1
    return round(max(min(value, max_val), min_val), 2)        # Otherwise, round to two decimal places

params = {
    "geschoss_flaechenzahl": {
        "min": row["Min Geschoss-flächenzahl"],
        "max": row["Max Geschoss-flächenzahl"],
        "value": random_between(row["Min Geschoss-flächenzahl"], row["Max Geschoss-flächenzahl"])
    },
    "grund_flaechenzahl": {
        "min": row["Min Grund-flächenzahl"],
        "max": row["Max Grund-flächenzahl"],
        "value": random_between(row["Min Grund-flächenzahl"], row["Max Grund-flächenzahl"])
    },
    "gebaeude_pro_ha": {
        "min": row["Min Gebäude pro ha"],
        "max": row["Max Gebäude pro ha"],
        "value": random_between(row["Min Gebäude pro ha"], row["Max Gebäude pro ha"])
    },
    "leitungsabgaenge": {
        "mean_value": row["Mittelwert Anzahl der Leitungsabgänge je Netzstation"],
        "min": row["Min Anzahl der Leitungsabgänge je Netzstation"],
        "max": row["Max Anzahl der Leitungsabgänge je Netzstation"],
        "value": min(random_with_mean(row["Mittelwert Anzahl der Leitungsabgänge je Netzstation"],
                                  row["Min Anzahl der Leitungsabgänge je Netzstation"],
                                  row["Max Anzahl der Leitungsabgänge je Netzstation"]), 4)
    },
    "laenge_netzstrahlabschnitte": {
        "mean_value": row["Mittelwert Länge der Netzstrahlabschnitte (m)"],
        "min": row["Min Länge der Netzstrahlabschnitte (m)"],
        "max": row["Max Länge der Netzstrahlabschnitte (m)"],
        "value": random_with_mean(row["Mittelwert Länge der Netzstrahlabschnitte (m)"],
                                  row["Min Länge der Netzstrahlabschnitte (m)"],
                                  row["Max Länge der Netzstrahlabschnitte (m)"])
    },
    "abstand_hausanschluesse": {
        "mean_value": row["Mittelwert Abstand benachbarter Hausanschlüsse  (m)"],
        "min": row["Min Abstand benachbarter Hausanschlüsse  (m)"],
        "max": row["Max Abstand benachbarter Hausanschlüsse  (m)"],
        "value": random_with_mean(row["Mittelwert Abstand benachbarter Hausanschlüsse  (m)"],
                                  row["Min Abstand benachbarter Hausanschlüsse  (m)"],
                                  row["Max Abstand benachbarter Hausanschlüsse  (m)"])
    },
    "HA-Leitungen": {
        "min": row["Min HA-Leitungen (m)"],
        "max": row["Max HA-Leitungen (m)"],
        "value": random_between(row["Min HA-Leitungen (m)"],
                                row["Max HA-Leitungen (m)"])
    },
    "wohneinheiten": {
        "mean_value": row["Mittelwert Wohnheiten je Hausanschlus"],
        "min": row["Min Wohnheiten je Hausanschlus"],
        "max": row["Max Wohnheiten je Hausanschlus"],
        "value": random_with_mean(row["Mittelwert Wohnheiten je Hausanschlus"],
                                  row["Min Wohnheiten je Hausanschlus"],
                                  row["Max Wohnheiten je Hausanschlus"])
    },
    "seitenverhaeltnis": {
        "mean_value": row["Mittelwert Seitenverhältnis (B/L)"],
        "min": row["Min Seitenverhältnis (B/L)"],
        "max": row["Max Seitenverhältnis (B/L)"],
        "value": random_with_mean(row["Mittelwert Seitenverhältnis (B/L)"],
                                  row["Min Seitenverhältnis (B/L)"],
                                  row["Max Seitenverhältnis (B/L)"])
    },
    "flaeche_bezirk_m2": {
        "mean_value": row["Mittelwert Fläche des Bezirkes (ha)"] * 10000,  # Convert hectares to square meters
        "min": row["Min Fläche des Bezirkes (ha)"] * 10000,
        "max": row["Max Fläche des Bezirkes (ha)"] * 10000,
        "value": random_with_mean(row["Mittelwert Fläche des Bezirkes (ha)"] * 10000,
                                  row["Min Fläche des Bezirkes (ha)"] * 10000,
                                  row["Max Fläche des Bezirkes (ha)"] * 10000)
    },
    "lastangriffsfaktor_epsilon": round(row["Lastangriffsfaktor ε"], 2),
    "stdev_lastangriffsfaktor_sigma": round(row["stdev Lastangriffsfaktor σ"], 2),
    "gebaeudegrundflaeche_je_wohneinheit": int(row["Gebäudegrundfläche je Wohneinheit (m²)"]),
    "netzaufbau": row["Netzaufbau"],
    "share_non_residential": float(row["Nichtwohnnutzung (%)"]),
    "share_mixed_use": float(row["Mischnutzung (%)"]),
    "share_residential": float(row["Wohnnutzung (%)"]),
    "frequency_education": row["Häufigkeit Schule, Kindebetreuungsstätte"],
    "frequency_office_medical": row["Häufigkeit Büro, Praxis, Kanzlei"],
    "frequency_retail_service": row["Häufigkeit Einzelhandel und Dienstleistung"],
    "frequency_restaurant": row["Häufigkeit Gaststätte"],
    "frequency_workshop": row["Häufigkeit Handwerksbetrieb"],
    "frequency_agriculture": row["Häufigkeit Landwirtschaftlicher Betrieb"],

    "building_type_mapping": {
        "frequency_education": ["SC", "UNI"],
        "frequency_office_medical": ["OB", "HOSPITAL"],
        "frequency_retail_service": ["RETAIL", "GS"],
        "frequency_restaurant": ["RE"],
        "frequency_workshop": ["WORKSHOP"],
        "frequency_agriculture": ["WORKSHOP"]
    },

    "gebaeudealter": {
        "vor_1919": row["Gebäudealtersverteilung vor 1919 (%)"],
        "1919_1949": row["Gebäudealtersverteilung 1919 - 1949 (%)"],
        "1950_1959": row["Gebäudealtersverteilung 1950 - 1959 (%)"],
        "1960_1969": row["Gebäudealtersverteilung 1960 - 1969 (%)"],
        "1970_1979": row["Gebäudealtersverteilung 1970 - 1979 (%)"],
        "1980_1989": row["Gebäudealtersverteilung 1980 - 1989 (%)"],
        "1990_1999": row["Gebäudealtersverteilung 1990 - 1999 (%)"],
        "2000_2005": row["Gebäudealtersverteilung 2000 - 2005 (%)"],
        "2006_2009": row["Gebäudealtersverteilung 2006 - 2009 (%)"],
        "2010_2019": row["Gebäudealtersverteilung 2010 - 2019 (%)"]
    },

    "sanierung": {
        "unsaniert": row["Unsaniert (%)"],
        "teilsaniert": row["Teilsaniert (%)"],
        "vollsaniert": row["Vollsaniert (%)"]
    },

    "anzahl_vollgeschosse_0": row["Anzahl Vollgeschosse 0%"],
    "anzahl_vollgeschosse_25": row["Anzahl Vollgeschosse 25%"],
    "anzahl_vollgeschosse_50": row["Anzahl Vollgeschosse 50%"],
    "anzahl_vollgeschosse_75": row["Anzahl Vollgeschosse 75%"],
    "anzahl_vollgeschosse_100": row["Anzahl Vollgeschosse 100%"],

    "random_seed": random_seed,

}
