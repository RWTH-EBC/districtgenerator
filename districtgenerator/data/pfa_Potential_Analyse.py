from pathlib import Path
import math
import re
import warnings

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter, MaxNLocator

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# =============================================================================
# PFA – GRUPPENANALYSE DER ABWÄRMEPOTENTIALE – ITERATION 7
# =============================================================================
#
# ZIEL
# ----
# Jede fertig aufbereitete Profil-/Experimentgruppe wird EINZELN analysiert.
# Es findet KEINE gruppenübergreifende Statistik statt.
#
# Analysiert werden insbesondere:
#
#   - Jahreswärmemenge / Größe der Quellen
#   - Q1-Q7 und Quellen-/Maschinenfamilien
#   - Quelltemperaturen
#   - Betriebs-/Verfügbarkeitsklassen
#   - Saisonalität
#   - äquivalente Vollaststunden Q_year / P_max (nur diagnostisch)
#   - Quellenstruktur innerhalb eines Standorts
#   - Unterschiede zwischen Standorten derselben Gruppe
#   - Konzentration / Dominanz einzelner Quellen
#   - Q-Klassen-Kookkurrenz innerhalb von Standorten
#   - numerische und kategoriale Abhängigkeiten
#   - explorative Standort-PCA als Hilfe zur Erkennung möglicher Standorttypen
#
# DATENBASIS
# ----------
# Der Code setzt auf den fertigen Gruppenordnern aus pfa_empirisch.py auf.
# Benötigt wird mindestens:
#
#   source_blocks.parquet ODER source_blocks.csv
#
# Optional wird sites.parquet/csv eingelesen; die wichtigsten Standortkennzahlen
# werden aber aus source_blocks selbst neu berechnet.
#
# WICHTIG
# -------
# Die gemeldete maximale thermische Leistung und daraus berechnete
# Vollaststunden sind NUR Diagnosegrößen. Sie steuern keine Eignung und keine
# Profilgenerierung.
#
# Die Diagramme und Kennzahlen sollen zunächst explorativ Muster sichtbar
# machen. Ein statistischer Zusammenhang ist keine Kausalitätsaussage.
# =============================================================================


# =============================================================================
# 1. KONFIGURATION
# =============================================================================

BASE_DIR = Path("WZ2025_Vorbereitung")
SOURCE_DIR = BASE_DIR / "Quellenklassifikation_final"

# Fertige empirische Datenpakete aus pfa_empirisch.py
INPUT_BASE_DIR = SOURCE_DIR / "Generator_Datenpakete_Iteration4"

# Neue, getrennte Analyseausgabe
OUTPUT_BASE_DIR = SOURCE_DIR / "Gruppenanalyse_Iteration7"

# Optionale, manuell bzw. per KI ergänzte Standortgrößenklassifikation.
# Version 2 enthält bis zu fünf unabhängige Größenkennzahlen je Standort.
SIZE_INFO_DIR = SOURCE_DIR / "KI_Standortgroesse_Recherche_v2" / "Einzelgruppen_fertig"
SIZE_INFO_SHEET = "Standorte_KI"
SIZE_INFO_GLOB = "KI_Standortgroesse_{group_id}*.xlsx"

# Falls die Bewertungsdatei außerhalb der Standardordner liegt, kann hier
# ein konkreter Pfad eingetragen werden. Normalerweise None lassen.
# Beispiel:
# SIZE_INFO_FILE_OVERRIDE = Path("KI_Standortgroesse_G62_Scores.xlsx")
SIZE_INFO_FILE_OVERRIDE = None


# Für die erste Iteration nur eine oder wenige Gruppen testen.
# Später: TARGET_GROUPS = None
TARGET_GROUPS = ["G62", "G06" , "G10", "G16", "G20", "G32", "G38", "G39", "G43", "G45"]

# Falls None: alle Unterordner Gxx analysieren.
GROUP_FOLDER_PATTERN = "G*"

# Diagrammoptionen
TOP_N_SITES_STACKED = 25
TOP_N_FAMILIES = 20
TOP_N_PORTFOLIOS = 20
TOP_N_EXTREMES = 30

# ---------------------------------------------------------------------------
# Einheitliche Kurzbezeichnungen der Abwärmeklassen in ALLEN Diagrammen,
# in denen Q1-Q7 dargestellt werden.
# ---------------------------------------------------------------------------
Q_ORDER = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]

Q_SHORT_LABELS = {
    "Q1": "Q1 – Flüssig",
    "Q2": "Q2 – Dampf/Kondensat",
    "Q3": "Q3 – Abluft/Prozessgas",
    "Q4": "Q4 – Rauchgas",
    "Q5": "Q5 – Diffus/Fest",
    "Q6": "Q6 – Kälte/Verflüssiger",
    "Q7": "Q7 – Druckluft/Kompressor",
}

# Bewusst ohne Lila; dieselben Farben werden über alle Q-Diagramme hinweg
# verwendet, damit die Klassen wiedererkennbar bleiben.
Q_COLORS = {
    "Q1": "#1f77b4",
    "Q2": "#17becf",
    "Q3": "#2ca02c",
    "Q4": "#d62728",
    "Q5": "#7f7f7f",
    "Q6": "#ff7f0e",
    "Q7": "#bcbd22",
}

# Standardisierte Betriebsprofile. Alles andere (BP_EXAKT_..., BP_UNBEKANNT,
# leere Angaben etc.) wird in den Diagrammen zu "Sonstige" zusammengefasst.
STANDARD_BP_ORDER = [
    "BP_8x5", "BP_12x5", "BP_16x5", "BP_20x5", "BP_24x5",
    "BP_8x7", "BP_12x7", "BP_16x7", "BP_20x7", "BP_24x7",
]
STANDARD_BP_SET = set(STANDARD_BP_ORDER)

BP_DISPLAY_LABELS = {
    "BP_8x5": "8 h × 5 d",
    "BP_12x5": "12 h × 5 d",
    "BP_16x5": "16 h × 5 d",
    "BP_20x5": "20 h × 5 d",
    "BP_24x5": "24 h × 5 d",
    "BP_8x7": "8 h × 7 d",
    "BP_12x7": "12 h × 7 d",
    "BP_16x7": "16 h × 7 d",
    "BP_20x7": "20 h × 7 d",
    "BP_24x7": "24 h × 7 d",
    "Sonstige": "Sonstige",
}

# Grau -> Dunkelgrün für Heatmaps. Kleine Werte erscheinen sehr hellgrau,
# hohe Werte dunkelgrün. Diese Skala wird für Q×Betrieb, Q×Temperatur,
# Q×Saison und Q-Kookkurrenz verwendet.
GREY_GREEN_CMAP = LinearSegmentedColormap.from_list(
    "grey_green",
    ["#f2f2f2", "#dfe8df", "#b8d3b9", "#74a978", "#2f6f3e", "#0b3d1d"],
)

# Regressionslinien in Punktwolken.
MIN_N_REGRESSION = 5
SHOW_OVERALL_REGRESSION = True
SHOW_Q_SPECIFIC_REGRESSIONS = True

# Vollaststunden – ausschließlich Diagnose
MAX_PHYSICAL_HOURS_PER_YEAR = 8784.0
LOW_FLH_STRONG = 10.0
LOW_FLH_WARNING = 100.0

# Saisonklassen
SEASON_STRONG_WINTER = 0.85
SEASON_FLAT_LOW = 0.95
SEASON_FLAT_HIGH = 1.05
SEASON_STRONG_SUMMER = 1.15

# Temperaturklassen
TEMP_BINS = [-np.inf, 25, 60, 90, 110, np.inf]
TEMP_LABELS = ["<25", "25-60", "60-90", "90-110", ">=110"]

# ---------------------------------------------------------------------------
# Vorbehandlung / robuste Ausreißerbehandlung
# ---------------------------------------------------------------------------
# Temperaturwerte außerhalb dieses sehr breiten physikalischen Korridors werden
# NICHT als gültige Temperatur in die Analyse übernommen. Die Quelle selbst
# bleibt für alle anderen Merkmale erhalten; der Rohwert wird dokumentiert.
TEMP_HARD_MIN_C = 10.0
TEMP_HARD_MAX_C = 800.0

# Extrem große Quellen können praktisch alle größenbezogenen Diagramme und
# Standortkennzahlen dominieren. Deshalb wird auf log10(Q_year) ein konservativer
# robuster Obergrenzentest durchgeführt. Eine Quelle wird nur dann automatisch
# ausgeschlossen, wenn sie oberhalb BEIDER starken Grenzwerte liegt:
#   Median + HEAT_OUTLIER_MAD_Z * 1.4826 * MAD
#   Q3     + HEAT_OUTLIER_IQR_MULTIPLIER * IQR
# Durch die AND-Regel werden nur sehr deutliche Ausreißer entfernt.
HEAT_OUTLIER_MIN_N = 20
HEAT_OUTLIER_MAD_Z = 5.0
HEAT_OUTLIER_IQR_MULTIPLIER = 3.0

# Bei kleineren Gruppen wird keine automatische Wärmemengenentfernung vorgenommen.
# Die berechneten Grenzwerte und alle Ausschlüsse werden separat exportiert.

# Schwellen für automatische Musterhinweise.
MIN_N_ASSOCIATION = 10
SPEARMAN_NOTE_THRESHOLD = 0.30
ETA2_NOTE_THRESHOLD = 0.10
CRAMERS_V_NOTE_THRESHOLD = 0.20

# Dateiausgabe
WRITE_EXCEL = True
WRITE_CSV_TABLES = True
WRITE_PNG = True


# =============================================================================
# 2. ALLGEMEINE HILFSFUNKTIONEN
# =============================================================================


