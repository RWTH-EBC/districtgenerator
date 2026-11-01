from pathlib import Path
import json
import re

import numpy as np
import pandas as pd


# =============================================================================
# REALISTISCHE 8760-STUNDEN-STANDORTPROFILE AUS EMPIRISCHEN PFA-DATEN
# =============================================================================
# Zwei Auswahlarten:
# (1) KI-Größenscore mit Scoretoleranz; optional erweiterbar um unbewertete
#     Standorte mit ±2 % Wärme eines Score-Referenzstandorts UND Nähe zur
#     robusten Regression log10(Jahreswärme) ~ KI-Score.
# (2) Jahresabwärme mit absoluter Wärmetoleranz in kWh/a.
# Eine weitere Funktion berichtet Größenkennzahlen für 0–10 und 90–100 Score.
# Die tatsächliche Abwärmemenge und das Quellenportfolio werden empirisch
# übernommen; je Quelle entsteht ein eigenes 8760-Stunden-Profil.
# Zufallsziehungen nutzen bei jedem Aufruf frische Betriebssystementropie.
# =============================================================================

# =============================================================================
# 1. KONFIGURATION
# =============================================================================

BASE_DIR = Path("WZ2025_Vorbereitung")

SOURCE_DIR = (
        BASE_DIR
        / "Quellenklassifikation_final"
)

GENERATOR_PACKAGE_DIR = (
        SOURCE_DIR
        / "Generator_Datenpakete_Iteration4"
)

OUTPUT_BASE_DIR = (
        SOURCE_DIR
        / "Generierte_Standortprofile_8760"
)



# -----------------------------------------------------------------------------
# Wie viele realistische Standorte pro Lauf erzeugen?
#
# Für deinen aktuellen Anwendungsfall:
#     1
#
# Später z. B.:
#     100
# -----------------------------------------------------------------------------

N_SITES_TO_GENERATE = 1


# -----------------------------------------------------------------------------
# Optional einen bestimmten realen Standort als Strukturvorlage verwenden.
#
# None:
#     zufällig einen Standort aus der Gruppe ziehen.
#
# Beispiel:
#     FIXED_BASIS_SITE_ID = "SV_..."
# -----------------------------------------------------------------------------

FIXED_BASIS_SITE_ID = None


# -----------------------------------------------------------------------------
# Absolute Jahreswärmemenge des generierten Standorts.
#
# None:
#     reale Q1-Q7-Jahreswärmemenge des gezogenen Standorts übernehmen.
#
# Beispiel:
#     TARGET_SITE_ANNUAL_HEAT_KWH = 10_000_000
#
# Dann werden nur die absoluten Quellengrößen skaliert.
# Portfolio und relative Quellenanteile bleiben empirisch.
# -----------------------------------------------------------------------------

TARGET_SITE_ANNUAL_HEAT_KWH = None


# KI-Dateien für Größenscore und externe Standortkennzahlen.
SIZE_INFO_DIR = SOURCE_DIR / "KI_Standortgroesse_Recherche_v2" / "Einzelgruppen_fertig"
SIZE_INFO_SHEET = "Standorte_KI"
SIZE_SCORE_COL = "KI_Relativer_Groessenscore_0_100"

HEAT_ASSOCIATION_RELATIVE_TOLERANCE = 0.02
# Maximaler Abstand der Abwärme zur robusten Regressionsschätzung in log10.
# 0,20 dex entspricht einem Faktor von etwa 1,58 nach oben/unten.
REGRESSION_ASSOCIATION_LOG10_HALF_WIDTH = 0.20
# Optionale Ausreißerfilterung: Tukey 1,5 * IQR von log10(Wärme);
# für bewertete Standorte zusätzlich stark auffällige Regressionsresiduen.
OUTLIER_MIN_SAMPLE_SIZE = 8

# =============================================================================
# 2. REFERENZJAHR
# =============================================================================

# Muss ein Nicht-Schaltjahr mit genau 8760 Stunden sein.
REFERENCE_YEAR = 2025


# =============================================================================
# 3. BETRIEBSFENSTER
# =============================================================================

STANDARD_START_HOUR_BY_DAILY_HOURS = {
    8.0: 6,
    12.0: 6,
    16.0: 6,
    20.0: 2,
    24.0: 0,
}

SPECIAL_PROFILE_DEFAULT_START_HOUR = 6


ACTIVE_WEEKDAYS_BY_DAYS_PER_WEEK = {
    1: {0},
    2: {0, 1},
    3: {0, 1, 2},
    4: {0, 1, 2, 3},
    5: {0, 1, 2, 3, 4},
    6: {0, 1, 2, 3, 4, 5},
    7: {0, 1, 2, 3, 4, 5, 6},
}


# =============================================================================
# 4. FALLBACKS
# =============================================================================

USE_DONOR_FOR_MISSING_OPERATING_PROFILE = True
USE_DONOR_FOR_MISSING_SEASONALITY = True

ALLOW_DEFAULT_OPERATING_PROFILE_LAST_RESORT = True
DEFAULT_OPERATING_PROFILE_CODE = "BP_24x7"

ALLOW_FLAT_SEASONALITY_LAST_RESORT = True


# =============================================================================
# 5. KONSOLE
# =============================================================================
PRINT_SITE_SUMMARY = True
PRINT_EACH_SOURCE = True

# =============================================================================
# 6. DATEIAUSGABE
# =============================================================================

SAVE_OUTPUT_FILES = True

FLOAT_DTYPE = np.float64


# =============================================================================
# 7. KONSTANTEN
# =============================================================================

VALID_Q_TYPES = {
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "Q5",
    "Q6",
    "Q7",
}

MONTH_CODES = [
    "Jan",
    "Feb",
    "Mrz",
    "Apr",
    "Mai",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Okt",
    "Nov",
    "Dez",
]

MONTH_NUMBER_TO_CODE = {
    1: "Jan",
    2: "Feb",
    3: "Mrz",
    4: "Apr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Okt",
    11: "Nov",
    12: "Dez",
}


# =============================================================================
# 8. HILFSFUNKTIONEN
# =============================================================================

def clean_string(value) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in {
        "nan",
        "none",
    }:
        return ""

    return text


def numeric_value(value):
    if pd.isna(value):
        return np.nan

    if isinstance(
            value,
            (
                    int,
                    float,
                    np.integer,
                    np.floating,
            ),
    ):
        return float(value)

    text = clean_string(value)

    if not text:
        return np.nan

    text = text.replace(
        " ",
        "",
    )

    if (
            ","
            in text
            and
            "."
            in text
    ):
        if (
                text.rfind(",")
                >
                text.rfind(".")
        ):
            text = (
                text
                .replace(".", "")
                .replace(",", ".")
            )

    elif "," in text:
        text = text.replace(
            ",",
            ".",
        )

    try:
        return float(text)

    except ValueError:
        return np.nan


def bool_value(value):
    if isinstance(
            value,
            bool,
    ):
        return value

    if pd.isna(value):
        return False

    return (
            clean_string(value)
            .casefold()
            in {
                "true",
                "wahr",
                "ja",
                "yes",
                "1",
            }
    )


# =============================================================================
# 9. TABELLEN LADEN
# =============================================================================

def read_table_auto(
        folder: Path,
        basename: str,
):
    parquet_path = (
            folder
            / f"{basename}.parquet"
    )

    csv_path = (
            folder
            / f"{basename}.csv"
    )

    if parquet_path.exists():

        try:
            return pd.read_parquet(
                parquet_path
            )

        except Exception as exc:

            print(
                f"WARNUNG: {parquet_path.name} konnte nicht "
                "gelesen werden."
            )

            print(
                f"         {exc}"
            )

            print(
                "         CSV-Fallback wird verwendet."
            )

    if csv_path.exists():

        return pd.read_csv(
            csv_path,
            sep=";",
            encoding="utf-8-sig",
            low_memory=False,
        )

    raise FileNotFoundError(
        f"Weder {parquet_path} noch {csv_path} gefunden."
    )


def load_group_data(
        group_id,
):
    folder = (
            GENERATOR_PACKAGE_DIR
            / group_id
    )

    if not folder.exists():

        raise FileNotFoundError(
            "Generator-Datenpaket nicht gefunden:\n"
            f"{folder}"
        )

    blocks = read_table_auto(
        folder,
        "source_blocks",
    )

    sites = read_table_auto(
        folder,
        "sites",
    )

    try:

        donors = read_table_auto(
            folder,
            "donor_pool",
        )

    except FileNotFoundError:

        donors = blocks.copy()

    return (
        folder,
        sites,
        blocks,
        donors,
    )


# =============================================================================
# 10. 8760-ZEITINDEX
# =============================================================================

def build_reference_time_index(
        year,
):
    start = pd.Timestamp(
        year=year,
        month=1,
        day=1,
        hour=0,
    )

    end = pd.Timestamp(
        year=year + 1,
        month=1,
        day=1,
        hour=0,
    )

    n_hours = int(
        (
                end
                -
                start
        )
        /
        pd.Timedelta(
            hours=1
        )
    )

    if n_hours != 8760:

        raise ValueError(
            f"REFERENCE_YEAR={year} besitzt {n_hours} Stunden. "
            "Bitte ein Nicht-Schaltjahr mit 8760 Stunden verwenden."
        )

    return pd.date_range(
        start=start,
        periods=8760,
        freq="h",
    )


# =============================================================================
# 11. EINEN REALISTISCHEN STANDORT ZIEHEN
# =============================================================================

