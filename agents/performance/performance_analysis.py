"""Performance analysis for simulation-bridge agents.

This module parses the session logs emitted by each agent's
``PerformanceMonitor`` and derives the *agent overhead* — the time spent by the
agent processing a request, excluding engine startup and simulation runtime.
For every agent it renders matplotlib plots (overhead trend, startup/total
ratio, resource usage) and writes a consolidated Markdown report, plus a
cross-agent overhead comparison.

It follows the approach of ``agents/matlab/performance/performance_analysis.py``
but is generic over the agent engine label, so the same code analyses the base,
Python and MATLAB agents. The logs are produced by
``generate_performance_data.py``, which means the whole pipeline runs without
executing the actual MATLAB or Python simulations.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, NamedTuple

import matplotlib

matplotlib.use("Agg")  # Headless backend so plots render without a display.

import matplotlib.pyplot as plt  # noqa: E402  pylint: disable=wrong-import-position
import pandas as pd  # noqa: E402  pylint: disable=wrong-import-position

DEFAULT_INPUT_DIR = Path(__file__).resolve().parent / "performance_logs"
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Maps the log file stem prefix to a human-readable agent name.
AGENT_LABELS = {
    "base": "Base Agent",
    "python": "Python Agent",
    "matlab": "MATLAB Agent",
}

_STARTUP_COLUMN_RE = re.compile(r"^(?P<label>.+) Startup Duration \(s\)$")


class AgentSummary(NamedTuple):
    """Aggregate metrics for a single agent's session log."""

    name: str
    engine_label: str
    mean_overhead: float
    mean_startup_ratio: float
    mean_cpu: float
    mean_memory: float
    dataframe: pd.DataFrame


def detect_engine_label(dataframe: pd.DataFrame) -> str:
    """Return the engine label embedded in the startup-duration column."""

    for column in dataframe.columns:
        match = _STARTUP_COLUMN_RE.match(column)
        if match:
            return match.group("label")
    raise KeyError("No '<label> Startup Duration (s)' column found in log.")


def compute_overheads(dataframe: pd.DataFrame, engine_label: str) -> pd.DataFrame:
    """Add agent overhead and startup/total ratio columns to ``dataframe``."""

    startup = dataframe[f"{engine_label} Startup Duration (s)"]
    simulation = dataframe["Simulation Duration (s)"]
    total = dataframe["Total Duration (s)"]

    dataframe["Agent Overhead (s)"] = total - startup - simulation

    # Total processing time excluding the simulation run; guard divide-by-zero
    # for agents (e.g. the base agent) that never start an engine.
    processing = (total - simulation).replace(0.0, pd.NA)
    dataframe["Startup/Total Ratio"] = (startup / processing).fillna(0.0)
    return dataframe


def plot_agent_overhead(dataframe: pd.DataFrame, mean_overhead: float,
                        agent_name: str, output_path: Path) -> None:
    """Plot the per-operation agent overhead and save it to ``output_path``."""

    plt.figure(figsize=(12, 8))
    plt.plot(dataframe["Operation ID"], dataframe["Agent Overhead (s)"],
             "b-o", label="Agent Overhead")
    plt.axhline(mean_overhead, color="r", linestyle="--",
                label=f"Mean Overhead ({mean_overhead * 1000:.2f} ms)")

    plt.title(f"{agent_name} Overhead", fontsize=16)
    plt.xlabel("Request ID")
    plt.ylabel("Agent Overhead (seconds)")
    plt.xticks(rotation=45, ha="right")
    plt.legend(loc="best", fontsize=12)
    plt.grid(True)

    note = (
        "Note:\n"
        "Agent Overhead is the time spent excluding engine startup and "
        "simulation durations.\n"
        "It represents overhead in processing the request."
    )
    plt.text(
        0.5, -0.4, note, ha="center", va="top", fontsize=10, color="black",
        transform=plt.gca().transAxes,
        bbox={"facecolor": "white", "alpha": 0.8, "boxstyle": "round,pad=0.5"},
    )
    plt.tight_layout(rect=(0, 0.05, 1, 1))
    plt.savefig(output_path)
    plt.close()


