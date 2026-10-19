from pathlib import Path
import hashlib
import re
import unicodedata

import pandas as pd


# ============================================================
# 1. GRUNDKONFIGURATION
# ============================================================

# ------------------------------------------------------------
# Eingabedatei
# ------------------------------------------------------------
# Excel-Datei mit der vollständigen PFA-Datentabelle.
#
# Falls Skript und Excel-Datei im selben Ordner liegen,
# reicht der Dateiname.
# ------------------------------------------------------------

INPUT_FILE = Path(
    "pfa_datentabelle_excel.xlsx"
)


# ------------------------------------------------------------
# Relevantes Tabellenblatt
# ------------------------------------------------------------

SHEET_NAME = "Abwärmepotentiale"


# ------------------------------------------------------------
# Ausgabeordner
# ------------------------------------------------------------

OUTPUT_DIR = Path("WZ2025_Vorbereitung")

BATCH_DIR = OUTPUT_DIR / "Batches"


# ------------------------------------------------------------
# Anzahl eindeutiger Standorte pro KI-Batch
# ------------------------------------------------------------

BATCH_SIZE = 100


# ============================================================
# 2. HILFSFUNKTIONEN
# ============================================================


def clean_column_name(column_name: str) -> str:
    """
    Bereinigt die Spaltennamen aus der Excel-Datei.

    Hintergrund:
    - Einige Spaltennamen enthalten Zeilenumbrüche.
    - Manche Überschriften enthalten mehrere Leerzeichen.

    Beispiel:
        "Unternehmens-\\nID"
    wird zu:
        "Unternehmens- ID"

    Die Daten selbst werden dadurch nicht verändert.
    """

    text = str(column_name)

    # Zeilenumbrüche entfernen
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    # Mehrfache Leerzeichen zusammenfassen
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_key_value(value) -> str:
    """
    Normalisiert Werte ausschließlich für die Bildung
    des internen Standort-Schlüssels.

    Die sichtbaren Originalwerte bleiben unverändert.

    Normalisierung:
    - fehlende Werte -> leerer String
    - Unicode vereinheitlichen
    - unsichtbare Zeichen entfernen
    - geschützte Leerzeichen ersetzen
    - Mehrfach-Leerzeichen reduzieren
    - Groß-/Kleinschreibung ignorieren

    Bewusst NICHT gemacht:
    - kein Fuzzy Matching
    - keine automatische Adresskorrektur
    - kein "Straße" -> "Str."
    - keine Tippfehlerkorrektur

    Dadurch werden nur relativ sichere Dubletten
    zusammengeführt.
    """

    if pd.isna(value):
        return ""

    text = str(value)

    # Unicode vereinheitlichen
    text = unicodedata.normalize("NFKC", text)

    # Zero-Width-Zeichen entfernen
    text = text.replace("\u200b", "")

    # Geschützte Leerzeichen ersetzen
    text = text.replace("\xa0", " ")

    # Mehrfache Leerzeichen reduzieren
    text = re.sub(r"\s+", " ", text)

    # Außenliegende Leerzeichen entfernen
    text = text.strip()

    # Groß-/Kleinschreibung ignorieren
    text = text.casefold()

    return text


def most_common_nonempty(series: pd.Series) -> str:
    """
    Liefert den häufigsten nicht-leeren Originalwert
    innerhalb einer Standortgruppe.

    Beispiel:
        "Firma GmbH"
        "Firma GmbH"
        "Firma GmbH "

    -> "Firma GmbH"

    Sinnvoll, falls Originaldaten leichte Unterschiede
    oder einzelne leere Felder enthalten.
    """

    values = (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )

    values = values[
        values != ""
        ]

    if values.empty:
        return ""

    return values.value_counts().index[0]


def join_unique(series: pd.Series) -> str:
    """
    Fügt alle unterschiedlichen nicht-leeren Werte
    einer Gruppe zusammen.

    Reihenfolge:
    - Reihenfolge des ersten Auftretens bleibt erhalten.

    Beispiel:
        1001
        1001
        1002
        1003

    wird zu:
        "1001 | 1002 | 1003"
    """

    values = []
    seen = set()

    for value in series:

        if pd.isna(value):
            continue

        value = str(value).strip()

        if not value:
            continue

        if value not in seen:

            values.append(value)
            seen.add(value)

    return " | ".join(values)