def load_ki_size_table(group_id: str):
    """Liest die vollständige KI-Standorttabelle einer Profilgruppe."""
    if not SIZE_INFO_DIR.is_dir():
        raise FileNotFoundError(f"KI-Rechercheordner fehlt: {SIZE_INFO_DIR}")
    paths = sorted({
        path for path in SIZE_INFO_DIR.glob(f"KI_Standortgroesse_{group_id}*.xlsx")
        if path.is_file() and not path.name.startswith("~$")
           and re.match(rf"^KI_Standortgroesse_{re.escape(group_id)}(?:_|\.)", path.name, re.I)
    }, key=lambda path: ("score" in path.stem.casefold(), path.stat().st_mtime),
        reverse=True)
    if not paths:
        raise FileNotFoundError(f"Keine KI-Datei für {group_id} in {SIZE_INFO_DIR}")
    path = paths[0]
    df = pd.read_excel(path, sheet_name=SIZE_INFO_SHEET,
                       dtype={"Standortverbund_ID": str})
    required = {"Standortverbund_ID", SIZE_SCORE_COL}
    if not required.issubset(df.columns):
        raise ValueError(f"{path.name}: Pflichtspalten fehlen: {required - set(df.columns)}")
    if "Experiment_Gruppe" in df.columns:
        df = df.loc[df["Experiment_Gruppe"].map(clean_string).str.upper()
        .eq(group_id.upper())].copy()
    df["Standortverbund_ID"] = df["Standortverbund_ID"].map(clean_string)
    df[SIZE_SCORE_COL] = df[SIZE_SCORE_COL].map(numeric_value)
    df = df.loc[df["Standortverbund_ID"].ne("")].copy()
    df.loc[~df[SIZE_SCORE_COL].between(0, 100), SIZE_SCORE_COL] = np.nan
    if df["Standortverbund_ID"].duplicated().any():
        raise ValueError(f"{path.name}: doppelte Standortverbund_ID")
    return df, path


def load_ki_size_scores(group_id: str):
    """Kompatibilität: Nur ID und validierter Score zur Standorteauswahl."""
    df, path = load_ki_size_table(group_id)
    return df[["Standortverbund_ID", SIZE_SCORE_COL]].copy(), path


def build_site_heat_table(blocks: pd.DataFrame):
    """Standortwärme ausschließlich aus gültigen Q1–Q7-Blöcken (kWh/a)."""
    required = {"Standortverbund_ID", "Quellklasse_Code", "Waermemenge_Block_kWh_a"}
    if not required.issubset(blocks.columns):
        raise ValueError(f"source_blocks fehlen Spalten: {required - set(blocks.columns)}")
    b = blocks.loc[blocks["Quellklasse_Code"].map(clean_string).isin(VALID_Q_TYPES)].copy()
    b["Standortverbund_ID"] = b["Standortverbund_ID"].map(clean_string)
    b["_heat"] = b["Waermemenge_Block_kWh_a"].map(numeric_value)
    b = b.loc[(b["_heat"] > 0) & np.isfinite(b["_heat"]) &
              b["Standortverbund_ID"].ne("")]
    return b.groupby("Standortverbund_ID", as_index=False)["_heat"].sum().rename(
        columns={"_heat": "_Auswahl_Waermemenge_kWh_a"})


def fit_robust_heat_regression(scored: pd.DataFrame):
    """Robuste Huber-IRLS-Regressionsgerade log10(kWh/a) auf Score.

    Keine Normalverteilungsannahme und keine exponentiell großen Residuen:
    Kleinste-Quadrate-Startwert, dann Begrenzung des Einflusses extremer
    Residuen. Bei zu wenigen Messungen: robuste konstante Medianschätzung.
    """
    x = scored[SIZE_SCORE_COL].to_numpy(dtype=float)
    q = scored["_Auswahl_Waermemenge_kWh_a"].to_numpy(dtype=float)
    valid = np.isfinite(x) & np.isfinite(q) & (q > 0)
    x, y = x[valid], np.log10(q[valid])
    if not len(x):
        raise ValueError("Keine Score-Wärme-Paare zur Regression vorhanden.")
    if len(x) < 5 or np.ptp(x) < 5:
        return {"intercept": float(np.median(y)), "slope": 0.0,
                "method": "MEDIAN_BEI_WENIG_DATEN", "n": int(len(x))}
    # Skalierter x-Wert vermeidet schlechte Kondition; slope bleibt pro Scorepunkt.
    xm = float(np.median(x))
    a = np.column_stack((np.ones(len(x)), x - xm))
    beta = np.linalg.lstsq(a, y, rcond=None)[0]
    for _ in range(40):
        residual = y - a @ beta
        center = float(np.median(residual))
        mad = float(np.median(np.abs(residual - center)))
        scale = max(1.4826 * mad, 0.08)
        abs_r = np.abs(residual - center)
        weights = np.minimum(1., (1.345 * scale) / np.maximum(abs_r, 1e-12))
        new = np.linalg.lstsq(a * np.sqrt(weights[:, None]),
                              y * np.sqrt(weights), rcond=None)[0]
        if np.max(np.abs(new - beta)) < 1e-8:
            beta = new
            break
        beta = new
    # Der unabhängige KI-Größenscore soll keine negative Größenrelation bewirken.
    slope = max(0.0, float(beta[1]))
    intercept = float(beta[0] - slope * xm) if slope else float(np.median(y))
    return {"intercept": intercept, "slope": slope,
            "method": "HUBER_IRLS_LOG10" if slope else "ROBUSTER_MEDIAN_FALLBACK",
            "n": int(len(x))}


def predict_log10_heat(model, scores):
    return model["intercept"] + model["slope"] * np.asarray(scores, dtype=float)


def heat_outlier_mask_log_iqr(available: pd.DataFrame):
    """Hohe UND niedrige globale Wärmeausreißer, 1.5 IQR in Log10-Einheiten."""
    heat = available["_Auswahl_Waermemenge_kWh_a"].to_numpy(dtype=float)
    if len(heat) < OUTLIER_MIN_SAMPLE_SIZE:
        return np.zeros(len(available), dtype=bool)
    logs = np.log10(heat)
    q1, q3 = np.percentile(logs, [25, 75])
    iqr = float(q3 - q1)
    if iqr < 1e-6:
        return np.abs(logs - float(np.median(logs))) > 0.7
    return (logs < q1 - 1.5 * iqr) | (logs > q3 + 1.5 * iqr)


def score_residual_outlier_mask(scored: pd.DataFrame, model):
    """Stark abweichende Score-Wärme-Kombinationen (nur bei hinreichendem n)."""
    if len(scored) < OUTLIER_MIN_SAMPLE_SIZE or model["slope"] <= 0:
        return np.zeros(len(scored), dtype=bool)
    residual = np.log10(scored["_Auswahl_Waermemenge_kWh_a"].to_numpy(dtype=float)) - \
               predict_log10_heat(model, scored[SIZE_SCORE_COL].to_numpy(dtype=float))
    center = float(np.median(residual))
    mad = float(np.median(np.abs(residual - center)))
    threshold = max(0.7, 3.0 * 1.4826 * mad)
    return np.abs(residual - center) > threshold

def find_heat_associated_sites(unscored_sites: pd.DataFrame,
                               score_references: pd.DataFrame,
                               relative_tolerance=HEAT_ASSOCIATION_RELATIVE_TOLERANCE):
    """Findet unbewertete Standorte mit Abwärme innerhalb ±r EINER Referenz.

    Beide Tabellen müssen auf Grundlage der Q1-Q7-Quellenwärme desselben
    Generator-Datenpakets gebildet sein. Kein Standort wird mehrfach gezählt,
    auch wenn er mehrere Score-Referenzen trifft. Die mathematische Bedingung
    lautet: |Q_unbewertet - Q_referenz| <= r * Q_referenz.
    """
    if not 0 <= relative_tolerance < 1:
        raise ValueError("Die relative Abwärmetoleranz muss zwischen 0 und 1 liegen.")
    if unscored_sites.empty or score_references.empty:
        return unscored_sites.iloc[0:0].copy()

    heat_col = "_Auswahl_Waermemenge_kWh_a"
    reference = score_references.sort_values(heat_col, kind="stable").reset_index(drop=True)
    ref_heats = reference[heat_col].to_numpy(dtype=float)
    ref_ids = reference["Standortverbund_ID"].to_numpy(dtype=str)
    unscored = unscored_sites.copy().reset_index(drop=True)
    heats = unscored[heat_col].to_numpy(dtype=float)

    # Aus |q - r| <= t*r ergibt sich r in [q/(1+t), q/(1-t)].
    # Suchen im sortierten Referenzfeld statt kartesischer Kreuzverknüpfung.
    left = np.searchsorted(ref_heats, heats / (1.0 + relative_tolerance), side="left")
    right = np.searchsorted(ref_heats, heats / (1.0 - relative_tolerance), side="right")
    associated_mask = left < right
    matched = unscored.loc[associated_mask].copy()
    if matched.empty:
        return matched

    # Für jede Trefferzeile einen (ggf. von mehreren) Referenzstandorten
    # auditierbar dokumentieren. Die Auswahrscheinlichkeit wird dadurch NICHT
    # gewichtet: Ein Standort bleibt immer ein Kandidat.
    indices = np.flatnonzero(associated_mask)
    matched_refs = []
    matched_ref_heats = []
    relative_diffs = []
    reference_counts = []
    for i in indices:
        indices_in_range = np.arange(left[i], right[i])
        deviations = np.abs(heats[i] - ref_heats[indices_in_range]) / ref_heats[indices_in_range]
        best = indices_in_range[int(np.argmin(deviations))]
        matched_refs.append(ref_ids[best])
        matched_ref_heats.append(float(ref_heats[best]))
        relative_diffs.append(float(np.min(deviations)))
        reference_counts.append(int(len(indices_in_range)))

    matched["_Assoziation_Referenz_Standort_ID"] = matched_refs
    matched["_Assoziation_Referenzwaerme_kWh_a"] = matched_ref_heats
    matched["_Assoziation_Relative_Waermeabweichung"] = relative_diffs
    matched["_Assoziation_Anzahl_passender_Referenzen"] = reference_counts
    return matched.reset_index(drop=True)


