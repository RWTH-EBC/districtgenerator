from pathlib import Path
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter

import numpy as np
import pandas as pd

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# =============================================================================
# GENERATOR-DATENPAKETE – ITERATION 3
# =============================================================================
#
# ZIEL
# ----
# Dieser Code ist ein NEUER Verarbeitungsschritt nach:
#
#   1. Profilgruppe_Gxx.xlsx
#   2. manuell fertig bearbeiteter Pruefung_Gxx_geprueft.xlsx
#
# Er führt noch KEINE endgültige synthetische Profilgenerierung durch.
#
# Stattdessen erzeugt er eine belastbare empirische Datenbasis für die
# halbsynthetische Profilgenerierung und gleichzeitig Diagnoseauswertungen,
# die wir in den nächsten Iterationen gemeinsam verbessern können.
#
#
# ZENTRALE METHODIK
# -----------------
#
# A) Manuelle Prüfentscheidungen anwenden
#
#    BESTAETIGT
#        -> Originalwerte bleiben bestehen
#
#    KORRIGIERT
#        -> nur ausgefüllte Korrekturfelder ersetzen Originalwerte
#
#    AUSSCHLIESSEN
#        -> Potential wird vollständig aus der weiteren Generatorbasis entfernt
#
#
# B) 20-%-QX-Eignung NACH den Korrekturen neu berechnen
#
#    QX-Anteil =
#
#        Wärmemenge nicht Q1-Q7
#        ----------------------
#        gesamte positive Jahreswärmemenge
#
#    Nur Standorte mit QX <= 20 % bleiben in der Generatorbasis.
#
#    WICHTIG:
#    Die ursprünglichen Gruppendateien enthalten nur die bereits vorläufig
#    geeigneten Standorte. Dieser Code kann daher Standorte nachträglich
#    ENTFERNEN, aber keine zuvor herausgefilterten Standorte neu hinzufügen.
#
#
# C) QX anschließend NICHT in das Generator-Quellenportfolio aufnehmen
#
#    Für die technischen Q1-Q7-Anteile wird auf Q1-Q7 renormiert.
#
#
# D) Betriebsprofil aus vorhandenen Angaben ableiten
#
#    Bevorzugt:
#        "Verfügbarkeit" wie "5 Tage 8 Std"
#
#    Falls dort "Rest" / keine strukturierte Angabe:
#        tägliche Verfügbarkeit [h]
#        + Wochenende Ja/Nein
#
#    Standardisierte Stundenklassen:
#        8 / 12 / 16 / 20 / 24 h pro Tag
#
#    Standardisierte Wochentage:
#        5 / 7 Tage
#
#    Ungewöhnliche Angaben (z. B. 6 Tage/Woche, <6 h/Tag) werden vorerst
#    NICHT gewaltsam zugeordnet, sondern als SONSTIG markiert und in der
#    Diagnostik ausgewertet.
#
#
# E) Saisonalität aus Monats-Leistungsprofilen ableiten
#
#    Die ABSOLUTEN Leistungswerte werden NICHT als Generatorleistung verwendet.
#
#    Es wird ausschließlich die RELATIVE FORM der 12 Monatswerte genutzt.
#
#    Monatsfaktor:
#
#        f_m = Monatswert / gewichteter Jahresmittelwert
#
#    Sommerfaktor April–September:
#
#        = 1    -> keine Verschiebung
#        > 1    -> sommerlastig
#        < 1    -> winterlastig
#
#    Für Iteration 1 werden nur vollständige 12-Monats-Profile als empirische
#    Saisonalität akzeptiert. Unvollständige Profile werden als unbekannt
#    markiert und diagnostisch ausgewertet.
#
#
# F) Quellenblöcke bilden
#
#    Mehrere technisch praktisch gleiche Quellen desselben Standortes werden
#    konservativ zusammengefasst, wenn ALLE folgenden Merkmale gleich sind:
#
#        - Standort
#        - Q-Klasse
#        - normalisierte Quellen-/Maschinenfamilie
#        - Temperatur (Iteration 1: auf 1 °C gerundet)
#        - standardisiertes Betriebsprofil
#        - Saisonalitätssignatur
#
#    Beispiel:
#
#        Kompressor 1, Q7, 60 °C, 16/5, gleiche Saisonform
#        Kompressor 2, Q7, 60 °C, 16/5, gleiche Saisonform
#
#    -> ein Generator-Quellenblock
#
#    Aggregiert wird primär die JAHRESWÄRMEMENGE.
#
#    Die gemeldete Leistung wird nur diagnostisch summiert und ist KEINE
#    Generator-Maximalleistung.
#
#
# G) Empirische halbsynthetische Struktur
#
#    Ein realer Standort bleibt als gemeinsame Beobachtung erhalten:
#
#        Portfolio + relative Größen der Quellenblöcke
#
#    Dadurch werden Portfolio und Quellengrößen NICHT unabhängig voneinander
#    gezogen.
#
#
# AUSGABE
# -------
#
# OUTPUT_DIR/
#   Gxx/
#       cleaned_potentials.parquet
#       source_blocks.parquet
#       sites.parquet
#       mapping_original_to_block.parquet
#       portfolio_frequency.parquet
#       operating_profile_distribution.parquet
#       temperature_distribution.parquet
#       seasonality_distribution.parquet
#       metadata.json
#       Diagnose_Gxx_Iteration3.xlsx
#
# Zusätzlich optional CSV-Dateien als leicht kontrollierbare Fallbacks.
#
# Für die nächste Iteration am besten Diagnose_Gxx_Iteration3.xlsx zurückgeben.
# =============================================================================


# =============================================================================
# 1. PFADE / AUSWAHL
# =============================================================================

BASE_DIR = Path("WZ2025_Vorbereitung")

SOURCE_DIR = (
        BASE_DIR
        / "Quellenklassifikation_final"
)

GROUP_DIR = (
        SOURCE_DIR
        / "Profilgruppen_Export_Waermemenge20_vorlaeufig"
)

REVIEW_DIR = (
        SOURCE_DIR
        / "Profilgruppen_Pruefung_Waermemenge"
)

OUTPUT_DIR = (
        SOURCE_DIR
        / "Generator_Datenpakete_Iteration3"
)

GROUP_PATTERN = "Profilgruppe_G*.xlsx"


# -----------------------------------------------------------------------------
# FÜR DIE ERSTE ITERATION EMPFOHLEN:
#
# Nur eine große Gruppe setzen, z. B.
#
#     TARGET_GROUPS = ["G39"]
#
# Wenn None:
#     alle vorhandenen Gruppen verarbeiten.
# -----------------------------------------------------------------------------

TARGET_GROUPS = ["G39"]


# =============================================================================
# 2. METHODISCHE PARAMETER
# =============================================================================

QX_HEAT_THRESHOLD = 0.20

VALID_SOURCE_CLASSES = [
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "Q5",
    "Q6",
    "Q7",
]


# -----------------------------------------------------------------------------
# Manuelle Prüfdateien
# -----------------------------------------------------------------------------

STRICT_REVIEW_COMPLETE = True

# Wenn eine Gruppendatei "Zahlen_Plausibilitaet" enthält, muss grundsätzlich
# auch Pruefung_Gxx_geprueft.xlsx vorhanden sein.
REQUIRE_REVIEW_FILE_IF_PLAUSIBILITY_EXISTS = True


# -----------------------------------------------------------------------------
# Betriebsprofil
# -----------------------------------------------------------------------------

STANDARD_DAILY_HOURS = [
    8,
    12,
    16,
    20,
    24,
]

# Nur diese Wochenmuster werden in Iteration 1 als Standardprofile akzeptiert.
STANDARD_DAYS_PER_WEEK = [
    5,
    7,
]

# Unterhalb von 6 h/Tag wird vorerst NICHT auf 8 h gezwungen.
MIN_HOURS_FOR_STANDARDIZATION = 6.0

MAX_DAILY_HOURS = 24.0

# Exakte Sonderprofile nur, wenn die Angabe gar nicht sinnvoll in das
# Standardraster 8/12/16/20/24 h und 5/7 Tage passt.

# Größenklassen für Donor-Pools
SIZE_CLASS_Q1 = 1 / 3
SIZE_CLASS_Q2 = 2 / 3
MIN_N_FOR_BRANCH_Q_TEMPERATURE_MODEL = 20

# Ausschluss-Effekte
EXCLUSION_EFFECT_UNRESOLVED = "UNAUFGELOEST_WIE_QX"
EXCLUSION_EFFECT_REMOVE = "PHYSISCH_ENTFERNEN"

PHYSICAL_REMOVAL_KEYWORDS = [
    "duplikat",
    "doppelt",
    "doppelmeldung",
    "mehrfachmeldung",
    "identischer datensatz",
    "kein eigenständiges",
    "kein eigenstaendiges",
    "nicht eigenständig",
    "nicht eigenstaendig",
    "kein separates abwärmepotential",
    "kein separates abwaermepotential",
    "nicht zusätzlich",
    "nicht zusaetzlich",
]

REVIEW_FILE_TEMPLATE = "Pruefung_{group_id}_geprueft.xlsx"


# -----------------------------------------------------------------------------
# Saisonalität
# -----------------------------------------------------------------------------

# In Iteration 1 nur vollständige 12-Monats-Daten als empirische Saisonform.
REQUIRE_ALL_12_MONTHS_FOR_SEASONALITY = True

# Rundung für die Signatur bei der Aggregation.
# Zwei Quellen werden nur zusammengefasst, wenn die normalisierten Monatsfaktoren
# nach Rundung gleich sind.
SEASON_SIGNATURE_DECIMALS = 2  # nur Alt-Kompatibilität; nicht mehr Aggregationskriterium

SUMMER_MONTHS = [
    "Apr",
    "Mai",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
]

WINTER_MONTHS = [
    "Okt",
    "Nov",
    "Dez",
    "Jan",
    "Feb",
    "Mrz",
]


# Kalenderjahr mit 8760 Stunden.
MONTH_HOURS = {
    "Jan": 31 * 24,
    "Feb": 28 * 24,
    "Mrz": 31 * 24,
    "Apr": 30 * 24,
    "Mai": 31 * 24,
    "Jun": 30 * 24,
    "Jul": 31 * 24,
    "Aug": 31 * 24,
    "Sep": 30 * 24,
    "Okt": 31 * 24,
    "Nov": 30 * 24,
    "Dez": 31 * 24,
}


# -----------------------------------------------------------------------------
# Quellenblock-Aggregation
# -----------------------------------------------------------------------------

ENABLE_SOURCE_BLOCK_AGGREGATION = True

# Temperatur wird zunächst sehr streng behandelt.
# 60.0 und 60.4 -> 60 °C
# 60 und 61 -> verschiedene Blöcke
AGGREGATION_MAX_TEMPERATURE_SPAN_C = 5.0

# Quellen ohne Namen werden NICHT anhand eines leeren Namens zusammengefasst.
AGGREGATE_EMPTY_SOURCE_NAMES = False


# -----------------------------------------------------------------------------
# Iteration 3: zusätzliche Sensitivitäts- und Preflight-Parameter
# -----------------------------------------------------------------------------

# Produktive Aggregation bleibt bei maximal 5 K Temperaturspanne.
# 10 K werden ausschließlich diagnostisch simuliert.
AGGREGATION_SENSITIVITY_TEMPERATURE_SPAN_C = 10.0

# Preflight: harte physikalische Grenzen.
ABSOLUTE_TEMPERATURE_MIN_C = -273.15
ABSOLUTE_TEMPERATURE_MAX_C = 2000.0

# Sehr breite Q-spezifische Plausibilitätsgrenzen.
# Außerhalb dieser Bereiche wird NICHT automatisch korrigiert oder gelöscht;
# der Block wird lediglich nicht als Temperatur-/Komplettdonor verwendet.
DONOR_TEMPERATURE_BOUNDS_C = {
    "Q1": (-20.0, 250.0),
    "Q2": (-20.0, 400.0),
    "Q3": (-50.0, 600.0),
    "Q4": (-20.0, 1600.0),
    "Q5": (-50.0, 600.0),
    "Q6": (-50.0, 200.0),
    "Q7": (-50.0, 300.0),
}

SEASON_NORMALIZATION_TOLERANCE = 0.02
SITE_SHARE_SUM_TOLERANCE = 1e-6

# Vorsichtige Namensnormalisierung:
# Nur wahrscheinliche laufende Anlagenkennzeichnungen werden abstrahiert.
ID_PRECEDERS = {
    "anlage",
    "aggregat",
    "extruder",
    "filter",
    "kompressor",
    "kessel",
    "linie",
    "maschine",
    "ofen",
    "pumpe",
    "rlt",
    "tnv",
    "gt",
    "trockner",
    "ventilator",
    "verdichter",
    "walze",
    "kalander",
}

TECHNICAL_UNIT_TOKENS = {
    "w", "kw", "mw", "gw",
    "kwh", "mwh", "gwh",
    "c", "°c",
    "bar", "mbar", "pa", "kpa", "mpa",
    "l", "m3", "m³",
    "kg", "t", "h", "min",
    "mm", "cm", "m",
}

TECHNICAL_CODE_PREFIXES = {
    "dn",
    "pn",
    "ip",
}


# -----------------------------------------------------------------------------
# Dateien schreiben
# -----------------------------------------------------------------------------

WRITE_PARQUET = True
WRITE_CSV = True
WRITE_DIAGNOSTIC_EXCEL = True

# Vorherige Ergebnisse im Zielordner derselben Gruppe überschreiben.
OVERWRITE_GROUP_OUTPUT = True


# =============================================================================
# 3. MONATE / SUCHBEGRIFFE
# =============================================================================

MONTHS = [
    ("Jan", ["januar", "jan"]),
    ("Feb", ["februar", "feb"]),
    ("Mrz", ["märz", "maerz", "mrz"]),
    ("Apr", ["april", "apr"]),
    ("Mai", ["mai"]),
    ("Jun", ["juni", "jun"]),
    ("Jul", ["juli", "jul"]),
    ("Aug", ["august", "aug"]),
    ("Sep", ["september", "sep"]),
    ("Okt", ["oktober", "okt"]),
    ("Nov", ["november", "nov"]),
    ("Dez", ["dezember", "dez"]),
]


# =============================================================================
# 4. ALLGEMEINE HILFSFUNKTIONEN
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
    """
    Robuste Umwandlung deutscher/englischer Zahlenschreibweisen.
    """

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

    # 1.234,56
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

    # 1234,56
    elif "," in text:

        text = text.replace(
            ",",
            ".",
        )

    try:
        return float(text)

    except ValueError:
        return np.nan


def numeric_series(series: pd.Series) -> pd.Series:
    return series.map(
        numeric_value
    )


def bool_value(value) -> bool:
    if isinstance(
            value,
            bool,
    ):
        return value

    if pd.isna(value):
        return False

    if isinstance(
            value,
            (
                    int,
                    float,
                    np.integer,
                    np.floating,
            ),
    ):
        return bool(value)

    text = (
        clean_string(value)
        .casefold()
    )

    return text in {
        "true",
        "wahr",
        "ja",
        "yes",
        "1",
        "y",
    }


def safe_divide(
        numerator,
        denominator,
):
    if (
            pd.isna(numerator)
            or
            pd.isna(denominator)
            or
            denominator == 0
    ):
        return np.nan

    return (
            numerator
            / denominator
    )


def normalize_header(value) -> str:
    """
    Für flexible Spaltensuche.
    """

    text = clean_string(
        value
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char
        in text
        if not unicodedata.combining(char)
    )

    text = text.casefold()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def first_existing_column(
        df,
        candidates,
        required=False,
        label="Spalte",
):
    for column in candidates:

        if column in df.columns:
            return column

    if required:

        raise ValueError(
            f"{label} wurde nicht gefunden.\n\n"
            "Gesuchte Kandidaten:\n"
            + "\n".join(
                f"- {column}"
                for column
                in candidates
            )
        )

    return None


def find_column_by_keywords(
        df,
        include_all=None,
        include_any=None,
        exclude_any=None,
):
    """
    Flexible Suche anhand normalisierter Spaltennamen.
    """

    include_all = [
        normalize_header(x)
        for x
        in (
                include_all
                or []
        )
    ]

    include_any = [
        normalize_header(x)
        for x
        in (
                include_any
                or []
        )
    ]

    exclude_any = [
        normalize_header(x)
        for x
        in (
                exclude_any
                or []
        )
    ]

    for column in df.columns:

        normalized = normalize_header(
            column
        )

        if (
                include_all
                and
                not all(
                    token
                    in normalized
                    for token
                    in include_all
                )
        ):
            continue

        if (
                include_any
                and
                not any(
                    token
                    in normalized
                    for token
                    in include_any
                )
        ):
            continue

        if (
                exclude_any
                and
                any(
                    token
                    in normalized
                    for token
                    in exclude_any
                )
        ):
            continue

        return column

    return None


