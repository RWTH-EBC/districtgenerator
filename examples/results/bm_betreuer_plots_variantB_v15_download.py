from pathlib import Path
import re
import pickle
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm, Normalize, LinearSegmentedColormap
from matplotlib.patches import Patch

# ══════════════════════════════════════════════════════════════════════
# KONFIGURATION — hier Ordner waehlen
# ══════════════════════════════════════════════════════════════════════
# RESULTS_DIR: Ordner mit den PKL-Dateien aus e8_2 (summary_*.pkl, timeseries_*.pkl,
#              topology_*.pkl). Identisch zu RESULT_ROOT/RESULTS_SUBFOLDER bzw. dem
#              uebergeordneten Ordner, der mehrere Quartiere enthaelt.
#              Wird rekursiv (rglob) durchsucht, also reicht der Wurzelordner.
# OUT_DIR    : Zielordner fuer Plots und CSV-Exporte.
RESULTS_DIR = Path(r"C:\Users\rha-csa\PycharmProjects\districtgenerator\districtgenerator\results\Ergebnisse\bm_results_basis_alpha_0.8_foerderung")
# Basis-Zielordner. Die Plots landen in OUT_BASE/<Name des RESULTS_DIR>.
OUT_BASE    = Path(r"C:\Users\rha-csa\PycharmProjects\districtgenerator\districtgenerator\results\bm_plots_dynam")
OUT_DIR     = OUT_BASE / RESULTS_DIR.name

# Filter optional (None = alle). scenario_filter: None / "A" / "B".
QUARTIER_FILTER = None
SCENARIO_FILTER = None


# ══════════════════════════════════════════════════════════════════════
# SCHRITT 1: DataFrames direkt aus den PKLs ableiten (keine Excel).
#            BmTableBuilder liest nur die in e8_2 gespeicherten PKLs und
#            berechnet die abgeleiteten Felder — keine Neu-Optimierung.
# ══════════════════════════════════════════════════════════════════════
def load_dataframes(results_dir: Path):
    """
    Laesst BmTableBuilder ueber die PKLs in results_dir laufen und gibt die
    Zeilenlisten direkt als DataFrames zurueck (cmp, cost, tech, build).

    Robust gegen Start aus examples/results:
    Wenn districtgenerator nicht als Package installiert ist, wird der Projektordner
    automatisch ueber die Elternordner bzw. ueber eine lokale Suche nach
    bm_compariosn_table.py in sys.path aufgenommen.
    """

    def _ensure_project_import_paths() -> None:
        script_dir = Path(__file__).resolve().parent

        # Elternordner aufnehmen, damit Imports funktionieren, wenn das Skript
        # z. B. aus examples/results gestartet wird.
        for parent in [script_dir, *script_dir.parents]:
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))

        # Lokal nach bm_compariosn_table.py suchen und dessen Ordner aufnehmen.
        search_roots = []
        for parent in [script_dir, *script_dir.parents]:
            search_roots.append(parent)
            if parent.name.lower() == 'districtgenerator':
                break

        for root in search_roots:
            try:
                matches = list(root.rglob('bm_compariosn_table.py'))
            except Exception:
                matches = []
            for match in matches:
                module_dir = match.parent
                package_root = module_dir.parent
                for candidate in [module_dir, package_root, root]:
                    if str(candidate) not in sys.path:
                        sys.path.insert(0, str(candidate))

    _ensure_project_import_paths()

    try:
        from bm_compariosn_table import BmTableBuilder
    except ModuleNotFoundError:
        try:
            from districtgenerator.functions.bm_compariosn_table import BmTableBuilder
        except ModuleNotFoundError:
            try:
                from districtgenerator.classes.bm_compariosn_table import BmTableBuilder
            except ModuleNotFoundError:
                try:
                    from districtgenerator.bm_compariosn_table import BmTableBuilder
                except ModuleNotFoundError as exc:
                    raise ModuleNotFoundError(
                        "BmTableBuilder konnte nicht importiert werden. "
                        "Bitte pruefen, ob bm_compariosn_table.py im Projekt liegt "
                        "oder ob das Projekt/districtgenerator-Package im aktiven "
                        "Python-Interpreter installiert ist. Aktueller Skriptpfad: "
                        f"{Path(__file__).resolve()}"
                    ) from exc

    builder = BmTableBuilder(
        input_root=results_dir,
        quartier_filter=QUARTIER_FILTER,
        scenario_filter=SCENARIO_FILTER,
    )

    # run() ohne Excel-Schreiben: nur PKLs einlesen und Zeilen aufbauen.
    for summary_path in sorted(builder.input_root.rglob("summary_*.pkl")):
        info = builder.parse_filename(summary_path)
        if info is None:
            continue
        if builder.quartier_filter and info["quartier"].upper() != builder.quartier_filter:
            continue
        if builder.scenario_filter and info["scenario"].upper() != builder.scenario_filter:
            continue
        try:
            summary = builder.load_pickle(summary_path)
            timeseries = builder.load_matching_timeseries(summary_path)
            topology = builder.load_matching_topology(summary_path)
            builder.process_summary(summary, summary_path, info, timeseries, topology)
        except Exception as exc:
            print(f"  ⚠ {summary_path.name}: {exc!r}")

    cmp = pd.DataFrame(builder.overview_rows)
    cost = pd.DataFrame(builder.costs_rows)
    tech = pd.DataFrame(builder.devices_rows)
    build = pd.DataFrame(builder.building_a_rows)

    if cmp.empty:
        raise RuntimeError(f"Keine verwertbaren summary_*.pkl in {results_dir} gefunden.")
    return cmp, cost, tech, build


# ══════════════════════════════════════════════════════════════════════
# SCHRITT 2: Plots
# ══════════════════════════════════════════════════════════════════════
BM_LABEL = {
    'waermecontracting': 'WC',
    'waermecontracting_ggv': 'WC-GGV',
    'waermecontracting_kundenanlage': 'KA',
    'waermegenossenschaft': 'GEN',
}
BM_LONG = {
    'waermecontracting': 'Wärmecontracting',
    'waermecontracting_ggv': 'Wärmecontracting GGV',
    'waermecontracting_kundenanlage': 'Kundenanlage',
    'waermegenossenschaft': 'Wärmegenossenschaft',
}
REF_LABEL = {'ref_boi': 'BOI', 'ref_wp': 'WP'}
REF_MARKER = {'ref_boi': 'o', 'ref_wp': 's'}
# Eine Farbe je BM; Referenzfall ueber Fuellung: BOI voll, WP/PV gemustert.
BM_COLOR = {
    'waermecontracting': '#1f77b4',
    'waermecontracting_ggv': '#ff7f0e',
    'waermecontracting_kundenanlage': '#2ca02c',
    'waermegenossenschaft': '#d62728',
}
REF_HATCH = {'ref_boi': '', 'ref_wp': ''}  # nicht mehr genutzt: Referenz wird ueber Markerform gezeigt
BMS = ['waermecontracting', 'waermecontracting_ggv', 'waermecontracting_kundenanlage', 'waermegenossenschaft']
# Preis-/p_min-/p_max-Plots ohne Genossenschaft, damit keine leeren Spalten/Luecken entstehen.
PRICE_BMS = ['waermecontracting', 'waermecontracting_ggv', 'waermecontracting_kundenanlage']
REFS = ['ref_boi', 'ref_wp']

# Variante B: technische/inhaltliche Gruppierung
# WC, WC-GGV und Genossenschaft werden fuer die Auslegung zusammengefasst.
BM_GROUP_LABEL = {
    'waermecontracting': 'WC/WC-GGV/GEN',
    'waermecontracting_ggv': 'WC/WC-GGV/GEN',
    'waermegenossenschaft': 'WC/WC-GGV/GEN',
    'waermecontracting_kundenanlage': 'KA',
}
BM_GROUP_COLOR = {
    'WC/WC-GGV/GEN': '#1f77b4',
    'KA': '#2ca02c',
}

# Bevorzugte Repräsentanten je BM-Gruppe.
# Wichtig: Für WC/WC-GGV/GEN wird WC als technischer Repräsentant verwendet.
# Falls WC fehlt, wird auf WC-GGV bzw. GEN zurückgefallen.
BM_GROUP_REPRESENTATIVE_PRIORITY = {
    'WC/WC-GGV/GEN': ['waermecontracting', 'waermecontracting_ggv', 'waermegenossenschaft'],
    'KA': ['waermecontracting_kundenanlage'],
}

# Die tatsächliche Auswahl erfolgt später robust anhand der vorhandenen Dateien.
# Für WC/WC-GGV/GEN ist WC der bevorzugte Vertreter.
SCATTER_BM_REPRESENTATIVES = {
    group: reps[0]
    for group, reps in BM_GROUP_REPRESENTATIVE_PRIORITY.items()
}

# Szenario A / Plot 11: WC und Genossenschaft werden als eine Kategorie gezeigt.
# Falls beide Werte vorhanden sind, wird ein Mittelwert gebildet; bei identischen
# Ergebnissen entspricht das exakt dem Einzelwert.
A_CONN_GROUP_LABEL = {
    'waermecontracting': 'WC/GEN',
    'waermegenossenschaft': 'WC/GEN',
    'waermecontracting_ggv': 'WC-GGV',
    'waermecontracting_kundenanlage': 'KA',
}
A_CONN_GROUP_COLOR = {
    'WC/GEN': '#1f77b4',
    'WC-GGV': '#ff7f0e',
    'KA': '#2ca02c',
}