def build_selection_candidates(
        group_id, sites, blocks, *, size_score=None, score_tolerance=None,
        annual_heat_kwh=None, heat_tolerance_kwh=None,
        use_heat_association=True, exclude_heat_outliers=False):
    """Ein Standort = eine gleichgewichtete Ziehungsoption.

    Modus Score: direkte Treffer plus optional unbewertete Standorte,
    die sowohl ±2 % Wärme einer Referenz haben ALS AUCH innerhalb eines
    robusten Regressionskorridors von ±0.20 dex liegen.
    """
    if not isinstance(use_heat_association, (bool, np.bool_)):
        raise ValueError("use_heat_association muss True oder False sein.")
    if not isinstance(exclude_heat_outliers, (bool, np.bool_)):
        raise ValueError("exclude_heat_outliers muss True oder False sein.")
    score_mode = size_score is not None
    if score_mode == (annual_heat_kwh is not None):
        raise ValueError("Genau EIN Ziel angeben: size_score ODER annual_heat_kwh.")
    if score_mode:
        target, tolerance = numeric_value(size_score), numeric_value(score_tolerance)
        if not np.isfinite(target) or not 0 <= target <= 100:
            raise ValueError("size_score muss zwischen 0 und 100 liegen.")
        if not np.isfinite(tolerance) or tolerance < 0:
            raise ValueError("score_tolerance muss nichtnegativ sein.")
        mode, value_column = "KI_GROESSENSCORE", SIZE_SCORE_COL
    else:
        target, tolerance = numeric_value(annual_heat_kwh), numeric_value(heat_tolerance_kwh)
        if not np.isfinite(target) or target <= 0:
            raise ValueError("annual_heat_kwh muss positiv sein.")
        if not np.isfinite(tolerance) or tolerance < 0:
            raise ValueError("heat_tolerance_kwh muss nichtnegativ sein.")
        mode, value_column = "JAHRESABWAERME", "_Auswahl_Waermemenge_kWh_a"

    heat_table = build_site_heat_table(blocks)
    available = sites.copy()
    available["Standortverbund_ID"] = available["Standortverbund_ID"].map(clean_string)
    if available["Standortverbund_ID"].duplicated().any():
        raise ValueError("sites enthält doppelte Standortverbund_ID-Werte.")
    available = available.merge(heat_table, on="Standortverbund_ID",
                                how="inner", validate="one_to_one")
    if available.empty:
        raise ValueError(f"{group_id}: keine Standorte mit positiver Q1–Q7-Wärme.")
    total_before_filter = len(available)
    score_file = None
    associated_count = 0
    score_reference_count = 0
    regression = None
    corridor = None
    available_scored_count = 0
    available_unscored_count = 0
    removed_global = 0
    removed_residual = 0
    removed_global_mask = heat_outlier_mask_log_iqr(available) if exclude_heat_outliers \
        else np.zeros(len(available), dtype=bool)
    removed_global = int(removed_global_mask.sum())
    available = available.loc[~removed_global_mask].copy()
    if available.empty:
        raise ValueError("Alle Standorte wurden als Wärmeausreißer ausgeschlossen.")

    if score_mode:
        scores, score_file = load_ki_size_scores(group_id)
        available = available.merge(scores, on="Standortverbund_ID", how="left",
                                    validate="one_to_one")
        available[SIZE_SCORE_COL] = pd.to_numeric(available[SIZE_SCORE_COL], errors="coerce")
        has_score = available[SIZE_SCORE_COL].between(0, 100)
        scored = available.loc[has_score].copy()
        if scored.empty:
            raise ValueError(f"{group_id}: keine gültigen KI-Scores vorhanden.")
        if exclude_heat_outliers:
            preliminary = fit_robust_heat_regression(scored)
            residual_mask = score_residual_outlier_mask(scored, preliminary)
            # Genügend Score-Referenzen zur Neuberechnung bewahren.
            if int((~residual_mask).sum()) >= 3:
                removed_residual = int(residual_mask.sum())
                available = available.loc[~available["Standortverbund_ID"].isin(
                    scored.loc[residual_mask, "Standortverbund_ID"])].copy()
                scored = scored.loc[~residual_mask].copy()
        unscored = available.loc[~available[SIZE_SCORE_COL].between(0, 100)].copy()
        available_scored_count, available_unscored_count = len(scored), len(unscored)
        scored["_Auswahl_Abstand"] = (scored[SIZE_SCORE_COL] - target).abs()
        inside = scored["_Auswahl_Abstand"] <= tolerance + 1e-10
        within_count = int(inside.sum())
        fallback = within_count == 0
        if fallback:
            distance = float(scored["_Auswahl_Abstand"].min())
            refs = scored.loc[np.isclose(scored["_Auswahl_Abstand"], distance,
                                         atol=1e-9, rtol=1e-12)].copy()
        else:
            refs = scored.loc[inside].copy()
        score_reference_count = len(refs)
        refs["_Auswahl_Herkunft"] = "MIT_KI_SCORE"
        candidates = refs.copy()
        if use_heat_association and not unscored.empty:
            regression = fit_robust_heat_regression(scored)
            expected = predict_log10_heat(regression,
                                          refs[SIZE_SCORE_COL].to_numpy(dtype=float))
            lo_log = float(np.min(expected) - REGRESSION_ASSOCIATION_LOG10_HALF_WIDTH)
            hi_log = float(np.max(expected) + REGRESSION_ASSOCIATION_LOG10_HALF_WIDTH)
            corridor = (10.0 ** lo_log, 10.0 ** hi_log)
            matched = find_heat_associated_sites(unscored, refs,
                                                 HEAT_ASSOCIATION_RELATIVE_TOLERANCE)
            matched = matched.loc[matched["_Auswahl_Waermemenge_kWh_a"].between(
                corridor[0], corridor[1])].copy()
            associated_count = len(matched)
            if associated_count:
                matched["_Auswahl_Herkunft"] = "ABWAERMEASSOZIATION_OHNE_SCORE"
                candidates = pd.concat([refs, matched], ignore_index=True)
        available_valid_count = available_scored_count
    else:
        if exclude_heat_outliers and len(available) == 0:
            raise ValueError("Keine Standorte nach Wärmeausreißerfilter vorhanden.")
        available[value_column] = pd.to_numeric(available[value_column], errors="coerce")
        available = available.loc[np.isfinite(available[value_column])].copy()
        available["_Auswahl_Abstand"] = (available[value_column] - target).abs()
        inside = available["_Auswahl_Abstand"] <= tolerance + 1e-10
        within_count = int(inside.sum())
        fallback = within_count == 0
        if fallback:
            distance = float(available["_Auswahl_Abstand"].min())
            candidates = available.loc[np.isclose(available["_Auswahl_Abstand"],
                                                  distance, atol=1e-9, rtol=1e-12)].copy()
        else:
            candidates = available.loc[inside].copy()
        candidates["_Auswahl_Herkunft"] = "JAHRESABWAERME"
        available_valid_count = len(available)

    if candidates.empty or candidates["Standortverbund_ID"].duplicated().any():
        raise RuntimeError("Ungültiger Kandidatenpool (leer oder doppelte IDs).")
    candidates = candidates.reset_index(drop=True)
    return candidates, {
        "selection_mode": mode,
        "selection_target": float(target),
        "selection_tolerance": float(tolerance),
        "matching_sites_in_window": int(within_count),
        "selection_candidate_count": int(len(candidates)),
        "available_sites_with_valid_value": int(available_valid_count),
        "fallback_to_nearest": bool(fallback),
        "score_file": str(score_file) if score_file else None,
        "score_reference_site_count": int(score_reference_count),
        "associated_sites_by_heat": int(associated_count),
        "heat_association_relative_tolerance": (
            HEAT_ASSOCIATION_RELATIVE_TOLERANCE if score_mode and use_heat_association else None),
        "available_sites_without_score": (int(available_unscored_count) if score_mode else None),
        "use_heat_association": bool(use_heat_association) if score_mode else False,
        "exclude_heat_outliers": bool(exclude_heat_outliers),
        "outliers_removed_global": int(removed_global),
        "outliers_removed_score_residual": int(removed_residual),
        "available_sites_before_outlier_filter": int(total_before_filter),
        "regression_method": regression["method"] if regression else None,
        "regression_n": regression["n"] if regression else None,
        "regression_intercept_log10": regression["intercept"] if regression else None,
        "regression_slope_log10_per_score": regression["slope"] if regression else None,
        "association_regression_corridor_kwh_a": list(corridor) if corridor else None,
    }

def choose_basis_site(sites, rng, used_site_ids=None):
    """Zieht einen realen Standort gleichwahrscheinlich aus den Kandidaten."""
    if used_site_ids is None:
        used_site_ids = set()

    candidates = sites.copy()
    if FIXED_BASIS_SITE_ID is not None:
        candidates = candidates[candidates["Standortverbund_ID"].map(clean_string).eq(
            clean_string(FIXED_BASIS_SITE_ID)
        )]
        if candidates.empty:
            raise ValueError(
                "FIXED_BASIS_SITE_ID ist nicht unter den passenden Standorten: "
                f"{FIXED_BASIS_SITE_ID}"
            )

    not_used = candidates[
        ~candidates["Standortverbund_ID"].map(clean_string).isin(used_site_ids)
    ]
    if not not_used.empty:
        candidates = not_used
    # Bei mehr gewünschten Profilen als passenden Standorten können Standorte
    # erst nach Ausschöpfen des Pools erneut auftreten.
    position = int(rng.integers(0, len(candidates)))
    return candidates.iloc[position]


