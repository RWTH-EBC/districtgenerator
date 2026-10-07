"""QG-interne Hüllprofile: ein Gebäude-/Nutzerkontext, standard/retrofit.

Vorschlag, vor produktiver Verwendung mit dem lokalen 5R1C-Solver validieren.
Alle Leistungsprofile bleiben in W; keine FIWARE-Skalierung in diesem Modul.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import itertools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PARTS = ("outer_walls", "windows", "roofs", "ground_floors")
COMPONENTS = dict(zip(PARTS, ("wall", "window", "roof", "floor")))
RANK = {"standard": 0, "retrofit": 1}
SETPOINTS = ("T_set_min", "T_set_min_night", "T_set_min_free_day", "T_set_max", "T_set_max_night")
MATERIALS = ("d", "d_iso", "rho", "cp", "Lambda", "U", "kappa", "R_se", "R_si", "epsilon", "alpha_Sc", "g_gl")
INPUT_PROFILES = ("elec", "dhw", "occ", "gains")
VERSION = "QGP2"
logger = logging.getLogger("app.qg-envelope-profiles")


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(type(value).__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=_json_default,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_hash(values):
    values = np.ascontiguousarray(values, dtype="<f8")
    if not np.isfinite(values).all():
        raise ValueError("Non-finite input profile.")
    return hashlib.sha256(values.tobytes()).hexdigest()


def valid_profile(values):
    values = np.asarray(values, dtype=float)
    if values.shape != (8760,) or not np.isfinite(values).all() or np.any(values < -1e-6):
        raise ValueError("Expected 8760 finite, non-negative hourly values in W.")
    return np.maximum(values, 0.0)


def source_signature():
    import districtgenerator
    import teaser
    result = hashlib.sha256()
    for package in (districtgenerator, teaser):
        root = Path(inspect.getfile(package)).parent
        result.update(package.__name__.encode())
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".json"}):
            result.update(str(path.relative_to(root)).replace("\\", "/").encode())
            result.update(path.read_bytes())
    return result.hexdigest()


def profile_key(states):
    return "".join(f"{letter}{RANK[states[part]]}" for part, letter in zip(PARTS, "OWRG"))


def allowed_combinations(initial, allowed_states=("standard", "retrofit")):
    if set(initial) != set(PARTS) or any(s not in RANK for s in initial.values()):
        raise ValueError(f"Invalid initial envelope: {initial}")
    if not allowed_states or any(s not in RANK for s in allowed_states):
        raise ValueError("Only standard and retrofit are supported.")
    choices = [[initial[p], *sorted({s for s in allowed_states if RANK[s] > RANK[initial[p]]}, key=RANK.get)] for p in PARTS]
    return [dict(zip(PARTS, values)) for values in itertools.product(*choices)]


def scenario_input(features):
    return {"id": int(features["id"]), "gmlId": str(features.get("gmlId", "")),
        "building": str(features["building"]), "year": int(features["year"]),
        "area": float(features["area"]), "number_of_floors": int(features["number_of_floors"]),
        "height_of_floors": float(features["height_of_floors"]),
        "night_setback": int(features["night_setback"]), "cooling": int(features["cooling"]),
        "initial_state": {p: str(features[f"retrofit_{p}"]).strip().lower() for p in PARTS}}


def initialize_context(qg):
    if qg.design_building_data["thermal_model_type"] != "5R1C":
        return None
    if qg.time["timeResolution"] != 3600 or qg.time["timeSteps"] != 8760:
        raise ValueError("Envelope profiles require a non-leap year with 8760 hourly values.")
    env_path = getattr(qg, "_envelope_profiles_env_path", None)
    weather = (Path(qg.filePath) / "weather" / f"TRY_{qg.site['TRYYear'][-4:]}_{qg.site['TRYType']}"
        / f"{qg.site['TRYYear']}_{qg.site['Location']}_{qg.site['TRYType']}.dat")
    paths = [weather, Path(qg.filePath) / "plz_geocoord_matched.xlsx", Path(qg.filePath) / "site_data_with_KLZ.txt"]
    context = {"source_hash": source_signature(), "env_hash": file_hash(env_path) if env_path else None,
        "environment_files": {str(p.resolve()): file_hash(p) for p in paths},
        "calendar": copy.deepcopy(qg.calendar)}
    context["digest"] = digest({"version": VERSION, "source": context["source_hash"],
        "env": context["env_hash"], "site": qg.site, "time": qg.time, "calendar": context["calendar"],
        "initial_day": qg.initial_day, "physics": qg.physics, "design": qg.design_building_data,
        "calcThick": qg.calcThick})
    return context


def clone_envelope(base):
    # The TEASER geometry is shared read-only; other mutable envelope state is isolated.
    return copy.deepcopy(base, {id(base.prj): base.prj,
        id(base.physics): base.physics, id(base.design_building_data): base.design_building_data})


def fixed_signature(envelope):
    return digest({"A": envelope.A, "V": envelope.V, "id": envelope.id,
        "usage": envelope.usage_short, "year": envelope.construction_year, "retrofit": envelope.retrofit,
        "setpoints": {name: getattr(envelope, name) for name in SETPOINTS},
        "partially_heated_portion": envelope.partially_heated_portion,
        "ventilationRate": envelope.ventilationRate, "rho_air": envelope.rho_air, "c_p_air": envelope.c_p_air,
        "T_bivalent": envelope.T_bivalent, "T_heatlimit": envelope.T_heatlimit,
        "internal_components": {name: {p: getattr(envelope, name)["opaque"][p]
            for p in ("intWall", "ceiling", "intFloor")} for name in MATERIALS}})


def build_material_bank(base):
    # Existing QG material loader, no new TEASER geometry or user constructor.
    # Its temporary behaviour adjustment is discarded; only external material slots are copied.
    bank = {}
    # Only retrofit can be a new target; standard slots already come from the initial envelope.
    for state in ("retrofit",):
        candidate = clone_envelope(base)
        candidate.component_construction_data = {c: f"tabula_de_{state}" for c in COMPONENTS.values()}
        candidate.loadComponentProperties(candidate.prj, (0, 0, 0, 0), False)
        bank[state] = candidate
    return bank


def variant_envelope(base, initial, states, bank):
    envelope = clone_envelope(base)
    for part, component in COMPONENTS.items():
        if states[part] == initial[part]:
            continue
        candidate = bank[states[part]]
        for name in MATERIALS:
            target, source = getattr(envelope, name), getattr(candidate, name)
            if component == "window":
                target["window"] = copy.deepcopy(source["window"])
            else:
                target["opaque"][component] = copy.deepcopy(source["opaque"][component])
        envelope.component_construction_data[component] = f"tabula_de_{states[part]}"
    return envelope


def prepare_envelope(qg, envelope, user, night):
    for attr, method in (("heatload", "design"), ("bivalent", "bivalent"), ("heatlimit", "heatlimit")):
        setattr(envelope, attr, envelope.calcHeatLoad(site=qg.site, method=method, night_setback=night))
    envelope.calculateHeatCapacity(envelope.prj)  # invalidate the initial C_m after replacing external materials
    envelope.coolingload = envelope.calcCoolingLoad(site=qg.site, nb_occ=np.sum(user.nb_occ))
    envelope.calcNormativeProperties(qg.site["SunRad"], user.gains)


def calculate_profiles(qg, building):
    context = qg._envelope_profiles_context
    features, base, user = building["buildingFeatures"], building["envelope"], building["user"]
    scenario = scenario_input(features)
    for name in ("night_setback", "cooling"):
        if float(features[name]) not in (0, 1):
            raise ValueError(f"{name} must be 0 or 1.")
    initial = scenario["initial_state"]
    combinations = allowed_combinations(initial)
    keys = [profile_key(states) for states in combinations]
    logger.debug("%s, Building %s: %d zulässige Hüllkombinationen wurden erzeugt.",
                 qg.scenario_name, scenario["id"], len(keys), )
    inputs = {name: array_hash(getattr(user, name)) for name in INPUT_PROFILES}
    for name in INPUT_PROFILES:
        if np.asarray(getattr(user, name)).shape != (8760,):
            raise ValueError(f"Expected 8760 values for {name}.")
    fingerprint = digest({"context": context["digest"], "scenario": scenario, "inputs": inputs,
        "nb_occ": np.asarray(user.nb_occ), "fixed_envelope": fixed_signature(base),
        "materials": {name: getattr(base, name) for name in MATERIALS}, "keys": keys})
    folder = (Path(qg.demands_path) / "qg_envelope_profiles" / building["unique_name"])
    archive = folder / "profiles_W.npz"
    manifest = folder / "manifest.json"

    profiles, cooling, info = None, None, None
    existing_profiles_loaded = False

    archive_exists = archive.is_file()
    manifest_exists = manifest.is_file()

    if archive_exists and manifest_exists:
        try:
            info = json.loads(manifest.read_text(encoding="utf-8"))

            required_fields = {"version", "fingerprint", "sha256", "annual_kwh", "states", "initial_key", "initial_state",}
            missing_fields = required_fields.difference(info)

            if missing_fields:
                raise ValueError("Missing manifest fields: " + ", ".join(sorted(missing_fields)))

            if info["version"] != VERSION:
                raise ValueError(f"Profile version mismatch: saved={info['version']}, expected={VERSION}")

            if info["fingerprint"] != fingerprint:
                raise ValueError("Profile fingerprint does not match the current inputs or model configuration.")

            if info["sha256"] != file_hash(archive):
                raise ValueError("Profile archive checksum does not match the manifest.")

            with np.load(archive, allow_pickle=False) as data:
                expected_keys = set(keys) | {"initial_cooling"}

                if set(data.files) != expected_keys:
                    raise ValueError("Stored profile keys do not match the required envelope combinations.")

                profiles = {key: valid_profile(data[key]) for key in keys}
                cooling = valid_profile(data["initial_cooling"])

            existing_profiles_loaded = True

        except Exception as exc:
            profiles, cooling, info = None, None, None

            logger.error("%s, Building %s: Existing envelope profiles cannot be loaded: %s: %s",
                         qg.scenario_name, scenario["id"], type(exc).__name__, exc, exc_info=logger.isEnabledFor(logging.DEBUG),)

    elif archive_exists or manifest_exists:
        missing_file = str(manifest if archive_exists else archive)

        logger.error("%s, Building %s: Envelope profile cache is incomplete. Missing file: %s",
                     qg.scenario_name, scenario["id"], missing_file,)

    if profiles is None:
        if not archive_exists and not manifest_exists:
            logger.warning("%s, Building %s: No existing envelope profiles found. Profiles will be calculated.",
                           qg.scenario_name, scenario["id"],)
        else:
            logger.warning("%s, Building %s: Existing envelope profiles cannot be used. Profiles will be recalculated.",
                           qg.scenario_name, scenario["id"],)
    if profiles is None:
        previous = getattr(user, "heat", None)
        bank = build_material_bank(base) if len(keys) > 1 else {}
        fixed = fixed_signature(base)
        weather_signature = digest(qg.site)
        profiles = {}
        for states, key in zip(combinations, keys):
            envelope = variant_envelope(base, initial, states, bank)
            if fixed_signature(envelope) != fixed:
                raise ValueError("Non-envelope conditions changed between variants.")
            prepare_envelope(qg, envelope, user, scenario["night_setback"])
            # A shallow copy keeps all initialized user inputs, without drawing any new random values.
            output_user = copy.copy(user)
            output_user.calcHeatingProfile(site=qg.site, envelope=envelope, thermal_model="5R1C",
                night_setback=scenario["night_setback"], is_cooled=scenario["cooling"],
                calendar=copy.deepcopy(context["calendar"]), time_resolution=3600, initial_day=qg.initial_day)
            if fixed_signature(envelope) != fixed:
                raise ValueError("The solver changed fixed building conditions.")
            profiles[key] = valid_profile(output_user.heat)
            if key == keys[0]:
                cooling = valid_profile(output_user.cooling)
                initial_envelope = envelope
        for name in INPUT_PROFILES:
            if inputs[name] != array_hash(getattr(user, name)):
                raise ValueError(f"The solver modified the shared input {name}.")
        if digest(qg.site) != weather_signature:
            raise ValueError("The solver modified shared weather/environment inputs.")
        folder.mkdir(parents=True, exist_ok=True)
        temp_archive = folder / "profiles_W.tmp.npz"
        np.savez_compressed(temp_archive, **profiles, initial_cooling=cooling)
        temp_archive.replace(archive)
        info = {"version": VERSION, "fingerprint": fingerprint, "sha256": file_hash(archive),
            "unit": "W", "dt_s": 3600, "source_hash": context["source_hash"], "env_hash": context["env_hash"],
            "environment_files": context["environment_files"], "context_digest": context["digest"],
            "scenario_input": scenario, "input_profile_hashes": inputs, "nb_occ": np.asarray(user.nb_occ).tolist(),
            "initial_key": keys[0], "initial_state": initial, "states": dict(zip(keys, combinations)),
            "setpoints": {name: float(getattr(base, name)) for name in SETPOINTS},
            "fixed_envelope_signature": fixed, "new_simulations": len(keys),
            "annual_kwh": {key: float(values.sum()) / 1000 for key, values in profiles.items()}}
        if previous is not None and np.asarray(previous).shape == (8760,):
            diff = profiles[keys[0]] - np.asarray(previous)
            info["old_heating_comparison"] = {"annual_difference_kwh": float(diff.sum()) / 1000,
                "absolute_profile_difference_kwh": float(np.abs(diff).sum()) / 1000,
                "max_difference_w": float(np.abs(diff).max())}
        temp_manifest = folder / "manifest.tmp.json"
        temp_manifest.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_manifest.replace(manifest)
        building["envelope"] = initial_envelope
    else:
        # Restore derived properties required by the remaining QG workflow.
        prepare_envelope(qg, base, user, scenario["night_setback"],)

    user.heat = profiles[keys[0]]
    user.cooling = cooling
    user.annual_heat_demand = float(user.heat.sum())
    user.annual_cooling_demand = float(user.cooling.sum())

    if existing_profiles_loaded:
        profile_source = "existing_profile_archive"
        status = "Existing envelope profiles validated and loaded."
        simulations_this_call = 0
        validation_checks = "existing_profiles_validated"
    else:
        profile_source = "new_qg_calculation"
        status = "Envelope profiles recalculated and saved."
        simulations_this_call = len(keys)
        validation_checks = "new_profiles_validated"

    # Append one validation record per building and call.
    with (folder / "validation.jsonl").open("a", encoding="utf-8",) as stream:
        stream.write(json.dumps({"at_utc": datetime.now(timezone.utc).isoformat(),
                                 "version": VERSION,
                                 "fingerprint": fingerprint,
                                 "profiles_loaded_from_archive":
                                     existing_profiles_loaded,
                                 "profile_source": profile_source,
                                 "status": status,
                                 "simulations_this_call": simulations_this_call,
                                 "profile_count": len(keys),
                                 "initial_key": keys[0],
                                 "annual_kwh": info["annual_kwh"],
                                 "checks": validation_checks,},
                                ensure_ascii=False,) + "\n")

    if existing_profiles_loaded:
        logger.info("%s, Building %s: Existing envelope profiles are valid and were loaded (%d combinations).",
                    qg.scenario_name, scenario["id"], len(keys),)
    else:
        logger.info("%s, Building %s: Envelope profiles were recalculated and saved (%d combinations).",
                    qg.scenario_name, scenario["id"], len(keys),)
    return profiles, info
