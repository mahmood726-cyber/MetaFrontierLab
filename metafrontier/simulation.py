from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass
class SimulationConfig:
    seed: int = 20260401
    studies: int = 32
    moderator_count: int = 4
    target_effect: float = -0.35
    heterogeneity: float = 0.28
    rare_event_logit: float = -3.7
    publication_strength: float = 1.35
    observational_fraction: float = 0.4
    observational_design_strength: float = 0.55
    observational_bias_intercept: float = 0.18
    observational_bias_slope: float = 0.12
    target_profile: tuple[float, float] = (0.0, 0.0)
    study_profile_shift: tuple[float, float] = (0.0, 0.0)
    selection_floor: float = 0.18
    selection_ceiling: float = 0.92
    min_observed_studies: int = 12


def moderator_columns(count: int) -> list[str]:
    return [f"moderator_{i + 1}" for i in range(count)]


def profile_columns() -> list[str]:
    return ["profile_1", "profile_2"]


def target_moderators_for_config(config: SimulationConfig) -> np.ndarray:
    target = np.zeros(config.moderator_count, dtype=float)
    target_profile = np.asarray(config.target_profile, dtype=float)
    if config.moderator_count >= 1:
        target[0] = target_profile[0]
    if config.moderator_count >= 2:
        target[1] = target_profile[1]
    return target


def simulate_publication_biased_binary_meta(config: SimulationConfig) -> tuple[pd.DataFrame, dict[str, float]]:
    rng = np.random.default_rng(config.seed)
    k = config.studies
    p = config.moderator_count

    profile_shift = np.asarray(config.study_profile_shift, dtype=float)
    target_profile = np.asarray(config.target_profile, dtype=float)
    profiles = rng.normal(size=(k, 2)) + profile_shift

    moderators = np.column_stack(
        [
            profiles[:, 0] + 0.25 * rng.normal(size=k),
            profiles[:, 1] + 0.25 * rng.normal(size=k),
            rng.normal(size=k),
            rng.normal(size=k),
        ]
    )[:, :p]
    beta_true = np.array([0.22, -0.16, 0.09, -0.05], dtype=float)[:p]
    target_moderators = target_moderators_for_config(config)[:p]

    is_observational = rng.binomial(1, config.observational_fraction, size=k)
    design_strength = np.where(is_observational == 1, config.observational_design_strength, 1.0)

    treat_total = rng.integers(40, 240, size=k)
    control_total = rng.integers(40, 240, size=k)
    baseline_logit = config.rare_event_logit + 0.55 * profiles[:, 0] - 0.35 * profiles[:, 1]

    heterogeneity = rng.standard_t(df=4, size=k) * (config.heterogeneity / np.sqrt(2.0))
    observational_bias = is_observational * (config.observational_bias_intercept + config.observational_bias_slope * profiles[:, 0])
    theta_true = config.target_effect + moderators @ beta_true + heterogeneity + observational_bias
    true_target_effect = config.target_effect + float(target_moderators @ beta_true)

    p_control = 1.0 / (1.0 + np.exp(-baseline_logit))
    p_treat = 1.0 / (1.0 + np.exp(-(baseline_logit + theta_true)))

    control_events = rng.binomial(control_total, np.clip(p_control, 1e-5, 1 - 1e-5))
    treat_events = rng.binomial(treat_total, np.clip(p_treat, 1e-5, 1 - 1e-5))

    a = treat_events + 0.5
    b = treat_total - treat_events + 0.5
    c = control_events + 0.5
    d = control_total - control_events + 0.5
    y = np.log((a * d) / (b * c))
    se = np.sqrt(1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d)
    z = y / se
    pval = 2.0 * norm.sf(np.abs(z))

    relevance = np.exp(-0.5 * np.sum((profiles - target_profile) ** 2, axis=1))
    selection_logit = -0.25 + 0.65 * config.publication_strength * (0.05 - pval) / 0.02 + 0.45 * relevance + 0.25 * (1 - is_observational)
    selection_prob = 1.0 / (1.0 + np.exp(-selection_logit))
    selected = rng.binomial(1, np.clip(selection_prob, config.selection_floor, config.selection_ceiling), size=k).astype(bool)
    min_required = min(k, max(config.min_observed_studies, p + 6))
    if selected.sum() < min_required:
        top = np.argsort(selection_prob)[-min_required:]
        selected[top] = True

    observed = pd.DataFrame(
        {
            "study": [f"study_{i+1:02d}" for i in range(k)],
            "treat_events": treat_events,
            "treat_total": treat_total,
            "control_events": control_events,
            "control_total": control_total,
            "profile_1": profiles[:, 0],
            "profile_2": profiles[:, 1],
            "moderator_1": moderators[:, 0] if p >= 1 else 0.0,
            "moderator_2": moderators[:, 1] if p >= 2 else 0.0,
            "moderator_3": moderators[:, 2] if p >= 3 else 0.0,
            "moderator_4": moderators[:, 3] if p >= 4 else 0.0,
            "design_strength": design_strength,
            "is_observational": is_observational,
            "selected": selected,
            "theta_true": theta_true,
        }
    )
    observed = observed.loc[observed["selected"]].reset_index(drop=True)

    truth = {
        "true_target_effect": float(true_target_effect),
        "target_profile_1": float(target_profile[0]),
        "target_profile_2": float(target_profile[1]),
        "target_moderators": target_moderators.tolist(),
        "study_profile_shift_1": float(profile_shift[0]),
        "study_profile_shift_2": float(profile_shift[1]),
        "full_study_count": int(k),
        "observed_study_count": int(len(observed)),
    }
    return observed, truth


def naive_random_effects_log_or(data: pd.DataFrame) -> dict[str, float]:
    a = data["treat_events"].to_numpy(dtype=float) + 0.5
    b = data["treat_total"].to_numpy(dtype=float) - data["treat_events"].to_numpy(dtype=float) + 0.5
    c = data["control_events"].to_numpy(dtype=float) + 0.5
    d = data["control_total"].to_numpy(dtype=float) - data["control_events"].to_numpy(dtype=float) + 0.5

    y = np.log((a * d) / (b * c))
    v = 1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d
    w = 1.0 / v
    mu_fixed = np.sum(w * y) / np.sum(w)
    q = np.sum(w * (y - mu_fixed) ** 2)
    c_term = np.sum(w) - np.sum(w**2) / np.sum(w)
    tau2 = max((q - (len(y) - 1)) / max(c_term, 1e-8), 0.0)
    w_re = 1.0 / (v + tau2)
    mu = np.sum(w_re * y) / np.sum(w_re)
    se = np.sqrt(1.0 / np.sum(w_re))
    return {
        "estimate": float(mu),
        "std_error": float(se),
        "ci_low": float(mu - 1.96 * se),
        "ci_high": float(mu + 1.96 * se),
        "tau": float(np.sqrt(tau2)),
    }
