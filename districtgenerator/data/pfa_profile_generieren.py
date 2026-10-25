from pathlib import Path
import json
import re

import numpy as np
import pandas as pd


# =============================================================================
# REALISTISCHEN STANDORT AUS EINER FERTIGEN PROFILGRUPPE GENERIEREN
# =============================================================================
#
# ZIEL
# ----
# NICHT alle Quellenblöcke einer Gruppe ausgeben.
#
# Stattdessen:
#
#   1. Einen real beobachteten Standort aus der fertigen Gruppe ziehen.
#   2. Damit gemeinsam übernehmen:
#        - Anzahl der Quellen
#        - Q-Typen Q1 ... Q7
#        - relative Größen der Quellen zueinander
#   3. Für jede Quelle ein eigenes 8760-Stunden-Profil erzeugen.
#   4. Zusätzlich alle Quellen zum 8760-Stunden-Standortprofil summieren.
#
#
# Beispiel:
#
#   gezogener Standort:
#
#       Quelle 1: Q1, 25 %
#       Quelle 2: Q4, 60 %
#       Quelle 3: Q7, 15 %
#
#   Rückgabe:
#
#       source_profiles.shape == (3, 8760)
#       q_types == ["Q1", "Q4", "Q7"]
#       site_profile.shape == (8760,)
#
#
# METHODISCH WICHTIG
# ------------------
# Der Standort wird standardmäßig GLEICHGEWICHTET aus den realen Standorten
# gezogen.
#
# Dadurch entspricht:
#
#     1 realer Standort = 1 mögliche Standortstruktur
#
# Große Standorte werden also NICHT nur deshalb häufiger gezogen, weil sie
# viel mehr Abwärme besitzen.
#
#
# ABSOLUTE STANDORTGRÖSSE
# ----------------------
# Zwei Modi sind möglich:
#
# A) TARGET_SITE_ANNUAL_HEAT_KWH = None
#
#    -> Jahreswärmemenge des gezogenen realen Standorts verwenden.
#
# B) TARGET_SITE_ANNUAL_HEAT_KWH = z. B. 10_000_000
#
#    -> dieselbe empirische Quellenstruktur / dieselben relativen Anteile
#       auf insgesamt 10 GWh/a skalieren.
#
#
# ZEITLICHE PROFILE
# -----------------
# Jede Quelle wird aus:
#
#     Jahreswärmemenge
#     + Betriebsprofil
#     + vollständigem 12-Monats-Saisonalitätsvektor
#
# auf 8760 Stunden verteilt.
#
# Die gemeldete Maximalleistung wird NICHT zur Skalierung verwendet.
#
#
# BETRIEBSSTUNDEN – MODELLANNAHME
# -------------------------------
# Die PFA-Daten geben typischerweise die Stunden pro Tag, aber nicht den
# tatsächlichen Schichtbeginn an.
#
# Deshalb wird aktuell angenommen:
#
#      8 h -> 06:00–14:00
#     12 h -> 06:00–18:00
#     16 h -> 06:00–22:00
#     20 h -> 02:00–22:00
#     24 h -> 00:00–24:00
#
# Diese Annahme ist unten zentral änderbar und wird in der Konsole ausgegeben.
#
#
# FEHLENDE BETRIEBSPROFILE / SAISONALITÄT
# ----------------------------------------
# Falls beim gezogenen Standort noch ein Attribut fehlt, wird ein realer
# Donorblock derselben Experimentgruppe gezogen.
#
# Reihenfolge:
#
#     1. gleiche Q-Klasse + Größenklasse + Maschinenfamilie
#     2. gleiche Q-Klasse + Größenklasse
#     3. gleiche Q-Klasse
#     4. gesamte Gruppe
#
# Kein Profil_WZ_Code wird als Bedingung verwendet.
#
#
# AUSGABE
# -------
# Pro generiertem Standort:
#
#     source_profiles_8760.npy
#         Matrix (n_Quellen, 8760)
#
#     site_profile_8760.npy
#         aufsummiertes Standortprofil (8760,)
#
#     site_profiles.npz
#         Quellenprofile + Q-Typen + IDs + Standortprofil
#
#     source_metadata.csv
#         Metadaten pro Quelle
#
#     hourly_index.csv
#
#
# PYTHON-RÜCKGABE
# ---------------
#
# result = generate_realistic_site(...)
#
# result["source_profiles"]
#     NumPy-Matrix (n_Quellen, 8760)
#
# result["q_types"]
#     z. B. array(["Q1", "Q4", "Q7"])
#
# result["site_profile"]
#     NumPy-Array (8760,)
#
# result["sources"]
#     Liste mit einem Dictionary je Standortquelle
#
#
# EXTERNE ÜBERGABE
# ----------------
# Der konkrete Übergabeblock an ein späteres anderes Modell ist ganz unten
# ABSICHTLICH auskommentiert.
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
# HIER DIE FERTIGE GRUPPE EINTRAGEN
# -----------------------------------------------------------------------------