def join_examples(
        series: pd.Series,
        max_items: int = 10,
        max_length_per_item: int = 400,
) -> str:
    """
    Erstellt eine kompakte Zusammenfassung verschiedener
    Textangaben eines Standortes.

    Verwendung beispielsweise für:
    - Namen der Abwärmepotentiale
    - ergänzende Informationen
    - weitere Hinweise

    Warum begrenzen?
    Manche Standorte besitzen sehr viele Abwärmezeilen.
    Würden alle Freitexte in die KI-Batches übernommen,
    würden einzelne Zellen extrem groß.

    Deshalb:
    - maximal max_items verschiedene Angaben
    - pro Angabe maximal max_length_per_item Zeichen
    - zusätzliche Angaben werden lediglich gezählt
    """

    unique_values = []
    seen = set()

    for value in series:

        if pd.isna(value):
            continue

        value = str(value).strip()

        if not value:
            continue

        if value in seen:
            continue

        seen.add(value)

        # Sehr lange Einzeltexte begrenzen
        if len(value) > max_length_per_item:

            value = (
                    value[:max_length_per_item]
                    + " …"
            )

        unique_values.append(value)

    total_unique = len(unique_values)

    shown_values = unique_values[:max_items]

    result = " | ".join(shown_values)

    # Hinweis auf weitere vorhandene Informationen
    if total_unique > max_items:

        result += (
            f" | … "
            f"(+{total_unique - max_items} weitere)"
        )

    return result


def create_classification_id(key: str) -> str:
    """
    Erstellt eine stabile technische ID für genau eine
    Unternehmens-/Standortkombination.

    Beispiel:
        ST_4F82A1C97B21

    Grundlage ist der normalisierte Standortschlüssel.

    Vorteil:
    Die ID ist unabhängig davon,
    - an welcher Stelle der Standort in Excel steht,
    - wie die Tabelle sortiert wird,
    - welchem 100er-Batch er zugeordnet wird.

    SHA-1 wird hier NICHT aus Sicherheitsgründen verwendet,
    sondern lediglich zur Bildung eines stabilen kurzen Hashes.
    """

    digest = hashlib.sha1(
        key.encode("utf-8")
    ).hexdigest()[:12].upper()

    return f"ST_{digest}"


# ============================================================
# 3. EXCEL-DATEI EINLESEN
# ============================================================

# ------------------------------------------------------------
# Besonderheit der PFA-Datei:
#
# Excel-Zeile 1:
#     übergeordnete Themenüberschriften
#
# Excel-Zeile 2:
#     tatsächliche Spaltennamen
#
# Deshalb:
#     header=1
#
# Pandas zählt ab 0:
#     header=1 = zweite Excel-Zeile
# ------------------------------------------------------------

df = pd.read_excel(
    INPUT_FILE,
    sheet_name=SHEET_NAME,
    header=1,
    dtype=str,
    keep_default_na=False,
)


print()
print("=" * 60)
print("DATEI EINGELESEN")
print("=" * 60)

print(
    f"Originalzeilen: {len(df):,}"
)


# ============================================================
# 4. SPALTENNAMEN BEREINIGEN
# ============================================================

df.columns = [
    clean_column_name(column)
    for column in df.columns
]


# ------------------------------------------------------------
# ID-Spalten verständlicher benennen
# ------------------------------------------------------------

df = df.rename(
    columns={
        "Unternehmens- ID":
            "Unternehmens_ID",

        "Melde- ID":
            "Melde_ID",
    }
)


# ============================================================
# 5. BENÖTIGTE SPALTEN PRÜFEN
# ============================================================

required_columns = [

    "Unternehmens_ID",
    "Melde_ID",

    "Firmenname",
    "Standortname",

    "Straße und Hausnummer",
    "PLZ",
    "Ort",

    "Name des Abwärmepotentials",

    "Ergänzende Informationen zum Abwärmepotential",

    "Weitere Hinweise",
]


missing_columns = [

    column
    for column in required_columns

    if column not in df.columns
]


if missing_columns:

    raise ValueError(
        "\nFolgende benötigte Spalten fehlen "
        "in der Excel-Datei:\n\n"
        + "\n".join(
            f"- {column}"
            for column in missing_columns
        )
    )


# ============================================================
# 6. ORIGINALDATENSATZ-ID VERGEBEN
# ============================================================

