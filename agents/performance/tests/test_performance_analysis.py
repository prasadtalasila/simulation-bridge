"""Tests for the agent performance analysis pipeline."""

import pandas as pd
import pytest

import generate_performance_data as gen
import performance_analysis as analysis


@pytest.fixture(name="logs_dir")
def fixture_logs_dir(tmp_path):
    """Generate the full set of agent logs in a temporary directory."""

    gen.generate_all(tmp_path, gen.DEFAULT_SEED)
    return tmp_path


def test_detect_engine_label():
    """The engine label is extracted from the startup-duration column."""

    frame = pd.DataFrame(
        {"MATLAB Startup Duration (s)": [1.0], "Total Duration (s)": [2.0]}
    )
    assert analysis.detect_engine_label(frame) == "MATLAB"


def test_detect_engine_label_missing():
    """A log without a startup-duration column raises KeyError."""

    frame = pd.DataFrame({"Total Duration (s)": [1.0]})
    with pytest.raises(KeyError):
        analysis.detect_engine_label(frame)


def test_compute_overheads():
    """Overhead and startup ratio are derived correctly."""

    frame = pd.DataFrame(
        {
            "MATLAB Startup Duration (s)": [1.0],
            "Simulation Duration (s)": [2.0],
            "Total Duration (s)": [3.5],
        }
    )
    result = analysis.compute_overheads(frame, "MATLAB")
    assert result["Agent Overhead (s)"].iloc[0] == pytest.approx(0.5)
    # Ratio = startup / (total - simulation) = 1.0 / 1.5.
    assert result["Startup/Total Ratio"].iloc[0] == pytest.approx(1.0 / 1.5)


def test_compute_overheads_zero_processing():
    """A base-agent style row with no engine time yields a zero ratio."""

    frame = pd.DataFrame(
        {
            "ENGINE Startup Duration (s)": [0.0],
            "Simulation Duration (s)": [0.0],
            "Total Duration (s)": [0.0],
        }
    )
    result = analysis.compute_overheads(frame, "ENGINE")
    assert result["Startup/Total Ratio"].iloc[0] == 0.0


def test_analyse_agent_writes_plots(logs_dir, tmp_path):
    """Analysing one agent writes its three plot files."""

    results_dir = tmp_path / "results"
    csv_path = logs_dir / "matlab_agent_performance_metrics.csv"
    summary = analysis.analyse_agent("matlab", csv_path, results_dir)

    assert summary.engine_label == "MATLAB"
    assert summary.mean_overhead > 0
    for suffix in ("overhead", "startup_total_ratio_pie", "resource_usage"):
        assert (results_dir / f"matlab_{suffix}.png").exists() or (
            results_dir / f"matlab_agent_{suffix}.png"
        ).exists()


def test_run_analysis_full_pipeline(logs_dir, tmp_path):
    """The full pipeline produces a summary per agent, plots and a report."""

    results_dir = tmp_path / "results"
    summaries = analysis.run_analysis(logs_dir, results_dir)

    assert len(summaries) == 3
    assert (results_dir / "agent_overhead_comparison.png").exists()
    report = results_dir / "report_performance.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Mean Agent Overhead" in text
    assert "MATLAB Agent" in text


def test_run_analysis_no_logs(tmp_path):
    """An empty input directory yields no summaries and no crash."""

    summaries = analysis.run_analysis(tmp_path / "empty", tmp_path / "out")
    assert summaries == []
