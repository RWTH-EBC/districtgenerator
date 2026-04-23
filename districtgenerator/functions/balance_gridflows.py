from decimal import Decimal
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
                                       .setdefault(cluster, {})[step] = value

            # total_demand berechnen (PV wird abgezogen)
            total = 0.0
            for d in dev:
                v = float(row[d]) if d in df.columns and pd.notna(row[d]) else 0.0
                total += -v if d == "PV" else v

            timeseries_dict[district].setdefault("total_demand", {}) \
                                   .setdefault(year, {}) \
                                   .setdefault(cluster, {})[step] = total

    return timeseries_dict



def balance_total_demand_multi_sender(timeseries_dict: dict, district1: str, district2: str, district3: str,  round_decimals: int | None = None,) -> dict:
    districts = [district1, district2, district3]
    eps = Decimal("1e-12")

    def dval(x) -> Decimal:
        return Decimal(str(x))

    def get_val(d, key, y, c, s):
        return dval(
            timeseries_dict.get(d, {})
            .get(key, {})
            .get(y, {})
            .get(c, {})
            .get(s, 0.0)
        )
    
    def set_val(d, key, y, c, s, value):
        if round_decimals is None:
            out = float(value)
        else:
            out = round(float(value), round_decimals)

        timeseries_dict.setdefault(d, {}) \
            .setdefault(key, {}) \
            .setdefault(y, {}) \
            .setdefault(c, {})[s] = out

    # Koordinaten aus total_demand sammeln
    coords = set()
    for d in districts:
        for y, clusters in timeseries_dict.get(d, {}).get("total_demand", {}).items():
            for c, steps in clusters.items():
                for s in steps.keys():
                    coords.add((y, c, s))

    for y, c, s in coords:
        # Flüsse zurücksetzen
        for d in districts:
            set_val(d, "to_network", y, c, s, 0.0)
            set_val(d, "from_network", y, c, s, 0.0)
            set_val(d, "to_main_grid", y, c, s, 0.0)
            set_val(d, "from_main_grid", y, c, s, 0.0)
            set_val(d, "from_grid", y, c, s, 0.0)
            set_val(d, "to_grid", y, c, s, 0.0)

        td_orig = {d: get_val(d, "total_demand", y, c, s) for d in districts}
        surplus = {d: max(-td_orig[d], Decimal("0.0")) for d in districts}  # sendbar
        deficit = {d: max(td_orig[d], Decimal("0.0")) for d in districts}   # Bedarf

        senders = [d for d in districts if surplus[d] > eps]
        receivers = [d for d in districts if deficit[d] > eps]

        total_surplus = sum(surplus[d] for d in senders)
        total_deficit = sum(deficit[d] for d in receivers)

        sent = {d: Decimal("0") for d in districts}
        received = {d: Decimal("0") for d in districts}

        if total_surplus > eps and total_deficit > eps:
            if total_surplus >= total_deficit:
                # Receiver voll decken, Sender proportional belasten
                for r in receivers:
                    received[r] = deficit[r]
                for sdr in senders:
                    sent[sdr] = total_deficit * (surplus[sdr] / total_surplus)
            else:
                # Sender geben alles ab, Receiver proportional bedienen
                for sdr in senders:
                    sent[sdr] = surplus[sdr]
                for r in receivers:
                    received[r] = total_surplus * (deficit[r] / total_deficit)

        # Ergebnisse schreiben
        for d in districts:
            set_val(d, "to_network", y, c, s, sent[d])
            set_val(d, "from_network", y, c, s, received[d])

            # Restüberschuss ins Main Grid
            set_val(d, "to_main_grid", y, c, s, max(Decimal("0.0"), surplus[d] - sent[d]))

            # Restbedarf aus Main Grid
            set_val(d, "from_main_grid", y, c, s, max(Decimal("0.0"), deficit[d] - received[d]))

            # Summenflüsse
            set_val(
                d, "from_grid", y, c, s,
                get_val(d, "from_network", y, c, s) + get_val(d, "from_main_grid", y, c, s)
            )
            set_val(
                d, "to_grid", y, c, s,
                get_val(d, "to_network", y, c, s) + get_val(d, "to_main_grid", y, c, s)
            )

    return timeseries_dict



