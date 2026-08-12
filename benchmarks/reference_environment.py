"""Read-only cold-start doctor for the external Gate 1 reference environment."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "requirements" / "reference-campaign.txt"
EXPECTED_PIN_NAMES = frozenset(
    {
        "duckdb",
        "jsonschema",
        "mypy",
        "polars",
        "psutil",
        "pyarrow",
        "pytest",
        "pytest-cov",
        "ruff",
    }
)
PROJECT_DISTRIBUTIONS = {
    "brullik-grid-platform-dev": "0.2.0",
    "grid-bybit-private": "0.2.0",
    "grid-bybit-public": "0.2.0",
    "grid-contracts": "0.2.0",
    "grid-data": "0.2.0",
    "grid-live": "0.2.0",
    "grid-release": "0.2.0",
    "grid-research": "0.2.0",
}
REQUIRED_MODULES = (
    "duckdb",
    "grid_contracts",
    "grid_data",
    "jsonschema",
    "polars",
    "psutil",
    "pyarrow",
)
PRIVATE_EXCHANGE_ENVIRONMENT = tuple(
    f"BYBIT_{environment}_API_{member}"
    for environment in ("DEMO", "MAINNET", "TESTNET")
    for member in ("KEY", "SECRET")
)


def normalize_distribution_name(name: str) -> str:
    """Apply the canonical package-name comparison used by Python packaging tools."""

    return re.sub(r"[-_.]+", "-", name).lower()


def parse_exact_constraints(path: Path = CONSTRAINTS) -> dict[str, str]:
    """Read the reviewed direct pins and reject ranges, markers, URLs, or duplicate names."""

    pins: dict[str, str] = {}
    pattern = re.compile(r"(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[A-Za-z0-9_.+!-]+)")
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.fullmatch(line)
        if match is None:
            raise ValueError(f"constraint line {line_number} is not one exact direct pin")
        name = normalize_distribution_name(match.group("name"))
        if name in pins:
            raise ValueError(f"constraint line {line_number} duplicates {name}")
        pins[name] = match.group("version")
    return pins


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _installed_versions(names: Sequence[str]) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _git_output(*arguments: str) -> tuple[bool, str]:
    result = _run(("git", *arguments))
    return result.returncode == 0, result.stdout.strip()


def _canonical_origin(url: str) -> bool:
    normalized = url.strip().lower().removesuffix(".git")
    return bool(
        re.fullmatch(
            r"(?:https://github\.com/|git@github\.com:)"
            r"brullik/brullik-bybit-grid-bot-research",
            normalized,
        )
    )


def evaluate_reference_environment(
    *,
    python_version: tuple[int, int],
    python_version_full: str,
    isolated_environment: bool,
    working_directory_is_root: bool,
    constraints: Mapping[str, str],
    installed_versions: Mapping[str, str | None],
    importable_modules: Mapping[str, bool],
    pip_check_passed: bool,
    source_manifest_verified: bool,
    git_clean: bool,
    git_branch: str,
    git_head: str,
    origin_main: str,
    canonical_origin: bool,
    private_environment_names: Sequence[str],
) -> dict[str, Any]:
    """Evaluate already collected facts without reading secrets or mutating the host."""

    try:
        constraints_sha256 = hashlib.sha256(CONSTRAINTS.read_bytes()).hexdigest()
    except OSError:
        constraints_sha256 = ""
    constraint_contract = set(constraints) == EXPECTED_PIN_NAMES
    constrained_versions_match = constraint_contract and all(
        installed_versions.get(name) == version for name, version in constraints.items()
    )
    project_versions_match = all(
        installed_versions.get(name) == version for name, version in PROJECT_DISTRIBUTIONS.items()
    )
    required_modules_importable = all(
        importable_modules.get(name) is True for name in REQUIRED_MODULES
    )
    checks = {
        "canonical_origin": canonical_origin,
        "clean_worktree": git_clean,
        "constraint_contract": constraint_contract,
        "constrained_versions_match": constrained_versions_match,
        "exact_python_3_12": python_version == (3, 12),
        "head_matches_origin_main": bool(git_head) and git_head == origin_main,
        "isolated_virtual_environment": isolated_environment,
        "main_branch_checked_out": git_branch == "main",
        "monorepo_distributions_installed": project_versions_match,
        "pip_dependencies_consistent": pip_check_passed,
        "private_exchange_environment_absent": not private_environment_names,
        "required_modules_importable": required_modules_importable,
        "source_manifest_verified": source_manifest_verified,
        "working_directory_is_repository_root": working_directory_is_root,
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    return {
        "checks": checks,
        "constraints": {
            "artifact": CONSTRAINTS.relative_to(ROOT).as_posix(),
            "artifact_sha256": constraints_sha256,
            "pins": dict(sorted(constraints.items())),
        },
        "failures": failures,
        "observed": {
            "git_branch": git_branch,
            "git_head": git_head,
            "installed_versions": dict(sorted(installed_versions.items())),
            "private_exchange_environment_names": sorted(private_environment_names),
            "python": python_version_full,
        },
        "status": "ready-for-reference-campaign" if not failures else "blocked-preflight",
    }


def collect_reference_environment() -> dict[str, Any]:
    """Collect a secret-safe, read-only bootstrap report from the current checkout."""

    try:
        constraints = parse_exact_constraints()
    except (OSError, ValueError):
        constraints = {}
    installed = _installed_versions(tuple(sorted(set(constraints) | set(PROJECT_DISTRIBUTIONS))))
    importable = {name: importlib.util.find_spec(name) is not None for name in REQUIRED_MODULES}
    pip_check = _run((sys.executable, "-m", "pip", "check"))
    manifest = _run((sys.executable, str(ROOT / "scripts" / "update_manifest.py")))
    status_ok, status = _git_output("status", "--porcelain=v1", "--untracked-files=all")
    branch_ok, branch = _git_output("symbolic-ref", "--short", "-q", "HEAD")
    head_ok, head = _git_output("rev-parse", "HEAD")
    origin_main_ok, origin_main = _git_output("rev-parse", "refs/remotes/origin/main")
    origin_ok, origin = _git_output("remote", "get-url", "origin")
    private_names = [name for name in PRIVATE_EXCHANGE_ENVIRONMENT if name in os.environ]
    return evaluate_reference_environment(
        python_version=(sys.version_info.major, sys.version_info.minor),
        python_version_full=platform.python_version(),
        isolated_environment=sys.prefix != sys.base_prefix,
        working_directory_is_root=Path.cwd().resolve() == ROOT,
        constraints=constraints,
        installed_versions=installed,
        importable_modules=importable,
        pip_check_passed=pip_check.returncode == 0,
        source_manifest_verified=manifest.returncode == 0,
        git_clean=status_ok and not status,
        git_branch=branch if branch_ok else "",
        git_head=head if head_ok else "",
        origin_main=origin_main if origin_main_ok else "",
        canonical_origin=origin_ok and _canonical_origin(origin),
        private_environment_names=private_names,
    )


def main() -> int:
    report = collect_reference_environment()
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "ready-for-reference-campaign" else 2


if __name__ == "__main__":
    raise SystemExit(main())