# =============================================================================
# 12. QUELLENSTRUKTUR DES GEZOGENEN STANDORTS
# =============================================================================

def get_site_source_structure(
        site_row,
        blocks,
):
    basis_site_id = clean_string(
        site_row[
            "Standortverbund_ID"
        ]
    )

    source_rows = blocks[
        blocks[
            "Standortverbund_ID"
        ]
        .map(clean_string)
        .eq(
            basis_site_id
        )
    ].copy()

    if source_rows.empty:

        raise ValueError(
            f"Für Standort {basis_site_id} wurden keine Quellenblöcke gefunden."
        )

    source_rows[
        "_empirical_heat"
    ] = (
        source_rows[
            "Waermemenge_Block_kWh_a"
        ]
        .map(
            numeric_value
        )
    )

    invalid = source_rows[
        source_rows[
            "_empirical_heat"
        ].isna()
        |
        (
                source_rows[
                    "_empirical_heat"
                ]
                <= 0
        )
        ]

    if not invalid.empty:

        raise ValueError(
            "Der gezogene Standort enthält Quellenblöcke ohne "
            "positive Jahreswärmemenge."
        )

    empirical_total = float(
        source_rows[
            "_empirical_heat"
        ].sum()
    )

    source_rows[
        "_empirical_share"
    ] = (
            source_rows[
                "_empirical_heat"
            ]
            /
            empirical_total
    )

    if (
            TARGET_SITE_ANNUAL_HEAT_KWH
            is None
    ):

        generated_total = empirical_total

    else:

        generated_total = float(
            TARGET_SITE_ANNUAL_HEAT_KWH
        )

        if generated_total <= 0:

            raise ValueError(
                "TARGET_SITE_ANNUAL_HEAT_KWH muss positiv sein."
            )

    source_rows[
        "_generated_heat"
    ] = (
            source_rows[
                "_empirical_share"
            ]
            *
            generated_total
    )

    return {
        "basis_site_id":
            basis_site_id,

        "source_rows":
            source_rows,

        "empirical_total_heat":
            empirical_total,

        "generated_total_heat":
            generated_total,
    }


# =============================================================================
# 13. BETRIEBSPROFIL AUS EINEM BLOCK LESEN
# =============================================================================

def parse_profile_code(
        profile_code,
):
    code = clean_string(
        profile_code
    )

    match_standard = re.fullmatch(
        r"BP_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)",
        code,
    )

    if match_standard:

        return (
            float(
                match_standard.group(1)
            ),
            float(
                match_standard.group(2)
            ),
            "STANDARD",
        )

    match_exact = re.fullmatch(
        r"BP_EXAKT_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)",
        code,
    )

    if match_exact:

        return (
            float(
                match_exact.group(1)
            ),
            float(
                match_exact.group(2)
            ),
            "EXAKT",
        )

    return (
        np.nan,
        np.nan,
        "UNBEKANNT",
    )


def resolve_operating_profile_from_row(
        row,
):
    code = clean_string(
        row.get(
            "Betriebsprofil_Code",
            "",
        )
    )

    hours = numeric_value(
        row.get(
            "Betriebsprofil_h_pro_Tag",
            np.nan,
        )
    )

    days = numeric_value(
        row.get(
            "Betriebsprofil_Tage_pro_Woche",
            np.nan,
        )
    )

    parsed_hours, parsed_days, kind = (
        parse_profile_code(
            code
        )
    )

    if pd.isna(hours):
        hours = parsed_hours

    if pd.isna(days):
        days = parsed_days

    valid = (
            code != "BP_UNBEKANNT"
            and
            pd.notna(hours)
            and
            pd.notna(days)
            and
            0 < hours <= 24
            and
            0 < days <= 7
    )

    return {
        "code":
            code,

        "hours_per_day":
            hours,

        "days_per_week":
            days,

        "kind":
            kind,

        "valid":
            bool(valid),
    }


# =============================================================================
# 14. SAISONALITÄT LESEN
# =============================================================================

def resolve_seasonality_from_row(
        row,
):
    factors = {}

    for month in MONTH_CODES:

        factors[
            month
        ] = numeric_value(
            row.get(
                f"Saison_Faktor_{month}",
                np.nan,
            )
        )

    valid = all(
        pd.notna(
            factors[
                month
            ]
        )
        and
        factors[
            month
        ] >= 0
        for month
        in MONTH_CODES
    )

    if valid:

        if sum(
                factors.values()
        ) <= 0:

            valid = False

    return {
        "factors":
            factors,

        "valid":
            bool(valid),

        "summer_factor":
            numeric_value(
                row.get(
                    "Saisonfaktor_Sommer",
                    np.nan,
                )
            ),

        "winter_factor":
            numeric_value(
                row.get(
                    "Saisonfaktor_Winter",
                    np.nan,
                )
            ),

        "active_months":
            numeric_value(
                row.get(
                    "Saison_Aktive_Monate",
                    np.nan,
                )
            ),

        "concentration":
            numeric_value(
                row.get(
                    "Saison_Konzentration_0_1",
                    np.nan,
                )
            ),
    }


# =============================================================================
# 15. DONOR-FALLBACK
# =============================================================================

def choose_donor(
        target_row,
        donor_df,
        rng,
        require_operating,
        require_seasonality,
):
    donors = donor_df.copy()

    target_block_id = clean_string(
        target_row.get(
            "Generator_Block_ID",
            "",
        )
    )

    if (
            target_block_id
            and
            "Generator_Block_ID"
            in donors.columns
    ):

        donors = donors[
            donors[
                "Generator_Block_ID"
            ]
            .map(clean_string)
            .ne(
                target_block_id
            )
        ]

    if require_operating:

        if (
                "Betriebsprofil_Donor_verwendbar"
                in donors.columns
        ):

            donors = donors[
                donors[
                    "Betriebsprofil_Donor_verwendbar"
                ]
                .map(
                    bool_value
                )
            ]

        else:

            donors = donors[
                donors[
                    "Betriebsprofil_Code"
                ]
                .map(clean_string)
                .ne(
                    "BP_UNBEKANNT"
                )
            ]

    if require_seasonality:

        if (
                "Saisonalitaet_Donor_verwendbar"
                in donors.columns
        ):

            donors = donors[
                donors[
                    "Saisonalitaet_Donor_verwendbar"
                ]
                .map(
                    bool_value
                )
            ]

        else:

            donors = donors[
                donors[
                    "Saison_Profil_gueltig"
                ]
                .map(
                    bool_value
                )
            ]

    q_code = clean_string(
        target_row.get(
            "Quellklasse_Code",
            "",
        )
    )

    size_class = clean_string(
        target_row.get(
            "Groessenklasse_Q",
            "",
        )
    )

    family = clean_string(
        target_row.get(
            "Quellenfamilie_normalisiert",
            "",
        )
    )

    levels = []

    if (
            q_code
            and
            size_class
            and
            family
    ):

        levels.append(
            (
                "Q_GROESSE_FAMILIE",
                donors[
                    donors[
                        "Quellklasse_Code"
                    ]
                    .map(clean_string)
                    .eq(
                        q_code
                    )
                    &
                    donors[
                        "Groessenklasse_Q"
                    ]
                    .map(clean_string)
                    .eq(
                        size_class
                    )
                    &
                    donors[
                        "Quellenfamilie_normalisiert"
                    ]
                    .map(clean_string)
                    .eq(
                        family
                    )
                    ],
            )
        )

    if (
            q_code
            and
            size_class
    ):

        levels.append(
            (
                "Q_GROESSE",
                donors[
                    donors[
                        "Quellklasse_Code"
                    ]
                    .map(clean_string)
                    .eq(
                        q_code
                    )
                    &
                    donors[
                        "Groessenklasse_Q"
                    ]
                    .map(clean_string)
                    .eq(
                        size_class
                    )
                    ],
            )
        )

    if q_code:

        levels.append(
            (
                "Q",
                donors[
                    donors[
                        "Quellklasse_Code"
                    ]
                    .map(clean_string)
                    .eq(
                        q_code
                    )
                ],
            )
        )

    levels.append(
        (
            "GRUPPE",
            donors,
        )
    )

    for level_name, candidates in levels:

        if candidates.empty:
            continue

        position = int(
            rng.integers(
                0,
                len(
                    candidates
                ),
            )
        )

        return (
            candidates.iloc[
                position
            ],
            level_name,
        )

    return (
        None,
        "",
    )