# ------------------------------------------------------------
# Jede einzelne Originalzeile bekommt eine einfache
# fortlaufende numerische ID:
#
# 1
# 2
# 3
# ...
#
# Diese ID ist unabhängig von der Melde-ID.
# ------------------------------------------------------------

df["Originaldatensatz_ID"] = range(
    1,
    len(df) + 1,
    )


# ------------------------------------------------------------
# Zusätzlich speichern wir die tatsächliche Excel-Zeilennummer.
#
# Da:
# Zeile 1 = Themenüberschrift
# Zeile 2 = Spaltenüberschrift
# Zeile 3 = erster Datensatz
#
# gilt:
# DataFrame-Index 0 -> Excel-Zeile 3
# ------------------------------------------------------------

df["Original_Excel_Zeile"] = (
        df.index + 3
)


# ============================================================
# 7. NORMALISIERTE SCHLÜSSELFELDER ERZEUGEN
# ============================================================

# ------------------------------------------------------------
# Diese Spalten dienen ausschließlich intern zur
# Standorterkennung.
#
# Die Originalwerte werden NICHT überschrieben.
# ------------------------------------------------------------

df["_company_key"] = (
    df["Unternehmens_ID"]
    .map(normalize_key_value)
)

df["_site_name_key"] = (
    df["Standortname"]
    .map(normalize_key_value)
)

df["_street_key"] = (
    df["Straße und Hausnummer"]
    .map(normalize_key_value)
)

df["_postcode_key"] = (
    df["PLZ"]
    .map(normalize_key_value)
)

df["_city_key"] = (
    df["Ort"]
    .map(normalize_key_value)
)


# ============================================================
# 8. STANDORTSCHLÜSSEL DEFINIEREN
# ============================================================

# ------------------------------------------------------------
# Ein klassifikationsrelevanter Standort wird definiert durch:
#
# Unternehmens-ID
# +
# Standortname
# +
# Straße und Hausnummer
# +
# PLZ
# +
# Ort
#
# Warum so konservativ?
#
# Wir wollen vermeiden, dass unterschiedliche Betriebsteile
# oder Standorte versehentlich zusammengeführt werden.
#
# Eine spätere kontrollierte Zusammenführung ist leichter,
# als versehentlich zusammengeführte Fälle wieder zu trennen.
# ------------------------------------------------------------

df["_classification_key"] = (

        df["_company_key"]
        + "||"

        + df["_site_name_key"]
        + "||"

        + df["_street_key"]
        + "||"

        + df["_postcode_key"]
        + "||"

        + df["_city_key"]
)


# ============================================================
# 9. KLASSIFIKATIONS-ID ERZEUGEN
# ============================================================

df["Klassifikations_ID"] = (

    df["_classification_key"]
    .map(create_classification_id)
)


# ============================================================
# 10. MAPPING AUF ORIGINALDATEN ERZEUGEN
# ============================================================

# ------------------------------------------------------------
# Dieses Blatt ist später die wichtigste Verbindung zwischen:
#
# WZ-Klassifikation
#
# und
#
# den ursprünglichen Abwärmedatensätzen.
#
# Es bleibt EINE ZEILE PRO ORIGINALDATENSATZ erhalten.
# ------------------------------------------------------------

mapping_df = df[
    [
        "Klassifikations_ID",

        "Originaldatensatz_ID",
        "Original_Excel_Zeile",

        "Unternehmens_ID",
        "Melde_ID",

        "Firmenname",
        "Standortname",

        "Straße und Hausnummer",
        "PLZ",
        "Ort",

        "Name des Abwärmepotentials",
    ]
].copy()


# ============================================================
# 11. EINDEUTIGE STANDORTE AGGREGIEREN
# ============================================================

grouped = df.groupby(
    "Klassifikations_ID",
    sort=False,
)


