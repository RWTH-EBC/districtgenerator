from pathlib import Path
import re

import numpy as np
import pandas as pd

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter


# ============================================================
# 1. KONFIGURATION
# ============================================================
#
# DIESER CODE ERSETZT DEN BISHERIGEN CODE ZUR ERSTELLUNG DER
# MANUELLEN WZ-GRUPPIERUNGS-EXCEL VOLLSTÄNDIG.
#
# Grundlage ist jetzt NICHT mehr der QX-Anteil der Leistung,
# sondern ausschließlich:
#
#     QX_Anteil_Waermemenge_bearbeitet
#
# und der im vorherigen Postprocessing erzeugte VORLÄUFIGE
# Eignungsstatus:
#
#     Geeignet_QX_Waermemenge_max_20pct_vorlaeufig
#
# Plausibilitätsauffällige Wärmemengen werden an dieser Stelle
# bewusst NICHT herausgefiltert. Sie werden nur als
# Qualitätsinformation mitgeführt.
# ============================================================

BASE_DIR = Path("WZ2025_Vorbereitung")
SOURCE_DIR = BASE_DIR / "Quellenklassifikation_final"

INPUT_FILE = SOURCE_DIR / "Branchenanalyse_Q1_Q7_v2.xlsx"
INPUT_SHEET = "Standort_Analyse"

# Die neue Arbeitsmappe kann denselben Namen wie bisher verwenden.
# Bestehende manuelle G01/G02/...-Zuordnungen werden VOR dem
# Überschreiben nach Möglichkeit eingelesen und übernommen.
OUTPUT_FILE = (
        SOURCE_DIR
        / "WZ_Gruppen_Zusammenlegung_Experiment.xlsx"
)

# Zusätzlich werden auch ältere/alternative Dateien nach bereits
# vorgenommenen manuellen Zuordnungen durchsucht.
EXISTING_FILE_PATTERNS = [
    "WZ_Gruppen_Zusammenlegung_Experiment.xlsx",
    "WZ_Gruppen_Zusammenlegung_Experiment_GPT.xlsx",
    "WZ_Gruppen_Zusammenlegung_Experiment*.xlsx",
]

# Neue zentrale Regel.
QX_HEAT_THRESHOLD = 0.20

# Mehr als 40 bzw. 60 Experimentgruppen bleiben problemlos möglich.
MAX_EXPERIMENT_GROUPS = 100


# ============================================================
# 2. BEKANNTE WZ-BEZEICHNUNGEN / FALLBACKS
# ============================================================

WZ3_LABEL_FALLBACKS = {
    "05.1": "Steinkohlenbergbau",
}


# ============================================================
# 3. SPALTENERKLÄRUNGEN FÜR DIE EXCELDATEI
# ============================================================

COLUMN_EXPLANATIONS = {

    "WZ3_Code":
        "WZ-2025-Gruppe auf WZ3-Ebene, z. B. 22.2.",

    "WZ2_Code":
        "Übergeordnete zweistellige WZ-Abteilung.",

    "Profil_WZ_Code":
        "Feinster für die Profilbildung verwendeter WZ-Code; "
        "bewusst auch feiner als WZ3 möglich, z. B. 38.21.",

    "Kurzname":
        "Kurze Branchen- bzw. Gruppenbezeichnung.",

    "Standorte_gesamt":
        "Anzahl physischer Standortprofile vor dem vorläufigen "
        "20-%-QX-Wärmemengenfilter.",

    "Unternehmen_gesamt":
        "Anzahl unterschiedlicher Unternehmen hinter den "
        "ungefilterten Standorten.",

    "Standorte_QX_Waermemenge_max_20pct_vorlaeufig":
        "Anzahl der vorläufig geeigneten Standorte. Grundlage ist "
        "QX <= 20 % der gemeldeten Jahreswärmemenge. "
        "Plausibilitätsauffällige positive Wärmemengen werden noch "
        "nicht herausgefiltert.",

    "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig":
        "Anzahl unterschiedlicher Unternehmen unter den vorläufig "
        "geeigneten Standorten.",

    "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig":
        "Anteil der ursprünglichen Standorte, der nach dem "
        "vorläufigen Wärmemengen-QX-Filter verbleibt.",

    "Mittlerer_QX_Waermengenanteil":
        "Mittlerer Anteil von QX an der gemeldeten Jahreswärmemenge "
        "über alle Standorte der WZ-Gruppe.",

    "Median_QX_Waermengenanteil":
        "Median des QX-Anteils an der gemeldeten Jahreswärmemenge.",

    "Standorte_Zahlenpruefung_hoch_gesamt":
        "Standorte mit mindestens einer Quelle hoher "
        "Zahlen-Prüfpriorität. Diese Standorte werden noch NICHT "
        "automatisch ausgeschlossen.",

    "Standorte_Zahlenpruefung_hoch_unter_Geeigneten":
        "Vorläufig geeignete Standorte, die mindestens eine Quelle "
        "mit hoher Zahlen-Prüfpriorität enthalten.",

    "Anteil_geeignete_Standorte_mit_Zahlenpruefung_hoch":
        "Anteil der vorläufig geeigneten Standorte mit mindestens "
        "einem Zahlenproblem hoher Prüfpriorität.",

    "Standorte_Eignung_kann_sich_aendern":
        "Vorläufig geeignete Standorte, deren endgültiger "
        "20-%-Status sich nach Prüfung/Korrektur auffälliger "
        "Zahlenwerte noch ändern kann.",

    "Standorte_groesstes_Unternehmen_QX20":
        "Anzahl vorläufig geeigneter Standorte des am stärksten "
        "vertretenen einzelnen Unternehmens.",

    "Anteil_groesstes_Unternehmen_QX20":
        "Anteil des größten einzelnen Unternehmens an den "
        "vorläufig geeigneten Standorten.",

    "Anzahl_enthaltener_WZ3_Gruppen":
        "Anzahl unterschiedlicher WZ3-Gruppen innerhalb dieser "
        "WZ2-Gruppe.",

    "Enthaltene_WZ3_Codes":
        "Alle unterschiedlichen WZ3-Codes innerhalb der jeweiligen "
        "WZ2- bzw. Experimentgruppe.",

    "Enthaltene_WZ3_Bezeichnungen":
        "Kurzbezeichnungen der enthaltenen WZ3-Gruppen.",

    "Experiment_Gruppe":
        "Manuell zu vergebende Kennung. Profil-WZ-Gruppen mit "
        "derselben Kennung werden gemeinsam ausgewertet, z. B. G01.",

    "Kommentar":
        "Freies Notizfeld für die fachliche Begründung der "
        "Zusammenlegung.",

    "Anzahl_Profil_WZ_Gruppen":
        "Anzahl einzelner Profil-WZ-Codes, die dieser "
        "Experimentgruppe zugeordnet sind.",

    "Anzahl_WZ3_Gruppen":
        "Anzahl unterschiedlicher WZ3-Codes innerhalb der fertigen "
        "Experimentgruppe.",
}


# ============================================================
# 4. ALLGEMEINE HILFSFUNKTIONEN
# ============================================================

def clean_string(value) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in {"nan", "none"}:
        return ""

    return text


def normalize_wz_code(value) -> str:
    """
    Erhält die vorhandene WZ-Tiefe.

    Beispiele:
        38.21 -> 38.21
        38.2  -> 38.2
        6.1   -> 06.1
        05.1  -> 05.1
        0.5.1 -> 05.1
    """

    text = (
        clean_string(value)
        .replace(",", ".")
        .replace(" ", "")
    )

    if not text:
        return ""

    malformed = re.fullmatch(
        r"0\.(\d)\.(\d+)",
        text,
    )

    if malformed:
        return f"0{malformed.group(1)}.{malformed.group(2)}"

    match = re.match(
        r"^(\d{1,2})(.*)$",
        text,
    )

    if not match:
        return text

    return (
        f"{int(match.group(1)):02d}"
        f"{match.group(2)}"
    )


def derive_wz3(value) -> str:
    text = normalize_wz_code(value)

    match = re.match(
        r"^(\d{2})\.(\d)",
        text,
    )

    if not match:
        return ""

    return f"{match.group(1)}.{match.group(2)}"


def derive_wz2(value) -> str:
    text = normalize_wz_code(value)

    match = re.match(
        r"^(\d{2})",
        text,
    )

    if not match:
        return ""

    return match.group(1)


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
            f"{label} nicht gefunden.\n\n"
            "Gesuchte Kandidaten:\n"
            + "\n".join(f"- {column}" for column in candidates)
        )

    return None


def numeric_fraction(series: pd.Series) -> pd.Series:
    """
    Wandelt z. B. 0.2, 20, '20 %' oder '20,0%' in 0..1 um.
    """

    def convert(value):
        text = clean_string(value)

        if not text:
            return np.nan

        has_percent = "%" in text

        text = (
            text
            .replace("%", "")
            .replace(" ", "")
            .replace(",", ".")
        )

        try:
            number = float(text)

        except ValueError:
            return np.nan

        if has_percent:
            return number / 100.0

        if 1 < number <= 100:
            return number / 100.0

        return number

    return series.map(convert)


def numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.map(
            lambda value:
            clean_string(value).replace(",", ".")
        ),
        errors="coerce",
    )


def bool_series(series: pd.Series) -> pd.Series:
    """
    Robuste Umwandlung von Excel-/pandas-Werten in bool.
    """

    true_values = {
        "true",
        "wahr",
        "1",
        "ja",
        "yes",
        "y",
    }

    false_values = {
        "false",
        "falsch",
        "0",
        "nein",
        "no",
        "n",
        "",
    }

    def convert(value):
        if isinstance(value, bool):
            return value

        if pd.isna(value):
            return False

        if isinstance(value, (int, float, np.integer, np.floating)):
            return bool(value)

        text = clean_string(value).casefold()

        if text in true_values:
            return True

        if text in false_values:
            return False

        return False

    return series.map(convert)


def mode_non_empty(series) -> str:
    values = series.map(clean_string)
    values = values[values.ne("")]

    if values.empty:
        return ""

    return clean_string(
        values.value_counts().index[0]
    )


def unique_non_empty(series):
    seen = set()
    result = []

    for value in series:
        value = clean_string(value)

        if value and value not in seen:
            seen.add(value)
            result.append(value)

    return result


def safe_ratio(numerator, denominator):
    if (
            denominator is None
            or denominator == 0
            or pd.isna(denominator)
    ):
        return np.nan

    return numerator / denominator