BUILDING_TYPE_ORDER = ['MFH', 'SFH', 'RE', 'GS', 'SC', 'OB']
BUILDING_TYPE_COLOR = {
    'MFH': '#1f77b4',
    'SFH': '#ff7f0e',
    'RE': '#2ca02c',
    'GS': '#d62728',
    'SC': '#9467bd',
    'OB': '#8c564b',
    'unbekannt': '#7f7f7f',
}

PLOT_FORMAT = 'pdf'
PLOT_COST_STRUCTURE = False       # Kostenstruktur-Plots 05/06 nicht ausfuehren
PLOT_QUARTIER_DASHBOARDS = False  # Quartier-Dashboards nicht ausfuehren
PLOT_TECHNIK = True               # Technik-Plots 09/10 ausfuehren


def save_fig(fig, path_no_suffix: Path) -> None:
    """Speichert Plots einheitlich als PDF."""
    fig.savefig(path_no_suffix.with_suffix(f'.{PLOT_FORMAT}'), bbox_inches='tight')
    plt.close(fig)


def _safe_slug(text) -> str:
    """Dateinamen-taugliche Kurzform."""
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(text)).strip('_')


def npv_heatmap_norm(vals: np.ndarray):
    """
    Farbskala fuer Delta-NPV mit alter linearer Skalenaufteilung:
    - Skala bleibt linear von -80 % bis +25 %,
    - 0 % wird trotzdem gezielt auf gelb/hell gelegt,
    - Gruen beginnt erst oberhalb von 0 %.
    """
    vmin = -80.0
    vmax = 25.0
    zero_pos = (0.0 - vmin) / (vmax - vmin)
    cmap = LinearSegmentedColormap.from_list(
        'delta_npv_linear_red_yellow_green',
        [
            (0.0, '#B2182B'),
            (zero_pos, '#FEE08B'),
            (1.0, '#1A9850'),
        ],
        N=256,
    )
    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)
    ticks = np.array([-80, -60, -40, -20, 0, 20], dtype=float)
    return cmap, norm, ticks


def q_short(q):
    """A01 -> A, B04 -> B (nur fuer Anzeige; Schluessel bleiben voll)."""
    return re.sub(r'\d+$', '', str(q))


def normalize_building_type(value) -> str:
    """Normiert Gebaeudetypen auf MFH, SFH, RE, GS, SC, OB oder unbekannt."""
    if value is None or pd.isna(value):
        return 'unbekannt'
    text = str(value).strip().upper()
    mapping = {
        'MULTI_FAMILY_HOUSE': 'MFH',
        'MULTIFAMILY': 'MFH',
        'MFH': 'MFH',
        'APARTMENT': 'MFH',
        'SINGLE_FAMILY_HOUSE': 'SFH',
        'SINGLEFAMILY': 'SFH',
        'SFH': 'SFH',
        'ROW_HOUSE': 'RE',
        'REIHENHAUS': 'RE',
        'RE': 'RE',
        'RH': 'RE',
        'GEWERBE': 'GS',
        'COMMERCIAL': 'GS',
        'GS': 'GS',
        'SCHOOL': 'SC',
        'SCHULE': 'SC',
        'SC': 'SC',
        'OFFICE': 'OB',
        'OFFICE_BUILDING': 'OB',
        'BUERO': 'OB',
        'BÜRO': 'OB',
        'OB': 'OB',
    }
    return mapping.get(text, text if text in BUILDING_TYPE_ORDER else 'unbekannt')


def _building_type_from_row(row: pd.Series) -> str:
    """Ermittelt den Gebaeudetyp aus moeglichen Builder-/PKL-Spalten."""
    for col in [
        'gebaeudetyp', 'gebäudetyp', 'building_type', 'building',
        'typ', 'building_category', 'usage', 'nutzung'
    ]:
        if col in row.index and pd.notna(row[col]) and str(row[col]).strip():
            return normalize_building_type(row[col])
    return 'unbekannt'


def _nice_axis_max(value: float, step: int) -> float:
    """Rundet Achsengrenzen auf den naechsten Schritt auf."""
    if not np.isfinite(value) or value <= 0:
        return float(step)
    return float(np.ceil(value / step) * step)


def _nice_tick_step(value: float) -> int:
    """Waehlt eine lesbare Schrittweite fuer flexible y-Achsen."""
    if not np.isfinite(value) or value <= 0:
        return 1
    for step in [1, 2, 5, 10, 20, 50, 100, 250, 500, 1000, 2000, 5000]:
        if value / step <= 8:
            return step
    magnitude = 10 ** np.floor(np.log10(value))
    return int(magnitude)


def _select_representative_rows(df: pd.DataFrame, priority_map: dict, group_col: str = 'bm_group') -> pd.DataFrame:
    """
    Waehlt je Quartier, BM-Gruppe und Referenz einen vorhandenen Repräsentanten.
    Dadurch verschwindet WC/WC-GGV/GEN nicht, wenn z. B. nur WC statt WC-GGV vorliegt.
    """
    if df is None or df.empty or group_col not in df.columns or 'bm' not in df.columns:
        return df.copy() if df is not None else pd.DataFrame()

    group_keys = ['quartier', group_col]
    if 'reference' in df.columns:
        group_keys.append('reference')

    selected = []
    for _, sub in df.groupby(group_keys, dropna=False):
        group_label = sub[group_col].iloc[0]
        priority = priority_map.get(group_label, list(sub['bm'].dropna().unique()))
        chosen = None
        for bm in priority:
            cand = sub[sub['bm'].eq(bm)]
            if not cand.empty:
                chosen = cand
                break
        if chosen is None or chosen.empty:
            chosen = sub
        selected.append(chosen)

    return pd.concat(selected, ignore_index=True) if selected else pd.DataFrame(columns=df.columns)


def _apply_grouped_bm_ref_xticks(ax, bm_order, ref_order, bm_labels=None, ref_labels=None, y_bm=-0.18):
    """
    X-Achse zweistufig beschriften:
    - direkte Ticklabels = Referenzmodelle (BOI/WP)
    - darunter je Geschäftsmodell ein zentriertes Label, nur einmal
    """
    bm_labels = bm_labels or BM_LABEL
    ref_labels = ref_labels or REF_LABEL

    n_ref = len(ref_order)
    n_cols = len(bm_order) * n_ref
    x = np.arange(n_cols)

    ax.set_xticks(x)
    ax.set_xticklabels(
        [ref_labels.get(ref, ref) for _bm in bm_order for ref in ref_order],
        rotation=0,
        ha='center',
        fontsize=8,
    )

    for i, bm in enumerate(bm_order):
        center = i * n_ref + (n_ref - 1) / 2
        ax.text(
            center,
            y_bm,
            bm_labels.get(bm, bm),
            ha='center',
            va='top',
            fontsize=9,
            fontweight='bold',
            transform=ax.get_xaxis_transform(),
        )

    for i in range(1, len(bm_order)):
        ax.axvline(i * n_ref - 0.5, color='black', linewidth=0.8)

    ax.set_xlim(-0.5, n_cols - 0.5)


def _finish_heatmap_axes(ax, im, n_rows: int, n_cols: int) -> None:
    """Verhindert optisches Ueberlaufen der Heatmap-Flaechen und zeichnet Zellgrenzen."""
    im.set_clip_path(ax.patch)
    ax.set_xlim(-0.5, n_cols - 0.5)
    ax.set_ylim(n_rows - 0.5, -0.5)
    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=0.35)
    ax.tick_params(which='minor', bottom=False, left=False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
        spine.set_color('black')


def _grouped_bars_by_device(ax, df, valcol, ylabel, title):
    """Gruppierte Balken: x = Technologie, Gruppen = BM (Farbe = BM_COLOR)."""
    if df is None or df.empty:
        ax.axis('off')
        ax.set_title(title)
        return
    devices = sorted(df['technologie'].dropna().unique())
    bms = [b for b in BMS if b in set(df['bm'])]
    if not devices or not bms:
        ax.axis('off')
        ax.set_title(title)
        return
    x = np.arange(len(devices))
    w = 0.8 / len(bms)
    for i, bm in enumerate(bms):
        vals = [float(df[(df['bm'].eq(bm)) & (df['technologie'].eq(d))][valcol].sum())
                for d in devices]
        ax.bar(x + i * w - 0.4 + w / 2, vals, w, color=BM_COLOR[bm],
               edgecolor='black', linewidth=0.4, label=BM_LABEL[bm])
    ax.set_xticks(x)
    ax.set_xticklabels(devices)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis='y', linestyle=':', alpha=0.45)
    ax.legend(fontsize=8)

COST_GROUPS = {
    'Erzeuger': ['erzeuger_ann_inv_EUR_a', 'erzeuger_om_EUR_a'],
    'Speicher': ['speicher_ann_inv_EUR_a', 'speicher_om_EUR_a'],
    'Wärmenetz': ['waermenetz_ann_EUR_a', 'waermenetz_om_EUR_a'],
    'Stromnetz/Trafo/PV': ['stromnetz_kundenanlage_ann_EUR_a', 'trafo_ann_EUR_a', 'pv_dezentral_ann_EUR_a'],
    'Energiebezug': ['energiekosten_strom_EUR_a', 'energiekosten_gas_EUR_a', 'energiekosten_biomasse_EUR_a'],
}




def _ct_per_kwh(value) -> float:
    """Konvertiert EUR/kWh nach ct/kWh, falls der Wert offenbar in EUR/kWh vorliegt."""
    if value is None or pd.isna(value):
        return np.nan
    value = float(value)
    return value * 100.0 if abs(value) < 2.0 else value