unique_sites = grouped.agg(

    # ========================================================
    # Unternehmensinformationen
    # ========================================================

    Unternehmens_ID=(
        "Unternehmens_ID",
        most_common_nonempty,
    ),

    Firmenname=(
        "Firmenname",
        most_common_nonempty,
    ),

    # Falls verschiedene Schreibweisen vorkommen
    Firmenname_Varianten=(
        "Firmenname",
        join_unique,
    ),


    # ========================================================
    # Standortinformationen
    # ========================================================

    Standortname=(
        "Standortname",
        most_common_nonempty,
    ),

    Strasse_Hausnummer=(
        "Straße und Hausnummer",
        most_common_nonempty,
    ),

    PLZ=(
        "PLZ",
        most_common_nonempty,
    ),

    Ort=(
        "Ort",
        most_common_nonempty,
    ),


    # ========================================================
    # Rückverweise
    # ========================================================

    Melde_IDs=(
        "Melde_ID",
        join_unique,
    ),

    Originaldatensatz_IDs=(
        "Originaldatensatz_ID",
        lambda s: " | ".join(
            s.astype(str)
        ),
    ),

    Original_Excel_Zeilen=(
        "Original_Excel_Zeile",
        lambda s: " | ".join(
            s.astype(str)
        ),
    ),


    # ========================================================
    # Informationen für die KI-Klassifikation
    # ========================================================

    Abwaermepotentiale_Beispiele=(
        "Name des Abwärmepotentials",
        lambda s: join_examples(
            s,
            max_items=12,
            max_length_per_item=300,
        ),
    ),

    Ergaenzende_Informationen_Beispiele=(
        "Ergänzende Informationen zum Abwärmepotential",
        lambda s: join_examples(
            s,
            max_items=5,
            max_length_per_item=400,
        ),
    ),

    Weitere_Hinweise_Beispiele=(
        "Weitere Hinweise",
        lambda s: join_examples(
            s,
            max_items=5,
            max_length_per_item=400,
        ),
    ),

).reset_index()


# ============================================================
# 12. ANZAHL ORIGINALZEILEN PRO STANDORT
# ============================================================

row_counts = (

    grouped
    .size()
    .rename("Anzahl_Originalzeilen")
    .reset_index()
)


unique_sites = unique_sites.merge(
    row_counts,
    on="Klassifikations_ID",
    how="left",
)


# ============================================================
# 13. KLASSIFIKATIONSSPALTEN FÜR DIE KI
# ============================================================

# ------------------------------------------------------------
# Neue empfohlene Strategie:
#
# Standardziel = WZ-GRUPPE
#
# Keine standardmäßige Klassifikation auf:
# - Klasse
# - Unterklasse
#
# Dadurch wird die Klassifikation wesentlich schneller
# und bleibt für die späteren Abwärmeprofile ausreichend.
# ------------------------------------------------------------

classification_columns = [

    # --------------------------------------------------------
    # Wichtigste Ergebnisfelder
    # --------------------------------------------------------

    "WZ_Gruppe_Code",

    "WZ_Gruppe_Bezeichnung",


    # --------------------------------------------------------
    # Falls die Gruppe NICHT sicher bestimmbar ist
    # --------------------------------------------------------

    "WZ_Sichere_Ebene",

    "WZ_Sicherer_Code",

    "WZ_Sichere_Bezeichnung",


    # --------------------------------------------------------
    # Kurze Beschreibung der tatsächlichen Standorttätigkeit
    # --------------------------------------------------------

    "Standorttaetigkeit_kurz",


    # --------------------------------------------------------
    # Kurze Begründung
    # --------------------------------------------------------

    "WZ_Begruendung",


    # --------------------------------------------------------
    # Recherchequellen
    # --------------------------------------------------------

    "Recherchequelle_1",

    "Recherchequelle_2",


    # --------------------------------------------------------
    # hoch / mittel / gering
    # --------------------------------------------------------

    "Konfidenz",
]


# ------------------------------------------------------------
# Leere Klassifikationsspalten hinzufügen
# ------------------------------------------------------------

for column in classification_columns:

    unique_sites[column] = ""


# ============================================================
# 14. SPALTENREIHENFOLGE DER MASTERDATEI
# ============================================================

master_columns = [

                     # --------------------------------------------------------
                     # Technische ID
                     # --------------------------------------------------------

                     "Klassifikations_ID",


                     # --------------------------------------------------------
                     # Unternehmen
                     # --------------------------------------------------------

                     "Unternehmens_ID",

                     "Firmenname",

                     "Firmenname_Varianten",


                     # --------------------------------------------------------
                     # Standort
                     # --------------------------------------------------------

                     "Standortname",

                     "Strasse_Hausnummer",

                     "PLZ",

                     "Ort",


                     # --------------------------------------------------------
                     # Rückverweise
                     # --------------------------------------------------------

                     "Melde_IDs",

                     "Originaldatensatz_IDs",

                     "Original_Excel_Zeilen",

                     "Anzahl_Originalzeilen",


                     # --------------------------------------------------------
                     # Kontextinformationen
                     # --------------------------------------------------------

                     "Abwaermepotentiale_Beispiele",

                     "Ergaenzende_Informationen_Beispiele",

                     "Weitere_Hinweise_Beispiele",

                 ] + classification_columns