def unique_nonempty(values):
    seen = set()
    result = []

    for value in values:

        text = clean_string(
            value
        )

        if (
                text
                and
                text not in seen
        ):
            seen.add(
                text
            )

            result.append(
                text
            )

    return result


def quantile_or_nan(
        series,
        q,
):
    values = pd.to_numeric(
        series,
        errors="coerce",
    ).dropna()

    if values.empty:
        return np.nan

    return float(
        values.quantile(q)
    )


def deterministic_id(
        prefix,
        parts,
        length=14,
):
    text = "||".join(
        clean_string(part)
        for part
        in parts
    )

    digest = hashlib.sha1(
        text.encode(
            "utf-8"
        )
    ).hexdigest()[:length].upper()

    return (
        f"{prefix}_{digest}"
    )


def group_id_from_path(
        path: Path,
) -> str:
    match = re.search(
        r"Profilgruppe_(G[^.]+)",
        path.name,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            match
            .group(1)
            .upper()
        )

    return (
        path.stem
        .replace(
            "Profilgruppe_",
            "",
        )
        .upper()
    )


# =============================================================================
# 5. SPALTENIDENTIFIKATION
# =============================================================================

def identify_columns(
        df,
):
    """
    Relevante Spalten aus der originalen Gruppendatei.
    """

    columns = {}

    columns["id"] = first_existing_column(
        df,
        [
            "Originaldatensatz_ID",
        ],
        required=True,
        label="Originaldatensatz_ID",
    )

    columns["site"] = first_existing_column(
        df,
        [
            "Standortverbund_ID",
        ],
        required=True,
        label="Standortverbund_ID",
    )

    columns["company"] = first_existing_column(
        df,
        [
            "Firmenname",
            "Profil_Firmenname",
        ],
    )

    columns["location"] = first_existing_column(
        df,
        [
            "Standortname",
            "Profil_Standortname",
        ],
    )

    columns["name"] = first_existing_column(
        df,
        [
            "Name des Abwärmepotentials",
        ],
        required=True,
        label="Name des Abwärmepotentials",
    )

    columns["heat"] = first_existing_column(
        df,
        [
            "Wärmemenge pro Jahr (in kWh/a)",
            "Waermemenge_pro_Jahr_kWh_a",
        ],
        required=True,
        label="Jahreswärmemenge",
    )

    columns["power"] = first_existing_column(
        df,
        [
            "Maximale thermische Leistung (in kW)",
            "Maximale_thermische_Leistung_kW",
        ],
    )

    columns["temperature"] = first_existing_column(
        df,
        [
            "Durchschnittliches Temperaturniveau (in °C)",
            "Durchschnittliches_Temperaturniveau_C",
        ],
    )

    columns["temp_range"] = first_existing_column(
        df,
        [
            "Temperaturbereich",
        ],
    )

    columns["source_class"] = first_existing_column(
        df,
        [
            "Quellklasse_Code",
        ],
        required=True,
        label="Quellklasse_Code",
    )

    columns["source_class_label"] = first_existing_column(
        df,
        [
            "Quellklasse",
        ],
    )

    columns["extra"] = first_existing_column(
        df,
        [
            "Ergänzende Informationen zum Abwärmepotential",
        ],
    )

    columns["notes"] = first_existing_column(
        df,
        [
            "Weitere Hinweise",
        ],
    )

    columns["profile_wz"] = first_existing_column(
        df,
        [
            "Gruppen_Profil_WZ_Code",
            "Profil_WZ_Final_Code",
        ],
    )

    columns["wz3"] = first_existing_column(
        df,
        [
            "Gruppen_WZ3_Code",
            "Profil_WZ3_Code",
        ],
    )

    # -------------------------------------------------------------------------
    # Verfügbarkeit
    # -------------------------------------------------------------------------

    columns["availability"] = first_existing_column(
        df,
        [
            "Verfügbarkeit",
            "Verfuegbarkeit",
        ],
    )

    if columns["availability"] is None:

        columns["availability"] = find_column_by_keywords(
            df,
            include_all=[
                "verfugbarkeit",
            ],
            exclude_any=[
                "wochenende",
                "vorhersagbarkeit",
                "tagl",
                "taegl",
            ],
        )

    columns["daily_availability"] = find_column_by_keywords(
        df,
        include_all=[
            "verfugbarkeit",
        ],
        include_any=[
            "tagl",
            "taegl",
            "tagliche",
        ],
        exclude_any=[
            "wochenende",
        ],
    )

    columns["weekend"] = find_column_by_keywords(
        df,
        include_all=[
            "verfugbarkeit",
            "wochenende",
        ],
    )

    columns["predictability"] = find_column_by_keywords(
        df,
        include_any=[
            "vorhersagbarkeit",
            "vorhersehbarkeit",
        ],
    )

    columns["regulation"] = find_column_by_keywords(
        df,
        include_any=[
            "regelungsmoglichkeiten",
            "regelungsmoeglichkeiten",
            "regelbarkeit",
        ],
    )

    # -------------------------------------------------------------------------
    # Monats-Leistungsprofile
    # -------------------------------------------------------------------------

    month_columns = {}

    for month_code, aliases in MONTHS:

        found = None

        for column in df.columns:

            normalized = normalize_header(
                column
            )

            if (
                    "leistungsprofil"
                    not in normalized
            ):
                continue

            if any(
                    normalize_header(alias)
                    in normalized
                    for alias
                    in aliases
            ):
                found = column
                break

        month_columns[
            month_code
        ] = found

    columns["months"] = month_columns

    return columns


# =============================================================================
# 6. REVIEW-DATEIEN
# =============================================================================

def load_review_table(
        group_id,
):
    """Lädt ausschließlich die fertig geprüfte Datei."""

    path = (
            REVIEW_DIR
            / REVIEW_FILE_TEMPLATE.format(
        group_id=group_id
    )
    )

    if not path.exists():
        return None, path

    review = pd.read_excel(
        path,
        sheet_name="Prueffaelle",
        dtype=str,
        keep_default_na=False,
    )

    return review, path

def validate_review(
        group_id,
        review,
):
    """
    Strenge, nachvollziehbare Prüfung der manuellen Bearbeitung.
    """

    if review is None:
        return []

    required = [
        "Originaldatensatz_ID",
        "Pruefstatus",
        "Korrigierte_Waermemenge_kWh_a",
        "Korrigierte_Leistung_kW",
        "Korrigierte_Temperatur_C",
        "Ausschlussgrund",
        "Pruefbegruendung",
    ]

    missing = [
        column
        for column
        in required
        if column not in review.columns
    ]

    if missing:

        raise ValueError(
            f"{group_id}: In der Prüfdatei fehlen Spalten:\n"
            + "\n".join(
                missing
            )
        )

    errors = []

    allowed = {
        "BESTAETIGT",
        "KORRIGIERT",
        "AUSSCHLIESSEN",
        "OFFEN",
    }

    for index, row in review.iterrows():

        original_id = clean_string(
            row["Originaldatensatz_ID"]
        )

        status = (
            clean_string(
                row["Pruefstatus"]
            )
            .upper()
        )

        if status not in allowed:

            errors.append(
                f"ID {original_id}: ungültiger Pruefstatus '{status}'."
            )

            continue

        corrected_fields = [
            clean_string(
                row[
                    "Korrigierte_Waermemenge_kWh_a"
                ]
            ),
            clean_string(
                row[
                    "Korrigierte_Leistung_kW"
                ]
            ),
            clean_string(
                row[
                    "Korrigierte_Temperatur_C"
                ]
            ),
        ]

        if (
                status == "OFFEN"
                and
                STRICT_REVIEW_COMPLETE
        ):

            errors.append(
                f"ID {original_id}: Pruefstatus ist noch OFFEN."
            )

        if (
                status == "KORRIGIERT"
                and
                not any(
                    corrected_fields
                )
        ):

            errors.append(
                f"ID {original_id}: KORRIGIERT, aber kein "
                "Korrekturwert eingetragen."
            )

        if (
                status == "AUSSCHLIESSEN"
                and
                not clean_string(
                    row[
                        "Ausschlussgrund"
                    ]
                )
        ):

            errors.append(
                f"ID {original_id}: AUSSCHLIESSEN ohne Ausschlussgrund."
            )

        if (
                status in {
            "KORRIGIERT",
            "AUSSCHLIESSEN",
        }
                and
                not clean_string(
                    row[
                        "Pruefbegruendung"
                    ]
                )
        ):

            errors.append(
                f"ID {original_id}: {status} ohne Pruefbegruendung."
            )

    return errors


# =============================================================================
# 7. KORREKTUREN ANWENDEN
# =============================================================================

def classify_exclusion_effect(
        decision_row,
):
    """
    Explizite Angabe in optionaler Spalte Ausschluss_Effekt hat Vorrang.

    Sonst gilt:
        Duplikat / kein eigenständiges Potential -> PHYSISCH_ENTFERNEN
        jeder andere Ausschluss                  -> UNAUFGELOEST_WIE_QX
    """

    explicit = ""

    if "Ausschluss_Effekt" in decision_row.index:
        explicit = clean_string(
            decision_row["Ausschluss_Effekt"]
        ).upper()

    if explicit in {
        EXCLUSION_EFFECT_UNRESOLVED,
        EXCLUSION_EFFECT_REMOVE,
    }:
        return explicit, "EXPLIZIT"

    text = (
            clean_string(
                decision_row.get("Ausschlussgrund", "")
            )
            + " "
            + clean_string(
        decision_row.get("Pruefbegruendung", "")
    )
    ).casefold()

    if any(
            keyword in text
            for keyword in PHYSICAL_REMOVAL_KEYWORDS
    ):
        return (
            EXCLUSION_EFFECT_REMOVE,
            "AUTOMATISCH_DUPLIKAT_ODER_NICHT_EIGENSTAENDIG",
        )

    return (
        EXCLUSION_EFFECT_UNRESOLVED,
        "STANDARD_AUSSCHLUSS_WIE_QX",
    )


def apply_review(
        group_id,
        potentials,
        review,
        columns,
):
    """
    Originalwerte werden niemals überschrieben.

    AUSSCHLIESSEN wird zusätzlich in zwei methodische Effekte aufgeteilt:
      - UNAUFGELOEST_WIE_QX
      - PHYSISCH_ENTFERNEN
    """

    work = potentials.copy()

    id_column = columns["id"]

    work["_Original_ID"] = (
        work[id_column]
        .map(clean_string)
    )

    if not work["_Original_ID"].is_unique:
        raise ValueError(
            f"{group_id}: Originaldatensatz_ID ist in Abwaermepotentiale nicht eindeutig."
        )

    work["Waermemenge_original_kWh_a"] = numeric_series(
        work[columns["heat"]]
    )

    if columns["power"]:
        work["Leistung_original_kW"] = numeric_series(
            work[columns["power"]]
        )
    else:
        work["Leistung_original_kW"] = np.nan

    if columns["temperature"]:
        work["Temperatur_original_C"] = numeric_series(
            work[columns["temperature"]]
        )
    else:
        work["Temperatur_original_C"] = np.nan

    work["Waermemenge_final_kWh_a"] = work["Waermemenge_original_kWh_a"]
    work["Leistung_final_kW"] = work["Leistung_original_kW"]
    work["Temperatur_final_C"] = work["Temperatur_original_C"]

    work["Pruefstatus_final"] = "NICHT_PRUEFFALL"
    work["Ausgeschlossen_final"] = False
    work["Ausschluss_Effekt"] = ""
    work["Ausschluss_Effekt_Herkunft"] = ""

    work["Korrektur_Waermemenge"] = False
    work["Korrektur_Leistung"] = False
    work["Korrektur_Temperatur"] = False

    work["Ausschlussgrund_final"] = ""
    work["Pruefbegruendung_final"] = ""
    work["Begruendungsgrundlage_final"] = ""

    if review is None:
        return work

    review = review.copy()
    review["_Original_ID"] = review["Originaldatensatz_ID"].map(clean_string)

    if not review["_Original_ID"].is_unique:
        raise ValueError(
            f"{group_id}: doppelte Originaldatensatz_ID in Prueffaelle."
        )

    unknown_ids = set(review["_Original_ID"]) - set(work["_Original_ID"])
    if unknown_ids:
        raise ValueError(
            f"{group_id}: Prüfdatei enthält unbekannte IDs:\n"
            + "\n".join(sorted(unknown_ids)[:30])
        )

    review_map = review.set_index("_Original_ID")

    for row_index, row in work.iterrows():
        original_id = row["_Original_ID"]

        if original_id not in review_map.index:
            continue

        decision = review_map.loc[original_id]
        status = clean_string(decision["Pruefstatus"]).upper()

        work.at[row_index, "Pruefstatus_final"] = status
        work.at[row_index, "Ausschlussgrund_final"] = clean_string(
            decision.get("Ausschlussgrund", "")
        )
        work.at[row_index, "Pruefbegruendung_final"] = clean_string(
            decision.get("Pruefbegruendung", "")
        )
        work.at[row_index, "Begruendungsgrundlage_final"] = clean_string(
            decision.get("Begruendungsgrundlage", "")
        )

        if status == "AUSSCHLIESSEN":
            effect, source = classify_exclusion_effect(decision)
            work.at[row_index, "Ausgeschlossen_final"] = True
            work.at[row_index, "Ausschluss_Effekt"] = effect
            work.at[row_index, "Ausschluss_Effekt_Herkunft"] = source
            continue

        if status != "KORRIGIERT":
            continue

        corrected_heat = numeric_value(
            decision["Korrigierte_Waermemenge_kWh_a"]
        )
        corrected_power = numeric_value(
            decision["Korrigierte_Leistung_kW"]
        )
        corrected_temperature = numeric_value(
            decision["Korrigierte_Temperatur_C"]
        )

        if pd.notna(corrected_heat):
            work.at[row_index, "Waermemenge_final_kWh_a"] = corrected_heat
            work.at[row_index, "Korrektur_Waermemenge"] = True

        if pd.notna(corrected_power):
            work.at[row_index, "Leistung_final_kW"] = corrected_power
            work.at[row_index, "Korrektur_Leistung"] = True

        if pd.notna(corrected_temperature):
            work.at[row_index, "Temperatur_final_C"] = corrected_temperature
            work.at[row_index, "Korrektur_Temperatur"] = True

    return work

def parse_yes_no(
        value,
):
    text = (
        clean_string(
            value
        )
        .casefold()
    )

    if text in {
        "ja",
        "yes",
        "j",
        "1",
        "true",
        "wahr",
    }:
        return True

    if text in {
        "nein",
        "no",
        "n",
        "0",
        "false",
        "falsch",
    }:
        return False

    return None


def parse_structured_availability(
        value,
):
    """
    Erkennt z. B.:

        5 Tage 8 Std
        5 Tage 24 Std
        7 Tage 24 Std

    Gibt:
        (days_per_week, hours_per_day)
    """

    text = normalize_header(
        value
    )

    if not text:
        return None, None

    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*tage?\s*(\d+(?:[.,]\d+)?)\s*(?:std|stunden|h)",
        text,
    )

    if not match:
        return None, None

    days = numeric_value(
        match.group(1)
    )

    hours = numeric_value(
        match.group(2)
    )

    return days, hours


def standardize_daily_hours(
        hours,
):
    """
    Standardraster bleibt bestehen:
        8 / 12 / 16 / 20 / 24 h

    Nur wenn der Wert gar nicht sinnvoll in dieses Raster passt (<6 h),
    bleibt er als exaktes Sonderprofil erhalten.
    """

    if pd.isna(hours):
        return {
            "standard_hours": np.nan,
            "effective_hours": np.nan,
            "status": "UNBEKANNT",
            "is_special": False,
        }

    hours = float(hours)

    if hours <= 0 or hours > MAX_DAILY_HOURS + 0.5:
        return {
            "standard_hours": np.nan,
            "effective_hours": np.nan,
            "status": "UNPLAUSIBEL",
            "is_special": False,
        }

    if hours < MIN_HOURS_FOR_STANDARDIZATION:
        return {
            "standard_hours": np.nan,
            "effective_hours": hours,
            "status": "EXAKT_SONDERPROFIL",
            "is_special": True,
        }

    if hours < 10:
        standard = 8.0
    elif hours < 14:
        standard = 12.0
    elif hours < 18:
        standard = 16.0
    elif hours < 22:
        standard = 20.0
    else:
        standard = 24.0

    return {
        "standard_hours": standard,
        "effective_hours": standard,
        "status": "STANDARDISIERT",
        "is_special": False,
    }

