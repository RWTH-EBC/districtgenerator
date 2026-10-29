"""Update Aachen results, optionally using a cached use recount and generation weights."""

from __future__ import annotations

import argparse
import json
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION = ROOT / "docs" / "aachen_osm_street_cluster_method_results.md"
RESULT_HEADING = "## 10. Candidate-generation results"
TYPES = list("ABCDEFGHI")
NRB_LABELS = {
    "OB": "Office", "SC": "School", "RE": "Restaurant",
    "GS": "Grocery", "UNI": "University", "HOSPITAL": "Hospital/medical",
    "CULTURE": "Culture", "SPORT": "Sport", "RETAIL": "Other retail",
    "WORKSHOP": "Workshop/industrial", "OTHER_NRB": "Other identified NRB",
}


def _int(value):
    return f"{int(value):,}"


def _pct(value, digits=1):
    return f"{float(value):.{digits}f}%"


def _percentage(part, whole):
    return 100.0 * part / whole if whole else 0.0


def _sum(frame, column):
    return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _quantile(frame, column, label, digits=3):
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return f"| {label} | — | — | — |"
    q1, median, q3 = values.quantile([.25, .5, .75])
    return (f"| {label} | {q1:.{digits}f} | {median:.{digits}f} | "
            f"{q3:.{digits}f} |")