def resolve_profile_parameters(
        target_row,
        donor_df,
        rng,
):
    operating = (
        resolve_operating_profile_from_row(
            target_row
        )
    )

    seasonality = (
        resolve_seasonality_from_row(
            target_row
        )
    )

    operating_imputed = False
    seasonality_imputed = False

    operating_donor_id = ""
    operating_donor_level = ""

    seasonality_donor_id = ""
    seasonality_donor_level = ""

    # -------------------------------------------------------------------------
    # Wenn beide fehlen: möglichst ein gemeinsamer Donor.
    # -------------------------------------------------------------------------

    if (
            not operating[
                "valid"
            ]
            and
            not seasonality[
                "valid"
            ]
            and
            USE_DONOR_FOR_MISSING_OPERATING_PROFILE
            and
            USE_DONOR_FOR_MISSING_SEASONALITY
    ):

        donor, level = choose_donor(
            target_row=
            target_row,

            donor_df=
            donor_df,

            rng=
            rng,

            require_operating=
            True,

            require_seasonality=
            True,
        )

        if donor is not None:

            operating = (
                resolve_operating_profile_from_row(
                    donor
                )
            )

            seasonality = (
                resolve_seasonality_from_row(
                    donor
                )
            )

            donor_id = clean_string(
                donor.get(
                    "Generator_Block_ID",
                    "",
                )
            )

            operating_imputed = True
            seasonality_imputed = True

            operating_donor_id = donor_id
            operating_donor_level = level

            seasonality_donor_id = donor_id
            seasonality_donor_level = level

    # -------------------------------------------------------------------------
    # Betriebsprofil einzeln ergänzen.
    # -------------------------------------------------------------------------

    if not operating[
        "valid"
    ]:

        if USE_DONOR_FOR_MISSING_OPERATING_PROFILE:

            donor, level = choose_donor(
                target_row=
                target_row,

                donor_df=
                donor_df,

                rng=
                rng,

                require_operating=
                True,

                require_seasonality=
                False,
            )

            if donor is not None:

                operating = (
                    resolve_operating_profile_from_row(
                        donor
                    )
                )

                operating_imputed = True

                operating_donor_id = clean_string(
                    donor.get(
                        "Generator_Block_ID",
                        "",
                    )
                )

                operating_donor_level = level

        if not operating[
            "valid"
        ]:

            if not ALLOW_DEFAULT_OPERATING_PROFILE_LAST_RESORT:

                raise ValueError(
                    "Kein gültiges Betriebsprofil und kein Donor "
                    f"für Block {target_row.get('Generator_Block_ID')}"
                )

            hours, days, kind = (
                parse_profile_code(
                    DEFAULT_OPERATING_PROFILE_CODE
                )
            )

            operating = {
                "code":
                    DEFAULT_OPERATING_PROFILE_CODE,

                "hours_per_day":
                    hours,

                "days_per_week":
                    days,

                "kind":
                    kind,

                "valid":
                    True,
            }

            operating_imputed = True

            operating_donor_level = (
                "LETZTER_FALL_STANDARDPROFIL"
            )

    # -------------------------------------------------------------------------
    # Saisonalität einzeln ergänzen.
    # -------------------------------------------------------------------------

    if not seasonality[
        "valid"
    ]:

        if USE_DONOR_FOR_MISSING_SEASONALITY:

            donor, level = choose_donor(
                target_row=
                target_row,

                donor_df=
                donor_df,

                rng=
                rng,

                require_operating=
                False,

                require_seasonality=
                True,
            )

            if donor is not None:

                seasonality = (
                    resolve_seasonality_from_row(
                        donor
                    )
                )

                seasonality_imputed = True

                seasonality_donor_id = clean_string(
                    donor.get(
                        "Generator_Block_ID",
                        "",
                    )
                )

                seasonality_donor_level = level

        if not seasonality[
            "valid"
        ]:

            if not ALLOW_FLAT_SEASONALITY_LAST_RESORT:

                raise ValueError(
                    "Keine gültige Saisonalität und kein Donor "
                    f"für Block {target_row.get('Generator_Block_ID')}"
                )

            seasonality = {
                "factors":
                    {
                        month: 1.0
                        for month
                        in MONTH_CODES
                    },

                "valid":
                    True,

                "summer_factor":
                    1.0,

                "winter_factor":
                    1.0,

                "active_months":
                    12.0,

                "concentration":
                    0.0,
            }

            seasonality_imputed = True

            seasonality_donor_level = (
                "LETZTER_FALL_FLACHE_SAISONALITAET"
            )

    return {
        "operating":
            operating,

        "seasonality":
            seasonality,

        "operating_imputed":
            operating_imputed,

        "seasonality_imputed":
            seasonality_imputed,

        "operating_donor_id":
            operating_donor_id,

        "operating_donor_level":
            operating_donor_level,

        "seasonality_donor_id":
            seasonality_donor_id,

        "seasonality_donor_level":
            seasonality_donor_level,
    }


# =============================================================================
# 16. BETRIEBSMASKE
# =============================================================================

def get_start_hour(
        hours_per_day,
):
    hours = float(
        hours_per_day
    )

    if hours >= 23.999:
        return 0

    if (
            hours
            in
            STANDARD_START_HOUR_BY_DAILY_HOURS
    ):

        return int(
            STANDARD_START_HOUR_BY_DAILY_HOURS[
                hours
            ]
        )

    return int(
        SPECIAL_PROFILE_DEFAULT_START_HOUR
    )


def build_operating_mask(
        time_index,
        hours_per_day,
        days_per_week,
        start_hour,
):
    hours_per_day = float(
        hours_per_day
    )

    days_per_week = float(
        days_per_week
    )

    rounded_days = int(
        round(
            days_per_week
        )
    )

    rounded_hours = int(
        round(
            hours_per_day
        )
    )

    if (
            abs(
                days_per_week
                -
                rounded_days
            )
            >
            1e-9
    ):

        raise ValueError(
            "Aktuell werden nur ganzzahlige Tage/Woche unterstützt: "
            f"{days_per_week}"
        )

    if (
            abs(
                hours_per_day
                -
                rounded_hours
            )
            >
            1e-9
    ):

        raise ValueError(
            "Aktuell werden nur ganzzahlige Stunden/Tag unterstützt: "
            f"{hours_per_day}"
        )

    if (
            rounded_days
            not in
            ACTIVE_WEEKDAYS_BY_DAYS_PER_WEEK
    ):

        raise ValueError(
            f"Ungültige Tage/Woche: {rounded_days}"
        )

    if (
            rounded_hours <= 0
            or
            rounded_hours > 24
    ):

        raise ValueError(
            f"Ungültige Stunden/Tag: {rounded_hours}"
        )

    active_weekdays = (
        ACTIVE_WEEKDAYS_BY_DAYS_PER_WEEK[
            rounded_days
        ]
    )

    weekday_mask = np.fromiter(
        (
            timestamp.weekday()
            in active_weekdays
            for timestamp
            in time_index
        ),
        dtype=bool,
        count=len(
            time_index
        ),
    )

    if rounded_hours == 24:

        hour_mask = np.ones(
            len(
                time_index
            ),
            dtype=bool,
        )

    else:

        end_hour = (
                start_hour
                +
                rounded_hours
        )

        if end_hour <= 24:

            hour_mask = np.fromiter(
                (
                    start_hour
                    <=
                    timestamp.hour
                    <
                    end_hour
                    for timestamp
                    in time_index
                ),
                dtype=bool,
                count=len(
                    time_index
                ),
            )

        else:

            wrapped_end = (
                    end_hour
                    -
                    24
            )

            hour_mask = np.fromiter(
                (
                    timestamp.hour
                    >=
                    start_hour
                    or
                    timestamp.hour
                    <
                    wrapped_end
                    for timestamp
                    in time_index
                ),
                dtype=bool,
                count=len(
                    time_index
                ),
            )

    return (
            weekday_mask
            &
            hour_mask
    )


# =============================================================================
# 17. MONATLICHE ENERGIEANTEILE
# =============================================================================

def calculate_monthly_energy_shares(
        time_index,
        season_factors,
):
    month_hours = {}

    for month_number, month_code in (
            MONTH_NUMBER_TO_CODE.items()
    ):

        month_hours[
            month_code
        ] = int(
            (
                    time_index.month
                    ==
                    month_number
            ).sum()
        )

    weighted = {}

    for month in MONTH_CODES:

        factor = float(
            season_factors[
                month
            ]
        )

        if factor < 0:

            raise ValueError(
                f"Negativer Saisonfaktor in {month}: {factor}"
            )

        weighted[
            month
        ] = (
                factor
                *
                month_hours[
                    month
                ]
        )

    total = sum(
        weighted.values()
    )

    if total <= 0:

        raise ValueError(
            "Saisonalität ergibt keine positive Jahresenergie."
        )

    shares = {
        month:
            weighted[
                month
            ]
            /
            total
        for month
        in MONTH_CODES
    }

    return shares


# =============================================================================
# 18. EIN 8760-PROFIL ERZEUGEN
# =============================================================================

def generate_single_source_profile(
        annual_heat_kwh,
        time_index,
        operating,
        seasonality,
):
    annual_heat_kwh = float(
        annual_heat_kwh
    )

    hours_per_day = float(
        operating[
            "hours_per_day"
        ]
    )

    days_per_week = float(
        operating[
            "days_per_week"
        ]
    )

    start_hour = get_start_hour(
        hours_per_day
    )

    operating_mask = build_operating_mask(
        time_index=
        time_index,

        hours_per_day=
        hours_per_day,

        days_per_week=
        days_per_week,

        start_hour=
        start_hour,
    )

    monthly_shares = (
        calculate_monthly_energy_shares(
            time_index=
            time_index,

            season_factors=
            seasonality[
                "factors"
            ],
        )
    )

    profile = np.zeros(
        8760,
        dtype=FLOAT_DTYPE,
    )

    active_hours_by_month = {}

    for month_number, month_code in (
            MONTH_NUMBER_TO_CODE.items()
    ):

        month_mask = (
                time_index.month
                ==
                month_number
        )

        active_mask = (
                month_mask
                &
                operating_mask
        )

        active_count = int(
            active_mask.sum()
        )

        active_hours_by_month[
            month_code
        ] = active_count

        month_energy = (
                annual_heat_kwh
                *
                monthly_shares[
                    month_code
                ]
        )

        if month_energy <= 0:
            continue

        if active_count <= 0:

            raise ValueError(
                f"Monat {month_code}: positive Monatsenergie, "
                "aber keine aktive Betriebsstunde."
            )

        profile[
            active_mask
        ] = (
                month_energy
                /
                active_count
        )

    # Fließkomma-Rest auf letzte positive Stunde.
    difference = (
            annual_heat_kwh
            -
            float(
                profile.sum()
            )
    )

    positive_indices = np.flatnonzero(
        profile > 0
    )

    if len(
            positive_indices
    ) == 0:

        raise RuntimeError(
            "Erzeugtes Profil besitzt keine positive Stunde."
        )

    profile[
        positive_indices[-1]
    ] += difference

    if not np.isclose(
            profile.sum(),
            annual_heat_kwh,
            rtol=1e-10,
            atol=1e-6,
    ):

        raise RuntimeError(
            "Profil stimmt energetisch nicht mit der Jahreswärmemenge überein."
        )

    return {
        "profile_kWh":
            profile,

        "start_hour":
            start_hour,

        "active_hours_year":
            int(
                operating_mask.sum()
            ),

        "active_hours_by_month":
            active_hours_by_month,

        "monthly_energy_shares":
            monthly_shares,
    }