unique_sites = unique_sites[
    master_columns
]


# ============================================================
# 15. STANDORTE FÜR EFFIZIENTERE KI-BATCHES SORTIEREN
# ============================================================

# ------------------------------------------------------------
# Sehr wichtig für die spätere KI-Klassifikation.
#
# Standorte desselben Unternehmens werden möglichst
# direkt hintereinander angeordnet.
#
# Vorteile:
# - Unternehmensinformationen müssen weniger oft recherchiert
#   werden.
# - Erkenntnisse können innerhalb eines Batches wiederverwendet
#   werden.
# - mehrere Werke desselben Unternehmens landen mit höherer
#   Wahrscheinlichkeit im selben 100er-Batch.
# ------------------------------------------------------------

unique_sites = (

    unique_sites
    .sort_values(
        by=[
            "Unternehmens_ID",
            "PLZ",
            "Ort",
            "Standortname",
        ],
        kind="stable",
        na_position="last",
    )
    .reset_index(drop=True)
)


# ============================================================
# 16. QUALITÄTSCHECK:
#     GLEICHE FIRMA + GLEICHE ADRESSE
#     ABER MEHRERE STANDORTNAMEN
# ============================================================

# ------------------------------------------------------------
# Solche Fälle werden NICHT automatisch zusammengeführt.
#
# Beispiel:
#
# Unternehmen 123
# Musterstraße 1
#
# Standortname:
#   "Werk 1"
#
# und
#
# Standortname:
#   "Energiezentrale"
#
# könnten tatsächlich unterschiedliche klassifikationsrelevante
# Betriebsteile sein.
#
# Deshalb werden diese Fälle nur separat ausgegeben.
# ------------------------------------------------------------

qc_address = (

    df
    .groupby(
        [
            "Unternehmens_ID",
            "_street_key",
            "_postcode_key",
            "_city_key",
        ]
    )
    .agg(

        Firmenname=(
            "Firmenname",
            most_common_nonempty,
        ),

        Standortnamen=(
            "Standortname",
            join_unique,
        ),

        Anzahl_Standortnamen=(
            "Standortname",
            lambda s: len(
                {
                    normalize_key_value(x)
                    for x in s
                    if normalize_key_value(x)
                }
            ),
        ),

    )
    .reset_index()
)


qc_address = qc_address[
    qc_address["Anzahl_Standortnamen"] > 1
    ].copy()


# ============================================================
# 17. QUALITÄTSCHECK:
#     GLEICHER STANDORTNAME
#     ABER MEHRERE ADRESSEN
# ============================================================

df["_address_display"] = (

        df["Straße und Hausnummer"]
        + ", "
        + df["PLZ"]
        + " "
        + df["Ort"]
)


qc_site_name = (

    df
    .groupby(
        [
            "Unternehmens_ID",
            "_site_name_key",
        ]
    )
    .agg(

        Firmenname=(
            "Firmenname",
            most_common_nonempty,
        ),

        Standortname=(
            "Standortname",
            most_common_nonempty,
        ),

        Adressen=(
            "_address_display",
            join_unique,
        ),

        Anzahl_Adressen=(
            "_address_display",
            lambda s: len(
                {
                    str(x).strip()
                    for x in s
                    if str(x).strip()
                }
            ),
        ),

    )
    .reset_index()
)


qc_site_name = qc_site_name[
    qc_site_name["Anzahl_Adressen"] > 1
    ].copy()


# ============================================================
# 18. WEITERE QUALITÄTSCHECKS
# ============================================================

# ------------------------------------------------------------
# Fehlende Unternehmens-ID
# ------------------------------------------------------------

qc_missing_company_id = df[

    df["Unternehmens_ID"]
    .astype(str)
    .str.strip()
    .eq("")

].copy()


# ------------------------------------------------------------
# Fehlende Standortadresse
# ------------------------------------------------------------

qc_missing_address = df[

    (
        df["Straße und Hausnummer"]
        .astype(str)
        .str.strip()
        .eq("")
    )

    &

    (
        df["PLZ"]
        .astype(str)
        .str.strip()
        .eq("")
    )

    &

    (
        df["Ort"]
        .astype(str)
        .str.strip()
        .eq("")
    )

    ].copy()