def clean_string(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return text



def numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")



def safe_divide(numerator, denominator):
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator



def weighted_mean(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return np.nan
    return float(np.average(values[valid], weights=weights[valid]))



def weighted_std(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if valid.sum() < 2:
        return np.nan
    v = values[valid]
    w = weights[valid]
    mean = np.average(v, weights=w)
    variance = np.average((v - mean) ** 2, weights=w)
    return float(np.sqrt(variance))



def weighted_quantile(values, weights, q):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values = values[valid]
    weights = weights[valid]
    if len(values) == 0:
        return np.nan
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    cutoff = q * cumulative[-1]
    idx = np.searchsorted(cumulative, cutoff, side="left")
    idx = min(idx, len(values) - 1)
    return float(values[idx])



def first_existing_column(df, candidates):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None



def read_table_auto(folder: Path, basename: str, required=True):
    parquet_path = folder / f"{basename}.parquet"
    csv_path = folder / f"{basename}.csv"

    if parquet_path.exists():
        try:
            return pd.read_parquet(parquet_path)
        except Exception as exc:
            print(f"      WARNUNG {parquet_path.name}: {exc}")
            print("      CSV-Fallback wird versucht.")

    if csv_path.exists():
        # semikolon ist die Standardausgabe der bisherigen Codes
        return pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", low_memory=False)

    if required:
        raise FileNotFoundError(
            f"Weder {parquet_path.name} noch {csv_path.name} in {folder} gefunden."
        )
    return None



def group_sort_key(group_id):
    match = re.search(r"(\d+)", clean_string(group_id))
    return int(match.group(1)) if match else 10**9




def q_label(q):
    return Q_SHORT_LABELS.get(clean_string(q).upper(), clean_string(q))


def operating_profile_analysis_class(value):
    code = clean_string(value)
    return code if code in STANDARD_BP_SET else "Sonstige"


def ordered_present_qs(series):
    present = set(series.dropna().map(clean_string).str.upper())
    return [q for q in Q_ORDER if q in present]


def ordered_present_bp(series):
    present = set(series.dropna().map(clean_string))
    order = STANDARD_BP_ORDER + ["Sonstige"]
    return [bp for bp in order if bp in present]


def add_regression_line(
        ax,
        x,
        y,
        *,
        x_log=False,
        y_log=False,
        label="Regression gesamt",
        color="black",
        linestyle="--",
        linewidth=1.8,
        min_n=MIN_N_REGRESSION,
):
    """
    Fügt eine einfache lineare Regressionsgerade hinzu.

    Bei logarithmischer Achse wird auf dem logarithmierten Wert regressiert,
    damit die Gerade zur dargestellten Skala passt. Dies ist rein explorativ.
    """
    x = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(dtype=float)

    valid = np.isfinite(x) & np.isfinite(y)
    if x_log:
        valid &= x > 0
    if y_log:
        valid &= y > 0

    x = x[valid]
    y = y[valid]

    if len(x) < min_n:
        return None

    tx = np.log10(x) if x_log else x.copy()
    ty = np.log10(y) if y_log else y.copy()

    if np.nanstd(tx) <= 0 or np.nanstd(ty) <= 0:
        return None

    slope, intercept = np.polyfit(tx, ty, 1)
    pred = intercept + slope * tx

    ss_res = float(np.sum((ty - pred) ** 2))
    ss_tot = float(np.sum((ty - np.mean(ty)) ** 2))
    r2 = np.nan if ss_tot <= 0 else 1.0 - ss_res / ss_tot

    tx_line = np.linspace(np.min(tx), np.max(tx), 150)
    ty_line = intercept + slope * tx_line

    x_line = 10 ** tx_line if x_log else tx_line
    y_line = 10 ** ty_line if y_log else ty_line

    display_label = f"{label} (R²={r2:.2f}, n={len(x)})" if np.isfinite(r2) else f"{label} (n={len(x)})"

    ax.plot(
        x_line,
        y_line,
        color=color,
        linestyle=linestyle,
        linewidth=linewidth,
        label=display_label,
        zorder=4,
    )

    return {
        "n": len(x),
        "slope": float(slope),
        "intercept": float(intercept),
        "r2": float(r2) if np.isfinite(r2) else np.nan,
    }


def heatmap_with_grey_green(
        table,
        title,
        path,
        *,
        xlabel="",
        ylabel="",
        annotate=True,
        value_kind="count",
        mask_diagonal=False,
        triangle=None,
        x_labels=None,
        y_labels=None,
):
    if table is None or table.empty:
        return

    values = table.to_numpy(dtype=float)
    shown = values.copy()

    if mask_diagonal:
        diagonal_n = min(shown.shape[0], shown.shape[1])
        for idx in range(diagonal_n):
            shown[idx, idx] = np.nan

    # Für symmetrische Matrizen (z. B. Q-Kookkurrenz) kann nur eine Hälfte
    # dargestellt werden. "lower" zeigt ausschließlich die untere Dreiecksmatrix
    # ohne Diagonale; "upper" entsprechend die obere Hälfte.
    if triangle in {"lower", "upper", "lower_including_diagonal"}:
        for row_idx in range(shown.shape[0]):
            for col_idx in range(shown.shape[1]):
                if triangle == "lower" and row_idx <= col_idx:
                    shown[row_idx, col_idx] = np.nan
                elif triangle == "lower_including_diagonal" and row_idx < col_idx:
                    shown[row_idx, col_idx] = np.nan
                elif triangle == "upper" and row_idx >= col_idx:
                    shown[row_idx, col_idx] = np.nan

    cmap = GREY_GREEN_CMAP.copy()
    cmap.set_bad("#ffffff")

    finite = shown[np.isfinite(shown)]
    vmax = float(np.max(finite)) if finite.size else 1.0
    if vmax <= 0:
        vmax = 1.0

    fig_width = max(8.5, table.shape[1] * 0.9)
    fig_height = max(5.7, table.shape[0] * 0.72)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(shown, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)

    ax.set_xticks(np.arange(table.shape[1]))
    ax.set_yticks(np.arange(table.shape[0]))

    ax.set_xticklabels(
        x_labels if x_labels is not None else table.columns,
        rotation=45,
        ha="right",
    )
    ax.set_yticklabels(
        y_labels if y_labels is not None else table.index
    )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)

    if annotate:
        threshold = vmax * 0.58
        for row_idx in range(table.shape[0]):
            for col_idx in range(table.shape[1]):
                # Maskierte Felder (Diagonale bzw. redundante Hälfte) bleiben leer.
                if not np.isfinite(shown[row_idx, col_idx]):
                    continue

                value = values[row_idx, col_idx]
                if not np.isfinite(value):
                    continue

                if value_kind == "heat":
                    text_value = f"{value / 1e6:.1f}"
                elif value_kind == "percent":
                    text_value = f"{value:.1f}%"
                else:
                    text_value = f"{int(round(value))}"

                text_color = "white" if value >= threshold else "black"
                ax.text(
                    col_idx,
                    row_idx,
                    text_value,
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=8,
                )

    colorbar = fig.colorbar(image, ax=ax)
    if value_kind == "heat":
        colorbar.set_label("Wärmemenge [GWh/a]")
        # Heatmap values are stored in kWh; colorbar labels need GWh.
        colorbar.ax.yaxis.set_major_formatter(
            FuncFormatter(lambda value, _pos: f"{value / 1e6:.1f}")
        )
    elif value_kind == "percent":
        colorbar.set_label("Anteil [%]")
    else:
        colorbar.set_label("Anzahl")

    save_figure(fig, path)


def make_no_data_chart(path, title, message="Keine ausreichenden Daten für diese Darstellung."):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axis("off")
    ax.set_title(title)
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)
    save_figure(fig, path)


def season_class(value):
    if pd.isna(value):
        return "UNBEKANNT"
    if value < SEASON_STRONG_WINTER:
        return "STARK_WINTER"
    if value < SEASON_FLAT_LOW:
        return "LEICHT_WINTER"
    if value <= SEASON_FLAT_HIGH:
        return "NAHEZU_KONSTANT"
    if value <= SEASON_STRONG_SUMMER:
        return "LEICHT_SOMMER"
    return "STARK_SOMMER"



def flh_status(value):
    if pd.isna(value):
        return "KEINE_BELASTBARE_LEISTUNG"
    if value <= 0:
        return "UNPLAUSIBEL_LEQ_0"
    if value > MAX_PHYSICAL_HOURS_PER_YEAR:
        return "UEBER_8784"
    if value < LOW_FLH_STRONG:
        return "EXTREM_NIEDRIG_UNTER_10"
    if value < LOW_FLH_WARNING:
        return "NIEDRIG_UNTER_100"
    return "IM_PHYSIKALISCHEN_BEREICH"



def normalized_entropy(shares):
    shares = np.asarray(shares, dtype=float)
    shares = shares[np.isfinite(shares) & (shares > 0)]
    if len(shares) <= 1:
        return 0.0
    shares = shares / shares.sum()
    h = -np.sum(shares * np.log(shares))
    return float(h / np.log(len(shares)))



def hhi(shares):
    shares = np.asarray(shares, dtype=float)
    shares = shares[np.isfinite(shares) & (shares > 0)]
    if len(shares) == 0:
        return np.nan
    shares = shares / shares.sum()
    return float(np.sum(shares**2))



def eta_squared(categories, values):
    """Deskriptive Effektgröße: Anteil der Varianz in y, der durch Gruppenmittel erklärt wird."""
    temp = pd.DataFrame({"cat": categories, "value": values}).dropna()
    temp["cat"] = temp["cat"].map(clean_string)
    temp = temp[temp["cat"] != ""]
    if len(temp) < MIN_N_ASSOCIATION or temp["cat"].nunique() < 2:
        return np.nan, len(temp), temp["cat"].nunique()

    overall = temp["value"].mean()
    ss_total = ((temp["value"] - overall) ** 2).sum()
    if ss_total <= 0:
        return 0.0, len(temp), temp["cat"].nunique()

    ss_between = 0.0
    for _, grp in temp.groupby("cat"):
        ss_between += len(grp) * (grp["value"].mean() - overall) ** 2

    return float(ss_between / ss_total), len(temp), temp["cat"].nunique()



def cramers_v(series_a, series_b):
    temp = pd.DataFrame({"a": series_a, "b": series_b}).dropna()
    temp["a"] = temp["a"].map(clean_string)
    temp["b"] = temp["b"].map(clean_string)
    temp = temp[(temp["a"] != "") & (temp["b"] != "")]
    if len(temp) < MIN_N_ASSOCIATION:
        return np.nan, len(temp), 0, 0

    table = pd.crosstab(temp["a"], temp["b"])
    if table.shape[0] < 2 or table.shape[1] < 2:
        return np.nan, len(temp), table.shape[0], table.shape[1]

    observed = table.to_numpy(dtype=float)
    n = observed.sum()
    row_sum = observed.sum(axis=1, keepdims=True)
    col_sum = observed.sum(axis=0, keepdims=True)
    expected = row_sum @ col_sum / n
    valid = expected > 0
    chi2 = np.sum(((observed - expected) ** 2 / expected)[valid])

    phi2 = chi2 / n
    r, k = observed.shape
    # bias-korrigierte Variante nach Bergsma/Wicher
    phi2corr = max(0.0, phi2 - ((k - 1) * (r - 1)) / max(n - 1, 1))
    rcorr = r - ((r - 1) ** 2) / max(n - 1, 1)
    kcorr = k - ((k - 1) ** 2) / max(n - 1, 1)
    denom = min(kcorr - 1, rcorr - 1)
    if denom <= 0:
        return np.nan, int(n), r, k
    return float(np.sqrt(phi2corr / denom)), int(n), r, k



def spearman_pair(df, x, y):
    temp = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(temp) < MIN_N_ASSOCIATION:
        return np.nan, len(temp)
    if temp[x].nunique() < 2 or temp[y].nunique() < 2:
        return np.nan, len(temp)
    rho = temp[x].rank(method="average").corr(temp[y].rank(method="average"))
    return float(rho), len(temp)


# =============================================================================
# 3. QUELLENTABELLE AUFBEREITEN
# =============================================================================


def prepare_source_table(blocks: pd.DataFrame, group_id: str):
    df = blocks.copy()

    required = [
        "Generator_Block_ID",
        "Standortverbund_ID",
        "Quellklasse_Code",
        "Waermemenge_Block_kWh_a",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{group_id}: source_blocks fehlen Pflichtspalten: {', '.join(missing)}"
        )

    df["Experiment_Gruppe"] = group_id
    df["Generator_Block_ID"] = df["Generator_Block_ID"].map(clean_string)
    df["Standortverbund_ID"] = df["Standortverbund_ID"].map(clean_string)
    df["Quellklasse_Code"] = df["Quellklasse_Code"].map(clean_string).str.upper()

    df["Waermemenge_kWh_a"] = numeric_series(df["Waermemenge_Block_kWh_a"])

    temp_col = first_existing_column(
        df,
        ["Temperatur_Block_C", "Temperatur_final_C"],
    )
    df["Temperatur_C"] = numeric_series(df[temp_col]) if temp_col else np.nan

    power_col = first_existing_column(
        df,
        ["Leistung_Summe_nur_Diagnose_kW", "Leistung_final_kW"],
    )
    df["Leistung_Diagnose_kW"] = numeric_series(df[power_col]) if power_col else np.nan

    df["Vollaststunden_h_a"] = np.where(
        df["Leistung_Diagnose_kW"] > 0,
        df["Waermemenge_kWh_a"] / df["Leistung_Diagnose_kW"],
        np.nan,
        )
    df["Vollaststunden_Status"] = df["Vollaststunden_h_a"].map(flh_status)
    df["Vollaststunden_im_physikalischen_Bereich"] = (
            df["Vollaststunden_h_a"].notna()
            & (df["Vollaststunden_h_a"] > 0)
            & (df["Vollaststunden_h_a"] <= MAX_PHYSICAL_HOURS_PER_YEAR)
    )

    # Möglicher x1000-Hinweis: nur Diagnose, keine automatische Korrektur.
    flh_x1000 = np.where(
        df["Leistung_Diagnose_kW"] > 0,
        (df["Waermemenge_kWh_a"] * 1000.0) / df["Leistung_Diagnose_kW"],
        np.nan,
        )
    df["Moeglicher_x1000_Kandidat"] = (
            df["Vollaststunden_h_a"].notna()
            & (df["Vollaststunden_h_a"] < LOW_FLH_STRONG)
            & (flh_x1000 >= LOW_FLH_WARNING)
            & (flh_x1000 <= MAX_PHYSICAL_HOURS_PER_YEAR)
    )

    df["log10_Waermemenge"] = np.where(
        df["Waermemenge_kWh_a"] > 0,
        np.log10(df["Waermemenge_kWh_a"]),
        np.nan,
        )

    # Temperaturklasse
    df["Temperaturklasse_Analyse"] = pd.cut(
        df["Temperatur_C"],
        bins=TEMP_BINS,
        labels=TEMP_LABELS,
        right=False,
    ).astype("object")
    df["Temperaturklasse_Analyse"] = df["Temperaturklasse_Analyse"].fillna("UNBEKANNT")

    # Betriebsprofil
    if "Betriebsprofil_Code" not in df.columns:
        df["Betriebsprofil_Code"] = "BP_UNBEKANNT"
    df["Betriebsprofil_Code"] = df["Betriebsprofil_Code"].map(clean_string)

    # Für Diagramme werden nur die zehn vorgesehenen Standardprofile einzeln
    # dargestellt. Alle Sonder-/unbekannten Profile erscheinen gemeinsam als
    # "Sonstige". Die Originalspalte bleibt unverändert erhalten.
    df["Betriebsprofil_Analyse"] = df["Betriebsprofil_Code"].map(
        operating_profile_analysis_class
    )

    hours_col = first_existing_column(
        df,
        ["Betriebsprofil_h_pro_Tag", "Betriebsprofil_Generator_h_pro_Tag"],
    )
    days_col = first_existing_column(
        df,
        ["Betriebsprofil_Tage_pro_Woche", "Betriebsprofil_Generator_Tage_pro_Woche"],
    )
    df["Betrieb_h_Tag"] = numeric_series(df[hours_col]) if hours_col else np.nan
    df["Betrieb_Tage_Woche"] = numeric_series(df[days_col]) if days_col else np.nan

    # Saisonalität
    if "Saisonfaktor_Sommer" not in df.columns:
        df["Saisonfaktor_Sommer"] = np.nan
    else:
        df["Saisonfaktor_Sommer"] = numeric_series(df["Saisonfaktor_Sommer"])

    if "Saisonfaktor_Winter" not in df.columns:
        df["Saisonfaktor_Winter"] = np.nan
    else:
        df["Saisonfaktor_Winter"] = numeric_series(df["Saisonfaktor_Winter"])

    if "Saison_Konzentration_0_1" not in df.columns:
        df["Saison_Konzentration_0_1"] = np.nan
    else:
        df["Saison_Konzentration_0_1"] = numeric_series(df["Saison_Konzentration_0_1"])

    if "Saison_Aktive_Monate" not in df.columns:
        df["Saison_Aktive_Monate"] = np.nan
    else:
        df["Saison_Aktive_Monate"] = numeric_series(df["Saison_Aktive_Monate"])

    df["Saisonklasse"] = df["Saisonfaktor_Sommer"].map(season_class)

    # Quellenfamilie
    if "Quellenfamilie_normalisiert" not in df.columns:
        df["Quellenfamilie_normalisiert"] = ""
    df["Quellenfamilie_normalisiert"] = df["Quellenfamilie_normalisiert"].map(clean_string)

    if "Original_Quellennamen" not in df.columns:
        df["Original_Quellennamen"] = ""

    if "Groessenklasse_Q" not in df.columns:
        df["Groessenklasse_Q"] = ""

    # Standortanteil neu berechnen – unabhängig von vorhandenen Feldern.
    site_total = df.groupby("Standortverbund_ID")["Waermemenge_kWh_a"].transform("sum")
    df["Anteil_Quelle_am_Standort"] = df["Waermemenge_kWh_a"] / site_total

    return df


def preprocess_analysis_sources(sources: pd.DataFrame):
    """
    Robuste Vorbehandlung ausschließlich für die explorative Gruppenanalyse.

    1) Unglaubwürdige Temperaturen:
       - Rohwert bleibt in Temperatur_C_Roh erhalten.
       - außerhalb TEMP_HARD_MIN_C .. TEMP_HARD_MAX_C -> Temperatur_C = NaN
       - Quelle bleibt für alle nicht temperaturbezogenen Analysen erhalten.

    2) Extrem große Jahreswärmemengen:
       - Erkennung auf log10(Q_year) innerhalb DER AKTUELLEN PROFILGRUPPE.
       - automatische Entfernung nur bei mindestens HEAT_OUTLIER_MIN_N Quellen.
       - Quelle muss oberhalb des starken MAD- UND IQR-Grenzwerts liegen.
       - ausgeschlossene Quellen werden vollständig dokumentiert.
    """
    df = sources.copy()

    # ------------------------------------------------------------------
    # Temperatur
    # ------------------------------------------------------------------
    df["Temperatur_C_Roh"] = df["Temperatur_C"]
    temp_invalid = (
            df["Temperatur_C_Roh"].notna()
            & (
                    (df["Temperatur_C_Roh"] < TEMP_HARD_MIN_C)
                    | (df["Temperatur_C_Roh"] > TEMP_HARD_MAX_C)
            )
    )
    df["Temperatur_unplausibel"] = temp_invalid
    df.loc[temp_invalid, "Temperatur_C"] = np.nan

    # Temperaturklassen nach der Bereinigung neu bilden.
    df["Temperaturklasse_Analyse"] = pd.cut(
        df["Temperatur_C"],
        bins=TEMP_BINS,
        labels=TEMP_LABELS,
        right=False,
    ).astype("object")
    df["Temperaturklasse_Analyse"] = df["Temperaturklasse_Analyse"].fillna("UNBEKANNT")

    # ------------------------------------------------------------------
    # Wärmemenge – nur starke obere Ausreißer
    # ------------------------------------------------------------------
    valid_heat = df.loc[df["Waermemenge_kWh_a"] > 0, "Waermemenge_kWh_a"].dropna()
    log_heat = np.log10(valid_heat.to_numpy(dtype=float))

    bound_mad = np.nan
    bound_iqr = np.nan
    final_log_bound = np.nan
    final_heat_bound = np.nan

    if len(log_heat) >= HEAT_OUTLIER_MIN_N:
        median = float(np.median(log_heat))
        mad = float(np.median(np.abs(log_heat - median)))
        robust_sigma = 1.4826 * mad
        q1, q3 = np.quantile(log_heat, [0.25, 0.75])
        iqr = float(q3 - q1)

        # Falls MAD oder IQR == 0, ist der jeweilige Test nicht informativ.
        bound_mad = median + HEAT_OUTLIER_MAD_Z * robust_sigma if robust_sigma > 0 else np.nan
        bound_iqr = float(q3 + HEAT_OUTLIER_IQR_MULTIPLIER * iqr) if iqr > 0 else np.nan

        available_bounds = [v for v in [bound_mad, bound_iqr] if np.isfinite(v)]
        if available_bounds:
            # max(...) entspricht der konservativen AND-Logik.
            final_log_bound = max(available_bounds)
            final_heat_bound = 10 ** final_log_bound

    df["Waerme_Ausreisser_stark"] = False
    if np.isfinite(final_log_bound):
        df.loc[
            df["Waermemenge_kWh_a"].notna()
            & (df["Waermemenge_kWh_a"] > 0)
            & (np.log10(df["Waermemenge_kWh_a"]) > final_log_bound),
            "Waerme_Ausreisser_stark",
        ] = True

    df["Analyse_Ausschluss"] = df["Waerme_Ausreisser_stark"]
    df["Analyse_Ausschlussgrund"] = np.where(
        df["Waerme_Ausreisser_stark"],
        "EXTREME_WAERMEMENGE_GRUPPENAUSREISSER",
        "",
    )

    # Vollaststunden hängen von Q_year ab; bei ausgeschlossenen Quellen werden
    # sie nicht analysiert. Temperaturfehler beeinflussen Vollaststunden nicht.
    analysis = df.loc[~df["Analyse_Ausschluss"]].copy()

    # Standortanteile NACH Ausschluss neu berechnen, damit alle internen
    # Standortkennzahlen auf derselben bereinigten Datenbasis beruhen.
    site_total = analysis.groupby("Standortverbund_ID")["Waermemenge_kWh_a"].transform("sum")
    analysis["Anteil_Quelle_am_Standort"] = analysis["Waermemenge_kWh_a"] / site_total

    excluded_cols = [
        "Experiment_Gruppe",
        "Generator_Block_ID",
        "Standortverbund_ID",
        "Quellklasse_Code",
        "Original_Quellennamen",
        "Quellenfamilie_normalisiert",
        "Waermemenge_kWh_a",
        "Temperatur_C_Roh",
        "Betriebsprofil_Code",
        "Saisonfaktor_Sommer",
        "Analyse_Ausschlussgrund",
    ]
    excluded_cols = [c for c in excluded_cols if c in df.columns]
    excluded_heat = df.loc[df["Analyse_Ausschluss"], excluded_cols].copy()

    temp_cols = [
        "Experiment_Gruppe",
        "Generator_Block_ID",
        "Standortverbund_ID",
        "Quellklasse_Code",
        "Original_Quellennamen",
        "Quellenfamilie_normalisiert",
        "Waermemenge_kWh_a",
        "Temperatur_C_Roh",
    ]
    temp_cols = [c for c in temp_cols if c in df.columns]
    invalid_temps = df.loc[df["Temperatur_unplausibel"], temp_cols].copy()
    if not invalid_temps.empty:
        invalid_temps["Behandlung"] = (
            f"Temperatur außerhalb [{TEMP_HARD_MIN_C:g}; {TEMP_HARD_MAX_C:g}] °C; "
            "für temperaturbezogene Analysen auf fehlend gesetzt, Quelle sonst beibehalten."
        )

    pre_summary = pd.DataFrame([
        ["Quellen_vor_Bereinigung", int(len(df))],
        ["Quellen_nach_Waermeausreisserfilter", int(len(analysis))],
        ["Ausgeschlossene_extreme_Waermemengen", int(df["Analyse_Ausschluss"].sum())],
        ["Unplausible_Temperaturen_auf_NaN", int(df["Temperatur_unplausibel"].sum())],
        ["Temperatur_Min_erlaubt_C", TEMP_HARD_MIN_C],
        ["Temperatur_Max_erlaubt_C", TEMP_HARD_MAX_C],
        ["Waermeausreisser_Min_N", HEAT_OUTLIER_MIN_N],
        ["Waermeausreisser_MAD_Z", HEAT_OUTLIER_MAD_Z],
        ["Waermeausreisser_IQR_Multiplikator", HEAT_OUTLIER_IQR_MULTIPLIER],
        ["log10_Grenze_MAD", bound_mad],
        ["log10_Grenze_IQR", bound_iqr],
        ["log10_finale_Grenze", final_log_bound],
        ["Finale_Waermemengen_Grenze_kWh_a", final_heat_bound],
        ["Ausgeschlossene_Waermemenge_kWh_a", float(df.loc[df["Analyse_Ausschluss"], "Waermemenge_kWh_a"].sum())],
    ], columns=["Kennzahl", "Wert"])

    return analysis, df, excluded_heat, invalid_temps, pre_summary


# =============================================================================
# 4. STANDORTKENNZAHLEN
# =============================================================================


def build_site_metrics(sources: pd.DataFrame):
    rows = []

    for site_id, grp in sources.groupby("Standortverbund_ID", sort=False):
        grp = grp.copy()
        heat = grp["Waermemenge_kWh_a"].fillna(0.0)
        total_heat = heat.sum()
        if total_heat <= 0:
            continue

        shares = (heat / total_heat).to_numpy(dtype=float)
        sorted_shares = np.sort(shares)[::-1]

        q_heat = {
            q: float(grp.loc[grp["Quellklasse_Code"] == q, "Waermemenge_kWh_a"].sum())
            for q in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]
        }
        portfolio = [q for q in q_heat if q_heat[q] > 0]

        valid_temp = grp["Temperatur_C"].notna()
        temp_vals = grp.loc[valid_temp, "Temperatur_C"]
        temp_weights = grp.loc[valid_temp, "Waermemenge_kWh_a"]

        valid_season = grp["Saisonfaktor_Sommer"].notna()
        season_vals = grp.loc[valid_season, "Saisonfaktor_Sommer"]
        season_weights = grp.loc[valid_season, "Waermemenge_kWh_a"]

        valid_conc = grp["Saison_Konzentration_0_1"].notna()
        conc_vals = grp.loc[valid_conc, "Saison_Konzentration_0_1"]
        conc_weights = grp.loc[valid_conc, "Waermemenge_kWh_a"]

        valid_flh = grp["Vollaststunden_im_physikalischen_Bereich"]
        flh_vals = grp.loc[valid_flh, "Vollaststunden_h_a"]

        bp_24x7 = grp["Betriebsprofil_Code"].eq("BP_24x7")
        days7 = grp["Betrieb_Tage_Woche"].eq(7)
        hours20plus = grp["Betrieb_h_Tag"].ge(20)

        high_temp = grp["Temperatur_C"].ge(110)
        low_temp = grp["Temperatur_C"].lt(60)
        seasonal_extreme = (
                grp["Saisonfaktor_Sommer"].lt(SEASON_STRONG_WINTER)
                | grp["Saisonfaktor_Sommer"].gt(SEASON_STRONG_SUMMER)
        )

        row = {
            "Standortverbund_ID": site_id,
            "Waermemenge_Standort_kWh_a": float(total_heat),
            "log10_Waermemenge_Standort": float(np.log10(total_heat)),
            "Anzahl_Quellenbloecke": int(len(grp)),
            "Anzahl_Q_Klassen": int(len(portfolio)),
            "Quellenportfolio": "+".join(portfolio),
            "Groesste_Quelle_Anteil": float(sorted_shares[0]),
            "Top2_Quellen_Anteil": float(sorted_shares[:2].sum()),
            "Top3_Quellen_Anteil": float(sorted_shares[:3].sum()),
            "HHI_Quellenwaerme": hhi(shares),
            "Entropie_Quellenwaerme_normiert": normalized_entropy(shares),
            "Anzahl_Betriebsprofile": int(grp["Betriebsprofil_Code"].replace("", np.nan).nunique()),
            "Anteil_Waerme_BP_24x7": safe_divide(grp.loc[bp_24x7, "Waermemenge_kWh_a"].sum(), total_heat),
            "Anteil_Waerme_7Tage": safe_divide(grp.loc[days7, "Waermemenge_kWh_a"].sum(), total_heat),
            "Anteil_Waerme_ge20h_Tag": safe_divide(grp.loc[hours20plus, "Waermemenge_kWh_a"].sum(), total_heat),
            "Temperatur_gew_Mittel_C": weighted_mean(temp_vals, temp_weights),
            "Temperatur_Min_C": float(temp_vals.min()) if len(temp_vals) else np.nan,
            "Temperatur_Max_C": float(temp_vals.max()) if len(temp_vals) else np.nan,
            "Temperatur_Spanne_K": float(temp_vals.max() - temp_vals.min()) if len(temp_vals) else np.nan,
            "Anteil_Waerme_Temp_ge110C": safe_divide(grp.loc[high_temp, "Waermemenge_kWh_a"].sum(), total_heat),
            "Anteil_Waerme_Temp_lt60C": safe_divide(grp.loc[low_temp, "Waermemenge_kWh_a"].sum(), total_heat),
            "Sommerfaktor_gew_Mittel": weighted_mean(season_vals, season_weights),
            "Sommerfaktor_gew_Std": weighted_std(season_vals, season_weights),
            "Saison_Konzentration_gew_Mittel": weighted_mean(conc_vals, conc_weights),
            "Anteil_Waerme_stark_saisonal": safe_divide(grp.loc[seasonal_extreme, "Waermemenge_kWh_a"].sum(), total_heat),
            "Vollaststunden_Median_im_Bereich": float(flh_vals.median()) if len(flh_vals) else np.nan,
            "Anzahl_Vollaststunden_belastbar": int(len(flh_vals)),
        }

        for q in q_heat:
            row[f"Waermemenge_{q}_kWh_a"] = q_heat[q]
            row[f"Anteil_{q}"] = safe_divide(q_heat[q], total_heat)

        rows.append(row)

    return pd.DataFrame(rows)


