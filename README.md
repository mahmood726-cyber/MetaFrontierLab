# MetaFrontierLab

[![ci](https://github.com/mahmood726-cyber/MetaFrontierLab/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mahmood726-cyber/MetaFrontierLab/actions/workflows/ci.yml) [![codeql](https://github.com/mahmood726-cyber/MetaFrontierLab/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mahmood726-cyber/MetaFrontierLab/actions/workflows/codeql.yml) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

MetaFrontierLab is a prototype meta-analysis framework for rapid frontier-method development.

It does not pretend to be a validated statistical breakthrough. It is a research-grade implementation that takes several strong recent developments in meta-analysis and pushes them into one combined workflow:

- exact sparse-data likelihoods for binary outcomes
- model ensembling for publication-bias adjustment
- transport-to-target weighting for target-population inference
- power-style discounting of lower-trust evidence
- shrinkage meta-regression for many moderators

The main implemented method is called **TBEMA**:

**Transport-Bias Exact Meta-Analysis**

TBEMA combines four ideas in one estimator:

1. For sparse binary studies, it uses an exact conditional likelihood rather than relying only on asymptotic normal log-odds approximations.
2. It fits multiple bias-adjusted submodels instead of betting everything on one publication-bias correction.
3. It targets a user-defined population through relevance weights, so the estimand can move away from the average study population.
4. It discounts lower-credibility evidence through fractional likelihood weights, inspired by recent power-likelihood work.

## Implemented Components

### 1. Exact sparse-data random-effects layer

For binary treatment-control studies, the code uses a conditional exact likelihood built from the 2x2 table margins and integrates over a random-effects distribution with Gauss-Hermite quadrature.

That choice is motivated by recent work showing that sparse meta-analysis can break standard normal-normal random-effects approximations.

### 2. Selection-tempered evidence weighting

Instead of a single publication-bias correction, TBEMA fits an ensemble:

- baseline
- small-study adjusted
- mildly selection-tempered
- strongly selection-tempered

The selection tempering is a new extension in this prototype: studies with highly significant results are smoothly downweighted according to a tunable significance-response curve, then the resulting submodels are stacked with information-criterion weights.

This is not identical to a classical Copas or full selection-model likelihood. It is a deliberately robust pseudo-likelihood extension intended as a frontier prototype.

### 3. Transport-to-target estimation

If study-level population descriptors and a target profile are supplied, TBEMA applies Gaussian-kernel relevance weights so the pooled effect is explicitly targeted to the chosen population.

This pushes meta-analysis away from “what is the average study effect?” toward “what is the best estimate for the population I actually care about?”

### 4. Power-style design discounting

Each study can be assigned a `design_strength` between `0` and `1`.

- `1.0` means full trust
- values below `1.0` discount the study through a fractional-likelihood contribution

This is useful when combining randomized and observational evidence, or when some studies are much less credible than others.

### 5. Moderator shrinkage

Moderator effects are estimated with ridge regularization so the method remains usable when there are many candidate moderators and not many studies.

## What Is New Here

The prototype goes beyond any one cited paper by combining:

- exact sparse-data meta-analysis
- publication-bias model ensembling
- target-population transportability
- power-likelihood discounting
- moderator shrinkage

in one objective function and one result object.

In practical terms, the project is trying to answer:

> What if a meta-analysis had to be sparse-data aware, publication-bias pessimistic, target-population specific, and willing to partially borrow from lower-trust studies at the same time?

That joint problem is the frontier this prototype is aiming at.

## Source Trail

The design draws directly from these recent primary sources:

- Bartoš et al. (2023), *Research Synthesis Methods*: RoBMA model-averages complementary publication-bias adjustments rather than choosing one method.  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10087723/
- Hu et al. (2024), *Biometrics*: extends exact-likelihood sparse-data meta-analysis to publication-bias sensitivity analysis.  
  https://academic.oup.com/biometrics/article/80/3/ujae092/7754376
- Lin, Tarp, and Evans (2025), *Biometrics*: uses a power likelihood to borrow observational information while controlling how much it contributes.  
  https://academic.oup.com/biometrics/article/81/1/ujaf008/8016472
- Dahabreh et al. (2022), *Clinical Trials*: transport treatment-effect estimates from multiple trials to a defined target population.  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC9066547/
- Gronsbell et al. (2025), *Stats*: exact inference for random-effects meta-analysis with small, sparse data.  
  https://www.mdpi.com/2571-905X/8/1/5
- Rose (2024), *Stata Journal*: sparse multivariate meta-analysis becomes tractable via penalized low-dimensional structure.  
  https://ageconsearch.umn.edu/record/361294

## Files

- `metafrontier/core.py`: main estimator
- `metafrontier/simulation.py`: data generator and naive comparator
- `metafrontier/benchmark_methods.py`: benchmark comparators and method adapters
- `metafrontier/benchmarking.py`: scenario engine and summary aggregation
- `metafrontier/reporting.py`: plot and report generation
- `run_demo.py`: end-to-end simulation and example run
- `run_benchmarks.py`: multi-scenario benchmark runner
- `generate_benchmark_report.py`: report generation from existing benchmark outputs
- `generate_benchmark_pdf.py`: polished PDF export from benchmark outputs
- `results/`: generated outputs

## Run

```bash
python run_demo.py
```

To run the benchmark suite:

```bash
python run_benchmarks.py --replications 4
```

To generate the report from benchmark outputs:

```bash
python generate_benchmark_report.py --benchmark-dir results/benchmarks
```

Or in one step:

```bash
python run_benchmarks.py --replications 4 --report
```

To create a PDF report from an existing benchmark directory:

```bash
python generate_benchmark_pdf.py --benchmark-dir results/benchmarks_scaled_full
```

## Output

The demo writes:

- `results/demo_summary.json`
- `results/observed_studies.csv`
- `results/submodel_table.csv`

The benchmark runner writes:

- `results/benchmarks/benchmark_runs.csv`
- `results/benchmarks/benchmark_summary.csv`
- `results/benchmarks/benchmark_metadata.json`
- `results/benchmarks/benchmark_summary.json`

The report generator writes:

- `results/benchmarks/report/benchmark_report.md`
- `results/benchmarks/report/benchmark_report.html`
- `results/benchmarks/report/figures/*.png`

## Benchmark Methods

The suite currently benchmarks:

- `tbema`: the canonical TBEMA preset exposed by `make_tbema_analyzer()`
- `exact_baseline`: exact sparse-data baseline without transport or selection adjustments
- `dersimonian_laird`: conventional normal-normal random-effects pooling
- `henmi_copas`: a Python translation of the Henmi-Copas publication-bias-robust interval method from `metafor`
- `metafor_trimfill_external`: trim-and-fill via `metafor`
- `metafor_selmodel_external`: step-function selection model via `metafor::selmodel()`
- `copas_selection_external`: Copas selection model via `metasens`

There is also an optional external adapter:

- `robma_bibma_external`: calls `RoBMA::BiBMA()` through `Rscript` if a suitable R + `RoBMA` environment exists

The benchmark runner detects external methods per package, so `metafor`, `metasens`, and `RoBMA` adapters appear independently when their R dependencies are available.

## Caveat

This is a serious prototype, not a claim of settled methodology. If you want publication or applied deployment, the next step is formal simulation benchmarking against established methods under many data-generating regimes.
