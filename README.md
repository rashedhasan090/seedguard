# seedguard

Offline CLI that flags Python files using stochastic APIs (**`random`**, **`numpy.random`**, **`torch`** RNG, **`tf.random`**, ...) **without** any seed-setting call in the same file.

Built for ML / research reproducibility hygiene. Stdlib-only at runtime. CI-friendly exit codes.

## Why this is novel

Recent tooling in this series focused on agent JSONL manifests and call logs. **seedguard** rotates to research/ML: it does not lint style or ban randomness -- it checks **seed hygiene**. If a file draws from an RNG but never calls `seed` / `manual_seed` / `set_seed` (or equivalent) in that file, it is reported.

Distinct from agent-log tools (toolorphan, callstorm, stubtruth, claimcite, promptfence, ...) and from general linters: the signal is specifically stochastic use without local seed setup.

## Install

```bash
pip install -e ".[dev]"   # from a clone
# or
pip install .
```

Requires Python 3.10+.

## Usage

```bash
seedguard PATH
seedguard PATH --json
seedguard PATH --fail-on findings   # default; exit 1 if unseeded files
seedguard PATH --fail-on never      # always 0 on successful scan
seedguard PATH --fail-on errors     # exit 1 only on parse/IO errors
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | Clean (or `--fail-on never`) |
| 1 | Findings (or errors, depending on `--fail-on`) |
| 2 | Bad usage / path not found |

## Demo

```bash
# clean
seedguard examples/seeded.py
# -> scanned=1  unseeded=0

# flagged
seedguard examples/unseeded.py --fail-on findings
# -> exit 1, lists random.randint / np.random.randn
```

What counts as a **seed** (examples): `random.seed`, `np.random.seed`, `numpy.random.default_rng(...)`, `torch.manual_seed`, `torch.cuda.manual_seed_all`, `tf.random.set_seed`, `random.Random(seed)`.

What counts as **RNG use** (examples): `random.randint` / `choice` / `shuffle`, `np.random.randn`, `torch.rand` / `randn` / `randint`, `tf.random.uniform`, and similar.

Skipped directories: `.git`, venvs, `__pycache__`, `node_modules`, build artifacts, etc.

## License

MIT (c) 2026 Rashed Hasan
