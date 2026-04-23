from pathlib import Path
import pandas as pd



def load_timeseries_dict_nested(
    district1: str,
    district2: str,
    district3: str,
    base_path: str = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results",
) -> dict:
    """
    Ergebnisstruktur:
    timeseries_dict[district][column][year][cluster][step] = value
    plus:
    timeseries_dict[district]["total_demand"][year][cluster][step] = value
    """
    districts = [district1, district2, district3]
    timeseries_dict = {}

    dev = ["PV", "HP", "BAT", "EB", "BBOI", "BCHP", "Power_Demand_kW"]

    for district in districts:
        file_path = Path(base_path) / f"{district}_devices_power_timeseries.csv"
        if not file_path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

        df = pd.read_csv(file_path, sep=";")
        timeseries_dict[district] = {}

        for _, row in df.iterrows():
            year = int(row["Support_Year"])
            cluster = int(row["Cluster"])
            step = int(row["Timestep"])

            # Alle CSV-Spalten in die neue Struktur schreiben
            for col in df.columns:
                value = float(row[col]) if pd.notna(row[col]) else 0.0
                timeseries_dict[district].setdefault(col, {}) \
                                       .setdefault(year, {}) \
                                       .setdefault(cluster, {})[step] = round(value, 3)

            # total_demand berechnen (PV wird abgezogen)
            total = 0.0
            for d in dev:
                v = float(row[d]) if d in df.columns and pd.notna(row[d]) else 0.0
                total += -v if d == "PV" else v

            timeseries_dict[district].setdefault("total_demand", {}) \
                                   .setdefault(year, {}) \
                                   .setdefault(cluster, {})[step] = round(total, 3)

    return timeseries_dict


def balance_total_demand(timeseries_dict: dict, district1: str, district2: str, district3: str) -> dict:
    """
    Bilanzierung pro (year, cluster, step):
    - genau 1 abgebendes Quartier: total_demand < 0
    - 1 aufnehmendes Quartier: bekommt den vollen negativen Wert
    - 2 aufnehmende Quartiere: bekommen jeweils die Hälfte
    - abgebendes Quartier wird danach auf 0 gesetzt
    """
    districts = [district1, district2, district3]

    def get_val(d, key, y, c, s):
        return float(
            timeseries_dict.get(d, {})
            .get(key, {})
            .get(y, {})
            .get(c, {})
            .get(s, 0.0)
        )

    def set_val(d, key, y, c, s, value):
        timeseries_dict.setdefault(d, {}) \
            .setdefault(key, {}) \
            .setdefault(y, {}) \
            .setdefault(c, {})[s] = round(float(value), 3)

    # Alle vorhandenen Koordinaten sammeln
    coords = set()
    for d in districts:
        td = timeseries_dict.get(d, {}).get("total_demand", {})
        for y, clusters in td.items():
            for c, steps in clusters.items():
                for s in steps.keys():
                    coords.add((y, c, s))

    for y, c, s in coords:
        # Netzwerkflüsse für diesen Zeitschritt initialisieren
        for d in districts:
            set_val(d, "to_network", y, c, s, 0.0)
            set_val(d, "from_network", y, c, s, 0.0)
            set_val(d, "to_main_grid", y, c, s, 0.0)

        values = {d: get_val(d, "total_demand", y, c, s) for d in districts}
        senders = [d for d, v in values.items() if v < 0]

        # Nur Fall: genau ein Sender
        if len(senders) != 1:
            continue

        sender = senders[0]
        receivers = [d for d in districts if d != sender and values[d] > 0]

        if not receivers:
            continue

        available = -values[sender]  # positive Menge
        transferred_total = 0.0
        recv_transfer = {d: 0.0 for d in receivers}

        if len(receivers) == 1:
            r = receivers[0]
            need = max(0.0, values[r])
            t = min(available, need)

            recv_transfer[r] = t
            transferred_total = t

        elif len(receivers) == 2:
            r1, r2 = receivers
            need1 = max(0.0, values[r1])
            need2 = max(0.0, values[r2])

            # 50/50 Start
            half = available / 2.0
            t1 = min(half, need1)
            t2 = min(half, need2)

            rem = available - (t1 + t2)

            # Rest verteilen
            add1 = min(rem, need1 - t1)
            t1 += add1
            rem -= add1

            add2 = min(rem, need2 - t2)
            t2 += add2
            rem -= add2

            recv_transfer[r1] = t1
            recv_transfer[r2] = t2
            transferred_total = t1 + t2

        # Receiver aktualisieren
        for r, t in recv_transfer.items():
            set_val(r, "total_demand", y, c, s, values[r] - t)
            set_val(r, "from_network", y, c, s, t)
        # Sender aktualisieren
        new_sender_td = values[sender] + transferred_total   # bleibt <= 0
        set_val(sender, "total_demand", y, c, s, values[sender] + transferred_total)
        set_val(sender, "to_network", y, c, s, transferred_total)

        # Restüberschuss -> Hauptnetz
        to_main_grid = max(0.0, available - transferred_total)
        set_val(sender, "to_main_grid", y, c, s, to_main_grid)

    return timeseries_dict

