from pathlib import Path

from typer.testing import CliRunner

from voc_analyzer.cli import app

runner = CliRunner()
SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


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
