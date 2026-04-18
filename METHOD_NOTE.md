# Frontier Methods Note

This note names the new methods implemented or proposed in this directory and makes clear which parts are published, which parts are extensions, and which parts still need formal validation.

## 1. TBEMA

**Transport-Bias Exact Meta-Analysis**

For study `i`, let:

- `a_i` = treatment events
- `c_i` = control events
- `n1_i`, `n0_i` = treatment and control totals
- `x_i` = study moderators
- `r_i` = transport relevance weight
- `d_i` = design-strength weight
- `s_i` = small-study proxy

The latent study effect is modeled as:

`theta_i ~ N(mu + x_i' beta + gamma s_i, tau^2)`

For sparse binary outcomes, the within-study likelihood is the conditional exact likelihood:

`P(A_i = a_i | A_i + C_i = m_i, theta_i)`

which removes the nuisance baseline risk through conditioning on the total event count.

The overall pseudo-objective is:

`sum_i w_i log L_i - (lambda / 2) ||beta||^2`

where:

- `L_i` is the exact study likelihood integrated over the random-effects distribution
- `w_i = r_i * d_i * q_i`
- `q_i` is a selection-tempering weight

## 2. SET-Stack

**Selective Evidence Tempering with Stacking**

Recent robust Bayesian work shows that publication-bias correction should not be reduced to a single chosen method.

This prototype pushes that further by fitting a stack of submodels:

- no selection tempering
- mild selection tempering
- strong selection tempering with small-study adjustment

Each submodel gets an information-criterion weight, producing a pooled estimate that is more pessimistic about bias than a single-model workflow.

The new ingredient here is the smooth p-value response:

`q_i = 1 / (1 + lambda_sel * logistic((alpha - p_i) / temp))`

This is intentionally a robust pseudo-likelihood device rather than a claim of a fully identified publication process.

## 3. TAME-R

**Target-Aware Meta-Regression with Ridge Shrinkage**

Classical meta-regression is fragile when the number of moderators grows while the number of studies stays small.

TAME-R uses shrinkage so the target effect estimate is:

`mu_target = mu + x_target' beta`

with `beta` regularized by a ridge penalty. That allows the pooled estimate to adapt to moderators without the usual explosion in variance.

## Why This Goes Beyond the Source Papers

The source papers treat these ingredients mostly separately:

- sparse exact likelihood
- publication-bias model averaging
- transportability
- power-likelihood borrowing
- sparse meta-regression

This directory combines them into one operational framework with one API and one simulation harness.

## What Still Needs To Be Done

Before claiming this as a publishable new estimator, it needs:

1. large simulation benchmarking against RoBMA, standard random-effects models, Copas-style models, and exact sparse-data baselines
2. sensitivity analysis for the transport kernel and selection-tempering curve
3. theoretical work on consistency and coverage under pseudo-likelihood weighting
4. extension to multivariate and network meta-analysis

## Benchmark Harness Added Here

This repository now includes a benchmark harness that compares:

1. TBEMA
2. an exact sparse-data baseline
3. DerSimonian-Laird
4. Henmi-Copas
5. optional external `metafor::trimfill()`
6. optional external `metafor::selmodel()`
7. optional external Copas selection via `metasens`
8. optional external `RoBMA::BiBMA()` when an R stack is available

The benchmarked TBEMA path now uses the same canonical preset exposed by `make_tbema_analyzer()`, and the external R adapters are enabled per method based on the packages available in the detected R installation.