def add_network_totals(timeseries_dict: dict, cluster_weights: dict) -> dict:
    """
    Setzt pro District und Year:
    - from_network_total
    - to_network_total

    Formel:
    total = Summe über alle cluster, steps von
            network_value[year][cluster][step] * cluster_weights[district][cluster]
    """
    mappings = [
        ("from_network", "from_network_total"),
        ("to_network", "to_network_total"),
    ]

    for district, district_data in timeseries_dict.items():
        if district not in cluster_weights:
            raise KeyError(f"Fehlende Gewichte für District '{district}'")

        cw = cluster_weights[district]

        for source_key, target_key in mappings:
            source = district_data.get(source_key, {})
            district_data.setdefault(target_key, {})

            for year, clusters in source.items():
                total = 0.0

                for cluster, steps in clusters.items():
                    if cluster in cw:
                        weight = cw[cluster]
                    elif str(cluster) in cw:
                        weight = cw[str(cluster)]
                    else:
                        raise KeyError(
                            f"Fehlendes Gewicht für District '{district}', Cluster '{cluster}'"
                        )

                    for _, value in steps.items():
                        total += float(value) * float(weight)

                district_data[target_key][year] = round(total, 3)

    return timeseries_dict




def save_network_timeseries_to_csv(
    timeseries_dict: dict,
    output_path: str = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results\network_balance_timeseries.csv",
) -> str:
    rows = []

    for district, data in timeseries_dict.items():
        td = data.get("total_demand", {})
        tn = data.get("to_network", {})
        fn = data.get("from_network", {})
        tmg = data.get("to_main_grid", {})

        # Koordinaten aus allen 4 Strukturen sammeln
        coords = set()
        for src in (td, tn, fn, tmg):
            for year, clusters in src.items():
                for cluster, steps in clusters.items():
                    for step in steps.keys():
                        coords.add((int(year), int(cluster), int(step)))

        for year, cluster, step in sorted(coords):
            rows.append(
                {
                    "district": district,
                    "Support_Year": year,
                    "Cluster": cluster,
                    "Timestep": step,
                    "total_demand": round(float(td.get(year, {}).get(cluster, {}).get(step, 0.0)), 3),
                    "to_network": round(float(tn.get(year, {}).get(cluster, {}).get(step, 0.0)), 3),
                    "from_network": round(float(fn.get(year, {}).get(cluster, {}).get(step, 0.0)), 3),
                    "to_main_grid": round(float(tmg.get(year, {}).get(cluster, {}).get(step, 0.0)), 3),
                }
            )

    df_out = pd.DataFrame(rows).sort_values(["district", "Support_Year", "Cluster", "Timestep"])
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, sep=";", index=False)
    return output_path

if __name__ == "__main__":
    cluster_weights = {
    "ghd6": {0: 5, 1: 20, 2: 12, 3: 15},
    "residential2": {0: 6, 1: 20, 2: 11, 3: 15},
    "mixed1": {0: 5, 1: 22, 2: 10, 3: 15}
    }
    timeseries_dict = load_timeseries_dict_nested("ghd6", "residential2", "mixed1")
    timeseries_dict = balance_total_demand(timeseries_dict, "ghd6", "residential2", "mixed1")
    timeseries_dict = add_network_totals(timeseries_dict, cluster_weights)
    td = timeseries_dict["mixed1"]["to_main_grid"][0]
    #print(td)
    csv_file = save_network_timeseries_to_csv(timeseries_dict)
    print(f"Gespeichert: {csv_file}")
