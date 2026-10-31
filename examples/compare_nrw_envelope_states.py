"""Compare NRW envelopes and propose construction-year/refurbishment pairs.

Evaluation updates and native scenario exports require explicit command modes.
Model-only checks never generate annual profiles or run optimization.
Run with --output pointing to a research-artifact directory. Public GET responses
are cached in one JSON file, allowing the comparison to be repeated offline.
"""

import argparse
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import date
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil
import random
import sys
import time
import re
import traceback
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pandas as pd
import pyogrio
from teaser.project import Project
import teaser


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
API = "https://www.gebaeuderechner.nrw.de/api/rpc/debug_building_part"
AGES = {1900: (0, 1899), 1945: (1900, 1945), 1960: (1946, 1960),
        1970: (1961, 1970), 1980: (1971, 1980), 1985: (1981, 1985),
        1995: (1986, 1995), 2000: (1996, 2000), 2005: (2001, 2005),
        2010: (2006, 2010), 2015: (2011, 2015), 2022: (2016, 2100)}
TYPES = {"EFH": "single_family_house", "RH": "terraced_house",
         "MFH": "multi_family_house", "GMFH": "apartment_block"}
STATES = ["standard", "retrofit", "adv_retrofit"]
COMPONENTS = {"wall": "outer_walls", "window": "windows",
              "roof": "rooftops", "floor": "ground_floors"}


def representatives(frame, all_strata=False):
    single = frame.copy()
    single["official_ids"] = single.official_ids.fillna("").astype(str).str.split(";")
    single = single.explode("official_ids")
    single = single[single.official_ids.str.fullmatch(r"\d+")].copy()
    single["fest_id"] = single.official_ids.astype(int)
    residential = single[(single.use_group == "residential") &
                         single.nrw_residential_typology.isin(TYPES)].dropna(
                             subset=["modelled_age_class", "modelled_condition"])
    groups = residential.groupby(["nrw_residential_typology", "modelled_age_class",
                                  "modelled_condition"], sort=True)
    pool = []
    for key, group in groups:
        row = group.sort_values(["district_id", "fest_id"]).iloc[0].to_dict()
        row["represented_buildings"] = len(group)
        row["stratum"] = key
        pool.append(row)
    chosen, covered = [], set()
    while pool and (all_strata or len(chosen) < 48):
        def priority(row):
            tokens = set(enumerate(row["stratum"]))
            return (len(tokens - covered), row["represented_buildings"], -row["fest_id"])
        row = max(pool, key=priority)
        pool.remove(row)
        covered.update(enumerate(row["stratum"]))
        chosen.append(row)
    nonres = single[(single.use_group == "nonres") & single.nrb_category.notna()]
    keys = ["nrb_category", "modelled_age_class", "modelled_condition"] if all_strata else ["nrb_category"]
    for _, group in nonres.groupby(keys, sort=True, dropna=False):
        row = group.sort_values(["district_id", "fest_id"]).iloc[0].to_dict()
        row["represented_buildings"] = len(group)
        chosen.append(row)
    return chosen


@lru_cache(maxsize=1)
def reference_bands():
    source = Path(teaser.__file__).parent / "data/input/inputdata/TypeElements_TABULA_DE.json"
    rows = []
    for element in json.loads(source.read_text()).values():
        match = re.fullmatch(r"tabula_de_(standard|retrofit|adv_retrofit)_([12])_(SFH|TH|MFH|AB)", element["construction_data"])
        if match:
            low, high = element["building_age_group"]
            rows.append(dict(archetype=match[3], year_min=low, year_max=high))
    return pd.DataFrame(rows).drop_duplicates()


def target_envelope(data):
    """Combine only active roof/floor boundaries, without counting both twice."""
    u = data["u_values"]
    envelope = data["calculated_demands"]["envelope"]
    weighting_basis = "NRW_active_envelope_areas"
    if not all(isinstance(envelope.get(name), (int, float)) and math.isfinite(envelope[name])
               for name in ["wall", "window"]):
        # A fixed proxy geometry supplies weights only, never simulation areas.
        typology = data["building_type"]
        low, high = AGES[data["construction_year_class"]]
        year = 1850 if low == 0 else (low + min(high, date.today().year)) // 2
        if typology == "GMFH" and year > 1978:
            typology = "MFH"
        archetype = {"EFH": "SFH", "RH": "TH", "MFH": "MFH", "GMFH": "AB"}[typology]
        minimum_year = int(reference_bands().loc[lambda frame: frame.archetype.eq(archetype), "year_min"].min())
        if year < minimum_year:
            year = (max(low, minimum_year) + min(high, date.today().year)) // 2
        project = Project()
        project.add_residential(construction_data="tabula_de_standard",
            geometry_data="tabula_de_" + TYPES[typology], name="weight_reference",
            year_of_construction=year, number_of_floors=2, height_of_floors=2.5,
            net_leased_area=200)
        envelope = {name: sum(e.area for z in project.buildings[0].thermal_zones
                             for e in getattr(z, attribute))
                    for name, attribute in [("wall", "outer_walls"), ("window", "windows"),
                                             ("roof", "rooftops"), ("floor_against_ground", "ground_floors")]}
        weighting_basis = "fixed_TABULA_proxy_area_proportions"
    target = {"wall": u["wall"], "window": u["window"]}
    areas = {"wall": envelope["wall"], "window": envelope["window"]}
    boundaries = {}
    for component, alternatives in [("roof", ["roof", "top_floor_ceiling"]),
                                    ("floor", ["floor_against_ground", "floor_against_basement"])]:
        active = [name for name in alternatives if (envelope.get(name) or 0) > 0]
        area = sum(envelope[name] for name in active)
        if area:
            target[component] = sum(envelope[name] * u[name] for name in active) / area
            areas[component] = area
            boundaries[component] = ";".join(active)
    if not all(math.isfinite(value) and value > 0 for value in target.values()):
        raise ValueError("NRW component U-values must be finite and positive.")
    if not all(math.isfinite(value) and value >= 0 for value in areas.values()):
        raise ValueError("NRW component areas must be finite and nonnegative.")
    if sum(areas.values()) <= 0:
        raise ValueError("The NRW reference has no active envelope area.")
    return target, areas, boundaries, weighting_basis


def comparison_scores(target, areas, reference):
    result = {}
    for metric, names in [("wall", ["wall"]), ("wall_window", ["wall", "window"]),
                          ("envelope", list(target))]:
        names = [name for name in names if areas[name] > 0]
        denominator = sum(areas[name] for name in names)
        if denominator:
            if not all(math.isfinite(reference[name]) and reference[name] > 0 for name in names):
                raise ValueError("Project component U-values must be finite and positive.")
            result[metric] = math.sqrt(sum(areas[name] * math.log(reference[name] / target[name]) ** 2
                                          for name in names) / denominator)
    return result


def select_assignment(scores, before_1860_year=None):
    """Choose a pair; exact score ties prefer the wider age interval, then state 0.

    An exact observed year is honoured by restricting candidate intervals to that
    singleton before this function is called. Fit quality never blocks selection.
    """
    candidates = scores[scores.metric.eq("envelope")].copy()
    if candidates.empty:
        return {"assignment_status": "no_supported_reference"}
    if not candidates.score.map(math.isfinite).all() or candidates.score.lt(0).any():
        raise ValueError("Candidate scores must be finite and nonnegative.")
    candidates["width"] = candidates.year_max - candidates.year_min
    candidates = candidates.sort_values(["score", "width", "state", "year_min"],
                                         ascending=[True, False, True, True])
    best = candidates.iloc[0]
    low, high = int(best.year_min), int(best.year_max)
    if low == 0 and before_1860_year is None:
        year, status = None, "representative_early_year_required"
    elif low == 0:
        if not 1 <= before_1860_year <= high:
            raise ValueError("The representative early year must be inside the chosen age band.")
        year, status = before_1860_year, "assigned"
    else:
        year, status = (low + high) // 2, "assigned"
    return dict(assignment_status=status, simulation_year=year,
                refurbishment_state=int(best.state), selected_year_min=low, selected_year_max=high,
                fit_score=float(best.score),
                runner_up_score=float(candidates.iloc[1].score) if len(candidates) > 1 else None,
                representative_year_basis="explicit_early_band_convention" if low == 0 else "overlap_midpoint")


