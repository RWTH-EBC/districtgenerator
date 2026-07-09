import argparse
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.text import Text
from openpyxl import load_workbook


RESULT_RE = re.compile(
    r"KPIs_district_(?P<district>[A-Z])_seed_(?P<seed>\d+)_buildings_30_"
    r"(?P<system>central|decentral)_cost_(?P<cost>min|mean|max)\.xlsx$"
)

COST_CASES = ("min", "mean", "max")
REGRESSION_TARGETS = {
    "lower": "min_lcoh_ct_per_kwh",
    "mean": "mean_lcoh_ct_per_kwh",
    "upper": "max_lcoh_ct_per_kwh",
}
MODEL_SPECS = [
    ("linear_density_only", "linear", False, False, False),
    ("log_density_only", "log", False, False, False),
    ("log_density_plus_lhd_tertile", "log", False, True, False),
    ("log_density_times_lhd_tertile", "log", False, True, True),
    ("log_density_plus_district", "log", True, False, False),
]
VALIDATION_REPEATS = 100
VALIDATION_TEST_FRACTION = 0.20
VALIDATION_RANDOM_SEED = 42
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "districtgenerator" / "results" / "results_paper_2"
DEFAULT_OUTPUT_PREFIX = DEFAULT_RESULTS_DIR / "central_lcoh_vs_heat_density"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "districtgenerator" / "data" / ".env.CONFIG.PAPER"

DISTRICT_COLORS = {
    "A": "#0072B2",
    "B": "#D55E00",
    "C": "#009E73",
    "D": "#CC79A7",
    "E": "#E69F00",
    "F": "#56B4E9",
    "H": "#7F3C8D",
    "I": "#6B6B6B",
}

DISPLAY_DISTRICT_LABELS = {
    "H": "G",
    "I": "H",
}
TERTILE_COLORS = {"low": "#0072B2", "medium": "#E69F00", "high": "#009E73"}
FIGURE_SIZE = (10.5, 7.0)
BAND_ALPHA = 0.16
MODEL_DISPLAY_NAMES = {
    "linear_density_only": "Linear",
    "log_density_only": "Logarithmic",
    "log_density_plus_lhd_tertile": "Log. + density class",
    "log_density_times_lhd_tertile": "Log. x density class",
    "log_density_plus_district": "Log. + district type",
}


def apply_publication_style():
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 600,
            "font.size": 13,
            "axes.labelsize": 15,
            "axes.titlesize": 15,
            "axes.titleweight": "bold",
            "axes.linewidth": 1.1,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 11,
            "legend.title_fontsize": 12,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "path",
        }
    )


def district_color_map(districts):
    return {
        district: DISTRICT_COLORS.get(district, plt.get_cmap("tab10")(i))
        for i, district in enumerate(districts)
    }


def display_district(district):
    return DISPLAY_DISTRICT_LABELS.get(district, district)


def save_presentation_svg(fig, path):
    for axis in fig.axes:
        axis.set_title("")
        axis.grid(False, which="both")
        axis.xaxis.grid(False, which="both")
        axis.yaxis.grid(False, which="both")
    for text in fig.findobj(match=Text):
        text.set_fontsize(text.get_fontsize() * 1.25)
    fig.savefig(path, transparent=True)


def row_values_by_kpi(ws):
    values = {}
    for row in ws.iter_rows(values_only=True):
        if row and row[0] is not None:
            values[str(row[0]).strip()] = list(row[1:])
    return values


def find_kpi_row(values, row_name):
    if row_name in values:
        return values[row_name]
    for key, row in values.items():
        if key.startswith(row_name):
            return row
    raise KeyError(f"Could not find KPI row starting with '{row_name}'.")


def numeric_values(values):
    return [float(value) for value in values if isinstance(value, (int, float))]


def mean_kpi_row(values, row_name):
    numbers = numeric_values(find_kpi_row(values, row_name))
    if not numbers:
        raise ValueError(f"KPI row has no numeric values: {row_name}")
    return sum(numbers) / len(numbers)


def parse_config_value(raw_value):
    value = raw_value.split("#", 1)[0].strip()
    if value.startswith("[") and value.endswith("]"):
        return [float(item.strip()) for item in value[1:-1].split(",") if item.strip()]
    if "," in value:
        return [float(item.strip()) for item in value.split(",") if item.strip()]
    return float(value)


def read_config_values(config_path):
    values = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key in {
            "PRICE_SUPPLY_EL",
            "PRICE_SUPPLY_EL_EH",
            "REVENUE_FEED_IN_EL",
            "REVENUE_FEED_IN_EL_EH",
        }:
            values[key] = parse_config_value(raw_value)
    return values


def value_for_year(config_values, key, index):
    value = config_values[key]
    if isinstance(value, list):
        return value[index]
    return value


def sum_column(ws, column_name):
    header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    if column_name in header:
        idx = header.index(column_name)
    else:
        idx = next(
            (
                i for i, value in enumerate(header)
                if isinstance(value, str) and value.startswith(column_name)
            ),
            None,
        )
    if idx is None:
        return 0.0
    total = 0.0
    for row in ws.iter_rows(min_row=2, values_only=True):
        value = row[idx]
        if isinstance(value, (int, float)):
            total += float(value)
    return total


