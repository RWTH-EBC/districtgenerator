from pathlib import Path
import re
import pandas as pd


# ============================================================
# 1. KONFIGURATION
# ============================================================

BASE_DIR = Path("WZ2025_Vorbereitung")

SOURCE_DIR = (
        BASE_DIR
        / "Quellenklassifikation_final"
)


# ------------------------------------------------------------
# Vollständige Tabelle aus dem vorherigen Vorbereitungsschritt.
#
# Diese Datei definiert die Grundgesamtheit und enthält bereits
# u. a.:
#
# - alle ursprünglichen Abwärmepotentiale
# - Originaldatensatz_ID
# - Klassifikations_ID
# - ggf. Standortverbund_ID
# - ggf. Profil_Klassifikations_ID
# - finale WZ-/Profil-WZ-Informationen
# - leere Quellklassenspalten
# ------------------------------------------------------------

MASTER_FILE = (
        SOURCE_DIR
        / "Abwaermepotentiale_mit_WZ.xlsx"
)

MASTER_SHEET = "Abwaermepotentiale"


# ------------------------------------------------------------
# Ordner mit den von der KI fertig klassifizierten
# Quellen-Batches.
# ------------------------------------------------------------

CLASSIFIED_BATCH_DIR = (
        SOURCE_DIR
        / "Batches_klassifiziert"
)

CLASSIFIED_BATCH_PATTERN = (
    "Quellen_Batch_*_klassifiziert*.xlsx"
)

CLASSIFIED_BATCH_SHEET = "Abwaermequellen"


# ------------------------------------------------------------
# Vollständige Ausgabedatei.
#
# Es findet in diesem Schritt KEINE Filterung statt.
#
# QX, geringe Konfidenz und noch nicht klassifizierte Quellen
# bleiben vollständig enthalten.
# ------------------------------------------------------------

OUTPUT_FILE = (
        SOURCE_DIR
        / "Abwaermepotentiale_mit_Quellklassen.xlsx"
)


# ============================================================
# 2. QUELLKLASSEN-TAXONOMIE Q1-Q7 + QX
# ============================================================

VALID_SOURCE_CLASSES = {

    "Q1":
        "Flüssiger Wärmestrom",

    "Q2":
        "Prozessdampf / Brüden / Kondensat",

    "Q3":
        "Abluft / nicht verbrennungsbedingter Prozessgasstrom",

    "Q4":
        "Rauchgas / Verbrennungs- und Oxidationsabgas",

    "Q5":
        "Diffuse / feste Abwärme",

    "Q6":
        "Kälteanlagen- / Verflüssigerwärme",

    "Q7":
        "Druckluft- / Kompressorwärme",

    "QX":
        "Nicht eindeutig bestimmbar",
}


SOURCE_CLASS_ORDER = [

    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "Q5",
    "Q6",
    "Q7",
    "QX",
]


VALID_CONFIDENCE = {

    "hoch",
    "mittel",
    "gering",
    "keine",
}


# ============================================================
# KOMPATIBILITÄT MIT ÄLTEREN BATCHES
# ============================================================

# ------------------------------------------------------------
# Einige ältere, bereits klassifizierte Batches können noch
# die alten Bezeichnungen enthalten:
#
# Q2:
#     Dampf / Kondensat / Brüden
#
# Q3:
#     Abluft / Prozessluft
#
# Q4:
#     Rauchgas / Verbrennungsabgas
#
# Die Codes selbst haben sich NICHT geändert.
#
# Deshalb akzeptiert der Postprocessor diese bekannten alten
# Bezeichnungen und vereinheitlicht sie anschließend auf die
# neue Bezeichnung.
#
# WICHTIG:
#
# Es wird dabei NIEMALS ein Code verändert.
#
# Insbesondere wird:
#
#     QX
#
# NICHT automatisch zu:
#
#     Q6
#     oder
#     Q7
#
# umklassifiziert.
#
# Das wäre eine fachliche Neuklassifikation und darf nur in der
# eigentlichen Quellklassifikation erfolgen.
# ------------------------------------------------------------

SOURCE_CLASS_LABEL_ALIASES = {

    "Q1": {

        "Flüssiger Wärmestrom",
    },


    "Q2": {

        "Prozessdampf / Brüden / Kondensat",

        "Dampf / Kondensat / Brüden",

        "Dampf / Brüden / Kondensat",
    },


    "Q3": {

        "Abluft / nicht verbrennungsbedingter Prozessgasstrom",

        "Abluft / Prozessluft",
    },


    "Q4": {

        "Rauchgas / Verbrennungs- und Oxidationsabgas",

        "Rauchgas / Verbrennungsabgas",
    },


    "Q5": {

        "Diffuse / feste Abwärme",
    },


    "Q6": {

        "Kälteanlagen- / Verflüssigerwärme",

        "Kälteanlagen-/Verflüssigerwärme",

        "Kälteanlagen / Verflüssigerwärme",
    },


    "Q7": {

        "Druckluft- / Kompressorwärme",

        "Druckluft-/Kompressorwärme",

        "Druckluft / Kompressorwärme",
    },


    "QX": {

        "Nicht eindeutig bestimmbar",
    },
}


# ============================================================
# 3. HILFSFUNKTIONEN
# ============================================================

