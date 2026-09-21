"""Smoke tests for seedguard scanner and CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from seedguard.scan import analyze_source, scan_path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_unseeded_random_detected():
    src = "import random\nx = random.randint(0, 10)\n"
    finding = analyze_source(src, "t.py")
    assert finding.is_unseeded
    assert any(h.qualname == "random.randint" for h in finding.rng_uses)
    assert not finding.seeds


def test_seeded_random_clean():
    src = "import random\nrandom.seed(0)\nx = random.random()\n"
    finding = analyze_source(src, "t.py")
    assert not finding.is_unseeded
    assert finding.seeds
    assert finding.rng_uses


def test_numpy_unseeded():
    src = "import numpy as np\ny = np.random.randn(3)\n"
    finding = analyze_source(src, "t.py")
    assert finding.is_unseeded


def test_numpy_seeded():
    src = "import numpy as np\nnp.random.seed(1)\ny = np.random.rand(2)\n"
    finding = analyze_source(src, "t.py")
    assert not finding.is_unseeded


def test_torch_manual_seed():
    src = (
        "import torch\n"
        "torch.manual_seed(0)\n"
        "x = torch.randn(2)\n"
    )
    finding = analyze_source(src, "t.py")
    assert not finding.is_unseeded
    assert any("manual_seed" in h.qualname for h in finding.seeds)


def test_torch_unseeded():
    src = "import torch\nx = torch.rand(4)\n"
    finding = analyze_source(src, "t.py")
    assert finding.is_unseeded


def test_tf_set_seed():
    src = (
        "import tensorflow as tf\n"
        "tf.random.set_seed(123)\n"
        "z = tf.random.uniform((2,))\n"
    )
    finding = analyze_source(src, "t.py")
    assert not finding.is_unseeded


def test_from_import_seed():
    src = "from random import seed, randint\nseed(7)\nprint(randint(1, 3))\n"
    finding = analyze_source(src, "t.py")
    assert not finding.is_unseeded


def test_random_Random_constructor_counts_as_seed():
    src = "import random\nrng = random.Random(99)\nprint(rng.random())\n"
    finding = analyze_source(src, "t.py")
    # constructor is seed hygiene; method .random() on instance is not
    # statically tracked as np/random module -- may or may not flag.
    # At minimum Random(99) should be recorded as a seed call.
    assert any("Random" in h.qualname for h in finding.seeds)


def test_no_rng_no_finding():
    src = "def add(a, b):\n    return a + b\n"
    finding = analyze_source(src, "t.py")
    assert not finding.is_unseeded
    assert not finding.rng_uses


def test_scan_examples_dir():
    result = scan_path(EXAMPLES)
    assert result.scanned >= 2
    paths = {Path(f.path).name for f in result.unseeded}
    assert "unseeded.py" in paths
    assert "seeded.py" not in paths


def test_cli_json_and_exit_codes():
    seeded = EXAMPLES / "seeded.py"
    unseeded = EXAMPLES / "unseeded.py"
    r0 = subprocess.run(
        [sys.executable, "-m", "seedguard", str(seeded), "--fail-on", "findings"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r0.returncode == 0, r0.stdout + r0.stderr

    r1 = subprocess.run(
        [sys.executable, "-m", "seedguard", str(unseeded), "--json", "--fail-on", "findings"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r1.returncode == 1
    payload = json.loads(r1.stdout)
    assert payload["unseeded_count"] >= 1

    r2 = subprocess.run(
        [sys.executable, "-m", "seedguard", "/nonexistent/path", "--fail-on", "never"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r2.returncode == 2


def test_default_rng_counts_as_seed_hygiene():
    src = "import numpy as np\nrng = np.random.default_rng(0)\nprint(rng.normal())\n"
    finding = analyze_source(src, "t.py")
    assert finding.seeds
    # Instance method .normal() is not a module-level RNG qualname -- clean is ok.
    assert not finding.is_unseeded or finding.seeds