# =============================================================================
# 4b. OPTIONALE STANDORTGRÖSSEN-RECHERCHE ANBINDEN – VERSION 2
# =============================================================================


def _score_use_is_direct(value) -> bool:
    """Accept explicit YES-style or DIREKT_* flags; missing flags remain missing."""
    flag = clean_string(value).upper()
    if flag.startswith("DIREKT"):
        return True
    return flag in {"JA", "J", "YES", "Y", "TRUE", "WAHR", "1", "1.0", "X", "VERWENDET", "GENUTZT", "FUER_SCORE", "FÜR_SCORE"}


def find_size_info_file(group_id: str):
    if SIZE_INFO_FILE_OVERRIDE is not None:
        path = Path(SIZE_INFO_FILE_OVERRIDE)
        if path.exists():
            return path.resolve()
        warnings.warn(f"SIZE_INFO_FILE_OVERRIDE nicht gefunden: {path}")

    patterns = [
        f"KI_Standortgroesse_{group_id}_Scores*.xlsx",
        f"KI_Standortgroesse_{group_id}_scores*.xlsx",
        f"KI_Standortgroesse_{group_id}_v2*.xlsx",
        f"KI_Standortgroesse_{group_id}*Score*.xlsx",
        f"KI_Standortgroesse_{group_id}*.xlsx",
        SIZE_INFO_GLOB.format(group_id=group_id),
    ]

    # Neue v2-Struktur zuerst; ältere Orte bleiben nur als Fallback erhalten.
    search_dirs = [
        SIZE_INFO_DIR / "Einzelgruppen",
        SIZE_INFO_DIR,
        SOURCE_DIR / "KI_Standortgroesse_Recherche" / "Einzelgruppen",
        SOURCE_DIR / "KI_Standortgroesse_Recherche",
        SOURCE_DIR,
        BASE_DIR,
        Path('.'),
        ]

    candidates = []
    for folder in search_dirs:
        folder = Path(folder)
        if not folder.exists():
            continue
        for pattern in patterns:
            candidates.extend(folder.glob(pattern))

    candidates = sorted({p.resolve() for p in candidates if p.is_file()})
    if not candidates:
        return None

    # Neueste Datei bevorzugen; temporäre Excel-Sperrdateien ausschließen.
    candidates = [p for p in candidates if not p.name.startswith("~$")]
    candidates = sorted(
        candidates,
        key=lambda p: (p.stat().st_mtime, len(p.name)),
        reverse=True,
    )
    return candidates[0] if candidates else None


def load_size_info(group_id: str):
    path = find_size_info_file(group_id)
    if path is None:
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, sheet_name=SIZE_INFO_SHEET)
    except Exception as exc:
        warnings.warn(f"Standortgrößendatei konnte nicht gelesen werden: {path} – {exc}")
        return pd.DataFrame()

    if "Standortverbund_ID" not in df.columns:
        warnings.warn(f"{path.name}: Standortverbund_ID fehlt.")
        return pd.DataFrame()

    # Version-2-Felder vollständig mitnehmen. Dadurch bleiben auch Kennzahlen
    # erhalten, die recherchiert wurden, aber bewusst NICHT in den Score
    # eingegangen sind.
    base_columns = [
        "Standortverbund_ID",
        "Recherche_ID",
        "Experiment_Gruppe",
        "Firmenname",
        "Standortname",
        "KI_Bearbeitungsstatus",
        "KI_Standortidentifikation_Sicherheit",
        "KI_Recherchierter_Standortname",
        "KI_Anzahl_recherchierter_Kennzahlen",
        "KI_Anzahl_fuer_Score_verwendeter_Kennzahlen",
        "KI_Fuer_Score_verwendete_Kennzahlen",
        "KI_Score_Methodik",
        "KI_Relativer_Groessenscore_0_100",
        "KI_Groessenklasse_innerhalb_Gruppe",
        "KI_Vertrauen_Groessenschaetzung",
        "KI_Kurzbegruendung_Score",
        "KI_Mehrstandortunternehmen_Hinweis",
        "KI_Recherchehinweise",
    ]

    metric_columns = []
    for idx in range(1, 6):
        prefix = f"KI_Kennzahl_{idx}_"
        metric_columns.extend([c for c in df.columns if c.startswith(prefix)])

    keep = []
    for col in base_columns + metric_columns:
        if col in df.columns and col not in keep:
            keep.append(col)

    out = df[keep].copy()
    out["Standortverbund_ID"] = out["Standortverbund_ID"].map(clean_string)
    out = out[out["Standortverbund_ID"].ne("")].copy()

    score_col = "KI_Relativer_Groessenscore_0_100"
    if score_col not in out.columns:
        out[score_col] = np.nan
    out[score_col] = pd.to_numeric(out[score_col], errors="coerce")
    out.loc[~out[score_col].between(0, 100, inclusive="both"), score_col] = np.nan

    if "KI_Groessenklasse_innerhalb_Gruppe" not in out.columns:
        out["KI_Groessenklasse_innerhalb_Gruppe"] = ""
    out["KI_Groessenklasse_innerhalb_Gruppe"] = (
        out["KI_Groessenklasse_innerhalb_Gruppe"].fillna("").map(clean_string)
    )

    # Ein Score gilt nur dann als vorhanden, wenn tatsächlich ein numerischer
    # Wert vorliegt. Fehlende Scores werden NICHT als 0 interpretiert.
    out["KI_Hat_Groessenscore"] = out[score_col].notna()

    # Tatsächliche Zahl direkter Score-Kennzahlen robust aus den fünf Slots
    # ableiten. Das funktioniert auch mit Werten wie DIREKT_PERSONAL oder
    # DIREKT_FLAECHE statt nur JA/NEIN.
    direct_counts = pd.Series(0, index=out.index, dtype=int)
    for idx in range(1, 6):
        col = f"KI_Kennzahl_{idx}_Fuer_Score_verwenden"
        if col in out.columns:
            direct_counts += out[col].map(_score_use_is_direct).astype(int)
    out["KI_Anzahl_direkter_Scorekennzahlen_abgeleitet"] = direct_counts

    out["KI_Quelldatei"] = str(path)
    out = out.drop_duplicates(subset=["Standortverbund_ID"], keep="first")
    return out


def build_size_metrics_long(size_info: pd.DataFrame):
    """Bis zu fünf Recherchekennzahlen je Standort in Langform."""
    if size_info.empty:
        return pd.DataFrame()

    rows = []
    for _, row in size_info.iterrows():
        site_id = clean_string(row.get("Standortverbund_ID", ""))
        if not site_id:
            continue

        score = pd.to_numeric(
            pd.Series([row.get("KI_Relativer_Groessenscore_0_100", np.nan)]),
            errors="coerce",
        ).iloc[0]

        for idx in range(1, 6):
            prefix = f"KI_Kennzahl_{idx}_"
            typ = clean_string(row.get(prefix + "Typ", ""))
            bezeichnung = clean_string(row.get(prefix + "Bezeichnung", ""))
            wert = pd.to_numeric(
                pd.Series([row.get(prefix + "Wert", np.nan)]), errors="coerce"
            ).iloc[0]
            einheit = clean_string(row.get(prefix + "Einheit", ""))
            use_raw = clean_string(row.get(prefix + "Fuer_Score_verwenden", ""))

            # Leere Slots nicht künstlich als Kennzahl ausgeben.
            if not typ and not bezeichnung and pd.isna(wert) and not einheit:
                continue

            rows.append({
                "Standortverbund_ID": site_id,
                "Kennzahl_Slot": idx,
                "Kennzahl_Typ": typ,
                "Kennzahl_Bezeichnung": bezeichnung,
                "Kennzahl_Wert": wert,
                "Kennzahl_Einheit": einheit,
                "Kennzahl_Jahr": row.get(prefix + "Jahr", np.nan),
                "Kennzahl_Bezug": clean_string(row.get(prefix + "Bezug", "")),
                "Kennzahl_Datentyp": clean_string(row.get(prefix + "Datentyp", "")),
                "Kennzahl_Vertrauen": clean_string(row.get(prefix + "Vertrauen", "")),
                "Kennzahl_Vergleichbarkeit": clean_string(row.get(prefix + "Vergleichbarkeit_innerhalb_Gruppe", "")),
                "Kennzahl_Fuer_Score_Roh": use_raw,
                "Kennzahl_Direkt_fuer_Score": _score_use_is_direct(use_raw),
                "Kennzahl_Kommentar": clean_string(row.get(prefix + "Kommentar", "")),
                "KI_Relativer_Groessenscore_0_100": score,
                "KI_Hat_Groessenscore": pd.notna(score),
            })

    return pd.DataFrame(rows)


def build_score_coverage_table(size_info: pd.DataFrame):
    if size_info.empty:
        return pd.DataFrame([
            {"Kategorie": "KEINE_STANDORTGROESSENDATEI", "Anzahl_Standorte": 0, "Anteil": np.nan}
        ])

    total = len(size_info)
    scored = int(size_info["KI_Hat_Groessenscore"].sum())
    no_score = total - scored
    rows = [
        {"Kategorie": "MIT_SCORE", "Anzahl_Standorte": scored, "Anteil": safe_divide(scored, total)},
        {"Kategorie": "OHNE_SCORE", "Anzahl_Standorte": no_score, "Anteil": safe_divide(no_score, total)},
        {"Kategorie": "GESAMT", "Anzahl_Standorte": total, "Anteil": 1.0 if total else np.nan},
    ]
    return pd.DataFrame(rows)