def central_heat_net_annual_cost(kpi_path, config_values):
    wb = load_workbook(kpi_path, data_only=True, read_only=True)
    yearly = row_values_by_kpi(wb["Yearly KPIs"])

    electricity_costs = numeric_values(find_kpi_row(yearly, "Electricity Costs"))
    total_feed_in_revenue = numeric_values(find_kpi_row(yearly, "Revenue from Electricity Feed-in"))
    building_el_demand = numeric_values(find_kpi_row(yearly, "Electricity Demand within District"))
    building_el_feed_in = numeric_values(find_kpi_row(yearly, "Electricity Injection within District"))

    fuel_row_names = [
        "Gas Costs",
        "Biomethane Costs",
        "Oil Costs",
        "Waste Costs",
        "Biomass Costs",
        "District Heat Costs",
        "Hydrogen Costs",
    ]
    fuel_costs_by_year = []
    for row_name in fuel_row_names:
        try:
            fuel_costs_by_year.append(numeric_values(find_kpi_row(yearly, row_name)))
        except KeyError:
            fuel_costs_by_year.append([0.0] * len(electricity_costs))

    annual_heat_operation_costs = []
    for i, electricity_cost in enumerate(electricity_costs):
        building_import_cost = building_el_demand[i] * value_for_year(config_values, "PRICE_SUPPLY_EL", i)
        building_feed_in_revenue = -building_el_feed_in[i] * value_for_year(config_values, "REVENUE_FEED_IN_EL", i)
        energy_hub_electricity_cost = electricity_cost - building_import_cost
        energy_hub_feed_in_revenue = total_feed_in_revenue[i] - building_feed_in_revenue
        central_fuel_costs = sum(fuel_costs[i] for fuel_costs in fuel_costs_by_year)
        annual_heat_operation_costs.append(
            energy_hub_electricity_cost + energy_hub_feed_in_revenue + central_fuel_costs
        )
    mean_heat_operation_cost = sum(annual_heat_operation_costs) / len(annual_heat_operation_costs)

    central_costs = 0.0
    if "Central Devices Costs" in wb.sheetnames:
        central_costs = sum_column(wb["Central Devices Costs"], "Annualized Cost Subsidized")

    return mean_heat_operation_cost + central_costs


def scalar_json_value(data, key):
    value = data[key]
    if isinstance(value, dict) and "value" in value:
        return float(value["value"])
    return float(value)


def central_heat_grid_values(results_dir, district, seed):
    network_dir = results_dir / "network"
    candidates = sorted(
        network_dir.glob(
            f"district_{district}_seed_{seed}_buildings_30_central_cost_mean_*"
            "/heat_grid_parameters_outputs.json"
        )
    )
    if not candidates:
        candidates = sorted(
            network_dir.glob(
                f"district_{district}_seed_{seed}_buildings_30_central_cost_*_*"
                "/heat_grid_parameters_outputs.json"
            )
        )
    if not candidates:
        return None

    data = json.loads(candidates[0].read_text(encoding="utf-8"))
    heat_kwh = scalar_json_value(data, "total_net_heat_demand")
    pipe_m = scalar_json_value(data, "total_pipe_length")
    if heat_kwh <= 0 or pipe_m <= 0:
        return None
    return heat_kwh, pipe_m, heat_kwh / pipe_m


def collect_kpis(results_dir):
    records = {}
    for path in results_dir.glob("KPIs_district_*_seed_*_buildings_30_*_cost_*.xlsx"):
        match = RESULT_RE.match(path.name)
        if not match:
            continue
        key = (
            match.group("district"),
            int(match.group("seed")),
            match.group("system"),
            match.group("cost"),
        )
        records[key] = path
    return records


def make_ranges(results_dir, config_values, require_complete_decentral=False):
    kpis = collect_kpis(results_dir)
    district_seeds = sorted({(district, seed) for district, seed, _, _ in kpis})
    ranges = []
    cases = []

    for district, seed in district_seeds:
        heat_grid_values = central_heat_grid_values(results_dir, district, seed)
        if heat_grid_values is None:
            continue
        total_heat_kwh, pipe_length_m, density = heat_grid_values

        central_paths = {
            cost: kpis.get((district, seed, "central", cost)) for cost in COST_CASES
        }
        if any(path is None for path in central_paths.values()):
            continue
        if require_complete_decentral:
            decentral_paths = {
                cost: kpis.get((district, seed, "decentral", cost)) for cost in COST_CASES
            }
            if any(path is None for path in decentral_paths.values()):
                continue

        lcoh_by_case = {}
        net_cost_by_case = {}
        for cost_case, path in central_paths.items():
            net_cost = central_heat_net_annual_cost(path, config_values)
            lcoh = 100.0 * net_cost / total_heat_kwh
            net_cost_by_case[cost_case] = net_cost
            lcoh_by_case[cost_case] = lcoh
            cases.append(
                {
                    "district": district,
                    "seed": seed,
                    "cost_case": cost_case,
                    "linear_heat_density_kwh_per_m_a": density,
                    "total_net_heat_demand_kwh_per_a": total_heat_kwh,
                    "total_pipe_length_m": pipe_length_m,
                    "net_annual_cost_eur_per_a": net_cost,
                    "lcoh_ct_per_kwh": lcoh,
                }
            )

        lcoh_values = list(lcoh_by_case.values())
        ranges.append(
            {
                "district": district,
                "seed": seed,
                "linear_heat_density_kwh_per_m_a": density,
                "total_net_heat_demand_kwh_per_a": total_heat_kwh,
                "total_pipe_length_m": pipe_length_m,
                "min_lcoh_ct_per_kwh": min(lcoh_values),
                "mean_lcoh_ct_per_kwh": lcoh_by_case["mean"],
                "max_lcoh_ct_per_kwh": max(lcoh_values),
                "central_min_lcoh_ct_per_kwh": lcoh_by_case["min"],
                "central_mean_lcoh_ct_per_kwh": lcoh_by_case["mean"],
                "central_max_lcoh_ct_per_kwh": lcoh_by_case["max"],
                "central_mean_net_annual_cost_eur_per_a": net_cost_by_case["mean"],
            }
        )

    return pd.DataFrame(ranges), pd.DataFrame(cases)


def add_lhd_tertiles(df):
    df = df.copy()
    df["lhd_tertile"] = pd.qcut(
        df["linear_heat_density_kwh_per_m_a"],
        q=3,
        labels=["low", "medium", "high"],
        duplicates="drop",
    )
    return df


def set_scientific_axes(ax):
    ax.set_xlabel(r"Annual linear heat density, $q_\mathrm{L}$ (kWh m$^{-1}$ a$^{-1}$)")
    ax.set_ylabel(r"LCOH (ct kWh$^{-1}$)")
    ax.grid(True, which="major", color="#D0D0D0", linewidth=0.8, alpha=0.75)
    ax.grid(True, which="minor", color="#E8E8E8", linewidth=0.5, alpha=0.55)
    ax.minorticks_on()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", which="major", length=5, width=1.0)
    ax.tick_params(axis="both", which="minor", length=3, width=0.8)