def _derive_pmax_ct_kwh(detail: dict, p_min_eur_per_kwh: float) -> float:
    """
    Liefert p_max in ct/kWh.

    In einigen Summary-PKLs steht p_max = None, obwohl sich ein rechnerischer
    Schwellenpreis aus den gespeicherten NPV-Komponenten ableiten laesst.
    Das passiert typischerweise, wenn der Schwellenpreis negativ ist und vom
    BM-Breakdown nicht als gueltiger p_max gespeichert wurde.

    Herleitung aus:
      npv_wn_at_price = npv_strom_wn - p_min * bw_heat_i
      p_max: npv_strom_wn - p_max * bw_heat_i = npv_ref

    Daraus:
      bw_heat_i = (npv_strom_wn - npv_wn_at_price) / p_min
      p_max    = (npv_strom_wn - npv_ref) / bw_heat_i
    """
    if not isinstance(detail, dict):
        return np.nan

    raw = detail.get('p_max', np.nan)
    if raw is not None and not pd.isna(raw):
        return _ct_per_kwh(raw)

    needed = ['npv_ref', 'npv_strom_wn', 'npv_wn_at_price']
    if any(k not in detail or detail.get(k) is None or pd.isna(detail.get(k)) for k in needed):
        return np.nan
    if p_min_eur_per_kwh is None or pd.isna(p_min_eur_per_kwh) or float(p_min_eur_per_kwh) == 0:
        return np.nan

    npv_ref = float(detail['npv_ref'])
    npv_strom_wn = float(detail['npv_strom_wn'])
    npv_wn_at_price = float(detail['npv_wn_at_price'])
    p_min_eur_per_kwh = float(p_min_eur_per_kwh)

    bw_heat_i = (npv_strom_wn - npv_wn_at_price) / p_min_eur_per_kwh
    if not np.isfinite(bw_heat_i) or abs(bw_heat_i) <= 1e-12:
        return np.nan

    pmax_eur_per_kwh = (npv_strom_wn - npv_ref) / bw_heat_i
    return pmax_eur_per_kwh * 100.0


def _load_pickle_safe(path: Path):
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except Exception as exc:
        print(f"  ⚠ {path.name} konnte nicht gelesen werden: {exc!r}")
        return None


def _summary_meta(summary: dict, fallback_path: Path | None = None) -> dict:
    """Liest robuste Metadaten aus summary-PKL oder Dateiname."""
    meta = summary.get('metadata', {}) if isinstance(summary, dict) else {}

    q = meta.get('scenario_variant')
    bm = meta.get('business_model')
    ref = meta.get('reference_key')

    if fallback_path is not None:
        # summary_A01_bm_ref_boi_waermecontracting_B.pkl
        m = re.match(
            r"summary_(?P<q>[^_]+)_bm_(?P<ref>ref_[^_]+(?:_[^_]+)?)_(?P<bm>.+)_(?P<scen>[AB])\.pkl$",
            fallback_path.name,
        )
        if m:
            q = q or m.group('q')
            bm = bm or m.group('bm')
            ref = ref or m.group('ref')

    if ref in {'ref_boi_waermecontracting', 'ref_wp_waermecontracting'}:
        # Fallback fuer zu gierige Regex; normalerweise kommt reference_key aus metadata.
        ref = 'ref_boi' if 'boi' in ref else 'ref_wp'

    return {'quartier': q, 'bm': bm, 'reference': ref}


def _get_bm_breakdown(summary: dict, bm: str | None) -> dict:
    """Findet den BM-Breakdown in den bekannten PKL-Strukturen."""
    bb = summary.get('kpis', {}).get('bm_breakdown', {}) if isinstance(summary, dict) else {}
    if not isinstance(bb, dict):
        return {}

    candidates = []
    if bm:
        candidates.append(f'{bm}_breakdown')
    candidates.extend(['bm_breakdown', 'breakdown'])

    for key in candidates:
        val = bb.get(key)
        if isinstance(val, dict) and ('p_min' in val or 'scenario_a' in val or 'scenario_b' in val):
            return val

    for val in bb.values():
        if isinstance(val, dict) and ('p_min' in val or 'scenario_a' in val or 'scenario_b' in val):
            return val

    return {}


def load_building_pmax_B_from_summaries(results_dir: Path) -> pd.DataFrame:
    """
    Liest die Gebaeudeplots direkt aus summary_*.pkl.
    Grund: Der aktuelle BmTableBuilder schreibt diese Zeilen nicht in build.
    In den summary-PKLs liegen sie unter:
      kpis -> bm_breakdown -> ... -> scenario_a -> building_details / p_max_by_building
    p_min kommt aus demselben BM-Breakdown.
    """
    rows = []

    for summary_path in sorted(results_dir.rglob("summary_*_B.pkl")):
        summary = _load_pickle_safe(summary_path)
        if not isinstance(summary, dict):
            continue

        meta = _summary_meta(summary, summary_path)
        q = meta['quartier']
        bm = meta['bm']
        ref = meta['reference']

        if not q or not bm or not ref:
            continue
        if QUARTIER_FILTER and str(q).upper() != str(QUARTIER_FILTER).upper():
            continue
        if SCENARIO_FILTER and str(SCENARIO_FILTER).upper() != 'B':
            continue

        br = _get_bm_breakdown(summary, bm)
        if not br:
            continue

        p_min_raw = br.get('p_min')
        p_min = _ct_per_kwh(p_min_raw)
        p_min_eur_per_kwh = float(p_min_raw) if p_min_raw is not None and not pd.isna(p_min_raw) else np.nan
        scenario_a = br.get('scenario_a', {}) if isinstance(br.get('scenario_a', {}), dict) else {}
        details = scenario_a.get('building_details', {})
        pmax_by_building = scenario_a.get('p_max_by_building', {})

        if not isinstance(details, dict):
            details = {}
        if not isinstance(pmax_by_building, dict):
            pmax_by_building = {}

        building_ids = sorted(set(details.keys()) | set(pmax_by_building.keys()))
        if not building_ids:
            continue

        for bid in building_ids:
            detail = details.get(bid, {}) if isinstance(details.get(bid, {}), dict) else {}
            features = detail.get('_features', {}) if isinstance(detail.get('_features', {}), dict) else {}

            # p_max kann in der PKL None sein. Dann wird ein rechnerischer
            # Schwellenpreis aus den gespeicherten NPV-Komponenten abgeleitet.
            # Dadurch werden z. B. negative p_max-Werte sichtbar, statt das
            # Gebaeude als fehlend zu behandeln.
            pmax = detail.get('p_max', pmax_by_building.get(bid, np.nan))
            if pmax is None or pd.isna(pmax):
                pmax = _derive_pmax_ct_kwh(detail, p_min_eur_per_kwh)
            else:
                pmax = _ct_per_kwh(pmax)

            geb_id = features.get('original_bldg_id', features.get('building_index', bid))
            try:
                geb_id = int(geb_id)
            except Exception:
                geb_id = int(bid) if isinstance(bid, (int, np.integer)) else bid

            rows.append({
                'quartier': q,
                'reference': ref,
                'bm': bm,
                'scenario': 'B',
                'gebaeude': geb_id,
                'pmax_i_ct_kWh': pmax,
                'pmin_ct_kWh': p_min,
                'building_type': normalize_building_type(features.get('building')),
                'unique_name': features.get('unique_name', ''),
            })

    return pd.DataFrame(rows)


HEAT_GENERATION_KEYS = {
    'STC': 'heat_STC',
    'HP': 'heat_HP',
    'EB': 'heat_EB',
    'CHP': 'heat_CHP',
    'BOI': 'heat_BOI',
    'GHP': 'heat_GHP',
    'BCHP': 'heat_BCHP',
    'BBOI': 'heat_BBOI',
    'WCHP': 'heat_WCHP',
    'WBOI': 'heat_WBOI',
    'FC': 'heat_FC',
}


def _matching_timeseries_path(summary_path: Path) -> Path:
    return summary_path.with_name(summary_path.name.replace('summary_', 'timeseries_', 1))


def _cluster_weight(metadata: dict, cluster_key, cluster_pos: int) -> float:
    weights = metadata.get('clusterWeights', {})
    if isinstance(weights, dict):
        if cluster_key in weights:
            return float(weights[cluster_key])
        if str(cluster_key) in weights:
            return float(weights[str(cluster_key)])
        vals = [weights[k] for k in sorted(weights)]
        if cluster_pos < len(vals):
            return float(vals[cluster_pos])
    return 1.0