def envelope_candidates(data, model_archetype, nonresidential, *, observed_year=None,
                        year_min=None, year_max=None, newer_apartment_block_as_mfh=False):
    """Build general envelope candidates, independent of district or address."""
    age = data["construction_year_class"]
    low, high = AGES[age]
    high = min(high, date.today().year)
    if year_min is not None:
        low = int(year_min)
    if year_max is not None:
        high = int(year_max)
    if observed_year is not None:
        low = high = int(observed_year)
    if low < 0 or low > high or high > date.today().year:
        raise ValueError("Invalid construction-year evidence range.")
    target, areas, boundaries, weighting_basis = target_envelope(data)
    actual_archetype = model_archetype
    fallback = False
    if model_archetype in TYPES:
        archetype = {"EFH": "SFH", "RH": "TH", "MFH": "MFH", "GMFH": "AB"}[model_archetype]
        bands = reference_bands()
        bands = bands[bands.archetype.eq(archetype)]
        overlap = bands[(bands.year_min <= high) & (bands.year_max >= low)]
        if overlap.empty and model_archetype == "GMFH" and newer_apartment_block_as_mfh:
            actual_archetype, fallback = "MFH", True
            bands = reference_bands()
            bands = bands[bands.archetype.eq("MFH")]
        reference = lambda year, state: residential_reference(actual_archetype, year, state)
    elif model_archetype in nonresidential:
        specs = nonresidential[model_archetype]["building_age_group"]
        bands = pd.DataFrame([dict(year_min=int(key.split(" - ")[0]),
                                   year_max=int(key.split(" - ")[1])) for key in specs])
        def reference(year, state):
            band = next(key for key in specs if int(key.split(" - ")[0]) <= year <= int(key.split(" - ")[1]))
            values = specs[band][["not retrofitted", "partially retrofitted", "completely retrofitted"][state]]
            return {component: values[field] for component, field in
                    [("wall", "u_aw"), ("window", "u_fen"), ("roof", "u_d_opak"), ("floor", "u_ug")]}
    else:
        raise ValueError("Unsupported simulation archetype: " + str(model_archetype))
    overlap = bands[(bands.year_min <= high) & (bands.year_max >= low)]
    components, scores = [], []
    edges = {low, high + 1}
    for band in overlap.itertuples(index=False):
        edges.update([max(low, int(band.year_min)), min(high + 1, int(band.year_max) + 1)])
    edges = sorted(edges)
    for start, next_start in zip(edges, edges[1:]):
        end = next_start - 1
        if not ((overlap.year_min <= start) & (overlap.year_max >= end)).any():
            continue
        for state in range(3):
            ref = reference(max(1, start), state)
            for component, value in target.items():
                components.append(dict(year_min=start, year_max=end, state=state,
                    component=component, nrw_u=value, project_u=ref[component],
                    nrw_area=areas[component], model_archetype=actual_archetype))
            for metric, score in comparison_scores(target, areas, ref).items():
                scores.append(dict(year_min=start, year_max=end, state=state,
                                   metric=metric, score=score))
    return components, scores, dict(model_archetype=actual_archetype,
        model_archetype_substituted=fallback, nrw_nonresidential_proxy=model_archetype not in TYPES,
        area_weighting_basis=weighting_basis,
        construction_evidence_min=low, construction_evidence_max=high,
        **{f"boundary_{key}": value for key, value in boundaries.items()})


def extend_complete_pools(folder, units, buildings, summary):
    """Add complete-input candidates without replacing the reviewed selection."""
    shortlist = pd.read_csv(folder.parent / "ten_per_pool_review_shortlist.csv")
    evidence = pd.read_csv(folder.parent / "real_district_building_inputs.csv")
    gaps = ["unknown_uses", "unsupported_uses", "missing_storeys", "missing_age_input", "missing_condition_proxy"]
    additional = shortlist[shortlist[gaps].sum(axis=1).eq(0) & ~shortlist.district_id.isin(summary.district_id)]
    extra = evidence[evidence.district_id.isin(additional.district_id)].copy()
    rows = []
    for source in extra.itertuples():
        portions = [("RESIDENTIAL" if source.use_group == "residential" else source.nrb_category, source.effective_storeys)]
        if source.use_group == "mixed":
            if source.effective_storeys < 2:
                raise ValueError("A one-storey mixed building needs an explicit area allocation.")
            portions = [("RESIDENTIAL", source.effective_storeys - 1), (source.nrb_category, 1)]
        for use, storeys in portions:
            observed = source.osm_year_evidence
            low, high = AGES.get(source.modelled_age_class, (None, None))
            if pd.notna(observed):
                low = high = int(observed)
            rows.append(dict(district_id=source.district_id, osm_key=source.osm_key,
                unit_id=source.osm_key if len(portions) == 1 else f"{source.osm_key}/{use}",
                simulation_group=f"{source.osm_key}/{use}", nrw_part_id=float("nan"), use=use,
                footprint_m2=source.footprint_m2, allocated_storeys=storeys,
                gross_floor_proxy_m2=source.footprint_m2 * storeys,
                modelled_age_class=source.modelled_age_class, observed_year=observed,
                year_min=float("nan"), year_max=float("nan"), effective_year_min=low,
                effective_year_max=min(high, date.today().year) if high is not None else None,
                age_basis="explicit_OSM_year" if pd.notna(observed) else "NRW_modelled_age_class",
                condition_code=source.modelled_condition, supported_use=True,
                storey_input_available=True, age_input_available=True, condition_input_available=True,
                allocation_input_available=True, all_four_inputs_available=True,
                known_nonres_archetype=use if use != "RESIDENTIAL" else "",
                use_basis="existing_one_business_floor_rule" if len(portions) > 1 else source.use_source,
                attribute_basis="complete_accepted_source_inputs", physical_building_id=source.osm_key,
                shared_building_envelope_required=len(portions) > 1))
    if rows:
        units = pd.concat([units, pd.DataFrame(rows)], ignore_index=True)
        buildings = pd.concat([buildings, extra], ignore_index=True)
        additions = []
        for district in additional.itertuples():
            subset = units[units.district_id.eq(district.district_id)]
            additions.append(dict(selection_pool=district.selection_pool,
                rank_within_type=district.selection_rank, district_id=district.district_id,
                buildings=district.buildings, evaluation_units=len(subset), buildings_with_gaps=0,
                unknown_uses=0, missing_storeys=0, missing_age_input=0, missing_condition_proxy=0,
                additional_review_buildings=0, unallocated_mixed_buildings=0,
                joint_input_coverage_pct=100., unresolved_refurbishment_units=len(subset), simulation_ready=False))
        summary = pd.concat([summary, pd.DataFrame(additions)], ignore_index=True)
    summary["raw_settlement_type"] = summary.district_id.map(shortlist.set_index("district_id").typ)
    summary = summary.sort_values(["selection_pool", "rank_within_type", "district_id"])
    if units.unit_id.duplicated().any() or buildings.osm_key.duplicated().any():
        raise ValueError("Expanded evaluation contains duplicate source units or physical buildings.")
    counts = summary.groupby("selection_pool").size()
    if len(counts) != 8 or not counts.between(5, 10).all():
        raise ValueError("The completed selection must have 5 to 10 districts in each of eight pools.")
    return units, buildings, summary