def add_model_label(ax, text):
    ax.text(
        0.025,
        0.975,
        text,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=11,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "white",
            "edgecolor": "#B8B8B8",
            "alpha": 0.94,
        },
    )


def density_term(df, transform):
    if transform == "linear":
        return df["linear_heat_density_kwh_per_m_a"] / 1000.0
    if transform == "log":
        return np.log(df["linear_heat_density_kwh_per_m_a"])
    raise ValueError("transform must be 'linear' or 'log'.")


def density_term_from_values(density_kwh_per_m, transform):
    if transform == "linear":
        return density_kwh_per_m / 1000.0
    if transform == "log":
        return np.log(density_kwh_per_m)
    raise ValueError("transform must be 'linear' or 'log'.")


def fit_ols(
    df,
    model_name,
    response_name="mean",
    response_column="mean_lcoh_ct_per_kwh",
    transform=None,
    include_district=False,
    include_lhd_tertile=False,
    include_lhd_tertile_interaction=False,
):
    model_df = df.copy()

    x_parts = [pd.Series(1.0, index=model_df.index, name="intercept")]
    if transform is not None:
        density_column = "density_1000_kwh_per_m_a" if transform == "linear" else "ln_density_kwh_per_m_a"
        model_df[density_column] = density_term(model_df, transform)
        x_parts.append(model_df[density_column])
    if include_lhd_tertile or include_lhd_tertile_interaction:
        tertile_dummies = pd.get_dummies(model_df["lhd_tertile"], prefix="lhd", drop_first=True, dtype=float)
        x_parts.append(tertile_dummies)
        if include_lhd_tertile_interaction:
            if transform is None:
                raise ValueError("LHD tertile interaction requires a density transform.")
            interaction_terms = tertile_dummies.mul(model_df[density_column], axis=0)
            interaction_terms = interaction_terms.rename(
                columns={column: f"{density_column}_x_{column}" for column in interaction_terms.columns}
            )
            x_parts.append(interaction_terms)
    if include_district:
        dummies = pd.get_dummies(model_df["district"], prefix="district", drop_first=True, dtype=float)
        x_parts.append(dummies)

    x = pd.concat(x_parts, axis=1).astype(float)
    y = model_df[response_column].astype(float)

    results = sm.OLS(y, x).fit()
    n_obs = int(results.nobs)
    rss = float(results.ssr)
    rmse = float(np.sqrt(rss / n_obs))
    summary = {
        "model": model_name,
        "response": response_name,
        "response_column": response_column,
        "density_transform": transform if transform is not None else "none",
        "includes_district_type": include_district,
        "includes_lhd_tertile": include_lhd_tertile,
        "includes_lhd_tertile_interaction": include_lhd_tertile_interaction,
        "n_observations": n_obs,
        "n_parameters": int(results.df_model + 1),
        "df_model": float(results.df_model),
        "df_resid": float(results.df_resid),
        "r2": float(results.rsquared),
        "adjusted_r2": float(results.rsquared_adj),
        "rmse_ct_per_kwh": rmse,
        "residual_standard_error": float(np.sqrt(results.mse_resid)),
        "rss": rss,
        "aic": float(results.aic),
        "bic": float(results.bic),
        "f_statistic": float(results.fvalue) if results.fvalue is not None else np.nan,
        "f_pvalue": float(results.f_pvalue) if results.f_pvalue is not None else np.nan,
        "condition_number": float(results.condition_number),
    }
    conf_int = results.conf_int()
    coefficients = pd.DataFrame(
        {
            "model": model_name,
            "response": response_name,
            "term": x.columns,
            "coefficient": results.params.reindex(x.columns).to_numpy(),
            "std_error": results.bse.reindex(x.columns).to_numpy(),
            "t_value": results.tvalues.reindex(x.columns).to_numpy(),
            "p_value": results.pvalues.reindex(x.columns).to_numpy(),
            "ci_lower_95": conf_int.loc[x.columns, 0].to_numpy(),
            "ci_upper_95": conf_int.loc[x.columns, 1].to_numpy(),
        }
    )
    return summary, coefficients, results.params.to_dict(), results.summary().as_text()


def regression_design_matrix(
    df,
    transform=None,
    include_district=False,
    include_lhd_tertile=False,
    include_lhd_tertile_interaction=False,
    columns=None,
):
    model_df = df.copy()
    x_parts = [pd.Series(1.0, index=model_df.index, name="intercept")]
    density_column = None
    if transform is not None:
        density_column = "density_1000_kwh_per_m_a" if transform == "linear" else "ln_density_kwh_per_m_a"
        model_df[density_column] = density_term(model_df, transform)
        x_parts.append(model_df[density_column])
    if include_lhd_tertile or include_lhd_tertile_interaction:
        tertile_dummies = pd.get_dummies(model_df["lhd_tertile"], prefix="lhd", drop_first=True, dtype=float)
        x_parts.append(tertile_dummies)
        if include_lhd_tertile_interaction:
            if transform is None:
                raise ValueError("LHD tertile interaction requires a density transform.")
            interaction_terms = tertile_dummies.mul(model_df[density_column], axis=0)
            interaction_terms = interaction_terms.rename(
                columns={column: f"{density_column}_x_{column}" for column in interaction_terms.columns}
            )
            x_parts.append(interaction_terms)
    if include_district:
        x_parts.append(pd.get_dummies(model_df["district"], prefix="district", drop_first=True, dtype=float))
    x = pd.concat(x_parts, axis=1).astype(float)
    if columns is not None:
        x = x.reindex(columns=columns, fill_value=0.0)
    return x


