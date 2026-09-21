"""AST scanner: detect RNG use without seed-setting in the same file."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from seedguard.patterns import (
    RNG_ATTRS,
    RNG_QUALNAME_PREFIXES,
    RNG_ROOTS,
    SEED_ATTRS,
    SEED_OR_SETUP_ATTRS,
    SEED_QUALNAMES,
    SKIP_DIR_NAMES,
)


@dataclass
class Hit:
    kind: str  # "seed" | "rng"
    qualname: str
    lineno: int
    col: int


@dataclass
class FileFinding:
    path: str
    seeds: list[Hit] = field(default_factory=list)
    rng_uses: list[Hit] = field(default_factory=list)

    @property
    def is_unseeded(self) -> bool:
        return bool(self.rng_uses) and not self.seeds

    def to_dict(self) -> dict:
        d = asdict(self)
        d["unseeded"] = self.is_unseeded
        return d


@dataclass
class ScanResult:
    findings: list[FileFinding]
    scanned: int
    errors: list[str] = field(default_factory=list)

    @property
    def unseeded(self) -> list[FileFinding]:
        return [f for f in self.findings if f.is_unseeded]

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "unseeded_count": len(self.unseeded),
            "findings": [f.to_dict() for f in self.findings if f.is_unseeded],
            "errors": self.errors,
        }


def _attr_chain(node: ast.AST) -> list[str] | None:
    """Return dotted name parts for Name / Attribute chains."""
    parts: list[str] = []
    cur: ast.AST | None = node
    while True:
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            break
        if isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
            continue
        return None
    parts.reverse()
    return parts


def _qualname_from_call(node: ast.Call) -> str | None:
    parts = _attr_chain(node.func)
    if not parts:
        return None
    return ".".join(parts)


def _is_seed_call(qual: str) -> bool:
    if qual in SEED_QUALNAMES:
        return True
    if qual in {"random.Random", "Random"}:
        return True
    parts = qual.split(".")
    if parts and parts[-1] in SEED_ATTRS:
        if parts[0] in RNG_ROOTS or parts[-1] in SEED_ATTRS:
            return True
    return False


def _is_rng_use(qual: str) -> bool:
    if _is_seed_call(qual):
        return False
    parts = qual.split(".")
    if not parts:
        return False
    for prefix in RNG_QUALNAME_PREFIXES:
        if qual == prefix.rstrip(".") or qual.startswith(prefix):
            attr = parts[-1]
            if attr in SEED_OR_SETUP_ATTRS:
                return False
            if attr in RNG_ATTRS or parts[0] in {
                "np", "numpy", "random", "tf", "tensorflow", "torch"
            }:
                if attr in SEED_OR_SETUP_ATTRS:
                    return False
                if "random" in parts[:-1] or parts[0] == "random":
                    return attr not in SEED_OR_SETUP_ATTRS
                if parts[0] == "torch" and (
                    attr.startswith("rand")
                    or attr in {
                        "bernoulli", "normal", "multinomial", "poisson", "randperm"
                    }
                ):
                    return True
    if len(parts) >= 2 and parts[0] in RNG_ROOTS and parts[-1] in RNG_ATTRS:
        if parts[-1] in SEED_OR_SETUP_ATTRS:
            return False
        return True
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.seeds: list[Hit] = []
        self.rng_uses: list[Hit] = []
        self._aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            root = alias.name.split(".")[0]
            if root in RNG_ROOTS:
                self._aliases[name] = root
            if alias.name in {
                "numpy.random", "np.random", "tensorflow.random", "tf.random"
            }:
                self._aliases[name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            if mod in {
                "random", "numpy.random", "np.random", "torch",
                "tensorflow.random", "tf.random",
            }:
                if alias.name in SEED_ATTRS or alias.name == "Random":
                    self._aliases[local] = f"{mod}.{alias.name}"
                elif alias.name in RNG_ATTRS:
                    self._aliases[local] = f"{mod}.{alias.name}"
            if mod in {"numpy", "np"} and alias.name == "random":
                self._aliases[local] = "numpy.random"
            if mod in {"tensorflow", "tf"} and alias.name == "random":
                self._aliases[local] = "tf.random"
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        qual = _qualname_from_call(node)
        if qual is None:
            if isinstance(node.func, ast.Name):
                mapped = self._aliases.get(node.func.id)
                if mapped:
                    qual = mapped
                else:
                    self.generic_visit(node)
                    return
            else:
                self.generic_visit(node)
                return
        else:
            parts = qual.split(".")
            if parts[0] in self._aliases:
                root = self._aliases[parts[0]]
                parts = root.split(".") + parts[1:]
                qual = ".".join(parts)

        lineno = getattr(node, "lineno", 0) or 0
        col = getattr(node, "col_offset", 0) or 0

        if qual in {"random.Random", "Random"} or qual.endswith(".Random"):
            self.seeds.append(Hit("seed", qual, lineno, col))
            self.generic_visit(node)
            return

        if _is_seed_call(qual):
            self.seeds.append(Hit("seed", qual, lineno, col))
        elif _is_rng_use(qual):
            self.rng_uses.append(Hit("rng", qual, lineno, col))
        else:
            if isinstance(node.func, ast.Name):
                mapped = self._aliases.get(node.func.id, "")
                if mapped:
                    if mapped.split(".")[-1] in SEED_ATTRS or mapped.endswith(".Random"):
                        self.seeds.append(Hit("seed", mapped, lineno, col))
                    elif _is_rng_use(mapped) or mapped.split(".")[-1] in RNG_ATTRS:
                        self.rng_uses.append(Hit("rng", mapped, lineno, col))

        self.generic_visit(node)


def analyze_source(source: str, filename: str = "<string>") -> FileFinding:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise SyntaxError(f"{filename}: {exc}") from exc
    visitor = _Visitor()
    visitor.visit(tree)
    return FileFinding(path=filename, seeds=visitor.seeds, rng_uses=visitor.rng_uses)


def iter_python_files(root: Path) -> Iterable[Path]:
    root = root.resolve()
    if root.is_file():
        if root.suffix == ".py":
            yield root
        return
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def scan_path(root: Path) -> ScanResult:
    findings: list[FileFinding] = []
    errors: list[str] = []
    scanned = 0
    for path in iter_python_files(root):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            finding = analyze_source(text, filename=str(path))
            findings.append(finding)
        except SyntaxError as exc:
            errors.append(str(exc))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return ScanResult(findings=findings, scanned=scanned, errors=errors)
