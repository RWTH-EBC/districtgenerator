"""
Statistical check of FastElectricityProfile (numba) against richardsonpy's ElectricityProfile.

Both versions simulate the same households (appliances, light bulbs, occupancy, irradiance) for N flats x D days.
The fast version uses its own random number generator, so results are compared statistically, not bit by bit.
The DG normalization to the annual demand is NOT applied (stricter comparison of the raw model output).

Recommended usage (measure runtime and statistics separately):
    Runtime:    python tests/check_fast_richardson.py --n-flats 20 --workers 1
    Statistics: python tests/check_fast_richardson.py --n-flats 200 --workers 8

The original model needs roughly 45 s per flat and year, i.e. about 2.5 h CPU time for 200 flats.
Timings are only meaningful with --workers 1 (parallel workers compete for CPU and memory bandwidth).

Requires: richardsonpy 0.2.x, numba, numpy, scipy, matplotlib, districtgenerator (this repository).
"""

import argparse
import csv
import math
import multiprocessing as mp
import os
import random
import time

import numpy as np
import richardsonpy
import richardsonpy.classes.appliance as app_model
import richardsonpy.classes.lighting as light_model
import richardsonpy.classes.occupancy as occ_model
import richardsonpy.classes.stochastic_el_load_wrapper as wrap

import districtgenerator.functions.fast_richardson as fast_richardson

MINUTES_PER_DAY = 1440
HIST_MAX_W = 40000  # histogram range for minute power (1 W bins); larger values go to the last bin
QUANTILES = (0.5, 0.9, 0.99, 0.999)
INITIAL_DAY = 1

# Annual household electricity demand in kWh by number of occupants (DG-like ranges)
DEMAND_RANGE_KWH = {1: (1300, 2300), 2: (2000, 3300), 3: (2600, 4100), 4: (3000, 4800), 5: (3400, 5500)}


def _input_paths():
    src_path = os.path.dirname(richardsonpy.__file__)
    return (os.path.join(src_path, "inputs", "Appliances.csv"),
            os.path.join(src_path, "inputs", "LightBulbs.csv"))


def _irradiance_day(day):
    """Synthetic, deterministic horizontal irradiance in W/m2 at 1 minute resolution (daily and seasonal sine)."""
    amplitude = 450.0 + 350.0 * math.cos(2.0 * math.pi * (day - 172) / 365.0)
    minutes = np.arange(MINUTES_PER_DAY)
    # Daylight between 06:00 and 18:00
    return np.maximum(0.0, amplitude * np.sin(np.pi * (minutes - 360) / 720.0)) * ((minutes >= 360) & (minutes < 1080))


def _is_weekend(day):
    # Same weekday rule as Profiles.generate_el_profile_residential in the DG
    return (day + INITIAL_DAY) % 7 in (5, 6)


def _build_household(flat, seed, n_days):
    """Household parameters shared by both versions (seeded per flat)."""
    random.seed(seed + flat)
    np.random.seed((seed + flat) % 2 ** 32)
    nb_occ = flat % 5 + 1
    annual_demand = random.uniform(*DEMAND_RANGE_KWH[nb_occ])
    path_app, path_light = _input_paths()
    # Same settings as Users.create_el_wrapper in the DG (appliances = 90.4 % of the household demand)
    appliances = app_model.Appliances(path_app, annual_consumption=0.904 * annual_demand,
                                      randomize_appliances=True, max_iter=15, prev_heat_dev=True)
    lights = light_model.load_lighting_profile(filename=path_light, index=random.randrange(100))
    occupancy = np.asarray(occ_model.Occupancy(nb_occ, INITIAL_DAY, n_days).occupancy)
    return appliances, lights, occupancy


def _simulate(profile, occupancy, n_days, irradiance):
    """Run power_sim for all days. Returns minute power (n_days x 1440) for total, light, app and the runtime."""
    total = np.empty((n_days, MINUTES_PER_DAY))
    light = np.empty((n_days, MINUTES_PER_DAY))
    app = np.empty((n_days, MINUTES_PER_DAY))
    start = time.perf_counter()
    for day in range(n_days):
        t, l, a = profile.power_sim(irradiation=irradiance[day], weekend=_is_weekend(day), day=day,
                                    occupancy=occupancy[144 * day: 144 * (day + 1)])
        total[day], light[day], app[day] = t, l, a
    return total, light, app, time.perf_counter() - start