def repeated_train_test_validation(
    df,
    repeats=VALIDATION_REPEATS,
    test_fraction=VALIDATION_TEST_FRACTION,
    random_seed=VALIDATION_RANDOM_SEED,
):
    rng = np.random.default_rng(random_seed)
    rows = []
    n_obs = len(df)
    n_test = max(1, int(round(n_obs * test_fraction)))

    for repeat in range(repeats):
        shuffled = rng.permutation(df.index.to_numpy())
        test_index = shuffled[:n_test]
        train_index = shuffled[n_test:]
        train = df.loc[train_index].copy()
        test = df.loc[test_index].copy()

        for response_name, response_column in REGRESSION_TARGETS.items():
            y_train = train[response_column].astype(float)
            y_test = test[response_column].astype(float)
            for model_name, transform, include_district, include_lhd_tertile, include_lhd_tertile_interaction in MODEL_SPECS:
                x_train = regression_design_matrix(
                    train,
                    transform=transform,
                    include_district=include_district,
                    include_lhd_tertile=include_lhd_tertile,
                    include_lhd_tertile_interaction=include_lhd_tertile_interaction,
                )
                x_test = regression_design_matrix(
                    test,
                    transform=transform,
                    include_district=include_district,
                    include_lhd_tertile=include_lhd_tertile,
                    include_lhd_tertile_interaction=include_lhd_tertile_interaction,
                    columns=x_train.columns,
                )
                result = sm.OLS(y_train, x_train).fit()
                y_pred = result.predict(x_test)
                residuals = y_test - y_pred
                sse = float(np.sum(residuals**2))
                sst = float(np.sum((y_test - y_test.mean()) ** 2))
                rows.append(
                    {
                        "repeat": repeat,
                        "model": model_name,
                        "response": response_name,
                        "response_column": response_column,
                        "n_train": len(train),
                        "n_test": len(test),
                        "train_r2": float(result.rsquared),
                        "test_r2": np.nan if sst == 0 else 1.0 - sse / sst,
                        "test_mae_ct_per_kwh": float(np.mean(np.abs(residuals))),
                        "test_rmse_ct_per_kwh": float(np.sqrt(np.mean(residuals**2))),
                    }
                )
    raw = pd.DataFrame(rows)
    summary = (
        raw.groupby(["model", "response"], as_index=False)
        .agg(
            repeats=("repeat", "nunique"),
            train_r2_mean=("train_r2", "mean"),
            train_r2_std=("train_r2", "std"),
            test_r2_mean=("test_r2", "mean"),
            test_r2_std=("test_r2", "std"),
            test_mae_mean_ct_per_kwh=("test_mae_ct_per_kwh", "mean"),
            test_mae_std_ct_per_kwh=("test_mae_ct_per_kwh", "std"),
            test_rmse_mean_ct_per_kwh=("test_rmse_ct_per_kwh", "mean"),
            test_rmse_std_ct_per_kwh=("test_rmse_ct_per_kwh", "std"),
        )
    )
    return raw, summary


def leave_one_seed_out_validation(df):
    rows = []
    for test_index in df.index:
        train = df.drop(index=test_index).copy()
        test = df.loc[[test_index]].copy()
        test_case = f"{test['district'].iloc[0]}_seed_{int(test['seed'].iloc[0])}"

        for response_name, response_column in REGRESSION_TARGETS.items():
            y_train = train[response_column].astype(float)
            y_test = test[response_column].astype(float)
            for model_name, transform, include_district, include_lhd_tertile, include_lhd_tertile_interaction in MODEL_SPECS:
                x_train = regression_design_matrix(
                    train,
                    transform=transform,
                    include_district=include_district,
                    include_lhd_tertile=include_lhd_tertile,
                    include_lhd_tertile_interaction=include_lhd_tertile_interaction,
                )
                x_test = regression_design_matrix(
                    test,
                    transform=transform,
                    include_district=include_district,
                    include_lhd_tertile=include_lhd_tertile,
                    include_lhd_tertile_interaction=include_lhd_tertile_interaction,
                    columns=x_train.columns,
                )
                result = sm.OLS(y_train, x_train).fit()
                y_pred = result.predict(x_test)
                error = float(y_test.iloc[0] - y_pred.iloc[0])
                rows.append(
                    {
                        "test_case": test_case,
                        "model": model_name,
                        "response": response_name,
                        "response_column": response_column,
                        "n_train": len(train),
                        "n_test": 1,
                        "train_r2": float(result.rsquared),
                        "actual": float(y_test.iloc[0]),
                        "predicted": float(y_pred.iloc[0]),
                        "error": error,
                        "absolute_error": abs(error),
                        "squared_error": error**2,
                    }
                )
    raw = pd.DataFrame(rows)
    summary = (
        raw.groupby(["model", "response"], as_index=False)
        .agg(
            folds=("test_case", "nunique"),
            train_r2_mean=("train_r2", "mean"),
            train_r2_std=("train_r2", "std"),
            mae_ct_per_kwh=("absolute_error", "mean"),
            rmse_ct_per_kwh=("squared_error", lambda values: float(np.sqrt(np.mean(values)))),
            error_std_ct_per_kwh=("error", "std"),
        )
    )
    return raw, summary


def regression_comparison(df):
    fitted_models = []
    for response_name, response_column in REGRESSION_TARGETS.items():
        for model_name, transform, include_district, include_lhd_tertile, include_lhd_tertile_interaction in MODEL_SPECS:
            fitted_models.append(
                fit_ols(
                    df,
                    model_name=model_name,
                    response_name=response_name,
                    response_column=response_column,
                    transform=transform,
                    include_district=include_district,
                    include_lhd_tertile=include_lhd_tertile,
                    include_lhd_tertile_interaction=include_lhd_tertile_interaction,
                )
            )

    summary = pd.DataFrame([item[0] for item in fitted_models])
    coefficients = pd.concat([item[1] for item in fitted_models], ignore_index=True)
    beta_by_model = {
        (item[0]["model"], item[0]["response"]): item[2]
        for item in fitted_models
    }
    statsmodels_summaries = {
        f"{item[0]['model']}__{item[0]['response']}": item[3]
        for item in fitted_models
    }
    return summary, coefficients, beta_by_model, statsmodels_summaries


def beta_for(beta_by_model, model_name, response_name="mean"):
    return beta_by_model[(model_name, response_name)]


def model_r2(summary, model_name, response_name):
    row = summary[(summary["model"] == model_name) & (summary["response"] == response_name)]
    return row["r2"].iloc[0]