def merge_size_info_into_sites(sites: pd.DataFrame, size_info: pd.DataFrame):
    sites = sites.copy()
    if sites.empty:
        return sites

    if size_info.empty:
        sites["KI_Relativer_Groessenscore_0_100"] = np.nan
        sites["KI_Groessenklasse_innerhalb_Gruppe"] = ""
        sites["KI_Hat_Groessenscore"] = False
        sites["KI_Anzahl_direkter_Scorekennzahlen_abgeleitet"] = 0
        return sites

    merged = sites.merge(size_info, on="Standortverbund_ID", how="left")
    score_col = "KI_Relativer_Groessenscore_0_100"
    merged[score_col] = pd.to_numeric(merged.get(score_col), errors="coerce")
    merged["KI_Hat_Groessenscore"] = merged[score_col].notna()
    merged["KI_Groessenklasse_innerhalb_Gruppe"] = (
        merged.get("KI_Groessenklasse_innerhalb_Gruppe", "")
        .fillna("")
        .map(clean_string)
    )
    if "KI_Anzahl_direkter_Scorekennzahlen_abgeleitet" not in merged.columns:
        merged["KI_Anzahl_direkter_Scorekennzahlen_abgeleitet"] = 0
    merged["KI_Anzahl_direkter_Scorekennzahlen_abgeleitet"] = (
        pd.to_numeric(merged["KI_Anzahl_direkter_Scorekennzahlen_abgeleitet"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
    return merged


# =============================================================================
# 5. BASISÜBERSICHTEN
# =============================================================================


def build_overview(group_id, sources, sites):
    total_heat = sources["Waermemenge_kWh_a"].sum()
    qx_note = "QX ist in source_blocks der finalen Generatorbasis nicht enthalten."

    rows = [
        ["Experiment_Gruppe", group_id],
        ["Anzahl_Standorte", int(sites["Standortverbund_ID"].nunique())],
        ["Anzahl_Quellenbloecke", int(len(sources))],
        ["Gesamtwaermemenge_Q1_Q7_kWh_a", float(total_heat)],
        ["Median_Quelle_kWh_a", float(sources["Waermemenge_kWh_a"].median())],
        ["P90_Quelle_kWh_a", float(sources["Waermemenge_kWh_a"].quantile(0.90))],
        ["Maximum_Quelle_kWh_a", float(sources["Waermemenge_kWh_a"].max())],
        ["Median_Standort_kWh_a", float(sites["Waermemenge_Standort_kWh_a"].median())],
        ["P90_Standort_kWh_a", float(sites["Waermemenge_Standort_kWh_a"].quantile(0.90))],
        ["Maximum_Standort_kWh_a", float(sites["Waermemenge_Standort_kWh_a"].max())],
        ["Median_Quellen_je_Standort", float(sites["Anzahl_Quellenbloecke"].median())],
        ["Maximum_Quellen_je_Standort", int(sites["Anzahl_Quellenbloecke"].max())],
        ["Temperatur_Abdeckung", float(sources["Temperatur_C"].notna().mean())],
        ["Saisonalitaet_Abdeckung", float(sources["Saisonfaktor_Sommer"].notna().mean())],
        ["Betriebsprofil_Abdeckung", float(sources["Betriebsprofil_Code"].ne("BP_UNBEKANNT").mean())],
        ["Vollaststunden_im_Bereich_Anteil", float(sources["Vollaststunden_im_physikalischen_Bereich"].mean())],
        ["Hinweis_QX", qx_note],
    ]
    return pd.DataFrame(rows, columns=["Kennzahl", "Wert"])



def build_q_summary(sources):
    rows = []
    total_n = len(sources)
    total_heat = sources["Waermemenge_kWh_a"].sum()

    for q, grp in sources.groupby("Quellklasse_Code", sort=True):
        temp = grp["Temperatur_C"].dropna()
        season = grp["Saisonfaktor_Sommer"].dropna()
        flh = grp.loc[grp["Vollaststunden_im_physikalischen_Bereich"], "Vollaststunden_h_a"]

        rows.append({
            "Quellklasse_Code": q,
            "Anzahl_Bloecke": int(len(grp)),
            "Anteil_Bloecke": safe_divide(len(grp), total_n),
            "Waermemenge_kWh_a": float(grp["Waermemenge_kWh_a"].sum()),
            "Anteil_Waermemenge": safe_divide(grp["Waermemenge_kWh_a"].sum(), total_heat),
            "Waermemenge_Median_kWh_a": float(grp["Waermemenge_kWh_a"].median()),
            "Waermemenge_P90_kWh_a": float(grp["Waermemenge_kWh_a"].quantile(0.90)),
            "Temperatur_N": int(len(temp)),
            "Temperatur_Median_C": float(temp.median()) if len(temp) else np.nan,
            "Temperatur_P10_C": float(temp.quantile(0.10)) if len(temp) else np.nan,
            "Temperatur_P90_C": float(temp.quantile(0.90)) if len(temp) else np.nan,
            "Sommerfaktor_N": int(len(season)),
            "Sommerfaktor_Median": float(season.median()) if len(season) else np.nan,
            "Sommerfaktor_P10": float(season.quantile(0.10)) if len(season) else np.nan,
            "Sommerfaktor_P90": float(season.quantile(0.90)) if len(season) else np.nan,
            "Vollaststunden_im_Bereich_N": int(len(flh)),
            "Vollaststunden_Median": float(flh.median()) if len(flh) else np.nan,
        })

    return pd.DataFrame(rows)



def build_operating_summary(sources):
    grouped = (
        sources.groupby("Betriebsprofil_Code", dropna=False)
        .agg(
            Anzahl_Bloecke=("Generator_Block_ID", "count"),
            Waermemenge_kWh_a=("Waermemenge_kWh_a", "sum"),
        )
        .reset_index()
    )
    grouped["Anteil_Bloecke"] = grouped["Anzahl_Bloecke"] / grouped["Anzahl_Bloecke"].sum()
    grouped["Anteil_Waermemenge"] = grouped["Waermemenge_kWh_a"] / grouped["Waermemenge_kWh_a"].sum()
    return grouped.sort_values("Waermemenge_kWh_a", ascending=False)



def build_portfolio_summary(sites):
    grouped = (
        sites.groupby("Quellenportfolio", dropna=False)
        .agg(
            Anzahl_Standorte=("Standortverbund_ID", "count"),
            Waermemenge_kWh_a=("Waermemenge_Standort_kWh_a", "sum"),
            Median_Standortwaerme_kWh_a=("Waermemenge_Standort_kWh_a", "median"),
        )
        .reset_index()
    )
    grouped["Anteil_Standorte"] = grouped["Anzahl_Standorte"] / grouped["Anzahl_Standorte"].sum()
    grouped["Anteil_Waermemenge"] = grouped["Waermemenge_kWh_a"] / grouped["Waermemenge_kWh_a"].sum()
    return grouped.sort_values("Anzahl_Standorte", ascending=False)



def build_family_summary(sources):
    temp = sources.copy()
    temp["Quellenfamilie_normalisiert"] = temp["Quellenfamilie_normalisiert"].replace("", "UNBEKANNT")
    grouped = (
        temp.groupby(["Quellenfamilie_normalisiert", "Quellklasse_Code"], dropna=False)
        .agg(
            Anzahl_Bloecke=("Generator_Block_ID", "count"),
            Waermemenge_kWh_a=("Waermemenge_kWh_a", "sum"),
            Temperatur_Median_C=("Temperatur_C", "median"),
            Sommerfaktor_Median=("Saisonfaktor_Sommer", "median"),
        )
        .reset_index()
    )
    return grouped.sort_values(["Anzahl_Bloecke", "Waermemenge_kWh_a"], ascending=[False, False])


# =============================================================================
# 6. ABHÄNGIGKEITEN
# =============================================================================


def build_source_numeric_associations(sources):
    columns = [
        "log10_Waermemenge",
        "Temperatur_C",
        "Betrieb_h_Tag",
        "Betrieb_Tage_Woche",
        "Saisonfaktor_Sommer",
        "Saison_Konzentration_0_1",
        "Saison_Aktive_Monate",
        "Anteil_Quelle_am_Standort",
        "Vollaststunden_h_a",
    ]
    rows = []
    for i, x in enumerate(columns):
        for y in columns[i + 1:]:
            rho, n = spearman_pair(sources, x, y)
            rows.append({
                "Variable_1": x,
                "Variable_2": y,
                "Spearman_rho": rho,
                "N": n,
                "Abs_rho": abs(rho) if pd.notna(rho) else np.nan,
            })
    return pd.DataFrame(rows).sort_values("Abs_rho", ascending=False, na_position="last")



def build_site_numeric_associations(sites):
    columns = [
        "log10_Waermemenge_Standort",
        "Anzahl_Quellenbloecke",
        "Anzahl_Q_Klassen",
        "Groesste_Quelle_Anteil",
        "Top3_Quellen_Anteil",
        "HHI_Quellenwaerme",
        "Entropie_Quellenwaerme_normiert",
        "Anzahl_Betriebsprofile",
        "Anteil_Waerme_BP_24x7",
        "Anteil_Waerme_7Tage",
        "Anteil_Waerme_ge20h_Tag",
        "Temperatur_gew_Mittel_C",
        "Temperatur_Spanne_K",
        "Anteil_Waerme_Temp_ge110C",
        "Anteil_Waerme_Temp_lt60C",
        "Sommerfaktor_gew_Mittel",
        "Sommerfaktor_gew_Std",
        "Saison_Konzentration_gew_Mittel",
        "Anteil_Waerme_stark_saisonal",
    ]
    rows = []
    for i, x in enumerate(columns):
        for y in columns[i + 1:]:
            rho, n = spearman_pair(sites, x, y)
            rows.append({
                "Variable_1": x,
                "Variable_2": y,
                "Spearman_rho": rho,
                "N": n,
                "Abs_rho": abs(rho) if pd.notna(rho) else np.nan,
            })
    return pd.DataFrame(rows).sort_values("Abs_rho", ascending=False, na_position="last")



def build_numeric_by_category_effects(sources):
    categorical = [
        "Quellklasse_Code",
        "Betriebsprofil_Code",
        "Temperaturklasse_Analyse",
        "Saisonklasse",
        "Groessenklasse_Q",
    ]
    numeric = [
        "log10_Waermemenge",
        "Temperatur_C",
        "Betrieb_h_Tag",
        "Betrieb_Tage_Woche",
        "Saisonfaktor_Sommer",
        "Saison_Konzentration_0_1",
        "Anteil_Quelle_am_Standort",
        "Vollaststunden_h_a",
    ]

    rows = []
    for cat in categorical:
        for num in numeric:
            eta2, n, n_groups = eta_squared(sources[cat], numeric_series(sources[num]))
            rows.append({
                "Kategorie": cat,
                "Numerische_Variable": num,
                "Eta_Quadrat": eta2,
                "N": n,
                "Anzahl_Kategorien": n_groups,
            })
    return pd.DataFrame(rows).sort_values("Eta_Quadrat", ascending=False, na_position="last")



def build_categorical_associations(sources):
    categorical = [
        "Quellklasse_Code",
        "Betriebsprofil_Code",
        "Temperaturklasse_Analyse",
        "Saisonklasse",
        "Groessenklasse_Q",
    ]
    rows = []
    for i, a in enumerate(categorical):
        for b in categorical[i + 1:]:
            v, n, r, k = cramers_v(sources[a], sources[b])
            rows.append({
                "Variable_1": a,
                "Variable_2": b,
                "Cramers_V": v,
                "N": n,
                "Kategorien_1": r,
                "Kategorien_2": k,
            })
    return pd.DataFrame(rows).sort_values("Cramers_V", ascending=False, na_position="last")



def build_q_cooccurrence(sites, sources):
    """Q×Q: off-diagonal = sites with both types; diagonal = sites with >=2 blocks of the same type."""
    qs = Q_ORDER
    matrix = pd.DataFrame(0, index=qs, columns=qs, dtype=int)

    site_q = (
        sources.groupby(["Standortverbund_ID", "Quellklasse_Code"])["Waermemenge_kWh_a"]
        .sum().unstack(fill_value=0)
        .reindex(columns=qs, fill_value=0.0)
    )

    # Mehrfache Quellenblöcke derselben Q-Klasse dürfen nicht mit
    # dem rein binären Auftreten der Klasse verwechselt werden.
    site_q_counts = (
        sources.groupby(["Standortverbund_ID", "Quellklasse_Code"])
        .size().unstack(fill_value=0)
        .reindex(columns=qs, fill_value=0)
    )
    presence = site_q_counts > 0
    for a in qs:
        for b in qs:
            if a == b:
                matrix.loc[a, b] = int((site_q_counts[a] >= 2).sum())
            else:
                matrix.loc[a, b] = int((presence[a] & presence[b]).sum())

    matrix.index.name = "Q_Klasse"
    return matrix.reset_index(), site_q.reset_index()


# =============================================================================
# 7. EXTREMFÄLLE / PLAUSIBILITÄT
# =============================================================================


def build_extreme_cases(sources, sites):
    records = []

    def add_source_cases(label, frame, value_col):
        for _, row in frame.head(TOP_N_EXTREMES).iterrows():
            records.append({
                "Ebene": "QUELLE",
                "Kategorie": label,
                "Standortverbund_ID": row["Standortverbund_ID"],
                "Generator_Block_ID": row["Generator_Block_ID"],
                "Quellklasse_Code": row["Quellklasse_Code"],
                "Wert": row[value_col],
                "Quellenname": row.get("Original_Quellennamen", ""),
                "Hinweis": row.get("Vollaststunden_Status", ""),
            })

    add_source_cases(
        "GROESSTE_WAERMEMENGE",
        sources.sort_values("Waermemenge_kWh_a", ascending=False),
        "Waermemenge_kWh_a",
    )
    add_source_cases(
        "HOECHSTE_TEMPERATUR",
        sources.dropna(subset=["Temperatur_C"]).sort_values("Temperatur_C", ascending=False),
        "Temperatur_C",
    )
    add_source_cases(
        "STAERKSTE_SOMMERLAST",
        sources.dropna(subset=["Saisonfaktor_Sommer"]).sort_values("Saisonfaktor_Sommer", ascending=False),
        "Saisonfaktor_Sommer",
    )
    add_source_cases(
        "STAERKSTE_WINTERLAST",
        sources.dropna(subset=["Saisonfaktor_Sommer"]).sort_values("Saisonfaktor_Sommer", ascending=True),
        "Saisonfaktor_Sommer",
    )

    flh_problem = sources[
        sources["Vollaststunden_Status"].isin(
            ["UEBER_8784", "EXTREM_NIEDRIG_UNTER_10", "NIEDRIG_UNTER_100"]
        )
    ].sort_values("Vollaststunden_h_a", ascending=False)
    add_source_cases("VOLLASTSTUNDEN_AUFFAELLIG", flh_problem, "Vollaststunden_h_a")

    for _, row in sites.sort_values("Waermemenge_Standort_kWh_a", ascending=False).head(TOP_N_EXTREMES).iterrows():
        records.append({
            "Ebene": "STANDORT",
            "Kategorie": "GROESSTE_STANDORTWAERME",
            "Standortverbund_ID": row["Standortverbund_ID"],
            "Generator_Block_ID": "",
            "Quellklasse_Code": row["Quellenportfolio"],
            "Wert": row["Waermemenge_Standort_kWh_a"],
            "Quellenname": "",
            "Hinweis": f"{row['Anzahl_Quellenbloecke']} Bloecke",
        })

    for _, row in sites.sort_values("Groesste_Quelle_Anteil", ascending=False).head(TOP_N_EXTREMES).iterrows():
        records.append({
            "Ebene": "STANDORT",
            "Kategorie": "STAERKSTE_QUELLENDOMINANZ",
            "Standortverbund_ID": row["Standortverbund_ID"],
            "Generator_Block_ID": "",
            "Quellklasse_Code": row["Quellenportfolio"],
            "Wert": row["Groesste_Quelle_Anteil"],
            "Quellenname": "",
            "Hinweis": f"HHI={row['HHI_Quellenwaerme']:.3f}",
        })

    return pd.DataFrame(records)


# =============================================================================
# 8. EXPLORATIVE PCA DER STANDORTE
# =============================================================================


def build_site_pca(sites):
    # Für die PCA wird bewusst eine reduzierte und weniger kollineare
    # Merkmalsauswahl verwendet. Stark redundante Konzentrationsmaße werden
    # hier nicht parallel in voller Breite aufgenommen.
    features = [
        "log10_Waermemenge_Standort",
        "Anzahl_Quellenbloecke",
        "Anzahl_Q_Klassen",
        "Groesste_Quelle_Anteil",
        "Anteil_Waerme_BP_24x7",
        "Temperatur_gew_Mittel_C",
        "Sommerfaktor_gew_Mittel",
        "Anteil_Q1", "Anteil_Q2", "Anteil_Q3", "Anteil_Q4", "Anteil_Q5", "Anteil_Q6", "Anteil_Q7",
    ]

    if len(sites) < 10:
        return pd.DataFrame(), pd.DataFrame()

    X = sites[features].apply(pd.to_numeric, errors="coerce").copy()
    usable = [
        c for c in features
        if X[c].notna().sum() >= max(5, int(len(sites) * 0.5))
           and X[c].nunique(dropna=True) > 1
    ]
    if len(usable) < 3:
        return pd.DataFrame(), pd.DataFrame()

    X = X[usable]
    for col in usable:
        X[col] = X[col].fillna(X[col].median())

    means = X.mean(axis=0)
    stds = X.std(axis=0, ddof=0).replace(0, 1)
    Z = (X - means) / stds

    U, S, Vt = np.linalg.svd(Z.to_numpy(dtype=float), full_matrices=False)
    scores = U[:, :2] * S[:2]
    eigenvalues = (S**2) / max(len(Z) - 1, 1)
    explained = eigenvalues / eigenvalues.sum()

    score_df = pd.DataFrame({
        "Standortverbund_ID": sites["Standortverbund_ID"].to_numpy(),
        "PC1": scores[:, 0],
        "PC2": scores[:, 1],
        "PC1_Varianzanteil": explained[0],
        "PC2_Varianzanteil": explained[1] if len(explained) > 1 else np.nan,
        "Waermemenge_Standort_kWh_a": sites["Waermemenge_Standort_kWh_a"].to_numpy(),
        "Quellenportfolio": sites["Quellenportfolio"].to_numpy(),
        "Anzahl_Quellenbloecke": sites["Anzahl_Quellenbloecke"].to_numpy(),
        "Anzahl_Q_Klassen": sites["Anzahl_Q_Klassen"].to_numpy(),
        "KI_Relativer_Groessenscore_0_100": sites.get("KI_Relativer_Groessenscore_0_100", pd.Series(np.nan, index=sites.index)).to_numpy(),
    })

    loading_df = pd.DataFrame({
        "Merkmal": usable,
        "PC1_Loading": Vt[0, :],
        "PC2_Loading": Vt[1, :] if Vt.shape[0] > 1 else np.nan,
    })
    return score_df, loading_df


# =============================================================================
# 9. AUTOMATISCHE MUSTERHINWEISE
# =============================================================================


def build_pattern_notes(group_id, sources, sites, src_assoc, site_assoc, eta_df, cramers_df, q_summary, portfolio_summary):
    notes = []

    def add(category, text, strength=""):
        notes.append({
            "Experiment_Gruppe": group_id,
            "Kategorie": category,
            "Staerke": strength,
            "Hinweis": text,
        })

    # größte Q-Klassen nach Anzahl / Wärme
    if not q_summary.empty:
        by_count = q_summary.sort_values("Anzahl_Bloecke", ascending=False).iloc[0]
        by_heat = q_summary.sort_values("Waermemenge_kWh_a", ascending=False).iloc[0]
        add(
            "Q_STRUKTUR",
            f"Häufigste Q-Klasse nach Anzahl: {by_count['Quellklasse_Code']} ({int(by_count['Anzahl_Bloecke'])} Blöcke; {by_count['Anteil_Bloecke']:.1%}).",
        )
        add(
            "Q_STRUKTUR",
            f"Größte Q-Klasse nach Wärmemenge: {by_heat['Quellklasse_Code']} ({by_heat['Anteil_Waermemenge']:.1%} der Q1-Q7-Wärme).",
        )

    # Standortdominanz
    add(
        "STANDORTSTRUKTUR",
        f"Medianer Anteil der größten Quelle am Standort: {sites['Groesste_Quelle_Anteil'].median():.1%}; P90: {sites['Groesste_Quelle_Anteil'].quantile(0.90):.1%}.",
    )
    add(
        "STANDORTSTRUKTUR",
        f"Median der Quellenblöcke je Standort: {sites['Anzahl_Quellenbloecke'].median():.1f}; Maximum: {int(sites['Anzahl_Quellenbloecke'].max())}.",
    )

    # Häufigstes Portfolio
    if not portfolio_summary.empty:
        top = portfolio_summary.iloc[0]
        add(
            "PORTFOLIO",
            f"Häufigstes Quellenportfolio: {top['Quellenportfolio']} ({int(top['Anzahl_Standorte'])} Standorte; {top['Anteil_Standorte']:.1%}).",
        )

    # starke Spearman-Zusammenhänge
    for level_name, assoc in [("QUELLE", src_assoc), ("STANDORT", site_assoc)]:
        strong = assoc[(assoc["N"] >= MIN_N_ASSOCIATION) & (assoc["Abs_rho"] >= SPEARMAN_NOTE_THRESHOLD)].head(12)
        for _, row in strong.iterrows():
            diagnostic_prefix = (
                "Nur diagnostisch wegen möglicher Leistungsplatzhalter: "
                if "Vollaststunden" in str(row["Variable_1"]) or "Vollaststunden" in str(row["Variable_2"])
                else ""
            )
            add(
                f"{level_name}_NUMERISCH",
                diagnostic_prefix
                + f"Deskriptiver Zusammenhang {row['Variable_1']} ↔ {row['Variable_2']}: Spearman ρ={row['Spearman_rho']:.3f} bei N={int(row['N'])}.",
                strength=f"|ρ|={row['Abs_rho']:.3f}",
                )

    # eta²
    strong_eta = eta_df[(eta_df["N"] >= MIN_N_ASSOCIATION) & (eta_df["Eta_Quadrat"] >= ETA2_NOTE_THRESHOLD)].head(12)
    for _, row in strong_eta.iterrows():
        add(
            "KATEGORIE_NUMERISCH",
            f"{row['Kategorie']} erklärt deskriptiv einen relevanten Anteil der Streuung von {row['Numerische_Variable']}: η²={row['Eta_Quadrat']:.3f} (N={int(row['N'])}).",
            strength=f"η²={row['Eta_Quadrat']:.3f}",
        )

    # Cramér's V
    strong_v = cramers_df[(cramers_df["N"] >= MIN_N_ASSOCIATION) & (cramers_df["Cramers_V"] >= CRAMERS_V_NOTE_THRESHOLD)].head(10)
    for _, row in strong_v.iterrows():
        add(
            "KATEGORIAL",
            f"Kategorialer Zusammenhang {row['Variable_1']} ↔ {row['Variable_2']}: Cramér's V={row['Cramers_V']:.3f} (N={int(row['N'])}).",
            strength=f"V={row['Cramers_V']:.3f}",
        )

    # FLH Warnung
    over = int((sources["Vollaststunden_Status"] == "UEBER_8784").sum())
    low = int(sources["Vollaststunden_Status"].isin(["EXTREM_NIEDRIG_UNTER_10", "NIEDRIG_UNTER_100"]).sum())
    add(
        "VOLLASTSTUNDEN",
        f"Vollaststunden sind nur diagnostisch: {over} Blöcke liegen über 8784 h/a; {low} Blöcke liegen unter 100 h/a.",
    )

    return pd.DataFrame(notes)


# =============================================================================
# 10. DIAGRAMME
# =============================================================================


def save_figure(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def scatter_by_q_with_regressions(
        sources,
        x_col,
        y_col,
        path,
        *,
        xlabel,
        ylabel,
        title,
        x_log=False,
        y_log=False,
        horizontal_reference=None,
):
    fig, ax = plt.subplots(figsize=(10, 6.5))

    qs = ordered_present_qs(sources["Quellklasse_Code"])

    for q in qs:
        grp = sources[sources["Quellklasse_Code"].eq(q)].copy()
        valid = grp[
            grp[x_col].notna()
            & grp[y_col].notna()
            ].copy()

        if x_log:
            valid = valid[valid[x_col] > 0]
        if y_log:
            valid = valid[valid[y_col] > 0]

        if valid.empty:
            continue

        color = Q_COLORS[q]

        ax.scatter(
            valid[x_col],
            valid[y_col],
            alpha=0.65,
            s=34,
            color=color,
            label=q_label(q),
            edgecolors="none",
        )

        if SHOW_Q_SPECIFIC_REGRESSIONS:
            add_regression_line(
                ax,
                valid[x_col],
                valid[y_col],
                x_log=x_log,
                y_log=y_log,
                label=f"Regression {q}",
                color=color,
                linestyle="-",
                linewidth=1.35,
                min_n=MIN_N_REGRESSION,
            )
            # Die Q-spezifischen Regressionslinien sollen sichtbar sein, aber
            # die Legende nicht mit zusätzlichen Einträgen überladen.
            lines = ax.get_lines()
            if lines and lines[-1].get_label().startswith("Regression Q"):
                lines[-1].set_label("_nolegend_")

    if SHOW_OVERALL_REGRESSION:
        add_regression_line(
            ax,
            sources[x_col],
            sources[y_col],
            x_log=x_log,
            y_log=y_log,
            label="Regression gesamt",
            color="black",
            linestyle="--",
            linewidth=2.0,
            min_n=MIN_N_REGRESSION,
        )

    if horizontal_reference is not None:
        ax.axhline(horizontal_reference, color="#555555", linewidth=1.0, linestyle=":")

    if x_log:
        ax.set_xscale("log")
    if y_log:
        ax.set_yscale("log")

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.18)
    ax.legend(fontsize=8, ncol=2)

    ax.text(
        0.01,
        0.01,
        "Farbige Linien: lineare Regression innerhalb der jeweiligen Q-Klasse",
        transform=ax.transAxes,
        fontsize=8,
        color="#555555",
        va="bottom",
    )

    save_figure(fig, path)


def scatter_with_regression(
        df,
        x_col,
        y_col,
        path,
        *,
        xlabel,
        ylabel,
        title,
        x_log=False,
        y_log=False,
        ylim=None,
        integer_x=False,
):
    valid = df[
        df[x_col].notna()
        & df[y_col].notna()
        ].copy()

    if x_log:
        valid = valid[valid[x_col] > 0]
    if y_log:
        valid = valid[valid[y_col] > 0]

    if valid.empty:
        make_no_data_chart(path, title)
        return

    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    ax.scatter(
        valid[x_col],
        valid[y_col],
        alpha=0.70,
        s=38,
        color="#356b8c",
        edgecolors="none",
    )

    add_regression_line(
        ax,
        valid[x_col],
        valid[y_col],
        x_log=x_log,
        y_log=y_log,
        label="Regression gesamt",
        color="black",
        linestyle="--",
        linewidth=2.0,
    )

    if x_log:
        ax.set_xscale("log")
    if y_log:
        ax.set_yscale("log")
    if ylim is not None:
        ax.set_ylim(*ylim)

    if integer_x:
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=12))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.18)
    ax.legend(fontsize=8)

    save_figure(fig, path)