def _summarize(total, light, app, runtime):
    """Per-flat statistics that can be aggregated over flats."""
    hist, _ = np.histogram(np.clip(total, 0, HIST_MAX_W - 1), bins=HIST_MAX_W, range=(0, HIST_MAX_W))
    return {"annual_kwh": total.sum() / 60000.0,
            "annual_light_kwh": light.sum() / 60000.0,
            "annual_app_kwh": app.sum() / 60000.0,
            "daily_peaks": total.max(axis=1),
            "profile_sum": total.sum(axis=0),
            "hist": hist,
            "runtime_s": runtime}


def _run_flat(task):
    flat, seed, n_days = task
    appliances, lights, occupancy = _build_household(flat, seed, n_days)
    irradiance = [_irradiance_day(day) for day in range(n_days)]

    random.seed(seed * 1000 + flat)
    original = _summarize(*_simulate(wrap.ElectricityProfile(appliances, lights), occupancy, n_days, irradiance))

    random.seed(seed * 1000 + flat + 500)
    fast = _summarize(*_simulate(fast_richardson.FastElectricityProfile(appliances, lights), occupancy, n_days,
                                 irradiance))
    return flat, original, fast


def _warm_up():
    """Compile (or load from cache) the numba kernels once, so that they do not count in the per-flat times."""
    appliances, lights, occupancy = _build_household(0, 12345, 1)
    profile = fast_richardson.FastElectricityProfile(appliances, lights)
    start = time.perf_counter()
    profile.power_sim(irradiation=_irradiance_day(0), weekend=False, day=0, occupancy=occupancy[:144])
    return time.perf_counter() - start


def _quantiles_from_hist(hist):
    cumulative = np.cumsum(hist) / hist.sum()
    return [float(np.searchsorted(cumulative, q)) for q in QUANTILES]