# ============================================================
# 19. HASH-KOLLISIONEN PRÜFEN
# ============================================================

# ------------------------------------------------------------
# Da wir die Klassifikations-ID aus einem verkürzten Hash
# erzeugen, prüfen wir sicherheitshalber, dass nicht zwei
# unterschiedliche Standortschlüssel denselben Hash erhalten.
# ------------------------------------------------------------

hash_check = (

    df[
        [
            "Klassifikations_ID",
            "_classification_key",
        ]
    ]
    .drop_duplicates()
)


collision_check = (

    hash_check
    .groupby("Klassifikations_ID")[
        "_classification_key"
    ]
    .nunique()
)


hash_collisions = collision_check[
    collision_check > 1
    ]


if not hash_collisions.empty:

    raise RuntimeError(
        "Es wurde eine Hash-Kollision bei "
        "der Klassifikations_ID gefunden."
    )


# ============================================================
# 20. AUSGABEORDNER ERZEUGEN
# ============================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

BATCH_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 21. MASTERDATEI SPEICHERN
# ============================================================

MASTER_FILE = (

        OUTPUT_DIR
        / "WZ2025_Standorte_Master.xlsx"
)


with pd.ExcelWriter(
        MASTER_FILE,
        engine="openpyxl",
) as writer:

    # --------------------------------------------------------
    # Blatt 1:
    # ein Eintrag je klassifikationsrelevantem Standort
    # --------------------------------------------------------

    unique_sites.to_excel(
        writer,
        sheet_name="Standorte",
        index=False,
    )


    # --------------------------------------------------------
    # Blatt 2:
    # vollständiges Mapping auf alle Originalzeilen
    # --------------------------------------------------------

    mapping_df.to_excel(
        writer,
        sheet_name="Mapping_Originaldaten",
        index=False,
    )


    # --------------------------------------------------------
    # Blatt 3:
    # gleiche Firmenadresse, mehrere Standortnamen
    # --------------------------------------------------------

    qc_address.to_excel(
        writer,
        sheet_name="QC_Adresse_mehrere_Namen",
        index=False,
    )


    # --------------------------------------------------------
    # Blatt 4:
    # gleicher Standortname, mehrere Adressen
    # --------------------------------------------------------

    qc_site_name.to_excel(
        writer,
        sheet_name="QC_Name_mehrere_Adressen",
        index=False,
    )


    # --------------------------------------------------------
    # Blatt 5:
    # fehlende Unternehmens-IDs
    # --------------------------------------------------------

    qc_missing_company_id.to_excel(
        writer,
        sheet_name="QC_Fehlende_UnternehmensID",
        index=False,
    )


    # --------------------------------------------------------
    # Blatt 6:
    # vollständig fehlende Standortadresse
    # --------------------------------------------------------

    qc_missing_address.to_excel(
        writer,
        sheet_name="QC_Fehlende_Adresse",
        index=False,
    )


# ============================================================
# 22. SPALTEN FÜR DIE KI-BATCHES
# ============================================================

# ------------------------------------------------------------
# Die KI bekommt bewusst NICHT alle Informationen aus der
# Masterdatei.
#
# Ziel:
# möglichst kompakte, aber ausreichend informative Batches.
# ------------------------------------------------------------

batch_columns = [

                    # ========================================================
                    # Eindeutiger technischer Schlüssel
                    # ========================================================

                    "Klassifikations_ID",


                    # ========================================================
                    # Unternehmensinformationen
                    # ========================================================

                    "Unternehmens_ID",

                    "Firmenname",

                    "Firmenname_Varianten",


                    # ========================================================
                    # Standortinformationen
                    # ========================================================

                    "Standortname",

                    "Strasse_Hausnummer",

                    "PLZ",

                    "Ort",


                    # ========================================================
                    # Rückverweise
                    # ========================================================

                    "Melde_IDs",

                    "Originaldatensatz_IDs",

                    "Anzahl_Originalzeilen",


                    # ========================================================
                    # Informationen über Prozesse / Abwärme
                    # ========================================================

                    "Abwaermepotentiale_Beispiele",

                    "Ergaenzende_Informationen_Beispiele",

                    "Weitere_Hinweise_Beispiele",


                    # ========================================================
                    # Von der KI auszufüllende Felder
                    # ========================================================

                ] + classification_columns