TARGET_GROUP = "G"


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


# -----------------------------------------------------------------------------
# Zufall reproduzierbar machen.
# -----------------------------------------------------------------------------

RANDOM_SEED = 45


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

# Bei einem einzelnen Standort ist die vollständige Ausgabe meist noch
# handhabbar. Falls die Konsole zu groß wird:
#
#     PRINT_FULL_8760_ARRAYS = False
#
PRINT_FULL_8760_ARRAYS = False

# Bei False werden trotzdem die ersten und letzten Werte ausfgegeben.
PRINT_FIRST_N_HOURS = 48
PRINT_LAST_N_HOURS = 24


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

def choose_basis_site(
        sites,
        rng,
        used_site_ids=None,
):
    """
    Standardmäßig gleichgewichtete Ziehung über reale Standorte.

    Dadurch wird die Wahrscheinlichkeit NICHT mit der Wärmemenge gewichtet.
    """

    if used_site_ids is None:
        used_site_ids = set()

    if (
            FIXED_BASIS_SITE_ID
            is not None
    ):

        candidates = sites[
            sites[
                "Standortverbund_ID"
            ]
            .map(clean_string)
            .eq(
                clean_string(
                    FIXED_BASIS_SITE_ID
                )
            )
        ]

        if candidates.empty:

            raise ValueError(
                "FIXED_BASIS_SITE_ID wurde in sites nicht gefunden:\n"
                f"{FIXED_BASIS_SITE_ID}"
            )

        return candidates.iloc[0]

    candidates = sites.copy()

    if (
            N_SITES_TO_GENERATE
            <=
            len(
                candidates
            )
    ):

        not_used = candidates[
            ~candidates[
                "Standortverbund_ID"
            ]
            .map(clean_string)
            .isin(
                used_site_ids
            )
        ]

        if not not_used.empty:
            candidates = not_used

    chosen_position = int(
        rng.integers(
            0,
            len(
                candidates
            ),
        )
    )

    return candidates.iloc[
        chosen_position
    ]


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
    print()
    print("=" * 100)
    print(
        "MODELLANNAHMEN FÜR DIE 8760-STANDORTPROFILE"
    )
    print("=" * 100)

    print(
        f"Referenzjahr: {REFERENCE_YEAR}"
    )

    print(
        "Zeitauflösung: 1 Stunde"
    )

    print(
        "Einheit der Zeitreihen: kWh pro Stunde"
    )

    print()
    print(
        "Betriebsfenster:"
    )

    for hours, start in (
            STANDARD_START_HOUR_BY_DAILY_HOURS.items()
    ):

        end = (
                start
                +
                int(
                    hours
                )
        )

        if end > 24:
            end -= 24

        print(
            f"  {int(hours):>2} h/Tag "
            f"-> {start:02d}:00 bis {end:02d}:00"
        )

    print(
        f"  Sonderprofile starten standardmäßig um "
        f"{SPECIAL_PROFILE_DEFAULT_START_HOUR:02d}:00"
    )

    print()
    print(
        "5 Tage/Woche = Montag-Freitag"
    )

    print(
        "6 Tage/Woche = Montag-Samstag"
    )

    print(
        "7 Tage/Woche = Montag-Sonntag"
    )

    print()
    print(
        "Saisonalität: vollständiger empirischer 12-Monats-Vektor"
    )

    print(
        "Skalierung: ausschließlich über Jahreswärmemenge"
    )

    print(
        "Gemeldete Maximalleistung: nicht zur Profilskalierung verwendet"
    )

    print("=" * 100)


def print_site_summary(
        generated_site_id,
        structure,
        source_rows,
):
    if not PRINT_SITE_SUMMARY:
        return

    print()
    print("=" * 100)

    print(
        f"GENERIERTER STANDORT: {generated_site_id}"
    )

    print("=" * 100)

    print(
        f"Empirische Strukturvorlage: "
        f"{structure['basis_site_id']}"
    )

    print(
        f"Anzahl Quellenblöcke:       "
        f"{len(source_rows)}"
    )

    print(
        f"Empirische Jahreswärme:     "
        f"{structure['empirical_total_heat']:,.2f} kWh/a"
    )

    print(
        f"Generierte Jahreswärme:     "
        f"{structure['generated_total_heat']:,.2f} kWh/a"
    )

    print()
    print(
        "Quellenstruktur:"
    )

    for source_number, (_, row) in enumerate(
            source_rows.iterrows(),
            start=1,
    ):

        print(
            f"  Quelle {source_number:>2}: "
            f"{clean_string(row['Quellklasse_Code']):>2} | "
            f"Anteil {float(row['_empirical_share']):7.2%} | "
            f"Q_Jahr {float(row['_generated_heat']):,.2f} kWh/a"
        )

    print("=" * 100)


