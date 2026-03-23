from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import math
import numpy as np


@dataclass
class DebugIssue:
    level: str   # "ERROR" | "WARN" | "INFO"
    code: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DebugReport:
    issues: List[DebugIssue] = field(default_factory=list)

    def add(self, level: str, code: str, message: str, **context: Any) -> None:
        self.issues.append(DebugIssue(level=level, code=code, message=message, context=context))

    @property
    def has_error(self) -> bool:
        return any(i.level == "ERROR" for i in self.issues)

    def summary(self) -> str:
        n_err = sum(1 for i in self.issues if i.level == "ERROR")
        n_warn = sum(1 for i in self.issues if i.level == "WARN")
        n_info = sum(1 for i in self.issues if i.level == "INFO")
        return f"DebugReport(errors={n_err}, warnings={n_warn}, info={n_info})"

    def to_lines(self) -> List[str]:
        lines = [self.summary()]
        for i in self.issues:
            ctx = f" | context={i.context}" if i.context else ""
            lines.append(f"[{i.level}] {i.code}: {i.message}{ctx}")
        return lines


def _is_finite_number(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def _flatten_numeric(name: str, value: Any) -> Iterable[Tuple[str, float]]:
    """Flacht gängige numerische Container ab."""
    if value is None:
        return
    if isinstance(value, (int, float, np.number)):
        yield name, float(value)
        return
    if isinstance(value, np.ndarray):
        for idx, v in np.ndenumerate(value):
            yield f"{name}{idx}", float(v)
        return
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            if isinstance(v, (int, float, np.number)):
                yield f"{name}[{i}]", float(v)
            elif isinstance(v, (list, tuple, np.ndarray)):
                arr = np.array(v, dtype=float)
                for idx, vv in np.ndenumerate(arr):
                    yield f"{name}[{i}]{idx}", float(vv)
        return


def check_nan_inf(params: Dict[str, Any], report: DebugReport) -> None:
    for k, v in params.items():
        any_seen = False
        for kk, vv in _flatten_numeric(k, v):
            any_seen = True
            if not math.isfinite(vv):
                report.add("ERROR", "NUM_NOT_FINITE", f"Nicht-finite Zahl in '{kk}'", value=vv)
        if not any_seen and isinstance(v, dict):
            # flache Rekursion für dicts
            for sk, sv in v.items():
                for kk, vv in _flatten_numeric(f"{k}.{sk}", sv):
                    if not math.isfinite(vv):
                        report.add("ERROR", "NUM_NOT_FINITE", f"Nicht-finite Zahl in '{kk}'", value=vv)


def check_lengths(
    expected_n_districts: Optional[int],
    length_map: Dict[str, int],
    report: DebugReport,
) -> None:
    if expected_n_districts is None:
        return
    for name, n in length_map.items():
        if n != expected_n_districts:
            report.add(
                "ERROR",
                "LENGTH_MISMATCH",
                f"Länge von '{name}' passt nicht zur District-Anzahl",
                expected=expected_n_districts,
                actual=n,
            )


def check_bounds(
    bounds: Sequence[Tuple[str, Optional[float], Optional[float]]],
    report: DebugReport,
) -> None:
    for var_name, lb, ub in bounds:
        if lb is not None and not _is_finite_number(lb):
            report.add("ERROR", "BOUND_NOT_FINITE", f"Untere Grenze ungültig: {var_name}", lb=lb)
        if ub is not None and not _is_finite_number(ub):
            report.add("ERROR", "BOUND_NOT_FINITE", f"Obere Grenze ungültig: {var_name}", ub=ub)
        if lb is not None and ub is not None and lb > ub:
            report.add("ERROR", "BOUND_CONTRADICTION", f"lb > ub bei {var_name}", lb=lb, ub=ub)
        if lb is None and ub is None:
            report.add("WARN", "UNBOUNDED_VAR", f"Variable ohne Bounds: {var_name}")


def check_big_m(constants: Dict[str, float], report: DebugReport, warn_threshold: float = 1e6) -> None:
    for name, value in constants.items():
        if not _is_finite_number(value):
            report.add("ERROR", "BIGM_NOT_FINITE", f"Big-M/Skalierung nicht finite: {name}", value=value)
        elif abs(float(value)) > warn_threshold:
            report.add("WARN", "BIGM_LARGE", f"Sehr großer Wert in {name}", value=value, threshold=warn_threshold)


def check_connectivity(
    n_nodes: int,
    edges: Sequence[Tuple[int, int]],
    must_be_connected: bool,
    report: DebugReport,
) -> None:
    if not must_be_connected:
        return
    if n_nodes <= 0:
        report.add("ERROR", "GRAPH_EMPTY", "Keine Knoten vorhanden")
        return
    if not edges:
        report.add("ERROR", "GRAPH_NO_EDGES", "Keine Kanten vorhanden, Konnektivität unmöglich")
        return

    # einfacher BFS
    graph = {i: set() for i in range(n_nodes)}
    for u, v in edges:
        if not (0 <= u < n_nodes and 0 <= v < n_nodes):
            report.add("ERROR", "GRAPH_INDEX", "Kantenindex außerhalb des Bereichs", edge=(u, v), n_nodes=n_nodes)
            continue
        graph[u].add(v)
        graph[v].add(u)

    seen = set()
    stack = [0]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph[cur] - seen)

    if len(seen) != n_nodes:
        report.add("ERROR", "GRAPH_DISCONNECTED", "Graph ist nicht zusammenhängend", reached=len(seen), total=n_nodes)


def run_pre_solve_checks(
    params: Dict[str, Any],
    expected_n_districts: Optional[int] = None,
    length_map: Optional[Dict[str, int]] = None,
    bounds: Optional[Sequence[Tuple[str, Optional[float], Optional[float]]]] = None,
    big_m_constants: Optional[Dict[str, float]] = None,
    n_nodes: Optional[int] = None,
    edges: Optional[Sequence[Tuple[int, int]]] = None,
    must_be_connected: bool = False,
) -> DebugReport:
    report = DebugReport()
    check_nan_inf(params=params, report=report)

    if length_map:
        check_lengths(expected_n_districts=expected_n_districts, length_map=length_map, report=report)
    if bounds:
        check_bounds(bounds=bounds, report=report)
    if big_m_constants:
        check_big_m(constants=big_m_constants, report=report)
    if n_nodes is not None and edges is not None:
        check_connectivity(n_nodes=n_nodes, edges=edges, must_be_connected=must_be_connected, report=report)

    return report


def gurobi_post_status_diagnose(model: Any, iis_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Optional: Detaildiagnose nach optimize() für Gurobi.
    - Bei INF_OR_UNBD: DualReductions=0 und erneut lösen
    - Bei INFEASIBLE: IIS berechnen
    """
    out: Dict[str, Any] = {"status_before": getattr(model, "Status", None)}
    status = getattr(model, "Status", None)

    # Gurobi Statuscodes: 4=INF_OR_UNBD, 3=INFEASIBLE, 5=UNBOUNDED, 2=OPTIMAL
    if status == 4:
        model.setParam("DualReductions", 0)
        model.optimize()
        out["status_after_dualreductions0"] = model.Status
        status = model.Status

    if status == 3:
        model.computeIIS()
        out["iis_computed"] = True
        if iis_path:
            model.write(iis_path)
            out["iis_written_to"] = iis_path
    elif status == 5:
        out["hint"] = "Modell ist unbounded. Prüfe fehlende Bounds/Big-M."
    elif status == 2:
        out["hint"] = "Modell ist optimal lösbar."
    else:
        out["hint"] = f"Status={status}"

    return out