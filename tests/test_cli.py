import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from voc_analyzer.cli import app

runner = CliRunner()
SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


@pytest.fixture(autouse=True)
def _wide_terminal(monkeypatch):
    # Render rich/Typer output wide so error-message assertions don't depend on the headless
    # terminal width in CI (a narrow panel word-wraps phrases like "cannot read --from-raw file").
    monkeypatch.setenv("COLUMNS", "200")


def _all_output(result) -> str:
    """Combined stdout+stderr — Typer renders BadParameter errors to stderr, which `result.output`
    (stdout only) excludes in CI."""
    out = result.output
    if result.stderr_bytes:
        out += result.stderr
    return out


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_run_command_prints_product(tmp_path):
    result = runner.invoke(
        app,
        [
            "run",
            "--product",
            "TestProduct",
            "--from-raw",
            str(SAMPLES / "comments.jsonl"),
            "--output-dir",
            str(tmp_path),
            "--no-llm",
        ],
    )
    assert result.exit_code == 0
    assert "TestProduct" in result.stdout


def test_run_from_raw_writes_report(tmp_path):
    result = runner.invoke(
        app,
        [
            "run",
            "-p",
            "Acme Buds",
            "--from-raw",
            str(SAMPLES / "comments.jsonl"),
            "--output-dir",
            str(tmp_path),
            "--no-llm",
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "analysis.json").exists()


def test_run_empty_source_is_safe(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", "-p", "X", "--from-raw", str(empty), "--output-dir", str(tmp_path), "--no-llm"],
    )
    assert result.exit_code == 0
    assert (tmp_path / "report.md").exists()


def test_run_rejects_unknown_platform(tmp_path):
    result = runner.invoke(
        app,
        ["run", "-p", "X", "-P", "myspace", "--from-raw", str(SAMPLES / "comments.jsonl")],
    )
    assert result.exit_code != 0


def test_run_from_raw_skips_malformed_lines(tmp_path):
    good = (SAMPLES / "comments.jsonl").read_text(encoding="utf-8").splitlines()[0]
    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text(good + "\nnot json at all\n" + '{"source": "youtube"}\n', encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", "-p", "X", "--from-raw", str(mixed), "--output-dir", str(tmp_path), "--no-llm"],
    )
    assert result.exit_code == 0
    assert "skipping malformed line" in result.output
    assert (tmp_path / "report.md").exists()


def test_run_from_raw_missing_file_fails_cleanly(tmp_path):
    result = runner.invoke(
        app,
        ["run", "-p", "X", "--from-raw", str(tmp_path / "nope.jsonl"), "--no-llm"],
    )
    assert result.exit_code != 0
    assert "cannot read --from-raw file" in _all_output(result)


def test_run_from_raw_reports_platforms_from_data(tmp_path):
    result = runner.invoke(
        app,
        [
            "run",
            "-p",
            "Acme Buds",
            "--from-raw",
            str(SAMPLES / "comments.jsonl"),
            "--output-dir",
            str(tmp_path),
            "--no-llm",
        ],
    )
    assert result.exit_code == 0
    sources = {
        json.loads(line)["source"]
        for line in (SAMPLES / "comments.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    analysis = json.loads((tmp_path / "analysis.json").read_text(encoding="utf-8"))
    assert set(analysis["platforms"]) == sources
