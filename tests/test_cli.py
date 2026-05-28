from typer.testing import CliRunner

from voc_analyzer.cli import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_run_command_prints_product():
    result = runner.invoke(app, ["run", "--product", "TestProduct"])
    assert result.exit_code == 0
    assert "TestProduct" in result.stdout