def balance_total_demand(timeseries_dict: dict, district1: str, district2: str, district3: str) -> dict:
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
            .setdefault(c, {})[s] = float(value)

    # Alle Koordinaten aus total_demand
    coords = set()
    for d in districts:
        for y, clusters in timeseries_dict.get(d, {}).get("total_demand", {}).items():
            for c, steps in clusters.items():
                for s in steps.keys():
                    coords.add((y, c, s))

    for y, c, s in coords:
        # Flüsse je Zeitschritt zurücksetzen
        for d in districts:
            set_val(d, "to_network", y, c, s, 0.0)
            set_val(d, "from_network", y, c, s, 0.0)
            set_val(d, "to_main_grid", y, c, s, 0.0)
            set_val(d, "from_main_grid", y, c, s, 0.0)
            set_val(d, "from_grid", y, c, s, 0.0)
            set_val(d, "to_grid", y, c, s, 0.0)

        # ORIGINALWERTE (werden nicht verändert)
        td_orig = {d: get_val(d, "total_demand", y, c, s) for d in districts}
        senders = [d for d, v in td_orig.items() if v < 0]

        if len(senders) == 1:
            sender = senders[0]
            receivers = [d for d in districts if d != sender and td_orig[d] > 0]

            available = -td_orig[sender]  # exportierbare Menge
            recv_transfer = {d: 0.0 for d in receivers}
            transferred_total = 0.0

            if len(receivers) == 1:
                r = receivers[0]
                t = min(available, td_orig[r])
                recv_transfer[r] = t
                transferred_total = t

            elif len(receivers) == 2:
                r1, r2 = receivers
                need1, need2 = td_orig[r1], td_orig[r2]

                half = available / 2.0
                t1 = min(half, need1)
                t2 = min(half, need2)

                rem = available - (t1 + t2)
                add1 = min(rem, need1 - t1)
                t1 += add1
                rem -= add1
                add2 = min(rem, need2 - t2)
                t2 += add2

                recv_transfer[r1] = t1
                recv_transfer[r2] = t2
                transferred_total = t1 + t2

            # Receiver: nur Flüsse setzen (total_demand bleibt unverändert)
            for r, t in recv_transfer.items():
                set_val(r, "from_network", y, c, s, t)

            # Sender-Flüsse
            set_val(sender, "to_network", y, c, s, transferred_total)
            set_val(sender, "to_main_grid", y, c, s, max(0.0, available - transferred_total))

        # from_main_grid aus ORIGINAL total_demand ableiten
        for d in districts:
            td = td_orig[d]
            fn = get_val(d, "from_network", y, c, s)
            if td > 0:
                set_val(d, "from_main_grid", y, c, s, max(0.0, td - fn))
            else:
                set_val(d, "from_main_grid", y, c, s, 0.0)
            set_val(d, "from_grid", y, c, s, get_val(d, "from_network", y, c, s) + get_val(d, "from_main_grid", y, c, s))
            set_val(d, "to_grid", y, c, s, get_val(d, "to_network", y, c, s) + get_val(d, "to_main_grid", y, c, s))

    return timeseries_dict
    