def _aggregate(results, key):
    flats = [r[key] for r in results]
    return {"annual_kwh": np.array([f["annual_kwh"] for f in flats]),
            "annual_light_kwh": np.array([f["annual_light_kwh"] for f in flats]),
            "annual_app_kwh": np.array([f["annual_app_kwh"] for f in flats]),
            "daily_peaks": np.concatenate([f["daily_peaks"] for f in flats]),
            "profile": np.sum([f["profile_sum"] for f in flats], axis=0),
            "hist": np.sum([f["hist"] for f in flats], axis=0),
            "runtime_s": np.array([f["runtime_s"] for f in flats])}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-flats", type=int, default=200)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="fast_richardson_check")
    args = parser.parse_args()

    if not fast_richardson.FAST_AVAILABLE:
        raise SystemExit(f"FastElectricityProfile not available: {fast_richardson.FAST_UNAVAILABLE_REASON}")
    os.makedirs(args.out, exist_ok=True)

    # First call compiles the kernels (or loads them from the numba cache); measured separately
    jit_s = _warm_up()
    print(f"JIT / cache load of the first call: {jit_s:.2f} s")

    tasks = [(flat, args.seed, args.days) for flat in range(args.n_flats)]
    results = []
    start = time.perf_counter()
    if args.workers > 1:
        with mp.get_context("spawn").Pool(args.workers, initializer=_warm_up) as pool:
            for i, result in enumerate(pool.imap_unordered(_run_flat, tasks), start=1):
                results.append({"flat": result[0], "original": result[1], "fast": result[2]})
                print(f"\r{i}/{args.n_flats} flats", end="", flush=True)
    else:
        for i, task in enumerate(tasks, start=1):
            result = _run_flat(task)
            results.append({"flat": result[0], "original": result[1], "fast": result[2]})
            print(f"\r{i}/{args.n_flats} flats", end="", flush=True)
    print(f"\nTotal wall time: {(time.perf_counter() - start) / 60:.1f} min")

    original, fast = _aggregate(results, "original"), _aggregate(results, "fast")
    n_flat_days = args.n_flats * args.days
    q_orig, q_fast = _quantiles_from_hist(original["hist"]), _quantiles_from_hist(fast["hist"])

    from scipy.stats import ks_2samp
    ks_annual = ks_2samp(original["annual_kwh"], fast["annual_kwh"])
    ks_peaks = ks_2samp(original["daily_peaks"], fast["daily_peaks"])

    def rel(a, b):
        return (b - a) / a * 100.0 if a else float("nan")

    rows = [("annual total kWh (mean)", original["annual_kwh"].mean(), fast["annual_kwh"].mean()),
            ("annual total kWh (std)", original["annual_kwh"].std(ddof=1), fast["annual_kwh"].std(ddof=1)),
            ("annual light kWh (mean)", original["annual_light_kwh"].mean(), fast["annual_light_kwh"].mean()),
            ("annual appliances kWh (mean)", original["annual_app_kwh"].mean(), fast["annual_app_kwh"].mean()),
            ("daily peak W (mean)", original["daily_peaks"].mean(), fast["daily_peaks"].mean())]
    rows += [(f"minute power W, q{q * 100:g}", a, b) for q, a, b in zip(QUANTILES, q_orig, q_fast)]
    rows += [("runtime s per flat-year (median)", np.median(original["runtime_s"]) * 365 / args.days,
              np.median(fast["runtime_s"]) * 365 / args.days)]

    print(f"\n{'metric':36s} {'original':>12s} {'fast':>12s} {'diff %':>8s}")
    for name, a, b in rows:
        print(f"{name:36s} {a:12.2f} {b:12.2f} {rel(a, b):8.2f}")
    speedup = np.median(original["runtime_s"]) / np.median(fast["runtime_s"])
    print(f"{'speed-up (median)':36s} {speedup:12.1f}")
    print(f"KS annual totals:  D={ks_annual.statistic:.4f}, p={ks_annual.pvalue:.3f}  (n={args.n_flats} per version)")
    print(f"KS daily peaks:    D={ks_peaks.statistic:.4f}, p={ks_peaks.pvalue:.3f}  (n={n_flat_days} per version)")
    print("Note: with many samples (daily peaks) the KS test flags even tiny differences as significant; judge by "
          "the D statistic and the relative deviations above. Runtimes are only meaningful with --workers 1.")

    with open(os.path.join(args.out, "summary.csv"), "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["metric", "original", "fast", "diff_percent"])
        for name, a, b in rows:
            writer.writerow([name, f"{a:.4f}", f"{b:.4f}", f"{rel(a, b):.3f}"])
        writer.writerow(["ks_annual_D", f"{ks_annual.statistic:.5f}", "", f"p={ks_annual.pvalue:.4f}"])
        writer.writerow(["ks_daily_peaks_D", f"{ks_peaks.statistic:.5f}", "", f"p={ks_peaks.pvalue:.4f}"])
        writer.writerow(["jit_first_call_s", f"{jit_s:.3f}", "", ""])

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    hours = np.arange(MINUTES_PER_DAY) / 60.0
    ax1.plot(hours, original["profile"] / n_flat_days, label="richardsonpy", linewidth=1)
    ax1.plot(hours, fast["profile"] / n_flat_days, label="FastElectricityProfile", linewidth=1, linestyle="--")
    ax1.set_xlabel("hour of day")
    ax1.set_ylabel("mean power per flat [W]")
    ax1.set_title("Mean daily profile")
    ax1.legend()
    labels = [f"q{q * 100:g}" for q in QUANTILES]
    x = np.arange(len(QUANTILES))
    ax2.bar(x - 0.2, q_orig, width=0.4, label="richardsonpy")
    ax2.bar(x + 0.2, q_fast, width=0.4, label="FastElectricityProfile")
    ax2.set_xticks(x, labels)
    ax2.set_yscale("log")
    ax2.set_ylabel("minute power [W]")
    ax2.set_title("Quantiles of minute power")
    ax2.legend()
    fig.suptitle(f"{args.n_flats} flats x {args.days} days")
    fig.tight_layout()
    fig.savefig(os.path.join(args.out, "comparison.png"), dpi=150)
    print(f"Written: {os.path.join(args.out, 'summary.csv')}, {os.path.join(args.out, 'comparison.png')}")


if __name__ == "__main__":
    main()