def plot_startup_ratio(mean_startup_ratio: float, agent_name: str,
                       output_path: Path) -> None:
    """Plot the startup/total ratio as a pie chart and save it."""

    labels = ["Startup Duration", "Other Duration"]
    sizes = [mean_startup_ratio, 1 - mean_startup_ratio]
    colors = ["#66b3ff", "#ff9999"]

    plt.figure(figsize=(8, 8))
    plt.pie(
        sizes, labels=labels, autopct="%1.1f%%", startangle=90, colors=colors,
        wedgeprops={"edgecolor": "black"}, textprops={"fontsize": 12},
    )
    plt.title(f"{agent_name} Average Startup / Total Duration Ratio", fontsize=14)
    note = (
        "Note:\n"
        "Simulation Duration is excluded.\n"
        "This ratio shows the average time spent starting the engine\n"
        "relative to total processing time (excluding simulation)."
    )
    plt.text(
        0, -1.4, note, ha="center", va="top", fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.8, "boxstyle": "round,pad=0.5"},
    )
    plt.tight_layout(rect=(0, 0.05, 1, 1))
    plt.savefig(output_path)
    plt.close()


def plot_resource_usage(dataframe: pd.DataFrame, agent_name: str,
                        output_path: Path) -> None:
    """Plot CPU and memory usage per operation and save it."""

    df_sorted = dataframe.sort_values("Operation ID")
    _, ax1 = plt.subplots(figsize=(14, 7))

    color_cpu = "tab:green"
    ax1.set_xlabel("Request ID")
    ax1.set_ylabel("CPU Usage (%)", color=color_cpu)
    ax1.plot(df_sorted["Operation ID"], df_sorted["CPU Usage (%)"],
             "g-o", label="CPU Usage (%)")
    ax1.tick_params(axis="y", labelcolor=color_cpu)
    ax1.tick_params(axis="x", rotation=45)
    ax1.grid(True)

    ax2 = ax1.twinx()
    color_mem = "tab:blue"
    ax2.set_ylabel("Memory RSS (MB)", color=color_mem)
    ax2.plot(df_sorted["Operation ID"], df_sorted["Memory RSS (MB)"],
             "b-s", label="Memory RSS (MB)")
    ax2.tick_params(axis="y", labelcolor=color_mem)

    plt.title(f"{agent_name} CPU and Memory Usage", fontsize=16)
    note = (
        "Note:\n"
        "CPU Usage (%) and Memory RSS (MB) are shown for each request.\n"
        "Helps monitor resource consumption during performance tests."
    )
    plt.text(
        0.5, -0.5, note, ha="center", va="top", fontsize=10, color="black",
        transform=plt.gca().transAxes,
        bbox={"facecolor": "white", "alpha": 0.8, "boxstyle": "round,pad=0.5"},
    )
    plt.tight_layout(rect=(0, 0, 1, 1))
    plt.savefig(output_path)
    plt.close()


def plot_overhead_comparison(summaries: List[AgentSummary],
                             output_path: Path) -> None:
    """Plot a bar chart comparing mean overhead across agents and save it."""

    names = [summary.name for summary in summaries]
    overheads_ms = [summary.mean_overhead * 1000 for summary in summaries]

    plt.figure(figsize=(10, 7))
    bars = plt.bar(names, overheads_ms,
                   color=["#8da0cb", "#66c2a5", "#fc8d62"])
    for bar_item, value in zip(bars, overheads_ms):
        plt.text(bar_item.get_x() + bar_item.get_width() / 2,
                 bar_item.get_height(), f"{value:.2f} ms",
                 ha="center", va="bottom", fontsize=11)

    plt.title("Mean Agent Overhead Comparison", fontsize=16)
    plt.ylabel("Mean Agent Overhead (ms)")
    plt.grid(True, axis="y")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def analyse_agent(name: str, csv_path: Path, results_dir: Path) -> AgentSummary:
    """Analyse one agent's log, write its plots and return a summary."""

    dataframe = pd.read_csv(csv_path)
    dataframe.columns = dataframe.columns.str.strip()
    engine_label = detect_engine_label(dataframe)
    dataframe = compute_overheads(dataframe, engine_label)

    agent_name = AGENT_LABELS.get(name, name)
    mean_overhead = float(dataframe["Agent Overhead (s)"].mean())
    mean_ratio = float(dataframe["Startup/Total Ratio"].mean())

    results_dir.mkdir(parents=True, exist_ok=True)
    plot_agent_overhead(dataframe, mean_overhead, agent_name,
                        results_dir / f"{name}_agent_overhead.png")
    plot_startup_ratio(mean_ratio, agent_name,
                       results_dir / f"{name}_startup_total_ratio_pie.png")
    plot_resource_usage(dataframe, agent_name,
                        results_dir / f"{name}_resource_usage.png")

    return AgentSummary(
        name=agent_name,
        engine_label=engine_label,
        mean_overhead=mean_overhead,
        mean_startup_ratio=mean_ratio,
        mean_cpu=float(dataframe["CPU Usage (%)"].mean()),
        mean_memory=float(dataframe["Memory RSS (MB)"].mean()),
        dataframe=dataframe,
    )


