# -*- coding: utf-8 -*-
"""Interaktive Anbindung des PFA-Profilgenerators an die Distrikt-Erstellung.

Die Industrie ist ein SEPARATES Standortobjekt, kein Gebäude mit Wärmebedarf.
Die spätere Netzanbindung / Einspeiseoptimierung ist hier bewusst noch nicht
implementiert. Alle Abwärme- und Quellenprofile werden szenariospezifisch gesichert.

Pfadkonfiguration: siehe Umgebungsvariable PFA_SOURCE_DIR unten.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from pathlib import Path
import importlib
import io
import math
import os

import numpy as np
import pandas as pd



PFA_SOURCE_DIR = str(Path(__file__).resolve().parents[1]/ "data"/ "WZ2025_Vorbereitung"/ "Quellenklassifikation_final")

# Die Zuordnung der Profilgruppen zu WZ-Codes stammt aus der bereitgestellten
# Gruppentabelle. Die Kurznamen sind beschreibende Anzeige-Titel, keine
# eigenständigen amtlichen WZ-Schlüssel oder amtlichen Experimentgruppennamen.
PFA_GROUPS = {
    "G48": ("47.1, 47.2", "Einzelhandel"),
    "G43": ("35.1, 35.3", "Energie- und Wärmeversorgung"),
    "G62": ("22.2", "Kunststoffwaren"),
    "G59": ("86.1", "Krankenhausversorgung"),
    "G10": ("11.0", "Getränkeherstellung"),
    "G39": ("29.1, 29.3", "Kraftfahrzeuge und Fahrzeugteile"),
    "G52": ("52.1", "Lagerwirtschaft"),
    "G06": ("10.4, 10.6, 10.8", "Nahrungsmittel: Öle, Mühlen, Sonstiges"),
    "G20": ("20.1", "Chemische Grundstoffe"),
    "G32": ("25.5", "Oberflächenveredlung und Metallbearbeitung"),
    "G45": ("38.2, 38.3", "Abfallverwertung und -beseitigung"),
    "G25": ("23.2, 23.3, 23.4", "Keramische Erzeugnisse"),
    "G38": ("28.1, 28.2, 28.4, 28.9", "Maschinenbau"),
    "G31": ("25.1, 25.4, 25.6, 25.9", "Metallerzeugnisse und Metallbearbeitung"),
    "G21": ("20.3, 20.4, 20.5, 20.6", "Weitere chemische Erzeugnisse"),
    "G47": ("46.3", "Lebensmittel-Großhandel"),
    "G04": ("10.1, 10.2", "Fleisch- und Fischverarbeitung"),
    "G07": ("10.5", "Milchverarbeitung"),
    "G29": ("24.1, 24.3, 24.4", "Metallerzeugung und -verarbeitung"),
    "G16": ("17.1", "Papier und Zellstoff"),
}


def _find_source_dir() -> Path:
    if PFA_SOURCE_DIR:
        chosen = Path(PFA_SOURCE_DIR).expanduser().resolve()
        if not chosen.is_dir():
            raise FileNotFoundError(
                "PFA_SOURCE_DIR verweist auf kein Verzeichnis:\n"
                f"  {chosen}\n"
                "Erwartet wird 'Quellenklassifikation_final'."
            )
        return chosen

    current = Path(__file__).resolve()
    relative = Path("WZ2025_Vorbereitung") / "Quellenklassifikation_final"
    possibilities = [
        Path.cwd() / relative,
        current.parents[2] / relative,
        current.parents[1] / relative,
        Path.cwd() / "Quellenklassifikation_final",
        ]
    for path in possibilities:
        if path.is_dir():
            return path.resolve()
    raise FileNotFoundError(
        "PFA-Datenordner nicht gefunden. Setze PFA_SOURCE_DIR auf den "
        "vollständigen Pfad zu 'Quellenklassifikation_final'.\n"
        "Der Ordner muss Generator_Datenpakete_Iteration4 und "
        "KI_Standortgroesse_Recherche_v2 enthalten."
    )


def _get_generator():
    """Bestehenden Generator benutzen, ohne dessen Dateinamen zu ändern."""
    generator = importlib.import_module("districtgenerator.functions.pfa_profile_generieren")
    source_dir = _find_source_dir()
    generator.SOURCE_DIR = source_dir
    generator.GENERATOR_PACKAGE_DIR = source_dir / "Generator_Datenpakete_Iteration4"
    generator.SIZE_INFO_DIR = (
            source_dir / "KI_Standortgroesse_Recherche_v2" / "Einzelgruppen_fertig"
    )
    # Die Szenariodateien werden unten mit eindeutigen Namen gespeichert;
    # ein zusätzlicher Schreibzugriff in generische SYN_Gxx_0001-Ordner entfällt.
    generator.SAVE_OUTPUT_FILES = False
    return generator


def _ask_yes_no(question: str, *, default: bool | None = None) -> bool:
    suffix = " [J/n]" if default is True else " [j/N]" if default is False else " [j/n]"
    while True:
        text = input(question + suffix + ": ").strip().casefold()
        if not text and default is not None:
            return default
        if text in ("j", "ja", "y", "yes", "1"):
            return True
        if text in ("n", "nein", "no", "0"):
            return False
        print("  Bitte j oder n eingeben.")


def _ask_number(question: str, *, minimum: float = 0, maximum: float | None = None,
                strictly_positive: bool = False) -> float:
    while True:
        raw = input(question + ": ").strip().replace(" ", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            print("  Bitte eine Zahl eingeben (z. B. 12,5).")
            continue
        if not math.isfinite(value) or value < minimum or (strictly_positive and value <= 0) or (
                maximum is not None and value > maximum
        ):
            end = f" und {maximum:g}" if maximum is not None else ""
            print(f"  Erlaubter Bereich: {minimum:g}{end}." if not strictly_positive
                  else "  Der Wert muss positiv sein.")
            continue
        return value


def _format_size(value, unit: str) -> str:
    if value is None or not np.isfinite(value):
        return "k. A."
    if unit.casefold().replace(" ", "") in {"kwh/a", "kwh/jahr"}:
        return f"{value / 1e6:.3g} GWh/a"
    return f"{value:,.3g} {unit}".strip()


def _print_group_size_ranges(group_id: str) -> None:
    """Alle vorhandenen Größenkennzahlen für Score 0–10 und 90–100 anzeigen."""
    generator = _get_generator()
    print("\nORIENTIERUNG ZUR STANDORTGRÖSSE")
    print("  Mittelwerte in den Scorebereichen 0–10 bzw. 90–100.")
    try:
        with redirect_stdout(io.StringIO()):
            stats = generator.summarize_group_size_extremes(group_id)
    except (FileNotFoundError, ValueError, KeyError) as error:
        print(f"  Keine vollständige KI-Größenstatistik verfügbar: {error}")
        print("  Modus Jahresabwärme bleibt dennoch möglich, sofern Generator-Daten vorliegen.")
        return

    print(f"  Standorte mit KI-Score: {stats['scored_site_count']} "
          f"(unten n={stats['low_score_site_count']}, "
          f"oben n={stats['high_score_site_count']})")
    table = stats["table"]
    if table.empty:
        print("  Keine numerischen Größenkennzahlen vorhanden.")
        return

    for (kind, label, unit), group in table.groupby(
            ["Kennzahltyp", "Kennzahl", "Einheit"], sort=False, dropna=False
    ):
        values = {}
        for _, row in group.iterrows():
            v = row["Mittelwert_oder_Ersatzwert"]
            rendered = _format_size(v, str(unit))
            if pd.notna(row["Ersatz_Score"]):
                rendered += f" (Ersatz: Score {row['Ersatz_Score']:g})"
            rendered += f" [n={row['Anzahl_Standorte']}]"
            values[row["Scorebereich"]] = rendered
        print(f"  {label} [{kind}]")
        print(f"    Score 0–10:   {values.get('UNTEN_0_10', 'k. A.')} ")
        print(f"    Score 90–100: {values.get('OBEN_90_100', 'k. A.')} ")


def ask_industry_request() -> dict | None:
    """Nach den normalen Quartierabfragen optionale Industrieparameter erfragen."""
    print("\n" + "=" * 76)
    print("INDUSTRIELLE ABWÄRME – OPTIONALER ZUSÄTZLICHER STANDORT")
    print("=" * 76)
    if not _ask_yes_no("Industrieanlage mit Abwärme hinzufügen?", default=False):
        return None

    print("\nVERFÜGBARE PROFILGRUPPEN (WZ 2025)")
    for group_id, (codes, label) in PFA_GROUPS.items():
        print(f"  {group_id:4} | WZ {codes:<23} | {label}")
    print("  (Die Gruppenkurznamen sind beschreibend; maßgeblich sind die WZ-Codes.)")

    while True:
        group_id = input("\nProfilgruppe (z. B. G62): ").strip().upper()
        if group_id.isdecimal():
            group_id = "G" + group_id
        if group_id in PFA_GROUPS:
            break
        print("  Ungültige Gruppe. Bitte eine oben angezeigte Kennung auswählen.")

    # Prüfungen erfolgen vor den weiteren Eingaben: frühzeitig hilfreiche Fehler.
    generator = _get_generator()
    group_package = generator.GENERATOR_PACKAGE_DIR / group_id
    if not group_package.is_dir():
        raise FileNotFoundError(
            f"Für {group_id} wurde kein Generator-Datenpaket gefunden: {group_package}"
        )

    distance_m = _ask_number(
        "Entfernung Industrie–Quartiersrand (Luftlinie, Meter)", minimum=0
    )
    _print_group_size_ranges(group_id)

    print("\nAUSWAHLMETHODE")
    print("  1 = KI-Größenscore 0–100 mit Toleranz")
    print("  2 = Jahresabwärmemenge mit Toleranz")
    while True:
        mode = input("Methode [1/2]: ").strip()
        if mode in ("1", "2"):
            break
        print("  Bitte 1 oder 2 eingeben.")

    if mode == "1":
        size_score = _ask_number("Gewünschter KI-Größenscore (0–100)", minimum=0, maximum=100)
        score_tolerance = _ask_number("Toleranz (± Scorepunkte)", minimum=0)
        use_association = _ask_yes_no(
            "Standorte ohne Score per robuster Abwärmeassoziation ergänzen?", default=True
        )
        exclude_outliers = _ask_yes_no(
            "Auffällige Abwärmeausreißer aus dem Pool ausschließen?", default=True
        )
        selection = {
            "size_score": size_score,
            "score_tolerance": score_tolerance,
            "use_heat_association": use_association,
            "exclude_heat_outliers": exclude_outliers,
        }
    else:
        annual_gwh = _ask_number(
            "Gewünschte Jahresabwärme [GWh/a]", minimum=0, strictly_positive=True
        )
        tolerance_gwh = _ask_number("Toleranz (± GWh/a)", minimum=0)
        exclude_outliers = _ask_yes_no(
            "Auffällige Abwärmeausreißer aus dem Pool ausschließen?", default=False
        )
        selection = {
            "annual_heat_kwh": annual_gwh * 1e6,
            "heat_tolerance_kwh": tolerance_gwh * 1e6,
            "exclude_heat_outliers": exclude_outliers,
        }

    return {"group_id": group_id, "distance_m": distance_m,
            "selection": selection, "group_label": PFA_GROUPS[group_id][1],
            "wz_codes": PFA_GROUPS[group_id][0]}


def _position_outside_district(distance_m: float, roads, buildings_info) -> dict:
    """Industriepunkt östlich der räumlichen Quartier-Hüllrechteckgrenze.

    Punktabstand zur Ostkante entspricht exakt distance_m. Es wird weder
    Industriegrundstücksfläche noch Wärmenetzanschluss vorweggenommen.
    """
    points = []
    for road in roads:
        points.extend(list(road.coords))
    for building in buildings_info:
        points.extend(list(building["polygon"].exterior.coords))
    if not points:
        raise ValueError("Keine Straßen-/Gebäudepositionen zur Industriestandort-Platzierung.")
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    east = max(xs)
    north, south = max(ys), min(ys)
    cy = (north + south) / 2.0
    return {"position": [east + distance_m, cy],
            "reference_point_district_edge": [east, cy],
            "distance_m": float(distance_m),
            "distance_definition": "Luftlinie zur Ostkante des Quartier-Huellrechtecks"}


def create_industry_site(request: dict | None, roads, buildings_info) -> dict | None:
    """Empirisches Standortprofil ziehen und räumlich separat positionieren."""
    if request is None:
        return None
    generator = _get_generator()
    result = generator.generate_realistic_site(
        group_id=request["group_id"], **request["selection"]
    )
    geometry = _position_outside_district(request["distance_m"], roads, buildings_info)
    site = {
        "id": "industry_001",
        "group_id": request["group_id"],
        "group_label": request["group_label"],
        "wz_codes": request["wz_codes"],
        "position_data": geometry,
        "profile_result": result,
    }
    print("\n" + "=" * 76)
    print("GEZOGENER INDUSTRIESTANDORT")
    print("=" * 76)
    print(f"  Profilgruppe:                  {site['group_id']} – {site['group_label']}")
    print(f"  Empirischer Standort (ID):    {result['basis_site_id']}")
    print(f"  Standortauswahl:              {result['selection_mode']}")
    print(f"  Zufallspool:                  {result['selection_candidate_count']} Standorte")
    print(f"  Direkte Treffer im Fenster:   {result['matching_sites_in_window']}")
    print(f"  Zusätzlich über Abwärme:      {result['associated_sites_by_heat']}")
    print(f"  Fallback auf nächsten Wert:   {result['fallback_to_nearest']}")
    print(f"  Gewählte Auswahlherkunft:     {result['selected_site_selection_origin']}")
    print(f"  Jahresabwärme:                {result['generated_site_heat_kWh_a'] / 1e6:.3g} GWh/a")
    print(f"  Quellenanzahl:                {len(result['q_types'])}")
    print(f"  Entfernung zum Quartier:      {request['distance_m']:g} m")
    print(f"  Position (m):                 {geometry['position']}")
    print("  Quellenübersicht:")
    for i, source in enumerate(result["sources"], start=1):
        heat = float(source["Waermemenge_kWh_a"]) / 1e6
        temp = source.get("Temperatur_C")
        temp_string = f"{float(temp):.1f} °C" if temp is not None and np.isfinite(temp) else "k. A."
        print(f"    {i:2}: {source['Quellklasse_Code']}, {heat:.3g} GWh/a, "
              f"{temp_string}, {source.get('Betriebsprofil_Code', 'k. A.')}")
    print("=" * 76)
    return site


def show_industry_on_plot(ax, site: dict | None) -> None:
    """Standortpunkt mit bloßer Distanzreferenz, KEINE Wärmenetzleitung."""
    if site is None:
        return
    loc = site["position_data"]
    x, y = loc["position"]
    edge_x, edge_y = loc["reference_point_district_edge"]
    ax.plot([edge_x, x], [edge_y, y], linestyle=":", color="darkorange", linewidth=1.5)
    ax.plot(x, y, marker="D", color="darkorange", markersize=12,
            markeredgecolor="black", markeredgewidth=1.0)
    ax.annotate(f"Industrie {site['group_id']}\n{loc['distance_m']:g} m",
                xy=(x, y), xytext=(7, 7), textcoords="offset points",
                fontsize=10, color="darkorange")


def save_industry_site(site: dict | None, save_dir, scenario_stem: str) -> dict | None:
    """Szenariobezogene Profile speichern; nur referenzierbare Daten ins JSON."""
    if site is None:
        return None
    folder = Path(save_dir)
    folder.mkdir(parents=True, exist_ok=True)
    result = site["profile_result"]
    basename = f"{scenario_stem}_{site['id']}"
    profile_filename = f"{basename}_profiles.npz"
    sources_filename = f"{basename}_sources.csv"
    np.savez_compressed(
        folder / profile_filename,
        source_profiles=np.asarray(result["source_profiles"], dtype=np.float64),
        site_profile=np.asarray(result["site_profile"], dtype=np.float64),
        q_types=np.asarray(result["q_types"], dtype=str),
        source_ids=np.asarray(result["source_ids"], dtype=str),
        basis_site_id=np.asarray([result["basis_site_id"]], dtype=str),
        timestamps=np.asarray(result["time_index"].astype(str), dtype=str),
        )
    result["source_metadata"].to_csv(
        folder / sources_filename, sep=";", index=False, encoding="utf-8-sig"
    )

    # Profildaten in kWh je Stunde (bei 1h-Auflösung gleich mittlere kW).
    entry = {
        "id": site["id"],
        "type": "industrial_waste_heat_source",
        "group_id": site["group_id"],
        "group_label": site["group_label"],
        "wz2025_codes": site["wz_codes"],
        "position": site["position_data"]["position"],
        "distance_to_district_m": site["position_data"]["distance_m"],
        "distance_definition": site["position_data"]["distance_definition"],
        "reference_point_district_edge": site["position_data"]["reference_point_district_edge"],
        "basis_site_id": str(result["basis_site_id"]),
        "n_sources": int(len(result["q_types"])),
        "q_types": [str(q) for q in result["q_types"]],
        "yearly_waste_heat_kwh": float(result["generated_site_heat_kWh_a"]),
        "profile_file": profile_filename,
        "sources_file": sources_filename,
        "profile_resolution_hours": 1,
        "selection_mode": result["selection_mode"],
        "selection_target": float(result["selection_target"]),
        "selection_tolerance": float(result["selection_tolerance"]),
        "selection_candidate_count": int(result["selection_candidate_count"]),
        "matching_sites_in_window": int(result["matching_sites_in_window"]),
        "associated_sites_by_heat": int(result["associated_sites_by_heat"]),
        "fallback_to_nearest": bool(result["fallback_to_nearest"]),
        "selected_site_selection_origin": str(result["selected_site_selection_origin"]),
        "use_heat_association": bool(result["use_heat_association"]),
        "exclude_heat_outliers": bool(result["exclude_heat_outliers"]),
        "heat_outliers_removed_global": int(result["outliers_removed_global"]),
        "heat_outliers_removed_score_residual": int(result["outliers_removed_score_residual"]),
        "connected_to_heat_network": False,
    }
    return entry