def format_experiment_group_id(index: int) -> str:
    if index <= 99:
        return f"G{index:02d}"

    return f"G{index}"


# ============================================================
# 5. BISHERIGE MANUELLE ZUORDNUNGEN SUCHEN
# ============================================================

def candidate_existing_files():
    """
    Liefert mögliche alte/neue Gruppierungsdateien,
    ohne temporäre Excel-Dateien (~$...) zu berücksichtigen.
    """

    candidates = []

    if OUTPUT_FILE.exists():
        candidates.append(OUTPUT_FILE)

    for pattern in EXISTING_FILE_PATTERNS:
        for file in SOURCE_DIR.glob(pattern):
            if file.name.startswith("~$"):
                continue

            if file not in candidates:
                candidates.append(file)

    # Neueste Dateien zuerst.
    candidates = sorted(
        candidates,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    # Das exakte OUTPUT_FILE soll trotzdem höchste Priorität haben.
    if OUTPUT_FILE in candidates:
        candidates.remove(OUTPUT_FILE)
        candidates.insert(0, OUTPUT_FILE)

    return candidates


def find_header_row(
        file_path,
        sheet_name,
        required_header,
        max_rows=20,
):
    preview = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        header=None,
        nrows=max_rows,
        dtype=str,
        keep_default_na=False,
    )

    for row_index in range(len(preview)):
        values = {
            clean_string(value)
            for value
            in preview.iloc[row_index].tolist()
        }

        if required_header in values:
            return row_index

    return None


def load_existing_manual_inputs():
    """
    Übernimmt bestehende:
      - Experiment_Gruppe
      - Kommentar

    aus alter Einblatt-Version und/oder neuer Split-Version.

    Dadurch bleiben deine bisherigen fachlichen G01/G02/...
    Zuordnungen auch dann erhalten, wenn ein WZ-Code durch den neuen
    Wärmemengenfilter vom >2-Blatt auf das <=2-Blatt wechselt.
    """

    assignments = {}
    comments = {}

    possible_sheets = [
        "Zusammenlegung",
        "Zusammenlegung_gt2",
        "Zusammenlegung_bis2",
    ]

    used_file = None

    for existing_file in candidate_existing_files():

        try:
            excel = pd.ExcelFile(existing_file)

            found_any = False

            for sheet_name in possible_sheets:

                if sheet_name not in excel.sheet_names:
                    continue

                header_row = find_header_row(
                    existing_file,
                    sheet_name,
                    "Profil_WZ_Code",
                )

                if header_row is None:
                    continue

                old = pd.read_excel(
                    existing_file,
                    sheet_name=sheet_name,
                    header=header_row,
                    dtype=str,
                    keep_default_na=False,
                )

                if "Profil_WZ_Code" not in old.columns:
                    continue

                for _, row in old.iterrows():

                    code = normalize_wz_code(
                        row.get(
                            "Profil_WZ_Code",
                            "",
                        )
                    )

                    if not code:
                        continue

                    group_id = clean_string(
                        row.get(
                            "Experiment_Gruppe",
                            "",
                        )
                    ).upper()

                    comment = clean_string(
                        row.get(
                            "Kommentar",
                            "",
                        )
                    )

                    if group_id and code not in assignments:
                        assignments[code] = group_id
                        found_any = True

                    if comment and code not in comments:
                        comments[code] = comment

            if found_any and used_file is None:
                used_file = existing_file

        except Exception:
            # Eine einzelne nicht lesbare Altdatei soll den neuen Lauf
            # nicht verhindern.
            continue

    if used_file is not None:
        print(
            f"   -> bestehende Eingaben wurden aus "
            f"'{used_file.name}' und ggf. weiteren passenden Dateien "
            "übernommen"
        )

    return assignments, comments


# ============================================================
# 6. NEUE BRANCHENANALYSE EINLESEN
# ============================================================

def load_data() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Eingabedatei nicht gefunden:\n{INPUT_FILE}"
        )

    return pd.read_excel(
        INPUT_FILE,
        sheet_name=INPUT_SHEET,
        dtype=str,
        keep_default_na=False,
    )


# ============================================================
# 7. STANDORTDATEN VORBEREITEN
# ============================================================

