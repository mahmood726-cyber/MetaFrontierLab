from __future__ import annotations

from dataclasses import asdict, dataclass
from math import pi
from typing import Any, Callable

import numpy as np
import pandas as pd
from numpy.polynomial.hermite import hermgauss
from scipy.optimize import minimize, root_scalar
from scipy.special import expit, gammaln, logsumexp
from scipy.stats import fisher_exact, norm, t


@dataclass
class SubmodelSpec:
    name: str
    include_small_study: bool
    selection_lambda: float


@dataclass
class SubmodelFit:
    name: str
    success: bool
    message: str
    likelihood: str
    ridge_penalty: float
    objective: float
    aicc: float
    mu: float
    tau: float
    target_effect: float
    target_se: float
    small_study_slope: float
    coefficients: list[float]
    n_effective: float
    weight_summary: dict[str, float]
    uncertainty_method: str = ""


@dataclass
class FrontierMetaResult:
    estimate: float
    std_error: float
    ci_low: float
    ci_high: float
    tau: float
    likelihood: str
    submodel_weights: dict[str, float]
    submodel_table: pd.DataFrame
    settings: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["submodel_table"] = self.submodel_table.to_dict(orient="records")
        return payload


class FrontierMetaAnalyzer:
    def __init__(
        self,
        quadrature_points: int = 9,
        ridge_grid: tuple[float, ...] = (0.25,),
        submodel_specs: tuple[SubmodelSpec, ...] | None = None,
        selection_alpha: float = 0.05,
        selection_temperature: float = 0.015,
        robust_df: float = 4.0,
        transport_bandwidth: float = 1.0,
        transport_weight_mix: float = 1.0,
        design_power: float = 1.0,
        model_dispersion_scale: float = 1.0,
        simplicity_anchor: float = 0.0,
    ) -> None:
        self.quadrature_points = quadrature_points
        self.ridge_grid = ridge_grid
        self.submodel_specs = list(submodel_specs) if submodel_specs is not None else None
        self.selection_alpha = selection_alpha
        self.selection_temperature = selection_temperature
        self.robust_df = robust_df
        self.transport_bandwidth = transport_bandwidth
        self.transport_weight_mix = float(np.clip(transport_weight_mix, 0.0, 1.0))
        self.design_power = float(max(design_power, 1e-6))
        self.model_dispersion_scale = float(max(model_dispersion_scale, 0.0))
        self.simplicity_anchor = float(np.clip(simplicity_anchor, 0.0, 1.0))
        self.gh_nodes, self.gh_weights = hermgauss(quadrature_points)

    def fit(
        self,
        data: pd.DataFrame,
        effect_col: str | None = None,
        se_col: str | None = None,
        treat_events_col: str = "treat_events",
        treat_total_col: str = "treat_total",
        control_events_col: str = "control_events",
        control_total_col: str = "control_total",
        moderator_cols: list[str] | None = None,
        profile_cols: list[str] | None = None,
        target_profile: list[float] | np.ndarray | None = None,
        target_moderators: list[float] | np.ndarray | None = None,
        design_strength_col: str | None = None,
    ) -> FrontierMetaResult:
        dataset = self._prepare_dataset(
            data=data.copy(),
            effect_col=effect_col,
            se_col=se_col,
            treat_events_col=treat_events_col,
            treat_total_col=treat_total_col,
            control_events_col=control_events_col,
            control_total_col=control_total_col,
            moderator_cols=moderator_cols or [],
            profile_cols=profile_cols or [],
            target_profile=target_profile,
            target_moderators=target_moderators,
            design_strength_col=design_strength_col,
        )

        fits: list[SubmodelFit] = []
        for spec in self._submodel_specs():
            best_fit: SubmodelFit | None = None
            for ridge_penalty in self.ridge_grid:
                fit = self._fit_submodel(dataset, spec, ridge_penalty)
                if not fit.success:
                    continue
                if best_fit is None or fit.aicc < best_fit.aicc:
                    best_fit = fit
            if best_fit is not None:
                fits.append(best_fit)

        if not fits:
            raise RuntimeError("No submodel converged. Inspect the input data or reduce model complexity.")

        scores = np.array([-0.5 * fit.aicc for fit in fits], dtype=float)
        scores -= scores.max()
        weights = np.exp(scores)
        weights /= weights.sum()

        estimates = np.array([fit.target_effect for fit in fits], dtype=float)
        raw_center = float(np.dot(weights, estimates))
        interval_component_means = raw_center + np.sqrt(max(self.model_dispersion_scale, 0.0)) * (estimates - raw_center)
        taus = np.array([fit.tau for fit in fits], dtype=float)
        mix_weights, mix_means, mix_variances = self._stacked_distribution_components(fits, weights)
        pooled_estimate = float(np.dot(mix_weights, mix_means))
        pooled_variance = float(np.dot(mix_weights, mix_variances + (mix_means - pooled_estimate) ** 2))
        pooled_variance = max(pooled_variance, 1e-10)
        pooled_se = pooled_variance**0.5
        ci_low, ci_high, interval_method = self._mixture_interval(mix_weights, mix_means, mix_variances, pooled_estimate, pooled_se)

        table = pd.DataFrame(
            {
                "submodel": [fit.name for fit in fits],
                "likelihood": [fit.likelihood for fit in fits],
                "aicc": [fit.aicc for fit in fits],
                "ridge_penalty": [fit.ridge_penalty for fit in fits],
                "target_effect": [fit.target_effect for fit in fits],
                "target_se": [fit.target_se for fit in fits],
                "tau": [fit.tau for fit in fits],
                "small_study_slope": [fit.small_study_slope for fit in fits],
                "n_effective": [fit.n_effective for fit in fits],
                "uncertainty_method": [fit.uncertainty_method for fit in fits],
                "interval_component_mean": interval_component_means,
                "stack_weight": weights,
            }
        ).sort_values("stack_weight", ascending=False, ignore_index=True)

        return FrontierMetaResult(
            estimate=pooled_estimate,
            std_error=pooled_se,
            ci_low=ci_low,
            ci_high=ci_high,
            tau=float(np.dot(weights, taus)),
            likelihood=dataset["likelihood"],
            submodel_weights={fit.name: float(weight) for fit, weight in zip(fits, weights)},
            submodel_table=table,
            settings={
                "quadrature_points": self.quadrature_points,
                "ridge_grid": list(self.ridge_grid),
                "selection_alpha": self.selection_alpha,
                "selection_temperature": self.selection_temperature,
                "robust_df": self.robust_df,
                "transport_bandwidth": self.transport_bandwidth,
                "transport_weight_mix": self.transport_weight_mix,
                "design_power": self.design_power,
                "model_dispersion_scale": self.model_dispersion_scale,
                "simplicity_anchor": self.simplicity_anchor,
                "interval_method": interval_method,
                "moderator_count": int(dataset["x"].shape[1]),
                "study_count": int(dataset["k"]),
            },
        )

    def _prepare_dataset(
        self,
        data: pd.DataFrame,
        effect_col: str | None,
        se_col: str | None,
        treat_events_col: str,
        treat_total_col: str,
        control_events_col: str,
        control_total_col: str,
        moderator_cols: list[str],
        profile_cols: list[str],
        target_profile: list[float] | np.ndarray | None,
        target_moderators: list[float] | np.ndarray | None,
        design_strength_col: str | None,
    ) -> dict[str, Any]:
        uses_exact = all(col in data.columns for col in [treat_events_col, treat_total_col, control_events_col, control_total_col])
        if not uses_exact and not (effect_col and se_col):
            raise ValueError("Provide either exact binary study counts or effect-size and standard-error columns.")

        x_raw = data[moderator_cols].to_numpy(dtype=float) if moderator_cols else np.zeros((len(data), 0), dtype=float)
        x_mean = x_raw.mean(axis=0) if x_raw.size else np.zeros(0, dtype=float)
        x_scale = x_raw.std(axis=0, ddof=1) if x_raw.size and len(data) > 1 else np.ones(x_raw.shape[1], dtype=float)
        x_scale = np.where(x_scale < 1e-8, 1.0, x_scale)
        x = (x_raw - x_mean) / x_scale if x_raw.size else x_raw

        if target_moderators is None:
            x_target = np.zeros(x.shape[1], dtype=float)
        else:
            x_target_raw = np.asarray(target_moderators, dtype=float)
            if x_target_raw.shape[0] != x.shape[1]:
                raise ValueError("target_moderators must have the same length as moderator_cols.")
            x_target = (x_target_raw - x_mean) / x_scale if x_target_raw.size else x_target_raw

        profiles = data[profile_cols].to_numpy(dtype=float) if profile_cols else np.zeros((len(data), 0), dtype=float)
        if profiles.size and target_profile is None:
            target_profile_arr = profiles.mean(axis=0)
        elif profiles.size:
            target_profile_arr = np.asarray(target_profile, dtype=float)
            if target_profile_arr.shape[0] != profiles.shape[1]:
                raise ValueError("target_profile must have the same length as profile_cols.")
        else:
            target_profile_arr = np.zeros(0, dtype=float)

        transport_weights = self._compute_transport_weights(profiles, target_profile_arr)
        design_strength = (
            data[design_strength_col].to_numpy(dtype=float)
            if design_strength_col and design_strength_col in data.columns
            else np.ones(len(data), dtype=float)
        )
        design_strength = np.clip(design_strength, 0.05, 1.0) ** self.design_power

        dataset: dict[str, Any] = {
            "k": len(data),
            "x": x,
            "x_target": x_target,
            "transport_weights": transport_weights,
            "design_strength": design_strength,
            "study_ids": data.index.to_numpy(),
        }

        if uses_exact:
            a = data[treat_events_col].to_numpy(dtype=int)
            n_t = data[treat_total_col].to_numpy(dtype=int)
            c = data[control_events_col].to_numpy(dtype=int)
            n_c = data[control_total_col].to_numpy(dtype=int)
            b = n_t - a
            d = n_c - c
            if np.any(b < 0) or np.any(d < 0):
                raise ValueError("Event counts cannot exceed totals.")

            proxy = 1.0 / np.sqrt(np.maximum(n_t + n_c, 2))
            proxy_std = proxy.std(ddof=1) if len(proxy) > 1 else 1.0
            proxy = (proxy - proxy.mean()) / max(proxy_std, 1e-8)
            pvals = np.array([fisher_exact([[ai, bi], [ci, di]])[1] for ai, bi, ci, di in zip(a, b, c, d)], dtype=float)
            exact_cache = []
            for ai, ci, nti, nci in zip(a, c, n_t, n_c):
                total_events = int(ai + ci)
                lo = max(0, total_events - nci)
                hi = min(nti, total_events)
                support = np.arange(lo, hi + 1, dtype=int)
                exact_cache.append(
                    {
                        "a": int(ai),
                        "support": support,
                        "log_kernel_base": self._log_choose(nti, support) + self._log_choose(nci, total_events - support),
                        "log_obs_const": float(self._log_choose(nti, ai) + self._log_choose(nci, ci)),
                    }
                )

            dataset.update(
                {
                    "likelihood": "exact_binary",
                    "a": a,
                    "c": c,
                    "n_t": n_t,
                    "n_c": n_c,
                    "small_study_proxy": proxy,
                    "pvals": np.clip(pvals, 1e-12, 1.0),
                    "exact_cache": exact_cache,
                }
            )
        else:
            y = data[effect_col].to_numpy(dtype=float)
            se = np.clip(data[se_col].to_numpy(dtype=float), 1e-8, None)
            se_std = se.std(ddof=1) if len(se) > 1 else 1.0
            proxy = (se - se.mean()) / max(se_std, 1e-8)
            pvals = 2 * norm.sf(np.abs(y / se))
            dataset.update(
                {
                    "likelihood": "robust_continuous",
                    "y": y,
                    "se": se,
                    "small_study_proxy": proxy,
                    "pvals": np.clip(pvals, 1e-12, 1.0),
                }
            )

        return dataset

    def _submodel_specs(self) -> list[SubmodelSpec]:
        if self.submodel_specs is not None:
            return list(self.submodel_specs)
        return [
            SubmodelSpec(name="baseline", include_small_study=False, selection_lambda=0.0),
            SubmodelSpec(name="selection_mild", include_small_study=False, selection_lambda=0.75),
            SubmodelSpec(name="selection_strong_small", include_small_study=True, selection_lambda=2.0),
        ]

    def _fit_submodel(self, dataset: dict[str, Any], spec: SubmodelSpec, ridge_penalty: float) -> SubmodelFit:
        p = dataset["x"].shape[1]
        include_small = 1 if spec.include_small_study else 0
        base_weights = dataset["transport_weights"] * dataset["design_strength"]
        selection_weights = self._selection_tempering(dataset["pvals"], spec.selection_lambda)
        raw_weights = base_weights * selection_weights
        base_weight_sum = float(base_weights.sum())
        raw_weight_sum = float(raw_weights.sum())
        if raw_weight_sum <= 0 or not np.isfinite(raw_weight_sum):
            return SubmodelFit(
                name=spec.name,
                success=False,
                message="Submodel weights were invalid.",
                likelihood=dataset["likelihood"],
                ridge_penalty=float(ridge_penalty),
                objective=float("inf"),
                aicc=float("inf"),
                mu=float("nan"),
                tau=float("nan"),
                target_effect=float("nan"),
                target_se=float("nan"),
                small_study_slope=float("nan"),
                coefficients=[],
                n_effective=0.0,
                weight_summary={"min": float("nan"), "mean": float("nan"), "max": float("nan")},
            )
        weights = raw_weights * (base_weight_sum / raw_weight_sum)
        n_effective = float(weights.sum())

        start = np.zeros(2 + include_small + p, dtype=float)
        start[0] = self._initial_mu(dataset)
        start[1] = np.log(max(self._initial_tau(dataset), 0.05))

        def unpack_params(params: np.ndarray) -> tuple[float, float, float, np.ndarray, np.ndarray, int]:
            mu = params[0]
            tau = np.exp(np.clip(params[1], -8.0, 3.0))
            offset = 2
            small_slope = 0.0
            if spec.include_small_study:
                small_slope = params[offset]
                offset += 1
            beta = params[offset:]
            eta = mu + dataset["x"] @ beta
            if spec.include_small_study:
                eta = eta + small_slope * dataset["small_study_proxy"]
            return mu, tau, small_slope, beta, eta, offset

        def study_loglik(params: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float, int]:
            mu, tau, small_slope, beta, eta, offset = unpack_params(params)
            if dataset["likelihood"] == "exact_binary":
                study_ll = np.array([self._exact_study_loglik(cache, eta_i, tau) for cache, eta_i in zip(dataset["exact_cache"], eta)], dtype=float)
            else:
                scale2 = dataset["se"] ** 2 + tau**2
                z = (dataset["y"] - eta) / np.sqrt(scale2)
                study_ll = t.logpdf(z, df=self.robust_df) - 0.5 * np.log(scale2)
            return study_ll, beta, tau, small_slope, offset

        def neg_loglik(params: np.ndarray) -> float:
            study_ll, _, _, _, _ = study_loglik(params)
            return float(-(weights @ study_ll))

        def objective(params: np.ndarray) -> float:
            _, beta, _, _, _ = study_loglik(params)
            penalty = 0.5 * ridge_penalty * float(beta @ beta)
            return float(neg_loglik(params) + penalty)

        bounds = [(None, None)] * len(start)
        bounds[1] = (-8.0, 3.0)
        result = self._minimize_objective(objective, start, bounds=bounds, maxiter=80)
        if not result.success or not np.isfinite(result.fun) or not np.all(np.isfinite(result.x)):
            return SubmodelFit(
                name=spec.name,
                success=False,
                message=str(result.message),
                likelihood=dataset["likelihood"],
                ridge_penalty=float(ridge_penalty),
                objective=float(result.fun) if np.isfinite(result.fun) else float("inf"),
                aicc=float("inf"),
                mu=float("nan"),
                tau=float("nan"),
                target_effect=float("nan"),
                target_se=float("nan"),
                small_study_slope=float("nan"),
                coefficients=[],
                n_effective=n_effective,
                weight_summary={
                    "min": float(weights.min()),
                    "mean": float(weights.mean()),
                    "max": float(weights.max()),
                },
            )

        mu, tau, small_slope, beta, _, offset = unpack_params(result.x)
        target_effect = float(mu + dataset["x_target"] @ beta)
        target_se, uncertainty_method = self._estimate_target_se(
            neg_loglik,
            result.x,
            dataset["x_target"],
            spec.include_small_study,
        )
        if target_se is None:
            return SubmodelFit(
                name=spec.name,
                success=False,
                message="Target-effect uncertainty estimation failed after profile and Hessian fallbacks.",
                likelihood=dataset["likelihood"],
                ridge_penalty=float(ridge_penalty),
                objective=float(result.fun),
                aicc=float("inf"),
                mu=mu,
                tau=tau,
                target_effect=target_effect,
                target_se=float("nan"),
                small_study_slope=small_slope,
                coefficients=[float(x) for x in beta],
                n_effective=n_effective,
                weight_summary={
                    "min": float(weights.min()),
                    "mean": float(weights.mean()),
                    "max": float(weights.max()),
                },
            )
        param_count = len(result.x)
        denom = max(n_effective - param_count - 1.0, 1.0)
        unpenalized_nll = neg_loglik(result.x)
        aicc = float(2.0 * unpenalized_nll + 2.0 * param_count + (2.0 * param_count * (param_count + 1.0)) / denom)

        return SubmodelFit(
            name=spec.name,
            success=True,
            message=str(result.message),
            likelihood=dataset["likelihood"],
            ridge_penalty=float(ridge_penalty),
            objective=float(result.fun),
            aicc=aicc,
            mu=mu,
            tau=tau,
            target_effect=target_effect,
            target_se=target_se,
            small_study_slope=small_slope,
            coefficients=[float(x) for x in beta],
            n_effective=n_effective,
            weight_summary={
                "min": float(weights.min()),
                "mean": float(weights.mean()),
                "max": float(weights.max()),
            },
            uncertainty_method=uncertainty_method,
        )

    def _selection_tempering(self, pvals: np.ndarray, selection_lambda: float) -> np.ndarray:
        if selection_lambda <= 0:
            return np.ones_like(pvals)
        significance_score = expit((self.selection_alpha - pvals) / self.selection_temperature)
        return 1.0 / (1.0 + selection_lambda * significance_score)

    def _compute_transport_weights(self, profiles: np.ndarray, target_profile: np.ndarray) -> np.ndarray:
        if profiles.size == 0:
            return np.ones(profiles.shape[0], dtype=float)
        scale = profiles.std(axis=0, ddof=1) if profiles.shape[0] > 1 else np.ones(profiles.shape[1], dtype=float)
        scale = np.where(scale < 1e-8, 1.0, scale)
        z = (profiles - target_profile) / scale
        sqdist = np.sum(z**2, axis=1)
        weights = np.exp(-0.5 * sqdist / max(self.transport_bandwidth**2, 1e-8))
        weights = (1.0 - self.transport_weight_mix) + self.transport_weight_mix * weights
        return np.clip(weights, 1e-4, None)

    def _initial_mu(self, dataset: dict[str, Any]) -> float:
        if dataset["likelihood"] == "exact_binary":
            a = dataset["a"] + 0.5
            b = dataset["n_t"] - dataset["a"] + 0.5
            c = dataset["c"] + 0.5
            d = dataset["n_c"] - dataset["c"] + 0.5
            y = np.log((a * d) / (b * c))
            v = 1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d
            return float(np.sum(y / v) / np.sum(1.0 / v))
        weights = 1.0 / (dataset["se"] ** 2)
        return float(np.sum(dataset["y"] * weights) / np.sum(weights))

    def _initial_tau(self, dataset: dict[str, Any]) -> float:
        if dataset["likelihood"] == "exact_binary":
            a = dataset["a"] + 0.5
            b = dataset["n_t"] - dataset["a"] + 0.5
            c = dataset["c"] + 0.5
            d = dataset["n_c"] - dataset["c"] + 0.5
            y = np.log((a * d) / (b * c))
            v = 1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d
        else:
            y = dataset["y"]
            v = dataset["se"] ** 2
        w = 1.0 / v
        mu = np.sum(w * y) / np.sum(w)
        q = np.sum(w * (y - mu) ** 2)
        c_term = np.sum(w) - np.sum(w**2) / np.sum(w)
        tau2 = max((q - (len(y) - 1)) / max(c_term, 1e-8), 1e-6)
        return float(np.sqrt(tau2))

    def _exact_study_loglik(self, cache: dict[str, Any], eta: float, tau: float) -> float:
        support = cache["support"]
        log_kernel_base = cache["log_kernel_base"]
        if tau < 1e-8:
            log_norm = logsumexp(log_kernel_base + eta * support)
            return float(cache["log_obs_const"] + eta * cache["a"] - log_norm)

        theta = eta + np.sqrt(2.0) * tau * self.gh_nodes
        study_terms = []
        for point, weight in zip(theta, self.gh_weights):
            log_norm = logsumexp(log_kernel_base + point * support)
            cond_ll = cache["log_obs_const"] + point * cache["a"] - log_norm
            study_terms.append(np.log(weight) + cond_ll)
        return float(logsumexp(study_terms) - 0.5 * np.log(pi))

    def _log_choose(self, n: int | np.ndarray, k: int | np.ndarray) -> np.ndarray:
        n_arr = np.asarray(n)
        k_arr = np.asarray(k)
        return gammaln(n_arr + 1.0) - gammaln(k_arr + 1.0) - gammaln(n_arr - k_arr + 1.0)

    def _stacked_distribution_components(
        self,
        fits: list[SubmodelFit],
        weights: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        estimates = np.array([fit.target_effect for fit in fits], dtype=float)
        variances = np.array([fit.target_se**2 for fit in fits], dtype=float)
        raw_center = float(np.dot(weights, estimates))
        spread_scale = float(np.sqrt(max(self.model_dispersion_scale, 0.0)))
        adjusted_means = raw_center + spread_scale * (estimates - raw_center)

        component_weights = weights.copy()
        component_means = adjusted_means
        component_variances = variances.copy()

        if self.simplicity_anchor > 0:
            baseline_fit = next((fit for fit in fits if fit.name == "baseline"), fits[0])
            anchor = self.simplicity_anchor
            component_weights = np.concatenate([(1.0 - anchor) * component_weights, [anchor]])
            component_means = np.concatenate([component_means, [baseline_fit.target_effect]])
            component_variances = np.concatenate([component_variances, [baseline_fit.target_se**2]])

        component_weights = component_weights / component_weights.sum()
        return component_weights, component_means, component_variances

    def _mixture_cdf(self, x: float, weights: np.ndarray, means: np.ndarray, variances: np.ndarray) -> float:
        std = np.sqrt(np.clip(variances, 1e-10, None))
        z = (x - means) / std
        return float(np.dot(weights, norm.cdf(z)))

    def _mixture_quantile(
        self,
        q: float,
        weights: np.ndarray,
        means: np.ndarray,
        variances: np.ndarray,
    ) -> float | None:
        std = np.sqrt(np.clip(variances, 1e-10, None))
        lower = float(np.min(means - 8.0 * std))
        upper = float(np.max(means + 8.0 * std))

        lower_cdf = self._mixture_cdf(lower, weights, means, variances)
        upper_cdf = self._mixture_cdf(upper, weights, means, variances)
        expansions = 0
        width = max(upper - lower, 1.0)
        while (lower_cdf > q or upper_cdf < q) and expansions < 12:
            width *= 2.0
            lower = float(np.min(means) - width)
            upper = float(np.max(means) + width)
            lower_cdf = self._mixture_cdf(lower, weights, means, variances)
            upper_cdf = self._mixture_cdf(upper, weights, means, variances)
            expansions += 1
        if lower_cdf > q or upper_cdf < q:
            return None

        def root_equation(x: float) -> float:
            return self._mixture_cdf(x, weights, means, variances) - q

        try:
            result = root_scalar(root_equation, bracket=[lower, upper], method="brentq", xtol=1e-6, rtol=1e-8, maxiter=200)
        except ValueError:
            return None
        return float(result.root) if result.converged and np.isfinite(result.root) else None

    def _mixture_interval(
        self,
        weights: np.ndarray,
        means: np.ndarray,
        variances: np.ndarray,
        fallback_mean: float,
        fallback_se: float,
        alpha: float = 0.05,
    ) -> tuple[float, float, str]:
        lower = self._mixture_quantile(alpha / 2.0, weights, means, variances)
        upper = self._mixture_quantile(1.0 - alpha / 2.0, weights, means, variances)
        if lower is not None and upper is not None and lower <= upper:
            return lower, upper, "stacked_normal_mixture"
        return fallback_mean - 1.96 * fallback_se, fallback_mean + 1.96 * fallback_se, "wald_fallback"

    def _minimize_objective(
        self,
        objective_fn: Callable[[np.ndarray], float],
        start: np.ndarray,
        *,
        bounds: list[tuple[float | None, float | None]] | None = None,
        maxiter: int = 80,
    ):
        result = minimize(objective_fn, start, method="L-BFGS-B", bounds=bounds, options={"maxiter": maxiter, "ftol": 1e-6})
        if result.success and np.isfinite(result.fun) and np.all(np.isfinite(result.x)):
            return result
        fallback = minimize(objective_fn, start, method="Powell", bounds=bounds, options={"maxiter": maxiter * 8, "xtol": 1e-4, "ftol": 1e-4})
        return fallback if fallback.success and np.isfinite(fallback.fun) and np.all(np.isfinite(fallback.x)) else result

    def _target_gradient(self, x_target: np.ndarray, include_small: bool) -> np.ndarray:
        gradient = np.zeros(2 + int(include_small) + len(x_target), dtype=float)
        gradient[0] = 1.0
        if len(x_target):
            gradient[2 + int(include_small) :] = x_target
        return gradient

    def _nuisance_from_params(self, params: np.ndarray, include_small: bool) -> np.ndarray:
        offset = 2 + int(include_small)
        pieces = [params[1]]
        if include_small:
            pieces.append(params[2])
        if len(params) > offset:
            pieces.extend(params[offset:])
        return np.asarray(pieces, dtype=float)

    def _params_from_target_effect(
        self,
        target_effect: float,
        nuisance: np.ndarray,
        x_target: np.ndarray,
        include_small: bool,
    ) -> np.ndarray:
        nuisance = np.asarray(nuisance, dtype=float)
        p = len(x_target)
        expected = 1 + int(include_small) + p
        if len(nuisance) != expected:
            raise ValueError("Nuisance parameter vector has the wrong length.")
        params = np.zeros(2 + int(include_small) + p, dtype=float)
        params[1] = nuisance[0]
        cursor = 1
        if include_small:
            params[2] = nuisance[cursor]
            cursor += 1
        beta = nuisance[cursor:]
        params[2 + int(include_small) :] = beta
        params[0] = float(target_effect - x_target @ beta)
        return params

    def _profile_target_neg_loglik(
        self,
        objective_fn: Callable[[np.ndarray], float],
        target_effect: float,
        nuisance_start: np.ndarray,
        x_target: np.ndarray,
        include_small: bool,
    ) -> tuple[float, np.ndarray] | None:
        bounds = [(-8.0, 3.0)] + [(None, None)] * (len(nuisance_start) - 1)

        def profiled_objective(nuisance: np.ndarray) -> float:
            params = self._params_from_target_effect(target_effect, nuisance, x_target, include_small)
            return float(objective_fn(params))

        result = self._minimize_objective(profiled_objective, nuisance_start, bounds=bounds, maxiter=60)
        if not result.success or not np.isfinite(result.fun) or not np.all(np.isfinite(result.x)):
            return None
        return float(result.fun), np.asarray(result.x, dtype=float)

    def _profile_target_se(
        self,
        objective_fn: Callable[[np.ndarray], float],
        params: np.ndarray,
        x_target: np.ndarray,
        include_small: bool,
    ) -> float | None:
        target_gradient = self._target_gradient(x_target, include_small)
        target_effect = float(target_gradient @ params)
        nuisance_start = self._nuisance_from_params(params, include_small)
        centered = self._profile_target_neg_loglik(objective_fn, target_effect, nuisance_start, x_target, include_small)
        if centered is None:
            return None
        f0, center_nuisance = centered
        scale = max(1.0, abs(target_effect))
        for relative_step in (0.01, 0.025, 0.05):
            step = relative_step * scale
            upper = self._profile_target_neg_loglik(objective_fn, target_effect + step, center_nuisance, x_target, include_small)
            lower = self._profile_target_neg_loglik(objective_fn, target_effect - step, center_nuisance, x_target, include_small)
            if upper is None or lower is None:
                continue
            curvature = (upper[0] - 2.0 * f0 + lower[0]) / (step**2)
            if np.isfinite(curvature) and curvature > 1e-8:
                return float(np.sqrt(1.0 / curvature))
        return None

    def _directional_target_se(
        self,
        objective_fn: Callable[[np.ndarray], float],
        params: np.ndarray,
        x_target: np.ndarray,
        include_small: bool,
    ) -> float | None:
        target_gradient = self._target_gradient(x_target, include_small)
        norm_sq = float(target_gradient @ target_gradient)
        if not np.isfinite(norm_sq) or norm_sq <= 1e-12:
            return None
        direction = target_gradient / norm_sq
        target_effect = float(target_gradient @ params)
        f0 = float(objective_fn(params))
        scale = max(1.0, abs(target_effect))
        for relative_step in (0.005, 0.01, 0.025):
            step = relative_step * scale
            fp = objective_fn(params + step * direction)
            fm = objective_fn(params - step * direction)
            if not np.isfinite(fp) or not np.isfinite(fm):
                continue
            curvature = (fp - 2.0 * f0 + fm) / (step**2)
            if np.isfinite(curvature) and curvature > 1e-8:
                return float(np.sqrt(1.0 / curvature))
        return None

    def _estimate_target_se(
        self,
        objective_fn: Callable[[np.ndarray], float],
        params: np.ndarray,
        x_target: np.ndarray,
        include_small: bool,
    ) -> tuple[float | None, str]:
        profile_se = self._profile_target_se(objective_fn, params, x_target, include_small)
        if profile_se is not None:
            return profile_se, "profile_curvature"

        cov = self._extract_covariance(objective_fn, params)
        if cov is not None:
            target_gradient = self._target_gradient(x_target, include_small)
            variance = float(target_gradient @ cov @ target_gradient)
            if np.isfinite(variance) and variance > 1e-10:
                return float(np.sqrt(variance)), "regularized_hessian"

        directional_se = self._directional_target_se(objective_fn, params, x_target, include_small)
        if directional_se is not None:
            return directional_se, "directional_curvature"
        return None, ""

    def _extract_covariance(self, objective_fn: Callable[[np.ndarray], float], params: np.ndarray) -> np.ndarray | None:
        hessian = self._approx_hessian(objective_fn, params)
        if hessian is None:
            return None
        try:
            eigenvalues, eigenvectors = np.linalg.eigh(hessian)
        except np.linalg.LinAlgError:
            return None
        if not np.all(np.isfinite(eigenvalues)) or np.any(eigenvalues < -1e-5):
            return None
        regularized = np.clip(eigenvalues, 1e-6, None)
        inv_eigenvalues = np.diag(1.0 / regularized)
        cov = eigenvectors @ inv_eigenvalues @ eigenvectors.T
        if not np.all(np.isfinite(cov)):
            return None
        return cov

    def _approx_hessian(self, objective_fn: Callable[[np.ndarray], float], params: np.ndarray) -> np.ndarray | None:
        params = np.asarray(params, dtype=float)
        n_params = len(params)
        steps = 1e-4 * np.maximum(1.0, np.abs(params))
        f0 = objective_fn(params)
        if not np.isfinite(f0):
            return None

        hessian = np.zeros((n_params, n_params), dtype=float)
        for i in range(n_params):
            hi = steps[i]
            xp = params.copy()
            xm = params.copy()
            xp[i] += hi
            xm[i] -= hi
            fp = objective_fn(xp)
            fm = objective_fn(xm)
            if not np.isfinite(fp) or not np.isfinite(fm):
                return None
            hessian[i, i] = (fp - 2.0 * f0 + fm) / (hi**2)
            for j in range(i + 1, n_params):
                hj = steps[j]
                xpp = params.copy()
                xpm = params.copy()
                xmp = params.copy()
                xmm = params.copy()
                xpp[i] += hi
                xpp[j] += hj
                xpm[i] += hi
                xpm[j] -= hj
                xmp[i] -= hi
                xmp[j] += hj
                xmm[i] -= hi
                xmm[j] -= hj
                fpp = objective_fn(xpp)
                fpm = objective_fn(xpm)
                fmp = objective_fn(xmp)
                fmm = objective_fn(xmm)
                if not all(np.isfinite(value) for value in [fpp, fpm, fmp, fmm]):
                    return None
                hessian_ij = (fpp - fpm - fmp + fmm) / (4.0 * hi * hj)
                hessian[i, j] = hessian_ij
                hessian[j, i] = hessian_ij

        if not np.all(np.isfinite(hessian)):
            return None
        return hessian


def make_tbema_analyzer() -> FrontierMetaAnalyzer:
    return FrontierMetaAnalyzer(
        quadrature_points=5,
        ridge_grid=(0.5, 1.0),
        submodel_specs=(
            SubmodelSpec(name="baseline", include_small_study=False, selection_lambda=0.0),
            SubmodelSpec(name="selection_soft", include_small_study=False, selection_lambda=0.20),
            SubmodelSpec(name="selection_soft_small", include_small_study=True, selection_lambda=0.50),
        ),
        transport_bandwidth=1.8,
        transport_weight_mix=0.55,
        design_power=0.6,
        model_dispersion_scale=0.10,
        simplicity_anchor=0.0,
    )
