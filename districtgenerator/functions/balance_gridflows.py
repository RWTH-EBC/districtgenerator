from decimal import Decimal
from pathlib import Path
import pandas as pd
import os
import csv

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
        ("to_grid", "to_grid_total"),
        ("Power_Demand_kW", "Power_Demand_kW_total")
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

                district_data[target_key][year] = total/1000.0  # kWh -> MWh

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
        fg= data.get("from_grid", {})
        tg= data.get("to_grid", {})
        rows = []
        coords = set()

        for src in (td, tn, fn, tmg, fmg, fg, tg):
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
                    "total_demand": round(float(td.get(year, {}).get(cluster, {}).get(step, 0.0)), 4),
                    "to_network": round(float(tn.get(year, {}).get(cluster, {}).get(step, 0.0)), 4),
                    "from_network": round(float(fn.get(year, {}).get(cluster, {}).get(step, 0.0)), 4),
                    "to_main_grid": round(float(tmg.get(year, {}).get(cluster, {}).get(step, 0.0)), 4),
                    "from_main_grid": round(float(fmg.get(year, {}).get(cluster, {}).get(step, 0.0)), 4),
                    "from_grid": round(float(fg.get(year, {}).get(cluster, {}).get(step, 0.0)), 4),
                    "to_grid": round(float(tg.get(year, {}).get(cluster, {}).get(step, 0.0)), 4),
                }
            )

        df_out = pd.DataFrame(rows).sort_values(["Support_Year", "Cluster", "Timestep"])

        file_path = output_dir / f"{district}_network_balance_timeseries.csv"
        df_out.to_csv(file_path, sep=";", index=False)
        saved_files.append(str(file_path))

    return saved_files


def save_network_timeseries_per_district_weights(
    timeseries_dict: dict,
    cluster_weights: dict,
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
        fg = data.get("from_grid", {})
        tg = data.get("to_grid", {})

        rows = []
        coords = set()

        for src in (td, tn, fn, tmg, fmg, fg, tg):
            for year, clusters in src.items():
                for cluster, steps in clusters.items():
                    for step in steps.keys():
                        coords.add((int(year), int(cluster), int(step)))

        cw_d = cluster_weights.get(district, {})

        for year, cluster, step in sorted(coords):
            if cluster in cw_d:
                weight = float(cw_d[cluster])
            elif str(cluster) in cw_d:
                weight = float(cw_d[str(cluster)])
            else:
                raise KeyError(f"Fehlendes cluster_weight für {district}, cluster {cluster}")

            from_grid_val = float(fg.get(year, {}).get(cluster, {}).get(step, 0.0))
            from_grid_weighted = from_grid_val * weight

            rows.append(
                {
                    "Support_Year": year,
                    "Cluster": cluster,
                    "Timestep": step,
                    "total_demand": float(td.get(year, {}).get(cluster, {}).get(step, 0.0)),
                    "to_network": float(tn.get(year, {}).get(cluster, {}).get(step, 0.0)),
                    "from_network": float(fn.get(year, {}).get(cluster, {}).get(step, 0.0)),
                    "to_main_grid": float(tmg.get(year, {}).get(cluster, {}).get(step, 0.0)),
                    "from_main_grid": float(fmg.get(year, {}).get(cluster, {}).get(step, 0.0)),
                    "from_grid": from_grid_val,
                    "to_grid": float(tg.get(year, {}).get(cluster, {}).get(step, 0.0)),
                    "cluster_weight": weight,
                    "from_grid_x_cluster_weight": from_grid_weighted,
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
        "to_grid_total",
        "Power_Demand_kW_total"
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
                    "from_network_total": round(float(district_data.get("from_network_total", {}).get(year, 0.0)), 4),
                    "to_network_total": round(float(district_data.get("to_network_total", {}).get(year, 0.0)), 4),
                    "from_main_grid_total": round(float(district_data.get("from_main_grid_total", {}).get(year, 0.0)), 4),
                    "to_main_grid_total": round(float(district_data.get("to_main_grid_total", {}).get(year, 0.0)), 4),
                    "from_grid_total": round(float(district_data.get("from_grid_total", {}).get(year, 0.0)), 4),
                    "to_grid_total": round(float(district_data.get("to_grid_total", {}).get(year, 0.0)), 4),
                    "Power_Demand_kW_total": round(float(district_data.get("Power_Demand_kW_total", {}).get(year, 0.0)), 4),
                }
            )

    df = pd.DataFrame(rows).sort_values(["district", "Support_Year"])
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep=";", index=False)

    return output_path



def _to_year_dict(value, years):
    """
    Normalisiert value auf dict[year] = float.
    Unterstützt dict, list/tuple, numpy-array-ähnlich, Skalar.
    """
    if isinstance(value, dict):
        return {int(y): float(value.get(y, 0.0)) for y in years}

    try:
        seq = list(value)
        return {int(y): float(seq[i]) if i < len(seq) else 0.0 for i, y in enumerate(years)}
    except TypeError:
        return {int(y): float(value) for y in years}


