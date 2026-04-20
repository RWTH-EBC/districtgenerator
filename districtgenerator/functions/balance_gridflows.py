from pathlib import Path
import pandas as pd


def load_timeseries_dict(
    district1: str,
    district2: str,
    district3: str,
    base_path: str = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results"
) -> dict:
    """
    Lädt drei CSV-Dateien (<district>_devices_power_timeseries.csv) und speichert sie
    in einem 2-stufigen Dictionary:
    
    timeseries_dict[district][column_name] -> Liste der Werte in dieser Spalte
    """
    timeseries_dict = {}
    districts = [district1, district2, district3]

    for district in districts:
        file_path = Path(base_path) / f"{district}_devices_power_timeseries.csv"

        if not file_path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

        # Deine CSVs sind mit Semikolon getrennt
        df = pd.read_csv(file_path, sep=";")

        # 2. Ebene = Spaltennamen aus der CSV
        timeseries_dict[district] = {
            col: df[col].tolist() for col in df.columns
        }

    return timeseries_dict

def add_total_demand(timeseries_dict: dict) -> dict:
    dev = ["PV", "HP", "BAT", "EB", "BBOI", "Power_Demand_kW"]

    for district in timeseries_dict:
        # Länge der Zeitreihe aus der ersten vorhandenen Spalte bestimmen
        first_col = next(iter(timeseries_dict[district]))
        n = len(timeseries_dict[district][first_col])

        total = [0.0] * n

        for d in dev:
            # Falls Spalte im District fehlt -> mit 0 auffüllen
            series = timeseries_dict[district].get(d, [0.0] * n)
            sign = -1.0 if d == "PV" else 1.0
            # elementweise addieren
            total = [t + sign * float(s) for t, s in zip(total, series)]

        timeseries_dict[district]["total_demand"] = total

    return timeseries_dict

if __name__ == "__main__":
    timeseries_dict = load_timeseries_dict(
    district1="ghd6",
    district2="residential2",
    district3="mixed1")

    timeseries_dict = add_total_demand(timeseries_dict)
    print(timeseries_dict["mixed1"]["total_demand"][:5])