def model_r2_label(summary, model_name):
    return (
        r"$R^2$ lower/mean/upper = "
        f"{model_r2(summary, model_name, 'lower'):.3f} / "
        f"{model_r2(summary, model_name, 'mean'):.3f} / "
        f"{model_r2(summary, model_name, 'upper'):.3f}"
    )


def predict_density_only(beta, density_kwh_per_m, transform):
    term = "density_1000_kwh_per_m_a" if transform == "linear" else "ln_density_kwh_per_m_a"
    return beta["intercept"] + beta[term] * density_term_from_values(density_kwh_per_m, transform)


def predict_density_plus_district(beta, district, density_kwh_per_m, transform):
    term = "density_1000_kwh_per_m_a" if transform == "linear" else "ln_density_kwh_per_m_a"
    district_shift = beta.get(f"district_{district}", 0.0)
    return beta["intercept"] + district_shift + beta[term] * density_term_from_values(density_kwh_per_m, transform)


def predict_log_plus_tertile(beta, tertile, density_kwh_per_m):
    tertile_shift = beta.get(f"lhd_{tertile}", 0.0)
    return beta["intercept"] + tertile_shift + beta["ln_density_kwh_per_m_a"] * np.log(density_kwh_per_m)


def predict_log_times_tertile(beta, tertile, density_kwh_per_m):
    ln_density = np.log(density_kwh_per_m)
    tertile_shift = beta.get(f"lhd_{tertile}", 0.0)
    slope_shift = beta.get(f"ln_density_kwh_per_m_a_x_lhd_{tertile}", 0.0)
    return beta["intercept"] + tertile_shift + (beta["ln_density_kwh_per_m_a"] + slope_shift) * ln_density


def predictions_for_responses(predictor, beta_by_model, model_name, *args):
    return {
        response_name: predictor(beta_for(beta_by_model, model_name, response_name), *args)
        for response_name in REGRESSION_TARGETS
    }


def plot_response_band(ax, x, predictions, color, label=None, linestyle="-", linewidth=2.0, alpha=BAND_ALPHA):
    ax.fill_between(
        x,
        predictions["lower"],
        predictions["upper"],
        color=color,
        alpha=alpha,
        linewidth=0,
    )
    ax.plot(
        x,
        predictions["mean"],
        color=color,
        linestyle=linestyle,
        linewidth=linewidth,
        label=label,
    )


def plot_observations_by_district(ax, df, color_by_district, alpha=0.78):
    for district in sorted(df["district"].unique()):
        sub = df[df["district"] == district]
        yerr_lower = sub["mean_lcoh_ct_per_kwh"] - sub["min_lcoh_ct_per_kwh"]
        yerr_upper = sub["max_lcoh_ct_per_kwh"] - sub["mean_lcoh_ct_per_kwh"]
        ax.errorbar(
            sub["linear_heat_density_kwh_per_m_a"],
            sub["mean_lcoh_ct_per_kwh"],
            yerr=[yerr_lower, yerr_upper],
            fmt="o",
            markersize=6.2,
            capsize=3,
            elinewidth=1.0,
            alpha=alpha,
            color=color_by_district[district],
            markeredgecolor="white",
            markeredgewidth=0.55,
            label=f"District {display_district(district)}",
        )


def plot_observations_by_tertile(ax, df, color_by_tertile):
    for tertile in ("low", "medium", "high"):
        sub = df[df["lhd_tertile"] == tertile]
        if sub.empty:
            continue
        yerr_lower = sub["mean_lcoh_ct_per_kwh"] - sub["min_lcoh_ct_per_kwh"]
        yerr_upper = sub["max_lcoh_ct_per_kwh"] - sub["mean_lcoh_ct_per_kwh"]
        ax.errorbar(
            sub["linear_heat_density_kwh_per_m_a"],
            sub["mean_lcoh_ct_per_kwh"],
            yerr=[yerr_lower, yerr_upper],
            fmt="o",
            markersize=6.2,
            capsize=3,
            elinewidth=1.0,
            alpha=0.72,
            color=color_by_tertile[tertile],
            markeredgecolor="white",
            markeredgewidth=0.55,
            label=None,
        )


def plot_ranges(df, output_prefix):
    if df.empty:
        raise ValueError("No complete central seed ranges found.")

    districts = sorted(df["district"].unique())
    color_by_district = district_color_map(districts)
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
    plot_observations_by_district(ax, df, color_by_district)
    set_scientific_axes(ax)
    ax.set_title("Central LCOH versus annual linear heat density")
    ax.legend(ncols=2, frameon=False, loc="best")
    fig.savefig(f"{output_prefix}.pdf")
    plt.close(fig)


def format_signed_term(coefficient, label):
    sign = "+" if coefficient >= 0 else "-"
    return f" {sign} {abs(coefficient):.2f} {label}"


def equation(beta, transform):
    if transform == "linear":
        return (
            f"{beta['intercept']:.2f}"
            + format_signed_term(beta["density_1000_kwh_per_m_a"], "q_L/1000")
        )
    if transform == "log":
        return (
            f"{beta['intercept']:.2f}"
            + format_signed_term(beta["ln_density_kwh_per_m_a"], "ln(q_L/q0)")
        )
    raise ValueError("transform must be 'linear' or 'log'.")