# =============================================================================
# 19. KONSOLE
# =============================================================================

def print_model_assumptions():
    print(f"Profilmodell: {REFERENCE_YEAR} (8760 h), kWh je Stunde; "
          "Jahreswärme statt Maximalleistung als Skalierungsbasis.")
    print("Betriebsfenster und Saisonalität: empirische Betriebsdaten, "
          "12 Monatsfaktoren; fehlende Angaben ggf. per Donor ergänzt.")


def print_site_summary(generated_site_id, structure, source_rows):
    if PRINT_SITE_SUMMARY:
        print(f"\n{generated_site_id} | Vorlage {structure['basis_site_id']} | "
              f"{len(source_rows)} Quellen | "
              f"{structure['generated_total_heat'] / 1e6:.3f} GWh/a")


def print_source_profile(number, total, source):
    if not PRINT_EACH_SOURCE:
        return
    print(f"  Quelle {number}/{total}: {source['Quellklasse_Code']} | "
          f"{source['Waermemenge_kWh_a'] / 1e6:.3f} GWh/a | "
          f"{source['Anteil_am_Standort']:.1%} | "
          f"{source['Betriebsprofil_Code']} | "
          f"Betrieb ergänzt: {source['Betriebsprofil_imputiert']}, "
          f"Saison ergänzt: {source['Saisonalitaet_imputiert']}")

# =============================================================================
# 20. EINEN REALISTISCHEN STANDORT GENERIEREN
# =============================================================================

def generate_one_site(
        group_id,
        site_number,
        sites,
        blocks,
        donors,
        time_index,
        rng,
        used_site_ids,
        selection_info,
):
    basis_site = choose_basis_site(
        sites=
        sites,

        rng=
        rng,

        used_site_ids=
        used_site_ids,
    )

    structure = get_site_source_structure(
        site_row=
        basis_site,

        blocks=
        blocks,
    )

    basis_site_id = structure[
        "basis_site_id"
    ]

    used_site_ids.add(
        basis_site_id
    )

    generated_site_id = (
        f"SYN_{group_id}_{site_number:04d}"
    )

    source_rows = structure[
        "source_rows"
    ].copy()

    print_site_summary(
        generated_site_id=
        generated_site_id,

        structure=
        structure,

        source_rows=
        source_rows,
    )

    source_results = []
    matrix_rows = []
    metadata_rows = []

    for source_number, (_, row) in enumerate(
            source_rows.iterrows(),
            start=1,
    ):

        parameters = resolve_profile_parameters(
            target_row=
            row,

            donor_df=
            donors,

            rng=
            rng,
        )

        operating = parameters[
            "operating"
        ]

        seasonality = parameters[
            "seasonality"
        ]

        annual_heat = float(
            row[
                "_generated_heat"
            ]
        )

        generated = (
            generate_single_source_profile(
                annual_heat_kwh=
                annual_heat,

                time_index=
                time_index,

                operating=
                operating,

                seasonality=
                seasonality,
            )
        )

        profile = generated[
            "profile_kWh"
        ]

        source = {
            "Generierter_Standort_ID":
                generated_site_id,

            "Basis_Standortverbund_ID":
                basis_site_id,

            "Basis_Generator_Block_ID":
                clean_string(
                    row[
                        "Generator_Block_ID"
                    ]
                ),

            "Quellklasse_Code":
                clean_string(
                    row[
                        "Quellklasse_Code"
                    ]
                ),

            "Anteil_am_Standort":
                float(
                    row[
                        "_empirical_share"
                    ]
                ),

            "Waermemenge_kWh_a":
                annual_heat,

            "Temperatur_C":
                numeric_value(
                    row.get(
                        "Temperatur_Block_C",
                        np.nan,
                    )
                ),

            "Groessenklasse_Q":
                clean_string(
                    row.get(
                        "Groessenklasse_Q",
                        "",
                    )
                ),

            "Betriebsprofil_Code":
                operating[
                    "code"
                ],

            "Betriebsprofil_h_pro_Tag":
                float(
                    operating[
                        "hours_per_day"
                    ]
                ),

            "Betriebsprofil_Tage_pro_Woche":
                float(
                    operating[
                        "days_per_week"
                    ]
                ),

            "Startstunde_Tag":
                int(
                    generated[
                        "start_hour"
                    ]
                ),

            "Aktive_Stunden_Jahr":
                int(
                    generated[
                        "active_hours_year"
                    ]
                ),

            "Saisonfaktor_Sommer":
                seasonality[
                    "summer_factor"
                ],

            "Saisonfaktor_Winter":
                seasonality[
                    "winter_factor"
                ],

            "Saison_Aktive_Monate":
                seasonality[
                    "active_months"
                ],

            "Saison_Konzentration_0_1":
                seasonality[
                    "concentration"
                ],

            "Saisonfaktoren":
                dict(
                    seasonality[
                        "factors"
                    ]
                ),

            "Monatsenergieanteile":
                dict(
                    generated[
                        "monthly_energy_shares"
                    ]
                ),

            "Betriebsprofil_imputiert":
                bool(
                    parameters[
                        "operating_imputed"
                    ]
                ),

            "Saisonalitaet_imputiert":
                bool(
                    parameters[
                        "seasonality_imputed"
                    ]
                ),

            "Betriebsprofil_Donor_ID":
                parameters[
                    "operating_donor_id"
                ],

            "Betriebsprofil_Donor_Ebene":
                parameters[
                    "operating_donor_level"
                ],

            "Saisonalitaet_Donor_ID":
                parameters[
                    "seasonality_donor_id"
                ],

            "Saisonalitaet_Donor_Ebene":
                parameters[
                    "seasonality_donor_level"
                ],

            "profile_kWh":
                profile,
        }

        source_results.append(
            source
        )

        matrix_rows.append(
            profile
        )

        metadata_row = {
            key:
                value
            for key, value
            in source.items()
            if key
               not in {
                   "profile_kWh",
                   "Saisonfaktoren",
                   "Monatsenergieanteile",
               }
        }

        for month in MONTH_CODES:

            metadata_row[
                f"Saison_Faktor_{month}"
            ] = source[
                "Saisonfaktoren"
            ][
                month
            ]

            metadata_row[
                f"Energieanteil_{month}"
            ] = source[
                "Monatsenergieanteile"
            ][
                month
            ]

        metadata_rows.append(
            metadata_row
        )

        print_source_profile(
            number=
            source_number,

            total=
            len(
                source_rows
            ),

            source=
            source,
        )

    source_profiles = np.vstack(
        matrix_rows
    ).astype(
        FLOAT_DTYPE,
        copy=False,
    )

    q_types = np.array(
        [
            source[
                "Quellklasse_Code"
            ]
            for source
            in source_results
        ],
        dtype=str,
    )

    source_ids = np.array(
        [
            source[
                "Basis_Generator_Block_ID"
            ]
            for source
            in source_results
        ],
        dtype=str,
    )

    site_profile = source_profiles.sum(
        axis=0
    )

    expected_site_heat = float(
        structure[
            "generated_total_heat"
        ]
    )

    if not np.isclose(
            site_profile.sum(),
            expected_site_heat,
            rtol=1e-10,
            atol=1e-4,
    ):

        raise RuntimeError(
            "Standortprofil stimmt energetisch nicht mit "
            "der Standort-Jahreswärmemenge überein."
        )

    source_metadata = pd.DataFrame(
        metadata_rows
    )

    # -------------------------------------------------------------------------
    # Standortprofil in Konsole.
    # -------------------------------------------------------------------------

    print(f"  Standortprofil: {site_profile.shape}, "
          f"Jahreswärme {site_profile.sum() / 1e6:.3f} GWh/a; "
          f"Q-Typen: {', '.join(q_types)}")

    return {
        "generated_site_id":
            generated_site_id,

        "basis_site_id":
            basis_site_id,

        "empirical_site_heat_kWh_a":
            float(
                structure[
                    "empirical_total_heat"
                ]
            ),

        "generated_site_heat_kWh_a":
            expected_site_heat,

        "q_types":
            q_types,

        "source_ids":
            source_ids,

        "source_profiles":
            source_profiles,

        "site_profile":
            site_profile,

        "sources":
            source_results,

        "source_metadata":
            source_metadata,

        # Umfang des Kandidatenpools und tatsächliches Auswahlverfahren.
        "selection_mode": selection_info["selection_mode"],
        "selection_target": selection_info["selection_target"],
        "selection_tolerance": selection_info["selection_tolerance"],
        "matching_sites_in_window": selection_info["matching_sites_in_window"],
        "selection_candidate_count": selection_info["selection_candidate_count"],
        "available_sites_with_valid_value": selection_info["available_sites_with_valid_value"],
        "fallback_to_nearest": selection_info["fallback_to_nearest"],
        "score_file": selection_info["score_file"],
        "score_reference_site_count": selection_info["score_reference_site_count"],
        "associated_sites_by_heat": selection_info["associated_sites_by_heat"],
        "heat_association_relative_tolerance": selection_info["heat_association_relative_tolerance"],
        "available_sites_without_score": selection_info["available_sites_without_score"],
        **{key: selection_info[key] for key in (
            "use_heat_association", "exclude_heat_outliers",
            "outliers_removed_global", "outliers_removed_score_residual",
            "available_sites_before_outlier_filter", "regression_method",
            "regression_n", "regression_intercept_log10",
            "regression_slope_log10_per_score",
            "association_regression_corridor_kwh_a")},
        "selected_site_selection_origin": clean_string(basis_site.get("_Auswahl_Herkunft", "")),
        "selected_site_has_valid_score": bool(
            pd.notna(basis_site.get(SIZE_SCORE_COL))
            if selection_info["selection_mode"] == "KI_GROESSENSCORE"
            else False
        ),
        "selected_site_selection_value": (
            float(basis_site[SIZE_SCORE_COL])
            if selection_info["selection_mode"] == "KI_GROESSENSCORE"
               and pd.notna(basis_site.get(SIZE_SCORE_COL))
            else (
                float(basis_site["_Auswahl_Waermemenge_kWh_a"])
                if selection_info["selection_mode"] == "JAHRESABWAERME"
                else None
            )
        ),
        "selected_site_heat_kwh_a": float(basis_site["_Auswahl_Waermemenge_kWh_a"]),
        "association_reference_site_id": clean_string(
            basis_site.get("_Assoziation_Referenz_Standort_ID", "")
        ),
        "association_reference_heat_kwh_a": (
            float(basis_site["_Assoziation_Referenzwaerme_kWh_a"])
            if pd.notna(basis_site.get("_Assoziation_Referenzwaerme_kWh_a")) else None
        ),
        "association_relative_heat_difference": (
            float(basis_site["_Assoziation_Relative_Waermeabweichung"])
            if pd.notna(basis_site.get("_Assoziation_Relative_Waermeabweichung")) else None
        ),
    }