# ============================================================
# 23. KI-BATCHES ERZEUGEN
# ============================================================

number_of_batches = (

                            len(unique_sites)
                            + BATCH_SIZE
                            - 1

                    ) // BATCH_SIZE


for batch_number, start in enumerate(

        range(
            0,
            len(unique_sites),
            BATCH_SIZE,
        ),

        start=1,
):

    # --------------------------------------------------------
    # Maximal BATCH_SIZE Standorte auswählen
    # --------------------------------------------------------

    batch = (

        unique_sites
        .iloc[
        start:start + BATCH_SIZE
        ][batch_columns]
        .copy()
    )


    # --------------------------------------------------------
    # Batchnummer zusätzlich eintragen
    # --------------------------------------------------------
    # Kann später hilfreich sein, wenn klassifizierte Dateien
    # wieder zusammengeführt werden.
    # --------------------------------------------------------

    batch.insert(
        0,
        "Batch_ID",
        f"BATCH_{batch_number:03d}",
    )


    # --------------------------------------------------------
    # Dateiname
    # --------------------------------------------------------

    batch_file = (

            BATCH_DIR
            / (
                f"WZ2025_Batch_"
                f"{batch_number:03d}.xlsx"
            )
    )


    # --------------------------------------------------------
    # Excel-Datei schreiben
    # --------------------------------------------------------

    batch.to_excel(
        batch_file,
        sheet_name="Standorte",
        index=False,
        engine="openpyxl",
    )


# ============================================================
# 24. PLAUSIBILITÄTSCHECKS
# ============================================================

# ------------------------------------------------------------
# Anzahl Mapping-Zeilen muss exakt der Anzahl der
# Originalzeilen entsprechen.
# ------------------------------------------------------------

assert len(mapping_df) == len(df), (

    "Fehler: Nicht alle Originalzeilen befinden sich "
    "im Mapping."
)


# ------------------------------------------------------------
# Originaldatensatz_ID muss eindeutig sein.
# ------------------------------------------------------------

assert mapping_df[
    "Originaldatensatz_ID"
].is_unique, (

    "Fehler: Originaldatensatz_ID ist nicht eindeutig."
)


# ------------------------------------------------------------
# Klassifikations_ID muss in der Standorttabelle eindeutig sein.
# ------------------------------------------------------------

assert unique_sites[
    "Klassifikations_ID"
].is_unique, (

    "Fehler: Klassifikations_ID ist nicht eindeutig."
)


# ------------------------------------------------------------
# Jede Originalzeile muss eine Klassifikations-ID besitzen.
# ------------------------------------------------------------

assert mapping_df[
    "Klassifikations_ID"
].ne("").all(), (

    "Fehler: Mindestens eine Originalzeile besitzt "
    "keine Klassifikations_ID."
)


# ============================================================
# 25. ZUSAMMENFASSUNG AUSGEBEN
# ============================================================

print()
print("=" * 60)
print("WZ-2025 VORBEREITUNG ABGESCHLOSSEN")
print("=" * 60)

print()

print(
    f"Originale Abwärmezeilen: "
    f"{len(df):,}"
)

print(
    f"Eindeutige Unternehmens-/"
    f"Standortkombinationen: "
    f"{len(unique_sites):,}"
)

print(
    f"Unternehmen: "
    f"{unique_sites['Unternehmens_ID'].nunique():,}"
)

print(
    f"Erzeugte KI-Batches: "
    f"{number_of_batches:,}"
)

print(
    f"Maximale Batchgröße: "
    f"{BATCH_SIZE}"
)

print()

print(
    "Qualitätskontrollen:"
)

print(
    f"- gleiche Adresse / mehrere Standortnamen: "
    f"{len(qc_address):,}"
)

print(
    f"- gleicher Standortname / mehrere Adressen: "
    f"{len(qc_site_name):,}"
)

print(
    f"- Zeilen ohne Unternehmens-ID: "
    f"{len(qc_missing_company_id):,}"
)

print(
    f"- Zeilen ohne Standortadresse: "
    f"{len(qc_missing_address):,}"
)

print()

print(
    f"Masterdatei:\n"
    f"{MASTER_FILE}"
)

print()

print(
    f"Batchordner:\n"
    f"{BATCH_DIR}"
)

print()

print(
    "Alle Plausibilitätschecks erfolgreich."
)

print("=" * 60)