def format_number_for_profile(value):
    if pd.isna(value):
        return ""

    rounded = round(float(value), 2)

    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))

    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def derive_operating_profile(
        row,
        columns,
):
    """
    Priorität:
      1. strukturierte Angabe in Verfügbarkeit
      2. tägliche Stunden + Wochenende

    Standardprofile werden beibehalten. Nur echte Sonderfälle bleiben exakt.
    """

    availability_raw = ""
    if columns["availability"]:
        availability_raw = clean_string(row[columns["availability"]])

    daily_raw = np.nan
    if columns["daily_availability"]:
        daily_raw = numeric_value(row[columns["daily_availability"]])

    weekend_raw = ""
    weekend_bool = None
    if columns["weekend"]:
        weekend_raw = clean_string(row[columns["weekend"]])
        weekend_bool = parse_yes_no(weekend_raw)

    structured_days, structured_hours = parse_structured_availability(
        availability_raw
    )

    source = ""
    days = np.nan
    hours = np.nan

    if pd.notna(structured_days) and pd.notna(structured_hours):
        days = float(structured_days)
        hours = float(structured_hours)
        source = "VERFUEGBARKEIT_TEXT"

    elif pd.notna(daily_raw) and daily_raw > 0:
        hours = float(daily_raw)

        if weekend_bool is True:
            days = 7.0
        elif weekend_bool is False:
            days = 5.0

        source = "TAGLICH_PLUS_WOCHENENDE"

    standardized = standardize_daily_hours(hours)

    standard_hours = standardized["standard_hours"]
    effective_hours = standardized["effective_hours"]
    hour_status = standardized["status"]
    special_hour = standardized["is_special"]

    standard_days = np.nan
    effective_days = np.nan
    day_status = "UNBEKANNT"
    special_day = False

    if pd.notna(days):
        rounded_days = round(float(days), 2)
        nearest_integer = int(round(rounded_days))

        if (
                abs(rounded_days - nearest_integer) < 0.01
                and nearest_integer in STANDARD_DAYS_PER_WEEK
        ):
            standard_days = float(nearest_integer)
            effective_days = float(nearest_integer)
            day_status = "STANDARD"

        elif 0 < rounded_days <= 7:
            effective_days = rounded_days
            day_status = "EXAKT_SONDERPROFIL"
            special_day = True

        else:
            day_status = "UNPLAUSIBEL"

    profile_code = "BP_UNBEKANNT"
    profile_quality = "UNBEKANNT"

    if pd.notna(standard_hours) and pd.notna(standard_days):
        profile_code = f"BP_{int(standard_hours)}x{int(standard_days)}"
        profile_quality = "STANDARD"

    elif (
            pd.notna(effective_hours)
            and pd.notna(effective_days)
            and (special_hour or special_day)
    ):
        profile_code = (
            "BP_EXAKT_"
            f"{format_number_for_profile(effective_hours)}"
            "x"
            f"{format_number_for_profile(effective_days)}"
        )
        profile_quality = "EXAKT_SONDERPROFIL"

    elif pd.notna(hours) or pd.notna(days):
        profile_code = "BP_UNBEKANNT"
        profile_quality = f"{hour_status}|{day_status}"

    return {
        "Betriebsprofil_Roh_Verfuegbarkeit": availability_raw,
        "Betriebsprofil_Roh_h_pro_Tag": daily_raw,
        "Betriebsprofil_Roh_Wochenende": weekend_raw,
        "Betriebsprofil_Abgeleitet_h_pro_Tag": hours,
        "Betriebsprofil_Abgeleitet_Tage_pro_Woche": days,
        "Betriebsprofil_Standard_h_pro_Tag": standard_hours,
        "Betriebsprofil_Standard_Tage_pro_Woche": standard_days,
        "Betriebsprofil_Generator_h_pro_Tag": effective_hours,
        "Betriebsprofil_Generator_Tage_pro_Woche": effective_days,
        "Betriebsprofil_Code": profile_code,
        "Betriebsprofil_Herkunft": source,
        "Betriebsprofil_Qualitaet": profile_quality,
    }


def derive_seasonality(
        row,
        columns,
):
    """
    Leitet aus den 12 Monats-Leistungsprofilen ausschließlich die relative
    Jahresform ab.

    Neu in Iteration 3:
      - Anzahl aktive Monate
      - HHI-Konzentration
      - normierte Konzentration 0..1

    Der vollständige 12-Monats-Vektor bleibt weiterhin die eigentliche
    Saisoninformation.
    """

    month_columns = columns[
        "months"
    ]

    raw_values = {}

    for month_code, _ in MONTHS:
        column = month_columns.get(
            month_code
        )

        raw_values[
            month_code
        ] = (
            numeric_value(
                row[
                    column
                ]
            )
            if column
            else np.nan
        )

    count_present = sum(
        pd.notna(
            value
        )
        for value
        in raw_values.values()
    )

    count_zero = sum(
        (
                pd.notna(
                    value
                )
                and
                value == 0
        )
        for value
        in raw_values.values()
    )

    active_months = sum(
        (
                pd.notna(
                    value
                )
                and
                value > 0
        )
        for value
        in raw_values.values()
    )

    positive_sum = sum(
        value
        for value
        in raw_values.values()
        if (
                pd.notna(
                    value
                )
                and
                value > 0
        )
    )

    if REQUIRE_ALL_12_MONTHS_FOR_SEASONALITY:
        valid = (
                count_present == 12
                and
                positive_sum > 0
        )
    else:
        valid = (
                count_present >= 10
                and
                positive_sum > 0
        )

    result = {
        "Saison_Monate_vorhanden":
            count_present,

        "Saison_Nullmonate":
            count_zero,

        "Saison_Aktive_Monate":
            active_months,

        "Saison_Profil_gueltig":
            bool(
                valid
            ),

        "Saisonfaktor_Sommer":
            np.nan,

        "Saisonfaktor_Winter":
            np.nan,

        "Saison_Konzentration_HHI":
            np.nan,

        "Saison_Konzentration_0_1":
            np.nan,

        # Alt-Kompatibilität für ältere Diagnosefunktionen.
        "Saison_Signatur":
            "SAISON_UNBEKANNT",
    }

    for month_code, _ in MONTHS:
        result[
            f"Saison_Roh_{month_code}"
        ] = raw_values[
            month_code
        ]

        result[
            f"Saison_Faktor_{month_code}"
        ] = np.nan

    if not valid:
        return result

    total_hours = sum(
        MONTH_HOURS.values()
    )

    total_weighted = sum(
        raw_values[
            month
        ]
        *
        MONTH_HOURS[
            month
        ]
        for month, _
        in MONTHS
    )

    annual_mean = (
            total_weighted
            /
            total_hours
    )

    if (
            pd.isna(
                annual_mean
            )
            or
            annual_mean <= 0
    ):
        result[
            "Saison_Profil_gueltig"
        ] = False

        return result

    factors = {}

    for month_code, _ in MONTHS:
        factor = (
                raw_values[
                    month_code
                ]
                /
                annual_mean
        )

        factors[
            month_code
        ] = factor

        result[
            f"Saison_Faktor_{month_code}"
        ] = factor

    summer_hours = sum(
        MONTH_HOURS[
            month
        ]
        for month
        in SUMMER_MONTHS
    )

    result[
        "Saisonfaktor_Sommer"
    ] = (
            sum(
                factors[
                    month
                ]
                *
                MONTH_HOURS[
                    month
                ]
                for month
                in SUMMER_MONTHS
            )
            /
            summer_hours
    )

    winter_hours = sum(
        MONTH_HOURS[
            month
        ]
        for month
        in WINTER_MONTHS
    )

    result[
        "Saisonfaktor_Winter"
    ] = (
            sum(
                factors[
                    month
                ]
                *
                MONTH_HOURS[
                    month
                ]
                for month
                in WINTER_MONTHS
            )
            /
            winter_hours
    )

    # Monatsenergieanteile aus relativem Monatsfaktor * Kalenderstunden.
    monthly_energy_proxy = {
        month:
            factors[
                month
            ]
            *
            MONTH_HOURS[
                month
            ]
        for month, _
        in MONTHS
    }

    proxy_sum = sum(
        monthly_energy_proxy.values()
    )

    shares = {
        month:
            monthly_energy_proxy[
                month
            ]
            /
            proxy_sum
        for month, _
        in MONTHS
    }

    hhi = sum(
        share ** 2
        for share
        in shares.values()
    )

    # Referenz einer zeitlich flachen Quelle:
    # Monatsanteile unterscheiden sich nur wegen Monatslängen.
    flat_shares = {
        month:
            MONTH_HOURS[
                month
            ]
            /
            total_hours
        for month, _
        in MONTHS
    }

    hhi_flat = sum(
        share ** 2
        for share
        in flat_shares.values()
    )

    concentration_01 = safe_divide(
        hhi - hhi_flat,
        1.0 - hhi_flat,
        )

    if pd.notna(
            concentration_01
    ):
        concentration_01 = max(
            0.0,
            min(
                1.0,
                concentration_01,
            ),
        )

    result[
        "Saison_Konzentration_HHI"
    ] = hhi

    result[
        "Saison_Konzentration_0_1"
    ] = concentration_01

    signature_parts = [
        f"{month}:"
        f"{round(factors[month], SEASON_SIGNATURE_DECIMALS):.{SEASON_SIGNATURE_DECIMALS}f}"
        for month, _
        in MONTHS
    ]

    result[
        "Saison_Signatur"
    ] = "|".join(
        signature_parts
    )

    return result

def temperature_class(
        temperature,
):
    if pd.isna(
            temperature
    ):
        return "T_UNBEKANNT"

    if temperature < 25:
        return "T_LT25"

    if temperature < 60:
        return "T_25_60"

    if temperature < 90:
        return "T_60_90"

    if temperature < 110:
        return "T_90_110"

    return "T_GE110"



def assign_temperature_subclusters(
        group,
        max_span_c=AGGREGATION_MAX_TEMPERATURE_SPAN_C,
):
    """
    Bildet innerhalb einer sonst technisch gleichen Gruppe Cluster mit
    maximaler Temperaturspanne max_span_c.
    """

    result = pd.Series(
        index=group.index,
        dtype="object",
    )

    missing = group[
        group[
            "Temperatur_final_C"
        ].isna()
    ]

    if not missing.empty:
        result.loc[
            missing.index
        ] = "TEMP_MISSING"

    numeric = group[
        group[
            "Temperatur_final_C"
        ].notna()
    ].copy()

    if numeric.empty:
        return result

    numeric = numeric.sort_values(
        "Temperatur_final_C",
        kind="stable",
    )

    cluster_number = 1
    cluster_min = None

    for row_index, row in numeric.iterrows():

        temperature = float(
            row[
                "Temperatur_final_C"
            ]
        )

        if cluster_min is None:
            cluster_min = temperature

        elif (
                temperature
                -
                cluster_min
                >
                max_span_c
        ):
            cluster_number += 1
            cluster_min = temperature

        result.loc[
            row_index
        ] = (
            f"TCL_{cluster_number:02d}"
        )

    return result