# =============================================================================
# 21. DATEIEN EINES STANDORTS SPEICHERN
# =============================================================================

def save_site_result(
        group_id,
        result,
        time_index,
):
    if not SAVE_OUTPUT_FILES:
        return

    output_folder = (
            OUTPUT_BASE_DIR
            /
            group_id
            /
            result[
                "generated_site_id"
            ]
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    np.save(
        output_folder
        / "source_profiles_8760.npy",
        result[
            "source_profiles"
        ],
        )

    np.save(
        output_folder
        / "site_profile_8760.npy",
        result[
            "site_profile"
        ],
        )

    np.savez_compressed(
        output_folder
        / "site_profiles.npz",

        source_profiles=
        result[
            "source_profiles"
        ],

        site_profile=
        result[
            "site_profile"
        ],

        q_types=
        result[
            "q_types"
        ],

        source_ids=
        result[
            "source_ids"
        ],

        generated_site_id=
        np.array(
            [
                result[
                    "generated_site_id"
                ]
            ],
            dtype=str,
        ),

        basis_site_id=
        np.array(
            [
                result[
                    "basis_site_id"
                ]
            ],
            dtype=str,
        ),
        )

    result[
        "source_metadata"
    ].to_csv(
        output_folder
        / "source_metadata.csv",
        sep=";",
        encoding="utf-8-sig",
        index=False,
        )

    pd.DataFrame(
        {
            "Stunde_Index":
                np.arange(
                    8760
                ),

            "Zeitstempel":
                time_index,

            "Standortprofil_kWh":
                result[
                    "site_profile"
                ],
        }
    ).to_csv(
        output_folder
        / "hourly_site_profile.csv",
        sep=";",
        encoding="utf-8-sig",
        index=False,
        )

    metadata = {
        "group_id":
            group_id,

        "generated_site_id":
            result[
                "generated_site_id"
            ],

        "basis_site_id":
            result[
                "basis_site_id"
            ],

        "reference_year":
            REFERENCE_YEAR,

        "n_sources":
            int(
                len(
                    result[
                        "q_types"
                    ]
                )
            ),

        "q_types":
            result[
                "q_types"
            ].tolist(),

        "empirical_site_heat_kWh_a":
            result[
                "empirical_site_heat_kWh_a"
            ],

        "generated_site_heat_kWh_a":
            result[
                "generated_site_heat_kWh_a"
            ],

        "target_site_annual_heat_kWh_a":
            TARGET_SITE_ANNUAL_HEAT_KWH,

        "random_seed": None,  # Jeder Aufruf verwendet frische Systementropie.
        "selection_mode": result["selection_mode"],
        "selection_target": result["selection_target"],
        "selection_tolerance": result["selection_tolerance"],
        "matching_sites_in_window": result["matching_sites_in_window"],
        "selection_candidate_count": result["selection_candidate_count"],
        "available_sites_with_valid_value": result["available_sites_with_valid_value"],
        "fallback_to_nearest": result["fallback_to_nearest"],
        "selected_site_selection_value": result["selected_site_selection_value"],
        "score_file": result["score_file"],
        "score_reference_site_count": result["score_reference_site_count"],
        "associated_sites_by_heat": result["associated_sites_by_heat"],
        "heat_association_relative_tolerance": result["heat_association_relative_tolerance"],
        "available_sites_without_score": result["available_sites_without_score"],
        **{key: result[key] for key in (
            "use_heat_association", "exclude_heat_outliers",
            "outliers_removed_global", "outliers_removed_score_residual",
            "available_sites_before_outlier_filter", "regression_method",
            "regression_n", "regression_intercept_log10",
            "regression_slope_log10_per_score",
            "association_regression_corridor_kwh_a")},
        "selected_site_selection_origin": result["selected_site_selection_origin"],
        "selected_site_has_valid_score": result["selected_site_has_valid_score"],
        "selected_site_heat_kwh_a": result["selected_site_heat_kwh_a"],
        "association_reference_site_id": result["association_reference_site_id"],
        "association_reference_heat_kwh_a": result["association_reference_heat_kwh_a"],
        "association_relative_heat_difference": result["association_relative_heat_difference"],

        "standard_start_hours":
            {
                str(key):
                    value
                for key, value
                in STANDARD_START_HOUR_BY_DAILY_HOURS.items()
            },

        "special_profile_default_start_hour":
            SPECIAL_PROFILE_DEFAULT_START_HOUR,
    }

    with open(
            output_folder
            / "site_generation_metadata.json",
            "w",
            encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2,
        )


# =============================================================================
# 22. EINEN ODER MEHRERE REALISTISCHE STANDORTE GENERIEREN
# =============================================================================

def generate_realistic_sites(
        group_id, *, size_score=None, score_tolerance=None,
        annual_heat_kwh=None, heat_tolerance_kwh=None,
        use_heat_association=True, exclude_heat_outliers=False, n_sites=None):
    """Erzeugt zufällige reale Standortstrukturen mit 8760h-Profilen.

    use_heat_association gilt nur für den Score-Modus; bei False werden
    ausschließlich direkt passende bewertete Standorte gezogen.
    exclude_heat_outliers entfernt Wärme-IQR-Ausreißer (beide Modi) sowie
    extreme Regressionsresiduen bewerteter Standorte (Score-Modus).
    """
    group_id = clean_string(group_id).upper()
    if not re.fullmatch(r"G\d+", group_id):
        raise ValueError("group_id muss z. B. 'G62' lauten.")
    n_to_generate = N_SITES_TO_GENERATE if n_sites is None else n_sites
    if not isinstance(n_to_generate, (int, np.integer)) or n_to_generate < 1:
        raise ValueError("n_sites muss eine positive ganze Zahl sein.")
    input_folder, sites, blocks, donors = load_group_data(group_id)
    if sites.empty or blocks.empty:
        raise ValueError(f"{group_id}: sites oder source_blocks ist leer.")
    if "Standortverbund_ID" not in sites.columns:
        raise ValueError("sites enthält keine Standortverbund_ID.")
    required = {"Generator_Block_ID", "Standortverbund_ID",
                "Quellklasse_Code", "Waermemenge_Block_kWh_a"}
    if not required.issubset(blocks.columns):
        raise ValueError(f"source_blocks fehlen Spalten: {required - set(blocks.columns)}")
    blocks = blocks.loc[blocks["Quellklasse_Code"].map(clean_string).isin(VALID_Q_TYPES)].copy()
    if blocks.empty:
        raise ValueError(f"{group_id}: keine Q1–Q7-Quellenblöcke.")
    candidates, selection_info = build_selection_candidates(
        group_id, sites, blocks, size_score=size_score, score_tolerance=score_tolerance,
        annual_heat_kwh=annual_heat_kwh, heat_tolerance_kwh=heat_tolerance_kwh,
        use_heat_association=use_heat_association,
        exclude_heat_outliers=exclude_heat_outliers)
    time_index = build_reference_time_index(REFERENCE_YEAR)
    rng = np.random.default_rng()
    print_model_assumptions()
    print(f"\nAUSWAHL | {group_id} | {selection_info['selection_mode']} | "
          f"{selection_info['selection_target']:,.3g} ± "
          f"{selection_info['selection_tolerance']:,.3g}")
    print(f"  Direkte Treffer im Fenster: {selection_info['matching_sites_in_window']} | "
          f"Score-Referenzen: {selection_info['score_reference_site_count']} | "
          f"Fallback: {selection_info['fallback_to_nearest']}")
    if selection_info['selection_mode'] == 'KI_GROESSENSCORE':
        print(f"  Abwärmeassoziation aktiviert: {selection_info['use_heat_association']} | "
              f"NEU ohne Score (±2 % und Regressionskorridor): "
              f"{selection_info['associated_sites_by_heat']}")
        if selection_info['association_regression_corridor_kwh_a']:
            lo, hi = selection_info['association_regression_corridor_kwh_a']
            print(f"  Regressionskorridor: {lo / 1e6:.3f}–{hi / 1e6:.3f} GWh/a "
                  f"({selection_info['regression_method']}, "
                  f"n={selection_info['regression_n']})")
    print(f"  Wärmeausreißer ausgeschlossen: {selection_info['exclude_heat_outliers']} | "
          f"entfernt: {selection_info['outliers_removed_global']} global + "
          f"{selection_info['outliers_removed_score_residual']} Score-Residuen")
    print(f"  Tatsächlicher Zufallspool: {selection_info['selection_candidate_count']} "
          "unterschiedliche Standorte")
    results, used_site_ids = [], set()
    for site_number in range(1, n_to_generate + 1):
        result = generate_one_site(
            group_id=group_id, site_number=site_number, sites=candidates, blocks=blocks,
            donors=donors, time_index=time_index, rng=rng,
            used_site_ids=used_site_ids, selection_info=selection_info)
        print(f"  Auswahlherkunft: {result['selected_site_selection_origin']}")
        save_site_result(group_id=group_id, result=result, time_index=time_index)
        results.append(result)
    return {"group_id": group_id, "time_index": time_index,
            "sites": results, **selection_info}


def generate_realistic_site(
        group_id, *, size_score=None, score_tolerance=None,
        annual_heat_kwh=None, heat_tolerance_kwh=None,
        use_heat_association=True, exclude_heat_outliers=False):
    """Ein zufällig gewählter Standort mit Quellen- und Standortprofil."""
    results = generate_realistic_sites(
        group_id, size_score=size_score, score_tolerance=score_tolerance,
        annual_heat_kwh=annual_heat_kwh, heat_tolerance_kwh=heat_tolerance_kwh,
        use_heat_association=use_heat_association,
        exclude_heat_outliers=exclude_heat_outliers, n_sites=1)
    site = results["sites"][0]
    site["group_id"] = results["group_id"]
    site["time_index"] = results["time_index"]
    return site


def summarize_group_size_extremes(group_id):
    """Mittlere Unternehmens-/Standortkennzahlen für Score 0–10 und 90–100.

    Enthält Q1–Q7-Jahreswärme und alle numerisch auswertbaren KI_Kennzahl_*-Werte.
    Je Kennzahl-Typ, Bezeichnung und Einheit werden nur vergleichbare Werte
    gemittelt. Fehlt ein Wert in der Randgruppe, wird der nächstgelegene
    verfügbare Score aus der Innenrichtung verwendet (kein Mittelwert).
    """
    group_id = clean_string(group_id).upper()
    if not re.fullmatch(r"G\d+", group_id):
        raise ValueError("group_id muss z. B. 'G62' lauten.")
    _, sites, blocks, _ = load_group_data(group_id)
    ki, ki_path = load_ki_size_table(group_id)
    heat = build_site_heat_table(blocks)
    IDs = sites["Standortverbund_ID"].map(clean_string).drop_duplicates()
    ki = ki.loc[ki["Standortverbund_ID"].isin(IDs)].copy()
    ki = ki.merge(heat, on="Standortverbund_ID", how="left", validate="one_to_one")
    ki = ki.loc[ki[SIZE_SCORE_COL].between(0, 100)].copy()
    if ki.empty:
        raise ValueError(f"{group_id}: keine bewerteten Standorte für die Statistik.")

    # Long-Format: Es kann bis zu fünf externe Kennzahlen pro Standort geben.
    metrics = [{"Standortverbund_ID": row["Standortverbund_ID"],
                "score": float(row[SIZE_SCORE_COL]),
                "typ": "ABWAERMEMENGE_Q1_Q7", "bezeichnung": "Jahresabwärme Q1–Q7",
                "einheit": "kWh/a", "wert": numeric_value(row["_Auswahl_Waermemenge_kWh_a"])}
               for _, row in ki.iterrows()]
    for _, row in ki.iterrows():
        for i in range(1, 6):
            prefix = f"KI_Kennzahl_{i}_"
            value_col = prefix + "Wert"
            if value_col not in ki.columns:
                continue
            value = numeric_value(row.get(value_col))
            if not np.isfinite(value):
                continue
            typ = clean_string(row.get(prefix + "Typ")) or "UNBEKANNTE_KENNZAHL"
            label = clean_string(row.get(prefix + "Bezeichnung")) or typ
            unit = clean_string(row.get(prefix + "Einheit")) or "ohne Einheit"
            metrics.append({"Standortverbund_ID": row["Standortverbund_ID"],
                            "score": float(row[SIZE_SCORE_COL]), "typ": typ,
                            "bezeichnung": label, "einheit": unit, "wert": value})
    df = pd.DataFrame(metrics)
    # Verhindert Doppelgewichtung, falls derselbe Kennzahltyp in mehreren
    # KI-Kennzahl-Slots eines Standorts erneut vorkommt.
    df = df.groupby(["Standortverbund_ID", "score", "typ", "bezeichnung", "einheit"],
                    as_index=False)["wert"].mean()
    rows = []
    groups = df.groupby(["typ", "bezeichnung", "einheit"], dropna=False, sort=True)
    for (kind, label, unit), metric in groups:
        for region, low, high, side in (
                ("UNTEN_0_10", 0., 10., "OBEN"),
                ("OBEN_90_100", 90., 100., "UNTEN")):
            valid = metric.loc[np.isfinite(metric["wert"])].copy()
            inside = valid.loc[valid["score"].between(low, high)].copy()
            if not inside.empty:
                status = "MITTELWERT_IM_SCOREBEREICH"
                chosen = inside
                nearest_score = None
            else:
                # Nur in Richtung Gruppenmitte extrapolieren: vom unteren
                # Scorebereich nach oben, vom oberen Scorebereich nach unten.
                alternatives = valid.loc[valid["score"] > high if side == "OBEN"
                else valid["score"] < low].copy()
                if alternatives.empty:
                    chosen = alternatives
                    status = "KEIN_VERFUEGBARER_WERT"
                    nearest_score = None
                else:
                    nearest_score = (float(alternatives["score"].min()) if side == "OBEN"
                                     else float(alternatives["score"].max()))
                    chosen = alternatives.loc[np.isclose(alternatives["score"],
                                                         nearest_score, rtol=0, atol=1e-9)]
                    status = "ERSATZ_NAECHSTER_SCORE_VON_" + side
            rows.append({
                "Scorebereich": region,
                "Kennzahltyp": kind, "Kennzahl": label, "Einheit": unit,
                "Mittelwert_oder_Ersatzwert": (float(chosen["wert"].mean())
                                               if not chosen.empty else None),
                "Anzahl_Werte": int(len(chosen)),
                "Anzahl_Standorte": int(chosen["Standortverbund_ID"].nunique()),
                "Status": status,
                "Ersatz_Score": nearest_score,
                "Ersatz_Standort_IDs": (", ".join(chosen["Standortverbund_ID"].astype(str))
                                        if nearest_score is not None else ""),
            })
    table = pd.DataFrame(rows)
    print(f"\nGRÖSSENVERGLEICH {group_id}: Score 0–10 / 90–100")
    print(f"  Bewertete Standorte: {len(ki)} | "
          f"unten: {int(ki[SIZE_SCORE_COL].between(0, 10).sum())} | "
          f"oben: {int(ki[SIZE_SCORE_COL].between(90, 100).sum())}")
    for _, row in table.iterrows():
        number = row["Mittelwert_oder_Ersatzwert"]
        rendered = f"{number:,.3g}" if number is not None and np.isfinite(number) else "k.A."
        suffix = (f" [Ersatz bei Score {row['Ersatz_Score']:g}]"
                  if pd.notna(row["Ersatz_Score"]) else "")
        print(f"  {row['Scorebereich']:>11} | {row['Kennzahltyp']} / "
              f"{row['Kennzahl']} [{row['Einheit']}]: {rendered} "
              f"(n={row['Anzahl_Standorte']}){suffix}")
    return {
        "group_id": group_id,
        "source_file": str(ki_path),
        "scored_site_count": int(len(ki)),
        "low_score_site_count": int(ki[SIZE_SCORE_COL].between(0, 10).sum()),
        "high_score_site_count": int(ki[SIZE_SCORE_COL].between(90, 100).sum()),
        "table": table,
        "rows": table.to_dict(orient="records"),
    }

def main():
    # Modus 1 – KI-Score: Abwärmeassoziation und Ausreißerfilter einzeln steuerbar.

    TARGET_GROUP = "G62"
    result = generate_realistic_site(
        group_id=TARGET_GROUP,
        size_score=65,
        score_tolerance=10,
        use_heat_association=True,
        exclude_heat_outliers=True,
    )
    # Modus 2 – alternativ, Jahresabwärme in kWh/a:
    # result = generate_realistic_site(
    #     group_id=TARGET_GROUP,
    #     annual_heat_kwh=10_000_000,
    #     heat_tolerance_kwh=2_000_000,
    #     exclude_heat_outliers=True,
    # )
    print(f"\nRückgabe: {result['source_profiles'].shape[0]} Quellen, "
          f"Standortprofil {result['site_profile'].shape}, "
          f"{result['selection_candidate_count']} mögliche Standortvorlagen.")
    # Separater Aufruf für Randbereiche 0–10 und 90–100:
    # extremes = summarize_group_size_extremes(TARGET_GROUP)
    # print(extremes["table"])

if __name__ == "__main__":
    main()