def _read_metric_by_year_from_result_csv(csv_path, category, metric):
    """
    Liest aus Ergebnis-CSV (Semikolon-getrennt) Werte nach Jahr:
    scenario;category;metric;device;year;value;unit
    """
    out = {}
    with open(csv_path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row.get("category") == category and row.get("metric") == metric:
                y_raw = row.get("year", "").strip()
                v_raw = row.get("value", "").strip()
                if y_raw == "" or v_raw == "":
                    continue
                try:
                    out[int(float(y_raw))] = float(v_raw)
                except ValueError:
                    continue
    return out





def rebalance_ghg_emissions(
    timeseries_dict: dict,
    district_csv_paths: dict,
    years: list,
    grid_ef_by_year: dict,
    result_dir: str = "optimization_results",
    filename: str = "ghg_rebalanced.csv",
    ):
    """
    Liest die Basis-CO2-Emissionen je Quartier/Jahr aus den CSV-Dateien:
      category = "optimization"
      metric   = "co2_sum_distr_year"

    Berechnet dann:
      ghg_new = ghg_base - (grid_ef * from_network_total)

    Speichert Ergebnisse in:
      timeseries_dict[district]["ghg_rebalanced_by_year"][year]
    und als CSV.
    """
    os.makedirs(result_dir, exist_ok=True)
    csv_path = os.path.join(result_dir, filename)

    rows = [[
        "district", "year", "co2_base", "grid_ef",
        "from_network_total", "deduction", "co2_rebalanced"
    ]]

    for district, csv_file in district_csv_paths.items():
        base_co2_by_year = _read_metric_by_year_from_result_csv(
            csv_file, category="optimization", metric="co2_sum_distr_year"
        )

        ts_d = timeseries_dict.get(district, {})
        fnt_raw = ts_d.get("from_network_total", {})

        from_network_by_year = _to_year_dict(fnt_raw, years)
        ts_d.setdefault("ghg_rebalanced_by_year", {})

        for y in years:
            base_co2 = float(base_co2_by_year.get(y, 0.0))
            fnt = float(from_network_by_year.get(y, 0.0))
            ef = float(grid_ef_by_year.get(y, 0.0))

            deduction = ef * fnt
            ghg_new = base_co2 - deduction

            ts_d["ghg_rebalanced_by_year"][int(y)] = ghg_new

            rows.append([
                district, y,
                round(base_co2, 4),
                round(ef, 4),
                round(fnt, 4),
                round(deduction, 4),
                round(ghg_new, 4),
            ])

        timeseries_dict[district] = ts_d

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(rows)

    print(f"THG-Neubewertung gespeichert: {csv_path}")
    return timeseries_dict, csv_path

def recalculate_lcoe_by_year(
    timeseries_dict,
    district_csv_paths,
    years,
    p_stromaustausch_verbundnetz,  # neu: Zeitreihe (dict/list), Skalar bleibt erlaubt
    p_einspeisung_hauptnetz,       # neu: Zeitreihe (dict/list), Skalar bleibt erlaubt
    p_strombezug_hauptnetz,        # neu: Zeitreihe (dict/list), Skalar bleibt erlaubt
    is_network,
    result_dir="Main-tja/optimization_results/timeseries",
    filename="lcoe_adjusted_by_year.csv",
):
    """
    Berechnet LCOE je Quartier/Jahr neu und speichert:
      - timeseries_dict[district]["LCOE_adjusted_by_year"][year]
      - CSV-Datei im result_dir

    Preise können als dict/list (Zeitreihe) oder Skalar übergeben werden.
    """
    os.makedirs(result_dir, exist_ok=True)
    out_path = os.path.join(result_dir, filename)

    # Preise in €/kWh -> €/MWh
    p_verbund_by_year = {y: 1000.0 * v for y, v in _to_year_dict(p_stromaustausch_verbundnetz, years).items()}
    p_feed_in_by_year = {y: 1000.0 * v for y, v in _to_year_dict(p_einspeisung_hauptnetz, years).items()}
    p_main_grid_by_year = {y: 1000.0 * v for y, v in _to_year_dict(p_strombezug_hauptnetz, years).items()}


    rows = [[
        "district", "year", "TAC", "TAC_adjusted_EUR/a","heat_demand_MWh", "Power_Demand_MWh",
        "from_network_total_MWh", "to_network_total_MWh",
        "p_stromaustausch_verbundnetz_EUR_per_MWh",
        "p_einspeisung_hauptnetz_EUR_per_MWh",
        "p_strombezug_hauptnetz_EUR_per_MWh",
        "is_network", "LCOE_adjusted_EUR_per_MWh"
    ]]

    for district, csv_path in district_csv_paths.items():
        tac_by_year = _read_metric_by_year_from_result_csv(
            csv_path, category="optimization", metric="tac_per_distr_year"
        )
        heat_by_year = _read_metric_by_year_from_result_csv(
            csv_path, category="yearly_totals", metric="total_heat_demand_by_year"
        )

        ts_d = timeseries_dict.get(district, {})
        power_by_year = _to_year_dict(ts_d.get("Power_Demand_kW_total", {}), years)
        from_net_by_year = _to_year_dict(ts_d.get("from_network_total", {}), years)
        to_net_by_year = _to_year_dict(ts_d.get("to_network_total", {}), years)

        ts_d.setdefault("LCOE_adjusted_by_year", {})
        ts_d.setdefault("TAC_adjusted_by_year", {})

        for y in years:
            tac = float(tac_by_year.get(y, 0.0))
            heat = float(heat_by_year.get(y, 0.0))
            power = float(power_by_year.get(y, 0.0))
            from_net = float(from_net_by_year.get(y, 0.0))
            to_net = float(to_net_by_year.get(y, 0.0))

            p_verbund = float(p_verbund_by_year.get(y, 0.0))
            p_feed_in = float(p_feed_in_by_year.get(y, 0.0))
            p_main_grid = float(p_main_grid_by_year.get(y, 0.0))

            denom = heat + power
            if denom <= 0:
                lcoe = 0.0
            else:
                if is_network:
                    tac_new = tac
                else:
                    tac_new = (
                        tac
                        - from_net * (p_main_grid - p_verbund)
                        - to_net * (p_verbund - p_feed_in)
                    )
                lcoe = tac_new / denom
            ts_d["TAC_adjusted_by_year"][int(y)] = tac_new
            ts_d["LCOE_adjusted_by_year"][int(y)] = lcoe

            rows.append([
                district, y,
                round(tac, 4), round(tac_new, 4), round(heat, 4), round(power, 4),
                round(from_net, 4), round(to_net, 4),
                round(p_verbund, 4), round(p_feed_in, 4), round(p_main_grid, 4),
                bool(is_network), round(lcoe, 4)
            ])

        timeseries_dict[district] = ts_d

    with open(out_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerows(rows)

    print(f"Angepasste LCOE gespeichert: {out_path}")
    return timeseries_dict, out_path




def write_adjusted_metrics_to_district_csvs(
    timeseries_dict: dict,
    district_csv_paths: dict,
    is_network: bool,
    output_dir: str = r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results\updated",
    rename_co2_metric_to_ghg_new: bool = True,
    keep_metric_name_lcoe_year: bool = True,
    suffix: str = "_adjusted",
) -> list[str]:
    """
    Schreibt je Quartier eine neue CSV und ersetzt:
    - Wenn is_network == True: nur optimization / LCOE_year
    - Sonst: optimization / co2_sum_distr_year, optimization / LCOE_year
            und yearly_totals / Stromfluss-Metriken
    """
    os.makedirs(output_dir, exist_ok=True)
    written_files: list[str] = []

    yearly_totals_mapping = {
        "from_el_grid_total": "from_grid_total",
        "to_el_grid_total": "to_grid_total",
        "from_el_main_grid_total": "from_main_grid_total",
        "to_el_main_grid_total": "to_main_grid_total",
        "from_network_total": "from_network_total",
        "to_network_total": "to_network_total",
    }

    for district, in_path in district_csv_paths.items():
        in_file = Path(in_path)
        out_file = Path(output_dir) / f"{in_file.stem}{suffix}{in_file.suffix}"

        district_ts = timeseries_dict.get(district, {})
        ghg_by_year = district_ts.get("ghg_rebalanced_by_year", {})
        lcoe_by_year = district_ts.get("LCOE_adjusted_by_year", {})
        tac_by_year = district_ts.get("TAC_adjusted_by_year", {})

        with open(in_file, "r", newline="", encoding="utf-8") as f_in:
            reader = csv.DictReader(f_in, delimiter=";")
            fieldnames = reader.fieldnames or ["scenario", "category", "metric", "device", "year", "value", "unit"]
            rows = list(reader)

        for row in rows:
            category = row.get("category")
            metric = row.get("metric")
            y_raw = (row.get("year") or "").strip()

            if y_raw == "":
                continue

            try:
                y = int(float(y_raw))
            except ValueError:
                continue

            if category == "optimization":
                if metric == "LCOE_year" and y in lcoe_by_year:
                    row["value"] = f"{float(lcoe_by_year[y]):.10f}"
                    if not keep_metric_name_lcoe_year:
                        row["metric"] = "LCOE_adjusted_year"

                elif not is_network and metric == "co2_sum_distr_year" and y in ghg_by_year:
                    row["value"] = f"{float(ghg_by_year[y]):.6f}"
                    if rename_co2_metric_to_ghg_new:
                        row["metric"] = "ghg_new"

                elif not is_network and metric == "tac_per_distr_year" and y in tac_by_year:
                    row["value"] = f"{float(tac_by_year[y]):.6f}"


            elif not is_network and category == "yearly_totals" and metric in yearly_totals_mapping:
                ts_key = yearly_totals_mapping[metric]
                value_by_year = district_ts.get(ts_key, {})
                if y in value_by_year:
                    row["value"] = f"{float(value_by_year[y]):.6f}"

        with open(out_file, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

        written_files.append(str(out_file))

    return written_files





if __name__ == "__main__":

    #scenario_name1 = "residential0"
    scenario_name2 = "residential2"
    #scenario_name3 = "residential3"
    scenario_name3 ="mixed1"
    scenario_name1 = "ghd6"
    is_network = False

    # Real
    cluster_weights = {
    "ghd6": {0: 5, 1: 20, 2: 12, 3: 15},
    "mixed1": {0: 6, 1: 20, 2: 11, 3: 15},
    "residential2": {0: 5, 1: 22, 2: 10, 3: 15},
    #"residential0": {0: 10, 1: 22, 2: 11, 3: 9},
    #"residential3": {0: 5, 1: 22, 2: 10, 3: 15},
    }

    # Test
    # cluster_weights = {
    # "ghd6": {0: 5, 1: 20, 2: 12, 3: 15},
    # "mixed1": {0: 5, 1: 20, 2: 12, 3: 15},
    # "residential2": {0: 5, 1: 20, 2: 12, 3: 15},
    #"residential0": {0: 5, 1: 20, 2: 12, 3: 15},
    #"residential3": {0: 5, 1: 20, 2: 12, 3: 15},
    # }


    timeseries_dict = load_timeseries_dict_nested(scenario_name1, scenario_name2, scenario_name3)
    #timeseries_dict = balance_total_demand(timeseries_dict, "ghd6", "residential2", "mixed1")
    timeseries_dict=balance_total_demand_multi_sender(timeseries_dict, scenario_name1, scenario_name2, scenario_name3, round_decimals=5)
    timeseries_dict = add_network_totals(timeseries_dict, cluster_weights)

    csv_file = save_network_timeseries_per_district_weights(timeseries_dict, cluster_weights)
    print(f"Gespeichert: {csv_file}")
    total_file = save_totals_to_csv(timeseries_dict)


    years = [0, 5, 10, 15, 20]

    district_csv_paths = {
        "ghd6": r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results\ghd6_network_results.csv",
        "residential2": r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results\residential2_network_results.csv",
        "mixed1": r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results\mixed1_network_results.csv",
        #"residential0": r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results\residential0_network_results.csv",
        #"residential3": r"d:\cwu-tja\districtgenerator\Main-tja\optimization_results\residential3_network_results.csv",
    }

    grid_ef_by_year = {
        0: 0.328,
        5: 0.103,
        10: 0.049,
        15: 0.027,
        20: 0.0,
    }

    timeseries_dict, ghg_csv = rebalance_ghg_emissions(
        timeseries_dict=timeseries_dict,
        district_csv_paths=district_csv_paths,
        years=[0, 5, 10, 15, 20],
        grid_ef_by_year=grid_ef_by_year,
        result_dir=r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results\timeseries",
        filename="ghg_rebalanced.csv",
    )

    #Preise in €/kWh

    p_stromaustausch_verbundnetz = {0: 0.1069, 5: 0.0979, 10: 0.0939, 15: 0.0869, 20: 0.0869}
    p_einspeisung_hauptnetz      = {0: 0.0794, 5: 0.0794, 10: 0.0794, 15: 0.0794, 20: 0.0794}
    p_strombezug_hauptnetz       = {0: 0.1590, 5: 0.1410, 10: 0.1330, 15: 0.1190, 20: 0.1190}



    timeseries_dict, lcoe_csv = recalculate_lcoe_by_year(
        timeseries_dict=timeseries_dict,
        district_csv_paths=district_csv_paths,
        years=years,
        p_stromaustausch_verbundnetz=p_stromaustausch_verbundnetz,
        p_einspeisung_hauptnetz=p_einspeisung_hauptnetz,
        p_strombezug_hauptnetz=p_strombezug_hauptnetz,
        is_network=is_network,
    )

    updated_files = write_adjusted_metrics_to_district_csvs(
        timeseries_dict=timeseries_dict,
        district_csv_paths=district_csv_paths,
        is_network=is_network,
        output_dir=r"D:\cwu-tja\districtgenerator\Main-tja\optimization_results\updated",
        rename_co2_metric_to_ghg_new=False,
        keep_metric_name_lcoe_year=True,
        suffix="",
    )
    print(updated_files)