def apply_evaluation(args):
    """Assign reviewed evaluation units, preserving the evidence and a baseline."""
    folder = args.evaluation.resolve()
    units = pd.read_csv(folder / "evaluation_units.csv")
    buildings = pd.read_csv(folder / "evaluation_buildings.csv")
    selection_summary = pd.read_csv(folder / "candidate_summary.csv")
    if args.complete_pools:
        if args.apply:
            backup = folder / "provenance/pre_complete_pool_extension_20261031"
            backup.mkdir(parents=True, exist_ok=True)
            for name in ["evaluation_units.csv", "evaluation_buildings.csv", "candidate_summary.csv",
                         "evaluation_simulation_groups.csv", "source_manifest.json", "evaluation_preparation_manifest.json"]:
                if not (backup / name).exists():
                    shutil.copy2(folder / name, backup / name)
        units, buildings, selection_summary = extend_complete_pools(folder, units, buildings, selection_summary)
    raw = pd.read_pickle(args.source_cache / "osm_features_slim.pkl").to_crs(25832)
    decisions = json.loads((folder / "matching_review/review_decisions.json").read_text())
    decisions = {row["osm_key"]: row for row in decisions["decisions"]}
    parents = buildings.set_index(["district_id", "osm_key"])
    ids_by_unit = {}
    for row in units.itertuples():
        parent = parents.loc[(row.district_id, row.osm_key)]
        if pd.notna(row.nrw_part_id):
            ids = [int(row.nrw_part_id)]
        elif row.osm_key in decisions and decisions[row.osm_key].get("attribute_part_ids"):
            ids = decisions[row.osm_key]["attribute_part_ids"]
        else:
            ids = [int(value) for value in str(parent.official_ids).split(";") if value.isdigit()]
        ids_by_unit[row.unit_id] = ids
    ids = sorted({value for values in ids_by_unit.values() for value in values})
    official = {}
    for package in sorted(args.packages.glob("KWP-NRW_*_Shape.zip")):
        with ZipFile(package) as archive:
            layer = next(n for n in archive.namelist() if n.startswith("WBM-NRW_") and n.endswith(".shp"))
        frame = pyogrio.read_dataframe(f"/vsizip/{package.as_posix()}/{layer}",
            columns=["Fest_ID", "gml_id", "GEBAEUDETY", "sanierungs", "Shape_Area", "beheizt"],
            where='"Fest_ID" IN (' + ",".join(map(str, ids)) + ")", read_geometry=False)
        frame.columns = frame.columns.str.lower()
        official.update({int(row["fest_id"]): row for row in frame.to_dict("records")})
    cache_file = args.output / "public_model_responses.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    templates = {}
    for key, entry in sorted(cache.items(), key=lambda item: int(item[0])):
        data = entry.get("data", {})
        if data.get("building_type") in TYPES and data.get("construction_year_class") in AGES:
            templates.setdefault((data["building_type"], data["construction_year_class"], data["renovation_status"]), (int(key), data))
    nr = json.loads((ROOT / "districtgenerator/data/non_residential/non_residential_envelope.json").read_text())
    results = []
    for number, row in enumerate(units.itertuples(), 1):
        parent = parents.loc[(row.district_id, row.osm_key)]
        candidates = [official[value] for value in ids_by_unit[row.unit_id] if value in official]
        compatible = [source for source in candidates if source.get("sanierungs") == row.condition_code
                      and re.fullmatch(r"(EFH|RH|MFH|GMFH)_\d+", str(source.get("gebaeudety")))]
        source = max(compatible, key=lambda value: (value.get("shape_area") or 0, -value["fest_id"])) if compatible else None
        typology = str(parent.nrw_residential_typology)
        typology_basis = "NRW_residential_typology"
        if source:
            proxy_type, age = source["gebaeudety"].split("_")
            age = int(age)
            if typology not in TYPES:
                typology, typology_basis = proxy_type, "accepted_NRW_part_typology"
        else:
            proxy_type = typology
            age = int(row.modelled_age_class) if pd.notna(row.modelled_age_class) else None
        element, osm_id = row.osm_key.split("/")
        tags = raw.loc[(element, int(osm_id))]
        flats = pd.to_numeric(tags.get("building:flats"), errors="coerce")
        if row.use == "RESIDENTIAL":
            for tag in [tags.get("building:use"), tags.get("building")]:
                if pd.notna(flats):
                    typology = "EFH" if flats == 1 else "MFH" if flats >= 2 else typology
                    typology_basis = "OSM_building_flats"
                    break
                if tag in ["apartments", "dormitory"]:
                    typology, typology_basis = "MFH", "explicit_OSM_building_type"
                    break
                if tag in ["house", "detached", "bungalow", "farm", "semidetached_house", "terrace"]:
                    typology = "RH" if tag == "terrace" else "EFH"
                    typology_basis = "explicit_OSM_building_type"
                    break
            if typology not in TYPES and tags.get("building") == "residential":
                if row.footprint_m2 < 120:
                    typology = "EFH"
                elif row.footprint_m2 > 240:
                    typology = "MFH"
                typology_basis = "OSM_residential_footprint_inference"
        model_archetype = typology if row.use == "RESIDENTIAL" else row.use
        record = dict(unit_id=row.unit_id, district_id=row.district_id,
                      source_part_ids=";".join(map(str, ids_by_unit[row.unit_id])),
                      primary_source_part=int(source["fest_id"]) if source else None,
                      residential_typology_basis=typology_basis)
        if age not in AGES and pd.notna(row.effective_year_min):
            year = int(row.effective_year_min)
            age = next((code for code, (low, high) in AGES.items() if low <= year <= high), None)
        if proxy_type not in TYPES and typology in TYPES:
            proxy_type = typology
        reference_key = (proxy_type, age, row.condition_code)
        source_id = int(source["fest_id"]) if source else None
        entry = cache.get(str(source_id), {})
        data = entry.get("data")
        basis = "own_accepted_NRW_part"
        if data is not None:
            reference_id = source_id
        elif source is not None and not args.offline and "error" not in entry:
            url = API + "?" + urlencode({"_gml_id": source["gml_id"]})
            try:
                with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=30) as response:
                    data = json.load(response)
                if int(data["raw_building_part"]["fest_id"]) != source_id:
                    raise ValueError("Returned building identity mismatch")
                cache[str(source_id)] = {"url": url, "data": data}
                reference_id = source_id
            except Exception as error:
                cache[str(source_id)] = {"url": url, "error": str(error)}
            cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            time.sleep(0.2)
        if data is None and reference_key in templates:
            reference_id, data = templates[reference_key]
            data = deepcopy(data)
            data["calculated_demands"]["envelope"] = {"wall": None, "window": None}
            basis = "exact_same_type_age_condition_template"
        if data is None or model_archetype not in set(TYPES) | set(nr):
            results.append(dict(record, assignment_status="missing_reference_or_archetype"))
            continue
        if data.get("building_type") not in TYPES or data.get("construction_year_class") not in AGES:
            results.append(dict(record, assignment_status="unsupported_NRW_reference"))
            continue
        if data.get("renovation_status") != row.condition_code:
            results.append(dict(record, assignment_status="source_condition_disagreement"))
            continue
        _, scores, metadata = envelope_candidates(data, model_archetype, nr,
            year_min=int(row.effective_year_min) if pd.notna(row.effective_year_min) else None,
            year_max=int(row.effective_year_max) if pd.notna(row.effective_year_max) else None,
            newer_apartment_block_as_mfh=args.newer_apartment_block_as_mfh)
        proposal = select_assignment(pd.DataFrame(scores, columns=["metric", "score", "state", "year_min", "year_max"]),
                                     args.before_1860_year)
        results.append(dict(record, **metadata, **proposal,
            nrw_reference_basis=basis, nrw_reference_fest_id=reference_id,
            source_geometry_parts_differ=len({item["gebaeudety"] for item in compatible}) > 1))
        if number % 50 == 0:
            print(f"Evaluation assignments: {number}/{len(units)}", flush=True)
    assignments = pd.DataFrame(results)
    assignments.to_csv(args.output / "evaluation_assignment_proposals.csv", index=False)
    merged = units.drop(columns=[name for name in assignments.columns if name in units and name not in ["unit_id", "district_id"]])
    merged = merged.merge(assignments, on=["unit_id", "district_id"], validate="one_to_one")
    merged["refurbishment_mapping_status"] = merged.assignment_status
    merged["refurbishment_states_to_assess"] = ""
    merged["simulation_ready"] = merged.all_four_inputs_available & merged.allocation_input_available & merged.assignment_status.eq("assigned")
    if "envelope_original_simulation_group" not in merged:
        merged["envelope_original_simulation_group"] = merged.simulation_group
    for group_id, subset in merged.groupby("envelope_original_simulation_group"):
        variants = subset[["model_archetype", "simulation_year", "refurbishment_state"]].drop_duplicates()
        if len(variants) > 1:
            for index, unit in subset.iterrows():
                if unit.assignment_status == "assigned":
                    merged.loc[index, "simulation_group"] = (
                        f"{group_id}__{unit.model_archetype}_{int(unit.simulation_year)}_r{int(unit.refurbishment_state)}")
    merged["shared_building_envelope_required"] = merged.groupby("osm_key").simulation_group.transform("nunique").gt(1)
    groups = []
    for group_id, subset in merged.groupby("simulation_group", sort=True):
        first = subset.iloc[0]
        groups.append(dict(simulation_group=group_id, physical_building_id=first.osm_key,
            district_id=first.district_id, use=first.use, constituent_units=len(subset),
            gross_floor_proxy_m2=subset.gross_floor_proxy_m2.sum(),
            all_four_inputs_available=bool(subset.all_four_inputs_available.all()),
            allocation_input_available=bool(subset.allocation_input_available.all()),
            source_part_ids=";".join(str(int(value)) for value in subset.nrw_part_id.dropna()),
            shared_building_envelope_required=bool(subset.shared_building_envelope_required.any()),
            simulation_year=int(first.simulation_year) if pd.notna(first.simulation_year) else None,
            refurbishment_state=int(first.refurbishment_state) if pd.notna(first.refurbishment_state) else None,
            model_archetype=first.get("model_archetype"),
            simulation_ready=bool(subset.simulation_ready.all())))
    groups = pd.DataFrame(groups)
    summary = selection_summary
    for index, district in summary.iterrows():
        subset = merged[merged.district_id.eq(district.district_id)]
        summary.loc[index, "unresolved_refurbishment_units"] = int(subset.assignment_status.ne("assigned").sum())
        summary.loc[index, "simulation_ready"] = bool(subset.simulation_ready.all())
    merged.to_csv(args.output / "evaluation_units_assigned.csv", index=False)
    summary.to_csv(args.output / "evaluation_completeness.csv", index=False)
    groups.to_csv(args.output / "evaluation_groups_assigned.csv", index=False)
    if args.apply:
        backup = folder / "provenance/pre_envelope_assignment_20261031"
        backup.mkdir(parents=True, exist_ok=True)
        for name in ["evaluation_units.csv", "evaluation_buildings.csv", "candidate_summary.csv", "evaluation_simulation_groups.csv", "refurbishment_review.csv", "source_manifest.json", "evaluation_preparation_manifest.json"]:
            if not (backup / name).exists():
                shutil.copy2(folder / name, backup / name)
        merged.to_csv(folder / "evaluation_units.csv", index=False)
        summary.to_csv(folder / "candidate_summary.csv", index=False)
        groups.to_csv(folder / "evaluation_simulation_groups.csv", index=False)
        merged.to_csv(folder / "refurbishment_review.csv", index=False)
        for index, parent in buildings.iterrows():
            subset = merged[merged.osm_key.eq(parent.osm_key)]
            buildings.loc[index, "refurbishment_mapping_status"] = "assigned_per_evaluation_unit" if subset.simulation_ready.all() else "incomplete_evaluation_units"
            buildings.loc[index, "simulation_ready"] = bool(subset.simulation_ready.all())
            buildings.loc[index, "evaluation_refurbishment_states"] = ";".join(str(int(value)) for value in sorted(subset.refurbishment_state.dropna().unique()))
            buildings.loc[index, "evaluation_simulation_years"] = ";".join(str(int(value)) for value in sorted(subset.simulation_year.dropna().unique()))
            states = subset.refurbishment_state.dropna().unique()
            years = subset.simulation_year.dropna().unique()
            buildings.loc[index, "refurbishment_state"] = int(states[0]) if len(states) == 1 else float("nan")
            buildings.loc[index, "simulation_year"] = int(years[0]) if len(years) == 1 else float("nan")
        buildings.to_csv(folder / "evaluation_buildings.csv", index=False)
        manifest = dict(method="joint_envelope_age_refurbishment_v1", assignment_units=len(merged),
            physical_buildings=len(buildings), simulation_groups=len(groups),
            assignment_counts=merged.assignment_status.value_counts().to_dict(),
            before_1860_representative_year=args.before_1860_year,
            newer_apartment_block_as_mfh=args.newer_apartment_block_as_mfh,
            baseline=str(backup), script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            response_cache=str(cache_file), response_sha256=hashlib.sha256(cache_file.read_bytes()).hexdigest(),
            profiles_generated=False, native_scenario_exported=False,
            limitations=["NRW calculator parameters are model references, not measured building envelopes",
                         "Current calculator equivalence to the historical NRW heat model is not established",
                         "Non-residential envelopes may use labelled residential-like proxies",
                         "Shared physical envelopes must be handled before generating profiles"])
        (folder / "envelope_assignment_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        for name in ["source_manifest.json", "evaluation_preparation_manifest.json"]:
            saved = json.loads((folder / name).read_text())
            saved["refurbishment_mapping"] = "joint_envelope_age_refurbishment_v1"
            saved["envelope_assignment_manifest"] = "envelope_assignment_manifest.json"
            for output in saved.get("output_hashes", {}):
                saved["output_hashes"][output] = hashlib.sha256((folder / output).read_bytes()).hexdigest()
            (folder / name).write_text(json.dumps(saved, indent=2), encoding="utf-8")
        if args.export_real_districts:
            export_real_districts(args.export_real_districts, folder, merged, buildings, groups, summary, raw)
    print(assignments.assignment_status.value_counts().to_string())
    print(summary[["selection_pool", "district_id", "unresolved_refurbishment_units", "simulation_ready"]].to_string(index=False))


def export_real_districts(destination, evaluation, units, buildings, groups, summary, features):
    """Export real geometries and normalized inputs, not independent fake buildings."""
    import geopandas as gpd
    from shapely import wkt
    from shapely.ops import unary_union

    if not summary.simulation_ready.all():
        raise ValueError("Cannot export an input-complete dataset while assignments remain unresolved.")
    destination = destination.resolve()
    marker = destination / "dataset_manifest.json"
    if destination.exists() and any(destination.iterdir()) and not marker.exists():
        raise FileExistsError("Refusing to overwrite an unrelated real-district directory.")
    if marker.exists() and not set(json.loads(marker.read_text())["district_ids"]).issubset(set(summary.district_id)):
        raise ValueError("Existing export contains districts outside this selection; nothing is removed automatically.")
    destination.mkdir(parents=True, exist_ok=True)
    overrides = pd.read_csv(evaluation / "evaluation_geometry_overrides.csv")
    boundary_source = evaluation.parent / "candidate_districts.geojson"
    boundaries = json.loads(boundary_source.read_text())["features"]
    boundaries = {feature["properties"]["district_id"]: feature for feature in boundaries}
    for district in summary.itertuples():
        target = destination / district.district_id
        target.mkdir(exist_ok=True)
        physical = buildings[buildings.district_id.eq(district.district_id)].copy()
        geometries = []
        for row in physical.itertuples():
            replacement = overrides[overrides.osm_key.eq(row.osm_key)]
            if len(replacement):
                geometry = unary_union([wkt.loads(value) for value in replacement.geometry_wkt])
            else:
                element, osm_id = row.osm_key.split("/")
                geometry = features.loc[(element, int(osm_id))].geometry
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError("Invalid retained building geometry: " + row.osm_key)
            geometries.append(geometry)
        physical["position_x_epsg25832"] = [geometry.centroid.x for geometry in geometries]
        physical["position_y_epsg25832"] = [geometry.centroid.y for geometry in geometries]
        physical.to_csv(target / "buildings.csv", index=False)
        geo = gpd.GeoDataFrame(physical, geometry=geometries, crs=25832)
        (target / "buildings.geojson").write_text(geo.to_json(to_wgs84=True, drop_id=True), encoding="utf-8")
        (target / "boundary.geojson").write_text(json.dumps({"type": "FeatureCollection",
            "features": [boundaries[district.district_id]]}), encoding="utf-8")
        unit_subset = units[units.district_id.eq(district.district_id)].copy()
        unit_subset = unit_subset.merge(physical[["osm_key", "position_x_epsg25832", "position_y_epsg25832"]],
                                        on="osm_key", validate="many_to_one")
        unit_subset.to_csv(target / "thermal_units.csv", index=False)
        group_subset = groups[groups.district_id.eq(district.district_id)]
        group_subset.to_csv(target / "simulation_groups.csv", index=False)
        metadata = dict(district_id=district.district_id, settlement_type=district.selection_pool,
            physical_buildings=len(physical), thermal_use_units=len(unit_subset),
            compatible_simulation_groups=len(group_subset), input_complete=True,
            gross_floor_proxy_m2=float(unit_subset.gross_floor_proxy_m2.sum()),
            input_format="normalized_real_district_evaluation_v1",
            native_profile_scenario_ready=False,
            shared_envelope_handling_required=bool(unit_subset.shared_building_envelope_required.any()),
            separate_network_connections_for_units=False, profiles_generated=False)
        (target / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    summary.to_csv(destination / "district_index.csv", index=False)
    manifest = dict(format="normalized_real_district_evaluation_v1", district_ids=summary.district_id.tolist(),
        physical_buildings=len(buildings), thermal_use_units=len(units), compatible_simulation_groups=len(groups),
        evidence_source=str(evaluation.resolve()),
        assignment_manifest_sha256=hashlib.sha256((evaluation / "envelope_assignment_manifest.json").read_bytes()).hexdigest(),
        native_profile_scenario_exported=False, profiles_generated=False)
    marker.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Real district definitions exported: {destination}")


def export_native_scenarios(source, output, check_models=False):
    """Use native pre-split mixed rows and fixed floors; do not change the model."""
    source = source.resolve()
    code = {"EFH": "SFH", "RH": "TH", "MFH": "MFH", "GMFH": "AB"}
    index = pd.read_csv(source / "district_index.csv")
    manifest = json.loads((source / "dataset_manifest.json").read_text())
    reports, range_rows = [], []
    for district in index.itertuples():
        folder = source / district.district_id
        units = pd.read_csv(folder / "thermal_units.csv")
        physical = pd.read_csv(folder / "buildings.csv").set_index("osm_key")
        rows, mappings = [], []
        def append_row(subset, identifier, parent_id, mixed=False, role=""):
            if len(subset[["model_archetype", "simulation_year", "refurbishment_state", "use"]].drop_duplicates()) != 1:
                raise ValueError("Incompatible source units must not be collapsed into one scenario row.")
            first = subset.iloc[0]
            area = float(subset.gross_floor_proxy_m2.sum())
            footprint = float(subset.footprint_m2.sum())
            floors = area / footprint
            if not math.isclose(floors, round(floors), abs_tol=1e-8):
                raise ValueError("Different storey counts must remain separate in native scenarios.")
            floors = int(round(floors))
            building = code.get(first.model_archetype, first.model_archetype)
            position = physical.loc[first.osm_key]
            row = dict(id=identifier, position=f"({position.position_x_epsg25832}, {position.position_y_epsg25832})",
                building=building, year=int(first.simulation_year), retrofit=int(first.refurbishment_state),
                construction_type=2, night_setback=0, area=area, number_of_floors=floors,
                heater="heat_grid", cooling=0, EV=0, f_TES=15, f_BAT=0, f_PV1=0, f_PV2=0,
                f_STC=0, gamma_PV=0, ev_charging="on_demand", fixed_floors=floors,
                is_mixed_part=mixed, mixed_role=role, mixed_parent_id=parent_id,
                physical_building_id=first.osm_key, footprint_m2=footprint)
            rows.append(row)
            for unit in subset.itertuples():
                mappings.append(dict(scenario_row_id=identifier, source_unit_id=unit.unit_id,
                                     physical_building_id=unit.osm_key, area_m2=unit.gross_floor_proxy_m2))
        for number, (osm_key, building_units) in enumerate(units.groupby("osm_key", sort=True)):
            parent = f"b{number:03d}"
            remaining = building_units.copy()
            section_ids = building_units.nrw_part_id.fillna(-1).astype(int)
            for part_id, section in building_units.groupby(section_ids, sort=True):
                if len(section) == 2 and set(section.use) - {"RESIDENTIAL"} and section.use.eq("RESIDENTIAL").sum() == 1:
                    mixed_parent = parent if part_id == -1 else f"{parent}_p{part_id}"
                    residential = section[section.use.eq("RESIDENTIAL")]
                    business = section[~section.use.eq("RESIDENTIAL")]
                    append_row(residential, mixed_parent, mixed_parent, True, "main")
                    append_row(business, mixed_parent + "_secondary", mixed_parent, True, "secondary")
                    remaining = remaining.drop(section.index)
                elif len(section) > 1 and section.use.nunique() > 1:
                    raise ValueError("Source section is not representable by the existing two-use model.")
            plain_groups = list(remaining.groupby(["simulation_group", "allocated_storeys"], sort=True))
            for group_number, (_, subset) in enumerate(plain_groups):
                identifier = parent if len(remaining) == len(building_units) and len(plain_groups) == 1 else f"{parent}_s{group_number}"
                append_row(subset, identifier, identifier)
        scenario = pd.DataFrame(rows)
        links = pd.DataFrame(mappings)
        links["absorbed_small_section"] = False
        merge_records = []
        residential_codes = ["SFH", "TH", "MFH", "AB"]
        for physical_id, section_rows in scenario.groupby("physical_building_id", sort=True):
            residential = section_rows[section_rows.building.isin(residential_codes)]
            large = residential[residential.area.ge(43.5)]
            if large.empty:
                continue
            target_index = large.sort_values(["area", "id"], ascending=[False, True]).index[0]
            target_id = scenario.loc[target_index, "id"]
            small = residential[residential.area.lt(43.5) & ~residential.is_mixed_part]
            for small_index, small_row in small.iterrows():
                scenario.loc[target_index, "area"] += small_row.area
                scenario.loc[target_index, "footprint_m2"] = scenario.loc[target_index, "area"] / scenario.loc[target_index, "fixed_floors"]
                affected = links.scenario_row_id.eq(small_row.id)
                links.loc[affected, "scenario_row_id"] = target_id
                links.loc[affected, "absorbed_small_section"] = True
                merge_records.append(dict(physical_building_id=physical_id, absorbed_row=small_row.id,
                    retained_row=target_id, transferred_area_m2=float(small_row.area),
                    source_year=int(small_row.year), source_refurbishment=int(small_row.retrofit),
                    retained_year=int(scenario.loc[target_index, "year"]),
                    retained_refurbishment=int(scenario.loc[target_index, "retrofit"])))
                scenario = scenario.drop(small_index)
        scenario = scenario.reset_index(drop=True)
        if scenario.id.duplicated().any() or set(links.source_unit_id) != set(units.unit_id) or links.source_unit_id.duplicated().any():
            raise ValueError("Scenario export must cover each original unit exactly once.")
        if not math.isclose(scenario.area.sum(), units.gross_floor_proxy_m2.sum(), abs_tol=1e-7):
            raise ValueError("Scenario export changed the floor area.")
        source_areas = units.groupby("osm_key").gross_floor_proxy_m2.sum()
        exported_areas = scenario.groupby("physical_building_id").area.sum()
        if set(source_areas.index) != set(exported_areas.index) or any(
                not math.isclose(float(area), float(exported_areas.loc[key]), abs_tol=1e-7)
                for key, area in source_areas.items()):
            raise ValueError("Small-section merging changed a physical building's total floor area.")
        for row in scenario.itertuples():
            direct = links.scenario_row_id.eq(row.id) & ~links.absorbed_small_section
            original = units[units.unit_id.isin(links.loc[direct, "source_unit_id"])]
            if not original.simulation_year.eq(row.year).all() or not original.refurbishment_state.eq(row.retrofit).all():
                raise ValueError("Scenario export changed a year or refurbishment state.")
            if not original.allocated_storeys.eq(row.fixed_floors).all():
                raise ValueError("Scenario export changed an allocated storey count.")
        name = f"real_district_{str(district.selection_pool).replace('/', '_')}_{district.district_id}"
        path = source / (name + ".csv")
        scenario.to_csv(path, sep=";", index=False)
        links.to_csv(folder / "scenario_unit_mapping.csv", index=False)
        pd.DataFrame(merge_records, columns=["physical_building_id", "absorbed_row", "retained_row", "transferred_area_m2",
            "source_year", "source_refurbishment", "retained_year", "retained_refurbishment"]).to_csv(folder / "small_section_merges.csv", index=False)
        metadata = dict(source="real", district_id=district.district_id, physical_buildings=len(physical),
            scenario_rows=len(scenario), area_basis="approved footprint times allocated storeys; gross-floor proxy",
            archetypal_defaults=dict(construction_type=2, night_setback=0, building_PV=0, EV=0),
            profiles_generated=False, network_topology_exported=False,
            small_residential_section_threshold_m2=43.5, small_sections_absorbed=len(merge_records),
            area_caps_applied=False,
            physical_connection_authority="physical_building_id; sections are not extra district connections")
        (source / (name + ".json")).write_text(json.dumps(dict(metadata=metadata,
            parameters=dict(district_type=getattr(district, "raw_settlement_type", district.selection_pool), district_id=district.district_id,
                            source="real", physical_buildings=len(physical)))), encoding="utf-8")
        numeric = scenario[["area", "footprint_m2", "fixed_floors", "year", "retrofit"]]
        for field in numeric:
            range_rows.append(dict(district_id=district.district_id, pool=district.selection_pool, field=field,
                                   minimum=float(numeric[field].min()), maximum=float(numeric[field].max())))
        report = dict(district_id=district.district_id, scenario=name, physical_buildings=len(physical),
            scenario_rows=len(scenario), source_units=len(units), total_area_m2=float(scenario.area.sum()),
            mixed_pairs=int(scenario.is_mixed_part.sum() // 2), model_check="not_run")
        report["small_sections_absorbed"] = len(merge_records)
        if check_models:
            from districtgenerator.classes import Datahandler
            import numpy as np
            log = output / (name + "_model_check.log")
            data = None
            try:
                with log.open("w", encoding="utf-8") as stream, redirect_stdout(stream), redirect_stderr(stream):
                    unsafe = scenario[scenario.building.isin(["MFH", "AB"]) & scenario.area.map(lambda value: round(value / 29) < 2)]
                    if len(unsafe):
                        report["problematic_scenario_rows"] = ";".join(unsafe.id)
                        raise ValueError("Existing MFH/AB initializer cannot obtain two flats for these areas: "
                                         + "; ".join(f"{row.id}={row.area:.3f} m2" for row in unsafe.itertuples()))
                    seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
                    random.seed(seed)
                    np.random.seed(seed)
                    data = Datahandler(scenario_name=name, scenario_file_path=str(source),
                        env_path=".env.CONFIG.PAPER", resultPath=str(output / "model_checks" / name))
                    data.generateEnvironment()
                    data.initializeBuildings()
                    if len(data.district) != len(scenario):
                        raise ValueError("The model silently changed the imported scenario row count.")
                    data.generateBuildings()
                    for building in data.district:
                        features = building["buildingFeatures"]
                        expected = scenario.set_index("id").loc[str(features["id"])]
                        for field in ["area", "year", "retrofit", "fixed_floors"]:
                            if not math.isclose(float(features[field]), float(expected[field]), abs_tol=1e-8):
                                raise ValueError("Model initialization changed " + field)
                        if not math.isfinite(float(building["envelope"].heatload)):
                            raise ValueError("Nonfinite design heat load.")
                    report["model_check"] = "passed"
                    report["total_design_heatload_W"] = float(sum(b["envelope"].heatload for b in data.district))
            except Exception as error:
                report["model_check"] = "failed"
                report["model_error"] = f"{type(error).__name__}: {error}"
                if data is not None and "problematic_scenario_rows" not in report:
                    pending = [building for building in data.district if "envelope" not in building]
                    if pending:
                        report["problematic_scenario_rows"] = str(pending[0]["buildingFeatures"]["id"])
                with log.open("a", encoding="utf-8") as stream:
                    traceback.print_exc(file=stream)
            report["model_log"] = str(log)
        reports.append(report)
        print(f"Native scenario {district.district_id}: {len(scenario)} rows; model check {report['model_check']}", flush=True)
        meta_file = folder / "metadata.json"
        meta = json.loads(meta_file.read_text())
        meta.update(native_scenario=name, native_scenario_exported=True,
                    native_profile_scenario_ready=report["model_check"] == "passed")
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    pd.DataFrame(reports).to_csv(output / "native_scenario_checks.csv", index=False)
    pd.DataFrame(range_rows).to_csv(output / "native_scenario_ranges.csv", index=False)
    by_district = {row["district_id"]: row for row in reports}
    index["native_scenario"] = index.district_id.map(lambda key: by_district[key]["scenario"])
    index["native_model_check"] = index.district_id.map(lambda key: by_district[key]["model_check"])
    index["native_profile_scenario_ready"] = index.native_model_check.eq("passed")
    index.to_csv(source / "district_index.csv", index=False)
    readiness = index.groupby("selection_pool").agg(prepared_districts=("district_id", "size"),
        model_checks_passed=("native_profile_scenario_ready", "sum"))
    readiness["remaining"] = readiness.prepared_districts - readiness.model_checks_passed
    readiness.to_csv(source / "profile_readiness_by_pool.csv")
    manifest["native_profile_scenario_exported"] = True
    manifest["model_checks"] = {row["district_id"]: row["model_check"] for row in reports}
    manifest["small_sections_absorbed"] = sum(row["small_sections_absorbed"] for row in reports)
    manifest["area_caps_applied"] = False
    manifest["whole_building_areas_preserved"] = True
    (source / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def plot_real_floor_areas(source, output):
    """Plot uncapped whole-building areas for reviewed and complete-input pools."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter
    import numpy as np

    source = source.resolve()
    dataset = json.loads((source / "dataset_manifest.json").read_text())
    evaluation = Path(dataset["evidence_source"])
    analysis = evaluation.parent
    selected = pd.read_csv(source / "district_index.csv")
    shortlist = pd.read_csv(analysis / "ten_per_pool_review_shortlist.csv")
    evidence = pd.read_csv(analysis / "real_district_building_inputs.csv")
    records, sources = [], [source / "district_index.csv", analysis / "ten_per_pool_review_shortlist.csv",
                            analysis / "real_district_building_inputs.csv"]
    for district in selected.itertuples():
        path = source / district.district_id / "thermal_units.csv"
        sources.append(path)
        units = pd.read_csv(path)
        whole = units.groupby("osm_key", as_index=False).gross_floor_proxy_m2.sum()
        whole = whole.rename(columns={"gross_floor_proxy_m2": "floor_area_m2"})
        whole["district_id"] = district.district_id
        whole["pool"] = district.selection_pool
        whole["input_basis"] = "reviewed_units_summed_once_per_OSM_building"
        records.append(whole)
    gaps = ["unknown_uses", "unsupported_uses", "missing_storeys", "missing_age_input", "missing_condition_proxy"]
    additional = shortlist[shortlist[gaps].sum(axis=1).eq(0) & ~shortlist.district_id.isin(selected.district_id)]
    extra = evidence[evidence.district_id.isin(additional.district_id)].copy()
    extra = extra.merge(additional[["district_id", "selection_pool"]], on="district_id", validate="many_to_one")
    extra = extra.rename(columns={"gross_floor_proxy_m2": "floor_area_m2", "selection_pool": "pool"})
    extra["input_basis"] = "complete_source_inputs_pending_native_model_validation"
    records.append(extra[["district_id", "osm_key", "pool", "floor_area_m2", "input_basis"]])
    buildings = pd.concat(records, ignore_index=True)
    if buildings.duplicated(["district_id", "osm_key"]).any() or buildings.osm_key.duplicated().any():
        raise ValueError("A physical building occurs more than once in the area distribution.")
    if not np.isfinite(buildings.floor_area_m2).all() or not buildings.floor_area_m2.gt(0).all():
        raise ValueError("All plotted floor areas must be finite and positive.")
    order = ["A", "B", "C", "D", "E", "F/G", "H", "I"]
    summary = buildings.groupby("pool").agg(districts=("district_id", "nunique"),
        buildings=("osm_key", "size"), minimum_m2=("floor_area_m2", "min"),
        median_m2=("floor_area_m2", "median"), mean_m2=("floor_area_m2", "mean"),
        maximum_m2=("floor_area_m2", "max")).reindex(order)
    if summary.isna().any().any() or not summary.districts.between(5, 10).all():
        raise ValueError("Every evaluation pool must contain 5 to 10 input-complete districts.")
    buildings.to_csv(output / "real_building_floor_areas.csv", index=False)
    summary.to_csv(output / "real_building_floor_area_summary.csv")
    bins = np.geomspace(buildings.floor_area_m2.min() * .9, buildings.floor_area_m2.max() * 1.1, 25)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(4, 2, figsize=(12.5, 13), sharex=True, sharey=True)
    median_color, mean_color = "#087f73", "#c85a17"
    def draw(ax, pool):
        values = buildings.loc[buildings.pool.eq(pool), "floor_area_m2"].to_numpy()
        stats = summary.loc[pool]
        ax.hist(values, bins=bins, weights=np.full(len(values), 100 / len(values)),
                color="#d5dde3", edgecolor="#6a7a87", linewidth=.65)
        ax.axvline(stats.median_m2, color=median_color, linewidth=2.1)
        ax.axvline(stats.mean_m2, color=mean_color, linewidth=2.1, linestyle="--")
        ax.set_xscale("log")
        ax.set_xlim(bins[0], bins[-1])
        ax.set_title(f"{pool}  |  {int(stats.districts)} districts, {int(stats.buildings)} buildings", loc="left", fontsize=12, fontweight="bold")
        ax.text(.97, .93, f"Median: {stats.median_m2:,.1f} m$^2$\nMean: {stats.mean_m2:,.1f} m$^2$",
                transform=ax.transAxes, ha="right", va="top", fontsize=10)
        ax.grid(axis="y", color="#dbe0e4", linewidth=.55)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
    for ax, pool in zip(axes.flat, order):
        draw(ax, pool)
    fig.suptitle("Real districts: floor area per physical building", fontsize=17, fontweight="bold", y=.99)
    fig.text(.5, .955, f"{buildings.district_id.nunique()} input-complete districts; {len(buildings):,} buildings; original areas, no caps",
             ha="center", fontsize=11, color="#48545d")
    fig.legend(handles=[Line2D([0], [0], color=median_color, lw=2.1, label="Median"),
                        Line2D([0], [0], color=mean_color, lw=2.1, ls="--", label="Mean")],
               loc="upper center", bbox_to_anchor=(.5, .94), ncol=2, frameon=False)
    fig.supxlabel("Total floor area per physical building (m$^2$; logarithmic scale)", fontsize=12)
    fig.supylabel("Share of buildings (%)", fontsize=12)
    fig.tight_layout(rect=(.025, .03, 1, .91), h_pad=2.1, w_pad=2)
    fig.savefig(output / "real_floor_area_distributions_by_type.png", dpi=180)
    fig.savefig(output / "real_floor_area_distributions_by_type.svg")
    plt.close(fig)
    for pool in order:
        fig, ax = plt.subplots(figsize=(7, 4.6))
        draw(ax, pool)
        ax.set_xlabel("Total building floor area (m$^2$; logarithmic scale)")
        ax.set_ylabel("Share of buildings (%)")
        fig.tight_layout()
        fig.savefig(output / f"real_floor_area_distribution_{pool.replace('/', '_')}.png", dpi=180)
        plt.close(fig)
    manifest = dict(scope="reviewed districts plus remaining candidates with complete basic source inputs",
        native_model_readiness_not_implied=True, area_basis="footprint times storeys; parts summed per physical OSM building",
        area_caps_applied=False, districts=int(buildings.district_id.nunique()), buildings=len(buildings),
        sources={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})
    (output / "floor_area_plot_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(summary.to_string(float_format=lambda value: f"{value:,.2f}"))


@lru_cache(maxsize=None)
def residential_reference(typology, year, state):
    project = Project()
    project.add_residential(construction_data="tabula_de_" + STATES[state],
                            geometry_data="tabula_de_" + TYPES[typology],
                            name="reference", year_of_construction=year,
                            number_of_floors=2, height_of_floors=2.5,
                            net_leased_area=200)
    result = {}
    for component, attribute in COMPONENTS.items():
        elements = [e for zone in project.buildings[0].thermal_zones
                    for e in getattr(zone, attribute)]
        area = sum(e.area for e in elements)
        if area > 0:
            result[component] = sum(e.area * e.u_value for e in elements) / area
    return result


def export_real_network_geometry(source, source_cache, output):
    """Export cached metric roads and the shared synthetic/real hub heuristic."""
    import ast
    import geopandas as gpd
    import networkx as nx
    import shapely
    from districtgenerator.functions.design_network_with_road import choose_energy_hub_position

    cache = source_cache / "osm_features_slim.pkl"
    source_hash = hashlib.sha256(cache.read_bytes()).hexdigest()
    features = pd.read_pickle(cache).to_crs(25832)
    road_types = {"primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "pedestrian"}
    roads = features.loc[features.highway.fillna("").isin(road_types)
                         & features.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
    del features
    reports = []
    backup = output / "network_geometry_input_backup"
    backup.mkdir(parents=True, exist_ok=True)
    for district in pd.read_csv(source / "district_index.csv").itertuples():
        csv_path = source / (district.native_scenario + ".csv")
        json_path = csv_path.with_suffix(".json")
        metadata = json.loads(json_path.read_text(encoding="utf-8"))
        if metadata.get("metadata", {}).get("source") != "real":
            raise ValueError(f"Not a real scenario: {json_path}")
        frame = pd.read_csv(csv_path, sep=";").drop_duplicates("physical_building_id")
        points = [shapely.Point(ast.literal_eval(p)) for p in frame.position]
        folder = source / district.district_id
        boundary = gpd.read_file(folder / "boundary.geojson").to_crs(25832).geometry.union_all()
        corridor = boundary.buffer(100.0)
        nearby = roads.iloc[roads.sindex.query(corridor, predicate="intersects")]
        geometry = shapely.union_all(shapely.intersection(nearby.geometry.to_numpy(), corridor))
        segments = []
        for line in shapely.get_parts(geometry):
            if line.geom_type != "LineString":
                continue
            for a, b in zip(line.coords[:-1], line.coords[1:]):
                segment = shapely.LineString([tuple(round(v, 6) for v in a[:2]), tuple(round(v, 6) for v in b[:2])])
                if segment.length > .01:
                    segments.append(segment)
        graph = nx.Graph()
        for segment in segments:
            graph.add_edge(tuple(segment.coords[0]), tuple(segment.coords[-1]))
        report = dict(district_id=district.district_id, scenario=district.native_scenario,
                      physical_buildings=len(frame), csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest())
        if not segments:
            reports.append(dict(report, status="no_cached_roads"))
            continue
        components = list(nx.connected_components(graph))
        component_by_node = {node: i for i, nodes in enumerate(components) for node in nodes}
        nearest = shapely.STRtree(segments).nearest(points)
        serving = {component_by_node[tuple(segments[int(i)].coords[0])] for i in nearest}
        if len(serving) != 1:
            reports.append(dict(report, status="disconnected_required_roads", serving_components=len(serving)))
            continue
        serving_nodes = components[next(iter(serving))]
        segments = [line for line in segments if tuple(line.coords[0]) in serving_nodes]
        hub, degree = choose_energy_hub_position(segments, points)
        lines = [dict(id=i, start=list(line.coords[0]), end=list(line.coords[-1]), length=line.length)
                 for i, line in enumerate(segments)]
        if not (backup / json_path.name).exists():
            shutil.copy2(json_path, backup / json_path.name)
        metadata["values"] = dict(lines_info=lines, energy_hub=dict(position=hub))
        metadata["metadata"].update(network_geometry_exported=True,
            network_geometry=dict(crs="EPSG:25832", source_feature_cache_sha256=source_hash,
                road_buffer_m=100.0, hub_rule="highest road degree; geometry-center tie break",
                hub_road_degree=degree, hub_site_verified=False, recommended_topology="road"))
        json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        gpd.GeoDataFrame({"id": range(len(segments))}, geometry=segments, crs=25832).to_file(
            folder / "roads.geojson", driver="GeoJSON")
        reports.append(dict(report, status="ready", road_segments=len(segments), hub_degree=degree))
    pd.DataFrame(reports).to_csv(output / "network_geometry_checks.csv", index=False)
    ready = sum(row["status"] == "ready" for row in reports)
    manifest_path = source / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["network_geometry"] = dict(ready_districts=ready, total_districts=len(reports),
        crs="EPSG:25832", source_feature_cache_sha256=source_hash, hub_site_verified=False)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Real network geometry ready: {ready}/{len(reports)}; scenario CSVs and profiles unchanged.")
    if ready != len(reports):
        raise ValueError("Some required road connections are unresolved; see network_geometry_checks.csv. No road bridges were invented.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / "examples/results/"
                        "aachen_osm_building_sections_compact_v7/real_district_building_inputs.csv")
    parser.add_argument("--packages", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--plot-floor-areas", type=Path, help="Plot physical-building areas for all complete-input evaluation pools.")
    parser.add_argument("--native-scenarios", type=Path, help="Export a prepared real-district dataset in the native scenario format.")
    parser.add_argument("--network-geometry", type=Path, help="With --apply, add cached roads and hub coordinates to real scenarios; no profiles are generated.")
    parser.add_argument("--check-models", action="store_true", help="Build models only; never generate annual profiles.")
    parser.add_argument("--evaluation", type=Path, help="Apply the general rule to reviewed evaluation units.")
    parser.add_argument("--complete-pools", action="store_true", help="Include all other shortlisted candidates with complete basic inputs.")
    parser.add_argument("--source-cache", type=Path, default=ROOT / "examples/results/aachen_osm_pilot_v2")
    parser.add_argument("--apply", action="store_true", help="Update evaluation tables after preserving their baseline.")
    parser.add_argument("--export-real-districts", type=Path,
                        help="With --evaluation --apply, export real geometries and normalized district inputs.")
    parser.add_argument("--all-strata", action="store_true",
                        help="Check every observed type/age/condition combination instead of a sample.")
    parser.add_argument("--before-1860-year", type=int,
                        help="Explicit representative year for a selected open-ended early band.")
    parser.add_argument("--newer-apartment-block-as-mfh", action="store_true",
                        help="Use the MFH archetype when no AB reference covers the NRW age interval.")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.network_geometry:
        if not args.apply:
            parser.error("--network-geometry requires --apply")
        export_real_network_geometry(args.network_geometry, args.source_cache, args.output)
        return
    if args.plot_floor_areas:
        plot_real_floor_areas(args.plot_floor_areas, args.output)
        return
    if args.native_scenarios:
        export_native_scenarios(args.native_scenarios, args.output, args.check_models)
        export_real_network_geometry(args.native_scenarios, args.source_cache, args.output)
        return
    if args.packages is None:
        parser.error("--packages is required for NRW envelope assignment")
    if args.export_real_districts and not (args.evaluation and args.apply):
        parser.error("--export-real-districts requires --evaluation --apply")
    if args.evaluation:
        apply_evaluation(args)
        return
    if args.apply:
        parser.error("--apply requires --evaluation")
    selected = representatives(pd.read_csv(args.inputs), args.all_strata)
    ids = {row["fest_id"] for row in selected}
    official = {}
    for package in sorted(args.packages.glob("KWP-NRW_*_Shape.zip")):
        with ZipFile(package) as archive:
            layer = next(n for n in archive.namelist() if n.startswith("WBM-NRW_") and n.endswith(".shp"))
        records = pyogrio.read_dataframe(f"/vsizip/{package.as_posix()}/{layer}",
                    columns=["Fest_ID", "gml_id", "GEBAEUDETY", "sanierungs", "WG_NWG"],
                    where='"Fest_ID" IN (' + ",".join(map(str, sorted(ids))) + ")",
                    read_geometry=False)
        records.columns = records.columns.str.lower()
        for row in records.to_dict("records"):
            official[int(row["fest_id"])] = row
    cache_path = args.output / "public_model_responses.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for number, row in enumerate(selected, 1):
        key = str(row["fest_id"])
        if row["fest_id"] not in official:
            raise ValueError("Source GML ID not found: " + key)
        if key not in cache:
            if args.offline:
                raise ValueError("Missing cached response: " + key)
            url = API + "?" + urlencode({"_gml_id": official[row["fest_id"]]["gml_id"]})
            try:
                with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=30) as response:
                    data = json.load(response)
                cache[key] = {"url": url, "data": data}
            except Exception as error:
                cache[key] = {"url": url, "error": str(error)}
            cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            time.sleep(0.2)
        print(f"Public sample {number}/{len(selected)}: {key}", flush=True)

    nr = json.loads((ROOT / "districtgenerator/data/non_residential/non_residential_envelope.json").read_text())
    sample_rows, component_rows, score_rows, assignments = [], [], [], []
    for row in selected:
        key = str(row["fest_id"])
        entry = cache[key]
        base = {"fest_id": int(key), "district_id": row["district_id"],
                "use_group": row["use_group"], "nrb_category": row.get("nrb_category"),
                "source_type": official[int(key)].get("gebaeudety"),
                "source_condition": official[int(key)].get("sanierungs")}
        reference_basis, reference_id = "own_NRW_record", int(key)
        if "error" in entry:
            peers = [(int(peer_id), peer) for peer_id, peer in cache.items()
                     if peer.get("data", {}).get("raw_building_part", {}).get("gebaeudetyp") == base["source_type"]
                     and peer.get("data", {}).get("renovation_status") == base["source_condition"]]
            if not peers:
                sample_rows.append(dict(base, status="missing_NRW_reference", reason=entry["error"]))
                assignments.append(dict(base, assignment_status="missing_NRW_reference"))
                continue
            reference_id, entry = min(peers)
            reference_basis = "exact_same_type_age_condition_template"
        data = deepcopy(entry["data"])
        if reference_basis != "own_NRW_record":
            data["calculated_demands"]["envelope"] = {"wall": None, "window": None}
        raw = data.get("raw_building_part", {})
        if int(raw.get("fest_id", -1)) != reference_id or (
                reference_basis == "own_NRW_record" and raw.get("gml_id") != official[int(key)]["gml_id"]):
            raise ValueError("Returned identity does not match requested public record: " + key)
        base.update(calculator_type=data.get("building_type"),
                    calculator_age=data.get("construction_year_class"),
                    calculator_condition=data.get("renovation_status"),
                    calculator_source_sector=raw.get("wg_nwg"),
                    nrw_reference_basis=reference_basis, nrw_reference_fest_id=reference_id)
        typology = data.get("building_type")
        age = data.get("construction_year_class")
        if typology not in TYPES or age not in AGES:
            sample_rows.append(dict(base, status="unsupported_calculator_reference"))
            assignments.append(dict(base, assignment_status="unsupported_calculator_reference"))
            continue
        source_age = str(official[int(key)].get("gebaeudety", ""))
        expected = f"{typology}_{age}"
        if source_age != expected or float(base["source_condition"]) != float(base["calculator_condition"]):
            sample_rows.append(dict(base, status="source_model_disagreement"))
            assignments.append(dict(base, assignment_status="source_model_disagreement"))
            continue
        model_archetype = row["nrb_category"] if row["use_group"] == "nonres" else typology
        observed = row.get("osm_year_evidence")
        components, scores, metadata = envelope_candidates(data, model_archetype, nr,
            observed_year=int(observed) if pd.notna(observed) else None,
            newer_apartment_block_as_mfh=args.newer_apartment_block_as_mfh)
        sample_rows.append(dict(base, status="compared" if scores else "no_project_age_band", **metadata))
        component_rows.extend(dict(base, **record) for record in components)
        score_rows.extend(dict(fest_id=int(key), **record) for record in scores)
        proposal = select_assignment(pd.DataFrame(scores, columns=["metric", "score", "state", "year_min", "year_max"]),
                                     args.before_1860_year)
        assignments.append(dict(base, **metadata, **proposal))
    samples = pd.DataFrame(sample_rows)
    components = pd.DataFrame(component_rows)
    scores = pd.DataFrame(score_rows)
    samples.to_csv(args.output / "sample_checks.csv", index=False)
    components.to_csv(args.output / "component_comparisons.csv", index=False)
    scores.to_csv(args.output / "state_comparison_scores.csv", index=False)
    pd.DataFrame(assignments).to_csv(args.output / "assignment_proposals.csv", index=False)
    best = scores.sort_values(["score", "state"]).groupby(["fest_id", "year_min", "year_max", "metric"], as_index=False).first()
    best.to_csv(args.output / "closest_reference_by_age_band.csv", index=False)
    print(samples.status.value_counts().to_string())
    print("Assignment proposals saved; no scenario inputs modified.")
    print(best.groupby(["metric", "state"]).size().to_string())
    teaser_inputs = Path(teaser.__file__).parent / "data/input/inputdata"
    model_sources = [teaser_inputs / "TypeElements_TABULA_DE.json", teaser_inputs / "MaterialTemplates.json",
                     ROOT / "districtgenerator/data/non_residential/non_residential_envelope.json"]
    manifest = {"input_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "model_input_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in model_sources},
                "latest_construction_year": date.today().year,
                "sample_count": len(samples), "status_counts": samples.status.value_counts().to_dict(),
                "response_cache_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
                "metric": "area-weighted RMS log U-value ratio; smaller is closer",
                "selection_scope": "all observed strata" if args.all_strata else "stratified sample",
                "before_1860_representative_year": args.before_1860_year,
                "newer_apartment_block_as_mfh": args.newer_apartment_block_as_mfh,
                "tie_break": "lowest score, widest age interval, lowest state, earliest interval",
                "missing_area_policy": "fixed TABULA proxy component-area proportions, not simulation geometry",
                "missing_record_policy": "same type/age/condition U-value template if available; otherwise no fabricated assignment",
                "limitations": ["Current public calculator is not proven identical to historical NRW model",
                    "NRW age classes can overlap multiple project age bands; all overlaps tested",
                    "TEASER areas weight constructions within a component; NRW areas weight components",
                    "Ground and basement boundary differences remain; assignments are model approximations",
                    "NRW residential-like envelopes are permitted proxies for non-residential uses",
                    "Representative strata are not a population prevalence estimate"]}
    (args.output / "comparison_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
