// Generate known-truth meta-analysis datasets and emit them as JSON on stdout.
// Single-sources the DGP from ../../_kit/dgp.mjs so JS and Python agree.
//
// Usage: node gen_datasets.mjs <scenario> <nReps> <k> <mu> <tau2> [seed0]
// Emits: { meta:{...}, datasets:[ { y:[...], se:[...] }, ... ] }

import { generate, makeRng } from "./dgp.mjs";

const [, , scenario = "none", nRepsStr = "400", kStr = "15",
  muStr = "0.4", tau2Str = "0.04", seed0Str = "1000"] = process.argv;

const nReps = parseInt(nRepsStr, 10);
const k = parseInt(kStr, 10);
const mu = parseFloat(muStr);
const tau2 = parseFloat(tau2Str);
const seed0 = parseInt(seed0Str, 10);

const datasets = [];
for (let r = 0; r < nReps; r++) {
  const rng = makeRng(seed0 + r * 7919);
  const d = generate(mu, tau2, k, scenario, rng);
  datasets.push({ y: d.yi, se: d.vi.map((v) => Math.sqrt(v)) });
}

process.stdout.write(
  JSON.stringify({ meta: { scenario, nReps, k, mu, tau2, seed0 }, datasets })
);