def chart_heat_distribution(sources, path):
    values = sources.loc[
        sources["Waermemenge_kWh_a"] > 0,
        "Waermemenge_kWh_a",
    ]

    if values.empty:
        make_no_data_chart(path, "Größenverteilung der Quellen")
        return

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.hist(np.log10(values), bins=30, color="#5f8ca8", edgecolor="white")
    ax.set_xlabel("log10(Jahreswärmemenge [kWh/a])")
    ax.set_ylabel("Anzahl Quellenblöcke")
    ax.set_title("Größenverteilung der Quellen")
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def chart_heat_by_q(sources, path):
    qs = ordered_present_qs(sources["Quellklasse_Code"])
    data = [
        sources.loc[
            sources["Quellklasse_Code"].eq(q)
            & (sources["Waermemenge_kWh_a"] > 0),
            "Waermemenge_kWh_a",
        ].to_numpy()
        for q in qs
    ]

    if not qs:
        make_no_data_chart(path, "Quellengröße nach Q-Klasse")
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    box = ax.boxplot(
        data,
        tick_labels=[q_label(q) for q in qs],
        showfliers=False,
        patch_artist=True,
    )

    for patch, q in zip(box["boxes"], qs):
        patch.set_facecolor(Q_COLORS[q])
        patch.set_alpha(0.55)

    ax.set_yscale("log")
    ax.set_xlabel("Quellklasse")
    ax.set_ylabel("Jahreswärmemenge [kWh/a], logarithmisch")
    ax.set_title("Quellengröße nach Q-Klasse")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def chart_temp_by_q(sources, path):
    qs = ordered_present_qs(sources["Quellklasse_Code"])
    data = [
        sources.loc[
            sources["Quellklasse_Code"].eq(q)
            & sources["Temperatur_C"].notna(),
            "Temperatur_C",
        ].to_numpy()
        for q in qs
    ]

    if not qs:
        make_no_data_chart(path, "Temperaturverteilung nach Q-Klasse")
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    box = ax.boxplot(
        data,
        tick_labels=[q_label(q) for q in qs],
        showfliers=True,
        patch_artist=True,
    )

    for patch, q in zip(box["boxes"], qs):
        patch.set_facecolor(Q_COLORS[q])
        patch.set_alpha(0.55)

    ax.set_xlabel("Quellklasse")
    ax.set_ylabel("Temperatur [°C]")
    ax.set_title("Temperaturverteilung nach Q-Klasse")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def chart_heat_vs_temp(sources, path):
    scatter_by_q_with_regressions(
        sources,
        "Waermemenge_kWh_a",
        "Temperatur_C",
        path,
        xlabel="Jahreswärmemenge [kWh/a]",
        ylabel="Temperatur [°C]",
        title="Quellengröße und Temperatur",
        x_log=True,
    )


def chart_heat_vs_season(sources, path):
    scatter_by_q_with_regressions(
        sources,
        "Waermemenge_kWh_a",
        "Saisonfaktor_Sommer",
        path,
        xlabel="Jahreswärmemenge [kWh/a]",
        ylabel="Sommerfaktor",
        title="Quellengröße und Saisonalität",
        x_log=True,
        horizontal_reference=1.0,
    )


def chart_operating_q_heatmaps(sources, count_path, heat_path):
    temp = sources.copy()

    q_order = ordered_present_qs(temp["Quellklasse_Code"])
    bp_order = ordered_present_bp(temp["Betriebsprofil_Analyse"])

    count = pd.crosstab(
        temp["Quellklasse_Code"],
        temp["Betriebsprofil_Analyse"],
    ).reindex(
        index=q_order,
        columns=bp_order,
        fill_value=0,
    )

    heat = pd.pivot_table(
        temp,
        index="Quellklasse_Code",
        columns="Betriebsprofil_Analyse",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    ).reindex(
        index=q_order,
        columns=bp_order,
        fill_value=0,
    )

    y_labels = [q_label(q) for q in q_order]
    x_labels = [BP_DISPLAY_LABELS.get(bp, bp) for bp in bp_order]

    heatmap_with_grey_green(
        count,
        "Q-Klasse × Betriebsprofil – Anzahl Quellen",
        count_path,
        xlabel="Betriebsprofil",
        ylabel="Quellklasse",
        value_kind="count",
        x_labels=x_labels,
        y_labels=y_labels,
    )

    heatmap_with_grey_green(
        heat,
        "Q-Klasse × Betriebsprofil – Wärmemenge",
        heat_path,
        xlabel="Betriebsprofil",
        ylabel="Quellklasse",
        value_kind="heat",
        x_labels=x_labels,
        y_labels=y_labels,
    )


def chart_site_heat_vs_count(sites, path):
    scatter_with_regression(
        sites,
        "Waermemenge_Standort_kWh_a",
        "Anzahl_Quellenbloecke",
        path,
        xlabel="Standortwärmemenge [kWh/a]",
        ylabel="Anzahl Quellenblöcke",
        title="Standortgröße und Quellenanzahl",
        x_log=True,
    )


def chart_site_heat_vs_dominance(sites, path):
    subset = sites.loc[sites["Anzahl_Quellenbloecke"] >= 2].copy()
    if subset.empty:
        make_no_data_chart(path, "Standortgröße und Dominanz (ab 2 Quellen)")
        return
    scatter_with_regression(
        subset,
        "Waermemenge_Standort_kWh_a",
        "Groesste_Quelle_Anteil",
        path,
        xlabel="Standortwärmemenge [kWh/a]",
        ylabel="Anteil der größten Quelle",
        title=f"Standortgröße und Dominanz der größten Quelle (≥2 Quellen; n={len(subset)})",
        x_log=True,
        ylim=(-0.02, 1.02),
    )




def chart_site_q_stack(sites, path):
    subset = (
        sites.sort_values("Waermemenge_Standort_kWh_a", ascending=False)
        .head(TOP_N_SITES_STACKED)
        .copy()
        .sort_values("Waermemenge_Standort_kWh_a", ascending=True)
    )

    if subset.empty:
        make_no_data_chart(path, "Q-Zusammensetzung der größten Standorte")
        return

    fig, ax = plt.subplots(figsize=(14, max(6, len(subset) * 0.30)))
    left = np.zeros(len(subset))
    y = np.arange(len(subset))

    for q in Q_ORDER:
        column = f"Anteil_{q}"
        if column not in subset.columns:
            continue
        values = subset[column].fillna(0).to_numpy(dtype=float)
        ax.barh(
            y,
            values,
            left=left,
            label=q_label(q),
            color=Q_COLORS[q],
        )
        left += values

    ax.set_yticks(y)
    ax.set_yticklabels(subset["Standortverbund_ID"])
    ax.set_xlim(0, 1)
    ax.set_xlabel("Anteil an Q1-Q7-Jahreswärmemenge")
    ax.set_title(f"Q-Zusammensetzung der {len(subset)} größten Standorte")
    ax.legend(ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=8)
    save_figure(fig, path)


def _portfolio_display(portfolio):
    parts = [p for p in clean_string(portfolio).split("+") if p]
    return " + ".join(
        Q_SHORT_LABELS.get(p, p).replace(" – ", " ")
        for p in parts
    )


def chart_portfolios(portfolio_summary, path):
    subset = (
        portfolio_summary.head(TOP_N_PORTFOLIOS)
        .sort_values("Anzahl_Standorte", ascending=True)
        .copy()
    )

    if subset.empty:
        make_no_data_chart(path, "Häufigste Quellenportfolios")
        return

    subset["Portfolio_Anzeige"] = subset["Quellenportfolio"].map(_portfolio_display)

    fig, ax = plt.subplots(figsize=(12, max(6, len(subset) * 0.40)))
    ax.barh(
        subset["Portfolio_Anzeige"],
        subset["Anzahl_Standorte"],
        color="#52796f",
    )
    ax.set_xlabel("Anzahl Standorte")
    ax.set_title("Häufigste Quellenportfolios")
    ax.grid(axis="x", alpha=0.18)
    save_figure(fig, path)


def chart_q_cooccurrence(cooccurrence, path):
    if cooccurrence.empty:
        make_no_data_chart(path, "Gemeinsames Auftreten von Q-Klassen")
        return

    table = cooccurrence.set_index("Q_Klasse")
    present_q = [q for q in Q_ORDER if q in table.index and q in table.columns]
    table = table.reindex(index=present_q, columns=present_q)

    heatmap_with_grey_green(
        table,
        "Q-Kookkurrenz nach Standort (Diagonale: mind. 2 Quellen derselben Q-Klasse)",
        path,
        xlabel="Quellklasse",
        ylabel="Quellklasse",
        value_kind="count",
        mask_diagonal=False,
        triangle="lower_including_diagonal",
        x_labels=[q_label(q) for q in present_q],
        y_labels=[q_label(q) for q in present_q],
    )


def chart_families(family_summary, path):
    fam = (
        family_summary.groupby("Quellenfamilie_normalisiert")
        .agg(
            Anzahl_Bloecke=("Anzahl_Bloecke", "sum"),
            Waermemenge_kWh_a=("Waermemenge_kWh_a", "sum"),
        )
        .reset_index()
    )

    fam = fam[fam["Quellenfamilie_normalisiert"].map(clean_string).ne("")]

    fam = (
        fam.sort_values(
            ["Anzahl_Bloecke", "Waermemenge_kWh_a"],
            ascending=[False, False],
        )
        .head(TOP_N_FAMILIES)
        .sort_values("Anzahl_Bloecke", ascending=True)
    )

    if fam.empty:
        make_no_data_chart(path, "Häufigste Quellen-/Maschinenfamilien")
        return

    fig, ax = plt.subplots(figsize=(11, max(6, len(fam) * 0.34)))
    ax.barh(
        fam["Quellenfamilie_normalisiert"],
        fam["Anzahl_Bloecke"],
        color="#688e68",
    )
    ax.set_xlabel("Anzahl Quellenblöcke")
    ax.set_title("Häufigste Quellen-/Maschinenfamilien")
    ax.grid(axis="x", alpha=0.18)
    save_figure(fig, path)


def chart_pca(pca_scores, path):
    if pca_scores.empty:
        make_no_data_chart(path, "Explorative Standort-PCA")
        return

    fig, ax = plt.subplots(figsize=(9.2, 7.0))
    sizes = np.sqrt(pca_scores["Waermemenge_Standort_kWh_a"].clip(lower=1))
    sizes = 30 + 180 * (sizes - sizes.min()) / max(sizes.max() - sizes.min(), 1e-12)

    qdiv = pd.to_numeric(pca_scores["Anzahl_Q_Klassen"], errors="coerce").fillna(0).astype(int)
    unique_q = sorted([v for v in qdiv.unique().tolist() if v > 0])
    color_map = plt.cm.get_cmap("viridis", max(len(unique_q), 1))

    for idx, q_count in enumerate(unique_q):
        mask = qdiv.eq(q_count)
        ax.scatter(
            pca_scores.loc[mask, "PC1"],
            pca_scores.loc[mask, "PC2"],
            s=sizes[mask.to_numpy()],
            alpha=0.68,
            color=color_map(idx),
            edgecolors="white",
            linewidths=0.4,
            label=f"Q-Vielfalt = {q_count}",
        )

    if not unique_q:
        ax.scatter(
            pca_scores["PC1"],
            pca_scores["PC2"],
            s=sizes, alpha=0.68, color="#3d6f86", edgecolors="white", linewidths=0.4
        )

    pc1 = float(pca_scores["PC1_Varianzanteil"].iloc[0])
    pc2 = float(pca_scores["PC2_Varianzanteil"].iloc[0])

    ax.axhline(0, color="#999999", linestyle="--", linewidth=1.0, alpha=0.8)
    ax.axvline(0, color="#999999", linestyle="--", linewidth=1.0, alpha=0.8)
    ax.set_xlabel(f"PC1 ({pc1:.1%})")
    ax.set_ylabel(f"PC2 ({pc2:.1%})")
    ax.set_title("Explorative Standort-PCA\nFarbe = Q-Vielfalt, Punktgröße = Standortwärme")
    ax.grid(alpha=0.18)

    # Größen-Legende
    heat_vals = pd.to_numeric(pca_scores["Waermemenge_Standort_kWh_a"], errors="coerce")
    heat_vals = heat_vals[np.isfinite(heat_vals) & (heat_vals > 0)]
    if len(heat_vals):
        q25, q50, q75 = np.quantile(heat_vals, [0.25, 0.5, 0.75])
        def _size_from_heat(v):
            s = np.sqrt(max(v, 1))
            return 30 + 180 * (s - np.sqrt(max(heat_vals.min(), 1))) / max(np.sqrt(heat_vals.max()) - np.sqrt(max(heat_vals.min(), 1)), 1e-12)
        handles = [
            ax.scatter([], [], s=_size_from_heat(v), facecolors='none', edgecolors='#555555')
            for v in [q25, q50, q75]
        ]
        labels = [f"{v/1e6:.1f} Mio. kWh/a" for v in [q25, q50, q75]]
        leg2 = ax.legend(handles, labels, title="Standortwärme", loc="lower right", fontsize=8, frameon=True)
        ax.add_artist(leg2)

    if unique_q:
        ax.legend(title="Q-Vielfalt", loc="upper right", fontsize=8, frameon=True)

    save_figure(fig, path)