def print_source_profile(
        number,
        total,
        source,
):
    if not PRINT_EACH_SOURCE:
        return

    profile = source[
        "profile_kWh"
    ]

    print()
    print("-" * 100)

    print(
        f"STANDORTQUELLE {number}/{total}"
    )

    print(
        f"Q-Typ:                   "
        f"{source['Quellklasse_Code']}"
    )

    print(
        f"Generator_Block_ID:       "
        f"{source['Basis_Generator_Block_ID']}"
    )

    print(
        f"Anteil am Standort:       "
        f"{source['Anteil_am_Standort']:.2%}"
    )

    print(
        f"Jahreswärmemenge:         "
        f"{source['Waermemenge_kWh_a']:,.2f} kWh/a"
    )

    print(
        f"Temperatur:               "
        f"{source['Temperatur_C']} °C"
    )

    print(
        f"Betriebsprofil:           "
        f"{source['Betriebsprofil_Code']}"
    )

    print(
        f"Stunden/Tag:              "
        f"{source['Betriebsprofil_h_pro_Tag']}"
    )

    print(
        f"Tage/Woche:               "
        f"{source['Betriebsprofil_Tage_pro_Woche']}"
    )

    print(
        f"Startstunde:              "
        f"{source['Startstunde_Tag']:02d}:00"
    )

    print(
        f"Aktive Stunden/Jahr:      "
        f"{source['Aktive_Stunden_Jahr']:,}"
    )

    print(
        f"Sommerfaktor:             "
        f"{source['Saisonfaktor_Sommer']}"
    )

    print(
        f"Winterfaktor:             "
        f"{source['Saisonfaktor_Winter']}"
    )

    print(
        f"Saison aktive Monate:     "
        f"{source['Saison_Aktive_Monate']}"
    )

    print(
        f"Saisonkonzentration 0..1: "
        f"{source['Saison_Konzentration_0_1']}"
    )

    print(
        f"Betriebsprofil imputiert: "
        f"{source['Betriebsprofil_imputiert']}"
    )

    print(
        f"Saisonalität imputiert:   "
        f"{source['Saisonalitaet_imputiert']}"
    )

    if source[
        "Betriebsprofil_imputiert"
    ]:

        print(
            f"Betriebsprofil-Donor:     "
            f"{source['Betriebsprofil_Donor_ID']}"
        )

        print(
            f"Betriebsprofil-Donorlevel:"
            f" {source['Betriebsprofil_Donor_Ebene']}"
        )

    if source[
        "Saisonalitaet_imputiert"
    ]:

        print(
            f"Saisonalitäts-Donor:      "
            f"{source['Saisonalitaet_Donor_ID']}"
        )

        print(
            f"Saisonalitäts-Donorlevel: "
            f"{source['Saisonalitaet_Donor_Ebene']}"
        )

    print()
    print(
        "12 Monatsfaktoren:"
    )

    for month in MONTH_CODES:

        print(
            f"  {month}: "
            f"{source['Saisonfaktoren'][month]:.6f}"
        )

    print()
    print(
        "Zeitreihe der Quelle:"
    )

    print(
        f"  Form:        {profile.shape}"
    )

    print(
        f"  Summe:       {profile.sum():,.6f} kWh"
    )

    print(
        f"  Maximum:     {profile.max():,.6f} kWh/h"
    )

    print(
        f"  aktive h:    {int((profile > 0).sum()):,}"
    )

    with np.printoptions(
            threshold=(
                    np.inf
                    if PRINT_FULL_8760_ARRAYS
                    else 100
            ),
            edgeitems=12,
            linewidth=200,
            precision=4,
            suppress=True,
    ):

        print(
            profile
        )

    if not PRINT_FULL_8760_ARRAYS:

        print()
        print(
            f"Erste {PRINT_FIRST_N_HOURS} Stunden:"
        )

        print(
            profile[
            :PRINT_FIRST_N_HOURS
            ]
        )

        print()
        print(
            f"Letzte {PRINT_LAST_N_HOURS} Stunden:"
        )

        print(
            profile[
            -PRINT_LAST_N_HOURS:
            ]
        )


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

    print()
    print("=" * 100)

    print(
        f"GESAMTPROFIL STANDORT {generated_site_id}"
    )

    print("=" * 100)

    print(
        f"Q-Typen:              {q_types.tolist()}"
    )

    print(
        f"Quellenmatrix:         {source_profiles.shape}"
    )

    print(
        f"Standortprofil:        {site_profile.shape}"
    )

    print(
        f"Jahreswärme Standort:  {site_profile.sum():,.6f} kWh"
    )

    print(
        f"Max. Stundenwert:      {site_profile.max():,.6f} kWh/h"
    )

    print()
    print(
        "8760-Zeitreihe des gesamten Standorts:"
    )

    with np.printoptions(
            threshold=(
                    np.inf
                    if PRINT_FULL_8760_ARRAYS
                    else 100
            ),
            edgeitems=12,
            linewidth=200,
            precision=4,
            suppress=True,
    ):

        print(
            site_profile
        )

    print("=" * 100)

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

        "random_seed":
            RANDOM_SEED,

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
        group_id,
):
    (
        input_folder,
        sites,
        blocks,
        donors,
    ) = load_group_data(
        group_id
    )

    if sites.empty:
        raise ValueError(
            f"{group_id}: sites ist leer."
        )

    if blocks.empty:
        raise ValueError(
            f"{group_id}: source_blocks ist leer."
        )

    # Nur gültige Standorte.
    sites = sites.copy()

    if (
            "Standortverbund_ID"
            not in sites.columns
    ):
        raise ValueError(
            "sites enthält keine Spalte Standortverbund_ID."
        )

    required_block_columns = [
        "Generator_Block_ID",
        "Standortverbund_ID",
        "Quellklasse_Code",
        "Waermemenge_Block_kWh_a",
    ]

    missing_columns = [
        column
        for column
        in required_block_columns
        if column not in blocks.columns
    ]

    if missing_columns:
        raise ValueError(
            "source_blocks fehlen Pflichtspalten:\n"
            + "\n".join(
                missing_columns
            )
        )

    blocks = blocks[
        blocks[
            "Quellklasse_Code"
        ]
        .map(clean_string)
        .isin(
            VALID_Q_TYPES
        )
    ].copy()

    time_index = build_reference_time_index(
        REFERENCE_YEAR
    )

    rng = np.random.default_rng(
        RANDOM_SEED
    )

    print_model_assumptions()

    results = []
    used_site_ids = set()

    for site_number in range(
            1,
            N_SITES_TO_GENERATE + 1,
    ):

        result = generate_one_site(
            group_id=
            group_id,

            site_number=
            site_number,

            sites=
            sites,

            blocks=
            blocks,

            donors=
            donors,

            time_index=
            time_index,

            rng=
            rng,

            used_site_ids=
            used_site_ids,
        )

        save_site_result(
            group_id=
            group_id,

            result=
            result,

            time_index=
            time_index,
        )

        results.append(
            result
        )

    print()
    print("=" * 100)
    print(
        "STANDORTGENERIERUNG ABGESCHLOSSEN"
    )
    print("=" * 100)

    print(
        f"Gruppe:                {group_id}"
    )

    print(
        f"Generierte Standorte:  {len(results)}"
    )

    for result in results:

        print()
        print(
            f"{result['generated_site_id']}: "
            f"{len(result['q_types'])} Quellen | "
            f"Q-Typen {result['q_types'].tolist()} | "
            f"{result['generated_site_heat_kWh_a']:,.2f} kWh/a"
        )

    print("=" * 100)

    return {
        "group_id":
            group_id,

        "time_index":
            time_index,

        "sites":
            results,
    }


# =============================================================================
# 23. HAUPTPROGRAMM
# =============================================================================

def main():

    result = generate_realistic_sites(
        TARGET_GROUP
    )

    # ========================================================================
    # BEQUEMER ZUGRIFF BEI N_SITES_TO_GENERATE = 1
    # ========================================================================

    if len(
            result[
                "sites"
            ]
    ) == 1:

        site = result[
            "sites"
        ][0]

        source_profiles = site[
            "source_profiles"
        ]

        q_types = site[
            "q_types"
        ]

        site_profile = site[
            "site_profile"
        ]

        source_ids = site[
            "source_ids"
        ]

        # --------------------------------------------------------------------
        # SPÄTERE ÜBERGABE AN DAS NÄCHSTE MODELL / DEN EXTERNEN GENERATOR
        #
        # ABSICHTLICH NOCH AUSKOMMENTIERT.
        # --------------------------------------------------------------------
        #
        # generator_payload = {
        #     "source_profiles_8760": source_profiles,
        #     "source_types": q_types,
        #     "source_ids": source_ids,
        #     "site_profile_8760": site_profile,
        # }
        #
        # external_generator.receive_site(
        #     generator_payload
        # )
        #
        # --------------------------------------------------------------------


if __name__ == "__main__":
    main()