def _result_text(output_dir, use_results=None, generator_parameters=None):
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    candidates = pd.read_csv(output_dir / "candidate_metrics.csv")
    use_dir = use_results or output_dir
    split = pd.read_csv(use_dir / "osm_building_split_percentages_by_type.csv")
    nrb = pd.read_csv(use_dir / "osm_nrb_building_percentages_by_type.csv")
    created = datetime.fromisoformat(manifest["created_utc"].replace("Z", "+00:00"))
    scope = manifest.get("analysis_scope", "unspecified")
    included_mask = candidates["included_in_type_results"].astype(str).str.lower().isin(
        {"true", "1"})
    building_total = _sum(candidates, "building_count")
    eligible_total = int(manifest["eligible_buildings"])
    methods = candidates["boundary_method"].fillna("").astype(str)
    method_rows = [
        ("Road-block clusters, including morphology splits",
         methods.str.startswith("road_block").sum()),
        ("Two-sided street clusters, including morphology splits",
         methods.str.startswith("two_sided").sum()),
        ("Additional scattered-A candidates",
         methods.str.startswith("additional_scattered_A").sum()),
    ]
    method_rows = [(name, int(value)) for name, value in method_rows if value]
    lines = [RESULT_HEADING, "",
             (f"These results were generated automatically from the completed `{scope}` run "
              f"created on {created:%Y-%m-%d at %H:%M UTC}. The source directory is "
              f"`{output_dir.as_posix()}`."), "",
             f"The run identified {_int(len(candidates))} non-overlapping candidates.", "",
             "| Membership-selection procedure | Candidates |", "|---|---:|"]
    lines.extend(f"| {name} | {_int(value)} |" for name, value in method_rows)
    lines += [f"| **Total** | **{_int(len(candidates))}** |", "",
              (f"The candidates contain {_int(building_total)} unique building footprints, "
               f"corresponding to {_percentage(building_total, eligible_total):.3f}% of the "
               f"{_int(eligible_total)} eligible footprints."), "",
              "| Indicator | 25th percentile | Median | 75th percentile |",
              "|---|---:|---:|---:|",
              _quantile(candidates, "building_count", "Buildings per candidate", 0),
              _quantile(candidates, "area_ha", "District area (ha)"),
              _quantile(candidates, "bcr", "BCR"),
              _quantile(candidates, "density", "Building density (buildings/ha)"),
              _quantile(candidates, "far", "FAR, where available"),
              _quantile(candidates, "building_spacing_median_m", "Active building spacing (m)"),
              _quantile(candidates, "attached_building_pct", "Attached buildings (%)"),
              _quantile(candidates, "row_structure_pct", "General row structure (%)"),
              _quantile(candidates, "range_score", "Total range score $D_t$"),
              _quantile(candidates, "midpoint_score", "Total midpoint score $C_t$"), ""]
    if use_results:
        lines += ["Morphology and candidate assignments remain from that original run. "
                  "Sections 12--15 use the corrected sports-hall/fitness-centre cached recount, "
                  f"stored separately in `{use_dir.as_posix()}`. The original run files are "
                  "historical records and have not been overwritten. Type-A unknown-to-residential "
                  "generation weights are reported separately in Section 17; they do not alter "
                  "the observed-use tables.", ""]
    far_count = pd.to_numeric(candidates["far"], errors="coerce").notna().sum()
    block_count = (pd.to_numeric(candidates["block_frontage_structure_pct"],
                                 errors="coerce") >= 50).sum()
    rural_count = candidates["rural_influence_boundary_applied"].astype(
        str).str.lower().isin({"true", "1"}).sum()
    lines += [(f"FAR is available for {_int(far_count)} candidates. The block-frontage "
               f"requirement is met by {_int(block_count)} candidates. Rural influence "
               f"boundaries are applied to {_int(rural_count)} candidates."), "",
              (f"Candidate areas range from {pd.to_numeric(candidates.area_ha).min():.3f} "
               f"to {pd.to_numeric(candidates.area_ha).max():.3f} ha."), "",
              "## 11. Settlement-type assignment results", "",
              "| Type | Candidates | Buildings | Exact | Approximate | Unique compatible | Midpoint tie-break | Nearest outside ranges | Unknown use, original run |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for typ in TYPES + ["UNCLASSIFIED"]:
        group = candidates[candidates["assigned_type"] == typ]
        buildings = _sum(group, "building_count")
        weighted_unknown = ((pd.to_numeric(group["unknown_use_pct"], errors="coerce") *
                             pd.to_numeric(group["building_count"], errors="coerce")).sum()
                            / buildings if buildings else 0)
        lines.append(
            f"| {typ} | {_int(len(group))} | {_int(buildings)} | "
            f"{_int((group.classification_quality == 'exact').sum())} | "
            f"{_int((group.classification_quality == 'approximate').sum())} | "
            f"{_int((group.assignment_reason == 'unique_compatible').sum())} | "
            f"{_int((group.assignment_reason == 'midpoint_tiebreak').sum())} | "
            f"{_int((group.assignment_reason == 'nearest_outside_ranges').sum())} | "
            f"{_pct(weighted_unknown)} |")
    quality = manifest.get("classification_quality", {})
    contexts = manifest.get("settlement_contexts", {})
    lines += ["", "The unknown-use column above belongs to the original morphology export. "
              "For corrected observed use shares, see Section 13.", "",
              (f"Classification quality is exact for {_int(quality.get('exact', 0))}, "
                     f"approximate for {_int(quality.get('approximate', 0))} and unclassified "
                     f"for {_int(quality.get('unclassified', 0))} candidates. "
                     f"{_int(included_mask.sum())} candidates enter type-specific results."), "",
              ("The final context classes contain " + ", ".join(
                  f"{key}={_int(value)}" for key, value in contexts.items()) +
               f". Context changes {_int(manifest.get('context_changed_assignments', 0))} "
               "assignments relative to unrestricted scoring."), "",
              "## 12. Overall main building-use results", ""]
    split_counts = {
        "Residential": _sum(split, "residential_building_count"),
        "Mixed-use": _sum(split, "mixed_building_count"),
        "Non-residential": _sum(split, "nonres_building_count"),
        "Unknown": _sum(split, "unknown_building_count"),
    }
    split_total = sum(split_counts.values())
    known_total = split_total - split_counts["Unknown"]
    lines += ["| Main-use category | Buildings | Percentage of all | Percentage of known use |",
              "|---|---:|---:|---:|"]
    for label, count in split_counts.items():
        known = "—" if label == "Unknown" else _pct(
            _percentage(count, known_total), 3)
        lines.append(f"| {label} | {_int(count)} | "
                     f"{_pct(_percentage(count, split_total), 3)} | {known} |")
    lines += [f"| **Total** | **{_int(split_total)}** | **100.000%** | — |", "",
              (f"The known-use population contains {_int(known_total)} buildings; "
               f"{_pct(_percentage(split_counts['Unknown'], split_total), 3)} "
               "have unknown main use."), "",
              "## 13. Main-use results by assigned type", "",
              "| Type | Buildings | Residential, all | Mixed, all | Non-residential, all | Unknown | Known-use buildings | Residential, known | Mixed, known | Non-residential, known |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for _, row in split.sort_values("typ").iterrows():
        known = int(row.building_footprint_count - row.unknown_building_count)
        lines.append(f"| {row.typ} | {_int(row.building_footprint_count)} | "
                     f"{_pct(row.residential_building_percentage_of_all)} | "
                     f"{_pct(row.mixed_building_percentage_of_all)} | "
                     f"{_pct(row.nonres_building_percentage_of_all)} | "
                     f"{_pct(row.unknown_building_percentage_of_all)} | {_int(known)} | "
                     f"{_pct(row.residential_building_percentage_of_known)} | "
                     f"{_pct(row.mixed_building_percentage_of_known)} | "
                     f"{_pct(row.nonres_building_percentage_of_known)} |")
    nrb_total = _sum(nrb, "classified_nrb_building_count")
    all_buildings = _sum(nrb, "building_footprint_count")
    direct = _sum(nrb, "building_footprints_with_direct_nrb_tag_count")
    from_poi = _sum(nrb, "building_footprints_classified_from_poi_count")
    orphan = _sum(nrb, "classified_poi_without_building_count")
    lines += ["", "## 14. Overall non-residential subtype results", "",
              (f"A total of {_int(nrb_total)} buildings receive a subtype: {_int(direct)} from "
               f"direct building evidence and {_int(from_poi)} from contained POIs. "
               f"{_int(orphan)} classified POIs have no containing eligible building."), "",
              "| NRB subtype | Buildings | Percentage of classified NRB | Percentage of all buildings |",
              "|---|---:|---:|---:|"]
    for code, label in NRB_LABELS.items():
        count = _sum(nrb, f"nrb_{code}_building_count")
        lines.append(f"| {label} ({code}) | {_int(count)} | "
                     f"{_pct(_percentage(count, nrb_total), 3)} | "
                     f"{_pct(_percentage(count, all_buildings), 3)} |")
    lines += [f"| **Total** | **{_int(nrb_total)}** | **100.000%** | "
              f"**{_pct(_percentage(nrb_total, all_buildings), 3)}** |", "",
              "## 15. Non-residential subtype results by assigned type", "",
              "Percentages are conditional on subtype-classified NRB buildings within each assigned type.", ""]
    codes = list(NRB_LABELS)
    lines += ["| Type | NRB buildings | " + " | ".join(codes) + " |",
              "|---|---:|" + "---:|" * len(codes)]
    for _, row in nrb.sort_values("typ").iterrows():
        values = " | ".join(_pct(row[f"nrb_{code}_building_percentage"])
                            for code in codes)
        lines.append(f"| {row.typ} | {_int(row.classified_nrb_building_count)} | {values} |")
    map_size = (output_dir / "review_map.html").stat().st_size / (1024 * 1024)
    lines += ["", "## 16. Result files", "",
              f"The original morphology outputs are stored in `{output_dir.as_posix()}`:", "",
              "- `candidate_districts.geojson`: candidate geometries and indicators;",
              "- `candidate_metrics.csv`: morphology and matching results;",
              "- `building_membership.csv`: traceable OSM building membership;",
              "- `osm_use_counts_by_district.csv`: district-level use results;",
              "- `osm_building_split_percentages_by_type.csv`: pooled main-use shares;",
              "- `osm_nrb_building_percentages_by_type.csv`: pooled NRB subtype shares;",
              "- `osm_use_summary_by_type.csv`: extended type summary;",
              "- `review_map.html`: interactive review map;",
              "- `industrial_exclusion_sites.geojson`: excluded industrial areas; and",
              "- `manifest.json`: hashes, settings, versions and provenance.", "",
              f"The review map is approximately {map_size:.1f} MB.", "",
              "OSM data attribution: © OpenStreetMap contributors, ODbL.", ""]
    if use_results:
        lines += ["The original use CSVs above retain the old classification. Corrected use CSVs "
                  f"with the same filenames are in `{use_dir.as_posix()}`. "
                  "`source_hashes.json` records unchanged cached inputs. No downloads, "
                  "candidate regeneration or profile regeneration were required.", ""]
    if generator_parameters:
        params = pd.read_csv(generator_parameters)
        if 'generation' in set(params.policy):
            params = params[params.policy == 'generation']
        else:
            params = params[params.policy == 'halls_fitness_type_A_unknown_residential']
        params = params.set_index('typ')
        old = pd.read_csv(output_dir / 'osm_nrb_building_percentages_by_type.csv').set_index('typ')
        corrected = nrb.set_index('typ')
        supported = [code for code in NRB_LABELS if code != 'OTHER_NRB']
        lines += ["## 17. Corrected SPORT weights and generation parameters", "",
                  f"Updated {datetime.now():%d %B %Y}. These tables use the original OSM type codes A--I. "
                  "Raw type G is not used in the Paper-3 ensemble; raw H/I are labelled G/H in its figures.", "",
                  "### 17.1 SPORT classification correction", "",
                  "| Type | Original SPORT count | Corrected SPORT count | Original SPORT among supported NRB | Corrected SPORT among supported NRB |",
                  "|---|---:|---:|---:|---:|"]
        for typ in sorted(params.index):
            previous = old.loc[typ]
            denominator = sum(previous[f'nrb_{code}_building_count'] for code in supported)
            lines.append(f"| {typ} | {int(previous.nrb_SPORT_building_count)} | "
                         f"{int(corrected.loc[typ, 'nrb_SPORT_building_count'])} | "
                         f"{_pct(_percentage(previous.nrb_SPORT_building_count, denominator), 2)} | "
                         f"{_pct(params.loc[typ, 'SPORT_conditional_pct'], 2)} |")
        lines += ["", "In the historical frozen-Aachen audit, of the seven original type-A SPORT footprints, only fitness centre "
                  "`way/76448164` remains SPORT. Four grandstands and the public building associated "
                  "with a shooting POI are OTHER_NRB; the parking footprint becomes unknown. "
                  "The original type-A SPORT count of seven was therefore not seven supported sports halls.", "",
                  "### 17.2 Main-use generation assumptions", "",
                  "| Type | Residential | Non-residential | Mixed | Unknown footprints assumed residential | Marginal SPORT probability |",
                  "|---|---:|---:|---:|---:|---:|"]
        for typ in sorted(params.index):
            row = params.loc[typ]
            lines.append(f"| {typ} | {_pct(row.residential_pct, 2)} | {_pct(row.nonres_pct, 2)} | "
                         f"{_pct(row.mixed_pct, 2)} | {int(row.assumed_residential_from_unknown)} | "
                         f"{_pct(row.sport_all_buildings_probability_pct, 3)} |")
        promotion_path = ROOT / 'districtgenerator/data/scenarios/Paper_3/Districts/provenance/promotion.json'
        status = ("Classification, generation parameters and documentation are integrated in the OSM workflow. "
                  "A separate parameter workbook is exported; the input "
                  "`districtgenerator/data/typdistrict_parameters.xlsx` is not overwritten by the workflow. "
                  "Existing districts, load profiles and optimization results therefore still represent "
                  "their original parameter snapshots. No new scenario or optimization results are implied "
                  "by these tables. EFH/MFH, age and retrofit parameters are unchanged.")
        if promotion_path.exists():
            promoted = json.loads(promotion_path.read_text(encoding='utf-8'))
            status = ("The corrected parameter workbook is now active, with SHA-256 "
                      f"`{promoted['workbook_sha256']}`. `Paper_3/Districts` contains 20 validated "
                      "district definitions per type A--F, H and I, 160 total. True random seed IDs "
                      "remain in filenames; `district_index.csv` lists positions 01--20 in numeric "
                      "seed order within each type. B/82 replaces B/11 and H/30 replaces H/20; "
                      "both replacements passed byte-identical replay. The 98 unchanged districts "
                      "retain their original definitions; 60 use revised definitions under the same "
                      "seed IDs. Original definitions, old layout images, the prior workbook and "
                      f"outdated profile files are archived in `{promoted['archive']}`. "
                      "Profiles for 3,985 buildings remain reusable; 815 buildings require profiles "
                      "(818 generation tasks because three new mixed-use buildings split into parts). "
                      "No new demand profiles or optimizations were calculated. SPORT demand "
                      "parameters were retained as requested. Historical optimization results have "
                      "not been changed. EFH/MFH, age and retrofit probability parameters are unchanged.")
            first20_path = promotion_path.parent / 'active_first20_selection.json'
            if first20_path.exists():
                selection = json.loads(first20_path.read_text(encoding='utf-8'))
                status = ("The frozen workbook used to generate the active districts has SHA-256 "
                          f"`{selection['workbook_sha256']}`. `Paper_3/Districts` now contains the first "
                          "20 valid seeds from an ascending search beginning at seed 1 for each type "
                          "A--F, H and I, 160 districts total. Two independent searches produced identical "
                          "seed lists and CSV/JSON definitions. Compared with the previous revised set, "
                          "158 definition pairs remain byte-identical; C/8 replaces C/29 and H/27 "
                          "replaces H/30. B/82 remains the twentieth valid B seed. True seed IDs remain "
                          "in filenames; `district_index.csv` lists positions 01--20 within each type. "
                          f"Removed definitions and the prior index/provenance are archived in `{selection['selection_archive']}`. "
                          "This final selection update did not change demand profiles, optimization results "
                          "or the parameter workbook. The selected set can reuse profiles for "
                          f"{selection['reusable_buildings']:,} buildings; {selection['buildings_needing_profiles']:,} "
                          f"buildings need profiles ({selection['generation_tasks']:,} split-building generation tasks). "
                          "Those counts include profiles already missing before the selection update. "
                          "SPORT demand parameters, EFH/MFH, age and retrofit probability parameters remain unchanged. "
                          "The active `provenance/active_first20_selection.json` records the independent "
                          "search, hashes and archive; the earlier `promotion.json` retains the original "
                          "OSM-revision activation history.")
        assumption_enabled = 'A' in params.index and params.loc['A', 'known'] > params.loc['A', 'observed_known']
        lines += ["", f"Type-A unknown-as-residential assignment in these tables: {'enabled' if assumption_enabled else 'disabled or no unknowns assigned'}. "
                  "The default policy enables it; --no-type-a-unknown-residential disables it. "
                  "For B--I, unknowns remain excluded from the main-use denominator. "
                  "The supported-subtype denominator, which excludes OTHER_NRB, remains unchanged "
                  "for every type. Classification corrections nevertheless change subtype weights.", "",
                  "### 17.3 Implementation status and reproduction", "",
                  status, "",
                  f"Prepared probabilities: `{generator_parameters.as_posix()}`. "
                  "The integrated OSM workflow exports `typdistrict_parameters.xlsx` and "
                  "`generation_parameters.json`, which records the assumption, source hash and exact cell edits. "
                  "The input workbook is never overwritten. Raw unknown-use labels remain unchanged.", "",
                  "Reproduce counts, parameters and documentation together from cached morphology:", "",
                  "```powershell",
                  'python examples/aachen_osm_pilot.py --reuse-analysis "examples/results/aachen_osm_building_sections_compact_v7" --output "NEW_OUTPUT_DIR" --verify-parameters "districtgenerator/data/typdistrict_parameters.xlsx"',
                  "```", ""]
    return "\n".join(lines)


def update_documentation_results(output_dir, use_results=None, generator_parameters=None, documentation=None):
    output_dir = Path(output_dir).resolve()
    required = ["manifest.json", "candidate_metrics.csv",
                "osm_building_split_percentages_by_type.csv",
                "osm_nrb_building_percentages_by_type.csv", "review_map.html"]
    missing = [name for name in required if not (output_dir / name).exists()]
    if missing:
        raise FileNotFoundError("Missing completed-run files: " + ", ".join(missing))
    use_results = Path(use_results).resolve() if use_results else None
    generator_parameters = Path(generator_parameters).resolve() if generator_parameters else None
    target = Path(documentation) if documentation is not None else DOCUMENTATION
    current = target.read_text(encoding="utf-8")
    if '## 17. Corrected SPORT weights' in current and not (use_results and generator_parameters):
        warnings.warn('Kept existing corrected documentation unchanged. Provide --use-results and '
                      '--generator-parameters to refresh it without dropping the documented assumptions.',
                      stacklevel=2)
        return target
    if RESULT_HEADING not in current:
        raise ValueError(f"Missing documentation heading: {RESULT_HEADING}")
    prefix = current.split(RESULT_HEADING, 1)[0].rstrip()
    target.write_text(prefix + "\n\n\n" + _result_text(output_dir, use_results, generator_parameters), encoding="utf-8")
    return target


if __name__ == "__main__":
    default = ROOT / "examples/results/aachen_osm_building_sections_compact_v7"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--morphology-results', type=Path, default=default)
    parser.add_argument('--use-results', type=Path)
    parser.add_argument('--generator-parameters', type=Path)
    args = parser.parse_args()
    print(f"Updated documentation results: {update_documentation_results(args.morphology_results, args.use_results, args.generator_parameters)}")
