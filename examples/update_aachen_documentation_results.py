"""Generate Sections 10--16 of the Aachen documentation from a completed run."""

from __future__ import annotations

import json
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


def _result_text(output_dir):
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    candidates = pd.read_csv(output_dir / "candidate_metrics.csv")
    split = pd.read_csv(output_dir / "osm_building_split_percentages_by_type.csv")
    nrb = pd.read_csv(output_dir / "osm_nrb_building_percentages_by_type.csv")
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
              "| Type | Candidates | Buildings | Exact | Approximate | Unique compatible | Midpoint tie-break | Nearest outside ranges | Unknown use |",
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
    lines += ["", (f"Classification quality is exact for {_int(quality.get('exact', 0))}, "
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
              f"The documented outputs are stored in `{output_dir.as_posix()}`:", "",
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
    return "\n".join(lines)


def update_documentation_results(output_dir):
    output_dir = Path(output_dir).resolve()
    required = ["manifest.json", "candidate_metrics.csv",
                "osm_building_split_percentages_by_type.csv",
                "osm_nrb_building_percentages_by_type.csv", "review_map.html"]
    missing = [name for name in required if not (output_dir / name).exists()]
    if missing:
        raise FileNotFoundError("Missing completed-run files: " + ", ".join(missing))
    current = DOCUMENTATION.read_text(encoding="utf-8")
    if RESULT_HEADING not in current:
        raise ValueError(f"Missing documentation heading: {RESULT_HEADING}")
    prefix = current.split(RESULT_HEADING, 1)[0].rstrip()
    DOCUMENTATION.write_text(prefix + "\n\n\n" + _result_text(output_dir), encoding="utf-8")
    return DOCUMENTATION


if __name__ == "__main__":
    default = ROOT / "examples/results/aachen_osm_building_sections_compact_v7"
    print(f"Updated documentation results: {update_documentation_results(default)}")
