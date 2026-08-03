# -*- coding: utf-8 -*-
"""
e9_alpha_sensitivity.py — Alpha sensitivity analysis for business models.

Simplified version that:
- Runs alpha sweep ONLY for alpha-dependent BMs (contracting, mietstrom, kundenanlage)
- Does NOT run cooperative (alpha has no effect)
- Gets p_max from a single reference run
- Generates only the alpha sensitivity plot (no full KPIs storage)

Usage:
    python e9_alpha_sensitivity.py
"""

import os
import pickle
import warnings


from districtgenerator.classes import *
from districtgenerator.classes.plots_bm_comparison import plot_alpha_sensitivity

# Reuse cache infrastructure from e8
from e8_2 import (
    generate_or_load_thermal_base,
    get_thermal_cache_path,
    load_thermal_base_state,
    run_optimization_for_bm,
)

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

SCENARIO_NAME = "district_F_buildings_20"

# ┌─────────────────────────────────────────────────────────────────────┐
# │  Reference heat price from reference scenario            │
# │  This is the maximum heat price the BM must beat to be feasible.   │
# │  Obtain this value by running the reference scenario first!        │
# │  (e.g., from KPIs.p_max after running e8 with reference config)    │
# └─────────────────────────────────────────────────────────────────────┘
p_max = 0.1895  # EUR/kWh - ADJUST THIS VALUE!

# BM configs for alpha sweep (NO cooperative - alpha doesn't affect it)
BM_CONFIGS = {
    "contracting": ".env.CONFIG.waermecontracting",
    "mietstrom": ".env.CONFIG.waermecontracting_ggv",
    "kundenanlage": ".env.CONFIG.waermecontracting_kundenanlage",
}

# Alpha values to sweep
ALPHAS = [0.70, 0.80, 0.90]

CACHE_FILE = "../../examples/results/cache/alpha_sensitivity_results.pkl"


# ══════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════



def extract_p_min(data):
    """Extract p_min from completed Datahandler."""
    if hasattr(data, "KPIs") and data.KPIs is not None:
        return getattr(data.KPIs, "p_min", None)
    return None


def is_feasible(p_min, p_max):
    """Check if BM is economically feasible."""
    if p_min is None or p_max is None:
        return False
    return p_min <= p_max


# ══════════════════════════════════════════════════════════════════════
# ALPHA SWEEP
# ══════════════════════════════════════════════════════════════════════

def run_alpha_sweep(scenario_name, bm_configs, alphas,
                    topology_option="road", force_regenerate=False):
    """
    Run alpha sweep for each BM.

    Returns
    -------
    alpha_results : dict
        {bm_name: {alpha: p_min_value, ...}, ...}
    """
    warnings.filterwarnings("ignore", category=FutureWarning)

    # ── Generate thermal base (once) ───────────────────────────────────
    first_env = list(bm_configs.values())[0]
    bootstrap = generate_or_load_thermal_base(
        scenario_name=scenario_name,
        env_path=first_env,
        topology_option=topology_option,
        force_regenerate=force_regenerate,
    )
    cache_path = get_thermal_cache_path(bootstrap, scenario_name)

    # ── Alpha sweep for each BM ────────────────────────────────────────
    alpha_results = {}

    for bm_name, env_path in bm_configs.items():
        print(f"\n{'═' * 60}")
        print(f"  Alpha sweep: {bm_name}")
        print(f"{'═' * 60}")

        alpha_results[bm_name] = {}

        for alpha in alphas:
            print(f"\n  α = {alpha:.2f}", end="  ")

            data = Datahandler(scenario_name=scenario_name, env_path=env_path)
            load_thermal_base_state(data, cache_path)

            # Override alpha
            data.ecoData["alpha"] = alpha

            data = run_optimization_for_bm(data, bm_name)
            p_min = extract_p_min(data)

            # Store only p_min
            alpha_results[bm_name][alpha] = p_min

            # Print result
            if p_min is not None:
                feasible = "✓" if is_feasible(p_min, p_max) else "✗"
                print(f"→ p_min = {p_min * 100:.2f} ct/kWh  {feasible}")
            else:
                print(f"→ p_min = ERROR")

    return alpha_results


# ══════════════════════════════════════════════════════════════════════
# FIND OPTIMAL ALPHA
# ══════════════════════════════════════════════════════════════════════