def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Zentrale Umstellung auf den neuen Standard:

    - Profil-WZ bleibt exakt erhalten, z. B. 38.21.
    - Eignung basiert auf Jahreswärmemenge, NICHT auf Leistung.
    - Plausibilitätsauffällige positive Wärmemengen werden NICHT
      herausgefiltert.
    - Qualitätsprobleme werden separat mitgeführt.
    """

    data = df.copy()

    # --------------------------------------------------------
    # Standort-ID
    # --------------------------------------------------------

    site_column = first_existing_column(
        data,
        [
            "Standortverbund_ID",
            "Klassifikations_ID",
        ],
        required=True,
        label="physische Standort-ID",
    )

    data["_Standort_ID"] = (
        data[site_column]
        .map(clean_string)
    )

    if data["_Standort_ID"].eq("").any():
        raise ValueError(
            "Mindestens eine Zeile besitzt keine physische Standort-ID."
        )

    if not data["_Standort_ID"].is_unique:
        raise ValueError(
            "Das Blatt 'Standort_Analyse' enthält mehr als eine "
            "Zeile je physischem Standort."
        )

    # --------------------------------------------------------
    # Unternehmen
    # --------------------------------------------------------

    company_column = first_existing_column(
        data,
        [
            "_Company_Key",
            "Unternehmens_ID",
            "Profil_Unternehmens_ID",
        ],
    )

    company_name_column = first_existing_column(
        data,
        [
            "Profil_Firmenname",
            "Firmenname",
        ],
    )

    if company_column:
        data["_Unternehmen_Key"] = (
            data[company_column]
            .map(clean_string)
        )

    else:
        data["_Unternehmen_Key"] = ""

    if company_name_column:
        mask = data["_Unternehmen_Key"].eq("")

        data.loc[
            mask,
            "_Unternehmen_Key",
        ] = (
            data.loc[
                mask,
                company_name_column,
            ]
            .map(clean_string)
            .map(
                lambda value:
                f"NAME::{value.casefold()}"
                if value
                else ""
            )
        )

    mask = data["_Unternehmen_Key"].eq("")

    data.loc[
        mask,
        "_Unternehmen_Key",
    ] = (
            "SITE::"
            + data.loc[
                mask,
                "_Standort_ID",
            ]
    )

    # --------------------------------------------------------
    # WZ-Codes
    # --------------------------------------------------------

    final_wz_column = first_existing_column(
        data,
        [
            "Profil_WZ_Final_Code",
            "WZ_Final_Code",
            "Profil_WZ3_Code",
            "WZ3_Code",
        ],
        required=True,
        label="Profil-WZ-Code",
    )

    wz3_column = first_existing_column(
        data,
        [
            "Profil_WZ3_Code",
            "WZ3_Code",
        ],
    )

    wz2_column = first_existing_column(
        data,
        [
            "Profil_WZ2_Code",
            "WZ2_Code",
        ],
    )

    wz3_label_column = first_existing_column(
        data,
        [
            "Profil_WZ3_Bezeichnung",
            "Profil_WZ_Gruppe_Bezeichnung",
            "WZ3_Bezeichnung",
            "WZ_Gruppe_Bezeichnung",
        ],
    )

    wz2_label_column = first_existing_column(
        data,
        [
            "Profil_WZ2_Bezeichnung",
            "WZ2_Bezeichnung",
        ],
    )

    data["_Profil_WZ_Code"] = (
        data[final_wz_column]
        .map(normalize_wz_code)
    )

    if wz3_column:
        data["_WZ3_Code"] = (
            data[wz3_column]
            .map(normalize_wz_code)
        )

    else:
        data["_WZ3_Code"] = (
            data["_Profil_WZ_Code"]
            .map(derive_wz3)
        )

    missing_wz3 = data["_WZ3_Code"].eq("")

    data.loc[
        missing_wz3,
        "_WZ3_Code",
    ] = (
        data.loc[
            missing_wz3,
            "_Profil_WZ_Code",
        ]
        .map(derive_wz3)
    )

    if wz2_column:
        data["_WZ2_Code"] = (
            data[wz2_column]
            .map(normalize_wz_code)
        )

    else:
        data["_WZ2_Code"] = (
            data["_Profil_WZ_Code"]
            .map(derive_wz2)
        )

    missing_wz2 = data["_WZ2_Code"].eq("")

    data.loc[
        missing_wz2,
        "_WZ2_Code",
    ] = (
        data.loc[
            missing_wz2,
            "_Profil_WZ_Code",
        ]
        .map(derive_wz2)
    )

    # --------------------------------------------------------
    # Bezeichnungen
    # --------------------------------------------------------

    if wz3_label_column:
        data["_WZ3_Bezeichnung"] = (
            data[wz3_label_column]
            .map(clean_string)
        )

    else:
        data["_WZ3_Bezeichnung"] = ""

    for code, label in WZ3_LABEL_FALLBACKS.items():

        mask = (
                data["_WZ3_Code"].eq(code)
                & data["_WZ3_Bezeichnung"].eq("")
        )

        data.loc[
            mask,
            "_WZ3_Bezeichnung",
        ] = label

    if wz2_label_column:
        data["_WZ2_Bezeichnung"] = (
            data[wz2_label_column]
            .map(clean_string)
        )

    else:
        data["_WZ2_Bezeichnung"] = ""

    # ========================================================
    # NEUER QX-STANDARD: JAHRESWÄRMEMENGE
    # ========================================================

    qx_heat_column = first_existing_column(
        data,
        [
            "QX_Anteil_Waermemenge_bearbeitet",
            "Waermengenanteil_QX_bearbeitet",
        ],
        required=True,
        label="QX-Anteil an der Jahreswärmemenge",
    )

    data["_QX_Anteil_Waermemenge"] = (
        numeric_fraction(
            data[qx_heat_column]
        )
    )

    invalid_qx = (
            data["_QX_Anteil_Waermemenge"].notna()
            & (
                    (data["_QX_Anteil_Waermemenge"] < -1e-9)
                    | (data["_QX_Anteil_Waermemenge"] > 1.000001)
            )
    )

    if invalid_qx.any():
        raise ValueError(
            "Mindestens ein QX-Wärmemengenanteil liegt außerhalb 0..1."
        )

    # --------------------------------------------------------
    # Vorläufige Eignung:
    #
    # Bevorzugt wird das Feld aus dem unmittelbar vorherigen
    # Postprocessing. Nur falls es fehlt, wird konservativ aus den
    # vorhandenen Feldern rekonstruiert.
    # --------------------------------------------------------

    suitability_column = first_existing_column(
        data,
        [
            "Geeignet_QX_Waermemenge_max_20pct_vorlaeufig",
            "Geeignet_QX_Waermemenge_max_20pct",
        ],
    )

    if suitability_column:

        data["_Filter_QX20_WAERME"] = (
            bool_series(
                data[suitability_column]
            )
        )

    else:

        profile_usable_column = first_existing_column(
            data,
            [
                "Waermemengenprofil_auswertbar",
            ],
        )

        if profile_usable_column:
            usable = bool_series(
                data[profile_usable_column]
            )

        else:
            usable = (
                data["_QX_Anteil_Waermemenge"].notna()
            )

        data["_Filter_QX20_WAERME"] = (
                data["_Profil_WZ_Code"].ne("")
                & usable
                & data["_QX_Anteil_Waermemenge"].notna()
                & (
                        data["_QX_Anteil_Waermemenge"]
                        <= QX_HEAT_THRESHOLD
                )
        )

    # ========================================================
    # ZAHLENQUALITÄT:
    # nur Diagnose – KEIN Ausschluss
    # ========================================================

    hard_column = first_existing_column(
        data,
        [
            "Anzahl_Quellen_Zahlenpruefung_hoch",
        ],
    )

    medium_column = first_existing_column(
        data,
        [
            "Anzahl_Quellen_Zahlenpruefung_mittel",
        ],
    )

    change_column = first_existing_column(
        data,
        [
            "QX20_Eignung_kann_sich_durch_Zahlenpruefung_aendern",
        ],
    )

    if hard_column:
        hard_numeric = (
            numeric_series(
                data[hard_column]
            )
            .fillna(0)
        )

        data["_Zahlenpruefung_hoch"] = (
            hard_numeric.gt(0)
        )

    else:
        data["_Zahlenpruefung_hoch"] = False

    if medium_column:
        medium_numeric = (
            numeric_series(
                data[medium_column]
            )
            .fillna(0)
        )

        data["_Zahlenpruefung_mittel"] = (
            medium_numeric.gt(0)
        )

    else:
        data["_Zahlenpruefung_mittel"] = False

    if change_column:
        data["_Eignung_kann_sich_aendern"] = (
            bool_series(
                data[change_column]
            )
        )

    else:
        # Konservativer Fallback:
        # hoher Prüfbedarf kann die Wärmemengenanteile verändern.
        data["_Eignung_kann_sich_aendern"] = (
            data["_Zahlenpruefung_hoch"]
        )

    return data


# ============================================================
# 8. GRUPPENKENNZAHLEN
# ============================================================

def subset_metrics(group, mask):
    subset = group.loc[mask]

    return {
        "Standorte":
            int(len(subset)),

        "Unternehmen":
            int(
                subset["_Unternehmen_Key"]
                .replace("", pd.NA)
                .dropna()
                .nunique()
            ),
    }


def largest_company_metrics(subset):
    if subset.empty:
        return 0, np.nan

    counts = (
        subset["_Unternehmen_Key"]
        .replace("", pd.NA)
        .dropna()
        .value_counts()
    )

    if counts.empty:
        return 0, np.nan

    largest = int(counts.iloc[0])

    return (
        largest,
        safe_ratio(
            largest,
            len(subset),
        ),
    )


def wz2_description(group) -> str:
    explicit = mode_non_empty(
        group["_WZ2_Bezeichnung"]
    )

    if explicit:
        return explicit

    labels = unique_non_empty(
        group["_WZ3_Bezeichnung"]
    )

    if not labels:
        return ""

    if len(labels) <= 2:
        return " / ".join(labels)

    return (
            " / ".join(labels[:2])
            + " / ..."
    )


def build_group_summary(
        data,
        level,
) -> pd.DataFrame:
    """
    level:
        FINAL -> feinster Profil-WZ-Code
        WZ3
        WZ2

    Alle Filterkennzahlen beruhen jetzt auf der JAHRESWÄRMEMENGE.
    """

    if level == "FINAL":
        code_column = "_Profil_WZ_Code"

    elif level == "WZ3":
        code_column = "_WZ3_Code"

    elif level == "WZ2":
        code_column = "_WZ2_Code"

    else:
        raise ValueError(
            "level muss FINAL, WZ3 oder WZ2 sein."
        )

    usable = (
        data[
            data[code_column].ne("")
        ]
        .copy()
    )

    rows = []

    for code, group in usable.groupby(
            code_column,
            sort=True,
    ):

        raw_mask = pd.Series(
            True,
            index=group.index,
        )

        suitable_mask = (
            group["_Filter_QX20_WAERME"]
        )

        raw = subset_metrics(
            group,
            raw_mask,
        )

        suitable = subset_metrics(
            group,
            suitable_mask,
        )

        qx_values = (
            group["_QX_Anteil_Waermemenge"]
            .dropna()
        )

        suitable_subset = (
            group.loc[
                suitable_mask
            ]
            .copy()
        )

        (
            largest_company,
            largest_company_share,
        ) = largest_company_metrics(
            suitable_subset
        )

        hard_total = int(
            group["_Zahlenpruefung_hoch"].sum()
        )

        hard_suitable = int(
            (
                    suitable_mask
                    & group["_Zahlenpruefung_hoch"]
            ).sum()
        )

        changing_suitable = int(
            (
                    suitable_mask
                    & group["_Eignung_kann_sich_aendern"]
            ).sum()
        )

        if level == "WZ2":
            short_name = wz2_description(group)

        else:
            short_name = mode_non_empty(
                group["_WZ3_Bezeichnung"]
            )

            if not short_name:
                fallback_code = (
                    derive_wz3(code)
                    if level == "FINAL"
                    else code
                )

                short_name = (
                    WZ3_LABEL_FALLBACKS.get(
                        fallback_code,
                        "",
                    )
                )

        row = {

            (
                "Profil_WZ_Code"
                if level == "FINAL"
                else f"{level}_Code"
            ):
                code,

            "Kurzname":
                short_name,

            # UNGEFILTERT
            "Standorte_gesamt":
                raw["Standorte"],

            "Unternehmen_gesamt":
                raw["Unternehmen"],

            # VORLÄUFIG GEEIGNET NACH WÄRMEMENGE
            "Standorte_QX_Waermemenge_max_20pct_vorlaeufig":
                suitable["Standorte"],

            "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig":
                suitable["Unternehmen"],

            "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig":
                safe_ratio(
                    suitable["Standorte"],
                    raw["Standorte"],
                ),

            # QX
            "Mittlerer_QX_Waermengenanteil":
                (
                    float(qx_values.mean())
                    if len(qx_values)
                    else np.nan
                ),

            "Median_QX_Waermengenanteil":
                (
                    float(qx_values.median())
                    if len(qx_values)
                    else np.nan
                ),

            # Zahlenqualität – nur Diagnose
            "Standorte_Zahlenpruefung_hoch_gesamt":
                hard_total,

            "Standorte_Zahlenpruefung_hoch_unter_Geeigneten":
                hard_suitable,

            "Anteil_geeignete_Standorte_mit_Zahlenpruefung_hoch":
                safe_ratio(
                    hard_suitable,
                    suitable["Standorte"],
                ),

            "Standorte_Eignung_kann_sich_aendern":
                changing_suitable,

            # Unternehmenskonzentration auf der für die spätere
            # Profilbildung relevanten, vorläufig geeigneten Basis.
            "Standorte_groesstes_Unternehmen_QX20":
                largest_company,

            "Anteil_groesstes_Unternehmen_QX20":
                largest_company_share,
        }

        if level == "FINAL":

            row["WZ3_Code"] = mode_non_empty(
                group["_WZ3_Code"]
            )

            row["WZ2_Code"] = mode_non_empty(
                group["_WZ2_Code"]
            )

        elif level == "WZ3":

            row["WZ2_Code"] = mode_non_empty(
                group["_WZ2_Code"]
            )

        elif level == "WZ2":

            wz3_codes = unique_non_empty(
                group["_WZ3_Code"]
            )

            wz3_labels = unique_non_empty(
                group["_WZ3_Bezeichnung"]
            )

            row[
                "Anzahl_enthaltener_WZ3_Gruppen"
            ] = len(wz3_codes)

            row[
                "Enthaltene_WZ3_Codes"
            ] = " | ".join(wz3_codes)

            row[
                "Enthaltene_WZ3_Bezeichnungen"
            ] = " | ".join(wz3_labels)

        rows.append(row)

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    common_metrics = [
        "Standorte_gesamt",
        "Unternehmen_gesamt",

        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
        "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig",
        "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig",

        "Mittlerer_QX_Waermengenanteil",
        "Median_QX_Waermengenanteil",

        "Standorte_Zahlenpruefung_hoch_gesamt",
        "Standorte_Zahlenpruefung_hoch_unter_Geeigneten",
        "Anteil_geeignete_Standorte_mit_Zahlenpruefung_hoch",
        "Standorte_Eignung_kann_sich_aendern",

        "Standorte_groesstes_Unternehmen_QX20",
        "Anteil_groesstes_Unternehmen_QX20",
    ]

    if level == "WZ3":

        preferred = [
            "WZ3_Code",
            "Kurzname",
            "WZ2_Code",
            *common_metrics,
        ]

        result = result.sort_values(
            [
                "WZ2_Code",
                "WZ3_Code",
            ],
            kind="stable",
        )

    elif level == "WZ2":

        preferred = [
            "WZ2_Code",
            "Kurzname",
            *common_metrics,
            "Anzahl_enthaltener_WZ3_Gruppen",
            "Enthaltene_WZ3_Codes",
            "Enthaltene_WZ3_Bezeichnungen",
        ]

        result = result.sort_values(
            "WZ2_Code",
            kind="stable",
        )

    else:

        preferred = [
            "Profil_WZ_Code",
            "Kurzname",
            "WZ3_Code",
            "WZ2_Code",
            *common_metrics,
        ]

        result = result.sort_values(
            [
                "WZ2_Code",
                "WZ3_Code",
                "Profil_WZ_Code",
            ],
            kind="stable",
        )

    return (
        result[preferred]
        .reset_index(drop=True)
    )


# ============================================================
# 9. ZUSAMMENLEGUNGSBLÄTTER
# ============================================================

def build_assignment_tables(
        final_summary,
        existing_assignments,
        existing_comments,
):
    """
    Blatt 1:
        Zusammenlegung_gt2
        -> mehr als 2 VORLÄUFIG geeignete Standorte nach
           Wärmemengen-QX-Filter.

    Blatt 2:
        Zusammenlegung_bis2
        -> 0, 1 oder 2 vorläufig geeignete Standorte.

    Aus beiden Blättern kann weiterhin eine Experimentgruppe
    vergeben werden.
    """

    result = final_summary.copy()

    result["Experiment_Gruppe"] = (
        result["Profil_WZ_Code"]
        .map(existing_assignments)
        .fillna("")
    )

    result["Kommentar"] = (
        result["Profil_WZ_Code"]
        .map(existing_comments)
        .fillna("")
    )

    count_column = (
        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig"
    )

    gt2 = (
        result[
            result[count_column]
            > 2
            ]
        .copy()
        .reset_index(drop=True)
    )

    bis2 = (
        result[
            result[count_column]
            <= 2
            ]
        .copy()
        .reset_index(drop=True)
    )

    return gt2, bis2


# ============================================================
# 10. VERSTECKTE STANDORTBASIS
# ============================================================

def build_helper_data(data):
    return pd.DataFrame(
        {
            "Standort_ID":
                data["_Standort_ID"],

            "Unternehmen_Key":
                data["_Unternehmen_Key"],

            "Profil_WZ_Code":
                data["_Profil_WZ_Code"],

            "WZ3_Code":
                data["_WZ3_Code"],

            "WZ2_Code":
                data["_WZ2_Code"],

            "QX_Waermengenanteil":
                data["_QX_Anteil_Waermemenge"],

            "Geeignet_QX_Waermemenge_max_20pct_vorlaeufig":
                data["_Filter_QX20_WAERME"]
                .astype(int),

            "Zahlenpruefung_hoch":
                data["_Zahlenpruefung_hoch"]
                .astype(int),

            "Zahlenpruefung_mittel":
                data["_Zahlenpruefung_mittel"]
                .astype(int),

            "Eignung_kann_sich_aendern":
                data["_Eignung_kann_sich_aendern"]
                .astype(int),

            "Experiment_Gruppe":
                "",
        }
    )


# ============================================================
# 11. ERSTE EXCELDATEI SCHREIBEN
# ============================================================

def write_initial_workbook(
        wz3_summary,
        wz2_summary,
        assignment_gt2,
        assignment_bis2,
        helper_data,
):
    """
    Sichtbare Blätter:
        WZ3_Gruppen
        WZ2_Gruppen
        Zusammenlegung_gt2
        Zusammenlegung_bis2
        Gruppen_Ergebnis

    Versteckte Blätter:
        _Datenbasis
        _Gruppen_Roh
        _Listen
    """

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with pd.ExcelWriter(
            OUTPUT_FILE,
            engine="openpyxl",
    ) as writer:

        wz3_summary.to_excel(
            writer,
            sheet_name="WZ3_Gruppen",
            index=False,
            startrow=3,
        )

        wz2_summary.to_excel(
            writer,
            sheet_name="WZ2_Gruppen",
            index=False,
            startrow=3,
        )

        assignment_gt2.to_excel(
            writer,
            sheet_name="Zusammenlegung_gt2",
            index=False,
            startrow=3,
        )

        assignment_bis2.to_excel(
            writer,
            sheet_name="Zusammenlegung_bis2",
            index=False,
            startrow=3,
        )

        pd.DataFrame().to_excel(
            writer,
            sheet_name="Gruppen_Ergebnis",
            index=False,
        )

        helper_data.to_excel(
            writer,
            sheet_name="_Datenbasis",
            index=False,
        )

        pd.DataFrame(
            {
                "Experiment_Gruppe": [
                    format_experiment_group_id(index)
                    for index
                    in range(
                        1,
                        MAX_EXPERIMENT_GROUPS + 1,
                        )
                ]
            }
        ).to_excel(
            writer,
            sheet_name="_Listen",
            index=False,
        )

        pd.DataFrame().to_excel(
            writer,
            sheet_name="_Gruppen_Roh",
            index=False,
        )


# ============================================================
# 12. FORMATIERUNGSFARBEN
# ============================================================

def section_fill(section):
    colors = {
        "ID": "D9E2F3",
        "RAW": "DDEBF7",
        "QX20": "E2F0D9",
        "QUALITY": "FCE4D6",
        "MANUAL": "FFF2CC",
    }

    return PatternFill(
        fill_type="solid",
        fgColor=colors[section],
    )


def get_site_count_fill(value):
    """
    Farbskala wie zuletzt vereinbart:

        <=2       rot
        3-5       orange
        6-8       dunkles Gelb
        9-10      helles Gelb
        11-17     helles Grün
        18-25     Grün
        >25       dunkles Grün
    """

    try:
        number = float(value)

    except (TypeError, ValueError):
        return None

    if number <= 2:
        color = "F4CCCC"

    elif number <= 5:
        color = "F6B26B"

    elif number <= 8:
        color = "F1C232"

    elif number <= 10:
        color = "FFE599"

    elif number <= 17:
        color = "D9EAD3"

    elif number <= 25:
        color = "93C47D"

    else:
        color = "6AA84F"

    return PatternFill(
        fill_type="solid",
        start_color=color,
        end_color=color,
    )


def add_dynamic_site_count_formatting(
        worksheet,
        cell_range,
):
    rules = [
        (
            "lessThanOrEqual",
            ["2"],
            "F4CCCC",
        ),
        (
            "between",
            ["3", "5"],
            "F6B26B",
        ),
        (
            "between",
            ["6", "8"],
            "F1C232",
        ),
        (
            "between",
            ["9", "10"],
            "FFE599",
        ),
        (
            "between",
            ["11", "17"],
            "D9EAD3",
        ),
        (
            "between",
            ["18", "25"],
            "93C47D",
        ),
        (
            "greaterThan",
            ["25"],
            "6AA84F",
        ),
    ]

    for operator, formula, color in rules:

        worksheet.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator=operator,
                formula=formula,
                fill=PatternFill(
                    fill_type="solid",
                    start_color=color,
                    end_color=color,
                ),
                stopIfTrue=True,
            ),
        )


# ============================================================
# 13. EXCEL-HILFSFUNKTIONEN
# ============================================================

def header_map(
        worksheet,
        header_row,
):
    return {
        clean_string(cell.value):
            cell.column
        for cell
        in worksheet[header_row]
        if clean_string(cell.value)
    }


def add_explanation_row(
        worksheet,
        header_row,
        explanation_row,
):
    for cell in worksheet[header_row]:

        header = clean_string(
            cell.value
        )

        explanation = (
            COLUMN_EXPLANATIONS.get(
                header,
                "",
            )
        )

        worksheet.cell(
            row=explanation_row,
            column=cell.column,
            value=explanation,
        )

        if explanation:
            cell.comment = Comment(
                explanation,
                "OpenAI",
            )

    worksheet.row_dimensions[
        explanation_row
    ].height = 58


def apply_number_formats(
        worksheet,
        header_row,
        first_data_row,
):
    mapping = header_map(
        worksheet,
        header_row,
    )

    for header, column in mapping.items():

        if (
                "Anteil"
                in header
        ):

            for row in range(
                    first_data_row,
                    worksheet.max_row + 1,
            ):

                worksheet.cell(
                    row=row,
                    column=column,
                ).number_format = "0.0%"


def apply_static_site_count_colors(
        worksheet,
        header_row,
        first_data_row,
):
    """
    Farbcodiert vor allem die absoluten Standortzahlen.
    """

    mapping = header_map(
        worksheet,
        header_row,
    )

    for header in [
        "Standorte_gesamt",
        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
    ]:

        if header not in mapping:
            continue

        column = mapping[header]

        for row in range(
                first_data_row,
                worksheet.max_row + 1,
        ):

            cell = worksheet.cell(
                row=row,
                column=column,
            )

            fill = get_site_count_fill(
                cell.value
            )

            if fill is not None:
                cell.fill = fill

            cell.font = Font(
                bold=True,
                color="000000",
            )

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )


def apply_quality_warning_colors(
        worksheet,
        header_row,
        first_data_row,
):
    """
    Qualitätsfelder werden nicht als Filter interpretiert.
    Sie sollen nur optisch auf noch offene Zahlenprüfung hinweisen.
    """

    mapping = header_map(
        worksheet,
        header_row,
    )

    warning_headers = [
        "Standorte_Zahlenpruefung_hoch_gesamt",
        "Standorte_Zahlenpruefung_hoch_unter_Geeigneten",
        "Standorte_Eignung_kann_sich_aendern",
    ]

    warning_fill = PatternFill(
        fill_type="solid",
        fgColor="FCE4D6",
    )

    for header in warning_headers:

        if header not in mapping:
            continue

        column = mapping[header]

        for row in range(
                first_data_row,
                worksheet.max_row + 1,
        ):

            cell = worksheet.cell(
                row=row,
                column=column,
            )

            try:
                value = float(cell.value)

            except (TypeError, ValueError):
                value = 0

            if value > 0:
                cell.fill = warning_fill


def apply_wz2_separation(
        worksheet,
        header_row,
        first_data_row,
):
    mapping = header_map(
        worksheet,
        header_row,
    )

    if "WZ2_Code" not in mapping:
        return

    wz2_column = mapping[
        "WZ2_Code"
    ]

    medium = Side(
        style="medium",
        color="4F81BD",
    )

    fill_a = PatternFill(
        "solid",
        fgColor="F7F9FC",
    )

    fill_b = PatternFill(
        "solid",
        fgColor="EAF1F8",
    )

    previous = None
    block_index = -1

    for row in range(
            first_data_row,
            worksheet.max_row + 1,
    ):

        current = clean_string(
            worksheet.cell(
                row=row,
                column=wz2_column,
            ).value
        )

        if current != previous:

            block_index += 1

            for column in range(
                    1,
                    worksheet.max_column + 1,
            ):

                cell = worksheet.cell(
                    row=row,
                    column=column,
                )

                border = cell.border

                cell.border = Border(
                    left=border.left,
                    right=border.right,
                    top=medium,
                    bottom=border.bottom,
                )

        block_fill = (
            fill_a
            if block_index % 2 == 0
            else fill_b
        )

        for column in range(
                1,
                min(
                    3,
                    worksheet.max_column,
                ) + 1,
        ):

            worksheet.cell(
                row=row,
                column=column,
            ).fill = block_fill

        previous = current


# ============================================================
# 14. REFERENZBLÄTTER FORMATIEREN
# ============================================================

def configure_reference_sheet(
        worksheet,
        title,
        subtitle,
        is_wz3=False,
):
    """
    pandas schrieb:
        Zeile 4 = Header
        Zeile 5+ = Daten

    Wir fügen Zeile 5 als Erklärung ein.
    """

    worksheet.insert_rows(
        5,
        amount=1,
    )

    section_row = 3
    header_row = 4
    explanation_row = 5
    first_data_row = 6

    worksheet["A1"] = title
    worksheet["A2"] = subtitle

    worksheet["A1"].font = Font(
        bold=True,
        size=15,
    )

    worksheet["A2"].font = Font(
        italic=True,
        color="666666",
    )

    worksheet["A2"].alignment = Alignment(
        wrap_text=True,
    )

    worksheet.freeze_panes = (
        f"A{first_data_row}"
    )

    add_explanation_row(
        worksheet,
        header_row,
        explanation_row,
    )

    mapping = header_map(
        worksheet,
        header_row,
    )

    raw_headers = {
        "Standorte_gesamt",
        "Unternehmen_gesamt",
    }

    qx20_headers = {
        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
        "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig",
        "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
    }

    quality_headers = {
        "Mittlerer_QX_Waermengenanteil",
        "Median_QX_Waermengenanteil",
        "Standorte_Zahlenpruefung_hoch_gesamt",
        "Standorte_Zahlenpruefung_hoch_unter_Geeigneten",
        "Anteil_geeignete_Standorte_mit_Zahlenpruefung_hoch",
        "Standorte_Eignung_kann_sich_aendern",
        "Standorte_groesstes_Unternehmen_QX20",
        "Anteil_groesstes_Unternehmen_QX20",
        "Anzahl_enthaltener_WZ3_Gruppen",
        "Enthaltene_WZ3_Codes",
        "Enthaltene_WZ3_Bezeichnungen",
    }

    id_headers = {
        "WZ3_Code",
        "WZ2_Code",
        "Kurzname",
    }

    for header, column in mapping.items():

        header_cell = worksheet.cell(
            row=header_row,
            column=column,
        )

        explanation_cell = worksheet.cell(
            row=explanation_row,
            column=column,
        )

        if header in raw_headers:
            fill = section_fill("RAW")

        elif header in qx20_headers:
            fill = section_fill("QX20")

        elif header in id_headers:
            fill = section_fill("ID")

        else:
            fill = section_fill("QUALITY")

        header_cell.fill = fill
        explanation_cell.fill = fill

        header_cell.font = Font(
            bold=True,
        )

        header_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        explanation_cell.font = Font(
            italic=True,
            color="666666",
            size=9,
        )

        explanation_cell.alignment = Alignment(
            vertical="top",
            wrap_text=True,
        )

    # Abschnittsüberschriften
    blocks = []

    for section, title, headers in [
        (
                "ID",
                "Identifikation",
                id_headers,
        ),
        (
                "RAW",
                "UNGEFILTERTE STANDORTBASIS",
                raw_headers,
        ),
        (
                "QX20",
                "VORLÄUFIG GEEIGNET: QX ≤ 20 % DER JAHRESWÄRMEMENGE",
                qx20_headers,
        ),
        (
                "QUALITY",
                "QUALITÄT / NOCH OFFENE ZAHLENPRÜFUNG",
                quality_headers,
        ),
    ]:

        indices = [
            mapping[header]
            for header
            in headers
            if header in mapping
        ]

        if indices:

            blocks.append(
                (
                    section,
                    title,
                    min(indices),
                    max(indices),
                )
            )

    for section, title, start, end in blocks:

        if start != end:
            worksheet.merge_cells(
                start_row=section_row,
                start_column=start,
                end_row=section_row,
                end_column=end,
            )

        cell = worksheet.cell(
            row=section_row,
            column=start,
            value=title,
        )

        cell.fill = section_fill(
            section
        )

        cell.font = Font(
            bold=True,
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        for column in range(
                start,
                end + 1,
        ):
            worksheet.cell(
                row=section_row,
                column=column,
            ).fill = section_fill(
                section
            )

    for row in worksheet.iter_rows(
            min_row=first_data_row,
            max_row=worksheet.max_row,
    ):

        for cell in row:

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    apply_static_site_count_colors(
        worksheet,
        header_row,
        first_data_row,
    )

    apply_quality_warning_colors(
        worksheet,
        header_row,
        first_data_row,
    )

    apply_number_formats(
        worksheet,
        header_row,
        first_data_row,
    )

    if is_wz3:
        apply_wz2_separation(
            worksheet,
            header_row,
            first_data_row,
        )

    for header, column in mapping.items():

        width = 18

        if header in {
            "Kurzname",
            "Enthaltene_WZ3_Bezeichnungen",
        }:
            width = 38

        elif header in {
            "Enthaltene_WZ3_Codes",
        }:
            width = 28

        elif header in {
            "WZ3_Code",
            "WZ2_Code",
        }:
            width = 14

        elif header in quality_headers:
            width = 22

        worksheet.column_dimensions[
            get_column_letter(column)
        ].width = width


# ============================================================
# 15. ZUSAMMENLEGUNGSBLÄTTER FORMATIEREN
# ============================================================

def configure_assignment_sheet(
        worksheet,
        title,
        subtitle,
        row_count,
):
    """
    Beide Blätter sind vollständig editierbar:
      - Experiment_Gruppe
      - Kommentar
    """

    worksheet.insert_rows(
        5,
        amount=1,
    )

    section_row = 3
    header_row = 4
    explanation_row = 5
    first_data_row = 6

    last_data_row = (
            first_data_row
            + row_count
            - 1
    )

    worksheet["A1"] = title
    worksheet["A2"] = subtitle

    worksheet["A1"].font = Font(
        bold=True,
        size=15,
    )

    worksheet["A2"].alignment = Alignment(
        wrap_text=True,
    )

    worksheet.freeze_panes = (
        f"A{first_data_row}"
    )

    add_explanation_row(
        worksheet,
        header_row,
        explanation_row,
    )

    mapping = header_map(
        worksheet,
        header_row,
    )

    raw_headers = {
        "Standorte_gesamt",
        "Unternehmen_gesamt",
    }

    qx20_headers = {
        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
        "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig",
        "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
    }

    manual_headers = {
        "Experiment_Gruppe",
        "Kommentar",
    }

    id_headers = {
        "Profil_WZ_Code",
        "Kurzname",
        "WZ3_Code",
        "WZ2_Code",
    }

    quality_headers = (
            set(mapping.keys())
            - raw_headers
            - qx20_headers
            - manual_headers
            - id_headers
    )

    for header, column in mapping.items():

        if header in raw_headers:
            fill = section_fill("RAW")

        elif header in qx20_headers:
            fill = section_fill("QX20")

        elif header in manual_headers:
            fill = section_fill("MANUAL")

        elif header in id_headers:
            fill = section_fill("ID")

        else:
            fill = section_fill("QUALITY")

        header_cell = worksheet.cell(
            row=header_row,
            column=column,
        )

        explanation_cell = worksheet.cell(
            row=explanation_row,
            column=column,
        )

        header_cell.fill = fill
        explanation_cell.fill = fill

        header_cell.font = Font(
            bold=True,
        )

        header_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        explanation_cell.font = Font(
            italic=True,
            color="666666",
            size=9,
        )

        explanation_cell.alignment = Alignment(
            vertical="top",
            wrap_text=True,
        )

    section_specs = [
        (
            "ID",
            "Identifikation",
            id_headers,
        ),
        (
            "RAW",
            "UNGEFILTERTE STANDORTBASIS",
            raw_headers,
        ),
        (
            "QX20",
            "VORLÄUFIG GEEIGNET: QX ≤ 20 % DER JAHRESWÄRMEMENGE",
            qx20_headers,
        ),
        (
            "QUALITY",
            "QUALITÄT / ZAHLENPRÜFUNG",
            quality_headers,
        ),
        (
            "MANUAL",
            "MANUELLE EXPERIMENT-ZUORDNUNG",
            manual_headers,
        ),
    ]

    for section, label, headers in section_specs:

        indices = [
            mapping[header]
            for header
            in headers
            if header in mapping
        ]

        if not indices:
            continue

        start = min(indices)
        end = max(indices)

        if start != end:
            worksheet.merge_cells(
                start_row=section_row,
                start_column=start,
                end_row=section_row,
                end_column=end,
            )

        cell = worksheet.cell(
            row=section_row,
            column=start,
            value=label,
        )

        cell.fill = section_fill(
            section
        )

        cell.font = Font(
            bold=True,
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        for column in range(
                start,
                end + 1,
        ):
            worksheet.cell(
                row=section_row,
                column=column,
            ).fill = section_fill(
                section
            )

    # Dropdown für G01, G02, ...
    group_column = mapping[
        "Experiment_Gruppe"
    ]

    group_letter = get_column_letter(
        group_column
    )

    validation = DataValidation(
        type="list",
        formula1=(
            "'_Listen'!"
            f"$A$2:"
            f"$A${MAX_EXPERIMENT_GROUPS + 1}"
        ),
        allow_blank=True,
    )

    worksheet.add_data_validation(
        validation
    )

    if row_count > 0:

        validation.add(
            f"{group_letter}{first_data_row}:"
            f"{group_letter}{last_data_row}"
        )

    # Manuelle Spalten gelb.
    for header in manual_headers:

        if header not in mapping:
            continue

        column = mapping[header]

        for row in range(
                first_data_row,
                max(
                    first_data_row,
                    last_data_row,
                ) + 1,
        ):

            worksheet.cell(
                row=row,
                column=column,
            ).fill = section_fill(
                "MANUAL"
            )

    apply_static_site_count_colors(
        worksheet,
        header_row,
        first_data_row,
    )

    apply_quality_warning_colors(
        worksheet,
        header_row,
        first_data_row,
    )

    apply_number_formats(
        worksheet,
        header_row,
        first_data_row,
    )

    for row in worksheet.iter_rows(
            min_row=first_data_row,
            max_row=worksheet.max_row,
    ):

        for cell in row:
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    for header, column in mapping.items():

        width = 18

        if header in {
            "Kurzname",
            "Kommentar",
        }:
            width = 38

        elif header in {
            "Profil_WZ_Code",
            "WZ3_Code",
            "WZ2_Code",
            "Experiment_Gruppe",
        }:
            width = 16

        elif header in quality_headers:
            width = 22

        worksheet.column_dimensions[
            get_column_letter(column)
        ].width = width

    return {
        "header_row":
            header_row,

        "first_data_row":
            first_data_row,

        "last_data_row":
            last_data_row,

        "mapping":
            mapping,
    }


# ============================================================
# 16. FORMEL FÜR EXPERIMENTGRUPPE AUS BEIDEN EINGABEBLÄTTERN
# ============================================================

def assignment_lookup_formula(
        code_cell,
        gt2_layout,
        bis2_layout,
):
    """
    Klassisches INDEX/MATCH statt XLOOKUP.
    """

    parts = []

    for sheet_name, layout in [
        (
                "Zusammenlegung_gt2",
                gt2_layout,
        ),
        (
                "Zusammenlegung_bis2",
                bis2_layout,
        ),
    ]:

        first_row = layout[
            "first_data_row"
        ]

        last_row = layout[
            "last_data_row"
        ]

        if last_row < first_row:
            continue

        mapping = layout[
            "mapping"
        ]

        code_letter = get_column_letter(
            mapping[
                "Profil_WZ_Code"
            ]
        )

        group_letter = get_column_letter(
            mapping[
                "Experiment_Gruppe"
            ]
        )

        parts.append(
            (
                f"INDEX("
                f"'{sheet_name}'!"
                f"${group_letter}${first_row}:"
                f"${group_letter}${last_row},"
                f"MATCH("
                f"{code_cell},"
                f"'{sheet_name}'!"
                f"${code_letter}${first_row}:"
                f"${code_letter}${last_row},"
                f"0"
                f")"
                f")"
            )
        )

    if not parts:
        return '=""'

    formula = parts[-1]

    for part in reversed(
            parts[:-1]
    ):
        formula = (
            f"IFERROR("
            f"{part},"
            f"{formula}"
            f")"
        )

    return (
        f"=IFERROR("
        f"{formula},"
        f'""'
        f")"
    )


# ============================================================
# 17. VERSTECKTE DATENBASIS MIT ZUORDNUNGEN
# ============================================================

def configure_hidden_data(
        workbook,
        helper_data,
        gt2_layout,
        bis2_layout,
):
    data_sheet = workbook[
        "_Datenbasis"
    ]

    data_map = {
        clean_string(cell.value):
            cell.column
        for cell
        in data_sheet[1]
        if clean_string(cell.value)
    }

    profile_code_column = data_map[
        "Profil_WZ_Code"
    ]

    group_column = data_map[
        "Experiment_Gruppe"
    ]

    profile_code_letter = get_column_letter(
        profile_code_column
    )

    group_letter = get_column_letter(
        group_column
    )

    first_row = 2

    last_row = (
            first_row
            + len(helper_data)
            - 1
    )

    for row in range(
            first_row,
            last_row + 1,
    ):

        data_sheet[
            f"{group_letter}{row}"
        ] = assignment_lookup_formula(
            f"{profile_code_letter}{row}",
            gt2_layout,
            bis2_layout,
        )

    return {
        "data_first_row":
            first_row,

        "data_last_row":
            last_row,

        "data_map":
            data_map,
    }


# ============================================================
# 18. HILFSRANGES DER BEIDEN ZUSAMMENLEGUNGSBLÄTTER
# ============================================================

def assignment_ranges(
        gt2_layout,
        bis2_layout,
):
    """
    Liefert pro Eingabeblatt die relevanten Bereiche für:
      - Experiment_Gruppe
      - WZ3_Code

    Diese Ranges werden auch für die robuste WZ3-Liste im
    Ergebnisblatt verwendet.
    """

    result = []

    for sheet_name, layout in [
        (
                "Zusammenlegung_gt2",
                gt2_layout,
        ),
        (
                "Zusammenlegung_bis2",
                bis2_layout,
        ),
    ]:

        first_row = layout[
            "first_data_row"
        ]

        last_row = layout[
            "last_data_row"
        ]

        if last_row < first_row:
            continue

        mapping = layout[
            "mapping"
        ]

        group_letter = get_column_letter(
            mapping[
                "Experiment_Gruppe"
            ]
        )

        wz3_letter = get_column_letter(
            mapping[
                "WZ3_Code"
            ]
        )

        result.append(
            {
                "sheet_name":
                    sheet_name,

                "first_row":
                    first_row,

                "last_row":
                    last_row,

                "group_range":
                    (
                        f"'{sheet_name}'!"
                        f"${group_letter}${first_row}:"
                        f"${group_letter}${last_row}"
                    ),

                "wz3_range":
                    (
                        f"'{sheet_name}'!"
                        f"${wz3_letter}${first_row}:"
                        f"${wz3_letter}${last_row}"
                    ),
            }
        )

    return result


# ============================================================
# 19. ROHDATEN PRO EXPERIMENTGRUPPE
# ============================================================

def configure_group_raw_sheet(
        workbook,
        helper_layout,
        gt2_layout,
        bis2_layout,
        all_wz3_codes,
):
    """
    Versteckte Ergebnistabelle.

    WICHTIGE ÄNDERUNG:
    Die Liste der enthaltenen WZ3-Codes wird jetzt NICHT mehr über
    die frühere AGGREGATE-Hilfskonstruktion erzeugt.

    Stattdessen bekommt jeder mögliche WZ3-Code eine versteckte
    Hilfsspalte. COUNTIFS prüft robust, ob dieser Code in G01/G02/...
    vorkommt. TEXTJOIN fügt nur die vorhandenen Codes zusammen.

    Dadurch wird der frühere #WERT!-Fehler vermieden.
    """

    sheet = workbook[
        "_Gruppen_Roh"
    ]

    headers = [
        "Experiment_Gruppe",                              # A
        "Anzahl_Profil_WZ_Gruppen",                      # B
        "Enthaltene_WZ3_Codes",                          # C
        "Anzahl_WZ3_Gruppen",                            # D

        "Standorte_gesamt",                               # E
        "Unternehmen_gesamt",                             # F

        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig",# G
        "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig",# H
        "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig",# I

        "Standorte_Zahlenpruefung_hoch_unter_Geeigneten",# J
        "Anteil_geeignete_Standorte_mit_Zahlenpruefung_hoch",# K
        "Standorte_Eignung_kann_sich_aendern",           # L

        "Mittlerer_QX_Waermengenanteil_geeignete_Standorte",# M

        "Sort_Key",                                       # N
    ]

    helper_start_column = len(headers) + 1

    for wz3_code in all_wz3_codes:
        headers.append(
            f"WZ3_HELPER_{wz3_code}"
        )

    for column, header in enumerate(
            headers,
            start=1,
    ):
        sheet.cell(
            row=1,
            column=column,
            value=header,
        )

    # --------------------------------------------------------
    # Datenbasis
    # --------------------------------------------------------

    data_map = helper_layout[
        "data_map"
    ]

    data_first = helper_layout[
        "data_first_row"
    ]

    data_last = helper_layout[
        "data_last_row"
    ]

    def data_range(header):
        letter = get_column_letter(
            data_map[header]
        )

        return (
            f"_Datenbasis!"
            f"${letter}${data_first}:"
            f"${letter}${data_last}"
        )

    group_range = data_range(
        "Experiment_Gruppe"
    )

    company_range = data_range(
        "Unternehmen_Key"
    )

    qx_range = data_range(
        "QX_Waermengenanteil"
    )

    suitable_range = data_range(
        "Geeignet_QX_Waermemenge_max_20pct_vorlaeufig"
    )

    hard_range = data_range(
        "Zahlenpruefung_hoch"
    )

    change_range = data_range(
        "Eignung_kann_sich_aendern"
    )

    # --------------------------------------------------------
    # Assignment-Ranges
    # --------------------------------------------------------

    ranges = assignment_ranges(
        gt2_layout,
        bis2_layout,
    )

    # --------------------------------------------------------
    # Formeln je Experimentgruppe
    # --------------------------------------------------------

    raw_first_row = 2

    raw_last_row = (
            raw_first_row
            + MAX_EXPERIMENT_GROUPS
            - 1
    )

    for index in range(
            MAX_EXPERIMENT_GROUPS
    ):

        row = (
                raw_first_row
                + index
        )

        group_id = format_experiment_group_id(
            index + 1
        )

        sheet[
            f"A{row}"
        ] = group_id

        # B: Anzahl zugeordneter Profil-WZ-Codes
        count_parts = []

        for item in ranges:
            count_parts.append(
                (
                    f"COUNTIF("
                    f"{item['group_range']},"
                    f"$A{row}"
                    f")"
                )
            )

        sheet[
            f"B{row}"
        ] = (
                "="
                + (
                    "+".join(count_parts)
                    if count_parts
                    else "0"
                )
        )

        # E: alle zugeordneten Standorte
        sheet[
            f"E{row}"
        ] = (
            f'=COUNTIF('
            f'{group_range},'
            f'$A{row}'
            f')'
        )

        # F: unterschiedliche Unternehmen, ungefiltert
        sheet[
            f"F{row}"
        ] = (
            f'=IFERROR('
            f'SUMPRODUCT('
            f'({group_range}=$A{row})*'
            f'({company_range}<>"")/'
            f'COUNTIFS('
            f'{group_range},{group_range},'
            f'{company_range},{company_range}'
            f')'
            f'),'
            f'0'
            f')'
        )

        # G: vorläufig geeignete Standorte nach Wärmemengen-QX
        sheet[
            f"G{row}"
        ] = (
            f'=COUNTIFS('
            f'{group_range},$A{row},'
            f'{suitable_range},1'
            f')'
        )

        # H: unterschiedliche Unternehmen unter geeigneten Standorten
        sheet[
            f"H{row}"
        ] = (
            f'=IFERROR('
            f'SUMPRODUCT('
            f'({group_range}=$A{row})*'
            f'({suitable_range}=1)*'
            f'({company_range}<>"")/'
            f'COUNTIFS('
            f'{group_range},{group_range},'
            f'{suitable_range},{suitable_range},'
            f'{company_range},{company_range}'
            f')'
            f'),'
            f'0'
            f')'
        )

        # I: Retention
        sheet[
            f"I{row}"
        ] = (
            f'=IF('
            f'E{row}=0,'
            f'"",'
            f'G{row}/E{row}'
            f')'
        )

        # J: geeignete Standorte mit hoher Zahlen-Prüfpriorität
        sheet[
            f"J{row}"
        ] = (
            f'=COUNTIFS('
            f'{group_range},$A{row},'
            f'{suitable_range},1,'
            f'{hard_range},1'
            f')'
        )

        # K: Anteil davon
        sheet[
            f"K{row}"
        ] = (
            f'=IF('
            f'G{row}=0,'
            f'"",'
            f'J{row}/G{row}'
            f')'
        )

        # L: Eignung kann sich nach Zahlenprüfung noch ändern
        sheet[
            f"L{row}"
        ] = (
            f'=COUNTIFS('
            f'{group_range},$A{row},'
            f'{suitable_range},1,'
            f'{change_range},1'
            f')'
        )

        # M: mittlerer QX-Wärmemengenanteil unter den geeigneten
        sheet[
            f"M{row}"
        ] = (
            f'=IF('
            f'G{row}=0,'
            f'"",'
            f'SUMIFS('
            f'{qx_range},'
            f'{group_range},$A{row},'
            f'{suitable_range},1'
            f')/G{row}'
            f')'
        )

        # N: eindeutiger Sortierschlüssel
        sheet[
            f"N{row}"
        ] = (
            f'=IF('
            f'B{row}=0,'
            f'0,'
            f'(G{row}+1)*100000'
            f'+'
            f'{MAX_EXPERIMENT_GROUPS - index}'
            f')'
        )

        # ----------------------------------------------------
        # O...: je WZ3-Code eine robuste Hilfsformel
        # ----------------------------------------------------

        for wz_index, wz3_code in enumerate(
                all_wz3_codes
        ):

            column = (
                    helper_start_column
                    + wz_index
            )

            letter = get_column_letter(
                column
            )

            presence_parts = []

            for item in ranges:

                presence_parts.append(
                    (
                        f"COUNTIFS("
                        f"{item['group_range']},"
                        f"$A{row},"
                        f"{item['wz3_range']},"
                        f'"{wz3_code}"'
                        f")"
                    )
                )

            presence_formula = (
                "+".join(presence_parts)
                if presence_parts
                else "0"
            )

            sheet[
                f"{letter}{row}"
            ] = (
                f'=IF('
                f'({presence_formula})>0,'
                f'"{wz3_code}",'
                f'""'
                f')'
            )

        if all_wz3_codes:

            first_helper_letter = get_column_letter(
                helper_start_column
            )

            last_helper_letter = get_column_letter(
                helper_start_column
                + len(all_wz3_codes)
                - 1
            )

            # C: WZ3-Liste
            sheet[
                f"C{row}"
            ] = (
                f'=TEXTJOIN('
                f'", ",'
                f'TRUE,'
                f'{first_helper_letter}{row}:'
                f'{last_helper_letter}{row}'
                f')'
            )

            # D: Anzahl WZ3
            sheet[
                f"D{row}"
            ] = (
                f'=COUNTIF('
                f'{first_helper_letter}{row}:'
                f'{last_helper_letter}{row},'
                f'"<>"'
                f')'
            )

        else:

            sheet[
                f"C{row}"
            ] = '=""'

            sheet[
                f"D{row}"
            ] = "=0"

    return {
        "raw_first_row":
            raw_first_row,

        "raw_last_row":
            raw_last_row,
    }


# ============================================================
# 20. SICHTBARE, SORTIERTE ERGEBNISSEITE
# ============================================================

def configure_result_sheet(
        workbook,
        raw_layout,
):
    """
    Sortiert automatisch absteigend nach der Zahl der VORLÄUFIG
    geeigneten Standorte nach Wärmemengen-QX-Filter.
    """

    sheet = workbook[
        "Gruppen_Ergebnis"
    ]

    sheet["A1"] = (
        "Fertige experimentelle Gruppen – "
        "vorläufiger Wärmemengenstandard"
    )

    sheet["A2"] = (
        "Sortierung: Standorte_QX_Waermemenge_max_20pct_vorlaeufig "
        "absteigend. Nach Änderungen in den Zusammenlegungsblättern "
        "F9 drücken. Plausibilitätsauffällige positive Wärmemengen "
        "sind bewusst noch enthalten."
    )

    sheet["A3"] = (
        "Die Qualitätsfelder zeigen, bei wie vielen vorläufig "
        "geeigneten Standorten die Zahlenprüfung noch Einfluss auf "
        "die spätere endgültige Eignung haben kann."
    )

    sheet["A1"].font = Font(
        bold=True,
        size=15,
    )

    for row in [
        2,
        3,
    ]:
        sheet.cell(
            row=row,
            column=1,
        ).alignment = Alignment(
            wrap_text=True,
        )

    section_row = 4
    header_row = 5
    explanation_row = 6
    first_data_row = 7

    headers = [
        "Experiment_Gruppe",
        "Enthaltene_WZ3_Codes",
        "Anzahl_WZ3_Gruppen",
        "Anzahl_Profil_WZ_Gruppen",

        "Standorte_gesamt",
        "Unternehmen_gesamt",

        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
        "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig",
        "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig",

        "Standorte_Zahlenpruefung_hoch_unter_Geeigneten",
        "Anteil_geeignete_Standorte_mit_Zahlenpruefung_hoch",
        "Standorte_Eignung_kann_sich_aendern",

        "Mittlerer_QX_Waermengenanteil",
    ]

    for column, header in enumerate(
            headers,
            start=1,
    ):
        sheet.cell(
            row=header_row,
            column=column,
            value=header,
        )

    add_explanation_row(
        sheet,
        header_row,
        explanation_row,
    )

    mapping = header_map(
        sheet,
        header_row,
    )

    # Abschnittsfarben
    blocks = [
        (
            "ID",
            "Zusammensetzung der Experimentgruppe",
            1,
            4,
        ),
        (
            "RAW",
            "UNGEFILTERTE STANDORTBASIS",
            5,
            6,
        ),
        (
            "QX20",
            "VORLÄUFIG GEEIGNET: QX ≤ 20 % JAHRESWÄRMEMENGE",
            7,
            9,
        ),
        (
            "QUALITY",
            "ZAHLENQUALITÄT / VORLÄUFIGKEIT",
            10,
            13,
        ),
    ]

    for section, title, start, end in blocks:

        if start != end:
            sheet.merge_cells(
                start_row=section_row,
                start_column=start,
                end_row=section_row,
                end_column=end,
            )

        cell = sheet.cell(
            row=section_row,
            column=start,
            value=title,
        )

        cell.fill = section_fill(
            section
        )

        cell.font = Font(
            bold=True,
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        for column in range(
                start,
                end + 1,
        ):
            sheet.cell(
                row=section_row,
                column=column,
            ).fill = section_fill(
                section
            )

    for header, column in mapping.items():

        if column <= 4:
            fill = section_fill("ID")

        elif column <= 6:
            fill = section_fill("RAW")

        elif column <= 9:
            fill = section_fill("QX20")

        else:
            fill = section_fill("QUALITY")

        sheet.cell(
            row=header_row,
            column=column,
        ).fill = fill

        sheet.cell(
            row=explanation_row,
            column=column,
        ).fill = fill

        sheet.cell(
            row=header_row,
            column=column,
        ).font = Font(
            bold=True,
        )

        sheet.cell(
            row=header_row,
            column=column,
        ).alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        sheet.cell(
            row=explanation_row,
            column=column,
        ).font = Font(
            italic=True,
            color="666666",
            size=9,
        )

        sheet.cell(
            row=explanation_row,
            column=column,
        ).alignment = Alignment(
            vertical="top",
            wrap_text=True,
        )

    sheet.freeze_panes = (
        f"A{first_data_row}"
    )

    raw_first = raw_layout[
        "raw_first_row"
    ]

    raw_last = raw_layout[
        "raw_last_row"
    ]

    sort_range = (
        f"_Gruppen_Roh!"
        f"$N${raw_first}:"
        f"$N${raw_last}"
    )

    raw_group_range = (
        f"_Gruppen_Roh!"
        f"$A${raw_first}:"
        f"$A${raw_last}"
    )

    raw_columns = {
        "Enthaltene_WZ3_Codes":
            "C",

        "Anzahl_WZ3_Gruppen":
            "D",

        "Anzahl_Profil_WZ_Gruppen":
            "B",

        "Standorte_gesamt":
            "E",

        "Unternehmen_gesamt":
            "F",

        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig":
            "G",

        "Unternehmen_QX_Waermemenge_max_20pct_vorlaeufig":
            "H",

        "Anteil_Standorte_QX_Waermemenge_max_20pct_vorlaeufig":
            "I",

        "Standorte_Zahlenpruefung_hoch_unter_Geeigneten":
            "J",

        "Anteil_geeignete_Standorte_mit_Zahlenpruefung_hoch":
            "K",

        "Standorte_Eignung_kann_sich_aendern":
            "L",

        "Mittlerer_QX_Waermengenanteil":
            "M",
    }

    last_visible_row = (
            first_data_row
            + MAX_EXPERIMENT_GROUPS
            - 1
    )

    for index in range(
            MAX_EXPERIMENT_GROUPS
    ):

        row = (
                first_data_row
                + index
        )

        rank_number = (
                index
                + 1
        )

        # A: Experimentgruppe in Sortierreihenfolge
        sheet[
            f"A{row}"
        ] = (
            f'=IF('
            f'LARGE({sort_range},{rank_number})<=0,'
            f'"",'
            f'INDEX('
            f'{raw_group_range},'
            f'MATCH('
            f'LARGE({sort_range},{rank_number}),'
            f'{sort_range},'
            f'0'
            f')'
            f')'
            f')'
        )

        for header, raw_column in raw_columns.items():

            visible_column = get_column_letter(
                mapping[header]
            )

            sheet[
                f"{visible_column}{row}"
            ] = (
                f'=IF('
                f'$A{row}="",'
                f'"",'
                f'INDEX('
                f'_Gruppen_Roh!'
                f'${raw_column}${raw_first}:'
                f'${raw_column}${raw_last},'
                f'MATCH('
                f'$A{row},'
                f'{raw_group_range},'
                f'0'
                f')'
                f')'
                f')'
            )

    apply_number_formats(
        sheet,
        header_row,
        first_data_row,
    )

    # Standortzahlen dynamisch färben.
    for header in [
        "Standorte_gesamt",
        "Standorte_QX_Waermemenge_max_20pct_vorlaeufig",
    ]:

        column = mapping[
            header
        ]

        letter = get_column_letter(
            column
        )

        add_dynamic_site_count_formatting(
            sheet,
            (
                f"{letter}{first_data_row}:"
                f"{letter}{last_visible_row}"
            ),
        )

        for row in range(
                first_data_row,
                last_visible_row + 1,
        ):

            sheet.cell(
                row=row,
                column=column,
            ).font = Font(
                bold=True,
                color="000000",
            )

            sheet.cell(
                row=row,
                column=column,
            ).alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

    # Qualitätszahlen >0 orange hervorheben.
    warning_fill = PatternFill(
        fill_type="solid",
        fgColor="FCE4D6",
    )

    for header in [
        "Standorte_Zahlenpruefung_hoch_unter_Geeigneten",
        "Standorte_Eignung_kann_sich_aendern",
    ]:

        column = mapping[header]
        letter = get_column_letter(column)

        sheet.conditional_formatting.add(
            (
                f"{letter}{first_data_row}:"
                f"{letter}{last_visible_row}"
            ),
            CellIsRule(
                operator="greaterThan",
                formula=["0"],
                fill=warning_fill,
                stopIfTrue=False,
            ),
        )

    widths = {
        "A": 18,
        "B": 42,
        "C": 18,
        "D": 22,
        "E": 18,
        "F": 18,
        "G": 24,
        "H": 24,
        "I": 24,
        "J": 24,
        "K": 24,
        "L": 24,
        "M": 24,
    }

    for letter, width in widths.items():
        sheet.column_dimensions[
            letter
        ].width = width

    for row in sheet.iter_rows(
            min_row=first_data_row,
            max_row=last_visible_row,
    ):

        for cell in row:
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )


# ============================================================
# 21. ARBEITSMAPPE FERTIGSTELLEN
# ============================================================

def finalize_workbook(
        assignment_gt2,
        assignment_bis2,
        helper_data,
        all_wz3_codes,
):
    workbook = load_workbook(
        OUTPUT_FILE
    )

    # WZ3
    configure_reference_sheet(
        workbook[
            "WZ3_Gruppen"
        ],
        title=(
            "WZ3-Gruppen – Referenz für die experimentelle Zusammenlegung"
        ),
        subtitle=(
            "Die Eignung basiert jetzt auf dem QX-Anteil an der "
            "Jahreswärmemenge. Plausibilitätsauffällige positive "
            "Wärmemengen bleiben vorläufig enthalten."
        ),
        is_wz3=True,
    )

    # WZ2
    configure_reference_sheet(
        workbook[
            "WZ2_Gruppen"
        ],
        title=(
            "WZ2-Gruppen – aggregierte Referenzebene"
        ),
        subtitle=(
            "Aggregierte Sicht auf denselben vorläufigen "
            "Wärmemengenstandard."
        ),
        is_wz3=False,
    )

    # Zusammenlegung >2
    gt2_layout = configure_assignment_sheet(
        workbook[
            "Zusammenlegung_gt2"
        ],
        title=(
            "Zusammenlegung – mehr als 2 vorläufig geeignete Standorte"
        ),
        subtitle=(
            "Enthält Profil-WZ-Gruppen mit mehr als 2 Standorten, "
            "die nach den derzeit gemeldeten Jahreswärmemengen "
            "QX <= 20 % erfüllen. Zahlenauffälligkeiten sind noch "
            "nicht herausgefiltert; die Qualitätsfelder zeigen diese "
            "separat."
        ),
        row_count=len(
            assignment_gt2
        ),
    )

    # Zusammenlegung <=2
    bis2_layout = configure_assignment_sheet(
        workbook[
            "Zusammenlegung_bis2"
        ],
        title=(
            "Zusammenlegung – höchstens 2 vorläufig geeignete Standorte"
        ),
        subtitle=(
            "Enthält die übrigen Profil-WZ-Gruppen mit 0, 1 oder 2 "
            "vorläufig geeigneten Standorten. Auch diese Codes können "
            "bei Bedarf einer Experimentgruppe hinzugefügt werden."
        ),
        row_count=len(
            assignment_bis2
        ),
    )

    helper_layout = configure_hidden_data(
        workbook,
        helper_data,
        gt2_layout,
        bis2_layout,
    )

    raw_layout = configure_group_raw_sheet(
        workbook,
        helper_layout,
        gt2_layout,
        bis2_layout,
        all_wz3_codes,
    )

    configure_result_sheet(
        workbook,
        raw_layout,
    )

    # Hilfsblätter ausblenden.
    for sheet_name in [
        "_Datenbasis",
        "_Gruppen_Roh",
        "_Listen",
    ]:

        workbook[
            sheet_name
        ].sheet_state = "hidden"

    # --------------------------------------------------------
    # MANUELLE BERECHNUNG:
    #
    # So läuft die rechenintensive Ergebnissammlung nicht nach
    # jeder einzelnen G01/G02-Änderung neu an.
    #
    # Nach mehreren Änderungen:
    #
    #     F9
    #
    # --------------------------------------------------------

    try:
        workbook.calculation.calcMode = "manual"
        workbook.calculation.fullCalcOnLoad = False
        workbook.calculation.forceFullCalc = False

    except Exception:
        pass

    workbook.save(
        OUTPUT_FILE
    )


# ============================================================
# 22. HAUPTPROGRAMM
# ============================================================

def main():

    print()
    print("=" * 78)
    print(
        "WZ-GRUPPEN-ZUSAMMENLEGUNG – "
        "20-%-STANDARD NACH JAHRESWÄRMEMENGE"
    )
    print("=" * 78)
    print()

    # --------------------------------------------------------
    # 1. Bestehende manuelle Eingaben
    # --------------------------------------------------------

    print(
        "1. Bestehende Experiment-Zuordnungen werden gesucht ..."
    )

    (
        existing_assignments,
        existing_comments,
    ) = load_existing_manual_inputs()

    print(
        f"   -> {len(existing_assignments):,} "
        "bestehende Gruppenzuordnungen gefunden"
    )

    # --------------------------------------------------------
    # 2. Standortanalyse
    # --------------------------------------------------------

    print()
    print(
        "2. Neue Branchenanalyse wird eingelesen ..."
    )

    raw = load_data()

    print(
        f"   -> {len(raw):,} physische Standorte"
    )

    # --------------------------------------------------------
    # 3. Aufbereitung
    # --------------------------------------------------------

    print()
    print(
        "3. WZ-, Wärmemengen-QX- und Qualitätsfelder "
        "werden vorbereitet ..."
    )

    data = prepare_data(
        raw
    )

    print(
        "   -> Standorte mit Profil-WZ: "
        f"{data['_Profil_WZ_Code'].ne('').sum():,}"
    )

    print(
        "   -> Standorte mit WZ3: "
        f"{data['_WZ3_Code'].ne('').sum():,}"
    )

    print(
        "   -> vorläufig geeignete Standorte "
        "(QX-Wärmemenge <=20 %): "
        f"{int(data['_Filter_QX20_WAERME'].sum()):,}"
    )

    print(
        "   -> davon Standorte mit hoher Zahlen-Prüfpriorität: "
        f"{int((data['_Filter_QX20_WAERME'] & data['_Zahlenpruefung_hoch']).sum()):,}"
    )

    # --------------------------------------------------------
    # 4. Referenzblätter
    # --------------------------------------------------------

    print()
    print(
        "4. WZ3- und WZ2-Referenztabellen werden erstellt ..."
    )

    wz3_summary = build_group_summary(
        data,
        "WZ3",
    )

    wz2_summary = build_group_summary(
        data,
        "WZ2",
    )

    print(
        f"   -> {len(wz3_summary):,} WZ3-Gruppen"
    )

    print(
        f"   -> {len(wz2_summary):,} WZ2-Gruppen"
    )

    # --------------------------------------------------------
    # 5. Feinste Profil-WZ
    # --------------------------------------------------------

    print()
    print(
        "5. Profil-WZ-Gruppen werden nach der Zahl der "
        "vorläufig geeigneten Standorte aufgeteilt ..."
    )

    final_summary = build_group_summary(
        data,
        "FINAL",
    )

    (
        assignment_gt2,
        assignment_bis2,
    ) = build_assignment_tables(
        final_summary,
        existing_assignments,
        existing_comments,
    )

    print(
        "   -> >2 vorläufig geeignete Standorte: "
        f"{len(assignment_gt2):,} Gruppen"
    )

    print(
        "   -> <=2 vorläufig geeignete Standorte: "
        f"{len(assignment_bis2):,} Gruppen"
    )

    # --------------------------------------------------------
    # 6. Hilfsdaten
    # --------------------------------------------------------

    helper_data = build_helper_data(
        data
    )

    all_wz3_codes = sorted(
        {
            code
            for code
            in final_summary["WZ3_Code"].map(clean_string)
            if code
        }
    )

    # --------------------------------------------------------
    # 7. Schreiben
    # --------------------------------------------------------

    print()
    print(
        "6. Excel-Arbeitsmappe wird geschrieben ..."
    )

    write_initial_workbook(
        wz3_summary,
        wz2_summary,
        assignment_gt2,
        assignment_bis2,
        helper_data,
    )

    finalize_workbook(
        assignment_gt2,
        assignment_bis2,
        helper_data,
        all_wz3_codes,
    )

    # --------------------------------------------------------
    # Abschluss
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("FERTIG")
    print("=" * 78)
    print()

    print(
        f"Ausgabedatei:\n{OUTPUT_FILE.resolve()}"
    )

    print()
    print("Sichtbare Blätter:")
    print("  1. WZ3_Gruppen")
    print("  2. WZ2_Gruppen")
    print("  3. Zusammenlegung_gt2")
    print("  4. Zusammenlegung_bis2")
    print("  5. Gruppen_Ergebnis")

    print()
    print(
        "Neue Eignungsbasis:"
    )

    print(
        "  QX-Anteil an der JAHRESWÄRMEMENGE <= 20 %"
    )

    print()
    print(
        "Wichtig:"
    )

    print(
        "  Plausibilitätsauffällige positive Wärmemengen werden "
        "noch NICHT herausgefiltert."
    )

    print(
        "  Die entsprechenden Standorte bleiben vorläufig geeignet "
        "und werden über Qualitätsfelder markiert."
    )

    print()
    print(
        "Die Arbeitsmappe verwendet MANUELLE Excel-Berechnung."
    )

    print(
        "Nach mehreren Änderungen in den Zusammenlegungsblättern "
        "F9 drücken."
    )

    print()
    print(
        "Die Ergebnisseite sortiert automatisch nach der Zahl der "
        "vorläufig geeigneten Standorte absteigend."
    )

    print()
    print(
        "Farbskala der absoluten Standortzahlen:"
    )
    print("  <=2   rot")
    print("  3-5   orange")
    print("  6-8   dunkles Gelb")
    print("  9-10  helles Gelb")
    print("  11-17 helles Grün")
    print("  18-25 grün")
    print("  >25   dunkles Grün")

    print("=" * 78)


# ============================================================
# 23. PROGRAMMSTART
# ============================================================

if __name__ == "__main__":
    main()