def chart_pca_loadings(pca_loadings, component, path):
    if pca_loadings.empty or component not in pca_loadings.columns:
        make_no_data_chart(path, f"PCA-Loadings {component}")
        return

    temp = pca_loadings[["Merkmal", component]].copy()
    temp = temp.dropna()
    if temp.empty:
        make_no_data_chart(path, f"PCA-Loadings {component}")
        return

    temp["abs_loading"] = temp[component].abs()
    temp = temp.sort_values("abs_loading", ascending=False).head(10).sort_values(component)

    fig, ax = plt.subplots(figsize=(9.5, max(5.5, len(temp) * 0.45)))
    colors = ["#3d8aa3" if v >= 0 else "#d69552" for v in temp[component]]
    ax.barh(temp["Merkmal"], temp[component], color=colors)
    ax.axvline(0, color="#777777", linewidth=1)
    ax.set_xlabel("Ladung")
    ax.set_title(f"{component} – Komponentenladungen")
    ax.grid(axis="x", alpha=0.18)
    save_figure(fig, path)


def chart_q_count(sources, path):
    summary = (
        sources.groupby("Quellklasse_Code")
        .size()
        .reindex(Q_ORDER, fill_value=0)
    )
    summary = summary[summary > 0]

    if summary.empty:
        make_no_data_chart(path, "Häufigkeit der Q-Klassen")
        return

    qs = summary.index.tolist()
    fig, ax = plt.subplots(figsize=(12, 5.8))
    bars = ax.bar(
        [q_label(q) for q in qs],
        summary.to_numpy(),
        color=[Q_COLORS[q] for q in qs],
    )
    ax.set_ylabel("Anzahl Quellenblöcke")
    ax.set_title("Häufigkeit der Q-Klassen – Anzahl")
    ax.tick_params(axis="x", rotation=25)
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def chart_q_heat_share(sources, path):
    summary = (
        sources.groupby("Quellklasse_Code")["Waermemenge_kWh_a"]
        .sum()
        .reindex(Q_ORDER, fill_value=0)
    )

    total = summary.sum()
    if total <= 0:
        make_no_data_chart(path, "Energetische Bedeutung der Q-Klassen")
        return

    shares = 100.0 * summary / total
    shares = shares[summary > 0]
    qs = shares.index.tolist()

    fig, ax = plt.subplots(figsize=(12, 5.8))
    bars = ax.bar(
        [q_label(q) for q in qs],
        shares.to_numpy(),
        color=[Q_COLORS[q] for q in qs],
    )
    ax.set_ylabel("Anteil an der Jahreswärmemenge [%]")
    ax.set_title("Energetische Bedeutung der Q-Klassen")
    ax.tick_params(axis="x", rotation=25)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in shares], padding=3, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def chart_q_temp_heatmaps(sources, count_path, heat_path):
    q_order = ordered_present_qs(sources["Quellklasse_Code"])
    temp_order = TEMP_LABELS + ["UNBEKANNT"]

    count = pd.crosstab(
        sources["Quellklasse_Code"],
        sources["Temperaturklasse_Analyse"],
    ).reindex(
        index=q_order,
        columns=[c for c in temp_order if c in set(sources["Temperaturklasse_Analyse"])],
        fill_value=0,
    )

    heat = pd.pivot_table(
        sources,
        index="Quellklasse_Code",
        columns="Temperaturklasse_Analyse",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    ).reindex(
        index=q_order,
        columns=count.columns,
        fill_value=0,
    )

    heatmap_with_grey_green(
        count,
        "Q-Klasse × Temperaturklasse – Anzahl Quellen",
        count_path,
        xlabel="Temperaturklasse [°C]",
        ylabel="Quellklasse",
        value_kind="count",
        y_labels=[q_label(q) for q in q_order],
    )

    heatmap_with_grey_green(
        heat,
        "Q-Klasse × Temperaturklasse – Wärmemenge",
        heat_path,
        xlabel="Temperaturklasse [°C]",
        ylabel="Quellklasse",
        value_kind="heat",
        y_labels=[q_label(q) for q in q_order],
    )


def chart_q_season_heatmaps(sources, count_path, heat_path):
    q_order = ordered_present_qs(sources["Quellklasse_Code"])
    season_order = [
        "STARK_WINTER",
        "LEICHT_WINTER",
        "NAHEZU_KONSTANT",
        "LEICHT_SOMMER",
        "STARK_SOMMER",
        "UNBEKANNT",
    ]
    season_labels = {
        "STARK_WINTER": "stark Winter",
        "LEICHT_WINTER": "leicht Winter",
        "NAHEZU_KONSTANT": "nahezu konstant",
        "LEICHT_SOMMER": "leicht Sommer",
        "STARK_SOMMER": "stark Sommer",
        "UNBEKANNT": "unbekannt",
    }

    present_season = [
        s for s in season_order
        if s in set(sources["Saisonklasse"])
    ]

    count = pd.crosstab(
        sources["Quellklasse_Code"],
        sources["Saisonklasse"],
    ).reindex(
        index=q_order,
        columns=present_season,
        fill_value=0,
    )

    heat = pd.pivot_table(
        sources,
        index="Quellklasse_Code",
        columns="Saisonklasse",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    ).reindex(
        index=q_order,
        columns=present_season,
        fill_value=0,
    )

    x_labels = [season_labels[s] for s in present_season]

    heatmap_with_grey_green(
        count,
        "Q-Klasse × Saisonalität – Anzahl Quellen",
        count_path,
        xlabel="Saisonklasse",
        ylabel="Quellklasse",
        value_kind="count",
        x_labels=x_labels,
        y_labels=[q_label(q) for q in q_order],
    )

    heatmap_with_grey_green(
        heat,
        "Q-Klasse × Saisonalität – Wärmemenge",
        heat_path,
        xlabel="Saisonklasse",
        ylabel="Quellklasse",
        value_kind="heat",
        x_labels=x_labels,
        y_labels=[q_label(q) for q in q_order],
    )


def chart_operating_distribution(sources, count_path, heat_path):
    order = ordered_present_bp(sources["Betriebsprofil_Analyse"])
    display = [BP_DISPLAY_LABELS.get(bp, bp) for bp in order]

    count = (
        sources["Betriebsprofil_Analyse"]
        .value_counts()
        .reindex(order, fill_value=0)
    )

    heat = (
        sources.groupby("Betriebsprofil_Analyse")["Waermemenge_kWh_a"]
        .sum()
        .reindex(order, fill_value=0)
    )
    heat_share = 100.0 * heat / heat.sum() if heat.sum() > 0 else heat * np.nan

    fig, ax = plt.subplots(figsize=(12, 5.8))
    bars = ax.bar(display, count.to_numpy(), color="#5d8f68")
    ax.set_ylabel("Anzahl Quellenblöcke")
    ax.set_title("Betriebsprofile – Anzahl")
    ax.tick_params(axis="x", rotation=35)
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, count_path)

    fig, ax = plt.subplots(figsize=(12, 5.8))
    bars = ax.bar(display, heat_share.to_numpy(), color="#315f3a")
    ax.set_ylabel("Anteil an der Jahreswärmemenge [%]")
    ax.set_title("Betriebsprofile – energetische Bedeutung")
    ax.tick_params(axis="x", rotation=35)
    ax.bar_label(
        bars,
        labels=[f"{v:.1f}%" if np.isfinite(v) else "" for v in heat_share],
        padding=3,
        fontsize=8,
    )
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, heat_path)




def chart_site_heat_vs_temp_span(sites, path):
    scatter_with_regression(
        sites,
        "Waermemenge_Standort_kWh_a",
        "Temperatur_Spanne_K",
        path,
        xlabel="Standortwärmemenge [kWh/a]",
        ylabel="Temperaturspanne am Standort [K]",
        title="Standortgröße und Temperaturheterogenität",
        x_log=True,
    )


def chart_site_heat_vs_24x7_share(sites, path):
    scatter_with_regression(
        sites,
        "Waermemenge_Standort_kWh_a",
        "Anteil_Waerme_BP_24x7",
        path,
        xlabel="Standortwärmemenge [kWh/a]",
        ylabel="Wärmeanteil aus 24×7-Quellen",
        title="Standortgröße und Anteil kontinuierlicher 24×7-Quellen",
        x_log=True,
        ylim=(-0.02, 1.02),
    )


def chart_site_heat_vs_seasonal_share(sites, path):
    scatter_with_regression(
        sites,
        "Waermemenge_Standort_kWh_a",
        "Anteil_Waerme_stark_saisonal",
        path,
        xlabel="Standortwärmemenge [kWh/a]",
        ylabel="Wärmeanteil stark saisonaler Quellen",
        title="Standortgröße und starke Saisonalität",
        x_log=True,
        ylim=(-0.02, 1.02),
    )


def chart_source_count_vs_dominance(sites, path):
    scatter_with_regression(
        sites,
        "Anzahl_Quellenbloecke",
        "Groesste_Quelle_Anteil",
        path,
        xlabel="Anzahl Quellenblöcke am Standort",
        ylabel="Anteil der größten Quelle",
        title="Quellenanzahl und Dominanz der größten Quelle",
        ylim=(-0.02, 1.02),
        integer_x=True,
    )

def chart_source_count_vs_qdiversity(sites, path):
    scatter_with_regression(
        sites,
        "Anzahl_Quellenbloecke",
        "Anzahl_Q_Klassen",
        path,
        xlabel="Anzahl Quellenblöcke am Standort",
        ylabel="Anzahl unterschiedlicher Q-Klassen",
        title="Quellenanzahl und Q-Vielfalt",
    )


def chart_temp_vs_season(sources, path):
    scatter_by_q_with_regressions(
        sources,
        "Temperatur_C",
        "Saisonfaktor_Sommer",
        path,
        xlabel="Quelltemperatur [°C]",
        ylabel="Sommerfaktor",
        title="Temperatur und Saisonalität der Quellen",
        horizontal_reference=1.0,
    )




def _top_source_families(sources, n=18):
    temp = sources.copy()
    temp["Quellenfamilie_normalisiert"] = temp["Quellenfamilie_normalisiert"].map(clean_string)
    temp = temp[temp["Quellenfamilie_normalisiert"].ne("")]
    if temp.empty:
        return []
    ranking = (
        temp.groupby("Quellenfamilie_normalisiert")
        .agg(
            Anzahl=("Generator_Block_ID", "size"),
            Waerme=("Waermemenge_kWh_a", "sum"),
        )
        .sort_values(["Anzahl", "Waerme"], ascending=[False, False])
    )
    return ranking.head(n).index.tolist()


def chart_source_family_x_q_count(sources, path):
    families = _top_source_families(sources)
    if not families:
        make_no_data_chart(path, "Quellenfamilien und Q-Klassen – Anzahl")
        return
    temp = sources[sources["Quellenfamilie_normalisiert"].isin(families)].copy()
    qs = ordered_present_qs(temp["Quellklasse_Code"])
    table = pd.crosstab(
        temp["Quellenfamilie_normalisiert"],
        temp["Quellklasse_Code"],
    ).reindex(index=families, columns=qs, fill_value=0)
    heatmap_with_grey_green(
        table,
        "Häufige Quellenfamilien und zugehörige Q-Klassen – Anzahl",
        path,
        xlabel="Quellklasse",
        ylabel="Quellen-/Maschinenfamilie",
        value_kind="count",
        x_labels=[q_label(q) for q in qs],
    )


def chart_source_family_x_q_heat(sources, path):
    families = _top_source_families(sources)
    if not families:
        make_no_data_chart(path, "Quellenfamilien und Q-Klassen – Wärmemenge")
        return
    temp = sources[sources["Quellenfamilie_normalisiert"].isin(families)].copy()
    qs = ordered_present_qs(temp["Quellklasse_Code"])
    table = pd.pivot_table(
        temp,
        index="Quellenfamilie_normalisiert",
        columns="Quellklasse_Code",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    ).reindex(index=families, columns=qs, fill_value=0)
    heatmap_with_grey_green(
        table,
        "Häufige Quellenfamilien und zugehörige Q-Klassen – Wärmemenge",
        path,
        xlabel="Quellklasse",
        ylabel="Quellen-/Maschinenfamilie",
        value_kind="heat",
        x_labels=[q_label(q) for q in qs],
    )


def add_dominant_q_to_sites(sites, sources):
    if sites.empty:
        return sites.copy()
    q_heat = pd.pivot_table(
        sources,
        index="Standortverbund_ID",
        columns="Quellklasse_Code",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=Q_ORDER, fill_value=0)
    dominant = q_heat.idxmax(axis=1).rename("Dominante_Q_Klasse")
    out = sites.merge(dominant, left_on="Standortverbund_ID", right_index=True, how="left")
    return out


def chart_dominant_q_sites(sites, path):
    temp = sites[sites["Anzahl_Quellenbloecke"] >= 2].copy()
    if temp.empty:
        make_no_data_chart(path, "Q-Klasse der größten Quelle – nur Standorte mit mindestens 2 Quellen")
        return

    counts = (
        temp["Dominante_Q_Klasse"]
        .value_counts()
        .reindex(Q_ORDER, fill_value=0)
    )
    counts = counts[counts > 0]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(
        [q_label(q) for q in counts.index],
        counts.values,
        color=[Q_COLORS[q] for q in counts.index],
    )
    ax.set_ylabel("Anzahl Standorte")
    ax.set_xlabel("Q-Klasse der größten Quelle")
    ax.set_title("Q-Klasse der größten Quelle je Standort\n(nur Standorte mit mindestens 2 Quellen)")
    ax.grid(axis="y", alpha=0.18)
    ax.tick_params(axis="x", rotation=25)
    save_figure(fig, path)


def chart_source_share_by_q(sources, path):
    # Einzelquellenanteile sind nur an Standorten mit mindestens zwei Quellen
    # inhaltlich interpretierbar. Standortanteile wurden nach Vorbehandlung
    # bereits neu berechnet; keine weitere Aggregation nach Q-Klasse!
    n_blocks_per_site = sources.groupby("Standortverbund_ID")["Generator_Block_ID"].transform("size")
    temp = sources.loc[
        n_blocks_per_site.ge(2)
        & sources["Anteil_Quelle_am_Standort"].notna()
        ].copy()
    qs = ordered_present_qs(temp["Quellklasse_Code"])
    if not qs:
        make_no_data_chart(path, "Relative Bedeutung einzelner Quellen nach Q-Klasse")
        return

    fig, ax = plt.subplots(figsize=(12, 6.3))
    small_n = []
    for pos, q in enumerate(qs, start=1):
        values = temp.loc[temp["Quellklasse_Code"].eq(q), "Anteil_Quelle_am_Standort"].to_numpy(dtype=float)
        if len(values) >= 3:
            bp = ax.boxplot([values], positions=[pos], widths=0.55,
                            showfliers=True, patch_artist=True)
            bp["boxes"][0].set_facecolor(Q_COLORS[q])
            bp["boxes"][0].set_alpha(0.55)
        else:
            # Für 1 oder 2 Werte kein scheinbarer Boxplot: Einzelpunkte.
            small_n.append(q)
            offsets = np.array([0.0]) if len(values) == 1 else np.linspace(-0.07, 0.07, len(values))
            ax.scatter(pos + offsets, values, color=Q_COLORS[q],
                       edgecolors="black", linewidths=0.7, s=70, zorder=5)

    label_list = []
    for q in qs:
        subset = temp.loc[temp["Quellklasse_Code"].eq(q)]
        label_list.append(f"{q_label(q)}\n(n={len(subset)})")
    ax.set_xticks(np.arange(1, len(qs) + 1))
    ax.set_xticklabels(label_list, rotation=25, ha="right")
    ax.set_ylim(-0.02, 1.02)
    ax.set_ylabel("Anteil des einzelnen Quellenblocks an der Standortwärme")
    ax.set_xlabel("Quellklasse (n = Quellenblöcke; nur Standorte mit ≥2 Quellen)")
    ax.set_title("Relative Bedeutung einzelner Quellen innerhalb des Standorts")
    ax.grid(axis="y", alpha=0.18)
    if small_n:
        ax.text(0.01, 0.99, "Bei n < 3: Einzelpunkte statt Boxplot",
                va="top", fontsize=9, color="#555555", transform=ax.transAxes)
    save_figure(fig, path)


def _site_size_classes(sites):
    out = sites[["Standortverbund_ID", "Waermemenge_Standort_kWh_a"]].copy()
    if out.empty:
        out["Standortgroessenklasse"] = []
        return out
    values = out["Waermemenge_Standort_kWh_a"]
    try:
        out["Standortgroessenklasse"] = pd.qcut(
            values.rank(method="first"),
            q=4,
            labels=[
                "Quartil 1 – klein",
                "Quartil 2",
                "Quartil 3",
                "Quartil 4 – groß",
            ],
        ).astype(str)
    except Exception:
        out["Standortgroessenklasse"] = "Alle"
    return out


