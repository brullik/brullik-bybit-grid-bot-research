from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import benchmarks.reference_environment as environment

ROOT = Path(__file__).parents[2]


def valid_facts() -> dict[str, object]:
    constraints = environment.parse_exact_constraints()
    installed = {**constraints, **environment.PROJECT_DISTRIBUTIONS}
    return {
        "python_version": (3, 12),
        "python_version_full": "3.12.10",
        "isolated_environment": True,
        "working_directory_is_root": True,
        "constraints": constraints,
        "installed_versions": installed,
        "importable_modules": {name: True for name in environment.REQUIRED_MODULES},
        "pip_check_passed": True,
        "source_manifest_verified": True,
        "git_clean": True,
        "git_branch": "main",
        "git_head": "a" * 40,
        "origin_main": "a" * 40,
        "canonical_origin": True,
        "private_environment_names": [],
    }


def test_reference_constraints_pin_every_root_extra_exactly() -> None:
    pins = environment.parse_exact_constraints()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]
    declared_names = {
        environment.normalize_distribution_name(requirement.split("[", 1)[0].split(">", 1)[0])
        for group in ("data", "dev")
        for requirement in extras[group]
    }

    assert set(pins) == environment.EXPECTED_PIN_NAMES == declared_names


def test_reference_environment_accepts_only_complete_clean_main_install() -> None:
    report = environment.evaluate_reference_environment(**valid_facts())

    assert report["status"] == "ready-for-reference-campaign"
    assert report["failures"] == []
    assert all(report["checks"].values())


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("python_version", (3, 13), "exact_python_3_12"),
        ("isolated_environment", False, "isolated_virtual_environment"),
        ("git_clean", False, "clean_worktree"),
        ("git_branch", "feature", "main_branch_checked_out"),
        ("origin_main", "b" * 40, "head_matches_origin_main"),
        (
            "private_environment_names",
            ["BYBIT_MAINNET_API_SECRET"],
            "private_exchange_environment_absent",
        ),
    ],
)
def test_reference_environment_fails_closed_on_bootstrap_drift(
    field: str, value: object, failure: str
) -> None:
    facts = valid_facts()
    facts[field] = value

    report = environment.evaluate_reference_environment(**facts)

    assert report["status"] == "blocked-preflight"
    assert failure in report["failures"]


def test_reference_environment_rejects_missing_or_mismatched_install() -> None:
    facts = valid_facts()
    installed = dict(facts["installed_versions"])
    installed["duckdb"] = "future-version"
    installed["grid-data"] = None
    facts["installed_versions"] = installed
    modules = dict(facts["importable_modules"])
    modules["grid_data"] = False
    facts["importable_modules"] = modules

    report = environment.evaluate_reference_environment(**facts)

    assert report["status"] == "blocked-preflight"
    assert "constrained_versions_match" in report["failures"]
    assert "monorepo_distributions_installed" in report["failures"]
    assert "required_modules_importable" in report["failures"]


def test_constraint_parser_rejects_ranges_and_duplicates(tmp_path: Path) -> None:
    ranged = tmp_path / "ranged.txt"
    ranged.write_text("duckdb>=1.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not one exact direct pin"):
        environment.parse_exact_constraints(ranged)

    duplicate = tmp_path / "duplicate.txt"
    duplicate.write_text("duckdb==1.5.5\nDuckDB==1.5.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicates duckdb"):
        environment.parse_exact_constraints(duplicate)


def test_reference_report_never_contains_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_value = "must-not-appear"
    monkeypatch.setenv("BYBIT_MAINNET_API_SECRET", sentinel_value)
    facts = valid_facts()
    facts["private_environment_names"] = ["BYBIT_MAINNET_API_SECRET"]

    report = environment.evaluate_reference_environment(**facts)

    assert sentinel_value not in str(report)
    assert report["observed"]["private_exchange_environment_names"] == ["BYBIT_MAINNET_API_SECRET"]
