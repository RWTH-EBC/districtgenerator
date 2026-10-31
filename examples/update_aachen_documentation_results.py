"""Populate method documentation with observed-use results and generation weights."""

from __future__ import annotations

import argparse
import json
import warnings
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
             f"The following results describe the `{scope}` analysis extent.", "",
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
    lines += ["Sections 12--15 describe building-use evidence, including accepted NRW "
              "gap fills when enrichment is enabled. Section 17 gives generation weights "
              "after excluding unknown and unsupported pure non-residential buildings. "
              "Evidence counts and generation denominators are reported separately.", ""]
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
              "| Type | Candidates | Buildings | Exact | Approximate | Unique compatible | Midpoint tie-break | Nearest outside ranges |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for typ in TYPES + ["UNCLASSIFIED"]:
        group = candidates[candidates["assigned_type"] == typ]
        buildings = _sum(group, "building_count")
        lines.append(
            f"| {typ} | {_int(len(group))} | {_int(buildings)} | "
            f"{_int((group.classification_quality == 'exact').sum())} | "
            f"{_int((group.classification_quality == 'approximate').sum())} | "
            f"{_int((group.assignment_reason == 'unique_compatible').sum())} | "
            f"{_int((group.assignment_reason == 'midpoint_tiebreak').sum())} | "
            f"{_int((group.assignment_reason == 'nearest_outside_ranges').sum())} |")
    quality = manifest.get("classification_quality", {})
    contexts = manifest.get("settlement_contexts", {})
    lines += ["",
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
    lines += ["", "## 16. Result interpretation and traceability", "",
              "The analysis reports candidate boundaries, building memberships, "
              "morphological indicators, type-assignment scores and building-use "
              "counts. Type-level summaries distinguish pooled building-weighted "
              "shares from district-weighted means. Source identifiers and input "
              "provenance support reproducibility; automated type labels require "
              "morphological review before treating candidates as validated real districts.", "",
              "OSM data attribution: © OpenStreetMap contributors, ODbL.", ""]
    if generator_parameters:
        params = pd.read_csv(generator_parameters)
        policy = 'generation' if 'generation' in set(params.policy) else 'halls_fitness_type_A_unknown_residential'
        params = params[params.policy == policy].set_index('typ')
        lines += ["## 17. Generation parameters", "",
                  "Generation weights distinguish observed building uses from modelling assumptions. "
                  "The subtype weights are conditional on the ten supported NRB categories; "
                  "OTHER_NRB is not part of this denominator. Unsupported pure non-residential "
                  "buildings are also excluded from main-use generation shares; residential "
                  "and mixed-use buildings are included. Raw evidence tables describe all observed uses.", "",
                  "### 17.1 SPORT weights", "",
                  "| Type | SPORT buildings | SPORT among supported NRB |",
                  "|---|---:|---:|"]
        for typ, row in params.sort_index().iterrows():
            lines.append(f"| {typ} | {int(row.sport)} | {_pct(row.SPORT_conditional_pct, 2)} |")
        lines += ["", "### 17.2 Main-use generation weights", "",
                  "| Type | Residential | Non-residential | Mixed | Unknown footprints assigned residential | Marginal SPORT probability |",
                  "|---|---:|---:|---:|---:|---:|"]
        for typ, row in params.sort_index().iterrows():
            lines.append(f"| {typ} | {_pct(row.residential_pct, 2)} | {_pct(row.nonres_pct, 2)} | "
                         f"{_pct(row.mixed_pct, 2)} | {int(row.assumed_residential_from_unknown)} | "
                         f"{_pct(row.sport_all_buildings_probability_pct, 3)} |")
        assumed = int(params.assumed_residential_from_unknown.sum())
        policy_text = (
            "This export uses an explicit type-A unknown-as-residential modelling assumption. "
            "Raw unknown labels are retained in the observed-use tables."
            if assumed else
            "All types A--I use the same represented-building denominator: residential plus mixed "
            "plus supported pure non-residential buildings. Unknown-use footprints remain unknown; "
            "unknowns and unsupported pure non-residential buildings are excluded from generation shares.")
        lines += ["", policy_text, "",
                  "### 17.3 Probability interpretation", "",
                  "The main-use weights and supported subtype weights are distinct conditional "
                  "distributions. Their product determines the marginal probability of a "
                  "supported non-residential archetype in a stochastic district draw, subject "
                  "to the mixed-use eligibility rules in Section 8. A weight does not prescribe "
                  "an exact number of buildings in any individual district.", ""]
    enrichment_path = output_dir / 'precluster_enrichment_manifest.json'
    evidence_path = output_dir / 'member_input_evidence.csv'
    if enrichment_path.exists() and evidence_path.exists():
        enrichment = json.loads(enrichment_path.read_text(encoding='utf-8'))
        evidence = pd.read_csv(evidence_path)
        before_known = int(evidence.osm_use_group.ne('unknown').sum())
        after_known = int(evidence.use_group.ne('unknown').sum())
        lines += ["", "## 18. NRW enrichment evidence", "",
                  "OSM footprints and roads supply geometry. The NRW municipal building "
                  "packages supply accepted supplementary attributes before clustering. "
                  "Specific OSM evidence takes priority; model-derived attributes remain "
                  "distinguishable from observations.", "",
                  "| Indicator for final candidate members | Count |", "|---|---:|",
                  f"| Member footprints | {_int(len(evidence))} |",
                  f"| Known main use from OSM | {_int(before_known)} |",
                  f"| Known main use from combined OSM/NRW evidence | {_int(after_known)} |",
                  f"| Remaining unknown main use | {_int(len(evidence)-after_known)} |",
                  f"| Explicit OSM storeys | {_int(evidence.observed_storeys.notna().sum())} |",
                  f"| Effective storeys including calculated NRW gaps | {_int(evidence.effective_storeys.notna().sum())} |",
                  f"| NRW residential-typology labels used | {_int(_sum(candidates, 'nrw_residential_typology_count'))} |",
                  f"| Main-use conflict flags | {_int(evidence.main_use_conflict.sum())} |",
                  f"| Storey conflict flags | {_int(evidence.storey_conflict.sum())} |", ""]
        utility = enrichment.get('utility_eligibility', {})
        if utility:
            lines += [f"The pre-clustering utility check flags {_int(utility['flagged'])} "
                      f"footprints, excludes {_int(utility['excluded_flags'])} utility-only "
                      f"footprints, and retains {_int(utility['retained_for_review'])} "
                      "mixed/conflicting flags for review. These counts refer to the "
                      "initial eligible population, not only final candidate members.", ""]
        lines += ["Source identifiers and content hashes identify the building datasets. "
                  "Age classes and energy-condition proxies are not used for clustering or "
                  "settlement-type scoring. Model-derived attributes are proxies, not "
                  "independently verified observations of individual buildings.", ""]
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
    if use_results is None and (output_dir / 'probabilities.csv').is_file():
        use_results = output_dir
    if generator_parameters is None and use_results is not None and (use_results / 'probabilities.csv').is_file():
        generator_parameters = use_results / 'probabilities.csv'
    target = Path(documentation) if documentation is not None else DOCUMENTATION
    current = target.read_text(encoding="utf-8")
    if ('## 17. Corrected SPORT weights' in current or '## 17. Generation parameters' in current) and not (use_results and generator_parameters):
        warnings.warn('Kept existing generation documentation unchanged. Provide --use-results and '
                      '--generator-parameters to retain the documented assumptions.',
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