def _agent_report_section(summary: AgentSummary) -> List[str]:
    """Return the Markdown lines describing one agent."""

    name = summary.name
    stem = name.split()[0].lower()
    lines = [f"## {name}\n"]
    lines.append(f"> **Mean Agent Overhead:** "
                 f"`{summary.mean_overhead * 1000:.2f} ms`\n")
    lines.append(f"> **Mean Startup / Total Duration Ratio:** "
                 f"`{summary.mean_startup_ratio:.4f}`\n")
    lines.append(f"> **Mean CPU Usage:** `{summary.mean_cpu:.2f}%`\n")
    lines.append(f"> **Mean Memory RSS:** `{summary.mean_memory:.2f} MB`\n")

    lines.append("\n| Operation ID | Agent Overhead (ms) |")
    lines.append("|--------------|---------------------|")
    for _, row in summary.dataframe.iterrows():
        lines.append(
            f"| {row['Operation ID']} | "
            f"{row['Agent Overhead (s)'] * 1000:.2f} |"
        )

    lines.append(f"\n![{name} Overhead]({stem}_agent_overhead.png)\n")
    lines.append(f"![{name} Startup Ratio]({stem}_startup_total_ratio_pie.png)\n")
    lines.append(f"![{name} Resource Usage]({stem}_resource_usage.png)\n")
    lines.append("---\n")
    return lines


def generate_markdown_report(summaries: List[AgentSummary],
                             output_path: Path) -> None:
    """Write the consolidated Markdown report for all agents."""

    lines = ["# Agent Performance Analysis Report\n"]
    lines.append(
        "Performance measurements for the base, Python and MATLAB agents, "
        "derived from synthetic session logs that reproduce each agent's "
        "`PerformanceMonitor` schema without running the real simulations.\n"
    )

    lines.append("## Summary\n")
    lines.append("| Agent | Mean Overhead (ms) | Startup/Total Ratio | "
                 "Mean CPU (%) | Mean Memory (MB) |")
    lines.append("|-------|--------------------|---------------------|"
                 "--------------|------------------|")
    for summary in summaries:
        lines.append(
            f"| {summary.name} | {summary.mean_overhead * 1000:.2f} | "
            f"{summary.mean_startup_ratio:.4f} | {summary.mean_cpu:.2f} | "
            f"{summary.mean_memory:.2f} |"
        )
    lines.append("\n![Mean Agent Overhead Comparison]"
                 "(agent_overhead_comparison.png)\n")
    lines.append("---\n")

    for summary in summaries:
        lines.extend(_agent_report_section(summary))

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Markdown report written to {output_path}")


def run_analysis(input_dir: Path, results_dir: Path) -> List[AgentSummary]:
    """Analyse every agent log found in ``input_dir`` and write all outputs."""

    summaries: List[AgentSummary] = []
    for name in AGENT_LABELS:
        csv_path = input_dir / f"{name}_agent_performance_metrics.csv"
        if not csv_path.exists():
            print(f"Skipping {name}: {csv_path} not found.")
            continue
        summaries.append(analyse_agent(name, csv_path, results_dir))

    if summaries:
        plot_overhead_comparison(
            summaries, results_dir / "agent_overhead_comparison.png")
        generate_markdown_report(
            summaries, results_dir / "report_performance.md")
    return summaries


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description="Analyse agent performance logs and render plots/report."
    )
    parser.add_argument(
        "-i", "--input-dir", type=Path, default=DEFAULT_INPUT_DIR,
        help=f"Directory with agent session logs (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "-o", "--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
        help=f"Directory for plots and report (default: {DEFAULT_RESULTS_DIR})",
    )
    return parser


def main() -> None:
    """Entry point: analyse all agent logs and write plots and report."""

    args = _build_parser().parse_args()
    summaries = run_analysis(args.input_dir, args.results_dir)
    if not summaries:
        print("No agent logs found. Run generate_performance_data.py first.")


if __name__ == "__main__":
    main()
