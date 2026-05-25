from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import cache, lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.optimize import root_scalar
from scipy.stats import gamma as gamma_dist
from scipy.stats import norm

from .core import FrontierMetaAnalyzer, SubmodelSpec, make_tbema_analyzer
from .simulation import (
    SimulationConfig,
    moderator_columns,
    naive_random_effects_log_or,
    profile_columns,
    target_moderators_for_config,
)


@dataclass
class BenchmarkMethodResult:
    method: str
    status: str
    estimate: float | None = None
    std_error: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    tau: float | None = None
    elapsed_sec: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class MethodUnavailableError(RuntimeError):
    pass


def _effect_data(data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = data["treat_events"].to_numpy(dtype=float) + 0.5
    b = data["treat_total"].to_numpy(dtype=float) - data["treat_events"].to_numpy(dtype=float) + 0.5
    c = data["control_events"].to_numpy(dtype=float) + 0.5
    d = data["control_total"].to_numpy(dtype=float) - data["control_events"].to_numpy(dtype=float) + 0.5
    y = np.log((a * d) / (b * c))
    v = 1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d
    se = np.sqrt(v)
    return y, v, se


def _wrap_method(method_name: str, fn: Callable[..., dict[str, float]], data: pd.DataFrame, config: SimulationConfig) -> BenchmarkMethodResult:
    start = time.perf_counter()
    try:
        payload = fn(data, config)
        return BenchmarkMethodResult(method=method_name, status="ok", elapsed_sec=time.perf_counter() - start, **payload)
    except MethodUnavailableError as exc:
        return BenchmarkMethodResult(method=method_name, status="skipped", elapsed_sec=time.perf_counter() - start, note=str(exc))
    except Exception as exc:  # pragma: no cover - defensive path
        return BenchmarkMethodResult(method=method_name, status="error", elapsed_sec=time.perf_counter() - start, note=str(exc))


def _as_windows_path(path: str | Path) -> str:
    raw = str(path)
    if raw.startswith("/mnt/") and len(raw) > 7 and raw[5].isalpha() and raw[6] == "/":
        drive = raw[5].upper()
        rest = raw[7:].replace("/", "\\")
        return f"{drive}:\\{rest}"
    return raw


def _tbema_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    analyzer = make_tbema_analyzer()
    result = analyzer.fit(
        data,
        moderator_cols=moderator_columns(config.moderator_count),
        profile_cols=profile_columns(),
        target_profile=list(config.target_profile),
        target_moderators=target_moderators_for_config(config).tolist(),
        design_strength_col="design_strength",
    )
    return {
        "estimate": result.estimate,
        "std_error": result.std_error,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "tau": result.tau,
        "note": json.dumps({"submodels": result.submodel_weights, "settings": result.settings}),
    }


def _exact_baseline_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    del config
    analyzer = FrontierMetaAnalyzer(
        quadrature_points=5,
        ridge_grid=(0.0,),
        submodel_specs=(SubmodelSpec(name="exact_baseline", include_small_study=False, selection_lambda=0.0),),
    )
    result = analyzer.fit(data)
    return {
        "estimate": result.estimate,
        "std_error": result.std_error,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "tau": result.tau,
        "note": "single exact sparse-data baseline",
    }


def _dersimonian_laird_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    del config
    return naive_random_effects_log_or(data)


def _henmi_copas_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    del config
    y, v, _ = _effect_data(data)
    k = len(y)
    if k < 2:
        raise RuntimeError("Henmi-Copas requires at least two studies.")
    alpha = 0.05

    wi = 1.0 / v
    w1 = np.sum(wi)
    w2 = np.sum(wi**2) / w1
    w3 = np.sum(wi**3) / w1
    w4 = np.sum(wi**4) / w1
    beta = float(np.sum(wi * y) / w1)
    q = float(np.sum(wi * (y - beta) ** 2))
    tau2 = float(max(0.0, (q - (k - 1.0)) / max(w1 - w2, 1e-12)))

    vb = (tau2 * w2 + 1.0) / w1
    se = float(np.sqrt(max(vb, 1e-12)))
    vr = 1.0 + tau2 * w2
    sdr = float(np.sqrt(max(vr, 1e-12)))

    def eq(r: float) -> float:
        return (k - 1.0) + tau2 * (w1 - w2) + (tau2**2) * (((r**2) / (vr**2)) - (1.0 / vr)) * (w3 - w2**2)

    def vq(r: float) -> float:
        r2 = r**2
        recip_vr2 = 1.0 / (vr**2)
        return (
            2.0 * (k - 1.0)
            + 4.0 * tau2 * (w1 - w2)
            + 2.0 * tau2**2 * (w1 * w2 - 2.0 * w3 + w2**2)
            + 4.0 * tau2**2 * (recip_vr2 * r2 - 1.0 / vr) * (w3 - w2**2)
            + 4.0 * tau2**3 * (recip_vr2 * r2 - 1.0 / vr) * (w4 - 2.0 * w2 * w3 + w2**3)
            + 2.0 * tau2**4 * (recip_vr2 - 2.0 * r2 / (vr**3)) * (w3 - w2**2) ** 2
        )

    def scale_fn(r: float) -> float:
        return max(vq(r) / max(eq(r), 1e-12), 1e-12)

    def shape_fn(r: float) -> float:
        numerator = max(eq(r), 1e-12) ** 2
        return max(numerator / max(vq(r), 1e-12), 1e-12)

    def finv(f: float) -> float:
        return (w1 / w2 - 1.0) * (f**2 - 1.0) + (k - 1.0)

    def root_equation(x: float) -> float:
        def integrand(r: float) -> float:
            arg = finv(r / x)
            if arg <= 0:
                gamma_cdf = 0.0
            else:
                gamma_cdf = gamma_dist.cdf(arg, a=shape_fn(sdr * r), scale=scale_fn(sdr * r))
            return gamma_cdf * norm.pdf(r)

        integral, _ = quad(integrand, x, np.inf, limit=200)
        return integral - alpha / 2.0

    lower = 1e-6
    upper = 2.0
    f_lower = root_equation(lower)
    f_upper = root_equation(upper)
    while f_lower * f_upper > 0 and upper < 64.0:
        upper *= 2.0
        f_upper = root_equation(upper)
    if f_lower * f_upper > 0:
        raise RuntimeError("Henmi-Copas root finder failed to bracket the CI equation.")

    root = root_scalar(root_equation, bracket=[lower, upper], method="brentq")
    if not root.converged:
        raise RuntimeError("Henmi-Copas root finder did not converge.")

    u0 = sdr * root.root
    return {
        "estimate": beta,
        "std_error": se,
        "ci_low": float(beta - u0 * se),
        "ci_high": float(beta + u0 * se),
        "tau": float(np.sqrt(tau2)),
        "note": "Translated from metafor hc.rma.uni source",
    }


@lru_cache(maxsize=1)
def _rscript_path() -> str | None:
    rscript = shutil.which("Rscript")
    if rscript is None:
        candidates = sorted(
            Path("/mnt/c/Program Files/R").glob("R-*/bin/Rscript.exe"),
            key=lambda path: path.as_posix(),
            reverse=True,
        )
        if candidates:
            rscript = str(candidates[0])
    return rscript


@cache
def _r_package_environment(packages: tuple[str, ...]) -> tuple[bool, str]:
    rscript = _rscript_path()
    if rscript is None:
        return False, "Rscript not found"
    packages_vector = ", ".join(f"'{package}'" for package in packages)
    probe = subprocess.run(
        [
            rscript,
            "-e",
            (
                f"pkgs <- c({packages_vector}); "
                "ok <- all(vapply(pkgs, requireNamespace, logical(1), quietly=TRUE)); "
                "cat(ifelse(ok, '1', '0'))"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "1":
        joined = ", ".join(packages)
        return False, f"Required R packages not available: {joined}"
    return True, rscript


def _robma_bibma_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    del config
    ok, value = _r_package_environment(("RoBMA",))
    if not ok:
        raise MethodUnavailableError(value)

    project_root = Path(__file__).resolve().parents[1]
    script_path = project_root / "external" / "robma_bibma_adapter.R"
    if not script_path.exists():
        raise RuntimeError("RoBMA adapter script is missing.")

    temp_root = project_root / "results" / "_robma_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="metafrontier_robma_", dir=temp_root) as tmpdir:
        input_path = Path(tmpdir) / "studies.csv"
        output_path = Path(tmpdir) / "result.json"
        data[["study", "treat_events", "control_events", "treat_total", "control_total"]].to_csv(input_path, index=False)
        command = [value, str(script_path), str(input_path), str(output_path)]
        if value.lower().endswith(".exe"):
            command = [value, _as_windows_path(script_path), _as_windows_path(input_path), _as_windows_path(output_path)]
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=project_root,
            timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "RoBMA adapter failed.")
        payload = json.loads(output_path.read_text(encoding="utf-8"))

    status = payload.get("status")
    if status == "skipped":
        raise MethodUnavailableError(str(payload.get("message", "RoBMA adapter skipped")))
    if status != "ok":
        raise RuntimeError(str(payload.get("message", "RoBMA adapter returned an error")))

    return {
        "estimate": float(payload["estimate"]),
        "std_error": float(payload["std_error"]),
        "ci_low": float(payload["ci_low"]),
        "ci_high": float(payload["ci_high"]),
        "tau": float(payload["tau"]),
        "note": str(payload.get("message", "BiBMA external adapter")),
    }


def _run_r_adapter(
    script_name: str,
    data: pd.DataFrame,
    columns: list[str],
    packages: tuple[str, ...],
    timeout: int = 180,
) -> dict[str, float]:
    ok, value = _r_package_environment(packages)
    if not ok:
        raise MethodUnavailableError(value)

    project_root = Path(__file__).resolve().parents[1]
    script_path = project_root / "external" / script_name
    if not script_path.exists():
        raise RuntimeError(f"Adapter script '{script_name}' is missing.")

    temp_root = project_root / "results" / "_r_adapter_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="metafrontier_r_", dir=temp_root) as tmpdir:
        input_path = Path(tmpdir) / "studies.csv"
        output_path = Path(tmpdir) / "result.json"
        data[columns].to_csv(input_path, index=False)
        command = [value, str(script_path), str(input_path), str(output_path)]
        if value.lower().endswith(".exe"):
            command = [value, _as_windows_path(script_path), _as_windows_path(input_path), _as_windows_path(output_path)]
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=project_root,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{script_name} failed.")
        payload = json.loads(output_path.read_text(encoding="utf-8"))

    status = payload.get("status")
    if status == "skipped":
        raise MethodUnavailableError(str(payload.get("message", f"{script_name} skipped")))
    if status != "ok":
        raise RuntimeError(str(payload.get("message", f"{script_name} returned an error")))

    def numeric(key: str, *, required: bool = True) -> float:
        value = payload.get(key)
        if value is None:
            if required:
                raise ValueError(f"{script_name} returned no value for '{key}'.")
            return float("nan")
        numeric_value = float(value) if value is not None else float("nan")
        if required and not np.isfinite(numeric_value):
            raise ValueError(f"{script_name} returned a non-finite value for '{key}'.")
        return numeric_value

    return {
        "estimate": numeric("estimate"),
        "std_error": numeric("std_error"),
        "ci_low": numeric("ci_low"),
        "ci_high": numeric("ci_high"),
        "tau": numeric("tau", required=False),
        "note": str(payload.get("message", script_name)),
    }


def _trimfill_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    del config
    return _run_r_adapter(
        "metafor_trimfill_adapter.R",
        data,
        ["study", "treat_events", "control_events", "treat_total", "control_total"],
        ("metafor",),
        timeout=120,
    )


def _selmodel_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    del config
    return _run_r_adapter(
        "metafor_selmodel_adapter.R",
        data,
        ["study", "treat_events", "control_events", "treat_total", "control_total"],
        ("metafor",),
        timeout=120,
    )


def _copas_payload(data: pd.DataFrame, config: SimulationConfig) -> dict[str, float]:
    del config
    return _run_r_adapter(
        "copas_adapter.R",
        data,
        ["study", "treat_events", "control_events", "treat_total", "control_total"],
        ("meta", "metasens"),
        timeout=120,
    )


METHOD_REGISTRY: dict[str, Callable[[pd.DataFrame, SimulationConfig], BenchmarkMethodResult]] = {
    "tbema": lambda data, config: _wrap_method("tbema", _tbema_payload, data, config),
    "exact_baseline": lambda data, config: _wrap_method("exact_baseline", _exact_baseline_payload, data, config),
    "dersimonian_laird": lambda data, config: _wrap_method("dersimonian_laird", _dersimonian_laird_payload, data, config),
    "henmi_copas": lambda data, config: _wrap_method("henmi_copas", _henmi_copas_payload, data, config),
    "metafor_trimfill_external": lambda data, config: _wrap_method("metafor_trimfill_external", _trimfill_payload, data, config),
    "metafor_selmodel_external": lambda data, config: _wrap_method("metafor_selmodel_external", _selmodel_payload, data, config),
    "copas_selection_external": lambda data, config: _wrap_method("copas_selection_external", _copas_payload, data, config),
    "robma_bibma_external": lambda data, config: _wrap_method("robma_bibma_external", _robma_bibma_payload, data, config),
}


def available_benchmark_methods(include_external: bool = True) -> list[str]:
    methods = ["tbema", "exact_baseline", "dersimonian_laird", "henmi_copas"]
    if include_external:
        if _r_package_environment(("metafor",))[0]:
            methods.extend(["metafor_trimfill_external", "metafor_selmodel_external"])
        if _r_package_environment(("meta", "metasens"))[0]:
            methods.append("copas_selection_external")
        if _r_package_environment(("RoBMA",))[0]:
            methods.append("robma_bibma_external")
    return methods