def clean_string(value) -> str:
    """
    Wandelt Excel-Werte in saubere Strings um.

    NaN und None werden zu "".
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


def normalize_original_id(value) -> str:
    """
    Vereinheitlicht Originaldatensatz_ID.

    Excel kann IDs z. B. als

        4566

    oder

        4566.0

    einlesen.

    Beides wird auf:

        4566

    normalisiert.
    """

    text = clean_string(
        value
    )


    if not text:

        return ""


    if re.fullmatch(
            r"\d+\.0+",
            text,
    ):

        return text.split(
            "."
        )[0]


    return text


def normalize_source_code(value) -> str:
    """
    Bereinigt Quellklassencodes.

    Beispiel:

        " q6 "

    wird zu:

        "Q6"
    """

    return (

        clean_string(
            value
        )

        .replace(
            " ",
            "",
        )

        .upper()
    )


def normalize_label_key(value) -> str:
    """
    Normalisiert Klassenbezeichnungen ausschließlich
    für den technischen Vergleich.

    Dadurch werden z. B. toleriert:

        Kälteanlagen- / Verflüssigerwärme

        Kälteanlagen-/Verflüssigerwärme

    sowie verschiedene Gedankenstriche.
    """

    text = (

        clean_string(
            value
        )

        .casefold()
    )


    text = (

        text

        .replace(
            "–",
            "-",
        )

        .replace(
            "—",
            "-",
        )
    )


    text = re.sub(

        r"\s*/\s*",

        "/",

        text,
    )


    text = re.sub(

        r"\s*-\s*",

        "-",

        text,
    )


    text = re.sub(

        r"\s+",

        " ",

        text,
    )


    return text.strip()


def build_allowed_label_keys() -> dict:
    """
    Erzeugt alle zulässigen normalisierten
    Bezeichnungsvarianten je Quellklassencode.
    """

    result = {}


    for (
            code,
            canonical,
    ) in VALID_SOURCE_CLASSES.items():


        labels = set(

            SOURCE_CLASS_LABEL_ALIASES.get(
                code,
                set(),
            )
        )


        labels.add(
            canonical
        )


        result[
            code
        ] = {

            normalize_label_key(
                label
            )

            for label
            in labels
        }


    return result


ALLOWED_LABEL_KEYS = (
    build_allowed_label_keys()
)


def canonicalize_source_label(
        code: str,
        label: str,
) -> str:
    """
    Prüft, ob Code und Bezeichnung zusammenpassen.

    Falls eine bekannte alte Bezeichnung verwendet wurde,
    wird die aktuelle kanonische Bezeichnung zurückgegeben.

    Ungültige Kombination:
        -> ""
    """

    code = normalize_source_code(
        code
    )


    if (
            code
            not in VALID_SOURCE_CLASSES
    ):

        return ""


    normalized_label = (
        normalize_label_key(
            label
        )
    )


    if (
            normalized_label
            in ALLOWED_LABEL_KEYS[
        code
    ]
    ):

        return (
            VALID_SOURCE_CLASSES[
                code
            ]
        )


    return ""


# ============================================================
# 4. MASTERDATEI EINLESEN
# ============================================================

def load_master() -> pd.DataFrame:
    """
    Liest die vollständige Tabelle mit allen
    Abwärmepotentialen.

    Die Masterdatei definiert weiterhin die Grundgesamtheit.

    Der Rückspielprozess darf:

    - keine Zeile löschen
    - keine Zeile hinzufügen
    - keine Reihenfolge verändern
    """


    if not MASTER_FILE.exists():

        raise FileNotFoundError(

            f"Masterdatei nicht gefunden:\n"
            f"{MASTER_FILE}"
        )


    master = pd.read_excel(

        MASTER_FILE,

        sheet_name=
        MASTER_SHEET,

        dtype=str,

        keep_default_na=False,
    )


    # ========================================================
    # PFLICHTSPALTEN
    # ========================================================

    required = {

        "Originaldatensatz_ID",

        "Klassifikations_ID",
    }


    missing = (

            required

            - set(
        master.columns
    )
    )


    if missing:

        raise ValueError(

            "In der Masterdatei fehlen "
            "folgende Spalten:\n\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    # ========================================================
    # IDS BEREINIGEN
    # ========================================================

    master[
        "Originaldatensatz_ID"
    ] = (

        master[
            "Originaldatensatz_ID"
        ]

        .map(
            normalize_original_id
        )
    )


    master[
        "Klassifikations_ID"
    ] = (

        master[
            "Klassifikations_ID"
        ]

        .map(
            clean_string
        )
    )


    # --------------------------------------------------------
    # Neue Standortverbund-/Profil-IDs ebenfalls säubern,
    # sofern vorhanden.
    # --------------------------------------------------------

    for column in [

        "Standortverbund_ID",

        "Profil_Klassifikations_ID",

    ]:

        if (
                column
                in master.columns
        ):

            master[
                column
            ] = (

                master[
                    column
                ]

                .map(
                    clean_string
                )
            )


    # ========================================================
    # INTEGRITÄTSPRÜFUNGEN
    # ========================================================

    empty_ids = (

        master[
            "Originaldatensatz_ID"
        ]

        .eq("")
    )


    if empty_ids.any():

        raise ValueError(

            f"{empty_ids.sum()} Zeilen der "
            "Masterdatei besitzen keine "
            "Originaldatensatz_ID."
        )


    duplicated_ids = (

        master[
            "Originaldatensatz_ID"
        ]

        .duplicated(
            keep=False
        )
    )


    if duplicated_ids.any():


        display_columns = [

            column

            for column in [

                "Originaldatensatz_ID",

                "Firmenname",

                "Standortname",

            ]

            if column
               in master.columns
        ]


        examples = (

            master.loc[

                duplicated_ids,

                display_columns,
            ]

            .head(
                20
            )

            .to_string(
                index=False
            )
        )


        raise ValueError(

            "Originaldatensatz_ID ist in der "
            "Masterdatei nicht eindeutig.\n\n"

            f"Beispiele:\n"
            f"{examples}"
        )


    return master


# ============================================================
# 5. EINEN KLASSIFIZIERTEN BATCH PRÜFEN
# ============================================================

def validate_classified_batch(
        batch: pd.DataFrame,
        filename: str,
):
    """
    Prüft einen fertig klassifizierten KI-Batch.

    Neu:

    - Q6 zulässig
    - Q7 zulässig
    - neue Klassenbezeichnungen
    - alte bekannte Q2/Q3/Q4-Bezeichnungen kompatibel
    - Q1-Q7 dürfen nicht "keine" haben
    - QX muss immer "keine" haben
    """


    required = {

        "Originaldatensatz_ID",

        "Klassifikations_ID",

        "Quellklasse_Code",

        "Quellklasse",

        "Quellklasse_Begruendung",

        "Quellklasse_Konfidenz",
    }


    missing = (

            required

            - set(
        batch.columns
    )
    )


    if missing:

        raise ValueError(

            f"In {filename} fehlen "
            "folgende Spalten:\n\n"

            + "\n".join(
                sorted(
                    missing
                )
            )
        )


    # ========================================================
    # IDS NORMALISIEREN
    # ========================================================

    batch[
        "Originaldatensatz_ID"
    ] = (

        batch[
            "Originaldatensatz_ID"
        ]

        .map(
            normalize_original_id
        )
    )


    batch[
        "Klassifikations_ID"
    ] = (

        batch[
            "Klassifikations_ID"
        ]

        .map(
            clean_string
        )
    )


    for column in [

        "Standortverbund_ID",

        "Profil_Klassifikations_ID",

    ]:

        if (
                column
                in batch.columns
        ):

            batch[
                column
            ] = (

                batch[
                    column
                ]

                .map(
                    clean_string
                )
            )


    # ========================================================
    # IDS DÜRFEN NICHT LEER SEIN
    # ========================================================

    if (

            batch[
                "Originaldatensatz_ID"
            ]

                    .eq("")

                    .any()
    ):

        raise ValueError(

            f"In {filename} gibt es leere "
            "Originaldatensatz_IDs."
        )


    if (

            batch[
                "Klassifikations_ID"
            ]

                    .eq("")

                    .any()
    ):

        raise ValueError(

            f"In {filename} gibt es leere "
            "Klassifikations_IDs."
        )


    # ========================================================
    # ORIGINALDATENSATZ_ID MUSS PRO BATCH EINDEUTIG SEIN
    # ========================================================

    duplicated = (

        batch[
            "Originaldatensatz_ID"
        ]

        .duplicated(
            keep=False
        )
    )


    if duplicated.any():

        raise ValueError(

            f"In {filename} kommt mindestens "
            "eine Originaldatensatz_ID mehrfach vor."
        )


    # ========================================================
    # ERGEBNISFELDER BEREINIGEN
    # ========================================================

    for column in [

        "Quellklasse_Code",

        "Quellklasse",

        "Quellklasse_Begruendung",

        "Quellklasse_Konfidenz",

    ]:

        batch[
            column
        ] = (

            batch[
                column
            ]

            .map(
                clean_string
            )
        )


    batch[
        "Quellklasse_Code"
    ] = (

        batch[
            "Quellklasse_Code"
        ]

        .map(
            normalize_source_code
        )
    )


    batch[
        "Quellklasse_Konfidenz"
    ] = (

        batch[
            "Quellklasse_Konfidenz"
        ]

        .str.lower()

        .str.strip()
    )


    # ========================================================
    # KEINE LEEREN KLASSENCODES
    # ========================================================

    empty_codes = (

        batch[
            "Quellklasse_Code"
        ]

        .eq("")
    )


    if empty_codes.any():

        raise ValueError(

            f"In {filename} wurden "
            f"{empty_codes.sum()} Zeilen "
            "nicht klassifiziert."
        )


    # ========================================================
    # NUR Q1-Q7 / QX
    # ========================================================

    invalid_codes = (

        ~batch[
            "Quellklasse_Code"
        ]

        .isin(
            SOURCE_CLASS_ORDER
        )
    )


    if invalid_codes.any():


        invalid_values = (

            batch.loc[

                invalid_codes,

                "Quellklasse_Code",

            ]

            .unique()

            .tolist()
        )


        raise ValueError(

            f"In {filename} wurden ungültige "
            "Quellklassen-Codes gefunden:\n\n"

            f"{invalid_values}\n\n"

            "Zulässig sind ausschließlich: "

            + ", ".join(
                SOURCE_CLASS_ORDER
            )
        )


    # ========================================================
    # CODE UND BEZEICHNUNG PRÜFEN
    # ========================================================

    wrong_labels = []

    canonical_labels = []


    for _, row in (
            batch.iterrows()
    ):


        code = row[
            "Quellklasse_Code"
        ]


        actual = row[
            "Quellklasse"
        ]


        canonical = (
            canonicalize_source_label(

                code,

                actual,
            )
        )


        if canonical:


            canonical_labels.append(
                canonical
            )


        else:


            canonical_labels.append(
                actual
            )


            wrong_labels.append(
                (

                    row[
                        "Originaldatensatz_ID"
                    ],

                    code,

                    actual,

                    VALID_SOURCE_CLASSES[
                        code
                    ],
                )
            )


    if wrong_labels:


        text = "\n".join(

            f"ID {row_id}: "
            f"{code} / '{actual}' "
            f"(erwartet '{expected}')"

            for (
                row_id,
                code,
                actual,
                expected,
            )

            in wrong_labels[:10]
        )


        raise ValueError(

            f"In {filename} passen Code und "
            "Quellklassen-Bezeichnung nicht zusammen.\n\n"

            + text
        )


    # --------------------------------------------------------
    # Alle bekannten alten Bezeichnungen werden nun auf die
    # neue kanonische Bezeichnung vereinheitlicht.
    # --------------------------------------------------------

    batch[
        "Quellklasse"
    ] = canonical_labels


    # ========================================================
    # KONFIDENZ PRÜFEN
    # ========================================================

    invalid_confidence = (

        ~batch[
            "Quellklasse_Konfidenz"
        ]

        .isin(
            VALID_CONFIDENCE
        )
    )


    if invalid_confidence.any():


        invalid_values = (

            batch.loc[

                invalid_confidence,

                "Quellklasse_Konfidenz",

            ]

            .unique()

            .tolist()
        )


        raise ValueError(

            f"In {filename} wurden ungültige "
            "Konfidenzwerte gefunden:\n\n"

            f"{invalid_values}"
        )


    # ========================================================
    # QX MUSS IMMER "keine" HABEN
    # ========================================================

    qx_wrong = (

            batch[
                "Quellklasse_Code"
            ]
            .eq(
                "QX"
            )

            &

            ~batch[
                "Quellklasse_Konfidenz"
            ]
            .eq(
                "keine"
            )
    )


    if qx_wrong.any():

        raise ValueError(

            f"In {filename} besitzt mindestens "
            "eine QX-Zeile eine andere "
            "Konfidenz als 'keine'."
        )


    # ========================================================
    # Q1-Q7 DÜRFEN NIEMALS "keine" HABEN
    # ========================================================

    non_qx_wrong = (

            ~batch[
                "Quellklasse_Code"
            ]
            .eq(
                "QX"
            )

            &

            batch[
                "Quellklasse_Konfidenz"
            ]
            .eq(
                "keine"
            )
    )


    if non_qx_wrong.any():

        raise ValueError(

            f"In {filename} besitzt mindestens "
            "eine Q1-Q7-Zeile die "
            "Konfidenz 'keine'."
        )


    # ========================================================
    # BEGRÜNDUNG MUSS VORHANDEN SEIN
    # ========================================================

    empty_reason = (

        batch[
            "Quellklasse_Begruendung"
        ]

        .eq("")
    )


    if empty_reason.any():

        raise ValueError(

            f"In {filename} fehlen bei "
            f"{empty_reason.sum()} Zeilen "
            "die Begründungen."
        )


# ============================================================
# 6. ALLE KLASSIFIZIERTEN BATCHES EINLESEN
# ============================================================

def load_classified_batches() -> pd.DataFrame:
    """
    Liest alle derzeit vorhandenen klassifizierten
    Quellen-Batches.

    Es müssen noch NICHT zwingend alle Batches fertig sein.

    Fehlende Batches bleiben später im Master als:

        noch_nicht_klassifiziert
    """


    if not CLASSIFIED_BATCH_DIR.exists():

        raise FileNotFoundError(

            "Ordner mit klassifizierten "
            "Quellen-Batches wurde nicht gefunden:\n"

            f"{CLASSIFIED_BATCH_DIR}"
        )


    batch_files = sorted(

        file

        for file
        in CLASSIFIED_BATCH_DIR.glob(
            CLASSIFIED_BATCH_PATTERN
        )

        if not file.name.startswith(
            "~$"
        )
    )


    if not batch_files:

        raise FileNotFoundError(

            "Es wurden keine klassifizierten "
            "Quellen-Batches gefunden.\n\n"

            f"Ordner: "
            f"{CLASSIFIED_BATCH_DIR}\n"

            f"Muster: "
            f"{CLASSIFIED_BATCH_PATTERN}"
        )


    frames = []


    for file in batch_files:


        print(
            f"   Einlesen: "
            f"{file.name}"
        )


        batch = pd.read_excel(

            file,

            sheet_name=
            CLASSIFIED_BATCH_SHEET,

            dtype=str,

            keep_default_na=False,
        )


        # ====================================================
        # BATCH VOLLSTÄNDIG PRÜFEN
        # ====================================================

        validate_classified_batch(

            batch,

            file.name,
        )


        # ====================================================
        # BATCH-HERKUNFT MITFÜHREN
        # ====================================================

        if (
                "Batch_ID"
                in batch.columns
        ):


            batch[
                "_Quellklassifikation_Batch_ID"
            ] = (

                batch[
                    "Batch_ID"
                ]

                .map(
                    clean_string
                )
            )


        else:


            match = re.search(

                r"Quellen_Batch_(\d+)",

                file.name,

                flags=
                re.IGNORECASE,
            )


            if match:


                batch_id = (

                        "QUELLEN_BATCH_"

                        + str(

                    int(
                        match.group(1)
                    )
                )

                        .zfill(
                    3
                )
                )


            else:


                batch_id = (
                    file.stem
                )


            batch[
                "_Quellklassifikation_Batch_ID"
            ] = batch_id


        batch[
            "_Quellklassifikation_Datei"
        ] = file.name


        # ====================================================
        # BENÖTIGTE SPALTEN
        # ====================================================

        keep_columns = [

            "Originaldatensatz_ID",

            "Klassifikations_ID",
        ]


        # ----------------------------------------------------
        # Neue Identitätsspalten werden mitgeführt,
        # sofern sie im Batch vorhanden sind.
        # ----------------------------------------------------

        for optional_column in [

            "Standortverbund_ID",

            "Profil_Klassifikations_ID",

        ]:

            if (
                    optional_column
                    in batch.columns
            ):

                keep_columns.append(
                    optional_column
                )


        keep_columns += [

            "Quellklasse_Code",

            "Quellklasse",

            "Quellklasse_Begruendung",

            "Quellklasse_Konfidenz",

            "_Quellklassifikation_Batch_ID",

            "_Quellklassifikation_Datei",
        ]


        frames.append(

            batch[
                keep_columns
            ]

            .copy()
        )


    # ========================================================
    # ALLE BATCHERGEBNISSE ZUSAMMENFÜHREN
    # ========================================================

    classified = pd.concat(

        frames,

        ignore_index=True,

        sort=False,
    )


    # --------------------------------------------------------
    # Fehlende optionale Identitätsspalten aus älteren
    # einzelnen Batches werden nach concat als NaN erzeugt.
    # --------------------------------------------------------

    for optional_column in [

        "Standortverbund_ID",

        "Profil_Klassifikations_ID",

    ]:

        if (
                optional_column
                in classified.columns
        ):

            classified[
                optional_column
            ] = (

                classified[
                    optional_column
                ]

                .fillna("")

                .map(
                    clean_string
                )
            )


    # ========================================================
    # ORIGINALDATENSATZ_ID BATCHÜBERGREIFEND EINDEUTIG
    # ========================================================

    duplicated = (

        classified[
            "Originaldatensatz_ID"
        ]

        .duplicated(
            keep=False
        )
    )


    if duplicated.any():


        duplicate_table = (

            classified.loc[

                duplicated,

                [

                    "Originaldatensatz_ID",

                    "_Quellklassifikation_Batch_ID",

                    "_Quellklassifikation_Datei",
                ],
            ]

            .sort_values(
                "Originaldatensatz_ID"
            )
        )


        print()

        print(

            duplicate_table

            .head(
                30
            )

            .to_string(
                index=False
            )
        )


        raise ValueError(

            "\nDoppelte Originaldatensatz_IDs in den "
            "klassifizierten Batchdateien gefunden.\n\n"

            "Sehr wahrscheinlich liegen zwei Versionen "
            "derselben Batchdatei im Ordner.\n"

            "Bitte pro Quellen-Batch nur eine fertige "
            "Version behalten."
        )


    return classified


# ============================================================
# 7. KLASSIFIZIERTE BATCHES GEGEN MASTER PRÜFEN
# ============================================================

def validate_against_master(
        master: pd.DataFrame,
        classified: pd.DataFrame,
):
    """
    Prüft die technischen Identitäten gegen den Master.

    Pflicht:

    - Originaldatensatz_ID muss existieren
    - Klassifikations_ID muss übereinstimmen

    Zusätzlich:

    - Standortverbund_ID
    - Profil_Klassifikations_ID

    werden geprüft, sofern sie vom jeweiligen Batch
    tatsächlich mitgeführt werden.
    """


    master_columns = [

        "Originaldatensatz_ID",

        "Klassifikations_ID",
    ]


    for optional_column in [

        "Standortverbund_ID",

        "Profil_Klassifikations_ID",

    ]:

        if (
                optional_column
                in master.columns
        ):

            master_columns.append(
                optional_column
            )


    master_keys = (

        master[
            master_columns
        ]

        .copy()
    )


    check = classified.merge(

        master_keys,

        on=
        "Originaldatensatz_ID",

        how=
        "left",

        suffixes=(
            "_Batch",
            "_Master",
        ),

        indicator=True,

        validate=
        "1:1",
    )


    # ========================================================
    # A) UNBEKANNTE ORIGINALDATENSATZ_ID
    # ========================================================

    unknown_ids = (

        ~check[
            "_merge"
        ]

        .eq(
            "both"
        )
    )


    if unknown_ids.any():


        examples = (

            check.loc[

                unknown_ids,

                [

                    "Originaldatensatz_ID",

                    "_Quellklassifikation_Datei",
                ],
            ]

            .head(
                20
            )

            .to_string(
                index=False
            )
        )


        raise ValueError(

            "Mindestens eine Originaldatensatz_ID "
            "aus den klassifizierten Batches "
            "existiert nicht in der Mastertabelle.\n\n"

            f"Beispiele:\n"
            f"{examples}"
        )


    # ========================================================
    # B) KLASSIFIKATIONS_ID MUSS IDENTISCH SEIN
    # ========================================================

    wrong_site = (

            check[
                "Klassifikations_ID_Batch"
            ]

            !=

            check[
                "Klassifikations_ID_Master"
            ]
    )


    if wrong_site.any():


        examples = (

            check.loc[

                wrong_site,

                [

                    "Originaldatensatz_ID",

                    "Klassifikations_ID_Batch",

                    "Klassifikations_ID_Master",

                    "_Quellklassifikation_Datei",
                ],
            ]

            .head(
                20
            )

            .to_string(
                index=False
            )
        )


        raise ValueError(

            "Bei mindestens einer Originaldatensatz_ID "
            "stimmt die Klassifikations_ID aus dem "
            "Quellen-Batch nicht mit der "
            "Mastertabelle überein.\n\n"

            f"Beispiele:\n"
            f"{examples}"
        )


    # ========================================================
    # C) STANDORTVERBUND / PROFIL-ID OPTIONAL PRÜFEN
    # ========================================================

    for column in [

        "Standortverbund_ID",

        "Profil_Klassifikations_ID",

    ]:


        batch_column = (
            f"{column}_Batch"
        )


        master_column = (
            f"{column}_Master"
        )


        if (

                batch_column
                in check.columns

                and

                master_column
                in check.columns

        ):


            # ------------------------------------------------
            # Nur Zeilen prüfen, bei denen der Batch die
            # neue ID tatsächlich enthält.
            #
            # Dadurch bleiben ältere Batchdateien grundsätzlich
            # einlesbar.
            # ------------------------------------------------

            provided = (

                check[
                    batch_column
                ]

                .map(
                    clean_string
                )

                .ne("")
            )


            mismatch = (

                    provided

                    &

                    (

                            check[
                                batch_column
                            ]
                            .map(
                                clean_string
                            )

                            !=

                            check[
                                master_column
                            ]
                            .map(
                                clean_string
                            )
                    )
            )


            if mismatch.any():


                examples = (

                    check.loc[

                        mismatch,

                        [

                            "Originaldatensatz_ID",

                            batch_column,

                            master_column,

                            "_Quellklassifikation_Datei",
                        ],
                    ]

                    .head(
                        20
                    )

                    .to_string(
                        index=False
                    )
                )


                raise ValueError(

                    f"Bei mindestens einer Quelle "
                    f"stimmt '{column}' aus dem "
                    "klassifizierten Batch nicht mit "
                    "dem aktuellen Master überein.\n\n"

                    f"Beispiele:\n"
                    f"{examples}"
                )


# ============================================================
# 8. QUELLKLASSENERGEBNISSE ZURÜCKSPIELEN
# ============================================================

def merge_classifications(
        master: pd.DataFrame,
        classified: pd.DataFrame,
) -> pd.DataFrame:
    """
    Spielt ausschließlich die Quellklassenergebnisse
    und ihre technische Herkunft auf den Master zurück.

    Alle bereits im Master vorhandenen:

    - WZ_Final_Code
    - Profil_WZ_Final_Code
    - Standortverbund_ID
    - Profil_Klassifikations_ID
    - sonstigen WZ-/Standortfelder

    bleiben unverändert erhalten.
    """


    result = (
        master.copy()
    )


    # ========================================================
    # EVENTUELL ALTE QUELLKLASSENERGEBNISSE ENTFERNEN
    # ========================================================

    columns_to_replace = [

        "Quellklasse_Code",

        "Quellklasse",

        "Quellklasse_Begruendung",

        "Quellklasse_Konfidenz",

        "Quellklassifikation_Status",

        "Quellklassifikation_Batch_ID",

        "Quellklassifikation_Datei",
    ]


    existing = [

        column

        for column
        in columns_to_replace

        if column
           in result.columns
    ]


    if existing:

        result = result.drop(
            columns=
            existing
        )


    # ========================================================
    # ERGEBNISTABELLE VORBEREITEN
    # ========================================================

    classifications = (

        classified[
            [

                "Originaldatensatz_ID",

                "Quellklasse_Code",

                "Quellklasse",

                "Quellklasse_Begruendung",

                "Quellklasse_Konfidenz",

                "_Quellklassifikation_Batch_ID",

                "_Quellklassifikation_Datei",
            ]
        ]

        .copy()

        .rename(
            columns={

                "_Quellklassifikation_Batch_ID":
                    "Quellklassifikation_Batch_ID",

                "_Quellklassifikation_Datei":
                    "Quellklassifikation_Datei",
            }
        )
    )


    # ========================================================
    # LEFT JOIN
    #
    # MASTER BLEIBT GRUNDGESAMTHEIT
    # ========================================================

    result = result.merge(

        classifications,

        on=
        "Originaldatensatz_ID",

        how=
        "left",

        validate=
        "1:1",

        sort=False,
    )


    # ========================================================
    # LEERE WERTE BEREINIGEN
    # ========================================================

    classification_columns = [

        "Quellklasse_Code",

        "Quellklasse",

        "Quellklasse_Begruendung",

        "Quellklasse_Konfidenz",

        "Quellklassifikation_Batch_ID",

        "Quellklassifikation_Datei",
    ]


    for column in classification_columns:

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


    # ========================================================
    # STATUS
    # ========================================================

    result[
        "Quellklassifikation_Status"
    ] = (
        "noch_nicht_klassifiziert"
    )


    result.loc[

        result[
            "Quellklasse_Code"
        ]
        .ne(""),

        "Quellklassifikation_Status",

    ] = (
        "klassifiziert"
    )


    # ========================================================
    # ERGEBNISSPALTEN ANS ENDE SETZEN
    # ========================================================

    end_columns = [

        "Quellklassifikation_Status",

        "Quellklassifikation_Batch_ID",

        "Quellklassifikation_Datei",

        "Quellklasse_Code",

        "Quellklasse",

        "Quellklasse_Begruendung",

        "Quellklasse_Konfidenz",
    ]


    other_columns = [

        column

        for column
        in result.columns

        if column
           not in end_columns
    ]


    result = result[

        other_columns

        + end_columns
        ]


    return result


# ============================================================
# 9. FINALE INTEGRITÄTSPRÜFUNG
# ============================================================

def validate_final_table(
        master: pd.DataFrame,
        result: pd.DataFrame,
):
    """
    Stellt sicher, dass beim Rückspielen keine
    Originalquelle verloren geht oder vervielfacht wird.
    """


    # ========================================================
    # A) ZEILENANZAHL
    # ========================================================

    if (
            len(
                master
            )
            !=
            len(
                result
            )
    ):

        raise ValueError(

            "Die Zeilenzahl hat sich beim "
            "Zusammenführen verändert.\n\n"

            f"Master: "
            f"{len(master):,}\n"

            f"Ergebnis: "
            f"{len(result):,}"
        )


    # ========================================================
    # B) ORIGINALDATENSATZ_ID EINDEUTIG
    # ========================================================

    if not result[
        "Originaldatensatz_ID"
    ].is_unique:

        raise ValueError(

            "Originaldatensatz_ID ist nach dem "
            "Merge nicht mehr eindeutig."
        )


    # ========================================================
    # C) IDENTISCHE ID-MENGE
    # ========================================================

    if (

            set(
                master[
                    "Originaldatensatz_ID"
                ]
            )

            !=

            set(
                result[
                    "Originaldatensatz_ID"
                ]
            )

    ):

        raise ValueError(

            "Die Menge der Originaldatensatz_IDs "
            "hat sich durch das Zusammenführen verändert."
        )


    # ========================================================
    # D) REIHENFOLGE MUSS IDENTISCH BLEIBEN
    # ========================================================

    if (

            master[
                "Originaldatensatz_ID"
            ]
                    .tolist()

            !=

            result[
                "Originaldatensatz_ID"
            ]
                    .tolist()

    ):

        raise ValueError(

            "Die Reihenfolge der "
            "Originaldatensatz_IDs wurde verändert."
        )


    # ========================================================
    # E) FINALE QUELLKLASSEN NOCH EINMAL PRÜFEN
    # ========================================================

    classified_rows = result[

        result[
            "Quellklassifikation_Status"
        ]

        .eq(
            "klassifiziert"
        )

    ]


    invalid_code = (

        ~classified_rows[
            "Quellklasse_Code"
        ]

        .isin(
            SOURCE_CLASS_ORDER
        )
    )


    if invalid_code.any():

        raise ValueError(

            "Nach dem Merge existiert mindestens "
            "ein ungültiger Quellklassen-Code."
        )


    expected_labels = (

        classified_rows[
            "Quellklasse_Code"
        ]

        .map(
            VALID_SOURCE_CLASSES
        )
    )


    wrong_label = (

            classified_rows[
                "Quellklasse"
            ]

            !=

            expected_labels
    )


    if wrong_label.any():

        raise ValueError(

            "Nach dem Merge stimmt mindestens "
            "eine Quellklassen-Bezeichnung "
            "nicht mit dem Code überein."
        )


# ============================================================
# 10. ZUSAMMENFASSUNG
# ============================================================

def create_summary(
        result: pd.DataFrame,
        classified: pd.DataFrame,
) -> pd.DataFrame:
    """
    Erstellt Qualitäts- und Fortschrittskennzahlen.

    Es wird weiterhin NICHT gefiltert.
    """


    total = len(
        result
    )


    classified_count = int(

        result[
            "Quellklassifikation_Status"
        ]

        .eq(
            "klassifiziert"
        )

        .sum()
    )


    not_classified_count = (

            total

            - classified_count
    )


    rows = [

        {
            "Kennzahl":
                "Abwärmepotentiale gesamt",

            "Wert":
                total,
        },

        {
            "Kennzahl":
                "Bereits quellklassifiziert",

            "Wert":
                classified_count,
        },

        {
            "Kennzahl":
                "Noch nicht quellklassifiziert",

            "Wert":
                not_classified_count,
        },

        {
            "Kennzahl":
                "Anteil klassifiziert",

            "Wert":
                (
                    classified_count
                    / total

                    if total

                    else 0
                ),
        },

        {
            "Kennzahl":
                "Eingelesene klassifizierte Batchdateien",

            "Wert":
                classified[
                    "_Quellklassifikation_Datei"
                ]

                .nunique(),
        },
    ]


    # ========================================================
    # STANDORTKENNZAHLEN
    # ========================================================

    if (
            "Klassifikations_ID"
            in result.columns
    ):

        rows.append(
            {

                "Kennzahl":
                    "Teilstandorte / Klassifikations_IDs",

                "Wert":
                    result[
                        "Klassifikations_ID"
                    ]
                    .nunique(),
            }
        )


    if (
            "Standortverbund_ID"
            in result.columns
    ):

        rows.append(
            {

                "Kennzahl":
                    "Finale Standortverbünde",

                "Wert":
                    result[
                        "Standortverbund_ID"
                    ]
                    .nunique(),
            }
        )


    # ========================================================
    # VERTEILUNG Q1-Q7 + QX
    # ========================================================

    for code in (
            SOURCE_CLASS_ORDER
    ):


        count = int(

            result[
                "Quellklasse_Code"
            ]

            .eq(
                code
            )

            .sum()
        )


        rows.append(
            {

                "Kennzahl":
                    (
                        f"{code} – "
                        f"{VALID_SOURCE_CLASSES[code]}"
                    ),

                "Wert":
                    count,
            }
        )


    # ========================================================
    # QX / Q6 / Q7 BESONDERS AUSWEISEN
    # ========================================================

    qx_count = int(

        result[
            "Quellklasse_Code"
        ]

        .eq(
            "QX"
        )

        .sum()
    )


    q6_q7_count = int(

        result[
            "Quellklasse_Code"
        ]

        .isin(
            [
                "Q6",
                "Q7",
            ]
        )

        .sum()
    )


    rows += [

        {
            "Kennzahl":
                "QX-Anteil unter klassifizierten Quellen",

            "Wert":
                (
                    qx_count
                    / classified_count

                    if classified_count

                    else 0
                ),
        },

        {
            "Kennzahl":
                "Q6+Q7 Fallback-Klassen zusammen",

            "Wert":
                q6_q7_count,
        },

        {
            "Kennzahl":
                "Anteil Q6+Q7 unter klassifizierten Quellen",

            "Wert":
                (
                    q6_q7_count
                    / classified_count

                    if classified_count

                    else 0
                ),
        },
    ]


    # ========================================================
    # KONFIDENZ
    # ========================================================

    for confidence in [

        "hoch",

        "mittel",

        "gering",

        "keine",

    ]:


        rows.append(
            {

                "Kennzahl":
                    f"Konfidenz {confidence}",

                "Wert":
                    int(

                        result[
                            "Quellklasse_Konfidenz"
                        ]

                        .eq(
                            confidence
                        )

                        .sum()
                    ),
            }
        )


    return pd.DataFrame(
        rows
    )


# ============================================================
# 11. BATCHÜBERSICHT
# ============================================================

def create_batch_summary(
        classified: pd.DataFrame,
) -> pd.DataFrame:
    """
    Erstellt pro eingelesener Batchdatei die Verteilung
    über Q1-Q7 + QX.
    """


    rows = []


    for (
            filename,
            group,
    ) in classified.groupby(

        "_Quellklassifikation_Datei",

        sort=True,
    ):


        batch_ids = (

            group[
                "_Quellklassifikation_Batch_ID"
            ]

            .drop_duplicates()

            .tolist()
        )


        row = {

            "Batch_ID":
                (
                    batch_ids[0]

                    if batch_ids

                    else ""
                ),

            "Dateiname":
                filename,

            "Anzahl_Quellen":
                len(
                    group
                ),
        }


        # ----------------------------------------------------
        # Dynamisch alle Q1-Q7 + QX
        # ----------------------------------------------------

        for code in (
                SOURCE_CLASS_ORDER
        ):

            row[
                code
            ] = int(

                group[
                    "Quellklasse_Code"
                ]

                .eq(
                    code
                )

                .sum()
            )


        row[
            "QX_Anteil"
        ] = (

            row[
                "QX"
            ]

            / len(
                group
            )

            if len(
                group
            )

            else 0
        )


        row[
            "Q6_Q7_Fallbacks"
        ] = (

                row[
                    "Q6"
                ]

                + row[
                    "Q7"
                ]
        )


        rows.append(
            row
        )


    return pd.DataFrame(
        rows
    )


# ============================================================
# 12. TAXONOMIE-TABELLE
# ============================================================

def create_taxonomy_table() -> pd.DataFrame:
    """
    Dokumentiert die aktuell verwendete Q1-Q7+QX-Taxonomie
    direkt in der Ausgabedatei.
    """


    definitions = {


        "Q1":
            (
                "Konkreter flüssiger Wärmestrom, z. B. "
                "Kühlwasser, Warmwasser, Öl oder Glykol. "
                "Hat auch bei Kälteanlagen und Kompressoren "
                "Vorrang, wenn der Flüssigkeitspfad bekannt ist."
            ),


        "Q2":
            (
                "Wasserbasierter Prozessdampf, Brüden und "
                "zugehöriges Kondensat. "
                "Kältemittel sind ausgeschlossen."
            ),


        "Q3":
            (
                "Nicht verbrennungsbedingter Luft-/Gasstrom, "
                "z. B. Abluft, Kühlluft oder heiße Druckluft. "
                "Bei Kälteanlagen Vorrang vor Q6, wenn der "
                "luftseitige Wärmeweg bekannt ist."
            ),


        "Q4":
            (
                "Rauchgas bzw. Gasstrom aus Verbrennung "
                "oder thermischer Oxidation."
            ),


        "Q5":
            (
                "Feste, produktgebundene, Oberflächen- "
                "oder diffuse Abwärme."
            ),


        "Q6":
            (
                "Kältemittelseitige Kälteanlagen-/"
                "Verflüssigerwärme oder Fallback, wenn eine "
                "Kälteanlage eindeutig ist, der sekundäre "
                "Luft-/Flüssigkeitspfad aber unbekannt bleibt."
            ),


        "Q7":
            (
                "Fallback für eindeutig identifizierte "
                "Druckluft-/Luftkompression, wenn der konkrete "
                "Luft-/Flüssigkeitskühlpfad nicht angegeben ist."
            ),


        "QX":
            (
                "Technisch nicht eindeutig bestimmbar oder "
                "mehrere wesentlich verschiedene Wärmewege "
                "gemeinsam bilanziert."
            ),
    }


    return pd.DataFrame(

        [

            {

                "Quellklasse_Code":
                    code,

                "Quellklasse":
                    VALID_SOURCE_CLASSES[
                        code
                    ],

                "Kurzdefinition":
                    definitions[
                        code
                    ],
            }

            for code
            in SOURCE_CLASS_ORDER
        ]
    )


# ============================================================
# 13. AUSGABE SCHREIBEN
# ============================================================

def save_output(
        result: pd.DataFrame,
        summary: pd.DataFrame,
        batch_summary: pd.DataFrame,
        taxonomy: pd.DataFrame,
):
    """
    Schreibt die vollständige neue Gesamttabelle.

    Es findet KEINE Filterung statt.
    """


    missing = result[

        result[
            "Quellklassifikation_Status"
        ]

        .eq(
            "noch_nicht_klassifiziert"
        )

    ].copy()


    with pd.ExcelWriter(

            OUTPUT_FILE,

            engine=
            "openpyxl",

    ) as writer:


        # ====================================================
        # HAUPTTABELLE
        # ====================================================

        result.to_excel(

            writer,

            sheet_name=
            "Abwaermepotentiale",

            index=False,
        )


        # ====================================================
        # ZUSAMMENFASSUNG
        # ====================================================

        summary.to_excel(

            writer,

            sheet_name=
            "Zusammenfassung",

            index=False,
        )


        # ====================================================
        # BATCHÜBERSICHT
        # ====================================================

        batch_summary.to_excel(

            writer,

            sheet_name=
            "Batch_Uebersicht",

            index=False,
        )


        # ====================================================
        # TAXONOMIE-DOKUMENTATION
        # ====================================================

        taxonomy.to_excel(

            writer,

            sheet_name=
            "Quellklassen_Taxonomie",

            index=False,
        )


        # ====================================================
        # NOCH NICHT KLASSIFIZIERTE QUELLEN
        # ====================================================

        missing.to_excel(

            writer,

            sheet_name=
            "Noch_nicht_klassifiziert",

            index=False,
        )


# ============================================================
# 14. HAUPTPROGRAMM
# ============================================================

def main():


    print()

    print(
        "=" * 78
    )

    print(
        "RÜCKSPIELEN DER QUELLKLASSIFIKATIONEN – "
        "Q1-Q7 + QX"
    )

    print(
        "=" * 78
    )

    print()


    # ========================================================
    # 1. MASTER
    # ========================================================

    print(
        "1. Vollständige Mastertabelle "
        "wird eingelesen ..."
    )


    master = (
        load_master()
    )


    print(

        f"   -> "
        f"{len(master):,} "
        "ursprüngliche Abwärmepotentiale"
    )


    if (
            "Standortverbund_ID"
            in master.columns
    ):

        print(

            "   -> finale Standortverbünde "
            "im Master: "

            f"{master['Standortverbund_ID'].nunique():,}"
        )


    # ========================================================
    # 2. BATCHES
    # ========================================================

    print()

    print(
        "2. Klassifizierte Quellen-Batches "
        "werden eingelesen ..."
    )


    classified = (
        load_classified_batches()
    )


    print()


    print(

        f"   -> "
        f"{classified['_Quellklassifikation_Datei'].nunique():,} "
        "klassifizierte Batchdateien"
    )


    print(

        f"   -> "
        f"{len(classified):,} "
        "klassifizierte Quellen"
    )


    # ========================================================
    # 3. MASTERABGLEICH
    # ========================================================

    print()

    print(

        "3. IDs der klassifizierten Quellen "
        "werden gegen den Master geprüft ..."
    )


    validate_against_master(

        master,

        classified,
    )


    print(

        "   -> alle klassifizierten Quellen "
        "eindeutig dem Master zugeordnet"
    )


    # ========================================================
    # 4. ZURÜCKSPIELEN
    # ========================================================

    print()

    print(

        "4. Quellklassen werden auf die "
        "vollständige Tabelle zurückgespielt ..."
    )


    result = (
        merge_classifications(

            master,

            classified,
        )
    )


    # ========================================================
    # 5. FINALE INTEGRITÄT
    # ========================================================

    print()

    print(

        "5. Integrität der vollständigen "
        "Tabelle wird geprüft ..."
    )


    validate_final_table(

        master,

        result,
    )


    print(
        "   -> Zeilenanzahl unverändert"
    )


    print(
        "   -> keine Originaldatensatz_ID verloren"
    )


    print(
        "   -> keine Originaldatensatz_ID doppelt"
    )


    print(
        "   -> ursprüngliche Reihenfolge erhalten"
    )


    print(
        "   -> Q1-Q7/QX-Codes und Labels konsistent"
    )


    # ========================================================
    # 6. KENNZAHLEN
    # ========================================================

    summary = (
        create_summary(

            result,

            classified,
        )
    )


    batch_summary = (
        create_batch_summary(
            classified
        )
    )


    taxonomy = (
        create_taxonomy_table()
    )


    # ========================================================
    # 7. SPEICHERN
    # ========================================================

    print()

    print(

        "6. Vollständige Ergebnistabelle "
        "wird gespeichert ..."
    )


    save_output(

        result,

        summary,

        batch_summary,

        taxonomy,
    )


    # ========================================================
    # 8. TERMINALAUSGABE
    # ========================================================

    total = len(
        result
    )


    classified_count = int(

        result[
            "Quellklassifikation_Status"
        ]

        .eq(
            "klassifiziert"
        )

        .sum()
    )


    remaining = (

            total

            - classified_count
    )


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

        f"Abwärmepotentiale gesamt:       "
        f"{total:,}"
    )


    print(

        f"Quellklassifiziert:             "
        f"{classified_count:,}"
    )


    print(

        f"Noch nicht klassifiziert:       "
        f"{remaining:,}"
    )


    if total:

        print(

            f"Klassifikationsfortschritt:     "
            f"{classified_count / total:.2%}"
        )


    # ========================================================
    # VERTEILUNG
    # ========================================================

    print()

    print(
        "Verteilung der Quellklassen:"
    )


    for code in (
            SOURCE_CLASS_ORDER
    ):


        count = int(

            result[
                "Quellklasse_Code"
            ]

            .eq(
                code
            )

            .sum()
        )


        print(

            f"   {code:<3} "

            f"{VALID_SOURCE_CLASSES[code]:<55} "

            f"{count:>7,}"
        )


    # ========================================================
    # QX / Q6 / Q7
    # ========================================================

    if classified_count:


        qx_count = int(

            result[
                "Quellklasse_Code"
            ]

            .eq(
                "QX"
            )

            .sum()
        )


        q6_count = int(

            result[
                "Quellklasse_Code"
            ]

            .eq(
                "Q6"
            )

            .sum()
        )


        q7_count = int(

            result[
                "Quellklasse_Code"
            ]

            .eq(
                "Q7"
            )

            .sum()
        )


        print()


        print(

            "QX-Anteil unter klassifizierten Quellen: "

            f"{qx_count / classified_count:.2%}"
        )


        print(

            "Q6 Kälteanlagen-/Verflüssigerwärme:       "

            f"{q6_count:,}"
        )


        print(

            "Q7 Druckluft-/Kompressorwärme:             "

            f"{q7_count:,}"
        )


    # ========================================================
    # DATEI
    # ========================================================

    print()

    print(
        "Ausgabedatei:"
    )


    print(
        OUTPUT_FILE.resolve()
    )


    print()


    print(
        "Es wurde noch KEINE Quelle gefiltert."
    )


    print(

        "QX, geringe Konfidenzen und ggf. noch nicht "
        "klassifizierte Quellen bleiben vollständig enthalten."
    )


    print()


    print(

        "Wichtig: Der Postprocessor klassifiziert alte "
        "QX-Fälle NICHT automatisch zu Q6 oder Q7 um."
    )


    print(

        "Q6/Q7 müssen aus der aktualisierten eigentlichen "
        "Quellklassifikation stammen."
    )


    print()

    print(
        "=" * 78
    )


# ============================================================
# 15. PROGRAMMSTART
# ============================================================

if __name__ == "__main__":

    main()