"""CLI contract: commands, output shape, and exit codes.

Evidence for gate G1 and defects BASE-002 (``info`` used an empty ``SystemInfo`` and a schema that
did not exist), BASE-013 (failed results did not produce deterministic non-zero exits), PKG-006
(documented commands that were not implemented) and SYS-003 (reports leaked machine identifiers).
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from windowsoptimizerabso import __version__
from windowsoptimizerabso.cli.app import WITHDRAWN_COMMANDS, app
from windowsoptimizerabso.cli.exit_codes import DESCRIPTIONS, ExitCode

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == int(ExitCode.SUCCESS)
    assert __version__ in result.output


def test_version_is_a_prerelease():
    """PKG-005: the version must not imply maturity while blocking gates are open."""
    assert any(marker in __version__ for marker in ("a", "b", "rc", "dev")), __version__
    assert not __version__.startswith("1.")


def test_bare_invocation_shows_help_and_does_not_act():
    result = runner.invoke(app, [])
    assert "winopt" in result.output
    assert "inspect" in result.output


def test_unknown_command_is_a_usage_error():
    result = runner.invoke(app, ["definitely-not-a-command"])
    assert result.exit_code == int(ExitCode.USAGE)


def test_unknown_option_is_a_usage_error():
    result = runner.invoke(app, ["inspect", "--nonsense"])
    assert result.exit_code == int(ExitCode.USAGE)


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

def test_inspect_succeeds_on_any_platform():
    """BASE-002: the baseline's `info` raised AttributeError before printing anything."""
    result = runner.invoke(app, ["inspect"])
    assert result.exit_code == int(ExitCode.SUCCESS), result.output
    assert "Machine" in result.output


def test_inspect_json_is_parseable_and_has_the_documented_shape():
    result = runner.invoke(app, ["inspect", "--json"])
    assert result.exit_code == int(ExitCode.SUCCESS)
    payload = json.loads(result.output)
    for key in ["collected_at", "machine_fingerprint", "is_admin", "os", "collection_notes"]:
        assert key in payload, f"missing {key}"
    assert payload["os"]["system"] in {"Windows", "Linux", "Darwin"}


def test_inspect_redacts_identifiers_by_default():
    """SYS-003: a report that gets pasted into an issue must not carry the hostname."""
    payload = json.loads(runner.invoke(app, ["inspect", "--json"]).output)
    assert "hostname" not in payload
    assert "registered_owner" not in payload["os"]
    assert payload["identifiers_included"] is False
    assert payload["machine_fingerprint"]


def test_inspect_includes_identifiers_only_when_asked():
    payload = json.loads(runner.invoke(app, ["inspect", "--json", "--include-identifiers"]).output)
    assert payload["identifiers_included"] is True
    assert payload["hostname"]


def test_inspect_reports_what_it_could_not_collect():
    """"Not collected" must be visible rather than silently absent."""
    payload = json.loads(runner.invoke(app, ["inspect", "--json"]).output)
    assert isinstance(payload["collection_notes"], list)


def test_collected_at_is_timezone_aware():
    """SYS-004: a naive timestamp is ambiguous across a DST boundary."""
    from datetime import datetime

    payload = json.loads(runner.invoke(app, ["inspect", "--json"]).output)
    parsed = datetime.fromisoformat(payload["collected_at"])
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def test_doctor_reports_containment():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == int(ExitCode.SUCCESS), result.output
    assert "contained" in result.output.lower()


def test_doctor_json_exposes_checks_and_containment():
    payload = json.loads(runner.invoke(app, ["doctor", "--json"]).output)
    assert {c["name"] for c in payload["checks"]} == {
        "python version", "platform", "elevation", "containment",
    }
    assert payload["containment"]["mutation_enabled"] is False
    assert payload["containment"]["legacy_mutation_enabled"] is False


# ---------------------------------------------------------------------------
# exit codes
# ---------------------------------------------------------------------------

def test_every_exit_code_is_documented():
    for code in ExitCode:
        assert code in DESCRIPTIONS, f"{code.name} has no documented meaning"


def test_exit_codes_are_unique_and_stable():
    values = [int(c) for c in ExitCode]
    assert len(values) == len(set(values))
    # Pinned: automation depends on these numbers.
    assert int(ExitCode.SUCCESS) == 0
    assert int(ExitCode.USAGE) == 2
    assert int(ExitCode.CONTAINED) == 13


def test_exit_codes_command_lists_them_all():
    payload = json.loads(runner.invoke(app, ["exit-codes", "--json"]).output)
    assert {c.name for c in ExitCode} == set(payload)


# ---------------------------------------------------------------------------
# Withdrawn commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", sorted(WITHDRAWN_COMMANDS))
def test_withdrawn_command_names_its_defects(command):
    """A refusal has to be actionable: which defect, and where to read about it."""
    result = runner.invoke(app, [command])
    assert result.exit_code == int(ExitCode.CONTAINED)
    defects, _ = WITHDRAWN_COMMANDS[command]
    assert defects.split(",")[0].strip() in result.output
    assert "WORK_LEDGER" in result.output


def test_no_command_outside_the_withdrawn_set_can_mutate():
    """Whatever the CLI grows, `winopt --help` must list only read-only work for now."""
    help_text = runner.invoke(app, ["--help"]).output
    listed = {line.split()[0] for line in help_text.splitlines() if line.startswith(" ") and line.strip()}
    unexpected = listed & {"apply", "plan", "recover", "verify"}
    assert not unexpected, f"mutating lifecycle commands appeared before the executor: {unexpected}"