def draw_equations_page(fig, beta_by_model, summary, page):
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(
        0.03,
        0.96,
        "Central LCOH regression equations" if page == 1 else "Categorical regression equations",
        fontsize=15,
        weight="bold",
        transform=ax.transAxes,
    )

    if page == 1:
        linear_betas = {name: beta_for(beta_by_model, "linear_density_only", name) for name in REGRESSION_TARGETS}
        log_betas = {name: beta_for(beta_by_model, "log_density_only", name) for name in REGRESSION_TARGETS}
        lines = [
            "Definitions",
            "  q_L is annual linear heat density in kWh m^-1 a^-1.",
            "  LCOH = 100 * (C_EH,operation + C_central) / Q_heat",
            "  C_EH,operation excludes building-side electricity costs and revenues.",
            "  Decentral device investments, e.g. decentral PV, are not included.",
            "  Lower, mean, and upper curves are fitted to central min, mean, and max cost cases.",
            "",
            "Model 1: linear heat-density model",
            "  LCOH_min(q_L)  = " + equation(linear_betas["lower"], "linear"),
            "  LCOH_mean(q_L) = " + equation(linear_betas["mean"], "linear"),
            "  LCOH_max(q_L)  = " + equation(linear_betas["upper"], "linear"),
            (
                "  R2 min/mean/max = "
                f"{model_r2(summary, 'linear_density_only', 'lower'):.3f} / "
                f"{model_r2(summary, 'linear_density_only', 'mean'):.3f} / "
                f"{model_r2(summary, 'linear_density_only', 'upper'):.3f}"
            ),
            "",
            "Model 2: logarithmic heat-density model",
            "  LCOH_min(q_L)  = " + equation(log_betas["lower"], "log"),
            "  LCOH_mean(q_L) = " + equation(log_betas["mean"], "log"),
            "  LCOH_max(q_L)  = " + equation(log_betas["upper"], "log"),
            (
                "  R2 min/mean/max = "
                f"{model_r2(summary, 'log_density_only', 'lower'):.3f} / "
                f"{model_r2(summary, 'log_density_only', 'mean'):.3f} / "
                f"{model_r2(summary, 'log_density_only', 'upper'):.3f}"
            ),
        ]
    elif page == 2:
        tertile_mean = beta_for(beta_by_model, "log_density_plus_lhd_tertile", "mean")
        district_mean = beta_for(beta_by_model, "log_density_plus_district", "mean")
        lines = [
            "Model 3: ln(q_L/q0) + heat-density class",
            "  Reference class: low heat-density tertile",
            "  LCOH_mean,low(q_L)    = " + equation(tertile_mean, "log"),
            (
                "  LCOH_mean,medium(q_L) = "
                + equation(tertile_mean, "log")
                + format_signed_term(tertile_mean.get("lhd_medium", 0.0), "")
            ),
            (
                "  LCOH_mean,high(q_L)   = "
                + equation(tertile_mean, "log")
                + format_signed_term(tertile_mean.get("lhd_high", 0.0), "")
            ),
            (
                "  R2 min/mean/max = "
                f"{model_r2(summary, 'log_density_plus_lhd_tertile', 'lower'):.3f} / "
                f"{model_r2(summary, 'log_density_plus_lhd_tertile', 'mean'):.3f} / "
                f"{model_r2(summary, 'log_density_plus_lhd_tertile', 'upper'):.3f}"
            ),
            "",
            "Model 4: ln(q_L/q0) x heat-density class",
            "  This model allows both the intercept and ln(q_L/q0) slope to vary by class.",
            (
                "  R2 min/mean/max = "
                f"{model_r2(summary, 'log_density_times_lhd_tertile', 'lower'):.3f} / "
                f"{model_r2(summary, 'log_density_times_lhd_tertile', 'mean'):.3f} / "
                f"{model_r2(summary, 'log_density_times_lhd_tertile', 'upper'):.3f}"
            ),
            "",
            "Model 5: ln(q_L/q0) + district type",
            "  Reference district type: A",
            "  LCOH_mean,A(q_L) = " + equation(district_mean, "log"),
        ]
        for district in ("B", "C", "D", "E", "F", "H", "I"):
            lines.append(
                f"  LCOH_mean,{display_district(district)}(q_L) = "
                + equation(district_mean, "log")
                + format_signed_term(district_mean.get(f"district_{district}", 0.0), "")
            )
        lines.append(
            "  R2 min/mean/max = "
            f"{model_r2(summary, 'log_density_plus_district', 'lower'):.3f} / "
            f"{model_r2(summary, 'log_density_plus_district', 'mean'):.3f} / "
            f"{model_r2(summary, 'log_density_plus_district', 'upper'):.3f}"
        )
    else:
        raise ValueError("page must be 1 or 2")

    ax.text(
        0.03,
        0.89,
        "\n".join(lines),
        va="top",
        ha="left",
        family="monospace",
        fontsize=8.7,
        transform=ax.transAxes,
    )