def chart_site_size_class_q_mix(sites, sources, path):
    classes = _site_size_classes(sites)
    temp = sources.merge(classes[["Standortverbund_ID", "Standortgroessenklasse"]], on="Standortverbund_ID", how="inner")
    if temp.empty:
        make_no_data_chart(path, "Q-Mix nach Abwärme-Größenquartil")
        return
    pivot = pd.pivot_table(
        temp,
        index="Standortgroessenklasse",
        columns="Quellklasse_Code",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=Q_ORDER, fill_value=0)
    preferred = ["Quartil 1 – klein", "Quartil 2", "Quartil 3", "Quartil 4 – groß"]
    pivot = pivot.reindex([x for x in preferred if x in pivot.index])
    shares = pivot.div(pivot.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    fig, ax = plt.subplots(figsize=(12, 6.2))
    bottom = np.zeros(len(shares))
    x = np.arange(len(shares))
    for q in Q_ORDER:
        vals = shares[q].to_numpy(dtype=float)
        if np.all(vals == 0):
            continue
        ax.bar(x, vals, bottom=bottom, label=q_label(q), color=Q_COLORS[q])
        bottom += vals
    ax.set_xticks(x)
    ax.set_xticklabels(shares.index)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Anteil an der Jahreswärmemenge")
    ax.set_xlabel("Abwärme-Größenquartil innerhalb der Gruppe (aus Standortwärmemenge, nicht aus KI-Größenscore)")
    ax.set_title("Q-Mix nach Abwärme-Größenquartil")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    ax.text(0.99, -0.20, "Quartile basieren auf der gesamten Standortwärmemenge der PFA-Daten.", transform=ax.transAxes, ha="right", va="top", fontsize=8, color="#555555")
    save_figure(fig, path)


def chart_site_size_class_q_mix_lines(sites, sources, path):
    classes = _site_size_classes(sites)
    temp = sources.merge(classes[["Standortverbund_ID", "Standortgroessenklasse"]], on="Standortverbund_ID", how="inner")
    if temp.empty:
        make_no_data_chart(path, "Q-Anteile nach Abwärme-Größenquartil")
        return
    pivot = pd.pivot_table(
        temp,
        index="Standortgroessenklasse",
        columns="Quellklasse_Code",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=Q_ORDER, fill_value=0)
    order = ["Quartil 1 – klein", "Quartil 2", "Quartil 3", "Quartil 4 – groß"]
    pivot = pivot.reindex([x for x in order if x in pivot.index])
    shares = pivot.div(pivot.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

    fig, ax = plt.subplots(figsize=(12, 6.2))
    x = np.arange(len(shares))
    for q in Q_ORDER:
        vals = shares[q].to_numpy(dtype=float)
        if np.all(vals == 0):
            continue
        ax.plot(x, vals, marker='o', linewidth=2.0, color=Q_COLORS[q], label=q_label(q))
    ax.set_xticks(x)
    ax.set_xticklabels(shares.index)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Anteil an der Jahreswärmemenge")
    ax.set_xlabel("Abwärme-Größenquartil innerhalb der Gruppe (aus Standortwärmemenge, nicht aus KI-Größenscore)")
    ax.set_title("Q-Anteile nach Abwärme-Größenquartil – Linienansicht")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    ax.text(0.99, -0.20, "Diese Darstellung ergänzt das Balkendiagramm und zeigt Trendverläufe der Q-Anteile.", transform=ax.transAxes, ha="right", va="top", fontsize=8, color="#555555")
    save_figure(fig, path)


def _source_count_class(n):
    if n <= 1:
        return "1 Quelle"
    if n == 2:
        return "2 Quellen"
    if n <= 4:
        return "3–4 Quellen"
    if n <= 7:
        return "5–7 Quellen"
    return "8+ Quellen"


def chart_source_count_class_x_q_occurrence(sites, sources, path):
    classes = sites[["Standortverbund_ID", "Anzahl_Quellenbloecke"]].copy()
    classes["Quellenzahlklasse"] = classes["Anzahl_Quellenbloecke"].map(_source_count_class)
    site_q = (
        sources[["Standortverbund_ID", "Quellklasse_Code"]]
        .drop_duplicates()
        .merge(classes[["Standortverbund_ID", "Quellenzahlklasse"]], on="Standortverbund_ID", how="inner")
    )
    if site_q.empty:
        make_no_data_chart(path, "Q-Vorkommen nach Standortkomplexität")
        return
    order = ["1 Quelle", "2 Quellen", "3–4 Quellen", "5–7 Quellen", "8+ Quellen"]
    table = pd.crosstab(site_q["Quellenzahlklasse"], site_q["Quellklasse_Code"]).reindex(
        index=[x for x in order if x in set(site_q["Quellenzahlklasse"])],
        columns=Q_ORDER,
        fill_value=0,
    )
    qs = [q for q in Q_ORDER if table[q].sum() > 0]
    table = table[qs]
    heatmap_with_grey_green(
        table,
        "Auftreten der Q-Klassen nach Anzahl der Quellen am Standort",
        path,
        xlabel="Quellklasse",
        ylabel="Anzahl Quellenblöcke am Standort",
        value_kind="count",
        x_labels=[q_label(q) for q in qs],
    )


def _ki_size_class_order():
    return ["SEHR_KLEIN", "KLEIN", "MITTEL", "GROSS", "SEHR_GROSS"]


def _score_subset(sites):
    if "KI_Relativer_Groessenscore_0_100" not in sites.columns:
        return sites.iloc[0:0].copy()
    temp = sites.copy()
    temp["KI_Relativer_Groessenscore_0_100"] = pd.to_numeric(
        temp["KI_Relativer_Groessenscore_0_100"], errors="coerce"
    )
    return temp[temp["KI_Relativer_Groessenscore_0_100"].notna()].copy()


def _score_coverage_text(sites):
    n_total = len(sites)
    n_score = len(_score_subset(sites))
    return n_score, n_total, f"nur Standorte mit Score: n={n_score} von {n_total}"


def chart_heat_vs_ki_size_score(sites, path):
    temp = _score_subset(sites)
    n_score, n_total, note = _score_coverage_text(sites)
    if temp.empty:
        make_no_data_chart(path, "Standortwärme und KI-Größenscore", "Für diese Gruppe liegt kein belastbarer Größenscore vor.")
        return
    scatter_with_regression(
        temp,
        "KI_Relativer_Groessenscore_0_100",
        "Waermemenge_Standort_kWh_a",
        path,
        xlabel="KI-Größenscore [0–100]",
        ylabel="Standortwärmemenge [kWh/a]",
        title=f"Standortwärme und KI-Größenscore ({note})",
        y_log=True,
        x_log=False,
    )


def chart_qdiversity_vs_ki_size_score(sites, path):
    temp = _score_subset(sites)
    _, _, note = _score_coverage_text(sites)
    if temp.empty:
        make_no_data_chart(path, "Q-Vielfalt und KI-Größenscore", "Für diese Gruppe liegt kein belastbarer Größenscore vor.")
        return
    scatter_with_regression(
        temp,
        "KI_Relativer_Groessenscore_0_100",
        "Anzahl_Q_Klassen",
        path,
        xlabel="KI-Größenscore [0–100]",
        ylabel="Anzahl Q-Klassen am Standort",
        title=f"Q-Vielfalt und KI-Größenscore ({note})",
        y_log=False,
        x_log=False,
    )


def chart_sourcecount_vs_ki_size_score(sites, path):
    temp = _score_subset(sites)
    _, _, note = _score_coverage_text(sites)
    if temp.empty:
        make_no_data_chart(path, "Quellenanzahl und KI-Größenscore", "Für diese Gruppe liegt kein belastbarer Größenscore vor.")
        return
    scatter_with_regression(
        temp,
        "KI_Relativer_Groessenscore_0_100",
        "Anzahl_Quellenbloecke",
        path,
        xlabel="KI-Größenscore [0–100]",
        ylabel="Anzahl Quellenblöcke",
        title=f"Quellenanzahl und KI-Größenscore ({note})",
        y_log=False,
        x_log=False,
    )


def chart_ki_size_class_counts(sites, path):
    temp = sites.copy()
    if "KI_Groessenklasse_innerhalb_Gruppe" not in temp.columns:
        make_no_data_chart(path, "KI-Größenklassen und fehlende Scores")
        return

    score = pd.to_numeric(temp.get("KI_Relativer_Groessenscore_0_100"), errors="coerce")
    classes = temp["KI_Groessenklasse_innerhalb_Gruppe"].fillna("").map(clean_string)
    display = classes.where(score.notna() & classes.ne(""), "OHNE_SCORE")

    order = _ki_size_class_order() + ["OHNE_SCORE"]
    counts = display.value_counts().reindex(order, fill_value=0)
    counts = counts[counts > 0]
    colors = ["#5f8f5f" if label != "OHNE_SCORE" else "#d9d9d9" for label in counts.index]

    fig, ax = plt.subplots(figsize=(10, 5.8))
    bars = ax.bar(counts.index, counts.values, color=colors)
    ax.set_ylabel("Anzahl Standorte")
    ax.set_xlabel("KI-Größenklasse innerhalb der Gruppe")
    ax.set_title("KI-Größenklassen – fehlende Scores separat ausgewiesen")
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def _classified_size_sites(sites):
    """Use the same recorded, score-backed classes as figure 35; no rebinning."""
    if "KI_Groessenklasse_innerhalb_Gruppe" not in sites.columns:
        return pd.DataFrame(columns=["Standortverbund_ID", "KI_Groessenklasse_innerhalb_Gruppe"])
    subset = _score_subset(sites).copy()
    subset["KI_Groessenklasse_innerhalb_Gruppe"] = (
        subset["KI_Groessenklasse_innerhalb_Gruppe"].fillna("").map(clean_string)
        .str.upper().str.replace("-", "_", regex=False).str.replace(" ", "_", regex=False)
    )
    subset = subset[subset["KI_Groessenklasse_innerhalb_Gruppe"].isin(_ki_size_class_order())]
    return subset[["Standortverbund_ID", "KI_Groessenklasse_innerhalb_Gruppe"]].drop_duplicates("Standortverbund_ID")


def _class_q_mix(sites, sources):
    classified = _classified_size_sites(sites)
    if classified.empty:
        return pd.DataFrame(columns=Q_ORDER), classified
    temp = sources.merge(classified, on="Standortverbund_ID", how="inner")
    if temp.empty:
        return pd.DataFrame(columns=Q_ORDER), classified
    pivot = pd.pivot_table(
        temp, index="KI_Groessenklasse_innerhalb_Gruppe", columns="Quellklasse_Code",
        values="Waermemenge_kWh_a", aggfunc="sum", fill_value=0,
    ).reindex(index=_ki_size_class_order(), columns=Q_ORDER, fill_value=0)
    # Fehlende Klassen nicht künstlich als 0%-Mix darstellen.
    pivot = pivot.loc[pivot.sum(axis=1).gt(0)]
    shares = pivot.div(pivot.sum(axis=1), axis=0)
    return shares, classified


def chart_ki_size_class_q_mix(sites, sources, path):
    shares, classified = _class_q_mix(sites, sources)
    if shares.empty:
        make_no_data_chart(path, "Q-Mix nach KI-Größenklasse", "Keine Standorte mit dokumentierter Größenklasse und Score.")
        return
    class_counts = classified["KI_Groessenklasse_innerhalb_Gruppe"].value_counts()
    fig, ax = plt.subplots(figsize=(12, 6.2))
    bottom = np.zeros(len(shares))
    x = np.arange(len(shares))
    for q in Q_ORDER:
        vals = shares[q].to_numpy(dtype=float)
        if np.all(vals == 0):
            continue
        ax.bar(x, vals, bottom=bottom, label=q_label(q), color=Q_COLORS[q])
        bottom += vals
    labels = [f"{name.replace('_', ' ').title()}\n(n={class_counts.get(name, 0)})" for name in shares.index]
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Anteil an der Jahreswärmemenge")
    ax.set_xlabel("KI-Größenklasse innerhalb der Profilgruppe (keine Score-Quartile)")
    ax.set_title(f"Q-Mix nach KI-Größenklasse (n={len(classified)} klassifizierte Standorte)")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def chart_ki_size_class_q_mix_lines(sites, sources, path):
    shares, classified = _class_q_mix(sites, sources)
    if shares.empty:
        make_no_data_chart(path, "Q-Anteile nach KI-Größenklasse", "Keine Standorte mit dokumentierter Größenklasse und Score.")
        return
    class_counts = classified["KI_Groessenklasse_innerhalb_Gruppe"].value_counts()
    fig, ax = plt.subplots(figsize=(12, 6.2))
    x = np.arange(len(shares))
    for q in Q_ORDER:
        vals = shares[q].to_numpy(dtype=float)
        if np.all(vals == 0):
            continue
        ax.plot(x, vals, marker="o", linewidth=2.0, color=Q_COLORS[q], label=q_label(q))
    labels = [f"{name.replace('_', ' ').title()}\n(n={class_counts.get(name, 0)})" for name in shares.index]
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Anteil an der Jahreswärmemenge")
    ax.set_xlabel("KI-Größenklasse innerhalb der Profilgruppe (keine Score-Quartile)")
    ax.set_title(f"Q-Anteile nach KI-Größenklasse – Linien (n={len(classified)})")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(axis="y", alpha=0.18)
    save_figure(fig, path)


def chart_ki_metric_types(sites, path):
    # Primär echte für den Score dokumentierte Kennzahltypen auswerten.
    types = []
    all_types_on_scored_sites = []
    scored = _score_subset(sites)
    direct_sites = set()
    for idx in range(1, 6):
        type_col = f"KI_Kennzahl_{idx}_Typ"
        use_col = f"KI_Kennzahl_{idx}_Fuer_Score_verwenden"
        if type_col not in sites.columns:
            continue
        if use_col in sites.columns:
            mask = sites[use_col].map(_score_use_is_direct)
            vals = sites.loc[mask, type_col].fillna("").map(clean_string)
            types.extend([v for v in vals if v])
            direct_sites.update(sites.loc[mask, "Standortverbund_ID"].tolist())
        if type_col in scored.columns:
            vals_scored = scored[type_col].fillna("").map(clean_string)
            all_types_on_scored_sites.extend([v for v in vals_scored if v])

    if types:
        values = types
        xlabel = "Anzahl direkt für den Score verwendeter Kennzahlen"
        title = "Für den Größenscore direkt verwendete Kennzahltypen"
        note = f"Dokumentierte Direktverwendungen: {len(types)} bei {len(direct_sites)} Standorten"
    elif all_types_on_scored_sites:
        # Fallback ausdrücklich anders kennzeichnen: Aus dem Vorhandensein
        # eines Typs folgt NICHT, dass er direkt für den Score verwendet wurde.
        values = all_types_on_scored_sites
        xlabel = "Anzahl dokumentierter Kennzahlen bei Standorten mit Score"
        title = "Kennzahltypen bei Standorten mit KI-Score (Direktverwendung unbekannt)"
        note = "Keine expliziten Direktkennzeichnungen erkannt – keine Aussage zur Score-Verwendung!"
    else:
        n = len(scored)
        make_no_data_chart(
            path, "Kennzahltypen der KI-Größenscores",
            f"{n} Standorte mit Score, aber keine auswertbaren KI_Kennzahl_1..5_Typ-Felder.\n"
            "Scores/Größenklassen allein enthalten keine Information über die verwendeten Kennzahltypen."
        )
        return

    counts = pd.Series(values).value_counts().head(15).sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(11, max(5.5, len(counts) * 0.45)))
    ax.barh(counts.index, counts.values, color="#688e68")
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.18)
    ax.text(0.01, -0.13, note, transform=ax.transAxes, fontsize=8, va="top", color="#555555")
    save_figure(fig, path)


def chart_site_heat_vs_hhi(sites, path):
    scatter_with_regression(
        sites,
        "Waermemenge_Standort_kWh_a",
        "HHI_Quellenwaerme",
        path,
        xlabel="Standortwärmemenge [kWh/a]",
        ylabel="HHI der Quellenwärme (1 = vollständig konzentriert)",
        title="Standortgröße und Konzentration der Abwärme auf wenige Quellen",
        x_log=True,
        ylim=(-0.02, 1.02),
    )


def chart_q_source_size_classes(sources, path):
    temp = sources[sources["Waermemenge_kWh_a"] > 0].copy()
    if temp.empty:
        make_no_data_chart(path, "Q-Klassen nach relativer Quellengröße")
        return
    # Quartile werden innerhalb der aktuellen Profilgruppe gebildet.
    temp["Quellengroessenklasse"] = pd.qcut(
        temp["Waermemenge_kWh_a"].rank(method="first"),
        q=4,
        labels=["Q1 klein", "Q2", "Q3", "Q4 groß"],
    ).astype(str)
    q_order = ordered_present_qs(temp["Quellklasse_Code"])
    size_order = ["Q1 klein", "Q2", "Q3", "Q4 groß"]
    table = pd.crosstab(temp["Quellklasse_Code"], temp["Quellengroessenklasse"]).reindex(
        index=q_order,
        columns=size_order,
        fill_value=0,
    )
    heatmap_with_grey_green(
        table,
        "Q-Klassen nach relativer Größe der Einzelquellen",
        path,
        xlabel="Quellengrößenquartil innerhalb der Gruppe",
        ylabel="Quellklasse",
        value_kind="count",
        y_labels=[q_label(q) for q in q_order],
    )


# =============================================================================
# 11. EXCEL FORMATIEREN
# =============================================================================


def autosize_worksheet(ws, max_width=45):
    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        max_len = 0
        for row_idx in range(1, min(ws.max_row, 300) + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            if value is not None:
                max_len = max(max_len, len(str(value)))
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), max_width)



def format_excel(path):
    wb = load_workbook(path)
    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)

    for ws in wb.worksheets:
        if ws.max_row < 1:
            continue
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if ws.max_row >= 2:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        autosize_worksheet(ws)

    wb.save(path)


# =============================================================================
# 12. EINE GRUPPE ANALYSIEREN
# =============================================================================


