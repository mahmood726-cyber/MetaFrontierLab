# Truth-Recovery Report — MetaFrontierLab

**Date:** 2026-06-15
**Repo:** mahmood726-cyber/MetaFrontierLab — "Prototype Meta-Analysis Framework for Frontier Methods"
**Scope:** Additive validation only. No files under `metafrontier/` were modified.

## Verdict: GENUINE METHODS ENGINE — VALIDATED, with an honest negative finding

MetaFrontierLab is **not** a stub or marketing shell. `metafrontier/core.py` (844 lines)
implements a real, novel estimator: **TBEMA (Transport-Bias Exact Meta-Analysis)** plus a
SET-Stack model-averaging layer. The estimator:

- Fits multiple submodels (baseline / soft-selection / selection-with-small-study) and
  combines them by AICc stacking weights into a mixture distribution.
- Uses a robust (Student-t, df=4) random-effects within-study likelihood on the generic
  effect/SE path (`likelihood = "robust_continuous"`), and an exact conditional binomial
  likelihood with Gauss-Hermite quadrature on the binary-counts path.
- Adds transport-relevance weights, design-strength weights, and selection-tempering.

It accepts generic `effect_col` / `se_col` inverse-variance data, so a known Gaussian
random-effects DGP can be injected directly. This is what we did.

## Method

- **DGP:** single-sourced from `../../_kit/dgp.mjs` (seeded, reproducible). True
  `mu = 0.4`, `tau2 = 0.04` (tau = 0.2), `k = 15` published studies, SE ~ U(0.1, 0.5).
- **Selection scenarios:** `none`; `step_strong` (one-sided p-value step weights
  [1.0, 0.35, 0.10]); `copas_strong` (Copas selection, rho = 0.90).
- **Estimators compared on identical data:**
  - **FM** = the repo's own `make_tbema_analyzer()` (TBEMA + SET-Stack).
  - **DL** = DerSimonian-Laird random-effects + Wald CI (reference baseline, local).
- **Metric:** coverage of the TRUE mu by the 95% interval; mean point-estimate bias;
  mean interval width. 150 replications per scenario.

## Results (150 reps, k = 15, mu = 0.4, tau2 = 0.04)

| scenario     | naive bias | DL cover | DL bias | DL width | FM cover | FM bias | FM width |
|--------------|-----------:|---------:|--------:|---------:|---------:|--------:|---------:|
| none         |      0.010 |    0.893 |   0.006 |    0.312 |    0.887 |  -0.010 |    0.331 |
| step_strong  |      0.205 |    0.320 |   0.142 |    0.239 |    0.327 |   0.158 |    0.259 |
| copas_strong |      0.172 |    0.633 |   0.106 |    0.277 |    0.660 |   0.112 |    0.299 |

(Full machine-readable output: `truth-recovery/results.json`.)

## Findings

1. **No selection — both estimators are well-calibrated.** TBEMA covers true mu 88.7%
   of the time with near-zero bias (-0.010); DL covers 89.3%. Both are slightly below
   nominal 95%, expected at k = 15 with Wald/mixture intervals. **TBEMA does not break the
   honest baseline** — a necessary sanity result.

2. **Under publication selection, TBEMA does NOT recover the truth.** Despite being named
   and documented as a *bias-correcting* / selection-aware method:
   - `step_strong`: coverage **0.327** (vs DL 0.320), bias **+0.158** (vs DL +0.142) —
     TBEMA is *marginally worse* than the naive DL baseline on both metrics here.
   - `copas_strong`: coverage **0.660** (vs DL 0.633), bias +0.112 — a tiny improvement,
     still far below nominal.
   TBEMA's selection-tempering submodels move the estimate only slightly off the naive
   pooled value; under strong step-function publication bias it remains badly biased high
   and badly under-covers.

3. **Intervals are slightly wider than DL but not wide enough.** TBEMA's mixture interval
   is ~5-10% wider than DL across scenarios, yet under selection the extra width does not
   compensate for the residual bias, so coverage stays low.

## Recommendation

- **Keep and cite the engine as a genuine prototype** — the estimator is real, runs, and is
  well-calibrated under no selection. It is correctly labelled "Prototype."
- **Do NOT claim TBEMA corrects publication/selection bias** in README or paper copy without
  this caveat: as configured by `make_tbema_analyzer()`, it tracks the naive DL baseline and
  does not restore coverage under strong step or Copas selection (33% and 66% vs nominal 95%).
- Maintainer next step: selection-tempering appears too weak (selection_lambda 0.2-0.5,
  temperature 0.015). A grounded selection-model term with real leverage would be needed
  before any bias-correction claim is defensible. Methods-improvement TODO, not a bug.

## Reproduce

```
node truth-recovery/gen_datasets.mjs step_strong 150 15 0.4 0.04
python truth-recovery/harness.py none,step_strong,copas_strong 150
python -m pytest truth-recovery/test_truth_recovery.py -q
```
