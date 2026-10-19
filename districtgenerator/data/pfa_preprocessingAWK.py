from pathlib import Path
from collections import defaultdict
import hashlib
import re

import pandas as pd


# ============================================================
# 1. GRUNDKONFIGURATION
# ============================================================

BASE_DIR = Path("WZ2025_Vorbereitung")


# ------------------------------------------------------------
# Manuell bearbeitete Hauptvalidierung
# ------------------------------------------------------------

VALIDATION_FILE = (
        BASE_DIR
        / "WZ2025_Validierung_v4.xlsx"
)

VALIDATION_ALL_SHEET = (
    "Alle_Ergebnisse"
)

VALIDATION_WZ_REVIEW_SHEET = (
    "WZ_Pruefung"
)

VALIDATION_SITE_REVIEW_SHEET = (
    "Standortverbund_Pruefung"
)


# ------------------------------------------------------------
# Zweite manuell bearbeitete Zusatzprüfung
# ------------------------------------------------------------

SUPPLEMENT_FILE = (
        BASE_DIR
        / "WZ2025_Zusatzpruefung_v1.xlsx"
)

SUPPLEMENT_MAIN_FUNCTION_SHEET = (
    "Standortverbund_Hauptfunktion"
)

SUPPLEMENT_NEW_WZ_SHEET = (
    "Neue_ohne_WZ3"
)


# ------------------------------------------------------------
# Ursprüngliche PFA-Datei
# ------------------------------------------------------------

ORIGINAL_FILE = Path(
    "pfa_datentabelle_excel.xlsx"
)

ORIGINAL_SHEET = (
    "Abwärmepotentiale"
)


# ------------------------------------------------------------
# Bestehende Masterdatei aus dem ersten
# Vorverarbeitungsschritt
# ------------------------------------------------------------

MASTER_FILE = (
        BASE_DIR
        / "WZ2025_Standorte_Master.xlsx"
)

MASTER_SITE_SHEET = (
    "Standorte"
)

MAPPING_SHEET = (
    "Mapping_Originaldaten"
)


# ------------------------------------------------------------
# NEUER Ausgabeordner
#
# Bewusst NICHT der alte Quellenklassifikationsordner.
#
# Dadurch werden bisherige Dateien nicht versehentlich
# überschrieben.
# ------------------------------------------------------------

SOURCE_OUTPUT_DIR = (
        BASE_DIR
        / "Quellenklassifikation_final"
)

SOURCE_BATCH_DIR = (
        SOURCE_OUTPUT_DIR
        / "Batches"
)


# ------------------------------------------------------------
# Eine Zeile je finalem Profilstandort
# plus Blatt mit allen ursprünglichen Teilstandorten
# ------------------------------------------------------------

SITE_CLASSIFICATION_FILE = (
        SOURCE_OUTPUT_DIR
        / "Standortklassifikation_final.xlsx"
)


# ------------------------------------------------------------
# Vollständige Tabelle mit weiterhin allen
# ursprünglichen Abwärmequellen
# ------------------------------------------------------------

ENRICHED_FILE = (
        SOURCE_OUTPUT_DIR
        / "Abwaermepotentiale_mit_WZ.xlsx"
)


# ------------------------------------------------------------
# Quellen-Batchübersicht
# ------------------------------------------------------------

BATCH_OVERVIEW_FILE = (
        SOURCE_OUTPUT_DIR
        / "Quellen_Batch_Uebersicht.xlsx"
)


# ------------------------------------------------------------
# Quellenklassifikations-Batches
# ------------------------------------------------------------

SOURCE_BATCH_SIZE = 500


# Alte Batches innerhalb des NEUEN finalen Ausgabeordners
# beim erneuten Start entfernen.
CLEAR_OLD_SOURCE_BATCHES = True


# ============================================================
# 2. ALLGEMEINE HILFSFUNKTIONEN
# ============================================================