def load_vollaststunden_from_timeseries(results_dir: Path) -> pd.DataFrame:
    """
    Berechnet Vollbenutzungsstunden je Stützjahr direkt aus timeseries_*.pkl.
    Der Builder-tech-Export enthält die Stützjahre aktuell nicht.
    """
    rows = []

    for summary_path in sorted(results_dir.rglob("summary_*_B.pkl")):
        summary = _load_pickle_safe(summary_path)
        if not isinstance(summary, dict):
            continue

        meta = _summary_meta(summary, summary_path)
        q = meta['quartier']
        bm = meta['bm']
        ref = meta['reference']

        # Für Variante B nur BMs aus den technischen Gruppen auswerten.
        # Die konkrete Repräsentantenauswahl erfolgt später robust je Quartier.
        if bm not in set(BM_GROUP_LABEL.keys()):
            continue

        ts_path = _matching_timeseries_path(summary_path)
        if not ts_path.exists():
            continue

        ts = _load_pickle_safe(ts_path)
        if not isinstance(ts, dict):
            continue

        capacities = summary.get('capacities', {}).get('central', {})
        energy_hub = ts.get('energy_hub', {})
        ts_meta = ts.get('ts_meta', {})
        metadata = ts.get('metadata', {})

        dt_h = float(ts_meta.get('time_resolution_seconds', metadata.get('timeResolution_s', 3600))) / 3600.0

        if not isinstance(energy_hub, dict):
            continue

        for stuetzjahr, clusters in sorted(energy_hub.items(), key=lambda kv: float(kv[0])):
            if not isinstance(clusters, dict):
                continue

            for dev, heat_key in HEAT_GENERATION_KEYS.items():
                cap = capacities.get(dev, {}).get('cap_kW', 0.0) if isinstance(capacities.get(dev, {}), dict) else 0.0
                cap = float(cap or 0.0)
                if cap <= 0:
                    continue

                gen_kWh = 0.0
                for pos, (cluster_key, cluster_data) in enumerate(sorted(clusters.items(), key=lambda kv: kv[0])):
                    if not isinstance(cluster_data, dict) or heat_key not in cluster_data:
                        continue
                    arr = np.asarray(cluster_data[heat_key], dtype=float)
                    weight = _cluster_weight(metadata, cluster_key, pos)
                    gen_kWh += float(np.nansum(arr)) * dt_h * weight / 1000.0

                # Auch 0 h/a behalten: Wenn ein installierter Erzeuger in einem
                # Stuetzjahr nicht laeuft, soll das Jahr im Plot trotzdem erscheinen.
                rows.append({
                    'quartier': q,
                    'reference': ref,
                    'bm': bm,
                    'bm_group': BM_GROUP_LABEL.get(bm, bm),
                    'stuetzjahr': int(stuetzjahr) if float(stuetzjahr).is_integer() else stuetzjahr,
                    'technologie': dev,
                    'kapazitaet_kW': cap,
                    'generation_kWh': gen_kWh,
                    'vollaststunden_h_a': gen_kWh / cap,
                })

    return pd.DataFrame(rows)


def plot_vollaststunden_from_timeseries(results_dir: Path, out: Path, q_order) -> None:
    """
    Plot je Quartier mit allen Erzeugern in einem Bild.

    Aufbau:
      - ein PDF je Quartier
      - x-Achse = Technologie + Stützjahr
      - Balken = BM-Gruppe WC/WC-GGV/GEN bzw. KA
      - y-Achse = Vollbenutzungsstunden, 500er-Schritte
    """
    vls = load_vollaststunden_from_timeseries(results_dir)
    out_dir = out / 'technik' / 'vollaststunden_stuetzjahre'
    out_dir.mkdir(parents=True, exist_ok=True)

    if vls.empty:
        print("  ⚠ Keine Vollaststunden-Stützjahre aus timeseries_*.pkl gefunden.")
        return

    vls.to_csv(out / 'tables' / 'vollaststunden_stuetzjahre.csv', index=False, sep=';', decimal=',')

    # Plot-Auswahl robust je Gruppe: bevorzugt WC, sonst WC-GGV, sonst GEN.
    vls = _select_representative_rows(vls, BM_GROUP_REPRESENTATIVE_PRIORITY)

    tech_order = ['BCHP', 'BBOI', 'BOI', 'CHP', 'GHP', 'HP', 'EB', 'STC', 'WCHP', 'WBOI', 'FC']

    for q in q_order:
        tq = vls[vls['quartier'].eq(q)].copy()
        if tq.empty:
            continue

        present_tech = [t for t in tech_order if t in set(tq['technologie'])]
        present_tech += sorted([t for t in tq['technologie'].dropna().unique() if t not in present_tech])

        years = sorted(tq['stuetzjahr'].dropna().unique(), key=lambda x: float(x))
        groups = [g for g in ['WC/WC-GGV/GEN', 'KA'] if g in set(tq['bm_group'])]

        # Labelpositionen: Fuer jeden installierten Erzeuger werden alle
        # Stuetzjahre angezeigt, auch wenn er in einzelnen Jahren 0 h/a hat.
        x_positions = []
        x_labels = []
        tech_centers = {}
        tech_ranges = {}
        current_x = 0.0
        for tech_name in present_tech:
            xs_for_tech = []
            for year in years:
                x_positions.append(current_x)
                x_labels.append(str(year))
                xs_for_tech.append(current_x)
                current_x += 1.0
            if xs_for_tech:
                tech_centers[tech_name] = float(np.mean(xs_for_tech))
                tech_ranges[tech_name] = (float(xs_for_tech[0]), float(xs_for_tech[-1]))
                current_x += 0.7  # optische Trennung zwischen Technologien

        if not x_positions:
            continue

        fig_w = max(10.5, 0.42 * len(x_positions) + 4.5)
        fig, ax = plt.subplots(figsize=(fig_w, 5.6))

        w = 0.78 / max(len(groups), 1)
        max_y = 0.0

        low_vls_labels = []
        for i, group_label in enumerate(groups):
            vals_plot = []
            installed_flags = []

            for tech_name in present_tech:
                for year in years:
                    ss = tq[
                        tq['technologie'].eq(tech_name)
                        & tq['stuetzjahr'].eq(year)
                        & tq['bm_group'].eq(group_label)
                    ]

                    if ss.empty:
                        val = 0.0
                        installed = False
                    else:
                        val = float(ss['vollaststunden_h_a'].mean())
                        installed = float(ss['kapazitaet_kW'].mean()) > 0

                    vals_plot.append(val)
                    installed_flags.append(installed)

            max_y = max(max_y, max(vals_plot) if vals_plot else 0.0)
            x_bar = np.asarray(x_positions) + i * w - 0.39 + w / 2
            ax.bar(
                x_bar,
                vals_plot,
                w,
                color=BM_GROUP_COLOR[group_label],
                edgecolor='black',
                linewidth=0.45,
                label=group_label,
                zorder=3,
            )

            for xb, val, installed in zip(x_bar, vals_plot, installed_flags):
                if installed and val < 50:
                    low_vls_labels.append((float(xb), float(val)))

        # Sehr kleine Vollbenutzungsstunden sind als Balken praktisch unsichtbar.
        # Deshalb werden Werte < 50 h/a direkt angeschrieben.
        for idx_label, (xb, val) in enumerate(low_vls_labels):
            # Horizontale Beschriftung; leichte Staffelung verhindert,
            # dass mehrere 0-/Kleinwerte optisch zusammenlaufen.
            label_y = max(val, max_y * (0.016 + 0.010 * (idx_label % 3)), 8.0)
            ax.text(
                xb,
                label_y,
                f'{val:.0f}',
                ha='center',
                va='bottom',
                fontsize=6,
                rotation=0,
                color='black',
                zorder=5,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.70, pad=0.6),
            )

        ymax = _nice_axis_max(max_y, 500)
        ax.set_ylim(0, ymax)
        ax.set_yticks(np.arange(0, ymax + 500, 500))

        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels, fontsize=8)
        ax.set_xlabel('Stützjahr je Technologie')
        ax.set_ylabel('Vollbenutzungsstunden [h/a]')
        ax.set_title(f'Quartier {q_short(q)}: Vollbenutzungsstunden nach Stützjahr')
        ax.grid(axis='y', linestyle=':', alpha=0.45)
        ax.legend(fontsize=8)

        # Technologien als Gruppenbeschriftung unter der x-Achse.
        for tech_name, center in tech_centers.items():
            ax.text(
                center,
                -0.16,
                tech_name,
                ha='center',
                va='top',
                fontsize=9,
                fontweight='bold',
                transform=ax.get_xaxis_transform(),
            )

        # Dezente vertikale Trennlinien exakt in der Luecke zwischen Technologien.
        present_with_ranges = [t for t in present_tech if t in tech_ranges]
        for left_tech, right_tech in zip(present_with_ranges[:-1], present_with_ranges[1:]):
            left_end = tech_ranges[left_tech][1]
            right_start = tech_ranges[right_tech][0]
            ax.axvline((left_end + right_start) / 2, color='0.70', linewidth=0.7, zorder=1)

        plt.tight_layout(rect=[0, 0.08, 1, 1])
        save_fig(fig, out_dir / f'{q_short(q)}_vollaststunden_stuetzjahre_alle_erzeuger')