def save_regression_model_report(df, output_prefix, beta_by_model, summary):
    report_prefix = f"{output_prefix}_regression_models"
    pdf_path = f"{report_prefix}.pdf"
    for old_file in Path(output_prefix).parent.glob(f"{Path(report_prefix).name}_*.svg"):
        old_file.unlink()

    districts = sorted(df["district"].unique())
    color_by_district = district_color_map(districts)
    color_by_tertile = TERTILE_COLORS
    x_global = np.linspace(
        df["linear_heat_density_kwh_per_m_a"].min(),
        df["linear_heat_density_kwh_per_m_a"].max(),
        200,
    )

    figures = []

    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
    plot_observations_by_district(ax, df, color_by_district)
    linear_predictions = predictions_for_responses(
        predict_density_only, beta_by_model, "linear_density_only", x_global, "linear"
    )
    plot_response_band(ax, x_global, linear_predictions, "#111111", "Linear fit", linewidth=2.4)
    ax.set_title(r"Model 1: linear heat density")
    add_model_label(ax, model_r2_label(summary, "linear_density_only"))
    set_scientific_axes(ax)
    ax.legend(ncols=2, frameon=False, loc="best")
    figures.append(("01_lhd", fig))

    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
    plot_observations_by_district(ax, df, color_by_district)
    log_predictions = predictions_for_responses(
        predict_density_only, beta_by_model, "log_density_only", x_global, "log"
    )
    plot_response_band(ax, x_global, log_predictions, "#111111", "Logarithmic fit", linestyle="--", linewidth=2.4)
    ax.set_title(r"Model 2: logarithmic heat density")
    add_model_label(ax, model_r2_label(summary, "log_density_only"))
    set_scientific_axes(ax)
    ax.legend(ncols=2, frameon=False, loc="best")
    figures.append(("02_ln_lhd", fig))

    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
    plot_observations_by_tertile(ax, df, color_by_tertile)
    for tertile in ("low", "medium", "high"):
        sub = df[df["lhd_tertile"] == tertile]
        if sub.empty:
            continue
        x_tertile = np.linspace(
            sub["linear_heat_density_kwh_per_m_a"].min(),
            sub["linear_heat_density_kwh_per_m_a"].max(),
            80,
        )
        tertile_predictions = predictions_for_responses(
            predict_log_plus_tertile, beta_by_model, "log_density_plus_lhd_tertile", tertile, x_tertile
        )
        plot_response_band(
            ax,
            x_tertile,
            tertile_predictions,
            color_by_tertile[tertile],
            "Logarithmic fit" if tertile == "low" else None,
        )
    ax.set_title(r"Model 3: logarithmic heat density with density class")
    add_model_label(ax, model_r2_label(summary, "log_density_plus_lhd_tertile"))
    set_scientific_axes(ax)
    ax.legend(ncols=2, frameon=False, loc="best")
    figures.append(("03_ln_lhd_plus_lhd_tertile", fig))

    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
    plot_observations_by_tertile(ax, df, color_by_tertile)
    for tertile in ("low", "medium", "high"):
        sub = df[df["lhd_tertile"] == tertile]
        if sub.empty:
            continue
        x_tertile = np.linspace(
            sub["linear_heat_density_kwh_per_m_a"].min(),
            sub["linear_heat_density_kwh_per_m_a"].max(),
            80,
        )
        tertile_predictions = predictions_for_responses(
            predict_log_times_tertile, beta_by_model, "log_density_times_lhd_tertile", tertile, x_tertile
        )
        plot_response_band(
            ax,
            x_tertile,
            tertile_predictions,
            color_by_tertile[tertile],
            "Logarithmic fit" if tertile == "low" else None,
        )
    ax.set_title(r"Model 4: logarithmic heat density with class-specific slopes")
    add_model_label(ax, model_r2_label(summary, "log_density_times_lhd_tertile"))
    set_scientific_axes(ax)
    ax.legend(ncols=2, frameon=False, loc="best")
    figures.append(("04_ln_lhd_times_lhd_tertile", fig))

    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)
    plot_observations_by_district(ax, df, color_by_district)
    for district in districts:
        sub = df[df["district"] == district]
        x_district = np.linspace(
            sub["linear_heat_density_kwh_per_m_a"].min(),
            sub["linear_heat_density_kwh_per_m_a"].max(),
            80,
        )
        district_predictions = predictions_for_responses(
            predict_density_plus_district,
            beta_by_model,
            "log_density_plus_district",
            district,
            x_district,
            "log",
        )
        plot_response_band(ax, x_district, district_predictions, color_by_district[district], linewidth=1.8)
    ax.set_title(r"Model 5: logarithmic heat density with district type")
    add_model_label(ax, model_r2_label(summary, "log_density_plus_district"))
    set_scientific_axes(ax)
    ax.legend(ncols=2, frameon=False, loc="best")
    figures.append(("05_ln_lhd_plus_district_type", fig))

    fig = plt.figure(figsize=FIGURE_SIZE, constrained_layout=True)
    draw_equations_page(fig, beta_by_model, summary, page=1)
    figures.append(("06_equations_basic_models", fig))

    fig = plt.figure(figsize=FIGURE_SIZE, constrained_layout=True)
    draw_equations_page(fig, beta_by_model, summary, page=2)
    figures.append(("07_equations_categorical_models", fig))

    with PdfPages(pdf_path) as pdf:
        for name, fig in figures:
            pdf.savefig(fig)
            save_presentation_svg(fig, f"{report_prefix}_{name}.svg")
            plt.close(fig)


def plot_regression_comparison(df, output_prefix, beta_by_model, summary):
    if df.empty:
        raise ValueError("No complete central seed ranges found.")

    districts = sorted(df["district"].unique())
    color_by_district = district_color_map(districts)
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, constrained_layout=True)

    for district in districts:
        sub = df[df["district"] == district].sort_values("linear_heat_density_kwh_per_m_a")
        color = color_by_district[district]
        yerr_lower = sub["mean_lcoh_ct_per_kwh"] - sub["min_lcoh_ct_per_kwh"]
        yerr_upper = sub["max_lcoh_ct_per_kwh"] - sub["mean_lcoh_ct_per_kwh"]
        ax.errorbar(
            sub["linear_heat_density_kwh_per_m_a"],
            sub["mean_lcoh_ct_per_kwh"],
            yerr=[yerr_lower, yerr_upper],
            fmt="o",
            markersize=6.2,
            capsize=3,
            elinewidth=1.0,
            alpha=0.55,
            color=color,
            markeredgecolor="white",
            markeredgewidth=0.55,
            label=f"District {display_district(district)}",
        )
        x_district = np.linspace(
            sub["linear_heat_density_kwh_per_m_a"].min(),
            sub["linear_heat_density_kwh_per_m_a"].max(),
            50,
        )
        district_predictions = predictions_for_responses(
            predict_density_plus_district,
            beta_by_model,
            "log_density_plus_district",
            district,
            x_district,
            "log",
        )
        plot_response_band(ax, x_district, district_predictions, color=color, linewidth=1.8, alpha=0.10)

    x_global = np.linspace(
        df["linear_heat_density_kwh_per_m_a"].min(),
        df["linear_heat_density_kwh_per_m_a"].max(),
        200,
    )
    log_predictions = predictions_for_responses(
        predict_density_only,
        beta_by_model,
        "log_density_only",
        x_global,
        "log",
    )
    plot_response_band(
        ax,
        x_global,
        log_predictions,
        "#111111",
        "Logarithmic fit",
        linestyle="--",
        linewidth=2.4,
        alpha=0.10,
    )
    text = (
        r"$R^2$ shown as lower/mean/upper"
        "\n"
        rf"$q_\mathrm{{L}}$: {model_r2_label(summary, 'linear_density_only').split('= ')[1]}"
        "\n"
        rf"Logarithmic model: {model_r2_label(summary, 'log_density_only').split('= ')[1]}"
        "\n"
        rf"Logarithmic model + density class: {model_r2_label(summary, 'log_density_plus_lhd_tertile').split('= ')[1]}"
        "\n"
        rf"Logarithmic model x density class: {model_r2_label(summary, 'log_density_times_lhd_tertile').split('= ')[1]}"
        "\n"
        rf"Logarithmic model + district type: {model_r2_label(summary, 'log_density_plus_district').split('= ')[1]}"
    )
    add_model_label(ax, text)
    ax.set_title("Central LCOH: effect of annual linear heat density and district type")
    set_scientific_axes(ax)
    ax.legend(ncols=2, frameon=False, loc="best", handlelength=2.3)

    regression_prefix = f"{output_prefix}_regression"
    fig.savefig(f"{regression_prefix}.pdf")
    plt.close(fig)