def clean_column_name(
        column_name: str,
) -> str:
    """
    Bereinigt Zeilenumbrüche und Mehrfachleerzeichen
    in Excel-Spaltennamen.
    """

    text = str(
        column_name
    )

    text = (
        text
        .replace(
            "\n",
            " ",
        )
        .replace(
            "\r",
            " ",
        )
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def clean_string(
        value,
) -> str:
    """
    NaN / None -> leerer String.

    Sonst sauberer String.
    """

    if pd.isna(
            value
    ):

        return ""

    text = str(
        value
    ).strip()

    if text.lower() in {
        "nan",
        "none",
    }:

        return ""

    return text


def unique_join(
        series,
        separator=" | ",
) -> str:
    """
    Verbindet eindeutige nichtleere Werte.

    Reihenfolge des ersten Auftretens bleibt erhalten.
    """

    seen = set()

    values = []


    for value in series:

        value = clean_string(
            value
        )

        if (
                value
                and
                value not in seen
        ):

            seen.add(
                value
            )

            values.append(
                value
            )


    return separator.join(
        values
    )


def first_non_empty(
        series,
) -> str:
    """
    Gibt den ersten nichtleeren Wert zurück.
    """

    for value in series:

        value = clean_string(
            value
        )

        if value:

            return value

    return ""


# ============================================================
# 3. WZ-CODE-HILFSFUNKTIONEN
# ============================================================

def normalize_wz_code(
        value,
) -> str:
    """
    Bereinigt einen WZ-Code, ohne seine Tiefe zu reduzieren.

    Beispiele:

        38.21 -> 38.21
        38.2  -> 38.2
        5.1   -> 05.1
        35    -> 35

    WICHTIG:

        38.21 bleibt exakt 38.21.

    Der Code wird NICHT auf 38.2 reduziert.
    """

    text = (
        clean_string(
            value
        )
        .replace(
            ",",
            ".",
        )
        .replace(
            " ",
            "",
        )
    )


    if not text:

        return ""


    match = re.match(
        r"^(\d{1,2})(.*)$",
        text,
    )


    if not match:

        # z. B. Abschnittscode C
        return text


    division = int(
        match.group(1)
    )

    remainder = (
        match.group(2)
    )


    return (
        f"{division:02d}"
        f"{remainder}"
    )


def derive_wz3(
        value,
) -> str:
    """
    Leitet ZUSÄTZLICH die übergeordnete WZ-Gruppe ab.

    Der finale Code selbst wird NICHT verändert.

    Beispiele:

        38.21 -> 38.2
        38.2  -> 38.2
        20.3  -> 20.3
        05.1  -> 05.1
        38    -> ""
    """

    text = normalize_wz_code(
        value
    )


    match = re.match(
        r"^(\d{2})\.(\d)",
        text,
    )


    if not match:

        return ""


    return (
        f"{match.group(1)}."
        f"{match.group(2)}"
    )


def derive_wz2(
        value,
) -> str:
    """
    Leitet die zweistellige WZ-Abteilung ab.

    Beispiele:

        38.21 -> 38
        38.2  -> 38
        20.3  -> 20
        05.1  -> 05
        35    -> 35
    """

    text = normalize_wz_code(
        value
    )


    match = re.match(
        r"^(\d{2})",
        text,
    )


    if not match:

        return ""


    return match.group(1)


def infer_wz_level(
        value,
) -> str:
    """
    Technische Beschreibung der tatsächlich vorhandenen Tiefe.

    Die feineren Codes werden bewusst nicht automatisch
    auf offizielle Ebenennamen gezwungen.

    Dadurch bleibt z.B. 38.21 methodisch sauber erhalten.
    """

    text = normalize_wz_code(
        value
    )


    if not text:

        return ""


    if re.fullmatch(
            r"\d{2}",
            text,
    ):

        return "Abteilung"


    if re.fullmatch(
            r"\d{2}\.\d",
            text,
    ):

        return "Gruppe"


    if re.fullmatch(
            r"\d{2}\.\d+",
            text,
    ):

        return "Feiner_als_Gruppe"


    if re.fullmatch(
            r"[A-Za-z]",
            text,
    ):

        return "Abschnitt"


    return "Sonstige_Ebene"


def usable_safe_code(
        row,
) -> str:
    """
    WZ_Sicherer_Code darf als Fallback verwendet werden,
    sofern es ein numerischer WZ-Code ist.

    Ein reiner Abschnitt wie "C" wird NICHT als finaler
    Branchen-Code verwendet.
    """

    safe_code = normalize_wz_code(
        row.get(
            "WZ_Sicherer_Code",
            "",
        )
    )


    if re.match(
            r"^\d{2}",
            safe_code,
    ):

        return safe_code


    return ""


def determine_wz_status(
        final_code: str,
) -> str:
    """
    Finaler WZ-Status nach allen manuellen Prüfungen.
    """

    final_code = normalize_wz_code(
        final_code
    )


    if derive_wz3(
            final_code
    ):

        return (
            "klassifiziert_mit_WZ3"
        )


    if derive_wz2(
            final_code
    ):

        return (
            "klassifiziert_nur_WZ2"
        )


    return (
        "nicht_sicher_klassifizierbar"
    )


# ============================================================
# 4. ORIGINALDATEI EINLESEN
# ============================================================

def load_original_data() -> pd.DataFrame:
    """
    Liest die vollständige PFA-Tabelle.

    Excel-Zeile 1:
        Themenüberschriften

    Excel-Zeile 2:
        echte Spaltennamen

    Deshalb:
        header=1
    """

    df = pd.read_excel(

        ORIGINAL_FILE,

        sheet_name=
        ORIGINAL_SHEET,

        header=1,

        dtype=str,

        keep_default_na=False,
    )


    # --------------------------------------------------------
    # Spaltennamen bereinigen
    # --------------------------------------------------------

    df.columns = [

        clean_column_name(
            column
        )

        for column
        in df.columns
    ]


    # --------------------------------------------------------
    # ID-Spalten vereinheitlichen
    # --------------------------------------------------------

    df = df.rename(
        columns={

            "Unternehmens- ID":
                "Unternehmens_ID",

            "Melde- ID":
                "Melde_ID",
        }
    )


    # --------------------------------------------------------
    # Erwartete Spalten
    # --------------------------------------------------------

    required_columns = {

        "Unternehmens_ID",

        "Melde_ID",

        "Firmenname",

        "Standortname",

        "Straße und Hausnummer",

        "PLZ",

        "Ort",

        "Name des Abwärmepotentials",

        "Wärmemenge pro Jahr (in kWh/a)",

        "Maximale thermische Leistung (in kW)",

        "Durchschnittliches Temperaturniveau (in °C)",

        "Temperaturbereich",

        "Ergänzende Informationen zum Abwärmepotential",

        "Weitere Hinweise",
    }


    missing = (
            required_columns
            - set(
        df.columns
    )
    )


    if missing:

        raise ValueError(

            "In der ursprünglichen PFA-Datei "
            "fehlen Spalten:\n\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    # --------------------------------------------------------
    # Originaldatensatz_ID exakt wie ursprünglich
    # wiederherstellen.
    # --------------------------------------------------------

    df.insert(

        0,

        "Originaldatensatz_ID",

        range(
            1,
            len(df) + 1,
            ),
    )


    # Tatsächliche Excel-Zeile
    df.insert(

        1,

        "Original_Excel_Zeile",

        df.index + 3,
        )


    return df


# ============================================================
# 5. ORIGINALDATEN-MAPPING EINLESEN
# ============================================================

def load_mapping() -> pd.DataFrame:
    """
    Technische Verbindung:

        Originaldatensatz_ID
        ->
        Klassifikations_ID
    """

    mapping = pd.read_excel(

        MASTER_FILE,

        sheet_name=
        MAPPING_SHEET,

        dtype=str,

        keep_default_na=False,
    )


    required = {

        "Originaldatensatz_ID",

        "Klassifikations_ID",
    }


    missing = (
            required
            - set(
        mapping.columns
    )
    )


    if missing:

        raise ValueError(

            "Im Mapping fehlen Spalten:\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    mapping[
        "Originaldatensatz_ID"
    ] = (

        pd.to_numeric(

            mapping[
                "Originaldatensatz_ID"
            ],

            errors="raise",
        )

        .astype(int)
    )


    mapping[
        "Klassifikations_ID"
    ] = (

        mapping[
            "Klassifikations_ID"
        ]

        .map(
            clean_string
        )
    )


    if (
            mapping[
                "Originaldatensatz_ID"
            ]
                    .duplicated()
                    .any()
    ):

        raise ValueError(

            "Originaldatensatz_ID kommt "
            "im Mapping mehrfach vor."
        )


    return mapping[
        [
            "Originaldatensatz_ID",
            "Klassifikations_ID",
        ]
    ].copy()


# ============================================================
# 6. STANDORT-MASTER EINLESEN
# ============================================================

def load_master_sites() -> pd.DataFrame:
    """
    Lädt die ursprünglichen Klassifikations_IDs.

    Diese IDs bleiben vollständig erhalten, auch wenn
    mehrere davon später zu einem Standortverbund gehören.
    """

    sites = pd.read_excel(

        MASTER_FILE,

        sheet_name=
        MASTER_SITE_SHEET,

        dtype=str,

        keep_default_na=False,
    )


    # --------------------------------------------------------
    # Unterschiedliche mögliche Schreibweisen vereinheitlichen
    # --------------------------------------------------------

    sites = sites.rename(
        columns={

            "Straße und Hausnummer":
                "Strasse_Hausnummer",

            "Straße_Hausnummer":
                "Strasse_Hausnummer",
        }
    )


    required = {

        "Klassifikations_ID",

        "Unternehmens_ID",

        "Firmenname",

        "Standortname",
    }


    missing = (
            required
            - set(
        sites.columns
    )
    )


    if missing:

        raise ValueError(

            "Im Standort-Master fehlen Spalten:\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    sites[
        "Klassifikations_ID"
    ] = (

        sites[
            "Klassifikations_ID"
        ]

        .map(
            clean_string
        )
    )


    if not sites[
        "Klassifikations_ID"
    ].is_unique:

        raise ValueError(

            "Klassifikations_ID ist im "
            "Standort-Master nicht eindeutig."
        )


    return sites


# ============================================================
# 7. ORIGINALDATEI UND MAPPING PRÜFEN
# ============================================================

def validate_original_mapping(
        original,
        mapping,
):

    original_ids = set(

        original[
            "Originaldatensatz_ID"
        ]
    )


    mapping_ids = set(

        mapping[
            "Originaldatensatz_ID"
        ]
    )


    if (
            original_ids
            != mapping_ids
    ):

        raise ValueError(

            "Originaldatei und bestehendes Mapping "
            "enthalten nicht exakt dieselben "
            "Originaldatensatz_IDs."
        )


# ============================================================
# 8. HILFSFUNKTION FÜR EXCEL-BLÄTTER
# ============================================================

def read_required_sheet(
        file_path: Path,
        sheet_name: str,
) -> pd.DataFrame:
    """
    Liest ein Pflichtblatt.

    Fehlt Datei oder Blatt, wird mit klarer Meldung gestoppt.
    """

    if not file_path.exists():

        raise FileNotFoundError(

            f"Datei nicht gefunden:\n"
            f"{file_path}"
        )


    excel = pd.ExcelFile(
        file_path
    )


    if (
            sheet_name
            not in excel.sheet_names
    ):

        raise ValueError(

            f"Blatt '{sheet_name}' fehlt in:\n"
            f"{file_path}"
        )


    return pd.read_excel(

        file_path,

        sheet_name=
        sheet_name,

        dtype=str,

        keep_default_na=False,
    )


# ============================================================
# 9. BEIDE MANUELLEN PRÜFDATEIEN EINLESEN
# ============================================================

def load_manual_validation_files():
    """
    Liest:

    WZ2025_Validierung_v4.xlsx
        - Alle_Ergebnisse
        - WZ_Pruefung
        - Standortverbund_Pruefung

    WZ2025_Zusatzpruefung_v1.xlsx
        - Standortverbund_Hauptfunktion
        - Neue_ohne_WZ3
    """

    all_results = read_required_sheet(

        VALIDATION_FILE,

        VALIDATION_ALL_SHEET,
    )


    wz_review = read_required_sheet(

        VALIDATION_FILE,

        VALIDATION_WZ_REVIEW_SHEET,
    )


    site_review = read_required_sheet(

        VALIDATION_FILE,

        VALIDATION_SITE_REVIEW_SHEET,
    )


    main_function_review = (
        read_required_sheet(

            SUPPLEMENT_FILE,

            SUPPLEMENT_MAIN_FUNCTION_SHEET,
        )
    )


    new_wz_review = read_required_sheet(

        SUPPLEMENT_FILE,

        SUPPLEMENT_NEW_WZ_SHEET,
    )


    if not all_results[
        "Klassifikations_ID"
    ].is_unique:

        raise ValueError(

            "Klassifikations_ID ist in "
            "Alle_Ergebnisse nicht eindeutig."
        )


    return (

        all_results,

        wz_review,

        site_review,

        main_function_review,

        new_wz_review,
    )


# ============================================================
# 10. MANUELLE PRÜFUNGEN AUF VOLLSTÄNDIGKEIT PRÜFEN
# ============================================================

def validate_manual_reviews(
        wz_review,
        site_review,
        main_function_review,
        new_wz_review,
):
    """
    Stoppt absichtlich, wenn noch relevante manuelle
    Entscheidungen offen sind.
    """


    # ========================================================
    # A) ERSTE WZ-PRÜFUNG
    # ========================================================

    if not wz_review.empty:

        decisions = (

            wz_review[
                "WZ_Entscheidung"
            ]

            .map(
                clean_string
            )

            .str.upper()
        )


        open_mask = (
            decisions.isin(
                {
                    "",
                    "OFFEN",
                }
            )
        )


        if open_mask.any():

            raise ValueError(

                "WZ_Pruefung enthält noch "
                f"{open_mask.sum()} offene Fälle."
            )


        correction_mask = (

            decisions
            .eq(
                "WZ_KORRIGIEREN"
            )
        )


        missing_code = (

                correction_mask

                &

                wz_review[
                    "WZ_Manuell_Code"
                ]
                .map(
                    clean_string
                )
                .eq("")
        )


        if missing_code.any():

            raise ValueError(

                "Bei WZ_KORRIGIEREN fehlt "
                "mindestens einmal WZ_Manuell_Code."
            )


    # ========================================================
    # B) STANDORTVERBUND-PRÜFUNG
    # ========================================================

    if not site_review.empty:

        decisions = (

            site_review[
                "Standortverbund_Entscheidung"
            ]

            .map(
                clean_string
            )

            .str.upper()
        )


        open_mask = (
            decisions.isin(
                {
                    "",
                    "OFFEN",
                }
            )
        )


        if open_mask.any():

            raise ValueError(

                "Standortverbund_Pruefung enthält noch "
                f"{open_mask.sum()} offene Fälle."
            )


    # ========================================================
    # C) ZUSATZPRÜFUNG NEUE WZ-FÄLLE
    # ========================================================

    if not new_wz_review.empty:

        decisions = (

            new_wz_review[
                "Neue_WZ_Entscheidung"
            ]

            .map(
                clean_string
            )

            .str.upper()
        )


        open_mask = (
            decisions.isin(
                {
                    "",
                    "OFFEN",
                }
            )
        )


        if open_mask.any():

            raise ValueError(

                "Neue_ohne_WZ3 enthält noch "
                f"{open_mask.sum()} offene Fälle."
            )


        set_code = (
            decisions
            .eq(
                "WZ_CODE_FESTLEGEN"
            )
        )


        missing_code = (

                set_code

                &

                new_wz_review[
                    "WZ_Manuell_Code"
                ]
                .map(
                    clean_string
                )
                .eq("")
        )


        if missing_code.any():

            raise ValueError(

                "Bei WZ_CODE_FESTLEGEN fehlt "
                "mindestens einmal WZ_Manuell_Code."
            )


    # Die Hauptfunktionsprüfung wird später gruppenweise
    # noch strenger geprüft:
    #
    # Genau EINE JA-Zeile pro Standortverbund.


# ============================================================
# 11. WZ3-BEZEICHNUNGEN AUS KI-ERGEBNISSEN ABLEITEN
# ============================================================

def build_wz3_label_lookup(
        all_results: pd.DataFrame,
) -> dict:
    """
    Nutzt die bereits vorhandenen KI-Bezeichnungen.

    Für manuell feinere Codes wie 38.21 bleibt die
    übergeordnete WZ3-Bezeichnung von 38.2 separat erhalten.
    """

    lookup = {}


    for _, row in (
            all_results.iterrows()
    ):

        code = derive_wz3(

            row.get(
                "WZ_Gruppe_Code",
                "",
            )
        )


        label = clean_string(

            row.get(
                "WZ_Gruppe_Bezeichnung",
                "",
            )
        )


        if (
                code
                and
                label
                and
                code not in lookup
        ):

            lookup[
                code
            ] = label


    return lookup


# ============================================================
# 12. MANUELLE WZ-KORREKTUREN ANWENDEN
# ============================================================

def apply_manual_wz_corrections(
        all_results,
        wz_review,
        new_wz_review,
):
    """
    Erzeugt pro ursprünglicher Klassifikations_ID
    einen finalen WZ-Code.

    Reihenfolge:

    1. KI-Ausgangscode / sicherer Fallback
    2. WZ_Pruefung aus Validierung v4
    3. Neue_ohne_WZ3 aus Zusatzprüfung

    Wichtig:

    Ein manueller Code wie

        38.21

    bleibt exakt

        38.21

    und wird NICHT durch 38.2 ersetzt.
    """


    result = all_results.copy()


    # ========================================================
    # A) ERSTE MANUELLE WZ-PRÜFUNG ANBINDEN
    # ========================================================

    first_manual_columns = [

        "Klassifikations_ID",

        "WZ_Entscheidung",

        "WZ_Manuell_Code",

        "WZ_Manuell_Begruendung",
    ]


    missing = (

            set(
                first_manual_columns
            )

            - set(
        wz_review.columns
    )
    )


    if missing:

        raise ValueError(

            "In WZ_Pruefung fehlen Spalten:\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    first_manual = (

        wz_review[
            first_manual_columns
        ]

        .drop_duplicates(
            subset=[
                "Klassifikations_ID"
            ],
            keep="last",
        )

        .rename(
            columns={

                "WZ_Entscheidung":
                    "WZ_Entscheidung_V4",

                "WZ_Manuell_Code":
                    "WZ_Manuell_Code_V4",

                "WZ_Manuell_Begruendung":
                    "WZ_Manuell_Begruendung_V4",
            }
        )
    )


    result = result.merge(

        first_manual,

        on=
        "Klassifikations_ID",

        how=
        "left",

        validate=
        "1:1",
    )


    for column in [

        "WZ_Entscheidung_V4",

        "WZ_Manuell_Code_V4",

        "WZ_Manuell_Begruendung_V4",

    ]:

        result[
            column
        ] = (

            result[
                column
            ]

            .fillna("")

            .map(
                clean_string
            )
        )


    final_codes = []

    final_sources = []

    final_reasons = []


    for _, row in (
            result.iterrows()
    ):


        ai_group_code = (
            normalize_wz_code(

                row.get(
                    "WZ_Gruppe_Code",
                    "",
                )
            )
        )


        safe_code = (
            usable_safe_code(
                row
            )
        )


        decision = (

            clean_string(

                row.get(
                    "WZ_Entscheidung_V4",
                    "",
                )
            )

            .upper()
        )


        manual_code = (
            normalize_wz_code(

                row.get(
                    "WZ_Manuell_Code_V4",
                    "",
                )
            )
        )


        manual_reason = clean_string(

            row.get(
                "WZ_Manuell_Begruendung_V4",
                "",
            )
        )


        # ----------------------------------------------------
        # Ausgangspunkt:
        #
        # bevorzugt sichere WZ-Gruppe der KI.
        #
        # Falls diese fehlt:
        # sicherer numerischer Fallback.
        # ----------------------------------------------------

        final_code = (
                ai_group_code
                or
                safe_code
        )


        if ai_group_code:

            source = "KI"

        elif safe_code:

            source = (
                "KI_SICHERER_FALLBACK"
            )

        else:

            source = (
                "KEIN_SICHERER_CODE"
            )


        reason = ""


        # ====================================================
        # MANUELLE ENTSCHEIDUNGEN
        # ====================================================

        if (
                decision
                ==
                "KI_BESTAETIGT"
        ):

            source = (
                "KI_MANUELL_BESTAETIGT"
            )

            reason = (
                manual_reason
            )


        elif (
                decision
                ==
                "WZ_KORRIGIEREN"
        ):

            final_code = (
                manual_code
            )

            source = (
                "MANUELL_KORRIGIERT"
            )

            reason = (
                manual_reason
            )


        elif (
                decision
                ==
                "NUR_WZ2_SICHER"
        ):

            # WZ_Manuell_Ebene wird bewusst NICHT verwendet.
            #
            # Entscheidend ist ausschließlich der tatsächlich
            # eingetragene WZ_Manuell_Code.

            final_code = (

                    manual_code

                    or

                    derive_wz2(
                        safe_code
                    )

                    or

                    derive_wz2(
                        ai_group_code
                    )
            )


            source = (
                "MANUELL_NUR_WZ2"
            )

            reason = (
                manual_reason
            )


        elif (
                decision
                ==
                "NICHT_SICHER_KLASSIFIZIERBAR"
        ):

            final_code = ""

            source = (
                "MANUELL_NICHT_SICHER_KLASSIFIZIERBAR"
            )

            reason = (
                manual_reason
            )


        final_codes.append(
            normalize_wz_code(
                final_code
            )
        )


        final_sources.append(
            source
        )


        final_reasons.append(
            reason
        )


    result[
        "WZ_Final_Code"
    ] = final_codes


    result[
        "WZ_Final_Herkunft"
    ] = final_sources


    result[
        "WZ_Manuell_Begruendung"
    ] = final_reasons


    # ========================================================
    # B) ZUSATZPRÜFUNG "NEUE_OHNE_WZ3"
    # ========================================================

    extra_columns = [

        "Klassifikations_ID",

        "Neue_WZ_Entscheidung",

        "WZ_Manuell_Code",

        "WZ_Manuell_Begruendung",
    ]


    missing = (

            set(
                extra_columns
            )

            - set(
        new_wz_review.columns
    )
    )


    if missing:

        raise ValueError(

            "In Neue_ohne_WZ3 fehlen Spalten:\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    extra = (

        new_wz_review[
            extra_columns
        ]

        .drop_duplicates(
            subset=[
                "Klassifikations_ID"
            ],
            keep="last",
        )

        .rename(
            columns={

                "Neue_WZ_Entscheidung":
                    "Neue_WZ_Entscheidung_Zusatz",

                "WZ_Manuell_Code":
                    "WZ_Manuell_Code_Zusatz",

                "WZ_Manuell_Begruendung":
                    "WZ_Manuell_Begruendung_Zusatz",
            }
        )
    )


    result = result.merge(

        extra,

        on=
        "Klassifikations_ID",

        how=
        "left",

        validate=
        "1:1",
    )


    for column in [

        "Neue_WZ_Entscheidung_Zusatz",

        "WZ_Manuell_Code_Zusatz",

        "WZ_Manuell_Begruendung_Zusatz",

    ]:

        result[
            column
        ] = (

            result[
                column
            ]

            .fillna("")

            .map(
                clean_string
            )
        )


    # --------------------------------------------------------
    # Zusatzentscheidungen überschreiben ggf. die erste
    # Entscheidung.
    # --------------------------------------------------------

    for index, row in (
            result.iterrows()
    ):


        decision = (

            clean_string(

                row[
                    "Neue_WZ_Entscheidung_Zusatz"
                ]
            )

            .upper()
        )


        if not decision:

            continue


        manual_code = (
            normalize_wz_code(

                row[
                    "WZ_Manuell_Code_Zusatz"
                ]
            )
        )


        manual_reason = clean_string(

            row[
                "WZ_Manuell_Begruendung_Zusatz"
            ]
        )


        if (
                decision
                ==
                "WZ_CODE_FESTLEGEN"
        ):

            result.at[
                index,
                "WZ_Final_Code",
            ] = manual_code


            result.at[
                index,
                "WZ_Final_Herkunft",
            ] = (
                "MANUELL_ZUSATZ_WZ_CODE"
            )


            result.at[
                index,
                "WZ_Manuell_Begruendung",
            ] = manual_reason


        elif (
                decision
                ==
                "NUR_WZ2_SICHER"
        ):

            existing_wz2 = (
                derive_wz2(

                    result.at[
                        index,
                        "WZ_Final_Code",
                    ]
                )
            )


            safe_wz2 = (
                derive_wz2(

                    usable_safe_code(
                        row
                    )
                )
            )


            result.at[
                index,
                "WZ_Final_Code",
            ] = (

                    manual_code

                    or

                    existing_wz2

                    or

                    safe_wz2
            )


            result.at[
                index,
                "WZ_Final_Herkunft",
            ] = (
                "MANUELL_ZUSATZ_NUR_WZ2"
            )


            result.at[
                index,
                "WZ_Manuell_Begruendung",
            ] = manual_reason


        elif (
                decision
                ==
                "NICHT_SICHER_KLASSIFIZIERBAR"
        ):

            result.at[
                index,
                "WZ_Final_Code",
            ] = ""


            result.at[
                index,
                "WZ_Final_Herkunft",
            ] = (
                "MANUELL_ZUSATZ_NICHT_SICHER"
            )


            result.at[
                index,
                "WZ_Manuell_Begruendung",
            ] = manual_reason


    # ========================================================
    # FINALE WZ-HIERARCHIE ZUSÄTZLICH ABLEITEN
    # ========================================================

    result[
        "WZ_Final_Code"
    ] = (

        result[
            "WZ_Final_Code"
        ]

        .map(
            normalize_wz_code
        )
    )


    result[
        "WZ_Final_Ebene"
    ] = (

        result[
            "WZ_Final_Code"
        ]

        .map(
            infer_wz_level
        )
    )


    result[
        "WZ3_Code"
    ] = (

        result[
            "WZ_Final_Code"
        ]

        .map(
            derive_wz3
        )
    )


    result[
        "WZ2_Code"
    ] = (

        result[
            "WZ_Final_Code"
        ]

        .map(
            derive_wz2
        )
    )


    result[
        "WZ_Status"
    ] = (

        result[
            "WZ_Final_Code"
        ]

        .map(
            determine_wz_status
        )
    )


    # --------------------------------------------------------
    # WZ3-Bezeichnungen aus den vorhandenen KI-Batches
    # --------------------------------------------------------

    label_lookup = (
        build_wz3_label_lookup(
            all_results
        )
    )


    result[
        "WZ3_Bezeichnung"
    ] = (

        result[
            "WZ3_Code"
        ]

        .map(
            label_lookup
        )

        .fillna("")
    )


    return result


# ============================================================
# 13. STANDORTVERBUND-PRÜFUNG INTERPRETIEREN
# ============================================================

def interpret_site_review(
        site_review: pd.DataFrame,
) -> pd.DataFrame:
    """
    Unterstützt deine drei Varianten:

    ZUSAMMENFASSEN
    GETRENNT_LASSEN

    sowie deine eigenen Kennungen:

    ID1
    ID2
    ID3
    ...

    Eigene IDs gelten immer nur innerhalb des jeweiligen
    Kandidatenverbundes.
    """

    required = {

        "Kandidatenverbund_ID",

        "Klassifikations_ID",

        "Standortverbund_Entscheidung",

        "Standortverbund_Gruppe",

        "Standortverbund_Begruendung",
    }


    missing = (
            required
            - set(
        site_review.columns
    )
    )


    if missing:

        raise ValueError(

            "In Standortverbund_Pruefung fehlen Spalten:\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    work = (
        site_review.copy()
    )


    group_keys = []


    for _, row in (
            work.iterrows()
    ):


        candidate = clean_string(

            row[
                "Kandidatenverbund_ID"
            ]
        )


        decision = (

            clean_string(

                row[
                    "Standortverbund_Entscheidung"
                ]
            )

            .upper()
        )


        manual_group = clean_string(

            row[
                "Standortverbund_Gruppe"
            ]
        )


        # ====================================================
        # A) KOMPLETT ZUSAMMENFASSEN
        # ====================================================

        if (
                decision
                ==
                "ZUSAMMENFASSEN"
        ):

            # Exakt dieselbe Logik wie beim Erzeugen
            # der Zusatzprüfdatei.

            group_key = (

                    manual_group

                    or

                    candidate
            )


        # ====================================================
        # B) GETRENNT LASSEN
        # ====================================================

        elif (
                decision
                ==
                "GETRENNT_LASSEN"
        ):

            group_key = ""


        # ====================================================
        # C) EIGENE TEILGRUPPE
        #
        # z. B.
        #
        # ID1
        # ID2
        #
        # Die Kennung wird mit der Kandidaten-ID kombiniert,
        # damit "ID1" aus zwei unterschiedlichen Kandidaten
        # niemals versehentlich zusammengeführt wird.
        # ====================================================

        else:

            group_key = (

                f"{candidate}::"
                f"{decision}"
            )


        group_keys.append(
            group_key
        )


    work[
        "_Review_Group_Key"
    ] = group_keys


    # --------------------------------------------------------
    # Nur Gruppen mit mindestens 2 Standorten sind
    # tatsächlich Standortverbünde.
    # --------------------------------------------------------

    counts = (

        work.loc[

            work[
                "_Review_Group_Key"
            ].ne(""),

            "_Review_Group_Key",
        ]

        .value_counts()
    )


    valid_groups = set(

        counts[
            counts >= 2
            ].index
    )


    work[
        "_Confirmed_Merge"
    ] = (

        work[
            "_Review_Group_Key"
        ]

        .isin(
            valid_groups
        )
    )


    # Singleton-Untergruppen:
    # konservativ als Einzelstandort behandeln.

    work.loc[

        ~work[
            "_Confirmed_Merge"
        ],

        "_Review_Group_Key",

    ] = ""


    return work


# ============================================================
# 14. FINALE STANDORTSTRUKTUR ERZEUGEN
# ============================================================

def build_final_site_structure(
        master_sites,
        effective_wz,
        site_review,
        main_function_review,
):
    """
    Erzeugt zwei Ebenen:

    1. Teilstandorte
       ----------------
       weiterhin eine Zeile je ursprünglicher
       Klassifikations_ID

    2. Standortverbünde / Profilstandorte
       ----------------
       eine Zeile je finalem physischen Standort

    WICHTIG:

    Die ursprüngliche WZ des Teilstandorts bleibt erhalten.

    Zusätzlich wird die von dir ausgewählte Hauptfunktion
    als Profil-WZ für den gesamten Standortverbund gespeichert.

    Beispiel:

        Krankenhaus:
            WZ 86.1

        BHKW:
            WZ 35.3

        Standortverbund:
            Profil-WZ = 86.1

    Die BHKW-Quelle bleibt trotzdem Bestandteil des
    Krankenhaus-Standortprofils.
    """

    master = (
        master_sites
        .copy()
        .reset_index(
            drop=True
        )
    )


    master[
        "_Master_Order"
    ] = range(
        len(
            master
        )
    )


    # ========================================================
    # ID-MENGEN MÜSSEN IDENTISCH SEIN
    # ========================================================

    master_ids = set(

        master[
            "Klassifikations_ID"
        ]
    )


    wz_ids = set(

        effective_wz[
            "Klassifikations_ID"
        ]
    )


    if (
            master_ids
            != wz_ids
    ):

        raise ValueError(

            "Standort-Master und finale WZ-Ergebnisse "
            "enthalten nicht exakt dieselben "
            "Klassifikations_IDs."
        )


    # ========================================================
    # STANDORTVERBUND-ENTSCHEIDUNGEN INTERPRETIEREN
    # ========================================================

    interpreted_review = (
        interpret_site_review(
            site_review
        )
    )


    unknown_review_ids = (

            set(
                interpreted_review[
                    "Klassifikations_ID"
                ]
            )

            - master_ids
    )


    if unknown_review_ids:

        raise ValueError(

            "Standortverbund_Pruefung enthält "
            "unbekannte Klassifikations_IDs."
        )


    # ========================================================
    # REVIEW-INFOS AUF ALLE TEILSTANDORTE ÜBERTRAGEN
    # ========================================================

    review_lookup = (

        interpreted_review[
            [
                "Klassifikations_ID",

                "_Review_Group_Key",

                "Standortverbund_Entscheidung",

                "Standortverbund_Begruendung",
            ]
        ]

        .drop_duplicates(
            subset=[
                "Klassifikations_ID"
            ],
            keep="last",
        )
    )


    part_sites = master.merge(

        review_lookup,

        on=
        "Klassifikations_ID",

        how=
        "left",

        validate=
        "1:1",
    )


    for column in [

        "_Review_Group_Key",

        "Standortverbund_Entscheidung",

        "Standortverbund_Begruendung",

    ]:

        part_sites[
            column
        ] = (

            part_sites[
                column
            ]

            .fillna("")

            .map(
                clean_string
            )
        )


    # ========================================================
    # FINALE WZ-INFORMATIONEN ANBINDEN
    # ========================================================

    # --------------------------------------------------------
    # Ab diesem Punkt sind die WZ-Informationen aus
    # effective_wz die maßgebliche Quelle.
    #
    # Der alte Standort-Master kann bereits einzelne
    # WZ-/Tätigkeitsspalten enthalten.
    #
    # Würden wir diese einfach mitmergen, erzeugt pandas
    # Spalten wie:
    #
    #     Standorttaetigkeit_kurz_x
    #     Standorttaetigkeit_kurz_y
    #
    # Deshalb werden eventuell bereits vorhandene alte
    # WZ-Kontextspalten vor dem Merge bewusst entfernt.
    # --------------------------------------------------------

    keep_wz_columns = [

        "Klassifikations_ID",

        "WZ_Final_Code",

        "WZ_Final_Ebene",

        "WZ3_Code",

        "WZ2_Code",

        "WZ3_Bezeichnung",

        "WZ_Status",

        "WZ_Final_Herkunft",

        "WZ_Manuell_Begruendung",

        # ursprüngliche KI-Klassifikation
        "WZ_Gruppe_Code",

        "WZ_Gruppe_Bezeichnung",

        "Standorttaetigkeit_kurz",

        "Konfidenz",

        "Gesamt_Check",

        "Standortfunktion",

        "Referenz_Mehrfach_Match",
    ]


    # --------------------------------------------------------
    # Nur Spalten verwenden, die in effective_wz tatsächlich
    # vorhanden sind.
    # --------------------------------------------------------

    keep_wz_columns = [

        column

        for column in keep_wz_columns

        if column in effective_wz.columns
    ]


    wz_context = (

        effective_wz[
            keep_wz_columns
        ]

        .copy()
    )


    # --------------------------------------------------------
    # Sicherheitscheck:
    # Klassifikations_ID muss dort eindeutig sein.
    # --------------------------------------------------------

    if not wz_context[
        "Klassifikations_ID"
    ].is_unique:

        raise ValueError(

            "Klassifikations_ID ist in der finalen "
            "WZ-Tabelle nicht eindeutig."
        )


    # ========================================================
    # ALTE / DOPPELTE WZ-SPALTEN AUS DEM MASTER ENTFERNEN
    # ========================================================

    overlapping_columns = [

        column

        for column in wz_context.columns

        if (
                column != "Klassifikations_ID"
                and
                column in part_sites.columns
        )
    ]


    if overlapping_columns:

        print(
            "   -> Bereits vorhandene alte WZ-Kontextspalten "
            "im Standort-Master werden ersetzt:"
        )

        for column in overlapping_columns:

            print(
                f"      - {column}"
            )


        part_sites = part_sites.drop(
            columns=
            overlapping_columns
        )


    # ========================================================
    # MANUELL KORRIGIERTE WZ-INFORMATIONEN ANBINDEN
    # ========================================================

    part_sites = part_sites.merge(

        wz_context,

        on=
        "Klassifikations_ID",

        how=
        "left",

        validate=
        "1:1",
    )


    # ========================================================
    # ERWARTETE KONTEXTSPALTEN SICHERSTELLEN
    #
    # Einige ältere Dateien könnten einzelne optionale Felder
    # noch nicht enthalten. Für diese Felder ist ein leerer
    # Wert zulässig.
    # ========================================================

    optional_wz_columns = [

        "Standorttaetigkeit_kurz",

        "Standortfunktion",

        "Referenz_Mehrfach_Match",

        "Konfidenz",

        "Gesamt_Check",

        "WZ_Gruppe_Code",

        "WZ_Gruppe_Bezeichnung",
    ]


    for column in optional_wz_columns:

        if column not in part_sites.columns:

            part_sites[
                column
            ] = ""


    # ========================================================
    # KI-FELDER EINDEUTIG BENENNEN
    # ========================================================

    part_sites = part_sites.rename(
        columns={

            "WZ_Gruppe_Code":
                "WZ_AI_Gruppe_Code",

            "WZ_Gruppe_Bezeichnung":
                "WZ_AI_Gruppe_Bezeichnung",

            "Konfidenz":
                "WZ_AI_Konfidenz",

            "Gesamt_Check":
                "WZ_Qualitaetsflag",
        }
    )


    # ========================================================
    # FINALE STANDORTVERBUND_ID
    # ========================================================

    # Standard:
    # jeder bisherige Standort bleibt zunächst eigenständig.

    part_sites[
        "Standortverbund_ID"
    ] = (

        part_sites[
            "Klassifikations_ID"
        ]
    )


    part_sites[
        "Standortverbund_Status"
    ] = (
        "EINZELSTANDORT"
    )


    # --------------------------------------------------------
    # Bestätigte Gruppen bekommen deterministische SV_ID.
    #
    # Die ID basiert ausschließlich auf den enthaltenen
    # Klassifikations_IDs.
    # --------------------------------------------------------

    for (
            group_key,
            group,
    ) in (

            part_sites[

                part_sites[
                    "_Review_Group_Key"
                ].ne("")

            ]

                    .groupby(
                "_Review_Group_Key",
                sort=False,
            )
    ):


        members = sorted(

            group[
                "Klassifikations_ID"
            ]

            .tolist()
        )


        digest = (

            hashlib.sha1(

                "|".join(
                    members
                )
                .encode(
                    "utf-8"
                )
            )

            .hexdigest()[:12]

            .upper()
        )


        sv_id = (
            f"SV_{digest}"
        )


        mask = (

            part_sites[
                "_Review_Group_Key"
            ]
            .eq(
                group_key
            )
        )


        part_sites.loc[

            mask,

            "Standortverbund_ID",

        ] = sv_id


        part_sites.loc[

            mask,

            "Standortverbund_Status",

        ] = (
            "MANUELL_ZUSAMMENGEFASST"
        )


    # ========================================================
    # HAUPTFUNKTIONS-PRÜFUNG EINLESEN
    # ========================================================

    required_main = {

        "Standortverbund_Gruppe",

        "Klassifikations_ID",

        "Hauptfunktion",

        "Hauptfunktion_Begruendung",
    }


    missing = (

            required_main

            - set(
        main_function_review.columns
    )
    )


    if missing:

        raise ValueError(

            "In Standortverbund_Hauptfunktion "
            "fehlen Spalten:\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    main_work = (
        main_function_review
        .copy()
    )


    main_work[
        "Standortverbund_Gruppe"
    ] = (

        main_work[
            "Standortverbund_Gruppe"
        ]

        .map(
            clean_string
        )
    )


    main_work[
        "Hauptfunktion"
    ] = (

        main_work[
            "Hauptfunktion"
        ]

        .map(
            clean_string
        )

        .str.upper()
    )


    main_work[
        "Hauptfunktion_Begruendung"
    ] = (

        main_work[
            "Hauptfunktion_Begruendung"
        ]

        .map(
            clean_string
        )
    )


    main_by_group = {}

    main_reason_by_group = {}


    # --------------------------------------------------------
    # Pro geprüfter Gruppe exakt EINE JA-Zeile.
    # --------------------------------------------------------

    for (
            group_key,
            group,
    ) in (

            main_work.groupby(
                "Standortverbund_Gruppe",
                sort=False,
            )
    ):


        yes_rows = (

            group[
                group[
                    "Hauptfunktion"
                ].eq(
                    "JA"
                )
            ]
        )


        if len(
                yes_rows
        ) != 1:

            raise ValueError(

                f"Standortverbund '{group_key}' besitzt "
                "in der Hauptfunktionsprüfung "
                f"{len(yes_rows)} JA-Zeilen. "

                "Erwartet wird genau 1."
            )


        main_by_group[
            group_key
        ] = clean_string(

            yes_rows.iloc[0][
                "Klassifikations_ID"
            ]
        )


        main_reason_by_group[
            group_key
        ] = clean_string(

            yes_rows.iloc[0][
                "Hauptfunktion_Begruendung"
            ]
        )


    # ========================================================
    # FÜR JEDEN FINALEN STANDORTVERBUND HAUPTFUNKTION BESTIMMEN
    # ========================================================

    profile_main_id = {}

    profile_reason = {}


    for (
            sv_id,
            group,
    ) in (

            part_sites.groupby(
                "Standortverbund_ID",
                sort=False,
            )
    ):


        members = (

            group[
                "Klassifikations_ID"
            ]

            .tolist()
        )


        # ----------------------------------------------------
        # Einzelstandort:
        # automatisch selbst Hauptfunktion.
        # ----------------------------------------------------

        if len(
                group
        ) == 1:

            main_id = (
                members[0]
            )

            reason = ""


        # ----------------------------------------------------
        # Zusammengeführter Standort
        # ----------------------------------------------------

        else:

            review_group_keys = (

                group[
                    "_Review_Group_Key"
                ]

                .drop_duplicates()

                .tolist()
            )


            if len(
                    review_group_keys
            ) != 1:

                raise ValueError(

                    "Interner Fehler: "
                    f"Standortverbund {sv_id} besitzt "
                    "mehrere Review-Gruppen."
                )


            group_key = (
                review_group_keys[0]
            )


            # =================================================
            # FALL 1:
            # Du hast explizit Hauptfunktion ausgewählt.
            # =================================================

            if (
                    group_key
                    in main_by_group
            ):

                main_id = (
                    main_by_group[
                        group_key
                    ]
                )


                reason = (
                    main_reason_by_group.get(
                        group_key,
                        "",
                    )
                )


                if (
                        main_id
                        not in members
                ):

                    raise ValueError(

                        "Gewählte Hauptfunktion "
                        f"{main_id} gehört nicht zum "
                        f"Standortverbund {group_key}."
                    )


            # =================================================
            # FALL 2:
            # Keine Zusatzprüfung notwendig.
            #
            # Das ist nur zulässig, wenn alle Teilstandorte
            # denselben finalen WZ-Code haben.
            # =================================================

            else:

                final_codes = {

                    clean_string(
                        value
                    )

                    for value
                    in group[
                        "WZ_Final_Code"
                    ]

                    if clean_string(
                        value
                    )
                }


                missing_codes = (

                    group[
                        "WZ_Final_Code"
                    ]

                    .map(
                        clean_string
                    )

                    .eq("")

                    .any()
                )


                if (
                        len(
                            final_codes
                        ) > 1
                        or
                        missing_codes
                ):

                    raise ValueError(

                        f"Standortverbund '{group_key}' "
                        "hat unterschiedliche oder fehlende "
                        "finale WZ-Codes, aber keine eindeutige "
                        "Hauptfunktionsentscheidung."
                    )


                # Bei identischer WZ spielt die Wahl für
                # die Branchenzuordnung keine Rolle.
                #
                # Deshalb erster Teilstandort in ursprünglicher
                # Master-Reihenfolge.

                ordered = (

                    group.sort_values(
                        "_Master_Order",
                        kind="stable",
                    )
                )


                main_id = (

                    ordered.iloc[0][
                        "Klassifikations_ID"
                    ]
                )


                reason = (

                    "Automatisch gewählt, da alle "
                    "Teilstandorte denselben finalen "
                    "WZ-Code besitzen."
                )


        # ====================================================
        # SICHERHEITSCHECK HAUPTFUNKTION
        # ====================================================

        main_row = (

            group[

                group[
                    "Klassifikations_ID"
                ]
                .eq(
                    main_id
                )

            ]

                .iloc[0]
        )


        # Wenn andere Teilstandorte WZ haben, darf nicht
        # aus Versehen ein leerer Hauptstandort gewählt sein.

        if (
                len(
                    group
                ) > 1

                and

                not clean_string(
                    main_row[
                        "WZ_Final_Code"
                    ]
                )
        ):

            other_codes = [

                clean_string(
                    value
                )

                for value
                in group[
                    "WZ_Final_Code"
                ]

                if clean_string(
                    value
                )
            ]


            if other_codes:

                raise ValueError(

                    f"Für Standortverbund {sv_id} wurde "
                    "eine Hauptfunktion ohne finalen WZ-Code "
                    "gewählt, obwohl andere Teilstandorte "
                    "einen Code besitzen."
                )


        profile_main_id[
            sv_id
        ] = main_id


        profile_reason[
            sv_id
        ] = reason


    # ========================================================
    # HAUPTFUNKTION AUF TEILSTANDORTE ÜBERTRAGEN
    # ========================================================

    part_sites[
        "Profil_Klassifikations_ID"
    ] = (

        part_sites[
            "Standortverbund_ID"
        ]

        .map(
            profile_main_id
        )
    )


    part_sites[
        "Hauptfunktion_Begruendung"
    ] = (

        part_sites[
            "Standortverbund_ID"
        ]

        .map(
            profile_reason
        )

        .fillna("")
    )


    part_sites[
        "Ist_Hauptfunktion"
    ] = (

            part_sites[
                "Klassifikations_ID"
            ]

            ==

            part_sites[
                "Profil_Klassifikations_ID"
            ]
    )


    # ========================================================
    # PROFILKONTEXT DER HAUPTFUNKTION AUF ALLE TEILSTANDORTE
    # ========================================================

    profile_source_columns = [

        "Klassifikations_ID",

        "Firmenname",

        "Standortname",

        "Unternehmens_ID",

        "WZ_Final_Code",

        "WZ_Final_Ebene",

        "WZ3_Code",

        "WZ2_Code",

        "WZ3_Bezeichnung",

        "WZ_Status",

        "Standorttaetigkeit_kurz",
    ]


    profile_lookup = (

        part_sites[
            profile_source_columns
        ]

        .copy()
    )


    profile_lookup = (
        profile_lookup.rename(
            columns={

                "Klassifikations_ID":
                    "Profil_Klassifikations_ID",

                "Firmenname":
                    "Profil_Firmenname",

                "Standortname":
                    "Profil_Standortname",

                "Unternehmens_ID":
                    "Profil_Unternehmens_ID",

                "WZ_Final_Code":
                    "Profil_WZ_Final_Code",

                "WZ_Final_Ebene":
                    "Profil_WZ_Final_Ebene",

                "WZ3_Code":
                    "Profil_WZ3_Code",

                "WZ2_Code":
                    "Profil_WZ2_Code",

                "WZ3_Bezeichnung":
                    "Profil_WZ3_Bezeichnung",

                "WZ_Status":
                    "Profil_WZ_Status",

                "Standorttaetigkeit_kurz":
                    "Profil_Standorttaetigkeit_kurz",
            }
        )
    )


    part_sites = part_sites.merge(

        profile_lookup,

        on=
        "Profil_Klassifikations_ID",

        how=
        "left",

        validate=
        "m:1",
    )


    # ========================================================
    # KOMPATIBILITÄT ZUR BISHERIGEN PIPELINE
    # ========================================================

    # Lokale WZ-Gruppe
    part_sites[
        "WZ_Gruppe_Code"
    ] = (

        part_sites[
            "WZ3_Code"
        ]
    )


    part_sites[
        "WZ_Gruppe_Bezeichnung"
    ] = (

        part_sites[
            "WZ3_Bezeichnung"
        ]
    )


    # Profil-WZ-Gruppe
    part_sites[
        "Profil_WZ_Gruppe_Code"
    ] = (

        part_sites[
            "Profil_WZ3_Code"
        ]
    )


    part_sites[
        "Profil_WZ_Gruppe_Bezeichnung"
    ] = (

        part_sites[
            "Profil_WZ3_Bezeichnung"
        ]
    )


    # ========================================================
    # EINE ZEILE PRO FINALEM STANDORTVERBUND
    # ========================================================

    union_rows = []


    for (
            sv_id,
            group,
    ) in (

            part_sites.groupby(
                "Standortverbund_ID",
                sort=False,
            )
    ):


        main_id = (

            group.iloc[0][
                "Profil_Klassifikations_ID"
            ]
        )


        main_row = (

            group[

                group[
                    "Klassifikations_ID"
                ]
                .eq(
                    main_id
                )

            ]

                .iloc[0]
        )


        union_rows.append(
            {

                "Standortverbund_ID":
                    sv_id,

                "Standortverbund_Status":
                    (
                        "MANUELL_ZUSAMMENGEFASST"
                        if len(group) > 1
                        else
                        "EINZELSTANDORT"
                    ),

                "Anzahl_Teilstandorte":
                    len(
                        group
                    ),

                "Profil_Klassifikations_ID":
                    main_id,

                "Profil_Unternehmens_ID":
                    clean_string(
                        main_row.get(
                            "Unternehmens_ID",
                            "",
                        )
                    ),

                "Profil_Firmenname":
                    clean_string(
                        main_row.get(
                            "Firmenname",
                            "",
                        )
                    ),

                "Profil_Standortname":
                    clean_string(
                        main_row.get(
                            "Standortname",
                            "",
                        )
                    ),

                "Profil_Strasse_Hausnummer":
                    clean_string(
                        main_row.get(
                            "Strasse_Hausnummer",
                            "",
                        )
                    ),

                "Profil_PLZ":
                    clean_string(
                        main_row.get(
                            "PLZ",
                            "",
                        )
                    ),

                "Profil_Ort":
                    clean_string(
                        main_row.get(
                            "Ort",
                            "",
                        )
                    ),

                "Profil_WZ_Final_Code":
                    clean_string(
                        main_row.get(
                            "WZ_Final_Code",
                            "",
                        )
                    ),

                "Profil_WZ_Final_Ebene":
                    clean_string(
                        main_row.get(
                            "WZ_Final_Ebene",
                            "",
                        )
                    ),

                "Profil_WZ3_Code":
                    clean_string(
                        main_row.get(
                            "WZ3_Code",
                            "",
                        )
                    ),

                "Profil_WZ2_Code":
                    clean_string(
                        main_row.get(
                            "WZ2_Code",
                            "",
                        )
                    ),

                "Profil_WZ3_Bezeichnung":
                    clean_string(
                        main_row.get(
                            "WZ3_Bezeichnung",
                            "",
                        )
                    ),

                "Profil_WZ_Status":
                    clean_string(
                        main_row.get(
                            "WZ_Status",
                            "",
                        )
                    ),

                "Profil_Standorttaetigkeit_kurz":
                    clean_string(
                        main_row.get(
                            "Standorttaetigkeit_kurz",
                            "",
                        )
                    ),

                "Hauptfunktion_Begruendung":
                    clean_string(
                        group.iloc[0].get(
                            "Hauptfunktion_Begruendung",
                            "",
                        )
                    ),

                "Teil_Klassifikations_IDs":
                    unique_join(
                        group[
                            "Klassifikations_ID"
                        ]
                    ),

                "Unternehmens_IDs":
                    unique_join(
                        group[
                            "Unternehmens_ID"
                        ]
                    ),

                "Firmennamen":
                    unique_join(
                        group[
                            "Firmenname"
                        ]
                    ),

                "Standortnamen":
                    unique_join(
                        group[
                            "Standortname"
                        ]
                    ),
            }
        )


    unions = pd.DataFrame(
        union_rows
    )


    # --------------------------------------------------------
    # Nur interne Hilfsspalten entfernen.
    # --------------------------------------------------------

    part_sites = part_sites.drop(
        columns=[

            "_Master_Order",

            "_Review_Group_Key",

        ],
        errors="ignore",
    )


    return (
        part_sites,
        unions,
    )


# ============================================================
# 15. FINALE STANDORT-/WZ-STRUKTUR AUF ORIGINALQUELLEN MAPPEN
# ============================================================

def build_enriched_source_table(
        original,
        mapping,
        part_sites,
):
    """
    Eine Zeile bleibt weiterhin exakt eine ursprüngliche
    Abwärmequelle.

    Neu kommen hinzu:

    - Klassifikations_ID
    - Standortverbund_ID
    - lokale finale WZ
    - Profil-WZ des Standortverbunds
    - Hauptfunktionsinformationen

    Keine Quelle wird dedupliziert.
    """

    # ========================================================
    # ORIGINALDATENSATZ -> KLASSIFIKATIONS_ID
    # ========================================================

    enriched = original.merge(

        mapping,

        on=
        "Originaldatensatz_ID",

        how=
        "left",

        validate=
        "1:1",
    )


    missing_id = (

        enriched[
            "Klassifikations_ID"
        ]

        .fillna("")

        .astype(str)

        .str.strip()

        .eq("")
    )


    if missing_id.any():

        raise ValueError(

            f"{missing_id.sum()} Originalzeilen "
            "besitzen keine Klassifikations_ID."
        )


    # ========================================================
    # FINALE STANDORT-/WZ-INFORMATIONEN
    # ========================================================

    context_columns = [

        "Klassifikations_ID",

        "Standortverbund_ID",

        "Standortverbund_Status",

        "Profil_Klassifikations_ID",

        "Ist_Hauptfunktion",

        "Standortverbund_Entscheidung",

        "Standortverbund_Begruendung",

        "Hauptfunktion_Begruendung",


        # ----------------------------------------------------
        # LOKALER TEILSTANDORT-WZ
        # ----------------------------------------------------

        "WZ_Status",

        "WZ_Final_Code",

        "WZ_Final_Ebene",

        "WZ3_Code",

        "WZ2_Code",

        "WZ_Gruppe_Code",

        "WZ_Gruppe_Bezeichnung",

        "WZ_Final_Herkunft",

        "WZ_Manuell_Begruendung",

        "WZ_AI_Gruppe_Code",

        "WZ_AI_Gruppe_Bezeichnung",

        "Standorttaetigkeit_kurz",

        "WZ_AI_Konfidenz",

        "WZ_Qualitaetsflag",

        "Standortfunktion",

        "Referenz_Mehrfach_Match",


        # ----------------------------------------------------
        # PROFIL-/STANDORTVERBUND-KONTEXT
        # ----------------------------------------------------

        "Profil_Firmenname",

        "Profil_Standortname",

        "Profil_Unternehmens_ID",

        "Profil_WZ_Status",

        "Profil_WZ_Final_Code",

        "Profil_WZ_Final_Ebene",

        "Profil_WZ3_Code",

        "Profil_WZ2_Code",

        "Profil_WZ_Gruppe_Code",

        "Profil_WZ_Gruppe_Bezeichnung",

        "Profil_Standorttaetigkeit_kurz",
    ]


    context_columns = [

        column

        for column
        in context_columns

        if column
           in part_sites.columns
    ]


    enriched = enriched.merge(

        part_sites[
            context_columns
        ],

        on=
        "Klassifikations_ID",

        how=
        "left",

        validate=
        "m:1",
    )


    # ========================================================
    # LEERE ERGEBNISFELDER FÜR QUELLKLASSIFIKATION
    # ========================================================

    enriched[
        "Quellklasse_Code"
    ] = ""


    enriched[
        "Quellklasse"
    ] = ""


    enriched[
        "Quellklasse_Begruendung"
    ] = ""


    enriched[
        "Quellklasse_Konfidenz"
    ] = ""


    # ========================================================
    # SPALTENREIHENFOLGE
    # ========================================================

    front_columns = [

        "Originaldatensatz_ID",

        "Original_Excel_Zeile",

        "Klassifikations_ID",

        "Standortverbund_ID",

        "Profil_Klassifikations_ID",

        "Ist_Hauptfunktion",

        "Unternehmens_ID",

        "Melde_ID",

        "Firmenname",

        "Standortname",

        "Straße und Hausnummer",

        "PLZ",

        "Ort",


        # ----------------------------------------------------
        # LOKALER WZ-KONTEXT
        # ----------------------------------------------------

        "WZ_Status",

        "WZ_Final_Code",

        "WZ_Final_Ebene",

        "WZ3_Code",

        "WZ2_Code",

        "WZ_Gruppe_Code",

        "WZ_Gruppe_Bezeichnung",

        "Standorttaetigkeit_kurz",

        "WZ_Final_Herkunft",

        "WZ_AI_Konfidenz",

        "WZ_Qualitaetsflag",

        "Standortfunktion",


        # ----------------------------------------------------
        # PROFILKONTEXT
        # ----------------------------------------------------

        "Profil_Firmenname",

        "Profil_Standortname",

        "Profil_WZ_Status",

        "Profil_WZ_Final_Code",

        "Profil_WZ_Final_Ebene",

        "Profil_WZ3_Code",

        "Profil_WZ2_Code",

        "Profil_WZ_Gruppe_Bezeichnung",

        "Profil_Standorttaetigkeit_kurz",
    ]


    result_columns = [

        "Quellklasse_Code",

        "Quellklasse",

        "Quellklasse_Begruendung",

        "Quellklasse_Konfidenz",
    ]


    front_columns = [

        column

        for column
        in front_columns

        if column
           in enriched.columns
    ]


    middle_columns = [

        column

        for column
        in enriched.columns

        if (
                column not in front_columns
                and
                column not in result_columns
        )
    ]


    enriched = enriched[

        front_columns

        + middle_columns

        + result_columns
        ]


    return enriched


# ============================================================
# 16. SPALTEN FÜR DIE QUELLKLASSIFIKATIONS-BATCHES
# ============================================================

def get_ai_batch_columns(
        enriched,
):
    """
    Für die Quellklassifikation werden jetzt zwei
    WZ-Kontexte mitgegeben:

    1. konkrete Tätigkeit des ursprünglichen Teilstandorts
    2. finale Profilbranche des gesamten Standortverbunds

    Beispiel:

        BHKW:
            lokaler WZ = 35.3

        Klinikverbund:
            Profil-WZ = 86.1

    Damit verliert die Quell-KI keinen technischen Kontext.
    """

    desired = [

        # ----------------------------------------------------
        # TECHNISCHE IDS
        # ----------------------------------------------------

        "Originaldatensatz_ID",

        "Klassifikations_ID",

        "Standortverbund_ID",

        "Profil_Klassifikations_ID",

        "Unternehmens_ID",

        "Melde_ID",


        # ----------------------------------------------------
        # KONKRETER TEILSTANDORT
        # ----------------------------------------------------

        "Firmenname",

        "Standortname",


        # ----------------------------------------------------
        # LOKALER WZ-KONTEXT
        # ----------------------------------------------------

        "WZ_Final_Code",

        "WZ3_Code",

        "WZ_Gruppe_Bezeichnung",

        "Standorttaetigkeit_kurz",

        "WZ_Final_Herkunft",

        "WZ_AI_Konfidenz",

        "WZ_Qualitaetsflag",

        "Standortfunktion",


        # ----------------------------------------------------
        # PROFIL-/STANDORTVERBUND-KONTEXT
        # ----------------------------------------------------

        "Profil_Firmenname",

        "Profil_Standortname",

        "Profil_WZ_Final_Code",

        "Profil_WZ3_Code",

        "Profil_WZ_Gruppe_Bezeichnung",

        "Profil_Standorttaetigkeit_kurz",


        # ----------------------------------------------------
        # KONKRETE ABWÄRMEQUELLE
        # ----------------------------------------------------

        "Name des Abwärmepotentials",

        "Wärmemenge pro Jahr (in kWh/a)",

        "Maximale thermische Leistung (in kW)",

        "Durchschnittliches Temperaturniveau (in °C)",

        "Temperaturbereich",

        "Ergänzende Informationen zum Abwärmepotential",

        "Weitere Hinweise",


        # ----------------------------------------------------
        # VON DER QUELL-KI AUSZUFÜLLEN
        # ----------------------------------------------------

        "Quellklasse_Code",

        "Quellklasse",

        "Quellklasse_Begruendung",

        "Quellklasse_Konfidenz",
    ]


    return [

        column

        for column
        in desired

        if column
           in enriched.columns
    ]


# ============================================================
# 17. UNION-FIND FÜR BATCH-EINHEITEN
# ============================================================

class UnionFind:
    """
    Kleine technische Hilfsklasse.

    Sie wird ausschließlich für die Batchbildung verwendet.

    Ziel:
    Ein Unternehmen UND ein finaler Standortverbund dürfen
    jeweils niemals auf mehrere Quellen-Batches verteilt werden.
    """

    def __init__(
            self,
    ):

        self.parent = {}


    def add(
            self,
            item,
    ):

        if (
                item
                not in self.parent
        ):

            self.parent[
                item
            ] = item


    def find(
            self,
            item,
    ):

        self.add(
            item
        )


        if (
                self.parent[
                    item
                ]
                != item
        ):

            self.parent[
                item
            ] = self.find(

                self.parent[
                    item
                ]
            )


        return (
            self.parent[
                item
            ]
        )


    def union(
            self,
            a,
            b,
    ):

        root_a = self.find(
            a
        )

        root_b = self.find(
            b
        )


        if (
                root_a
                != root_b
        ):

            self.parent[
                root_b
            ] = root_a


# ============================================================
# 18. TECHNISCHER UNTERNEHMENSSCHLÜSSEL
# ============================================================

def build_company_batch_key(
        row,
) -> str:
    """
    Gleiche Logik wie bisher:

    Normalfall:
        Unternehmens_ID

    Falls diese fehlt:
        Klassifikations_ID
    """

    company_id = clean_string(

        row.get(
            "Unternehmens_ID",
            "",
        )
    )


    if company_id:

        return (

            f"COMPANY::"
            f"{company_id}"
        )


    classification_id = clean_string(

        row.get(
            "Klassifikations_ID",
            "",
        )
    )


    if classification_id:

        return (

            f"NO_COMPANY::"
            f"{classification_id}"
        )


    return (

        f"ROW::"
        f"{row['Originaldatensatz_ID']}"
    )


# ============================================================
# 19. QUELLEN-BATCHES ERZEUGEN
# ============================================================

def create_source_batches(
        enriched,
):
    """
    Batchlogik:

    - maximal 500 Quellen
    - Unternehmen niemals teilen
    - finalen Standortverbund niemals teilen
    - ursprüngliche Reihenfolge als Grundlage

    NEU:

    Falls ein bestätigter Standortverbund mehrere
    Unternehmens_IDs verbindet, werden diese Unternehmen
    für die Batchbildung als gemeinsame Einheit behandelt.

    Dadurch bleibt der gesamte physische Profilstandort
    sicher in einem Batch.
    """

    data = (

        enriched

        .sort_values(
            "Originaldatensatz_ID",
            kind="stable",
        )

        .reset_index(
            drop=True
        )

        .copy()
    )


    # ========================================================
    # UNTERNEHMENSSCHLÜSSEL
    # ========================================================

    data[
        "_Batch_Company_Key"
    ] = data.apply(

        build_company_batch_key,

        axis=1,
    )


    # ========================================================
    # GRAPH:
    #
    # Unternehmen <-> Standortverbund
    #
    # Dadurch wird beides zusammengehalten.
    # ========================================================

    uf = UnionFind()


    for _, row in (
            data.iterrows()
    ):


        company_node = (

                "C::"

                + row[
                    "_Batch_Company_Key"
                ]
        )


        site_node = (

                "S::"

                + clean_string(

            row[
                "Standortverbund_ID"
            ]
        )
        )


        uf.union(

            company_node,

            site_node,
        )


    # ========================================================
    # TECHNISCHE BATCH-GRUPPE
    # ========================================================

    data[
        "_Batch_Group_Key"
    ] = data.apply(

        lambda row:

        uf.find(

            "C::"

            + row[
                "_Batch_Company_Key"
            ]
        ),

        axis=1,
    )


    # ========================================================
    # BATCH-EINHEITEN
    # ========================================================

    groups = []


    for (
            key,
            group,
    ) in (

            data.groupby(
                "_Batch_Group_Key",
                sort=False,
            )
    ):


        group = (

            group.sort_values(
                "Originaldatensatz_ID",
                kind="stable",
            )
        )


        if (
                len(
                    group
                )
                > SOURCE_BATCH_SIZE
        ):

            companies = (

                group[
                    "_Batch_Company_Key"
                ]

                .nunique()
            )


            sites = (

                group[
                    "Standortverbund_ID"
                ]

                .nunique()
            )


            raise ValueError(

                f"Batch-Einheit '{key}' besitzt "
                f"{len(group)} Quellen und überschreitet "
                f"die Grenze {SOURCE_BATCH_SIZE}.\n"

                f"Unternehmen: {companies}\n"
                f"Standortverbünde: {sites}"
            )


        groups.append(
            group
        )


    # ========================================================
    # GRUPPEN IN MAXIMAL 500ER-BATCHES PACKEN
    # ========================================================

    batches = []

    current_parts = []

    current_size = 0


    for group in groups:


        group_size = len(
            group
        )


        if (
                current_size > 0

                and

                current_size
                + group_size
                > SOURCE_BATCH_SIZE
        ):

            batches.append(

                pd.concat(
                    current_parts,
                    ignore_index=True,
                )
            )


            current_parts = []

            current_size = 0


        current_parts.append(
            group
        )


        current_size += (
            group_size
        )


    if current_parts:

        batches.append(

            pd.concat(
                current_parts,
                ignore_index=True,
            )
        )


    return batches


# ============================================================
# 20. QUELLEN-BATCHES VALIDIEREN
# ============================================================

def validate_source_batches(
        batches,
        enriched,
):
    """
    Kontrolliert:

    - keine Quelle verloren
    - keine Quelle doppelt
    - maximal 500 Quellen
    - Unternehmen nicht geteilt
    - Standortverbund nicht geteilt
    """

    if not batches:

        raise ValueError(

            "Es wurden keine Quellen-Batches erzeugt."
        )


    all_rows = pd.concat(

        batches,

        ignore_index=True,
    )


    # ========================================================
    # ZEILENZAHL
    # ========================================================

    if (
            len(
                all_rows
            )
            !=
            len(
                enriched
            )
    ):

        raise ValueError(

            "Bei der Batchbildung gingen Quellen "
            "verloren oder kamen hinzu."
        )


    # ========================================================
    # ORIGINALDATENSATZ_ID EINDEUTIG
    # ========================================================

    if not all_rows[
        "Originaldatensatz_ID"
    ].is_unique:

        raise ValueError(

            "Originaldatensatz_ID kommt in den "
            "Quellen-Batches mehrfach vor."
        )


    # ========================================================
    # IDENTISCHE ID-MENGE
    # ========================================================

    if (

            set(
                all_rows[
                    "Originaldatensatz_ID"
                ]
            )

            !=

            set(
                enriched[
                    "Originaldatensatz_ID"
                ]
            )
    ):

        raise ValueError(

            "Die Quellen-Batches enthalten nicht "
            "exakt dieselben Originaldatensatz_IDs."
        )


    company_to_batch = {}

    site_to_batch = {}


    # ========================================================
    # JEDEN BATCH PRÜFEN
    # ========================================================

    for (
            batch_number,
            batch,
    ) in enumerate(
        batches,
        start=1,
    ):


        if (
                len(
                    batch
                )
                > SOURCE_BATCH_SIZE
        ):

            raise ValueError(

                f"Batch {batch_number} hat "
                f"{len(batch)} Zeilen und ist damit zu groß."
            )


        # ----------------------------------------------------
        # Unternehmen darf nur in einem Batch liegen
        # ----------------------------------------------------

        for company in (

                batch[
                    "_Batch_Company_Key"
                ]

                        .drop_duplicates()
        ):


            if (
                    company
                    in company_to_batch
            ):

                raise ValueError(

                    f"Unternehmen '{company}' wurde auf "
                    "mehrere Batches verteilt."
                )


            company_to_batch[
                company
            ] = batch_number


        # ----------------------------------------------------
        # Finaler Standortverbund darf ebenfalls nur
        # in einem Batch liegen.
        # ----------------------------------------------------

        for site in (

                batch[
                    "Standortverbund_ID"
                ]

                        .drop_duplicates()
        ):


            if (
                    site
                    in site_to_batch
            ):

                raise ValueError(

                    f"Standortverbund '{site}' wurde "
                    "auf mehrere Batches verteilt."
                )


            site_to_batch[
                site
            ] = batch_number


# ============================================================
# 21. AUSGABEORDNER VORBEREITEN
# ============================================================

def prepare_output_directories():

    SOURCE_OUTPUT_DIR.mkdir(

        parents=True,

        exist_ok=True,
    )


    SOURCE_BATCH_DIR.mkdir(

        parents=True,

        exist_ok=True,
    )


    if CLEAR_OLD_SOURCE_BATCHES:

        for file in (

                SOURCE_BATCH_DIR.glob(
                    "Quellen_Batch_*.xlsx"
                )
        ):

            file.unlink()


# ============================================================
# 22. FINALE STANDORTKLASSIFIKATION SPEICHERN
# ============================================================

def save_site_classification(
        part_sites,
        unions,
):
    """
    Die Datei enthält:

    Standortklassifikation
        -> eine Zeile je finalem Profilstandort

    Teilstandorte
        -> alle ursprünglichen Klassifikations_IDs

    Zusammenfassung
        -> Kontrollkennzahlen
    """

    summary = pd.DataFrame(
        [

            {
                "Kennzahl":
                    "Ursprüngliche Klassifikations_IDs / Teilstandorte",

                "Wert":
                    len(
                        part_sites
                    ),
            },

            {
                "Kennzahl":
                    "Finale Standortverbünde / Profilstandorte",

                "Wert":
                    unions[
                        "Standortverbund_ID"
                    ].nunique(),
            },

            {
                "Kennzahl":
                    "Manuell zusammengeführte Profilstandorte",

                "Wert":
                    int(
                        (
                                unions[
                                    "Anzahl_Teilstandorte"
                                ]
                                > 1
                        ).sum()
                    ),
            },

            {
                "Kennzahl":
                    "Teilstandorte in zusammengeführten Verbünden",

                "Wert":
                    int(
                        part_sites[
                            "Standortverbund_Status"
                        ]
                        .eq(
                            "MANUELL_ZUSAMMENGEFASST"
                        )
                        .sum()
                    ),
            },

            {
                "Kennzahl":
                    "Teilstandorte mit WZ3",

                "Wert":
                    int(
                        part_sites[
                            "WZ3_Code"
                        ]
                        .map(
                            clean_string
                        )
                        .ne("")
                        .sum()
                    ),
            },

            {
                "Kennzahl":
                    "Teilstandorte nur mit WZ2",

                "Wert":
                    int(
                        part_sites[
                            "WZ_Status"
                        ]
                        .eq(
                            "klassifiziert_nur_WZ2"
                        )
                        .sum()
                    ),
            },

            {
                "Kennzahl":
                    "Teilstandorte ohne sichere numerische WZ-Zuordnung",

                "Wert":
                    int(
                        part_sites[
                            "WZ_Status"
                        ]
                        .eq(
                            "nicht_sicher_klassifizierbar"
                        )
                        .sum()
                    ),
            },

            {
                "Kennzahl":
                    "Teilstandorte mit exaktem finalen Code 38.21",

                "Wert":
                    int(
                        part_sites[
                            "WZ_Final_Code"
                        ]
                        .eq(
                            "38.21"
                        )
                        .sum()
                    ),
            },
        ]
    )


    # ========================================================
    # LESBARE SPALTENREIHENFOLGE
    # ========================================================

    preferred_part_columns = [

        "Klassifikations_ID",

        "Standortverbund_ID",

        "Standortverbund_Status",

        "Profil_Klassifikations_ID",

        "Ist_Hauptfunktion",

        "Unternehmens_ID",

        "Firmenname",

        "Standortname",

        "Strasse_Hausnummer",

        "PLZ",

        "Ort",

        "WZ_Status",

        "WZ_Final_Code",

        "WZ_Final_Ebene",

        "WZ3_Code",

        "WZ2_Code",

        "WZ3_Bezeichnung",

        "WZ_Final_Herkunft",

        "WZ_Manuell_Begruendung",

        "WZ_AI_Gruppe_Code",

        "WZ_AI_Gruppe_Bezeichnung",

        "Standorttaetigkeit_kurz",

        "WZ_AI_Konfidenz",

        "WZ_Qualitaetsflag",

        "Standortfunktion",

        "Standortverbund_Begruendung",

        "Hauptfunktion_Begruendung",

        "Profil_WZ_Final_Code",

        "Profil_WZ_Final_Ebene",

        "Profil_WZ3_Code",

        "Profil_WZ2_Code",

        "Profil_WZ3_Bezeichnung",

        "Profil_Standorttaetigkeit_kurz",
    ]


    preferred_part_columns = [

        column

        for column
        in preferred_part_columns

        if column
           in part_sites.columns
    ]


    remaining = [

        column

        for column
        in part_sites.columns

        if column
           not in preferred_part_columns
    ]


    with pd.ExcelWriter(

            SITE_CLASSIFICATION_FILE,

            engine="openpyxl",

    ) as writer:


        # ----------------------------------------------------
        # Eine Zeile je FINALER Profilstandort
        # ----------------------------------------------------

        unions.to_excel(

            writer,

            sheet_name=
            "Standortklassifikation",

            index=False,
        )


        # ----------------------------------------------------
        # Alle ursprünglichen Klassifikations_IDs
        # ----------------------------------------------------

        part_sites[
            preferred_part_columns
            + remaining
            ].to_excel(

            writer,

            sheet_name=
            "Teilstandorte",

            index=False,
        )


        summary.to_excel(

            writer,

            sheet_name=
            "Zusammenfassung",

            index=False,
        )


# ============================================================
# 23. VOLLSTÄNDIGE ANGEREICHERTE QUELLENTABELLE SPEICHERN
# ============================================================

def save_enriched_data(
        enriched,
):

    summary = pd.DataFrame(
        [

            {
                "Kennzahl":
                    "Originale Abwärmepotentiale",

                "Wert":
                    len(
                        enriched
                    ),
            },

            {
                "Kennzahl":
                    "Quellen mit lokalem WZ3",

                "Wert":
                    int(
                        enriched[
                            "WZ3_Code"
                        ]
                        .map(
                            clean_string
                        )
                        .ne("")
                        .sum()
                    ),
            },

            {
                "Kennzahl":
                    "Quellen mit Profil-WZ3",

                "Wert":
                    int(
                        enriched[
                            "Profil_WZ3_Code"
                        ]
                        .map(
                            clean_string
                        )
                        .ne("")
                        .sum()
                    ),
            },

            {
                "Kennzahl":
                    "Quellen in zusammengeführten Standortverbünden",

                "Wert":
                    int(
                        enriched[
                            "Standortverbund_Status"
                        ]
                        .eq(
                            "MANUELL_ZUSAMMENGEFASST"
                        )
                        .sum()
                    ),
            },

            {
                "Kennzahl":
                    "Quellen mit Profilcode 38.21",

                "Wert":
                    int(
                        enriched[
                            "Profil_WZ_Final_Code"
                        ]
                        .eq(
                            "38.21"
                        )
                        .sum()
                    ),
            },
        ]
    )


    with pd.ExcelWriter(

            ENRICHED_FILE,

            engine="openpyxl",

    ) as writer:


        enriched.to_excel(

            writer,

            sheet_name=
            "Abwaermepotentiale",

            index=False,
        )


        summary.to_excel(

            writer,

            sheet_name=
            "Zusammenfassung",

            index=False,
        )


# ============================================================
# 24. QUELLEN-BATCHES SPEICHERN
# ============================================================

def save_source_batches(
        batches,
        batch_columns,
):

    overview_rows = []


    for (
            batch_number,
            batch,
    ) in enumerate(
        batches,
        start=1,
    ):


        batch_id = (

            f"QUELLEN_BATCH_"
            f"{batch_number:03d}"
        )


        output_batch = (

            batch[
                batch_columns
            ]

            .copy()
        )


        output_batch.insert(

            0,

            "Batch_ID",

            batch_id,
        )


        batch_file = (

                SOURCE_BATCH_DIR

                / (
                    f"Quellen_Batch_"
                    f"{batch_number:03d}.xlsx"
                )
        )


        output_batch.to_excel(

            batch_file,

            sheet_name=
            "Abwaermequellen",

            index=False,

            engine="openpyxl",
        )


        overview_rows.append(
            {

                "Batch_ID":
                    batch_id,

                "Dateiname":
                    batch_file.name,

                "Anzahl_Quellen":
                    len(
                        batch
                    ),

                "Anzahl_Unternehmen":
                    batch[
                        "_Batch_Company_Key"
                    ]
                    .nunique(),

                "Anzahl_Teilstandorte":
                    batch[
                        "Klassifikations_ID"
                    ]
                    .nunique(),

                "Anzahl_Profilstandorte":
                    batch[
                        "Standortverbund_ID"
                    ]
                    .nunique(),

                "Quellen_mit_lokalem_WZ3":
                    int(
                        batch[
                            "WZ3_Code"
                        ]
                        .map(
                            clean_string
                        )
                        .ne("")
                        .sum()
                    ),

                "Quellen_mit_Profil_WZ3":
                    int(
                        batch[
                            "Profil_WZ3_Code"
                        ]
                        .map(
                            clean_string
                        )
                        .ne("")
                        .sum()
                    ),

                "Originaldatensatz_ID_min":
                    int(
                        batch[
                            "Originaldatensatz_ID"
                        ]
                        .min()
                    ),

                "Originaldatensatz_ID_max":
                    int(
                        batch[
                            "Originaldatensatz_ID"
                        ]
                        .max()
                    ),
            }
        )


    overview = pd.DataFrame(
        overview_rows
    )


    overview.to_excel(

        BATCH_OVERVIEW_FILE,

        sheet_name=
        "Batch_Uebersicht",

        index=False,

        engine="openpyxl",
    )


    return overview


# ============================================================
# 25. HAUPTPROGRAMM
# ============================================================

def main():

    print()

    print(
        "=" * 78
    )

    print(
        "FINALE VORBEREITUNG DER "
        "ABWÄRMEQUELLEN-KLASSIFIKATION"
    )

    print(
        "=" * 78
    )

    print()


    # ========================================================
    # AUSGABEORDNER
    # ========================================================

    prepare_output_directories()


    # ========================================================
    # 1. ORIGINALDATEN
    # ========================================================

    print(
        "1. Ursprüngliche PFA-Daten werden eingelesen ..."
    )


    original = (
        load_original_data()
    )


    print(
        f"   -> {len(original):,} Abwärmepotentiale"
    )


    # ========================================================
    # 2. MAPPING
    # ========================================================

    print(
        "2. Originaldaten-Mapping wird eingelesen ..."
    )


    mapping = (
        load_mapping()
    )


    print(
        f"   -> {len(mapping):,} Mapping-Zeilen"
    )


    # ========================================================
    # 3. STANDORT-MASTER
    # ========================================================

    print(
        "3. Standort-Master wird eingelesen ..."
    )


    master_sites = (
        load_master_sites()
    )


    print(
        f"   -> {len(master_sites):,} "
        "ursprüngliche Klassifikations_IDs"
    )


    validate_original_mapping(
        original,
        mapping,
    )


    print(
        "   -> Originaldatei und Mapping sind konsistent"
    )


    # ========================================================
    # 4. BEIDE MANUELL BEARBEITETEN PRÜFDATEIEN
    # ========================================================

    print(

        "4. Bearbeitete Validierungs- und "
        "Zusatzprüfdateien werden eingelesen ..."
    )


    (
        all_results,

        wz_review,

        site_review,

        main_function_review,

        new_wz_review,

    ) = (
        load_manual_validation_files()
    )


    validate_manual_reviews(

        wz_review,

        site_review,

        main_function_review,

        new_wz_review,
    )


    print(
        f"   -> {len(wz_review):,} "
        "Fälle aus WZ_Pruefung"
    )


    print(
        f"   -> {len(site_review):,} "
        "Zeilen aus Standortverbund_Pruefung"
    )


    print(
        f"   -> {len(main_function_review):,} "
        "Zeilen aus Standortverbund_Hauptfunktion"
    )


    print(
        f"   -> {len(new_wz_review):,} "
        "Fälle aus Neue_ohne_WZ3"
    )


    # ========================================================
    # 5. FINALE WZ-KORREKTUREN
    # ========================================================

    print(
        "5. Manuelle WZ-Korrekturen werden angewendet ..."
    )


    effective_wz = (
        apply_manual_wz_corrections(

            all_results,

            wz_review,

            new_wz_review,
        )
    )


    print(

        "   -> Standorte mit WZ3: "

        f"{effective_wz['WZ3_Code'].map(clean_string).ne('').sum():,}"
    )


    print(

        "   -> nur WZ2: "

        f"{effective_wz['WZ_Status'].eq('klassifiziert_nur_WZ2').sum():,}"
    )


    print(

        "   -> ohne sichere numerische WZ-Zuordnung: "

        f"{effective_wz['WZ_Status'].eq('nicht_sicher_klassifizierbar').sum():,}"
    )


    print(

        "   -> exakter finaler Code 38.21: "

        f"{effective_wz['WZ_Final_Code'].eq('38.21').sum():,}"
    )


    # ========================================================
    # 6. FINALE STANDORTVERBÜNDE
    # ========================================================

    print(

        "6. Finale Standortverbünde und "
        "Hauptfunktionen werden aufgebaut ..."
    )


    (
        part_sites,
        site_unions,

    ) = (
        build_final_site_structure(

            master_sites,

            effective_wz,

            site_review,

            main_function_review,
        )
    )


    print(
        f"   -> {len(part_sites):,} "
        "ursprüngliche Teilstandorte"
    )


    print(
        f"   -> {len(site_unions):,} "
        "finale Profilstandorte"
    )


    print(

        "   -> davon zusammengeführt: "

        f"{(site_unions['Anzahl_Teilstandorte'] > 1).sum():,}"
    )


    save_site_classification(
        part_sites,
        site_unions,
    )


    # ========================================================
    # 7. AUF ALLE ORIGINALQUELLEN ZURÜCKMAPPEN
    # ========================================================

    print(

        "7. Finale Standort-/WZ-Struktur wird "
        "auf alle Abwärmequellen zurückgemappt ..."
    )


    enriched = (
        build_enriched_source_table(

            original,

            mapping,

            part_sites,
        )
    )


    # --------------------------------------------------------
    # Keine Originalquelle darf verloren gehen.
    # --------------------------------------------------------

    if (
            len(
                enriched
            )
            !=
            len(
                original
            )
    ):

        raise ValueError(

            "Zeilenzahl der angereicherten "
            "Gesamttabelle stimmt nicht."
        )


    print(
        f"   -> {len(enriched):,} Quellen vorbereitet"
    )


    save_enriched_data(
        enriched
    )


    # ========================================================
    # 8. QUELLEN-BATCHES
    # ========================================================

    print(
        "8. Quellen-Batches werden gebildet ..."
    )


    batches = (
        create_source_batches(
            enriched
        )
    )


    print(
        f"   -> {len(batches):,} Batches"
    )


    print(
        f"   -> maximale Batchgröße: "
        f"{SOURCE_BATCH_SIZE}"
    )


    # ========================================================
    # 9. INTEGRITÄT
    # ========================================================

    print(
        "9. Batch-Integrität wird geprüft ..."
    )


    validate_source_batches(
        batches,
        enriched,
    )


    print(
        "   -> keine Quelle verloren oder doppelt"
    )


    print(
        "   -> kein Unternehmen geteilt"
    )


    print(
        "   -> kein finaler Standortverbund geteilt"
    )


    print(
        "   -> kein Batch größer als 500"
    )


    # ========================================================
    # 10. BATCHES SPEICHERN
    # ========================================================

    print(
        "10. Quellen-Batches werden gespeichert ..."
    )


    batch_columns = (
        get_ai_batch_columns(
            enriched
        )
    )


    overview = (
        save_source_batches(

            batches,

            batch_columns,
        )
    )


    # ========================================================
    # ABSCHLUSS
    # ========================================================

    print()

    print(
        "=" * 78
    )

    print(
        "FERTIG"
    )

    print(
        "=" * 78
    )

    print()


    print(
        "Standortklassifikation:\n"
        f"  {SITE_CLASSIFICATION_FILE}"
    )


    print()


    print(
        "Vollständige angereicherte Tabelle:\n"
        f"  {ENRICHED_FILE}"
    )


    print()


    print(
        "Quellen-Batches:\n"
        f"  {SOURCE_BATCH_DIR}"
    )


    print()


    print(
        "Batchübersicht:\n"
        f"  {BATCH_OVERVIEW_FILE}"
    )


    print()


    print(
        f"Anzahl Quellen insgesamt: "
        f"{len(enriched):,}"
    )


    print(
        f"Anzahl Quellen-Batches: "
        f"{len(overview):,}"
    )


    print(
        f"Größter Batch: "
        f"{overview['Anzahl_Quellen'].max():,}"
    )


    print(
        f"Kleinster Batch: "
        f"{overview['Anzahl_Quellen'].min():,}"
    )


    print()

    print(
        "Wichtig:"
    )


    print(
        "- Manuelle WZ-Codes wie 38.21 bleiben exakt erhalten."
    )


    print(
        "- WZ3 und WZ2 werden nur zusätzlich abgeleitet."
    )


    print(
        "- Teilstandort-WZ und Profil-WZ werden getrennt gespeichert."
    )


    print(
        "- Zusammengeführte Standorte werden bei "
        "der Batchbildung nicht getrennt."
    )


    print(
        "=" * 78
    )


# ============================================================
# 26. PROGRAMMSTART
# ============================================================

if __name__ == "__main__":

    main()