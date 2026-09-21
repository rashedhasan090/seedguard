"""CLI entrypoint for seedguard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from seedguard import __version__
from seedguard.scan import ScanResult, scan_path


def _format_text(result: ScanResult) -> str:
    lines: list[str] = []
    unseeded = result.unseeded
    lines.append(
        f"scanned={result.scanned}  unseeded={len(unseeded)}  errors={len(result.errors)}"
    )
    if unseeded:
        lines.append("")
        lines.append("Unseeded RNG use (RNG calls with no seed-setting in the same file):")
        for finding in unseeded:
            rng_summary = ", ".join(
                f"{h.qualname}@{h.lineno}" for h in finding.rng_uses[:8]
            )
            extra = ""
            if len(finding.rng_uses) > 8:
                extra = f" (+{len(finding.rng_uses) - 8} more)"
            lines.append(f"  {finding.path}")
            lines.append(f"    rng: {rng_summary}{extra}")
    else:
        lines.append("")
        lines.append("No unseeded RNG files.")
    if result.errors:
        lines.append("")
        lines.append("Parse/IO errors:")
        for err in result.errors:
            lines.append(f"  {err}")
    return "\n".join(lines) + "\n"


def _format_json(result: ScanResult) -> str:
    return json.dumps(result.to_dict(), indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="seedguard",
        description=(
            "Scan Python sources for stochastic API use without seed-setting "
            "in the same file. Aimed at ML/research reproducibility hygiene."
        ),
    )
    p.add_argument(
        "path",
        type=Path,
        help="File or directory to scan",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON report",
    )
    p.add_argument(
        "--fail-on",
        choices=("findings", "never", "errors"),
        default="findings",
        help=(
            "Exit 1 when condition matches "
            "(default: findings -- CI-friendly). "
            "'never' always exits 0 on success; "
            "'errors' fails only on parse/IO errors."
        ),
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 2

    path: Path = args.path
    if not path.exists():
        print(f"seedguard: path not found: {path}", file=sys.stderr)
        return 2

    try:
        result = scan_path(path)
    except Exception as exc:  # noqa: BLE001 -- surface as usage/runtime error
        print(f"seedguard: {exc}", file=sys.stderr)
        return 2

    out = _format_json(result) if args.as_json else _format_text(result)
    sys.stdout.write(out)

    if args.fail_on == "never":
        return 0
    if args.fail_on == "errors":
        return 1 if result.errors else 0
    # findings (default)
    if result.unseeded:
        return 1
    if result.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