def make_plots(cmp: pd.DataFrame, cost: pd.DataFrame, tech: pd.DataFrame,
               build: pd.DataFrame, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / 'quartiere').mkdir(exist_ok=True)
    (out / 'tables').mkdir(exist_ok=True)

    for df in (cmp, cost, tech, build):
        if 'bm' in df.columns:
            df['bm_label'] = df['bm'].map(BM_LABEL).fillna(df['bm'])
            df['bm_long'] = df['bm'].map(BM_LONG).fillna(df['bm'])
        if 'reference' in df.columns:
            df['ref_label'] = df['reference'].map(REF_LABEL).fillna(df['reference'])

    cmp['wirtschaftlich_bool'] = cmp['wirtschaftlich'].fillna(0).astype(float) > 0.5
    cmp['anschluss_text'] = cmp.apply(
        lambda r: f"{int(r['gebaeude_angeschlossen'])}/{int(r['gebaeude_gesamt'])}"
        if pd.notna(r['gebaeude_angeschlossen']) and pd.notna(r['gebaeude_gesamt']) else '',
        axis=1,
    )

    # export summary table
    summary_cols = [
        'quartier', 'reference', 'bm', 'scenario', 'status', 'wirtschaftlich', 'NPV_diff_pct', 'NPV_diff_EUR',
        'p_min_ct_kWh', 'p_max_ct_kWh', 'p_min_minus_p_max_ct_kWh',
        'gebaeude_gesamt', 'gebaeude_angeschlossen', 'anschlussquote_gebaeude_pct', 'anschluss_text',
        'waerme_gesamt_MWh', 'waerme_angeschlossen_MWh', 'anschlussquote_waerme_pct', 'heat_density_kWh_m_a'
    ]
    summary_cols = [c for c in summary_cols if c in cmp.columns]
    cmp[summary_cols].sort_values(['quartier', 'bm', 'scenario', 'reference']).to_csv(
        out / 'tables' / 'summary_for_meeting.csv', index=False, sep=';', decimal=','
    )

    cost_b = cost[cost['scenario'].eq('B')].copy()
    rows = []
    for _, r in cost_b.iterrows():
        d = {
            'quartier': r['quartier'],
            'reference': r['reference'],
            'bm': r['bm'],
            'bm_label': r['bm_label'],
            'bm_long': r['bm_long'],
            'ref_label': r['ref_label'],
        }
        total = 0.0
        for group, cols in COST_GROUPS.items():
            val = sum(float(r.get(c, 0) or 0) for c in cols)
            d[group] = val
            total += val
        d['total'] = total
        match = cmp[(cmp['quartier'].eq(r['quartier'])) & (cmp['reference'].eq(r['reference'])) & (cmp['bm'].eq(r['bm'])) & (cmp['scenario'].eq('B'))]
        d['sort_gap'] = float(match['p_min_minus_p_max_ct_kWh'].iloc[0]) if not match.empty and pd.notna(match['p_min_minus_p_max_ct_kWh'].iloc[0]) else np.nan
        rows.append(d)
    cs = pd.DataFrame(rows)
    cs.to_csv(out / 'tables' / 'cost_structure_B.csv', index=False, sep=';', decimal=',')

    # 1 Heatmap ΔNPV for B
    bdf = cmp[cmp['scenario'].eq('B')].copy()
    q_order = sorted(bdf['quartier'].dropna().unique())
    bdf['col'] = bdf['bm_label'] + '\n' + bdf['ref_label']
    col_order = [BM_LABEL[b] + '\n' + REF_LABEL[r] for b in BMS for r in REFS]
    piv = bdf.pivot_table(index='quartier', columns='col', values='NPV_diff_pct', aggfunc='first').reindex(index=q_order, columns=col_order)

    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    vals = piv.to_numpy(dtype=float)
    cmap, norm, ticks = npv_heatmap_norm(vals)
    im = ax.imshow(vals, aspect='auto', cmap=cmap, norm=norm)
    _apply_grouped_bm_ref_xticks(ax, BMS, REFS)
    _finish_heatmap_axes(ax, im, vals.shape[0], vals.shape[1])
    ax.set_yticks(np.arange(len(piv.index)))
    ax.set_yticklabels([q_short(q) for q in piv.index])
    ax.set_title('ΔNPV gegenüber Referenz [%]')
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = vals[i, j]
            if np.isfinite(v):
                ax.text(j, i, f'{v:.1f}', ha='center', va='center', fontsize=8,
                        color='white' if abs(v) > 35 else 'black')
    ax.set_xlabel('Geschäftsmodell / Referenz')
    ax.set_ylabel('Quartier')
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02, ticks=ticks)
    cbar.set_label('ΔNPV [%]')
    plt.tight_layout(rect=[0, 0.08, 1, 1])
    save_fig(fig, out / '01_heatmap_npv_diff_pct')

    # 2 Heatmap gap for B
    price_col_order = [BM_LABEL[b] + '\n' + REF_LABEL[r] for b in PRICE_BMS for r in REFS]
    piv_gap = (
        bdf[bdf['bm'].isin(PRICE_BMS)]
        .pivot_table(index='quartier', columns='col', values='p_min_minus_p_max_ct_kWh', aggfunc='first')
        .reindex(index=q_order, columns=price_col_order)
    )
    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    vals = piv_gap.to_numpy(dtype=float)
    lim = np.nanmax(np.abs(vals))
    im = ax.imshow(vals, aspect='auto', cmap='RdYlGn_r', norm=TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim))
    _apply_grouped_bm_ref_xticks(ax, PRICE_BMS, REFS)
    _finish_heatmap_axes(ax, im, vals.shape[0], vals.shape[1])
    ax.set_yticks(np.arange(len(piv_gap.index)))
    ax.set_yticklabels([q_short(q) for q in piv_gap.index])
    ax.set_title('Wirtschaftlichkeitslücke p_min - p_max [ct/kWh]')
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = vals[i, j]
            if np.isfinite(v):
                ax.text(j, i, f'{v:.1f}', ha='center', va='center', fontsize=8,
                        color='white' if abs(v) > lim * 0.55 else 'black')
    ax.set_xlabel('Geschäftsmodell / Referenz')
    ax.set_ylabel('Quartier')
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label('p_min - p_max [ct/kWh]')
    plt.tight_layout(rect=[0, 0.08, 1, 1])
    save_fig(fig, out / '02_heatmap_gap_pmin_minus_pmax')

    # 3 Ranking
    rank = bdf[bdf['bm'].isin(PRICE_BMS)].dropna(subset=['p_min_minus_p_max_ct_kWh']).copy()
    rank['label'] = rank['quartier'].map(q_short) + ' | ' + rank['bm_label'] + ' | ' + rank['ref_label']
    rank = rank.sort_values('p_min_minus_p_max_ct_kWh')
    fig_h = max(8, 0.27 * len(rank) + 1.5)
    fig, ax = plt.subplots(figsize=(10.5, fig_h))
    y = np.arange(len(rank))
    vals = rank['p_min_minus_p_max_ct_kWh'].to_numpy()
    colors = np.where(vals <= 0, '#2E7D32', '#B03A2E')
    ax.barh(y, vals, color=colors, edgecolor='black', linewidth=0.4)
    ax.axvline(0, color='black', linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(rank['label'], fontsize=8)
    ax.set_xlabel('p_min - p_max [ct/kWh]')
    ax.set_title('Ranking nach Wirtschaftlichkeitslücke')
    ax.grid(axis='x', linestyle=':', alpha=0.45)
    plt.tight_layout()
    save_fig(fig, out / '03_ranking_gap')

    # 4 Scatter: Wärmedichte vs. Delta-NPV
    #    Variante B:
    #    - Kategorie WC/WC-GGV/GEN wird durch WC repraesentiert.
    #    - Kategorie KA wird durch KA repraesentiert.
    #    - BOI und WP werden im selben Plot ueber Markerformen gezeigt.
    scatter_df = bdf[bdf['bm'].isin(BM_GROUP_LABEL.keys())].dropna(
        subset=['heat_density_kWh_m_a', 'NPV_diff_pct']
    ).copy()

    if not scatter_df.empty:
        scatter_df['bm_group'] = scatter_df['bm'].map(BM_GROUP_LABEL)
        scatter_df = _select_representative_rows(scatter_df, BM_GROUP_REPRESENTATIVE_PRIORITY)
        fig, ax = plt.subplots(figsize=(9.8, 6.0))

        q_pos = (
            scatter_df[['quartier', 'heat_density_kWh_m_a']]
            .dropna()
            .groupby('quartier', as_index=False)['heat_density_kWh_m_a']
            .median()
            .sort_values('heat_density_kWh_m_a')
        )
        q_to_x = dict(zip(q_pos['quartier'], q_pos['heat_density_kWh_m_a']))

        for group_label in ['WC/WC-GGV/GEN', 'KA']:
            for ref in REFS:
                ss = scatter_df[
                    scatter_df['bm_group'].eq(group_label) & scatter_df['reference'].eq(ref)
                ].dropna(subset=['heat_density_kWh_m_a', 'NPV_diff_pct'])
                if ss.empty:
                    continue

                # Alle Punkte desselben Quartiers liegen exakt auf derselben
                # Wärmedichte. Keine x-Verschiebung/Jitter.
                x = ss['quartier'].map(q_to_x).astype(float).to_numpy()

                ax.scatter(
                    x,
                    ss['NPV_diff_pct'],
                    s=48,
                    marker=REF_MARKER[ref],
                    facecolor=BM_GROUP_COLOR[group_label],
                    edgecolor='black',
                    linewidth=0.75,
                    alpha=0.92,
                    zorder=3,
                )

        y_span = max(
            float(scatter_df['NPV_diff_pct'].max() - scatter_df['NPV_diff_pct'].min()),
            1.0,
        )
        label_offset = 0.030 * y_span

        for q, g in scatter_df.groupby('quartier'):
            if q not in q_to_x:
                continue
            y_label = float(g['NPV_diff_pct'].max()) + label_offset
            ax.text(
                float(q_to_x[q]),
                y_label,
                q_short(q),
                ha='center',
                va='bottom',
                fontsize=9,
                fontweight='bold',
                zorder=4,
            )

        y_min = float(scatter_df['NPV_diff_pct'].min())
        y_max = float(scatter_df['NPV_diff_pct'].max())
        ax.set_ylim(y_min - 0.10 * y_span, y_max + 0.14 * y_span)

        ax.axhline(0, color='black', linewidth=1.0)
        ax.set_xscale('log')
        ax.set_xlabel('Wärmedichte [kWh/m, log]')
        ax.set_ylabel('ΔNPV gegenüber Referenz [%]')
        ax.set_title('Wärmedichte und ΔNPV gegenüber Referenz')
        ax.grid(axis='y', linestyle=':', alpha=0.35)

        legend_handles = [
            Patch(facecolor=BM_GROUP_COLOR['WC/WC-GGV/GEN'], edgecolor='black', label='WC/WC-GGV/GEN'),
            Patch(facecolor=BM_GROUP_COLOR['KA'], edgecolor='black', label='KA'),
            plt.Line2D([0], [0], marker=REF_MARKER['ref_boi'], color='black',
                       markerfacecolor='white', markersize=8, linestyle='None', label='BOI'),
            plt.Line2D([0], [0], marker=REF_MARKER['ref_wp'], color='black',
                       markerfacecolor='white', markersize=8, linestyle='None', label='WP'),
        ]
        ax.legend(
            handles=legend_handles,
            title='Geschäftsmodellgruppe / Referenz',
            fontsize=8,
            title_fontsize=9,
            loc='best',
        )

        plt.tight_layout()
        save_fig(fig, out / '04_scatter_waermedichte_vs_npv_pct_WC-WC-GGV-GEN_KA')

    if PLOT_COST_STRUCTURE:
        # 5 Overall cost structure B
        cs2 = cs.dropna(subset=['sort_gap']).sort_values('sort_gap').copy()
        cs2['label'] = cs2['quartier'].map(q_short) + '\n' + cs2['bm_label'] + ' ' + cs2['ref_label']
        fig, ax = plt.subplots(figsize=(max(12, 0.34 * len(cs2) + 5), 6.4))
        bottom = np.zeros(len(cs2))
        colors = plt.get_cmap('tab10').colors
        for i, g in enumerate(COST_GROUPS):
            vals = cs2[g].to_numpy() / 1000
            ax.bar(cs2['label'], vals, bottom=bottom, label=g, edgecolor='black', linewidth=0.25, color=colors[i % len(colors)])
            bottom += vals
        ax.set_ylabel('annualisierte Kosten [k€/a]')
        ax.set_title('Komprimierte Kostenstruktur, sortiert nach Wirtschaftlichkeitslücke')
        ax.tick_params(axis='x', labelrotation=70, labelsize=7)
        ax.grid(axis='y', linestyle=':', alpha=0.45)
        ax.legend(bbox_to_anchor=(1.01, 1), loc='upper left')
        plt.tight_layout()
        save_fig(fig, out / '05_kostenstruktur_kompakt')

        # 6 Per-BM cost structure B
        for bm in BMS:
            sub = cs[(cs['bm'] == bm)].dropna(subset=['sort_gap']).sort_values('sort_gap').copy()
            if sub.empty:
                continue
            sub['label'] = sub['quartier'].map(q_short) + '\n' + sub['ref_label']
            fig_w = max(8.5, 0.7 * len(sub) + 2.8)
            fig, ax = plt.subplots(figsize=(fig_w, 5.6))
            bottom = np.zeros(len(sub))
            for i, g in enumerate(COST_GROUPS):
                vals = sub[g].to_numpy() / 1000
                ax.bar(sub['label'], vals, bottom=bottom, label=g, edgecolor='black', linewidth=0.25, color=colors[i % len(colors)])
                bottom += vals
            ax.set_ylabel('annualisierte Kosten [k€/a]')
            ax.set_title(f'Kostenstruktur – {BM_LONG[bm]}')
            ax.tick_params(axis='x', labelrotation=45, labelsize=8)
            ax.grid(axis='y', linestyle=':', alpha=0.45)
            ax.legend(fontsize=8, bbox_to_anchor=(1.01, 1), loc='upper left')
            plt.tight_layout()
            save_fig(fig, out / f'06_kostenstruktur_{_safe_slug(BM_LABEL[bm])}')


    # 7 Per-BM pmin vs pmax B
    for bm in PRICE_BMS:
        sub = bdf[bdf['bm'].eq(bm)].dropna(subset=['p_min_ct_kWh', 'p_max_ct_kWh']).copy()
        if sub.empty:
            continue
        fig, ax = plt.subplots(figsize=(7.2, 6.2))
        for ref in REFS:
            ss = sub[sub['reference'].eq(ref)]
            if ss.empty:
                continue
            point_colors = np.where(ss['wirtschaftlich_bool'], '#2E7D32', '#B03A2E')
            ax.scatter(ss['p_max_ct_kWh'], ss['p_min_ct_kWh'], s=85, marker=REF_MARKER[ref], c=point_colors,
                       edgecolor='black', label=REF_LABEL[ref])
            for _, r in ss.iterrows():
                ax.annotate(q_short(r['quartier']), (r['p_max_ct_kWh'], r['p_min_ct_kWh']), textcoords='offset points', xytext=(4, 3), fontsize=8)
        mn = min(sub['p_max_ct_kWh'].min(), sub['p_min_ct_kWh'].min()) - 1
        mx = max(sub['p_max_ct_kWh'].max(), sub['p_min_ct_kWh'].max()) + 1
        ax.plot([mn, mx], [mn, mx], '--', color='black', linewidth=1, label='p_min = p_max')
        ax.set_xlim(mn, mx)
        ax.set_ylim(mn, mx)
        ax.set_aspect('equal', adjustable='box')
        ax.set_xlabel('p_max [ct/kWh]')
        ax.set_ylabel('p_min [ct/kWh]')
        ax.set_title(f'Entscheidungsregel – {BM_LONG[bm]}')
        ax.grid(True, linestyle=':', alpha=0.45)
        ax.legend(fontsize=8)
        plt.tight_layout()
        save_fig(fig, out / f'07_pmin_vs_pmax_{_safe_slug(BM_LABEL[bm])}')

    if PLOT_QUARTIER_DASHBOARDS:
        # 8 Individual quartier dashboards
        for q in q_order:
            q_b = bdf[bdf['quartier'].eq(q)].copy()
            q_a = cmp[(cmp['quartier'].eq(q)) & (cmp['scenario'].eq('A'))].copy()
            q_build = build[build['quartier'].eq(q)].copy()
            q_cost = cs[cs['quartier'].eq(q)].copy()

            fig, axes = plt.subplots(3, 2, figsize=(13.5, 12.0))
            fig.suptitle(f'Quartier {q_short(q)}: Übersicht', fontsize=14, y=0.99)

            # Panel 1: NPV B
            ax = axes[0, 0]
            tmp = q_b.dropna(subset=['NPV_diff_pct']).copy().sort_values(['bm', 'reference'])
            tmp['label'] = tmp['bm_label'] + '\n' + tmp['ref_label']
            vals = tmp['NPV_diff_pct'].to_numpy()
            ax.bar(tmp['label'], vals, color=np.where(vals >= 0, '#2E7D32', '#B03A2E'), edgecolor='black', linewidth=0.4)
            ax.axhline(0, color='black', linewidth=1)
            ax.set_ylabel('ΔNPV [%]')
            ax.set_title('Szenario B: NPV gegenüber Referenz')
            ax.tick_params(axis='x', rotation=45, labelsize=8)
            ax.grid(axis='y', linestyle=':', alpha=0.45)

            # Panel 2: gap B
            ax = axes[0, 1]
            tmp = q_b.dropna(subset=['p_min_minus_p_max_ct_kWh']).copy()
            tmp['label'] = tmp['bm_label'] + '\n' + tmp['ref_label']
            tmp = tmp.sort_values('p_min_minus_p_max_ct_kWh')
            vals = tmp['p_min_minus_p_max_ct_kWh'].to_numpy()
            ax.barh(tmp['label'], vals, color=np.where(vals <= 0, '#2E7D32', '#B03A2E'), edgecolor='black', linewidth=0.4)
            ax.axvline(0, color='black', linewidth=1)
            ax.set_xlabel('p_min - p_max [ct/kWh]')
            ax.set_title('Szenario B: Wärmepreis-Lücke')
            ax.grid(axis='x', linestyle=':', alpha=0.45)

            # Panel 3: Scenario A connected buildings as counts
            ax = axes[1, 0]
            tmp = q_a[~q_a['bm'].eq('waermegenossenschaft')].copy().sort_values(['bm', 'reference'])
            if not tmp.empty:
                tmp['label'] = tmp['bm_label'] + '\n' + tmp['ref_label']
                vals = tmp['gebaeude_angeschlossen'].fillna(0).astype(float).to_numpy()
                totals = tmp['gebaeude_gesamt'].fillna(0).astype(float).to_numpy()
                colors_bar = np.where(vals == totals, '#2E7D32', '#4C78A8')
                ax.bar(tmp['label'], vals, color=colors_bar, edgecolor='black', linewidth=0.4)
                ymax = max(np.nanmax(totals), np.nanmax(vals), 1)
                ax.set_ylim(0, ymax * 1.20)
                ax.set_ylabel('angeschlossene Gebäude [Anzahl]')
                ax.set_title('Szenario A: angeschlossene Gebäude')
                ax.tick_params(axis='x', rotation=45, labelsize=8)
                ax.grid(axis='y', linestyle=':', alpha=0.45)
                for x, (v, t) in enumerate(zip(vals, totals)):
                    ax.text(x, v + ymax * 0.03, f'{int(v)}/{int(t)}', ha='center', va='bottom', fontsize=8)
            else:
                ax.axis('off')

            # Panel 4: building distribution A gap
            ax = axes[1, 1]
            qb = q_build[~q_build['bm'].eq('waermegenossenschaft')].copy()
            if not qb.empty:
                qb['label'] = qb['bm_label'] + '\n' + qb['ref_label']
                order = qb.groupby('label')['delta_pmax_minus_pmin_ct_kWh'].median().sort_values().index.tolist()
                data = [qb[qb['label'].eq(l)]['delta_pmax_minus_pmin_ct_kWh'].dropna().to_numpy() for l in order]
                if len(data) > 0:
                    bp = ax.boxplot(data, tick_labels=order, vert=False, patch_artist=True, showfliers=False)
                    for patch in bp['boxes']:
                        patch.set_facecolor('#B8C6D9')
                        patch.set_edgecolor('black')
                    ax.axvline(0, color='black', linewidth=1)
                    ax.set_xlabel('p_max,i - p_min [ct/kWh]')
                    ax.set_title('Szenario A: Gebäudestreuung')
                    ax.grid(axis='x', linestyle=':', alpha=0.45)
                else:
                    ax.axis('off')
            else:
                ax.axis('off')

            # Panel 5: compact cost structure for this quartier (B)
            ax = axes[2, 0]
            tmp = q_cost.dropna(subset=['sort_gap']).sort_values('sort_gap').copy()
            if not tmp.empty:
                tmp['label'] = tmp['bm_label'] + '\n' + tmp['ref_label']
                bottom = np.zeros(len(tmp))
                for i, g in enumerate(COST_GROUPS):
                    vals = tmp[g].to_numpy() / 1000.0
                    ax.bar(tmp['label'], vals, bottom=bottom, label=g, edgecolor='black', linewidth=0.25, color=colors[i % len(colors)])
                    bottom += vals
                ax.set_ylabel('Kosten [k€/a]')
                ax.set_title('Szenario B: Kostenstruktur')
                ax.tick_params(axis='x', rotation=45, labelsize=8)
                ax.grid(axis='y', linestyle=':', alpha=0.45)
                ax.legend(fontsize=7, loc='upper left')
            else:
                ax.axis('off')

            # Panel 6: pmin vs pmax for this quartier (B)
            ax = axes[2, 1]
            tmp = q_b.dropna(subset=['p_min_ct_kWh', 'p_max_ct_kWh']).copy()
            if not tmp.empty:
                for ref in REFS:
                    ss = tmp[tmp['reference'].eq(ref)]
                    if ss.empty:
                        continue
                    point_colors = np.where(ss['wirtschaftlich_bool'], '#2E7D32', '#B03A2E')
                    ax.scatter(ss['p_max_ct_kWh'], ss['p_min_ct_kWh'], s=80, marker=REF_MARKER[ref], c=point_colors, edgecolor='black', label=REF_LABEL[ref])
                    for _, r in ss.iterrows():
                        ax.annotate(r['bm_label'], (r['p_max_ct_kWh'], r['p_min_ct_kWh']), textcoords='offset points', xytext=(4, 3), fontsize=8)
                mn = min(tmp['p_max_ct_kWh'].min(), tmp['p_min_ct_kWh'].min()) - 1
                mx = max(tmp['p_max_ct_kWh'].max(), tmp['p_min_ct_kWh'].max()) + 1
                ax.plot([mn, mx], [mn, mx], '--', color='black', linewidth=1)
                ax.set_xlim(mn, mx)
                ax.set_ylim(mn, mx)
                ax.set_xlabel('p_max [ct/kWh]')
                ax.set_ylabel('p_min [ct/kWh]')
                ax.set_title('Szenario B: Entscheidungsregel')
                ax.grid(True, linestyle=':', alpha=0.45)
                ax.legend(fontsize=8)
            else:
                ax.axis('off')

            plt.tight_layout(rect=[0, 0, 1, 0.97])
            save_fig(fig, out / 'quartiere' / f'{q}_dashboard')


    if PLOT_TECHNIK:
        # 9 Auslegung je Quartier: Erzeuger [kW] + Speicher [kWh]
        #    Zwei technische Kategorien:
        #    - WC/WC-GGV/GEN: bevorzugt aus waermecontracting repraesentiert
        #    - KA: aus waermecontracting_kundenanlage
        (out / 'technik').mkdir(exist_ok=True)

        techB = tech[tech['scenario'].eq('B')].copy()
        techB['bm_group'] = techB['bm'].map(BM_GROUP_LABEL)

        tech_candidates = techB[techB['bm'].isin(BM_GROUP_LABEL.keys())].copy()
        tech_rep = _select_representative_rows(tech_candidates, BM_GROUP_REPRESENTATIVE_PRIORITY)

        # Referenz deduplizieren: technische Auslegung ist referenzunabhaengig.
        dedup_cols = ['quartier', 'bm_group', 'technologie']
        if 'stuetzjahr' in tech_rep.columns:
            # Fuer die reine Auslegung wird das erste vorhandene Stuetzjahr je Kombination genommen,
            # wenn mehrere Stuetzjahre vorhanden sind.
            dedup_cols.append('stuetzjahr')
        tech_rep = tech_rep.drop_duplicates(subset=[c for c in dedup_cols if c in tech_rep.columns])

        for q in q_order:
            tq = tech_rep[tech_rep['quartier'].eq(q)].copy()
            if tq.empty:
                continue

            gen = tq[tq['typ'].eq('Erzeuger')].copy()
            sto = tq[tq['typ'].eq('Speicher')].copy()

            fig, (axg, axs) = plt.subplots(1, 2, figsize=(13.5, 5.2))

            for ax, df_part, valcol, ylabel, title, step in [
                (axg, gen, 'kapazitaet', 'Kapazität [kW]', 'Erzeuger', None),
                (axs, sto, 'kapazitaet', 'Kapazität [kWh]', 'Speicher', None),
            ]:
                if df_part.empty:
                    ax.axis('off')
                    ax.set_title(title)
                    continue

                devices = sorted(df_part['technologie'].dropna().unique())
                groups = [g for g in ['WC/WC-GGV/GEN', 'KA'] if g in set(df_part['bm_group'])]
                x = np.arange(len(devices))
                # Speicherbalken bewusst sehr schlank halten. Zusätzlich wird
                # unten für Speicher ein breiterer x-Bereich gesetzt, damit ein
                # einzelner TES-Balken nicht optisch die ganze Achse ausfüllt.
                width_total = 0.12 if title == 'Speicher' else 0.8
                w = width_total / max(len(groups), 1)

                max_y = 0.0
                for i, group_label in enumerate(groups):
                    vals_plot = [
                        float(df_part[
                            df_part['bm_group'].eq(group_label) & df_part['technologie'].eq(d)
                        ][valcol].sum())
                        for d in devices
                    ]
                    max_y = max(max_y, max(vals_plot) if vals_plot else 0.0)
                    ax.bar(
                        x + i * w - width_total / 2 + w / 2,
                        vals_plot,
                        w,
                        color=BM_GROUP_COLOR[group_label],
                        edgecolor='black',
                        linewidth=0.4,
                        label=group_label,
                    )

                ax.set_xticks(x)
                ax.set_xticklabels(devices, rotation=0, ha='center')

                if title == 'Speicher':
                    # Matplotlib zoomt bei nur einer Kategorie stark auf den Balken.
                    # Dadurch wirkt TES trotz kleiner width sehr breit. Feste Ränder
                    # machen die absolute Balkenbreite sichtbar schmaler.
                    ax.set_xlim(-0.75, max(len(devices) - 0.25, 0.75))
                else:
                    ax.set_xlim(-0.5, len(devices) - 0.5)

                ax.set_ylabel(ylabel)
                ax.set_title(title)
                step_eff = _nice_tick_step(max_y) if step is None else step
                ymax_eff = _nice_axis_max(max_y, step_eff)
                ax.set_ylim(0, ymax_eff)
                ax.set_yticks(np.arange(0, ymax_eff + step_eff, step_eff))
                ax.grid(axis='y', linestyle=':', alpha=0.45)
                ax.legend(fontsize=8)

            fig.suptitle(f'Quartier {q_short(q)}: zentrale Auslegung', fontsize=13)
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            save_fig(fig, out / 'technik' / f'{q_short(q)}_auslegung')

        # 10 Vollbenutzungsstunden über alle Stützjahre direkt aus timeseries_*.pkl.
        plot_vollaststunden_from_timeseries(RESULTS_DIR, out, q_order)


    # 11 Szenario A: angeschlossene Gebaeude je Quartier und BM-Gruppe
    #     WC und Genossenschaft werden zusammengefasst.
    #     Die Beschriftung nutzt den Quartiers-Gesamtbestand, nicht die reduzierte
    #     Teilmenge einer Iteration.
    adf = cmp[cmp['scenario'].eq('A')].copy()
    if not adf.empty and {'gebaeude_angeschlossen', 'gebaeude_gesamt'}.issubset(adf.columns):
        total_by_q = (
            cmp.dropna(subset=['gebaeude_gesamt'])
            .groupby('quartier')['gebaeude_gesamt']
            .max()
            .to_dict()
        )

        rows = []
        for _, r in adf.iterrows():
            bm_group = A_CONN_GROUP_LABEL.get(r['bm'])
            if bm_group is None:
                continue

            angeschlossen = float(r.get('gebaeude_angeschlossen', 0) or 0)
            gesamt = float(total_by_q.get(r['quartier'], r.get('gebaeude_gesamt', 0) or 0))
            # In den Standard-Quartieren ist der Vollbestand 30 Gebaeude.
            # Dadurch wird z. B. 0/30 statt 0/29 gezeigt, wenn eine
            # Szenario-A-Iteration bereits eine reduzierte Teilmenge speichert.
            if gesamt < 30:
                gesamt = 30.0

            # Nur Kombinationen zeigen, bei denen sich tatsaechlich Gebaeude anschliessen.
            # Der Nenner bleibt trotzdem der Quartiers-Gesamtbestand.
            if gesamt <= 0 or angeschlossen <= 0:
                continue

            rows.append({
                'quartier': r['quartier'],
                'q_label': q_short(r['quartier']),
                'bm_group': bm_group,
                'reference': r['reference'],
                'ref_label': r.get('ref_label', REF_LABEL.get(r['reference'], r['reference'])),
                'angeschlossen': angeschlossen,
                'gesamt': gesamt,
            })

        if rows:
            aconn_raw = pd.DataFrame(rows)

            # Zusammenfassung von WC und Genossenschaft:
            # nicht summieren, sondern mitteln/erstwertartig aggregieren.
            aconn = (
                aconn_raw
                .groupby(['quartier', 'q_label', 'bm_group', 'reference', 'ref_label'], as_index=False)
                .agg({'angeschlossen': 'mean', 'gesamt': 'max'})
            )

            # Keine 0/30-Kombinationen anzeigen; nur reale Anschlussfaelle.
            aconn['label'] = aconn['q_label'] + '\n' + aconn['bm_group'] + ' ' + aconn['ref_label']
            group_order = {'WC/GEN': 0, 'WC-GGV': 1, 'KA': 2}
            aconn['group_order'] = aconn['bm_group'].map(group_order).fillna(99)
            aconn['ref_order'] = aconn['reference'].map({r: i for i, r in enumerate(REFS)}).fillna(99)
            aconn = aconn.sort_values(['quartier', 'group_order', 'ref_order'])

            fig, ax = plt.subplots(figsize=(max(8.5, 0.48 * len(aconn) + 2.5), 5.2))
            x = np.arange(len(aconn))
            colors_bar = [A_CONN_GROUP_COLOR.get(g, '#777777') for g in aconn['bm_group']]
            vals = aconn['angeschlossen'].to_numpy(dtype=float)
            totals = aconn['gesamt'].to_numpy(dtype=float)

            ax.bar(x, vals, color=colors_bar, edgecolor='black', linewidth=0.5)
            ax.set_xticks(x)
            ax.set_xticklabels(aconn['label'], rotation=0, ha='center', fontsize=7)
            ax.set_ylim(0, max(float(np.nanmax(totals)), 30.0) * 1.18)
            ax.set_ylabel('angeschlossene Gebäude [Anzahl]')
            ax.set_title('Ohne Anschlusszwang: freiwillig angeschlossene Gebäude')
            ax.grid(axis='y', linestyle=':', alpha=0.35)

            y_base = max(float(np.nanmax(totals)), 30.0)
            for xi, v, t in zip(x, vals, totals):
                ax.text(
                    xi,
                    v + y_base * 0.025,
                    f'{int(round(v))}/{int(round(t))}',
                    ha='center',
                    va='bottom',
                    fontsize=8,
                )

            handles = [
                Patch(facecolor=A_CONN_GROUP_COLOR[g], edgecolor='black', label=g)
                for g in ['WC/GEN', 'WC-GGV', 'KA']
                if g in set(aconn['bm_group'])
            ]
            ax.legend(handles=handles, title='Geschäftsmodell', fontsize=8, title_fontsize=9, loc='best')

            plt.tight_layout()
            save_fig(fig, out / '11_anschluesse_ohne_anschlusszwang')

    # 12 Szenario B: gebaeudescharfe Bewertung direkt aus summary_*.pkl.
    #     Der aktuelle Builder schreibt diese Gebaeudezeilen nicht in build.
    build_b_direct = load_building_pmax_B_from_summaries(RESULTS_DIR)
    if not build_b_direct.empty:
        # CSV enthaelt die rechnerischen Rohwerte. Negative p_max-Werte werden
        # nur im Plot auf 0 gekappt, nicht in der Tabelle.
        build_b_direct.to_csv(out / 'tables' / 'building_pmax_B_from_summaries.csv',
                              index=False, sep=';', decimal=',')
        plot_building_pmax_B(build_b_direct, out)
    elif {'scenario', 'pmax_i_ct_kWh', 'pmin_ct_kWh'}.issubset(build.columns):
        build_b = build[build['scenario'].eq('B')].copy()
        if not build_b.empty:
            plot_building_pmax_B(build_b, out)
    else:
        print('  ⚠ Keine Gebäudedaten fuer Szenario B gefunden.')


    print(f'Created plots in {out}')


# ══════════════════════════════════════════════════════════════════════
# OPTIONAL: Per-Gebaeude p_max,i vs. p_min (Szenario B)
# Voraussetzung: build_b-DataFrame mit Spalten
#   quartier, reference, bm, gebaeude, pmax_i_ct_kWh, pmin_ct_kWh
# Diese Zeilen muss der BmTableBuilder zusaetzlich emittieren
# (add_building_b_rows aus scenario_b['building_details'] — reines Lesen,
#  keine Neuberechnung). Solange das fehlt, wird die Funktion nicht aufgerufen.
# ══════════════════════════════════════════════════════════════════════
def plot_building_pmax_B(build_b: pd.DataFrame, out: Path) -> None:
    """
    Gebaeudescharfer Vergleich p_max,i gegen p_min als Balkendiagramm.

    Darstellung:
    - x-Achse: Gebaeude-ID 1..30
    - Balkenhoehe: p_max,i
    - Horizontale Linie: p_min
    - Farbe: Gebaeudetyp
    - Legende: nur im Modell vorkommende Gebaeudetypen aus MFH, SFH, RE, GS, SC, OB
    """
    out_dir = out / 'gebaeude_B'
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_all = build_b.copy()
    tmp_all['gebaeudetyp_plot'] = tmp_all.apply(_building_type_from_row, axis=1)

    for (q, bm, ref), sub in tmp_all.groupby(['quartier', 'bm', 'reference']):
        sub = sub.copy()
        if sub.empty:
            continue

        if 'gebaeude' in sub.columns:
            sub['gebaeude_nr_plot'] = pd.to_numeric(sub['gebaeude'], errors='coerce')
        elif 'building_id' in sub.columns:
            sub['gebaeude_nr_plot'] = pd.to_numeric(sub['building_id'], errors='coerce')
        else:
            sub['gebaeude_nr_plot'] = np.arange(1, len(sub) + 1)

        sub = sub.dropna(subset=['gebaeude_nr_plot']).copy()
        sub['gebaeude_nr_plot'] = sub['gebaeude_nr_plot'].astype(int)

        sub = sub.sort_values('gebaeude_nr_plot')

        p_min = (
            float(sub['pmin_ct_kWh'].iloc[0])
            if 'pmin_ct_kWh' in sub.columns and pd.notna(sub['pmin_ct_kWh'].iloc[0])
            else None
        )

        fig, ax = plt.subplots(figsize=(10.8, 5.4))

        missing_pmax = sub['pmax_i_ct_kWh'].isna()
        negative_pmax = sub['pmax_i_ct_kWh'].lt(0).fillna(False)

        # Fuer die Darstellung werden negative rechnerische p_max-Werte bei 0 gekappt.
        # Interpretation: Das Gebaeude waere selbst bei kostenloser Waerme nicht wirtschaftlich.
        plot_vals = sub['pmax_i_ct_kWh'].fillna(0.0).clip(lower=0.0)

        colors = [
            '#D9D9D9' if missing else BUILDING_TYPE_COLOR.get(t, BUILDING_TYPE_COLOR['unbekannt'])
            for t, missing in zip(sub['gebaeudetyp_plot'], missing_pmax)
        ]
        bars = ax.bar(
            sub['gebaeude_nr_plot'],
            plot_vals,
            color=colors,
            edgecolor='black',
            linewidth=0.45,
            width=0.8,
            zorder=3,
        )
        for bar, missing, negative in zip(bars, missing_pmax, negative_pmax):
            if missing:
                bar.set_hatch('///')
                bar.set_alpha(0.85)
            elif negative:
                bar.set_hatch('xx')
                bar.set_alpha(0.90)

        if p_min is not None:
            ax.axhline(
                p_min,
                color='black',
                linestyle='-',
                linewidth=1.2,
                label=f'p_min = {p_min:.1f} ct/kWh',
                zorder=4,
            )

        used_types = [
            t for t in BUILDING_TYPE_ORDER
            if t in set(sub['gebaeudetyp_plot'])
        ]
        if 'unbekannt' in set(sub['gebaeudetyp_plot']):
            used_types.append('unbekannt')

        handles = [
            Patch(
                facecolor=BUILDING_TYPE_COLOR.get(t, BUILDING_TYPE_COLOR['unbekannt']),
                edgecolor='black',
                label=t,
            )
            for t in used_types
        ]
        if bool(negative_pmax.any()):
            handles.append(Patch(facecolor='white', edgecolor='black', hatch='xx', label='p_max < 0, auf 0 gekappt'))
        if bool(missing_pmax.any()):
            handles.append(Patch(facecolor='#D9D9D9', edgecolor='black', hatch='///', label='kein p_max'))
        if p_min is not None:
            handles.append(plt.Line2D([0], [0], color='black', linewidth=1.2,
                                      label=f'p_min = {p_min:.1f} ct/kWh'))

        ax.legend(handles=handles, title='Gebäudetyp', fontsize=8, title_fontsize=9, loc='best')

        ax.set_xlim(-0.5, 29.5)
        ax.set_xticks(np.arange(0, 30, 1))
        ax.set_xticklabels([str(i) for i in range(0, 30)], fontsize=7)
        y_vals = [v for v in plot_vals.to_numpy(dtype=float) if np.isfinite(v)]
        if p_min is not None and np.isfinite(p_min):
            y_vals.append(p_min)

        ymax = max(y_vals) if y_vals else 1.0
        step = _nice_tick_step(ymax)
        ymax_eff = _nice_axis_max(ymax * 1.08, step)
        ax.set_ylim(0, ymax_eff)
        ax.set_yticks(np.arange(0, ymax_eff + step, step))
        ax.axhline(0, color='0.25', linewidth=0.8, zorder=2)

        ax.set_xlabel('Gebäude-ID')
        ax.set_ylabel('p_max,i [ct/kWh]')
        ax.set_title(
            f'Quartier {q_short(q)} – {BM_LABEL.get(bm, bm)} {REF_LABEL.get(ref, ref)}: '
            f'Gebäudevergleich zu p_min'
        )
        ax.grid(axis='y', linestyle=':', alpha=0.45)
        plt.tight_layout()
        save_fig(fig, out_dir / f'{q_short(q)}_{_safe_slug(BM_LABEL.get(bm, bm))}_{_safe_slug(ref)}')


# ══════════════════════════════════════════════════════════════════════
# AUSFUEHRUNG
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    cmp, cost, tech, build = load_dataframes(RESULTS_DIR)
    make_plots(cmp, cost, tech, build, OUT_DIR)