def analyze_group(group_id: str, group_folder: Path):
    print()
    print("=" * 90)
    print(f"GRUPPENANALYSE {group_id}")
    print("=" * 90)

    blocks = read_table_auto(group_folder, "source_blocks", required=True)
    _sites_input = read_table_auto(group_folder, "sites", required=False)

    sources_raw = prepare_source_table(blocks, group_id)
    sources_raw = sources_raw[sources_raw["Quellklasse_Code"].isin(["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"])].copy()
    sources_raw = sources_raw[sources_raw["Waermemenge_kWh_a"] > 0].copy()

    (
        sources,
        sources_with_flags,
        excluded_heat_sources,
        invalid_temperature_sources,
        preprocessing_summary,
    ) = preprocess_analysis_sources(sources_raw)

    sites = build_site_metrics(sources)
    size_info = load_size_info(group_id)
    size_metrics_long = build_size_metrics_long(size_info)
    score_coverage = build_score_coverage_table(size_info)
    sites = merge_size_info_into_sites(sites, size_info)
    sites = add_dominant_q_to_sites(sites, sources)
    overview = build_overview(group_id, sources, sites)
    q_summary = build_q_summary(sources)
    operating_summary = build_operating_summary(sources)
    portfolio_summary = build_portfolio_summary(sites)
    family_summary = build_family_summary(sources)

    source_assoc = build_source_numeric_associations(sources)
    site_assoc = build_site_numeric_associations(sites)
    eta_df = build_numeric_by_category_effects(sources)
    cramers_df = build_categorical_associations(sources)
    q_cooccurrence, site_q_matrix = build_q_cooccurrence(sites, sources)
    extremes = build_extreme_cases(sources, sites)
    pca_scores, pca_loadings = build_site_pca(sites)

    notes = build_pattern_notes(
        group_id,
        sources,
        sites,
        source_assoc,
        site_assoc,
        eta_df,
        cramers_df,
        q_summary,
        portfolio_summary,
    )

    # zusätzliche Pivot-Tabellen
    # In den Betriebsprofil-Auswertungen werden alle nicht standardisierten
    # Profile zu "Sonstige" zusammengefasst.
    q_bp_count = pd.crosstab(
        sources["Quellklasse_Code"],
        sources["Betriebsprofil_Analyse"],
    )
    q_bp_heat = pd.pivot_table(
        sources,
        index="Quellklasse_Code",
        columns="Betriebsprofil_Analyse",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    )

    q_season_count = pd.crosstab(
        sources["Quellklasse_Code"],
        sources["Saisonklasse"],
    )
    q_season_heat = pd.pivot_table(
        sources,
        index="Quellklasse_Code",
        columns="Saisonklasse",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    )

    q_temp_count = pd.crosstab(
        sources["Quellklasse_Code"],
        sources["Temperaturklasse_Analyse"],
    )
    q_temp_heat = pd.pivot_table(
        sources,
        index="Quellklasse_Code",
        columns="Temperaturklasse_Analyse",
        values="Waermemenge_kWh_a",
        aggfunc="sum",
        fill_value=0,
    )

    operating_analysis_summary = (
        sources.groupby("Betriebsprofil_Analyse")
        .agg(
            Anzahl_Quellen=("Generator_Block_ID", "size"),
            Waermemenge_kWh_a=("Waermemenge_kWh_a", "sum"),
        )
        .reset_index()
    )
    operating_analysis_summary["Anteil_Quellen"] = (
            operating_analysis_summary["Anzahl_Quellen"]
            / max(len(sources), 1)
    )
    operating_analysis_summary["Anteil_Waermemenge"] = (
            operating_analysis_summary["Waermemenge_kWh_a"]
            / max(sources["Waermemenge_kWh_a"].sum(), 1e-12)
    )

    output_dir = OUTPUT_BASE_DIR / group_id
    chart_dir = output_dir / "Diagramme"
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    # CSV-Tabellen
    tables = {
        "Ueberblick": overview,
        "Vorbehandlung": preprocessing_summary,
        "Ausgeschl_Waermeausreisser": excluded_heat_sources,
        "Bereinigte_Temperaturen": invalid_temperature_sources,
        "Quellen_mit_Pruefflags": sources_with_flags,
        "Automatische_Muster": notes,
        "Quellen": sources,
        "Standorte": sites,
        "Standortgroessen_Recherche": size_info,
        "Standortgroessen_Kennzahlen": size_metrics_long,
        "Standortgroessen_Scoreabdeckung": score_coverage,
        "Q_Uebersicht": q_summary,
        "Betriebsprofile_Roh": operating_summary,
        "Betriebsprofile_Analyse": operating_analysis_summary,
        "Portfolios": portfolio_summary,
        "Quellenfamilien": family_summary,
        "Quellen_Abhaeng": source_assoc,
        "Standort_Abhaeng": site_assoc,
        "Kategorie_Eta2": eta_df,
        "Kategorie_CramersV": cramers_df,
        "Q_Kookkurrenz": q_cooccurrence,
        "Standort_Q_Matrix": site_q_matrix,
        "Q_x_Betrieb_Anzahl": q_bp_count.reset_index(),
        "Q_x_Betrieb_Waerme": q_bp_heat.reset_index(),
        "Q_x_Saison_Anzahl": q_season_count.reset_index(),
        "Q_x_Saison_Waerme": q_season_heat.reset_index(),
        "Q_x_Temp_Anzahl": q_temp_count.reset_index(),
        "Q_x_Temp_Waerme": q_temp_heat.reset_index(),
        "Extremfaelle": extremes,
        "Standort_PCA": pca_scores,
        "PCA_Loadings": pca_loadings,
    }

    if WRITE_CSV_TABLES:
        csv_dir = output_dir / "Tabellen_CSV"
        csv_dir.mkdir(parents=True, exist_ok=True)
        for name, table in tables.items():
            table.to_csv(csv_dir / f"{name}.csv", sep=";", encoding="utf-8-sig", index=False)

    # Excel
    excel_path = output_dir / f"Gruppenanalyse_{group_id}_Iteration7.xlsx"
    if WRITE_EXCEL:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for sheet_name, table in tables.items():
                table.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        format_excel(excel_path)

    # Diagramme – Iteration 7: 36 Abbildungen, nach Themen und Relevanz geordnet.
    # Nummern und Dateien sind eindeutig; Excel-/CSV-Tabellenauswertungen bleiben erhalten.
    chart_index = []
    chart_section = ""

    def _chart_record(new_num, old_num, path, title):
        if path.exists():
            chart_index.append({
                "Datei": path.name,
                "Diagramm": title,
                "Neue_Nummer": int(new_num),
                "Bisherige_Nummer": int(old_num),
                "Themenblock": chart_section,
            })

    def make_chart(new_num, old_num, stem, title, func, *args):
        if not WRITE_PNG:
            return
        path = chart_dir / f"{new_num:02d}_{stem}.png"
        try:
            func(*args, path)
            _chart_record(new_num, old_num, path, title)
        except Exception as exc:
            warnings.warn(f"Diagramm {path.name} konnte nicht erzeugt werden: {exc}")

    def make_chart_pair(spec_a, spec_b, func, *args):
        """Zwei fachlich zusammengehörende Heatmaps in einem Aufruf erzeugen."""
        if not WRITE_PNG:
            return
        a_num, a_old, a_stem, a_title = spec_a
        b_num, b_old, b_stem, b_title = spec_b
        path_a = chart_dir / f"{a_num:02d}_{a_stem}.png"
        path_b = chart_dir / f"{b_num:02d}_{b_stem}.png"
        try:
            func(*args, path_a, path_b)
            _chart_record(a_num, a_old, path_a, a_title)
            _chart_record(b_num, b_old, path_b, b_title)
        except Exception as exc:
            warnings.warn(f"Diagrammpaar {path_a.name} / {path_b.name} fehlgeschlagen: {exc}")

    # =====================================================================
    # A – Grundlagen und Überblick
    # =====================================================================
    chart_section = 'A – Grundlagen und Überblick'
    make_chart(1, 1, 'Quellengroesse_Histogramm', 'Größenverteilung der Quellen', chart_heat_distribution, sources)
    make_chart(2, 16, 'Q_Haeufigkeit_Anzahl', 'Q-Klassen nach Anzahl der Quellen', chart_q_count, sources)
    make_chart(3, 17, 'Q_Waermeanteile', 'Q-Klassen nach Wärmemengenanteil', chart_q_heat_share, sources)
    make_chart(4, 2, 'Quellengroesse_nach_Q', 'Quellengröße nach Q-Klasse', chart_heat_by_q, sources)
    make_chart(5, 11, 'Q_Mix_groesste_Standorte', 'Q-Zusammensetzung größter Standorte', chart_site_q_stack, sites)

    # =====================================================================
    # B – Standortstruktur, Portfolio und Konzentration
    # =====================================================================
    chart_section = 'B – Standortstruktur, Portfolio und Konzentration'
    make_chart(6, 8, 'Standortwaerme_vs_Quellenzahl', 'Standortwärme gegen Quellenanzahl mit Regression', chart_site_heat_vs_count, sites)
    make_chart(7, 12, 'Haeufigste_Portfolios', 'Häufigste Quellenportfolios', chart_portfolios, portfolio_summary)
    make_chart(8, 13, 'Q_Kookkurrenz', 'Q-Klassen-Kookkurrenz mit Wiederholungen gleicher Q-Klasse', chart_q_cooccurrence, q_cooccurrence)
    make_chart(9, 24, 'Quellenzahl_vs_Dominanz', 'Quellenanzahl gegen Dominanz der größten Quelle mit Regression', chart_source_count_vs_dominance, sites)
    make_chart(10, 9, 'Standortwaerme_vs_Dominanz', 'Standortwärme gegen Dominanz der größten Quelle (nur >=2 Quellen)', chart_site_heat_vs_dominance, sites)
    make_chart(11, 31, 'Standortwaerme_vs_HHI', 'Standortwärme gegen Quellenkonzentration mit Regression', chart_site_heat_vs_hhi, sites)
    make_chart(12, 27, 'Dominante_Q_Klasse_Standorte_ab2Quellen', 'Q-Klasse der größten Quelle je Mehrquellenstandort', chart_dominant_q_sites, sites)
    make_chart(13, 28, 'Quellenanteil_am_Standort_nach_Q', 'Relative Quellenanteile nach Q (nur Mehrquellenstandorte)', chart_source_share_by_q, sources)
    make_chart(14, 29, 'Abwaermequartil_x_Q_Mix', 'Q-Mix nach PFA-Abwärme-Größenquartil', chart_site_size_class_q_mix, sites, sources)
    make_chart(15, 30, 'Abwaermequartil_x_Q_Mix_Linien', 'Q-Anteile nach PFA-Abwärme-Größenquartil – Linien', chart_site_size_class_q_mix_lines, sites, sources)

    # =====================================================================
    # C – Unabhängig recherchierte KI-Standortgröße
    # =====================================================================
    chart_section = 'C – Unabhängig recherchierte KI-Standortgröße'
    make_chart(16, 35, 'KI_Groessenklassen_Anzahl', 'Verteilung der KI-Größenklassen', chart_ki_size_class_counts, sites)
    make_chart(17, 40, 'KI_Score_Kennzahltypen', 'Für KI-Größenscore verwendete Kennzahltypen', chart_ki_metric_types, sites)
    make_chart(18, 32, 'KI_Groessenscore_vs_Standortwaerme', 'KI-Größenscore und Standortwärmemenge', chart_heat_vs_ki_size_score, sites)
    make_chart(19, 34, 'KI_Groessenscore_vs_Quellenzahl', 'KI-Größenscore und Quellenanzahl', chart_sourcecount_vs_ki_size_score, sites)
    make_chart(20, 33, 'KI_Groessenscore_vs_Q_Vielfalt', 'KI-Größenscore und Q-Vielfalt', chart_qdiversity_vs_ki_size_score, sites)
    make_chart(21, 36, 'KI_Groessenklasse_x_Q_Mix', 'Q-Mix nach KI-Größenklasse', chart_ki_size_class_q_mix, sites, sources)
    make_chart(22, 37, 'KI_Groessenklasse_x_Q_Mix_Linien', 'Q-Anteile nach KI-Größenklasse – Linien', chart_ki_size_class_q_mix_lines, sites, sources)

    # =====================================================================
    # D – Quellenfamilien und Betriebsprofile
    # =====================================================================
    chart_section = 'D – Quellenfamilien und Betriebsprofile'
    make_chart(23, 14, 'Quellenfamilien', 'Häufigste Quellen-/Maschinenfamilien', chart_families, family_summary)
    make_chart_pair(
        (24, 6, 'Q_x_Betrieb_Anzahl', 'Q × Betriebsprofil – Anzahl; Sonderprofile = Sonstige'),
        (25, 7, 'Q_x_Betrieb_Waerme', 'Q × Betriebsprofil – Wärmemenge; Sonderprofile = Sonstige'),
        chart_operating_q_heatmaps, sources,
    )

    # =====================================================================
    # E – Temperaturcharakteristik
    # =====================================================================
    chart_section = 'E – Temperaturcharakteristik'
    make_chart(26, 3, 'Temperatur_nach_Q', 'Temperatur nach Q-Klasse', chart_temp_by_q, sources)
    make_chart_pair(
        (27, 18, 'Q_x_Temperatur_Anzahl', 'Q × Temperaturklasse – Anzahl'),
        (28, 19, 'Q_x_Temperatur_Waerme', 'Q × Temperaturklasse – Wärmemenge'),
        chart_q_temp_heatmaps, sources,
    )
    make_chart(29, 4, 'Waerme_vs_Temperatur', 'Quellengröße und Temperatur', chart_heat_vs_temp, sources)

    # =====================================================================
    # F – Saisonalität
    # =====================================================================
    chart_section = 'F – Saisonalität'
    make_chart_pair(
        (30, 20, 'Q_x_Saison_Anzahl', 'Q × Saisonklasse – Anzahl'),
        (31, 21, 'Q_x_Saison_Waerme', 'Q × Saisonklasse – Wärmemenge'),
        chart_q_season_heatmaps, sources,
    )
    make_chart(32, 5, 'Waerme_vs_Sommerfaktor', 'Quellengröße und Saisonalität', chart_heat_vs_season, sources)
    make_chart(33, 23, 'Standortwaerme_vs_Saisonalitaetsanteil', 'Standortwärme und starke Saisonalität', chart_site_heat_vs_seasonal_share, sites)

    # =====================================================================
    # G – Explorative PCA
    # =====================================================================
    chart_section = 'G – Explorative PCA'
    make_chart(34, 15, 'Standort_PCA', 'Explorative Standort-PCA', chart_pca, pca_scores)
    make_chart(35, 38, 'PCA_Loadings_PC1', 'PCA-Loadings PC1', chart_pca_loadings, pca_loadings, "PC1_Loading")
    make_chart(36, 39, 'PCA_Loadings_PC2', 'PCA-Loadings PC2', chart_pca_loadings, pca_loadings, "PC2_Loading")

    # Nummern im Diagrammindex explizit absichern.
    chart_index.sort(key=lambda x: x["Neue_Nummer"])

    chart_index_df = pd.DataFrame(chart_index)
    if WRITE_CSV_TABLES:
        chart_index_df.to_csv(output_dir / "Diagrammindex.csv", sep=";", encoding="utf-8-sig", index=False)

    # Konsolenausgabe
    print(f"Standorte:           {len(sites):,}")
    print(f"Quellenblöcke:       {len(sources):,}")
    print(f"Gesamtwärmemenge:    {sources['Waermemenge_kWh_a'].sum():,.0f} kWh/a")
    print(f"Diagramme erzeugt:   {len(chart_index_df):,}")
    print(f"Wärmeausreißer entfernt: {len(excluded_heat_sources):,}")
    print(f"Temperaturwerte bereinigt: {len(invalid_temperature_sources):,}")
    if len(excluded_heat_sources):
        print("  -> Details: Excel/CSV 'Ausgeschl_Waermeausreisser'")
    if len(invalid_temperature_sources):
        print("  -> Details: Excel/CSV 'Bereinigte_Temperaturen'")
    print(f"Ausgabe:             {output_dir}")

    if not notes.empty:
        print()
        print("Ausgewählte automatische Musterhinweise:")
        for text in notes["Hinweis"].head(12):
            print(f"  - {text}")

    return {
        "Experiment_Gruppe": group_id,
        "Standorte": len(sites),
        "Quellenbloecke": len(sources),
        "Gesamtwaermemenge_kWh_a": float(sources["Waermemenge_kWh_a"].sum()),
        "Diagramme": len(chart_index_df),
        "Analyse_Datei": excel_path.name if WRITE_EXCEL else "",
    }


# =============================================================================
# 13. HAUPTPROGRAMM
# =============================================================================


def main():
    print()
    print("=" * 90)
    print("PFA – GRUPPENANALYSE DER ABWÄRMEPOTENTIALE – ITERATION 7")
    print("=" * 90)

    if not INPUT_BASE_DIR.exists():
        raise FileNotFoundError(f"Eingabeordner nicht gefunden: {INPUT_BASE_DIR}")

    group_folders = [p for p in INPUT_BASE_DIR.glob(GROUP_FOLDER_PATTERN) if p.is_dir()]
    group_folders = sorted(group_folders, key=lambda p: group_sort_key(p.name))

    if TARGET_GROUPS is not None:
        wanted = {clean_string(g).upper() for g in TARGET_GROUPS}
        group_folders = [p for p in group_folders if p.name.upper() in wanted]

    if not group_folders:
        raise FileNotFoundError("Keine passenden Gruppenordner gefunden.")

    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

    overview_rows = []
    failures = []

    for folder in group_folders:
        group_id = folder.name
        try:
            overview_rows.append(analyze_group(group_id, folder))
        except Exception as exc:
            print(f"\nFEHLER in {group_id}: {exc}")
            failures.append({"Experiment_Gruppe": group_id, "Fehler": str(exc)})

    if overview_rows:
        pd.DataFrame(overview_rows).to_csv(
            OUTPUT_BASE_DIR / "_Uebersicht_Gruppenanalyse_Iteration7.csv",
            sep=";",
            encoding="utf-8-sig",
            index=False,
            )

    if failures:
        pd.DataFrame(failures).to_csv(
            OUTPUT_BASE_DIR / "_Fehler_Gruppenanalyse_Iteration7.csv",
            sep=";",
            encoding="utf-8-sig",
            index=False,
            )

    print()
    print("=" * 90)
    print("FERTIG")
    print("=" * 90)
    print(f"Erfolgreich: {len(overview_rows):,}")
    print(f"Fehler:      {len(failures):,}")
    print()
    print("Zur Prüfung der Ausgaben hilfreich:")
    print("  - Gruppenanalyse_Gxx_Iteration7.xlsx")
    print("  - einige oder alle PNG-Diagramme")
    print("  - falls etwas merkwürdig aussieht: Quellen.csv und Standorte.csv")
    print("=" * 90)


if __name__ == "__main__":
    main()