def plot_train_test_validation(validation_summary, validation_raw, output_prefix):
    mean_summary = validation_summary[validation_summary["response"] == "mean"].copy()
    mean_summary["model_label"] = mean_summary["model"].map(MODEL_DISPLAY_NAMES)
    mean_summary = mean_summary.set_index("model").loc[list(MODEL_DISPLAY_NAMES)].reset_index()
    mean_raw = validation_raw[validation_raw["response"] == "mean"].copy()

    x = np.arange(len(mean_summary))
    colors = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#E45756"]

    fig, ax = plt.subplots(figsize=(8.6, 5.2), constrained_layout=True)
    ax.bar(
        x,
        mean_summary["rmse_ct_per_kwh"],
        color=colors,
        alpha=0.88,
    )
    rng = np.random.default_rng(7)
    for i, model in enumerate(mean_summary["model"]):
        errors = mean_raw.loc[mean_raw["model"] == model, "absolute_error"].astype(float).to_numpy()
        jitter = rng.uniform(-0.16, 0.16, size=len(errors))
        ax.scatter(
            np.full(len(errors), x[i]) + jitter,
            errors,
            s=24,
            color="#1F1F1F",
            alpha=0.62,
            edgecolors="white",
            linewidths=0.35,
            zorder=3,
        )
    ax.set_ylabel(r"RMSE (ct kWh$^{-1}$)")
    ax.set_title("Leave-one-district-seed-out validation")
    ax.set_xticks(x)
    ax.set_xticklabels(mean_summary["model_label"], rotation=28, ha="right")
    ax.grid(True, axis="y", color="#D0D0D0", linewidth=0.8, alpha=0.75)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", which="major", length=5, width=1.0)

    validation_prefix = f"{output_prefix}_leave_one_seed_out_validation"
    fig.savefig(f"{validation_prefix}.pdf")
    save_presentation_svg(fig, f"{validation_prefix}.svg")
    plt.close(fig)


def main():
    apply_publication_style()
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--require-complete-decentral-pair",
        action="store_true",
        help="Restrict LCOH analysis to seeds that also have complete decentral results.",
    )
    args = parser.parse_args()

    if not args.results_dir.exists():
        raise FileNotFoundError(f"Results directory does not exist: {args.results_dir}")
    if not args.config_path.exists():
        raise FileNotFoundError(f"Config file does not exist: {args.config_path}")

    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    config_values = read_config_values(args.config_path)
    ranges, cases = make_ranges(
        args.results_dir,
        config_values,
        require_complete_decentral=args.require_complete_decentral_pair,
    )
    if ranges.empty:
        raise ValueError("No complete central scenarios found.")
    ranges = add_lhd_tertiles(ranges)

    regression_summary, regression_coefficients, beta_by_model, statsmodels_summaries = regression_comparison(ranges)
    validation_raw, validation_summary = repeated_train_test_validation(ranges)
    loo_raw, loo_summary = leave_one_seed_out_validation(ranges)
    ranges.to_csv(f"{args.output_prefix}_ranges.csv", index=False)
    cases.to_csv(f"{args.output_prefix}_central_cases.csv", index=False)
    regression_summary.to_csv(f"{args.output_prefix}_regression_summary.csv", index=False)
    regression_coefficients.to_csv(f"{args.output_prefix}_regression_coefficients.csv", index=False)
    validation_raw.to_csv(f"{args.output_prefix}_train_test_validation_raw.csv", index=False)
    validation_summary.to_csv(f"{args.output_prefix}_train_test_validation_summary.csv", index=False)
    loo_raw.to_csv(f"{args.output_prefix}_leave_one_seed_out_validation_raw.csv", index=False)
    loo_summary.to_csv(f"{args.output_prefix}_leave_one_seed_out_validation_summary.csv", index=False)
    with open(f"{args.output_prefix}_statsmodels_summaries.txt", "w", encoding="utf-8") as file:
        for model_name, model_summary in statsmodels_summaries.items():
            file.write(f"{'=' * 100}\n")
            file.write(f"{model_name}\n")
            file.write(f"{'=' * 100}\n")
            file.write(model_summary)
            file.write("\n\n")

    plot_ranges(ranges, args.output_prefix)
    plot_regression_comparison(ranges, args.output_prefix, beta_by_model, regression_summary)
    plot_train_test_validation(loo_summary, loo_raw, args.output_prefix)
    save_regression_model_report(ranges, args.output_prefix, beta_by_model, regression_summary)

    print(f"Wrote {len(ranges)} central seed ranges")
    print(f"Wrote {len(cases)} central cost cases")
    print(f"Wrote {args.output_prefix}.pdf")
    print(f"Wrote {args.output_prefix}_ranges.csv")
    print(f"Wrote {args.output_prefix}_central_cases.csv")
    print(f"Wrote {args.output_prefix}_regression.pdf")
    print(f"Wrote {args.output_prefix}_regression_summary.csv")
    print(f"Wrote {args.output_prefix}_regression_coefficients.csv")
    print(f"Wrote {args.output_prefix}_train_test_validation_raw.csv")
    print(f"Wrote {args.output_prefix}_train_test_validation_summary.csv")
    print(f"Wrote {args.output_prefix}_leave_one_seed_out_validation_raw.csv")
    print(f"Wrote {args.output_prefix}_leave_one_seed_out_validation_summary.csv")
    print(f"Wrote {args.output_prefix}_leave_one_seed_out_validation.pdf")
    print(f"Wrote {args.output_prefix}_leave_one_seed_out_validation.svg")
    print(f"Wrote {args.output_prefix}_statsmodels_summaries.txt")
    print(f"Wrote {args.output_prefix}_regression_models.pdf")
    print(f"Wrote {args.output_prefix}_regression_models_*.svg")


if __name__ == "__main__":
    main()