def add_network_totals(timeseries_dict: dict, cluster_weights: dict) -> dict:
    """
    Setzt pro District und Year:
    - from_network_total
    - to_network_total
    - from_main_grid_total
    - to_main_grid_total

    Formel:
    total = Summe über alle cluster, steps von
            network_value[year][cluster][step] * cluster_weights[district][cluster]
    """
    mappings = [
        ("from_network", "from_network_total"),
        ("to_network", "to_network_total"),
        ("from_main_grid", "from_main_grid_total"),
        ("to_main_grid", "to_main_grid_total"),
        ("from_grid", "from_grid_total"),
        ("to_grid", "to_grid_total")
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
                        total += float(value) * float(weight)/1000.0  # kWh -> MWh

                district_data[target_key][year] = total

    return timeseries_dict



def save_network_timeseries_per_district(
    timeseries_dict: dict,
    output_dir: str = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results\timeseries",
) -> list[str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for district, data in timeseries_dict.items():
        td = data.get("total_demand", {})
        tn = data.get("to_network", {})
        fn = data.get("from_network", {})
        tmg = data.get("to_main_grid", {})
        fmg = data.get("from_main_grid", {})
        rows = []
        coords = set()

        for src in (td, tn, fn, tmg, fmg):
            for year, clusters in src.items():
                for cluster, steps in clusters.items():
                    for step in steps.keys():
                        coords.add((int(year), int(cluster), int(step)))

        for year, cluster, step in sorted(coords):
            rows.append(
                {
                    "Support_Year": year,
                    "Cluster": cluster,
                    "Timestep": step,
                    "total_demand": round(float(td.get(year, {}).get(cluster, {}).get(step, 0.0)), 5),
                    "to_network": round(float(tn.get(year, {}).get(cluster, {}).get(step, 0.0)), 5),
                    "from_network": round(float(fn.get(year, {}).get(cluster, {}).get(step, 0.0)), 5),
                    "to_main_grid": round(float(tmg.get(year, {}).get(cluster, {}).get(step, 0.0)), 5),
                    "from_main_grid": round(float(fmg.get(year, {}).get(cluster, {}).get(step, 0.0)), 5),
                }
            )

        df_out = pd.DataFrame(rows).sort_values(["Support_Year", "Cluster", "Timestep"])

        file_path = output_dir / f"{district}_network_balance_timeseries.csv"
        df_out.to_csv(file_path, sep=";", index=False)
        saved_files.append(str(file_path))

    return saved_files



def save_totals_to_csv(
    timeseries_dict: dict,
    output_path: str = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results\timeseries\network_totals.csv",
) -> str:
    rows = []

    total_keys = [
        "from_network_total",
        "to_network_total",
        "from_main_grid_total",
        "to_main_grid_total",
        "from_grid_total",
        "to_grid_total"
    ]

    for district, district_data in timeseries_dict.items():
        years = set()
        for key in total_keys:
            years.update(district_data.get(key, {}).keys())

        for year in sorted(years):
            rows.append(
                {
                    "district": district,
                    "Support_Year": int(year),
                    "from_network_total": round(float(district_data.get("from_network_total", {}).get(year, 0.0)), 5),
                    "to_network_total": round(float(district_data.get("to_network_total", {}).get(year, 0.0)), 5),
                    "from_main_grid_total": round(float(district_data.get("from_main_grid_total", {}).get(year, 0.0)), 5),
                    "to_main_grid_total": round(float(district_data.get("to_main_grid_total", {}).get(year, 0.0)), 5),
                    "from_grid_total": round(float(district_data.get("from_grid_total", {}).get(year, 0.0)), 5),
                    "to_grid_total": round(float(district_data.get("to_grid_total", {}).get(year, 0.0)), 5),
                }
            )

    df = pd.DataFrame(rows).sort_values(["district", "Support_Year"])
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep=";", index=False)

    return output_path

if __name__ == "__main__":
    cluster_weights = {
    "ghd6": {0: 5, 1: 20, 2: 12, 3: 15},
    "residential2": {0: 6, 1: 20, 2: 11, 3: 15},
    "mixed1": {0: 5, 1: 22, 2: 10, 3: 15}
    }
    timeseries_dict = load_timeseries_dict_nested("ghd6", "residential2", "mixed1")
    #timeseries_dict = balance_total_demand(timeseries_dict, "ghd6", "residential2", "mixed1")
    timeseries_dict=balance_total_demand_multi_sender(timeseries_dict, "ghd6", "residential2", "mixed1", round_decimals=7)
    timeseries_dict = add_network_totals(timeseries_dict, cluster_weights)
    td = timeseries_dict["mixed1"]["to_main_grid"][0]
    #print(td)
    csv_file = save_network_timeseries_per_district(timeseries_dict)
    print(f"Gespeichert: {csv_file}")
    total_file = save_totals_to_csv(timeseries_dict)