def find_optimal_alphas(alpha_results, p_max):
    """
    For each BM, find the lowest alpha where p_min <= p_max.

    Returns
    -------
    optimal : dict
        {bm_name: {"alpha_opt": float or None, "p_min": float or None}}
    """
    optimal = {}

    for bm_name, alpha_data in alpha_results.items():
        best_alpha = None
        best_p_min = None

        for alpha in sorted(alpha_data.keys()):
            p_min = alpha_data[alpha]
            if p_min is not None and is_feasible(p_min, p_max):
                best_alpha = alpha
                best_p_min = p_min
                break

        # Fallback: use highest alpha even if not feasible
        if best_alpha is None:
            highest = max(alpha_data.keys())
            best_p_min = alpha_data[highest]

        optimal[bm_name] = {
            "alpha_opt": best_alpha,
            "p_min": best_p_min,
        }

    return optimal


# ══════════════════════════════════════════════════════════════════════
# OUTPUT
# ══════════════════════════════════════════════════════════════════════

def print_summary(alpha_results, p_max, optimal):
    """Print summary table and recommendations."""

    print(f"\n{'#' * 70}")
    print(f"#  ALPHA SENSITIVITY — SUMMARY")
    print(f"#  p_max (Reference) = {p_max * 100:.2f} ct/kWh")
    print(f"{'#' * 70}\n")

    # ── Full table ─────────────────────────────────────────────────────
    for bm_name, alpha_data in alpha_results.items():
        print(f"  {bm_name}:")
        print(f"  {'α':>6}  {'p_min (ct)':>12}  {'Feasible':>10}")
        print(f"  {'-' * 35}")

        for alpha in sorted(alpha_data.keys()):
            p_min = alpha_data[alpha]
            pm = f"{p_min * 100:.2f}" if p_min else "-"
            feas = "✓" if p_min and is_feasible(p_min, p_max) else "✗"
            marker = " ← α*" if alpha == optimal[bm_name]["alpha_opt"] else ""
            print(f"  {alpha:>6.2f}  {pm:>12}  {feas:>10}{marker}")
        print()

    # ── Recommendations ────────────────────────────────────────────────
    print(f"{'=' * 70}")
    print(f"  RECOMMENDED .env SETTINGS (lowest feasible alpha):")
    print(f"{'=' * 70}\n")

    for bm_name, opt in optimal.items():
        a = opt["alpha_opt"]
        if a is not None:
            print(f"  {bm_name:<15}  →  ALPHA = {a:.2f}")
        else:
            print(f"  {bm_name:<15}  →  NO feasible alpha found!")

    print(f"\n  Copy these ALPHA values into the respective _env_CONFIG.* files.")
    print()


def save_results(alpha_results, p_max, optimal, filepath):
    """Save lightweight results to pickle."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "wb") as f:
        pickle.dump({
            "alpha_results": alpha_results,
            "p_max": p_max,
            "optimal": optimal,
        }, f)

    print(f"  Results saved to {filepath}")


def generate_plot(alpha_results, p_max, save_dir):
    """Generate the alpha sensitivity plot."""
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, "alpha_sensitivity.pdf")

    # plot_alpha_sensitivity expects: {bm: {alpha: p_min, ...}, ...}
    # That's exactly what we have!
    plot_alpha_sensitivity(
        alpha_results,
        p_max=p_max,
        save_path=save_path,
    )

    print(f"  Plot saved to {save_path}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'█' * 70}")
    print(f"  ALPHA SENSITIVITY ANALYSIS")
    print(f"  Scenario: {SCENARIO_NAME}")
    print(f"  BMs: {', '.join(BM_CONFIGS.keys())}")
    print(f"  Alphas: {ALPHAS}")
    print(f"{'█' * 70}\n")

    # ── Run sweep ──────────────────────────────────────────────────────
    alpha_results = run_alpha_sweep(
        scenario_name=SCENARIO_NAME,
        bm_configs=BM_CONFIGS,
        alphas=ALPHAS,
        topology_option="road",
        force_regenerate=False,
    )

    # ── Find optimal ───────────────────────────────────────────────────
    optimal = find_optimal_alphas(alpha_results, p_max)

    # ── Output ─────────────────────────────────────────────────────────
    print_summary(alpha_results, p_max, optimal)

    # ── Save & plot ────────────────────────────────────────────────────
    save_results(alpha_results, p_max, optimal, CACHE_FILE)

    save_dir = f"results/plots/alpha_sensitivity_{SCENARIO_NAME}"
    generate_plot(alpha_results, p_max, save_dir)

    print(f"\n{'█' * 70}")
    print(f"  DONE!")
    print(f"{'█' * 70}\n")

    return alpha_results, p_max, optimal


if __name__ == "__main__":
    alpha_results, p_max, optimal = main()