def normalize_source_family(
        value,
):
    """
    Vorsichtige Namensnormalisierung.

    Warum überhaupt?
    ----------------
    Ohne Normalisierung würden z. B.

        Kompressor 1
        Kompressor 2
        Kompressor 3

    als drei völlig verschiedene Maschinenfamilien erscheinen, obwohl sie
    technisch häufig dieselbe Familie repräsentieren. Für Aggregation und
    Donor-Suche ist das unnötig restriktiv.

    ABER:
    Technische Größen dürfen nicht verloren gehen. Deshalb werden NICHT mehr
    pauschal alle Zahlen ersetzt.

    Beispiele:
        Kompressor 1      -> kompressor <id>
        Kompressor 2      -> kompressor <id>
        GT1               -> gt<id>
        GT2               -> gt<id>
        RLT01             -> rlt<id>

    dagegen:
        Kompressor 500 kW -> kompressor 500 kw
        DN100             -> dn100
        PN16              -> pn16
    """

    text = clean_string(
        value
    )

    if not text:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        text,
    ).casefold()

    text = (
        text
        .replace("°", " °")
        .replace("/", " / ")
        .replace("-", " ")
        .replace("_", " ")
    )

    tokens = re.findall(
        r"[a-zäöüß]+[0-9]+|[a-zäöüß]+|[0-9]+(?:[.,][0-9]+)?|°c|[^\s]+",
        text,
    )

    normalized = []

    for index, token in enumerate(
            tokens
    ):
        token_clean = token.strip()

        # Alphanumerischer Anlagen-/Technikcode.
        match = re.fullmatch(
            r"([a-zäöüß]+)([0-9]+)",
            token_clean,
        )

        if match:
            prefix = match.group(1)

            if prefix in TECHNICAL_CODE_PREFIXES:
                normalized.append(
                    token_clean
                )
            else:
                normalized.append(
                    f"{prefix}<id>"
                )

            continue

        # Reine Zahl.
        if re.fullmatch(
                r"[0-9]+(?:[.,][0-9]+)?",
                token_clean,
        ):
            previous = (
                normalized[-1]
                if normalized
                else ""
            )

            next_token = (
                tokens[index + 1].casefold()
                if index + 1 < len(tokens)
                else ""
            )

            # Technische Größe beibehalten.
            if next_token in TECHNICAL_UNIT_TOKENS:
                normalized.append(
                    token_clean
                )
                continue

            # Laufende Nummer nach typischem Maschinenwort abstrahieren.
            if previous in ID_PRECEDERS:
                normalized.append(
                    "<id>"
                )
                continue

            normalized.append(
                token_clean
            )

            continue

        normalized.append(
            token_clean
        )

    text = " ".join(
        normalized
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def enrich_cleaned_potentials(
        group_id,
        work,
        columns,
):
    """Erzeugt die Generator-relevanten Merkmale je Originalpotential."""

    enriched = work.copy()

    enriched["Experiment_Gruppe"] = group_id
    enriched["Standortverbund_ID_final"] = enriched[columns["site"]].map(clean_string)
    enriched["Quellklasse_final"] = enriched[columns["source_class"]].map(clean_string).str.upper()
    enriched["Quellenname_final"] = enriched[columns["name"]].map(clean_string)
    enriched["Quellenfamilie_normalisiert"] = enriched["Quellenname_final"].map(normalize_source_family)
    enriched["Temperaturklasse_final"] = enriched["Temperatur_final_C"].map(temperature_class)

    operating_records = []
    seasonal_records = []

    for _, row in enriched.iterrows():
        operating_records.append(
            derive_operating_profile(
                row,
                columns,
            )
        )

        seasonal_records.append(
            derive_seasonality(
                row,
                columns,
            )
        )

    enriched = pd.concat(
        [
            enriched,
            pd.DataFrame(
                operating_records,
                index=enriched.index,
            ),
            pd.DataFrame(
                seasonal_records,
                index=enriched.index,
            ),
        ],
        axis=1,
    )

    # Ausgangszustand für spätere Nachvollziehbarkeit.
    enriched[
        "Betriebsprofil_Code_original_abgeleitet"
    ] = enriched[
        "Betriebsprofil_Code"
    ]

    enriched[
        "Betriebsprofil_deterministisch_ergaenzt"
    ] = False

    enriched[
        "Betriebsprofil_Ergaenzungsgrund"
    ] = ""

    enriched[
        "Betriebsprofil_Donor_Originaldatensatz_IDs"
    ] = ""

    if columns["predictability"]:
        enriched[
            "Vorhersagbarkeit_raw"
        ] = enriched[
            columns["predictability"]
        ].map(clean_string)
    else:
        enriched[
            "Vorhersagbarkeit_raw"
        ] = ""

    if columns["regulation"]:
        enriched[
            "Regelungsmoeglichkeiten_raw"
        ] = enriched[
            columns["regulation"]
        ].map(clean_string)
    else:
        enriched[
            "Regelungsmoeglichkeiten_raw"
        ] = ""

    if columns["profile_wz"]:
        enriched[
            "Profil_WZ_Code_final"
        ] = enriched[
            columns["profile_wz"]
        ].map(clean_string)
    else:
        enriched[
            "Profil_WZ_Code_final"
        ] = ""

    if columns["wz3"]:
        enriched[
            "WZ3_Code_final"
        ] = enriched[
            columns["wz3"]
        ].map(clean_string)
    else:
        enriched[
            "WZ3_Code_final"
        ] = ""

    return enriched


def complete_operating_profiles_strong_donors(
        enriched,
):
    """
    Deterministische Ergänzung NUR bei sehr starker Evidenz:

        gleicher Standort
        + gleiche Q-Klasse
        + gleiche normalisierte Maschinenfamilie
        + mindestens ein bekannter Donor
        + ALLE passenden bekannten Donoren haben dasselbe Betriebsprofil

    Der exakte Profil_WZ_Code ist ausdrücklich KEINE Bedingung.
    """

    work = enriched.copy()

    known = work[
        work[
            "Betriebsprofil_Code"
        ].ne(
            "BP_UNBEKANNT"
        )
        &
        ~work[
            "Ausgeschlossen_final"
        ]
        ].copy()

    missing_indices = work[
        work[
            "Betriebsprofil_Code"
        ].eq(
            "BP_UNBEKANNT"
        )
        &
        ~work[
            "Ausgeschlossen_final"
        ]
        ].index

    for row_index in missing_indices:
        row = work.loc[
            row_index
        ]

        family = clean_string(
            row[
                "Quellenfamilie_normalisiert"
            ]
        )

        if not family:
            continue

        donors = known[
            known[
                "Standortverbund_ID_final"
            ].eq(
                row[
                    "Standortverbund_ID_final"
                ]
            )
            &
            known[
                "Quellklasse_final"
            ].eq(
                row[
                    "Quellklasse_final"
                ]
            )
            &
            known[
                "Quellenfamilie_normalisiert"
            ].eq(
                family
            )
            ].copy()

        if donors.empty:
            continue

        donor_profiles = unique_nonempty(
            donors[
                "Betriebsprofil_Code"
            ]
        )

        if len(
                donor_profiles
        ) != 1:
            continue

        donor_hours = (
            donors[
                "Betriebsprofil_Generator_h_pro_Tag"
            ]
            .dropna()
            .unique()
        )

        donor_days = (
            donors[
                "Betriebsprofil_Generator_Tage_pro_Woche"
            ]
            .dropna()
            .unique()
        )

        if (
                len(
                    donor_hours
                ) != 1
                or
                len(
                    donor_days
                ) != 1
        ):
            continue

        profile_code = donor_profiles[
            0
        ]

        work.at[
            row_index,
            "Betriebsprofil_Code",
        ] = profile_code

        work.at[
            row_index,
            "Betriebsprofil_Generator_h_pro_Tag",
        ] = float(
            donor_hours[
                0
            ]
        )

        work.at[
            row_index,
            "Betriebsprofil_Generator_Tage_pro_Woche",
        ] = float(
            donor_days[
                0
            ]
        )

        match = re.fullmatch(
            r"BP_(8|12|16|20|24)x(5|7)",
            profile_code,
        )

        if match:
            work.at[
                row_index,
                "Betriebsprofil_Standard_h_pro_Tag",
            ] = float(
                match.group(
                    1
                )
            )

            work.at[
                row_index,
                "Betriebsprofil_Standard_Tage_pro_Woche",
            ] = float(
                match.group(
                    2
                )
            )

            work.at[
                row_index,
                "Betriebsprofil_Qualitaet",
            ] = "STANDARD_DETERMINISTISCH_ERGAENZT"

        else:
            work.at[
                row_index,
                "Betriebsprofil_Qualitaet",
            ] = "SONDERPROFIL_DETERMINISTISCH_ERGAENZT"

        work.at[
            row_index,
            "Betriebsprofil_Herkunft",
        ] = "DONOR_GLEICHER_STANDORT_Q_FAMILIE"

        work.at[
            row_index,
            "Betriebsprofil_deterministisch_ergaenzt",
        ] = True

        work.at[
            row_index,
            "Betriebsprofil_Ergaenzungsgrund",
        ] = (
            "Alle bekannten Donoren am gleichen Standort mit gleicher "
            "Q-Klasse und gleicher Maschinenfamilie haben dasselbe "
            f"Betriebsprofil {profile_code}."
        )

        work.at[
            row_index,
            "Betriebsprofil_Donor_Originaldatensatz_IDs",
        ] = " | ".join(
            donors[
                "_Original_ID"
            ].map(
                clean_string
            )
        )

    return work



def build_site_filter(
        enriched,
):
    """
    Finale Standort-Eignung nach manueller Prüfung.

    PHYSISCH_ENTFERNEN:
        zählt nicht im Nenner.

    UNAUFGELOEST_WIE_QX:
        bleibt im Nenner und zählt zum nicht-einordenbaren Anteil.

    Nicht ausgeschlossene Klassen außerhalb Q1-Q7 zählen ebenfalls als
    nicht einordenbar.

    Neu Iteration 3:
        Abstand zur 20%-Grenze + Sensitivkennzeichen ab 15%.
    """

    rows = []

    for site_id, group in enriched.groupby(
            "Standortverbund_ID_final",
            sort=False,
    ):

        physical_present = group[
            ~(
                    group["Ausgeschlossen_final"]
                    &
                    (
                            group["Ausschluss_Effekt"]
                            ==
                            EXCLUSION_EFFECT_REMOVE
                    )
            )
        ].copy()

        unresolved_excluded = physical_present[
            physical_present["Ausgeschlossen_final"]
            &
            (
                    physical_present["Ausschluss_Effekt"]
                    ==
                    EXCLUSION_EFFECT_UNRESOLVED
            )
            ].copy()

        unresolved_without_heat = unresolved_excluded[
            unresolved_excluded[
                "Waermemenge_final_kWh_a"
            ].isna()
            |
            (
                    unresolved_excluded[
                        "Waermemenge_final_kWh_a"
                    ]
                    <= 0
            )
            ]

        positive = physical_present[
            physical_present[
                "Waermemenge_final_kWh_a"
            ].notna()
            &
            (
                    physical_present[
                        "Waermemenge_final_kWh_a"
                    ]
                    > 0
            )
            ].copy()

        total_heat = positive[
            "Waermemenge_final_kWh_a"
        ].sum()

        known_mask = (
                ~positive["Ausgeschlossen_final"]
                &
                positive[
                    "Quellklasse_final"
                ].isin(
                    VALID_SOURCE_CLASSES
                )
        )

        known_heat = positive.loc[
            known_mask,
            "Waermemenge_final_kWh_a",
        ].sum()

        unresolved_mask = (
                (
                        ~positive["Ausgeschlossen_final"]
                        &
                        ~positive[
                            "Quellklasse_final"
                        ].isin(
                            VALID_SOURCE_CLASSES
                        )
                )
                |
                (
                        positive["Ausgeschlossen_final"]
                        &
                        (
                                positive["Ausschluss_Effekt"]
                                ==
                                EXCLUSION_EFFECT_UNRESOLVED
                        )
                )
        )

        unresolved_heat = positive.loc[
            unresolved_mask,
            "Waermemenge_final_kWh_a",
        ].sum()

        unresolved_share = safe_divide(
            unresolved_heat,
            total_heat,
        )

        if len(
                unresolved_without_heat
        ) > 0:
            status = (
                "NICHT_BEURTEILBAR_AUSSCHLUSS_OHNE_WAERMEMENGE"
            )
            suitable = False

        elif (
                pd.isna(
                    unresolved_share
                )
                or
                total_heat <= 0
        ):
            status = (
                "NICHT_BEURTEILBAR_KEINE_POSITIVE_WAERMEMENGE"
            )
            suitable = False

        elif known_heat <= 0:
            status = (
                "NICHT_GEEIGNET_KEINE_Q1_Q7_WAERME"
            )
            suitable = False

        elif (
                unresolved_share
                <=
                QX_HEAT_THRESHOLD
        ):
            status = "GEEIGNET"
            suitable = True

        else:
            status = (
                "NICHT_GEEIGNET_NICHT_EINORDENBAR_UEBER_20PCT"
            )
            suitable = False

        margin = (
            QX_HEAT_THRESHOLD
            -
            unresolved_share
            if pd.notna(
                unresolved_share
            )
            else np.nan
        )

        rows.append(
            {
                "Standortverbund_ID":
                    site_id,

                "Waermemenge_Gesamt_physisch_kWh_a":
                    total_heat,

                "Waermemenge_Q1_Q7_kWh_a":
                    known_heat,

                "Waermemenge_Nicht_einordenbar_kWh_a":
                    unresolved_heat,

                "Nicht_einordenbar_Anteil_Waermemenge_final":
                    unresolved_share,

                "Abstand_zur_QX20_Grenze":
                    margin,

                "QX20_Sensitiv_ab_15pct":
                    bool(
                        pd.notna(
                            unresolved_share
                        )
                        and
                        unresolved_share >= 0.15
                    ),

                "Geeignet_QX20_final":
                    bool(
                        suitable
                    ),

                "Eignungsstatus_final":
                    status,

                "Anzahl_Potentiale_physisch":
                    int(
                        len(
                            physical_present
                        )
                    ),

                "Anzahl_Potentiale_Q1_Q7":
                    int(
                        known_mask.sum()
                    ),

                "Anzahl_Ausschluss_unaufgeloest":
                    int(
                        (
                                group["Ausgeschlossen_final"]
                                &
                                (
                                        group["Ausschluss_Effekt"]
                                        ==
                                        EXCLUSION_EFFECT_UNRESOLVED
                                )
                        ).sum()
                    ),

                "Anzahl_Ausschluss_physisch_entfernt":
                    int(
                        (
                                group["Ausgeschlossen_final"]
                                &
                                (
                                        group["Ausschluss_Effekt"]
                                        ==
                                        EXCLUSION_EFFECT_REMOVE
                                )
                        ).sum()
                    ),

                "Anzahl_unaufgeloest_ohne_Waermemenge":
                    int(
                        len(
                            unresolved_without_heat
                        )
                    ),
            }
        )

    result = pd.DataFrame(
        rows
    )

    if result.empty:
        return result

    return (
        result
        .sort_values(
            [
                "Geeignet_QX20_final",
                "Waermemenge_Gesamt_physisch_kWh_a",
            ],
            ascending=[
                False,
                False,
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
    )


def prepare_aggregation_keys(
        generator_sources,
        max_span_c=AGGREGATION_MAX_TEMPERATURE_SPAN_C,
        key_column="_Aggregation_Key",
):
    """
    Aggregationsbasis:
      Standort + Q + Quellenfamilie + Betriebsprofil + Temperaturcluster.

    Saisonalität ist ausdrücklich KEIN Schlüssel.

    Profil_WZ_Code ist ausdrücklich KEINE Modell-/Aggregationsbedingung.
    """

    work = generator_sources.copy()

    if not AGGREGATE_EMPTY_SOURCE_NAMES:
        empty_family = work[
            "Quellenfamilie_normalisiert"
        ].eq("")

        work.loc[
            empty_family,
            "Quellenfamilie_normalisiert",
        ] = (
                "UNIQUE::"
                +
                work.loc[
                    empty_family,
                    "_Original_ID",
                ]
        )

    temp_cluster_column = (
        f"_Temp_Subcluster_{key_column}"
    )

    work[
        temp_cluster_column
    ] = ""

    base_columns = [
        "Standortverbund_ID_final",
        "Quellklasse_final",
        "Quellenfamilie_normalisiert",
        "Betriebsprofil_Code",
    ]

    for _, group in work.groupby(
            base_columns,
            sort=False,
            dropna=False,
    ):
        clusters = assign_temperature_subclusters(
            group,
            max_span_c=max_span_c,
        )

        work.loc[
            clusters.index,
            temp_cluster_column,
        ] = clusters

    work[
        key_column
    ] = work.apply(
        lambda row:
        (
            clean_string(
                row[
                    "Standortverbund_ID_final"
                ]
            ),
            clean_string(
                row[
                    "Quellklasse_final"
                ]
            ),
            clean_string(
                row[
                    "Quellenfamilie_normalisiert"
                ]
            ),
            clean_string(
                row[
                    "Betriebsprofil_Code"
                ]
            ),
            clean_string(
                row[
                    temp_cluster_column
                ]
            ),
        ),
        axis=1,
    )

    return work

def weighted_mean(
        values,
        weights,
):
    values = np.asarray(
        values,
        dtype=float,
    )

    weights = np.asarray(
        weights,
        dtype=float,
    )

    valid = (
            np.isfinite(
                values
            )
            &
            np.isfinite(
                weights
            )
            &
            (
                    weights > 0
            )
    )

    if not valid.any():
        return np.nan

    return float(
        np.average(
            values[
                valid
            ],
            weights=weights[
                valid
            ],
        )
    )


def weighted_quantile(
        values,
        weights,
        quantile,
):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)

    valid = (
            np.isfinite(values)
            & np.isfinite(weights)
            & (weights > 0)
    )

    values = values[valid]
    weights = weights[valid]

    if len(values) == 0:
        return np.nan

    order = np.argsort(values)
    values = values[order]
    weights = weights[order]

    cumulative = np.cumsum(weights)
    cutoff = quantile * cumulative[-1]
    index = np.searchsorted(cumulative, cutoff, side="left")
    index = min(index, len(values) - 1)

    return float(values[index])



def build_source_blocks(
        group_id,
        enriched,
        site_filter,
):
    """
    Bildet Generator-Quellenblöcke nur aus:
      - final geeigneten Standorten
      - nicht ausgeschlossenen Quellen
      - Q1-Q7
      - positiver Jahreswärmemenge

    Produktive Aggregation:
      - gleiche Standort-ID
      - gleiche Q-Klasse
      - gleiche normalisierte Quellenfamilie
      - gleiches Betriebsprofil
      - Temperaturspanne maximal 5 K

    Saisonalität wird innerhalb eines Blocks wärmemengengewichtet aggregiert.
    """

    suitable_sites = set(
        site_filter.loc[
            site_filter[
                "Geeignet_QX20_final"
            ],
            "Standortverbund_ID",
        ]
    )

    generator_sources = enriched[
        enriched[
            "Standortverbund_ID_final"
        ].isin(
            suitable_sites
        )
        &
        ~enriched[
            "Ausgeschlossen_final"
        ]
        &
        enriched[
            "Quellklasse_final"
        ].isin(
            VALID_SOURCE_CLASSES
        )
        &
        enriched[
            "Waermemenge_final_kWh_a"
        ].notna()
        &
        (
                enriched[
                    "Waermemenge_final_kWh_a"
                ]
                > 0
        )
        ].copy()

    if generator_sources.empty:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            generator_sources,
        )

    if ENABLE_SOURCE_BLOCK_AGGREGATION:
        generator_sources = prepare_aggregation_keys(
            generator_sources,
            max_span_c=
            AGGREGATION_MAX_TEMPERATURE_SPAN_C,
            key_column=
            "_Aggregation_Key",
        )
    else:
        generator_sources[
            "_Aggregation_Key"
        ] = generator_sources[
            "_Original_ID"
        ].map(
            lambda value:
            (
                "UNIQUE",
                value,
            )
        )

    block_rows = []
    mapping_rows = []

    for _, group in generator_sources.groupby(
            "_Aggregation_Key",
            sort=False,
    ):
        source_ids = sorted(
            group[
                "_Original_ID"
            ].map(
                clean_string
            )
        )

        site_id = clean_string(
            group[
                "Standortverbund_ID_final"
            ].iloc[
                0
            ]
        )

        q_code = clean_string(
            group[
                "Quellklasse_final"
            ].iloc[
                0
            ]
        )

        block_id = deterministic_id(
            "GB",
            [
                group_id,
                site_id,
                q_code,
                "||".join(
                    source_ids
                ),
            ],
        )

        heat = group[
            "Waermemenge_final_kWh_a"
        ].sum()

        power_values = group[
            "Leistung_final_kW"
        ].dropna()

        diagnostic_power_sum = (
            float(
                power_values.sum()
            )
            if not power_values.empty
            else np.nan
        )

        temperature = weighted_mean(
            group[
                "Temperatur_final_C"
            ],
            group[
                "Waermemenge_final_kWh_a"
            ],
        )

        temperature_values = group[
            "Temperatur_final_C"
        ].dropna()

        temperature_span = (
            float(
                temperature_values.max()
                -
                temperature_values.min()
            )
            if not temperature_values.empty
            else np.nan
        )

        valid_season = group[
            group[
                "Saison_Profil_gueltig"
            ]
        ].copy()

        valid_season_heat = valid_season[
            "Waermemenge_final_kWh_a"
        ].sum()

        season_coverage_heat = safe_divide(
            valid_season_heat,
            heat,
        )

        season_complete = (
                pd.notna(
                    season_coverage_heat
                )
                and
                season_coverage_heat
                >=
                0.999999
        )

        month_factors = {}

        for month, _ in MONTHS:
            month_factors[
                month
            ] = (
                weighted_mean(
                    valid_season[
                        f"Saison_Faktor_{month}"
                    ],
                    valid_season[
                        "Waermemenge_final_kWh_a"
                    ],
                )
                if not valid_season.empty
                else np.nan
            )

        def season_weighted(
                column,
        ):
            if valid_season.empty:
                return np.nan

            return weighted_mean(
                valid_season[
                    column
                ],
                valid_season[
                    "Waermemenge_final_kWh_a"
                ],
            )

        row = {
            "Experiment_Gruppe":
                group_id,

            "Generator_Block_ID":
                block_id,

            "Standortverbund_ID":
                site_id,

            # Nur Rückverfolgbarkeit. KEINE Donor-/Ziehbedingung.
            "Profil_WZ_Code":
                " | ".join(
                    unique_nonempty(
                        group[
                            "Profil_WZ_Code_final"
                        ]
                    )
                ),

            "WZ3_Code":
                " | ".join(
                    unique_nonempty(
                        group[
                            "WZ3_Code_final"
                        ]
                    )
                ),

            "Quellklasse_Code":
                q_code,

            "Waermemenge_Block_kWh_a":
                heat,

            "Anzahl_Originalpotentiale":
                int(
                    len(
                        group
                    )
                ),

            "Originaldatensatz_IDs":
                " | ".join(
                    source_ids
                ),

            "Original_Quellennamen":
                " | ".join(
                    unique_nonempty(
                        group[
                            "Quellenname_final"
                        ]
                    )
                ),

            "Quellenfamilie_normalisiert":
                clean_string(
                    group[
                        "Quellenfamilie_normalisiert"
                    ].iloc[
                        0
                    ]
                ),

            "Temperatur_Block_C":
                temperature,

            "Temperatur_Spannweite_Block_K":
                temperature_span,

            "Temperaturklasse":
                temperature_class(
                    temperature
                ),

            "Leistung_Summe_nur_Diagnose_kW":
                diagnostic_power_sum,

            "Betriebsprofil_Code":
                clean_string(
                    group[
                        "Betriebsprofil_Code"
                    ].iloc[
                        0
                    ]
                ),

            "Betriebsprofil_h_pro_Tag":
                numeric_value(
                    group[
                        "Betriebsprofil_Generator_h_pro_Tag"
                    ].iloc[
                        0
                    ]
                ),

            "Betriebsprofil_Tage_pro_Woche":
                numeric_value(
                    group[
                        "Betriebsprofil_Generator_Tage_pro_Woche"
                    ].iloc[
                        0
                    ]
                ),

            "Betriebsprofil_Qualitaet":
                clean_string(
                    group[
                        "Betriebsprofil_Qualitaet"
                    ].iloc[
                        0
                    ]
                ),

            "Betriebsprofil_deterministisch_ergaenzt":
                bool(
                    group[
                        "Betriebsprofil_deterministisch_ergaenzt"
                    ].any()
                ),

            "Saison_Abdeckung_Waermemenge_Block":
                season_coverage_heat,

            "Saison_Profil_gueltig":
                bool(
                    season_complete
                ),

            "Saisonfaktor_Sommer":
                season_weighted(
                    "Saisonfaktor_Sommer"
                ),

            "Saisonfaktor_Winter":
                season_weighted(
                    "Saisonfaktor_Winter"
                ),

            "Saison_Aktive_Monate":
                season_weighted(
                    "Saison_Aktive_Monate"
                ),

            "Saison_Konzentration_HHI":
                season_weighted(
                    "Saison_Konzentration_HHI"
                ),

            "Saison_Konzentration_0_1":
                season_weighted(
                    "Saison_Konzentration_0_1"
                ),

            "Vorhersagbarkeit_raw":
                " | ".join(
                    unique_nonempty(
                        group[
                            "Vorhersagbarkeit_raw"
                        ]
                    )
                ),

            "Regelungsmoeglichkeiten_raw":
                " | ".join(
                    unique_nonempty(
                        group[
                            "Regelungsmoeglichkeiten_raw"
                        ]
                    )
                ),
        }

        for month, _ in MONTHS:
            row[
                f"Saison_Faktor_{month}"
            ] = month_factors[
                month
            ]

        block_rows.append(
            row
        )

        for original_id in source_ids:
            mapping_rows.append(
                {
                    "Experiment_Gruppe":
                        group_id,

                    "Originaldatensatz_ID":
                        original_id,

                    "Standortverbund_ID":
                        site_id,

                    "Generator_Block_ID":
                        block_id,
                }
            )

    return (
        pd.DataFrame(
            block_rows
        ),
        pd.DataFrame(
            mapping_rows
        ),
        generator_sources,
    )

def assign_size_classes(
        blocks,
):
    if blocks.empty:
        return blocks.copy(), pd.DataFrame()

    result = blocks.copy()
    result["Groessenklasse_Q"] = ""
    cut_rows = []

    for q_code, group in result.groupby("Quellklasse_Code", sort=True):
        values = group["Waermemenge_Block_kWh_a"].dropna()
        if values.empty:
            continue

        q33 = float(values.quantile(SIZE_CLASS_Q1))
        q67 = float(values.quantile(SIZE_CLASS_Q2))

        cut_rows.append(
            {
                "Quellklasse_Code": q_code,
                "N_Bloecke": int(len(group)),
                "Q33_kWh_a": q33,
                "Q67_kWh_a": q67,
                "Branchenspezifische_Q_Verwendung_empfohlen": bool(
                    len(group) >= MIN_N_FOR_BRANCH_Q_TEMPERATURE_MODEL
                ),
            }
        )

        for row_index in group.index:
            value = result.at[row_index, "Waermemenge_Block_kWh_a"]

            if pd.isna(value):
                label = "UNBEKANNT"
            elif value <= q33:
                label = "KLEIN"
            elif value <= q67:
                label = "MITTEL"
            else:
                label = "GROSS"

            result.at[row_index, "Groessenklasse_Q"] = label

    return result, pd.DataFrame(cut_rows)


def build_sites_table(
        group_id,
        blocks,
        site_filter,
):
    if blocks.empty:
        return pd.DataFrame()

    rows = []
    filter_map = site_filter.set_index("Standortverbund_ID")

    for site_id, group in blocks.groupby("Standortverbund_ID", sort=False):
        total_known = group["Waermemenge_Block_kWh_a"].sum()

        q_heats = {
            q: float(
                group.loc[
                    group["Quellklasse_Code"] == q,
                    "Waermemenge_Block_kWh_a",
                ].sum()
            )
            for q in VALID_SOURCE_CLASSES
        }

        portfolio = [q for q in VALID_SOURCE_CLASSES if q_heats[q] > 0]

        row = {
            "Experiment_Gruppe": group_id,
            "Standortverbund_ID": site_id,
            "Waermemenge_Q1_Q7_kWh_a": total_known,
            "Anzahl_Quellenbloecke": int(len(group)),
            "Quellenportfolio": "+".join(portfolio),
            "Anzahl_Quellklassen": int(len(portfolio)),
            "Anzahl_unterschiedliche_Betriebsprofile": int(group["Betriebsprofil_Code"].nunique()),
            "Anzahl_Bloecke_mit_gueltiger_Saisonalitaet": int(group["Saison_Profil_gueltig"].sum()),
        }

        if site_id in filter_map.index:
            row["Waermemenge_Gesamt_physisch_kWh_a"] = filter_map.at[site_id, "Waermemenge_Gesamt_physisch_kWh_a"]
            row["Waermemenge_Nicht_einordenbar_kWh_a"] = filter_map.at[site_id, "Waermemenge_Nicht_einordenbar_kWh_a"]
            row["Nicht_einordenbar_Anteil_Waermemenge_final"] = filter_map.at[site_id, "Nicht_einordenbar_Anteil_Waermemenge_final"]

        for q in VALID_SOURCE_CLASSES:
            row[f"Waermemenge_{q}_kWh_a"] = q_heats[q]
            row[f"Anteil_{q}_renormiert"] = safe_divide(q_heats[q], total_known)

        rows.append(row)

    sites = pd.DataFrame(rows)
    if sites.empty:
        return sites

    sites = sites.sort_values(
        "Waermemenge_Q1_Q7_kWh_a",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)

    site_total_map = sites.set_index("Standortverbund_ID")["Waermemenge_Q1_Q7_kWh_a"]
    blocks["Anteil_Block_an_Q1_Q7_Standort"] = (
            blocks["Waermemenge_Block_kWh_a"]
            /
            blocks["Standortverbund_ID"].map(site_total_map)
    )

    return sites


def apply_preflight(
        blocks,
        sites,
):
    """
    Generator-Preflight.

    Auffällige Blöcke bleiben energetisch erhalten.
    Sie werden lediglich als ungeeignete technische Donoren markiert.

    KEINE automatische Korrektur.
    KEIN automatischer Ausschluss.
    """

    if blocks.empty:
        return (
            blocks.copy(),
            pd.DataFrame(),
        )

    result = blocks.copy()

    site_share_sums = (
        result
        .groupby(
            "Standortverbund_ID"
        )[
            "Anteil_Block_an_Q1_Q7_Standort"
        ]
        .sum()
    )

    result[
        "Preflight_Status"
    ] = "OK"

    result[
        "Preflight_Flags"
    ] = ""

    result[
        "Temperatur_Donor_verwendbar"
    ] = True

    result[
        "Betriebsprofil_Donor_verwendbar"
    ] = True

    result[
        "Saisonalitaet_Donor_verwendbar"
    ] = True

    diagnostics = []

    for row_index, row in result.iterrows():

        flags = []
        hard = False

        q_code = clean_string(
            row[
                "Quellklasse_Code"
            ]
        )

        temperature = numeric_value(
            row[
                "Temperatur_Block_C"
            ]
        )

        # Temperatur.
        if pd.isna(
                temperature
        ):
            flags.append(
                "TEMPERATUR_FEHLT"
            )

            result.at[
                row_index,
                "Temperatur_Donor_verwendbar",
            ] = False

        else:
            if (
                    temperature
                    <=
                    ABSOLUTE_TEMPERATURE_MIN_C
                    or
                    temperature
                    >
                    ABSOLUTE_TEMPERATURE_MAX_C
            ):
                flags.append(
                    "TEMPERATUR_HART_UNPLAUSIBEL"
                )

                hard = True

                result.at[
                    row_index,
                    "Temperatur_Donor_verwendbar",
                ] = False

            bounds = DONOR_TEMPERATURE_BOUNDS_C.get(
                q_code
            )

            if bounds:
                lower, upper = bounds

                if (
                        temperature < lower
                        or
                        temperature > upper
                ):
                    flags.append(
                        "TEMPERATUR_AUSSERHALB_BREITER_Q_PLAUSIBILITAET"
                    )

                    result.at[
                        row_index,
                        "Temperatur_Donor_verwendbar",
                    ] = False

        # Betriebsprofil.
        profile = clean_string(
            row[
                "Betriebsprofil_Code"
            ]
        )

        hours = numeric_value(
            row[
                "Betriebsprofil_h_pro_Tag"
            ]
        )

        days = numeric_value(
            row[
                "Betriebsprofil_Tage_pro_Woche"
            ]
        )

        if profile == "BP_UNBEKANNT":
            flags.append(
                "BETRIEBSPROFIL_UNBEKANNT"
            )

            result.at[
                row_index,
                "Betriebsprofil_Donor_verwendbar",
            ] = False

        elif (
                pd.isna(
                    hours
                )
                or
                pd.isna(
                    days
                )
                or
                hours <= 0
                or
                hours > 24
                or
                days <= 0
                or
                days > 7
        ):
            flags.append(
                "BETRIEBSPROFIL_WERTE_UNPLAUSIBEL"
            )

            hard = True

            result.at[
                row_index,
                "Betriebsprofil_Donor_verwendbar",
            ] = False

        # Saisonalität.
        if not bool(
                row[
                    "Saison_Profil_gueltig"
                ]
        ):
            flags.append(
                "SAISONALITAET_UNVOLLSTAENDIG"
            )

            result.at[
                row_index,
                "Saisonalitaet_Donor_verwendbar",
            ] = False

        else:
            weighted_mean_factor = safe_divide(
                sum(
                    numeric_value(
                        row[
                            f"Saison_Faktor_{month}"
                        ]
                    )
                    *
                    MONTH_HOURS[
                        month
                    ]
                    for month, _
                    in MONTHS
                ),
                sum(
                    MONTH_HOURS.values()
                ),
            )

            if (
                    pd.isna(
                        weighted_mean_factor
                    )
                    or
                    abs(
                        weighted_mean_factor
                        -
                        1.0
                    )
                    >
                    SEASON_NORMALIZATION_TOLERANCE
            ):
                flags.append(
                    "SAISON_NORMALISIERUNG_ABWEICHEND"
                )

                result.at[
                    row_index,
                    "Saisonalitaet_Donor_verwendbar",
                ] = False

        # Blockanteil.
        share = numeric_value(
            row[
                "Anteil_Block_an_Q1_Q7_Standort"
            ]
        )

        if (
                pd.isna(
                    share
                )
                or
                share <= 0
                or
                share
                >
                1.0
                +
                SITE_SHARE_SUM_TOLERANCE
        ):
            flags.append(
                "BLOCKANTEIL_UNPLAUSIBEL"
            )

            hard = True

        site_id = clean_string(
            row[
                "Standortverbund_ID"
            ]
        )

        site_sum = site_share_sums.get(
            site_id,
            np.nan,
        )

        if (
                pd.isna(
                    site_sum
                )
                or
                abs(
                    site_sum
                    -
                    1.0
                )
                >
                SITE_SHARE_SUM_TOLERANCE
        ):
            flags.append(
                "STANDORT_BLOCKANTEILE_SUMME_NICHT_1"
            )

            hard = True

        if hard:
            status = "HARTER_PRUEFFALL"

        elif flags:
            status = "PRUEFEN"

        else:
            status = "OK"

        result.at[
            row_index,
            "Preflight_Status",
        ] = status

        result.at[
            row_index,
            "Preflight_Flags",
        ] = " | ".join(
            flags
        )

        diagnostics.append(
            {
                "Generator_Block_ID":
                    row[
                        "Generator_Block_ID"
                    ],

                "Standortverbund_ID":
                    site_id,

                "Quellklasse_Code":
                    q_code,

                "Original_Quellennamen":
                    row[
                        "Original_Quellennamen"
                    ],

                "Temperatur_C":
                    temperature,

                "Betriebsprofil_Code":
                    profile,

                "Saisonfaktor_Sommer":
                    row[
                        "Saisonfaktor_Sommer"
                    ],

                "Preflight_Status":
                    status,

                "Preflight_Flags":
                    " | ".join(
                        flags
                    ),
            }
        )

    result[
        "Kompletter_Donor_verwendbar"
    ] = (
            result[
                "Temperatur_Donor_verwendbar"
            ]
            &
            result[
                "Betriebsprofil_Donor_verwendbar"
            ]
            &
            result[
                "Saisonalitaet_Donor_verwendbar"
            ]
            &
            result[
                "Preflight_Status"
            ].ne(
                "HARTER_PRUEFFALL"
            )
    )

    return (
        result,
        pd.DataFrame(
            diagnostics
        ),
    )


def build_portfolio_frequency(
        group_id,
        sites,
):
    if sites.empty:
        return pd.DataFrame()

    grouped = (
        sites
        .groupby("Quellenportfolio", dropna=False)
        .agg(
            Anzahl_Standorte=("Standortverbund_ID", "count"),
            Waermemenge_Q1_Q7_kWh_a=("Waermemenge_Q1_Q7_kWh_a", "sum"),
        )
        .reset_index()
    )

    grouped["Experiment_Gruppe"] = group_id
    grouped["Wahrscheinlichkeit_Standortgewichtet"] = (
            grouped["Anzahl_Standorte"]
            /
            grouped["Anzahl_Standorte"].sum()
    )
    grouped["Anteil_Waermemenge"] = (
            grouped["Waermemenge_Q1_Q7_kWh_a"]
            /
            grouped["Waermemenge_Q1_Q7_kWh_a"].sum()
    )

    return grouped[
        [
            "Experiment_Gruppe",
            "Quellenportfolio",
            "Anzahl_Standorte",
            "Wahrscheinlichkeit_Standortgewichtet",
            "Waermemenge_Q1_Q7_kWh_a",
            "Anteil_Waermemenge",
        ]
    ].sort_values(
        "Anzahl_Standorte",
        ascending=False,
        kind="stable",
    )

def build_operating_profile_distribution(
        group_id,
        blocks,
):
    if blocks.empty:
        return pd.DataFrame()

    frames = []

    q_scopes = ["ALLE", *VALID_SOURCE_CLASSES]
    size_scopes = ["ALLE", "KLEIN", "MITTEL", "GROSS"]

    for q_scope in q_scopes:
        q_subset = (
            blocks
            if q_scope == "ALLE"
            else blocks[blocks["Quellklasse_Code"] == q_scope]
        )

        if q_subset.empty:
            continue

        for size_scope in size_scopes:
            subset = (
                q_subset
                if size_scope == "ALLE"
                else q_subset[q_subset["Groessenklasse_Q"] == size_scope]
            )

            if subset.empty:
                continue

            grouped = (
                subset
                .groupby("Betriebsprofil_Code", dropna=False)
                .agg(
                    Anzahl_Bloecke=("Generator_Block_ID", "count"),
                    Waermemenge_kWh_a=("Waermemenge_Block_kWh_a", "sum"),
                )
                .reset_index()
            )

            grouped["Experiment_Gruppe"] = group_id
            grouped["Quellklasse_Scope"] = q_scope
            grouped["Groessenklasse_Scope"] = size_scope
            grouped["Wahrscheinlichkeit_Blockgewichtet"] = (
                    grouped["Anzahl_Bloecke"]
                    /
                    grouped["Anzahl_Bloecke"].sum()
            )
            grouped["Wahrscheinlichkeit_Waermemengengewichtet"] = (
                    grouped["Waermemenge_kWh_a"]
                    /
                    grouped["Waermemenge_kWh_a"].sum()
            )

            frames.append(grouped)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    return result[
        [
            "Experiment_Gruppe",
            "Quellklasse_Scope",
            "Groessenklasse_Scope",
            "Betriebsprofil_Code",
            "Anzahl_Bloecke",
            "Wahrscheinlichkeit_Blockgewichtet",
            "Waermemenge_kWh_a",
            "Wahrscheinlichkeit_Waermemengengewichtet",
        ]
    ]


def build_temperature_distribution(
        group_id,
        blocks,
):
    if blocks.empty:
        return pd.DataFrame()

    rows = []

    for q_scope in [
        "ALLE",
        *VALID_SOURCE_CLASSES,
    ]:
        subset = (
            blocks.copy()
            if q_scope == "ALLE"
            else blocks[
                blocks[
                    "Quellklasse_Code"
                ]
                ==
                q_scope
                ].copy()
        )

        if (
                "Temperatur_Donor_verwendbar"
                in subset.columns
        ):
            subset = subset[
                subset[
                    "Temperatur_Donor_verwendbar"
                ]
            ]

        subset = subset[
            subset[
                "Temperatur_Block_C"
            ].notna()
            &
            subset[
                "Waermemenge_Block_kWh_a"
            ].notna()
            &
            (
                    subset[
                        "Waermemenge_Block_kWh_a"
                    ]
                    > 0
            )
            ]

        if subset.empty:
            continue

        values = subset[
            "Temperatur_Block_C"
        ].to_numpy(
            dtype=float
        )

        weights = subset[
            "Waermemenge_Block_kWh_a"
        ].to_numpy(
            dtype=float
        )

        rows.append(
            {
                "Experiment_Gruppe":
                    group_id,

                "Quellklasse_Scope":
                    q_scope,

                "N_Donoren":
                    int(
                        len(
                            subset
                        )
                    ),

                "Branchenspezifisches_Modell_empfohlen":
                    bool(
                        q_scope != "ALLE"
                        and
                        len(
                            subset
                        )
                        >=
                        MIN_N_FOR_BRANCH_Q_TEMPERATURE_MODEL
                    ),

                "Minimum_C":
                    float(
                        np.min(
                            values
                        )
                    ),

                "P10_C":
                    float(
                        np.quantile(
                            values,
                            0.10,
                        )
                    ),

                "P25_C":
                    float(
                        np.quantile(
                            values,
                            0.25,
                        )
                    ),

                "Median_C":
                    float(
                        np.median(
                            values
                        )
                    ),

                "Mittelwert_C":
                    float(
                        np.mean(
                            values
                        )
                    ),

                "P75_C":
                    float(
                        np.quantile(
                            values,
                            0.75,
                        )
                    ),

                "P90_C":
                    float(
                        np.quantile(
                            values,
                            0.90,
                        )
                    ),

                "Maximum_C":
                    float(
                        np.max(
                            values
                        )
                    ),

                "Waermemengengewichteter_Mittelwert_C":
                    weighted_mean(
                        values,
                        weights,
                    ),

                "Waermemengengewichteter_P10_C":
                    weighted_quantile(
                        values,
                        weights,
                        0.10,
                    ),

                "Waermemengengewichteter_Median_C":
                    weighted_quantile(
                        values,
                        weights,
                        0.50,
                    ),

                "Waermemengengewichteter_P90_C":
                    weighted_quantile(
                        values,
                        weights,
                        0.90,
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


def build_seasonality_distribution(
        group_id,
        blocks,
):
    if blocks.empty:
        return pd.DataFrame()

    rows = []

    for q_scope in [
        "ALLE",
        *VALID_SOURCE_CLASSES,
    ]:
        subset = (
            blocks.copy()
            if q_scope == "ALLE"
            else blocks[
                blocks[
                    "Quellklasse_Code"
                ]
                ==
                q_scope
                ].copy()
        )

        if subset.empty:
            continue

        valid = subset[
            subset[
                "Saison_Profil_gueltig"
            ]
            &
            subset[
                "Saisonfaktor_Sommer"
            ].notna()
            ].copy()

        if (
                "Saisonalitaet_Donor_verwendbar"
                in valid.columns
        ):
            valid = valid[
                valid[
                    "Saisonalitaet_Donor_verwendbar"
                ]
            ]

        row = {
            "Experiment_Gruppe":
                group_id,

            "Quellklasse_Scope":
                q_scope,

            "Bloecke_gesamt":
                int(
                    len(
                        subset
                    )
                ),

            "Bloecke_mit_gueltiger_Saisonalitaet":
                int(
                    len(
                        valid
                    )
                ),

            "Abdeckung_Saisonalitaet_Blockgewichtet":
                safe_divide(
                    len(
                        valid
                    ),
                    len(
                        subset
                    ),
                ),

            "Abdeckung_Saisonalitaet_Waermemengengewichtet":
                safe_divide(
                    valid[
                        "Waermemenge_Block_kWh_a"
                    ].sum(),
                    subset[
                        "Waermemenge_Block_kWh_a"
                    ].sum(),
                ),
        }

        if not valid.empty:
            values = valid[
                "Saisonfaktor_Sommer"
            ].to_numpy(
                dtype=float
            )

            weights = valid[
                "Waermemenge_Block_kWh_a"
            ].to_numpy(
                dtype=float
            )

            row.update(
                {
                    "Sommerfaktor_P10":
                        float(
                            np.quantile(
                                values,
                                0.10,
                            )
                        ),

                    "Sommerfaktor_P25":
                        float(
                            np.quantile(
                                values,
                                0.25,
                            )
                        ),

                    "Sommerfaktor_Median":
                        float(
                            np.median(
                                values
                            )
                        ),

                    "Sommerfaktor_Mittel":
                        float(
                            np.mean(
                                values
                            )
                        ),

                    "Sommerfaktor_P75":
                        float(
                            np.quantile(
                                values,
                                0.75,
                            )
                        ),

                    "Sommerfaktor_P90":
                        float(
                            np.quantile(
                                values,
                                0.90,
                            )
                        ),

                    "Sommerfaktor_Waermemengengew_Mittel":
                        weighted_mean(
                            values,
                            weights,
                        ),

                    "Sommerfaktor_Waermemengengew_Median":
                        weighted_quantile(
                            values,
                            weights,
                            0.50,
                        ),

                    "Aktive_Monate_Median":
                        float(
                            valid[
                                "Saison_Aktive_Monate"
                            ].median()
                        ),

                    "Aktive_Monate_Waermemengengew_Mittel":
                        weighted_mean(
                            valid[
                                "Saison_Aktive_Monate"
                            ],
                            weights,
                        ),

                    "Konzentration_0_1_Median":
                        float(
                            valid[
                                "Saison_Konzentration_0_1"
                            ].median()
                        ),

                    "Konzentration_0_1_Waermemengengew_Mittel":
                        weighted_mean(
                            valid[
                                "Saison_Konzentration_0_1"
                            ],
                            weights,
                        ),
                }
            )

            for month, _ in MONTHS:
                month_values = valid[
                    f"Saison_Faktor_{month}"
                ].to_numpy(
                    dtype=float
                )

                row[
                    f"{month}_Mittel_Blockgewichtet"
                ] = float(
                    np.mean(
                        month_values
                    )
                )

                row[
                    f"{month}_Mittel_Waermemengengewichtet"
                ] = weighted_mean(
                    month_values,
                    weights,
                )

        rows.append(
            row
        )

    return pd.DataFrame(
        rows
    )

def build_site_draw_pool(
        sites,
        blocks,
):
    if sites.empty:
        return pd.DataFrame()

    rows = []

    for _, site_row in sites.iterrows():
        site_id = clean_string(site_row["Standortverbund_ID"])
        subset = blocks[blocks["Standortverbund_ID"] == site_id].copy()
        subset = subset.sort_values("Generator_Block_ID", kind="stable")

        structure = []
        for _, block in subset.iterrows():
            structure.append(
                {
                    "block_id": clean_string(block["Generator_Block_ID"]),
                    "q": clean_string(block["Quellklasse_Code"]),
                    "share": float(block["Anteil_Block_an_Q1_Q7_Standort"]),
                    "size_class": clean_string(block["Groessenklasse_Q"]),
                }
            )

        rows.append(
            {
                "Experiment_Gruppe": clean_string(site_row["Experiment_Gruppe"]),
                "Standortverbund_ID": site_id,
                "Quellenportfolio": clean_string(site_row["Quellenportfolio"]),
                "Anzahl_Quellenbloecke": int(site_row["Anzahl_Quellenbloecke"]),
                "Waermemenge_Q1_Q7_kWh_a": float(site_row["Waermemenge_Q1_Q7_kWh_a"]),
                "Blockstruktur_JSON": json.dumps(structure, ensure_ascii=False),
            }
        )

    return pd.DataFrame(rows)



def build_donor_pool(
        blocks,
):
    if blocks.empty:
        return pd.DataFrame()

    donor = blocks.copy()

    donor[
        "Donor_ID"
    ] = (
            "DONOR::"
            +
            donor[
                "Generator_Block_ID"
            ]
    )

    # Preflight-Felder haben Vorrang.
    if (
            "Betriebsprofil_Donor_verwendbar"
            not in donor.columns
    ):
        donor[
            "Betriebsprofil_Donor_verwendbar"
        ] = donor[
            "Betriebsprofil_Code"
        ].ne(
            "BP_UNBEKANNT"
        )

    if (
            "Saisonalitaet_Donor_verwendbar"
            not in donor.columns
    ):
        donor[
            "Saisonalitaet_Donor_verwendbar"
        ] = donor[
            "Saison_Profil_gueltig"
        ]

    if (
            "Temperatur_Donor_verwendbar"
            not in donor.columns
    ):
        donor[
            "Temperatur_Donor_verwendbar"
        ] = donor[
            "Temperatur_Block_C"
        ].notna()

    donor[
        "Donor_komplett"
    ] = (
            donor[
                "Betriebsprofil_Donor_verwendbar"
            ]
            &
            donor[
                "Saisonalitaet_Donor_verwendbar"
            ]
            &
            donor[
                "Temperatur_Donor_verwendbar"
            ]
            &
            donor.get(
                "Preflight_Status",
                pd.Series(
                    "OK",
                    index=donor.index,
                ),
            ).ne(
                "HARTER_PRUEFFALL"
            )
    )

    return donor


def build_operating_profile_donor_options(
        blocks,
):
    """
    Probabilistische Donor-Hierarchie für verbleibende unbekannte Profile.

    KEINE Bedingung auf Profil_WZ_Code.
    Die Experimentgruppe ist die Modellgruppe.
    """

    if blocks.empty:
        return pd.DataFrame()

    known = blocks[
        blocks[
            "Betriebsprofil_Code"
        ].ne(
            "BP_UNBEKANNT"
        )
    ].copy()

    if (
            "Betriebsprofil_Donor_verwendbar"
            in known.columns
    ):
        known = known[
            known[
                "Betriebsprofil_Donor_verwendbar"
            ]
        ].copy()

    missing = blocks[
        blocks[
            "Betriebsprofil_Code"
        ].eq(
            "BP_UNBEKANNT"
        )
    ].copy()

    rows = []

    for _, target in missing.iterrows():

        site = clean_string(
            target[
                "Standortverbund_ID"
            ]
        )

        q = clean_string(
            target[
                "Quellklasse_Code"
            ]
        )

        family = clean_string(
            target[
                "Quellenfamilie_normalisiert"
            ]
        )

        size_class = clean_string(
            target[
                "Groessenklasse_Q"
            ]
        )

        levels = [
            (
                "GLEICHER_STANDORT_Q_FAMILIE",
                known[
                    known[
                        "Standortverbund_ID"
                    ].eq(
                        site
                    )
                    &
                    known[
                        "Quellklasse_Code"
                    ].eq(
                        q
                    )
                    &
                    known[
                        "Quellenfamilie_normalisiert"
                    ].eq(
                        family
                    )
                    ],
            ),
            (
                "GLEICHER_STANDORT_Q",
                known[
                    known[
                        "Standortverbund_ID"
                    ].eq(
                        site
                    )
                    &
                    known[
                        "Quellklasse_Code"
                    ].eq(
                        q
                    )
                    ],
            ),
            (
                "GRUPPE_Q_FAMILIE",
                known[
                    known[
                        "Quellklasse_Code"
                    ].eq(
                        q
                    )
                    &
                    known[
                        "Quellenfamilie_normalisiert"
                    ].eq(
                        family
                    )
                    ],
            ),
            (
                "GRUPPE_Q_GROESSENKLASSE",
                known[
                    known[
                        "Quellklasse_Code"
                    ].eq(
                        q
                    )
                    &
                    known[
                        "Groessenklasse_Q"
                    ].eq(
                        size_class
                    )
                    ],
            ),
            (
                "GRUPPE_Q",
                known[
                    known[
                        "Quellklasse_Code"
                    ].eq(
                        q
                    )
                ],
            ),
        ]

        recommended = ""
        candidates = pd.DataFrame()
        counts = {}

        for rank, (
                label,
                subset,
        ) in enumerate(
            levels,
            start=1,
        ):
            counts[
                f"N_Level_{rank}_{label}"
            ] = int(
                len(
                    subset
                )
            )

            if (
                    recommended == ""
                    and
                    len(
                        subset
                    ) > 0
            ):
                recommended = label
                candidates = subset

        row = {
            "Generator_Block_ID":
                clean_string(
                    target[
                        "Generator_Block_ID"
                    ]
                ),

            "Standortverbund_ID":
                site,

            "Quellklasse_Code":
                q,

            "Quellenfamilie_normalisiert":
                family,

            "Groessenklasse_Q":
                size_class,

            "Empfohlene_Donor_Ebene":
                recommended,

            "Anzahl_Donoren_empfohlen":
                int(
                    len(
                        candidates
                    )
                ),

            "Donor_Block_IDs_Beispiele":
                (
                    " | ".join(
                        candidates[
                            "Generator_Block_ID"
                        ]
                        .head(
                            20
                        )
                        .map(
                            clean_string
                        )
                    )
                    if not candidates.empty
                    else ""
                ),
        }

        row.update(
            counts
        )

        rows.append(
            row
        )

    return pd.DataFrame(
        rows
    )

def build_exclusion_audit(
        enriched,
):
    excluded = enriched[enriched["Ausgeschlossen_final"]].copy()
    if excluded.empty:
        return pd.DataFrame()

    cols = [
        "_Original_ID",
        "Standortverbund_ID_final",
        "Quellklasse_final",
        "Quellenname_final",
        "Waermemenge_final_kWh_a",
        "Ausschluss_Effekt",
        "Ausschluss_Effekt_Herkunft",
        "Ausschlussgrund_final",
        "Pruefbegruendung_final",
    ]
    cols = [c for c in cols if c in excluded.columns]
    return excluded[cols].rename(columns={"_Original_ID": "Originaldatensatz_ID"})



def build_donor_coverage(
        blocks,
):
    if blocks.empty:
        return pd.DataFrame()

    rows = []

    for scope in [
        "ALLE",
        *VALID_SOURCE_CLASSES,
    ]:
        subset = (
            blocks
            if scope == "ALLE"
            else blocks[
                blocks[
                    "Quellklasse_Code"
                ]
                ==
                scope
                ]
        )

        if subset.empty:
            continue

        temp_ok = (
            subset[
                "Temperatur_Donor_verwendbar"
            ]
            if "Temperatur_Donor_verwendbar" in subset.columns
            else subset[
                "Temperatur_Block_C"
            ].notna()
        )

        bp_ok = (
            subset[
                "Betriebsprofil_Donor_verwendbar"
            ]
            if "Betriebsprofil_Donor_verwendbar" in subset.columns
            else subset[
                "Betriebsprofil_Code"
            ].ne(
                "BP_UNBEKANNT"
            )
        )

        season_ok = (
            subset[
                "Saisonalitaet_Donor_verwendbar"
            ]
            if "Saisonalitaet_Donor_verwendbar" in subset.columns
            else subset[
                "Saison_Profil_gueltig"
            ]
        )

        complete_ok = (
            subset[
                "Kompletter_Donor_verwendbar"
            ]
            if "Kompletter_Donor_verwendbar" in subset.columns
            else (
                    temp_ok
                    &
                    bp_ok
                    &
                    season_ok
            )
        )

        rows.append(
            {
                "Quellklasse_Scope":
                    scope,

                "N_Bloecke":
                    int(
                        len(
                            subset
                        )
                    ),

                "Temperatur_Abdeckung":
                    safe_divide(
                        temp_ok.sum(),
                        len(
                            subset
                        ),
                    ),

                "Betriebsprofil_Abdeckung":
                    safe_divide(
                        bp_ok.sum(),
                        len(
                            subset
                        ),
                    ),

                "Saisonalitaet_Abdeckung":
                    safe_divide(
                        season_ok.sum(),
                        len(
                            subset
                        ),
                    ),

                "Kompletter_Donor_Abdeckung":
                    safe_divide(
                        complete_ok.sum(),
                        len(
                            subset
                        ),
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


def build_aggregation_sensitivity_10k(
        generator_sources,
):
    """
    Reine Diagnose:
    Simuliert, welche zusätzlichen Zusammenführungen bei 10 K statt 5 K
    Temperaturspanne entstehen würden.

    Die produktiven Quellenblöcke bleiben unverändert bei 5 K.
    """

    if generator_sources.empty:
        return pd.DataFrame()

    simulated = prepare_aggregation_keys(
        generator_sources,
        max_span_c=
        AGGREGATION_SENSITIVITY_TEMPERATURE_SPAN_C,
        key_column=
        "_Aggregation_Key_10K",
    )

    rows = []

    base_columns = [
        "Standortverbund_ID_final",
        "Quellklasse_final",
        "Quellenfamilie_normalisiert",
        "Betriebsprofil_Code",
    ]

    for (
            site_id,
            q_code,
            family,
            profile,
    ), group in simulated.groupby(
        base_columns,
        sort=False,
        dropna=False,
    ):

        n_5k = group[
            "_Aggregation_Key"
        ].nunique()

        n_10k = group[
            "_Aggregation_Key_10K"
        ].nunique()

        if n_10k >= n_5k:
            continue

        temperatures = group[
            "Temperatur_final_C"
        ].dropna()

        rows.append(
            {
                "Standortverbund_ID":
                    site_id,

                "Quellklasse_Code":
                    q_code,

                "Quellenfamilie_normalisiert":
                    family,

                "Betriebsprofil_Code":
                    profile,

                "Anzahl_Originalpotentiale":
                    int(
                        len(
                            group
                        )
                    ),

                "Bloecke_bei_5K":
                    int(
                        n_5k
                    ),

                "Bloecke_bei_10K":
                    int(
                        n_10k
                    ),

                "Zusaetzliche_Zusammenfuehrungen_bei_10K":
                    int(
                        n_5k
                        -
                        n_10k
                    ),

                "Temperatur_Min_C":
                    (
                        float(
                            temperatures.min()
                        )
                        if not temperatures.empty
                        else np.nan
                    ),

                "Temperatur_Max_C":
                    (
                        float(
                            temperatures.max()
                        )
                        if not temperatures.empty
                        else np.nan
                    ),

                "Temperaturspanne_K":
                    (
                        float(
                            temperatures.max()
                            -
                            temperatures.min()
                        )
                        if not temperatures.empty
                        else np.nan
                    ),

                "Originaldatensatz_IDs":
                    " | ".join(
                        group[
                            "_Original_ID"
                        ].map(
                            clean_string
                        )
                    ),

                "Quellennamen":
                    " | ".join(
                        unique_nonempty(
                            group[
                                "Quellenname_final"
                            ]
                        )
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


def build_aggregation_diagnostics(
        group_id,
        generator_sources,
        blocks,
):
    """
    Zeigt:
        - wie viele Originalpotentiale zu Blöcken zusammengefasst wurden
        - welche Blöcke mehrere Quellen enthalten
        - welche potentiellen Familien wegen anderer Temperatur/BP/Saison
          NICHT zusammengeführt wurden
    """

    if generator_sources.empty:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )

    merged_blocks = blocks[
        blocks[
            "Anzahl_Originalpotentiale"
        ]
        > 1
        ].copy()

    # ---------------------------------------------------------
    # Kandidaten:
    # gleiche Standort + Q + Quellenfamilie, aber mehrere endgültige
    # Aggregationsschlüssel.
    # ---------------------------------------------------------

    temp = generator_sources.copy()

    candidate_rows = []

    base_group_columns = [
        "Standortverbund_ID_final",
        "Quellklasse_final",
        "Quellenfamilie_normalisiert",
    ]

    for (
            site_id,
            q_code,
            family,
    ), group in temp.groupby(
        base_group_columns,
        sort=False,
    ):

        if (
                not clean_string(
                    family
                )
                or
                len(
                    group
                )
                < 2
        ):
            continue

        distinct_aggregation_keys = (
            group[
                "_Aggregation_Key"
            ]
            .nunique()
        )

        if distinct_aggregation_keys <= 1:
            continue

        candidate_rows.append(
            {
                "Experiment_Gruppe":
                    group_id,

                "Standortverbund_ID":
                    site_id,

                "Quellklasse_Code":
                    q_code,

                "Quellenfamilie_normalisiert":
                    family,

                "Anzahl_Originalpotentiale":
                    int(
                        len(
                            group
                        )
                    ),

                "Anzahl_getrennter_Aggregationsschluessel":
                    int(
                        distinct_aggregation_keys
                    ),

                "Temperaturen_C":
                    " | ".join(
                        unique_nonempty(
                            group[
                                "Temperatur_final_C"
                            ]
                        )
                    ),

                "Betriebsprofile":
                    " | ".join(
                        unique_nonempty(
                            group[
                                "Betriebsprofil_Code"
                            ]
                        )
                    ),

                "Saison_Signaturen":
                    int(
                        group[
                            "Saison_Signatur"
                        ]
                        .nunique()
                    ),

                "Originaldatensatz_IDs":
                    " | ".join(
                        group[
                            "_Original_ID"
                        ]
                        .map(
                            clean_string
                        )
                    ),

                "Quellennamen":
                    " | ".join(
                        unique_nonempty(
                            group[
                                "Quellenname_final"
                            ]
                        )
                    ),
            }
        )

    candidates = pd.DataFrame(
        candidate_rows
    )

    return (
        merged_blocks,
        candidates,
    )


# =============================================================================
# 21. DIAGNOSE: ROHE BETRIEBSPROFILANGABEN
# =============================================================================


def build_operating_raw_diagnostics(
        enriched,
):
    columns = [
        "Betriebsprofil_Roh_Verfuegbarkeit",
        "Betriebsprofil_Roh_h_pro_Tag",
        "Betriebsprofil_Roh_Wochenende",
        "Betriebsprofil_Code_original_abgeleitet",
        "Betriebsprofil_Code",
        "Betriebsprofil_deterministisch_ergaenzt",
        "Betriebsprofil_Herkunft",
        "Betriebsprofil_Qualitaet",
    ]

    available = [
        column
        for column
        in columns
        if column
           in enriched.columns
    ]

    if not available:
        return pd.DataFrame()

    return (
        enriched[
            available
        ]
        .value_counts(
            dropna=False
        )
        .reset_index(
            name="Anzahl_Potentiale"
        )
    )

def build_review_audit(
        enriched,
):
    if enriched.empty:
        return pd.DataFrame()

    rows = []

    for status, group in enriched.groupby(
            "Pruefstatus_final",
            dropna=False,
    ):

        rows.append(
            {
                "Pruefstatus":
                    clean_string(
                        status
                    ),

                "Anzahl_Potentiale":
                    int(
                        len(
                            group
                        )
                    ),

                "Korrigierte_Waermemenge":
                    int(
                        group[
                            "Korrektur_Waermemenge"
                        ]
                        .sum()
                    ),

                "Korrigierte_Leistung":
                    int(
                        group[
                            "Korrektur_Leistung"
                        ]
                        .sum()
                    ),

                "Korrigierte_Temperatur":
                    int(
                        group[
                            "Korrektur_Temperatur"
                        ]
                        .sum()
                    ),

                "Ausgeschlossen":
                    int(
                        group[
                            "Ausgeschlossen_final"
                        ]
                        .sum()
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


# =============================================================================
# 23. ZUSAMMENFASSUNG
# =============================================================================


def build_summary(
        group_id,
        raw_potentials,
        enriched,
        site_filter,
        blocks,
        sites,
        review_path,
):
    final_suitable = (
        int(
            site_filter[
                "Geeignet_QX20_final"
            ].sum()
        )
        if not site_filter.empty
        else 0
    )

    unresolved_excluded = int(
        (
                enriched[
                    "Ausgeschlossen_final"
                ]
                &
                (
                        enriched[
                            "Ausschluss_Effekt"
                        ]
                        ==
                        EXCLUSION_EFFECT_UNRESOLVED
                )
        ).sum()
    )

    removed_physical = int(
        (
                enriched[
                    "Ausgeschlossen_final"
                ]
                &
                (
                        enriched[
                            "Ausschluss_Effekt"
                        ]
                        ==
                        EXCLUSION_EFFECT_REMOVE
                )
        ).sum()
    )

    if not blocks.empty:
        standard_bp = int(
            blocks[
                "Betriebsprofil_Code"
            ]
            .str.match(
                r"^BP_(8|12|16|20|24)x(5|7)$"
            )
            .sum()
        )

        exact_bp = int(
            blocks[
                "Betriebsprofil_Code"
            ]
            .str.startswith(
                "BP_EXAKT_"
            )
            .sum()
        )

        unknown_bp = int(
            blocks[
                "Betriebsprofil_Code"
            ]
            .eq(
                "BP_UNBEKANNT"
            )
            .sum()
        )

        hard_preflight = int(
            blocks[
                "Preflight_Status"
            ]
            .eq(
                "HARTER_PRUEFFALL"
            )
            .sum()
        )

        review_preflight = int(
            blocks[
                "Preflight_Status"
            ]
            .eq(
                "PRUEFEN"
            )
            .sum()
        )

        complete_donors = int(
            blocks[
                "Kompletter_Donor_verwendbar"
            ].sum()
        )

    else:
        standard_bp = 0
        exact_bp = 0
        unknown_bp = 0
        hard_preflight = 0
        review_preflight = 0
        complete_donors = 0

    deterministic_completed = int(
        enriched[
            "Betriebsprofil_deterministisch_ergaenzt"
        ].sum()
    )

    return pd.DataFrame(
        [
            [
                "Experiment_Gruppe",
                group_id,
            ],
            [
                "Originalpotentiale",
                int(
                    len(
                        raw_potentials
                    )
                ),
            ],
            [
                "Waermengen_Korrekturen",
                int(
                    enriched[
                        "Korrektur_Waermemenge"
                    ].sum()
                ),
            ],
            [
                "Leistungs_Korrekturen",
                int(
                    enriched[
                        "Korrektur_Leistung"
                    ].sum()
                ),
            ],
            [
                "Temperatur_Korrekturen",
                int(
                    enriched[
                        "Korrektur_Temperatur"
                    ].sum()
                ),
            ],
            [
                "Ausschluss_unaufgeloest_wie_QX",
                unresolved_excluded,
            ],
            [
                "Ausschluss_physisch_entfernt",
                removed_physical,
            ],
            [
                "Standorte_final_geeignet",
                final_suitable,
            ],
            [
                "Standorte_final_nicht_geeignet",
                int(
                    len(
                        site_filter
                    )
                    -
                    final_suitable
                ),
            ],
            [
                "Generator_Quellenbloecke",
                int(
                    len(
                        blocks
                    )
                ),
            ],
            [
                "Generator_Standorte",
                int(
                    len(
                        sites
                    )
                ),
            ],
            [
                "Betriebsprofile_Standard",
                standard_bp,
            ],
            [
                "Betriebsprofile_Exakt_Sonderfall",
                exact_bp,
            ],
            [
                "Betriebsprofile_Unbekannt",
                unknown_bp,
            ],
            [
                "Betriebsprofile_deterministisch_ergaenzt",
                deterministic_completed,
            ],
            [
                "Preflight_Harte_Prueffaelle",
                hard_preflight,
            ],
            [
                "Preflight_Pruefen",
                review_preflight,
            ],
            [
                "Komplette_Donoren",
                complete_donors,
            ],
            [
                "Profil_WZ_als_Modellbedingung",
                "NEIN",
            ],
            [
                "Review_Datei",
                (
                    review_path.name
                    if (
                            review_path is not None
                            and
                            review_path.exists()
                    )
                    else ""
                ),
            ],
        ],
        columns=[
            "Kennzahl",
            "Wert",
        ],
    )

def write_dataframe_files(
        folder,
        name,
        df,
):
    """
    Schreibt primär Parquet, zusätzlich optional CSV.
    """

    if WRITE_PARQUET:

        try:

            df.to_parquet(
                folder
                / f"{name}.parquet",
                index=False,
                )

        except Exception as exc:

            print(
                f"      WARNUNG: Parquet für {name} "
                f"konnte nicht geschrieben werden: {exc}"
            )

    if WRITE_CSV:

        df.to_csv(
            folder
            / f"{name}.csv",
            index=False,
            encoding="utf-8-sig",
            sep=";",
            )


def autosize_worksheet(
        worksheet,
        max_width=45,
):
    for column_cells in worksheet.columns:

        column_index = column_cells[0].column

        letter = get_column_letter(
            column_index
        )

        max_length = 0

        for cell in column_cells[:300]:

            if cell.value is None:
                continue

            max_length = max(
                max_length,
                len(
                    str(
                        cell.value
                    )
                ),
            )

        worksheet.column_dimensions[
            letter
        ].width = min(
            max(
                max_length + 2,
                10,
                ),
            max_width,
        )


def format_diagnostic_workbook(
        path,
):
    workbook = load_workbook(
        path
    )

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="1F4E78",
    )

    header_font = Font(
        color="FFFFFF",
        bold=True,
    )

    for worksheet in workbook.worksheets:

        if worksheet.max_row < 1:
            continue

        for cell in worksheet[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        if worksheet.max_row >= 2:

            worksheet.freeze_panes = "A2"

            worksheet.auto_filter.ref = (
                f"A1:"
                f"{get_column_letter(worksheet.max_column)}"
                f"{worksheet.max_row}"
            )

        for row in worksheet.iter_rows(
                min_row=2,
                max_row=worksheet.max_row,
        ):

            for cell in row:

                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

        autosize_worksheet(
            worksheet
        )

        # Prozentformat bei Anteil / Wahrscheinlichkeit / Abdeckung / Faktoren
        headers = {
            clean_string(
                cell.value
            ):
                cell.column
            for cell
            in worksheet[1]
            if clean_string(
                cell.value
            )
        }

        for header, column in headers.items():

            if (
                    "Anteil_"
                    in header
                    or
                    "Wahrscheinlichkeit"
                    in header
                    or
                    "Abdeckung"
                    in header
                    or
                    header
                    ==
                    "QX_Anteil_Waermemenge_final"
            ):

                for row in range(
                        2,
                        worksheet.max_row + 1,
                ):

                    worksheet.cell(
                        row=row,
                        column=column,
                    ).number_format = "0.0%"

    workbook.save(
        path
    )


def write_diagnostic_excel(
        folder,
        group_id,
        tables,
):
    if not WRITE_DIAGNOSTIC_EXCEL:
        return None

    path = (
            folder
            / f"Diagnose_{group_id}_Iteration3.xlsx"
    )

    with pd.ExcelWriter(
            path,
            engine="openpyxl",
    ) as writer:

        for sheet_name, df in tables.items():

            if df is None:
                continue

            # Leere Tabellen trotzdem mit Headern schreiben, falls vorhanden.
            df.to_excel(
                writer,
                sheet_name=sheet_name[:31],
                index=False,
            )

    format_diagnostic_workbook(
        path
    )

    return path


# =============================================================================
# 25. EINE GRUPPE VERARBEITEN
# =============================================================================


def process_group(
        group_file,
):
    group_id = group_id_from_path(
        group_file
    )

    print()
    print(
        f"--- {group_id} ---"
    )

    excel = pd.ExcelFile(
        group_file
    )

    if (
            "Abwaermepotentiale"
            not in excel.sheet_names
    ):
        raise ValueError(
            f"{group_id}: Blatt 'Abwaermepotentiale' fehlt."
        )

    raw_potentials = pd.read_excel(
        group_file,
        sheet_name="Abwaermepotentiale",
        dtype=str,
        keep_default_na=False,
    )

    columns = identify_columns(
        raw_potentials
    )

    review, review_path = load_review_table(
        group_id
    )

    has_plausibility_sheet = (
            "Zahlen_Plausibilitaet"
            in excel.sheet_names
    )

    if (
            has_plausibility_sheet
            and
            REQUIRE_REVIEW_FILE_IF_PLAUSIBILITY_EXISTS
            and
            review is None
    ):
        raise FileNotFoundError(
            f"{group_id}: Gruppendatei enthält Zahlen_Plausibilitaet, "
            "aber die fertig geprüfte Datei fehlt:\n"
            f"{review_path}"
        )

    review_errors = validate_review(
        group_id,
        review,
    )

    if review_errors:
        raise ValueError(
            f"{group_id}: Prüfdatei ist noch nicht konsistent:\n\n"
            + "\n".join(
                review_errors[
                :100
                ]
            )
        )

    reviewed = apply_review(
        group_id,
        raw_potentials,
        review,
        columns,
    )

    enriched = enrich_cleaned_potentials(
        group_id,
        reviewed,
        columns,
    )

    # -------------------------------------------------------------------------
    # Sehr starke Betriebsprofil-Donoren deterministisch übernehmen.
    # Profil_WZ_Code wird dabei NICHT verwendet.
    # -------------------------------------------------------------------------

    enriched = (
        complete_operating_profiles_strong_donors(
            enriched
        )
    )

    site_filter = build_site_filter(
        enriched
    )

    (
        blocks,
        mapping,
        generator_sources,
    ) = build_source_blocks(
        group_id,
        enriched,
        site_filter,
    )

    (
        blocks,
        size_cutpoints,
    ) = assign_size_classes(
        blocks
    )

    sites = build_sites_table(
        group_id,
        blocks,
        site_filter,
    )

    # -------------------------------------------------------------------------
    # Preflight erst nach Bildung der finalen Standortanteile.
    # -------------------------------------------------------------------------

    (
        blocks,
        preflight,
    ) = apply_preflight(
        blocks,
        sites,
    )

    site_draw_pool = build_site_draw_pool(
        sites,
        blocks,
    )

    portfolio_frequency = (
        build_portfolio_frequency(
            group_id,
            sites,
        )
    )

    operating_distribution = (
        build_operating_profile_distribution(
            group_id,
            blocks,
        )
    )

    temperature_distribution = (
        build_temperature_distribution(
            group_id,
            blocks,
        )
    )

    seasonality_distribution = (
        build_seasonality_distribution(
            group_id,
            blocks,
        )
    )

    donor_pool = build_donor_pool(
        blocks
    )

    donor_options = (
        build_operating_profile_donor_options(
            blocks
        )
    )

    donor_coverage = (
        build_donor_coverage(
            blocks
        )
    )

    (
        merged_blocks,
        aggregation_candidates,
    ) = build_aggregation_diagnostics(
        group_id,
        generator_sources,
        blocks,
    )

    aggregation_sensitivity_10k = (
        build_aggregation_sensitivity_10k(
            generator_sources
        )
    )

    review_audit = build_review_audit(
        enriched
    )

    exclusion_audit = build_exclusion_audit(
        enriched
    )

    operating_raw_all = (
        build_operating_raw_diagnostics(
            enriched
        )
    )

    generator_original_ids = set(
        mapping[
            "Originaldatensatz_ID"
        ]
        if not mapping.empty
        else []
    )

    enriched_generator = enriched[
        enriched[
            "_Original_ID"
        ].isin(
            generator_original_ids
        )
    ].copy()

    operating_raw_generator = (
        build_operating_raw_diagnostics(
            enriched_generator
        )
        if not enriched_generator.empty
        else pd.DataFrame()
    )

    summary = build_summary(
        group_id,
        raw_potentials,
        enriched,
        site_filter,
        blocks,
        sites,
        review_path,
    )

    # -------------------------------------------------------------------------
    # Ausgabeordner
    # -------------------------------------------------------------------------

    group_output = (
            OUTPUT_DIR
            /
            group_id
    )

    group_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    if OVERWRITE_GROUP_OUTPUT:
        for old_file in group_output.iterdir():
            if old_file.is_file():
                old_file.unlink()

    # -------------------------------------------------------------------------
    # Bereinigte Originalpotentiale
    # -------------------------------------------------------------------------

    cleaned_export_columns = [
        "_Original_ID",
        "Experiment_Gruppe",
        "Standortverbund_ID_final",
        "Profil_WZ_Code_final",
        "WZ3_Code_final",
        "Quellklasse_final",
        "Quellenname_final",
        "Quellenfamilie_normalisiert",

        "Waermemenge_original_kWh_a",
        "Waermemenge_final_kWh_a",
        "Korrektur_Waermemenge",

        "Leistung_original_kW",
        "Leistung_final_kW",
        "Korrektur_Leistung",

        "Temperatur_original_C",
        "Temperatur_final_C",
        "Korrektur_Temperatur",
        "Temperaturklasse_final",

        "Pruefstatus_final",
        "Ausgeschlossen_final",
        "Ausschluss_Effekt",
        "Ausschluss_Effekt_Herkunft",
        "Ausschlussgrund_final",
        "Pruefbegruendung_final",
        "Begruendungsgrundlage_final",

        "Betriebsprofil_Roh_Verfuegbarkeit",
        "Betriebsprofil_Roh_h_pro_Tag",
        "Betriebsprofil_Roh_Wochenende",
        "Betriebsprofil_Code_original_abgeleitet",
        "Betriebsprofil_Abgeleitet_h_pro_Tag",
        "Betriebsprofil_Abgeleitet_Tage_pro_Woche",
        "Betriebsprofil_Standard_h_pro_Tag",
        "Betriebsprofil_Standard_Tage_pro_Woche",
        "Betriebsprofil_Generator_h_pro_Tag",
        "Betriebsprofil_Generator_Tage_pro_Woche",
        "Betriebsprofil_Code",
        "Betriebsprofil_Herkunft",
        "Betriebsprofil_Qualitaet",
        "Betriebsprofil_deterministisch_ergaenzt",
        "Betriebsprofil_Ergaenzungsgrund",
        "Betriebsprofil_Donor_Originaldatensatz_IDs",

        "Saison_Monate_vorhanden",
        "Saison_Nullmonate",
        "Saison_Aktive_Monate",
        "Saison_Profil_gueltig",
        "Saisonfaktor_Sommer",
        "Saisonfaktor_Winter",
        "Saison_Konzentration_HHI",
        "Saison_Konzentration_0_1",

        "Vorhersagbarkeit_raw",
        "Regelungsmoeglichkeiten_raw",
    ]

    for month, _ in MONTHS:
        cleaned_export_columns.append(
            f"Saison_Roh_{month}"
        )

        cleaned_export_columns.append(
            f"Saison_Faktor_{month}"
        )

    cleaned_export_columns = [
        column
        for column
        in cleaned_export_columns
        if column
           in enriched.columns
    ]

    cleaned_potentials = enriched[
        cleaned_export_columns
    ].copy()

    cleaned_potentials = (
        cleaned_potentials
        .rename(
            columns={
                "_Original_ID":
                    "Originaldatensatz_ID",
            }
        )
    )

    datasets = {
        "cleaned_potentials":
            cleaned_potentials,

        "source_blocks":
            blocks,

        "sites":
            sites,

        "site_draw_pool":
            site_draw_pool,

        "mapping_original_to_block":
            mapping,

        "portfolio_frequency":
            portfolio_frequency,

        "operating_profile_distribution":
            operating_distribution,

        "temperature_distribution":
            temperature_distribution,

        "seasonality_distribution":
            seasonality_distribution,

        "donor_pool":
            donor_pool,

        "operating_profile_donor_options":
            donor_options,

        "size_class_cutpoints":
            size_cutpoints,

        "preflight":
            preflight,

        "aggregation_sensitivity_10k":
            aggregation_sensitivity_10k,
    }

    for name, df in datasets.items():
        write_dataframe_files(
            group_output,
            name,
            df,
        )

    metadata = {
        "iteration":
            3,

        "experiment_group":
            group_id,

        "source_group_file":
            str(
                group_file.resolve()
            ),

        "review_file":
            (
                str(
                    review_path.resolve()
                )
                if (
                        review_path is not None
                        and
                        review_path.exists()
                )
                else None
            ),

        "profile_wz_used_as_model_condition":
            False,

        "qx_heat_threshold":
            QX_HEAT_THRESHOLD,

        "excluded_default_effect":
            EXCLUSION_EFFECT_UNRESOLVED,

        "duplicate_or_nonphysical_effect":
            EXCLUSION_EFFECT_REMOVE,

        "operating_profile_standard_hours":
            STANDARD_DAILY_HOURS,

        "operating_profile_standard_days":
            STANDARD_DAYS_PER_WEEK,

        "special_operating_profiles_retained":
            True,

        "aggregation_max_temperature_span_c":
            AGGREGATION_MAX_TEMPERATURE_SPAN_C,

        "aggregation_sensitivity_temperature_span_c":
            AGGREGATION_SENSITIVITY_TEMPERATURE_SPAN_C,

        "seasonality_is_aggregation_key":
            False,

        "strong_operating_profile_completion":
            (
                "same site + Q + normalized family + unanimous known profile"
            ),

        "notes": [
            (
                "Profil_WZ_Code wird nur zur Rueckverfolgbarkeit "
                "mitgefuehrt und nicht als Zieh-/Donorbedingung verwendet."
            ),
            (
                "Portfolio und relative Blockgroessen bleiben gemeinsam "
                "empirisch auf Standortebene erhalten."
            ),
            (
                "Preflight-Auffaelligkeiten loeschen keine Waerme automatisch."
            ),
            (
                "Unplausible technische Attribute werden nur als Donoren gesperrt."
            ),
            (
                "5 K ist die produktive Aggregationsregel; 10 K nur Sensitivitaet."
            ),
            (
                "Der vollstaendige 12-Monats-Vektor bleibt die Saisonform."
            ),
        ],
    }

    with open(
            group_output
            /
            "metadata.json",
            "w",
            encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2,
        )

    excluded_sites = site_filter[
        ~site_filter[
            "Geeignet_QX20_final"
        ]
    ].copy()

    diagnostic_tables = {
        "Zusammenfassung":
            summary,

        "Review_Audit":
            review_audit,

        "Ausschluss_Effekte":
            exclusion_audit,

        "Standort_QX20":
            site_filter,

        "Ausgeschl_Standorte":
            excluded_sites,

        "Preflight":
            preflight,

        "Preflight_auffaellig":
            preflight[
                preflight[
                    "Preflight_Status"
                ].ne(
                    "OK"
                )
            ]
            if not preflight.empty
            else preflight,

        "Standorte_final":
            sites,

        "Site_Draw_Pool":
            site_draw_pool,

        "Portfolio":
            portfolio_frequency,

        "Betriebsprofile":
            operating_distribution,

        "Betrieb_Roh_alle":
            operating_raw_all,

        "Betrieb_Roh_generator":
            operating_raw_generator,

        "Unbek_Betrieb_Donoren":
            donor_options,

        "Donor_Abdeckung":
            donor_coverage,

        "Saisonalitaet":
            seasonality_distribution,

        "Temperaturen":
            temperature_distribution,

        "Groessenklassen":
            size_cutpoints,

        "Aggregierte_Bloecke":
            merged_blocks,

        "Aggregations_Kandidaten":
            aggregation_candidates,

        "Aggregation_10K_Sens":
            aggregation_sensitivity_10k,

        "Block_Stichprobe":
            blocks.head(
                300
            ),
    }

    diagnostic_path = (
        write_diagnostic_excel(
            group_output,
            group_id,
            diagnostic_tables,
        )
    )

    if not blocks.empty:
        standard_bp = int(
            blocks[
                "Betriebsprofil_Code"
            ]
            .str.match(
                r"^BP_(8|12|16|20|24)x(5|7)$"
            )
            .sum()
        )

        exact_bp = int(
            blocks[
                "Betriebsprofil_Code"
            ]
            .str.startswith(
                "BP_EXAKT_"
            )
            .sum()
        )

        unknown_bp = int(
            blocks[
                "Betriebsprofil_Code"
            ]
            .eq(
                "BP_UNBEKANNT"
            )
            .sum()
        )

        hard_preflight = int(
            blocks[
                "Preflight_Status"
            ]
            .eq(
                "HARTER_PRUEFFALL"
            )
            .sum()
        )

    else:
        standard_bp = 0
        exact_bp = 0
        unknown_bp = 0
        hard_preflight = 0

    deterministic_completed = int(
        enriched[
            "Betriebsprofil_deterministisch_ergaenzt"
        ].sum()
    )

    print(
        f"      Originalpotentiale: {len(raw_potentials):,}"
    )

    print(
        "      finale geeignete Standorte: "
        f"{int(site_filter['Geeignet_QX20_final'].sum()) if not site_filter.empty else 0:,}"
    )

    print(
        f"      Generatorblöcke: {len(blocks):,}"
    )

    print(
        f"      Standard-Betriebsprofile: {standard_bp:,}"
    )

    print(
        f"      exakte Sonderprofile: {exact_bp:,}"
    )

    print(
        f"      unbekannte Betriebsprofile: {unknown_bp:,}"
    )

    print(
        "      deterministisch ergänzte Betriebsprofile: "
        f"{deterministic_completed:,}"
    )

    print(
        f"      Preflight harte Prüffälle: {hard_preflight:,}"
    )

    print(
        f"      Portfoliotypen: {len(portfolio_frequency):,}"
    )

    if diagnostic_path:
        print(
            f"      Diagnose: {diagnostic_path.name}"
        )

    return {
        "Experiment_Gruppe":
            group_id,

        "Originalpotentiale":
            int(
                len(
                    raw_potentials
                )
            ),

        "Finale_Standorte":
            int(
                len(
                    sites
                )
            ),

        "Generator_Bloecke":
            int(
                len(
                    blocks
                )
            ),

        "Portfoliotypen":
            int(
                len(
                    portfolio_frequency
                )
            ),

        "Preflight_Harte_Prueffaelle":
            hard_preflight,

        "Diagnose_Datei":
            (
                diagnostic_path.name
                if diagnostic_path
                else ""
            ),
    }

def write_global_overview(
        rows,
):
    if not rows:
        return

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    overview = pd.DataFrame(
        rows
    )

    overview.to_csv(
        OUTPUT_DIR
        / "_Uebersicht_Iteration3.csv",
        sep=";",
        encoding="utf-8-sig",
        index=False,
        )

    try:

        overview.to_parquet(
            OUTPUT_DIR
            / "_Uebersicht_Iteration3.parquet",
            index=False,
            )

    except Exception:
        pass


# =============================================================================
# 27. HAUPTPROGRAMM
# =============================================================================

def main():

    print()
    print("=" * 88)
    print(
        "GENERATOR-DATENPAKETE – ITERATION 3"
    )
    print("=" * 88)
    print()

    if not GROUP_DIR.exists():

        raise FileNotFoundError(
            "Gruppenordner nicht gefunden:\n"
            f"{GROUP_DIR}"
        )

    group_files = [
        file
        for file
        in GROUP_DIR.glob(
            GROUP_PATTERN
        )
        if not file.name.startswith(
            "~$"
        )
    ]

    group_files = sorted(
        group_files
    )

    if TARGET_GROUPS is not None:

        wanted = {
            clean_string(
                group
            ).upper()
            for group
            in TARGET_GROUPS
        }

        group_files = [
            file
            for file
            in group_files
            if group_id_from_path(
                file
            )
               in wanted
        ]

    if not group_files:

        raise FileNotFoundError(
            "Keine passenden Profilgruppe_G*.xlsx-Dateien gefunden."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Zu verarbeitende Gruppen: {len(group_files):,}"
    )

    if TARGET_GROUPS is not None:

        print(
            "Auswahl: "
            + ", ".join(
                TARGET_GROUPS
            )
        )

    overview_rows = []

    failures = []

    for group_file in group_files:

        group_id = group_id_from_path(
            group_file
        )

        try:

            result = process_group(
                group_file
            )

            overview_rows.append(
                result
            )

        except Exception as exc:

            failures.append(
                {
                    "Experiment_Gruppe":
                        group_id,

                    "Fehler":
                        str(
                            exc
                        ),
                }
            )

            print()
            print(
                f"FEHLER in {group_id}:"
            )
            print(
                exc
            )

    write_global_overview(
        overview_rows
    )

    if failures:

        pd.DataFrame(
            failures
        ).to_csv(
            OUTPUT_DIR
            / "_Fehler_Iteration3.csv",
            sep=";",
            encoding="utf-8-sig",
            index=False,
            )

    print()
    print("=" * 88)
    print("FERTIG")
    print("=" * 88)
    print()

    print(
        f"Erfolgreich: {len(overview_rows):,} Gruppen"
    )

    print(
        f"Fehler:      {len(failures):,} Gruppen"
    )

    print()
    print(
        "Ausgabeordner:"
    )

    print(
        OUTPUT_DIR.resolve()
    )

    print()
    print(
        "Für die nächste Iteration bitte vorzugsweise für eine große Gruppe "
        "zurückgeben:"
    )

    print(
        "  1. Diagnose_Gxx_Iteration3.xlsx"
    )

    print(
        "  2. optional source_blocks.csv"
    )

    print(
        "  3. optional sites.csv"
    )

    print()
    print(
        "Besonders interessant für Iteration 3:"
    )

    print(
        "  - Verteilung der Roh-Betriebsprofile"
    )

    print(
        "  - Anteil BP_UNBEKANNT / BP_SONSTIG"
    )

    print(
        "  - Saisonalitätsabdeckung"
    )

    print(
        "  - Aggregations_Kandidaten"
    )

    print(
        "  - Anzahl und Häufigkeit der Quellenportfolios"
    )

    print(
        "  - Temperaturverteilungen je Q-Klasse"
    )

    print("=" * 88)


# =============================================================================
# 28. PROGRAMMSTART
# =============================================================================

if __name__ == "__main__":

    main()
