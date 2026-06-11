"""Synthesise performance-metric session logs for simulation-bridge agents.

Every agent in ``simulation-bridge`` records a CSV session log through its
``PerformanceMonitor`` (see ``agents/base/base_agent/utils/performance_monitor``
and the per-agent subclasses). Each row captures one simulation request with
the engine startup duration, simulation duration and total duration, from which
the *agent overhead* is later derived.

Running the real MATLAB or Python simulations is expensive and requires
licensed/third-party software, so this module reproduces the exact CSV schema
emitted by each ``PerformanceMonitor`` and fills it with realistic, seeded
values. The generated logs are then consumed by ``performance_analysis.py`` to
produce plots and a report, mirroring the workflow of
``agents/matlab/performance/performance_analysis.py`` without executing any
external program.

The headline *agent overhead* values follow the figures reported in the
research paper (``.local/research-papers/sections/results.tex``): a mean MATLAB
batch overhead of 2.7 ms and the per-frequency streaming overheads of 2.2, 4.1,
5.6, 4.9, 3.2 and 3.0 ms. The Python and base-agent figures are not published in
the paper and are modelled as plausible, lighter-weight equivalents.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np

DEFAULT_SEED = 42
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "performance_logs"

# Epoch used as the synthetic "wall clock" start for the first request.
_START_EPOCH = 1_700_000_000.0
# Idle gap inserted between two consecutive requests (seconds).
_REQUEST_GAP_S = 0.5
# Fraction of the agent overhead spent before the engine is invoked; the
# remainder is spent after the engine stops (parsing the request vs. building
# and publishing the response).
_PRE_ENGINE_OVERHEAD_FRACTION = 0.4


@dataclass
class Scenario:
    """A single simulation request to synthesise (one CSV row).

    All durations are expressed in milliseconds and converted to seconds when
    written, matching the seconds-based logs produced at runtime.
    """

    operation_id: str
    startup_ms: float
    simulation_ms: float
    overhead_ms: float
    cpu_percent: float
    memory_mb: float


@dataclass
class AgentProfile:
    """Description of one agent's synthetic session log."""

    name: str
    engine_label: str
    scenarios: List[Scenario]

    @property
    def csv_name(self) -> str:
        """File name used for this agent's session log."""

        return f"{self.name}_agent_performance_metrics.csv"


def _matlab_profile() -> AgentProfile:
    """MATLAB agent: heavy engine startup, paper-aligned overheads.

    Batch mode uses the MATLAB Engine API (large startup), while streaming mode
    keeps a persistent TCP connection (small startup) and the streaming
    frequency doubles as the per-step simulation duration.
    """

    streaming = [
        Scenario(f"streaming_{freq}ms", 5.0, float(freq), overhead, 92.0, 25.0)
        for freq, overhead in (
            (10, 2.2),
            (50, 4.1),
            (70, 5.6),
            (100, 4.9),
            (150, 3.2),
            (200, 3.0),
        )
    ]
    batch = Scenario("batch", 3800.0, 1200.0, 2.7, 94.3, 25.3)
    return AgentProfile("matlab", "MATLAB", streaming + [batch])


def _python_profile() -> AgentProfile:
    """Python agent: launches a CLI script as a subprocess (batch only).

    Startup is the interpreter/subprocess launch cost and simulation duration
    scales with the input size. Overheads are lighter than MATLAB's.
    """

    sizes = (
        (10, 0.9),
        (50, 1.1),
        (100, 1.2),
        (500, 1.4),
        (1000, 1.6),
    )
    scenarios = [
        Scenario(f"cli_{rows}rows", 120.0, rows * 0.6, overhead, 38.0, 18.0)
        for rows, overhead in sizes
    ]
    return AgentProfile("python", "Python", scenarios)


def _base_profile() -> AgentProfile:
    """Base agent: shared messaging core with no engine and no simulation.

    The base agent never starts a simulation engine, so its startup and
    simulation durations are zero and the recorded value is the pure
    request-handling overhead at different payload sizes.
    """

    payloads = (
        ("1kb", 0.4),
        ("10kb", 0.5),
        ("100kb", 0.7),
        ("1mb", 0.9),
    )
    scenarios = [
        Scenario(f"payload_{label}", 0.0, 0.0, overhead, 20.0, 15.0)
        for label, overhead in payloads
    ]
    return AgentProfile("base", "ENGINE", scenarios)


def build_profiles() -> Dict[str, AgentProfile]:
    """Return the synthetic profile for every supported agent."""

    return {
        "base": _base_profile(),
        "python": _python_profile(),
        "matlab": _matlab_profile(),
    }


def _jitter(rng: np.random.Generator, mean: float, rel_std: float) -> float:
    """Return ``mean`` perturbed by seeded Gaussian noise, clipped to >= 0."""

    if mean <= 0.0:
        return 0.0
    return float(max(0.0, rng.normal(mean, mean * rel_std)))


def _scenario_row(
    scenario: Scenario, engine_label: str, start_time: float, rng: np.random.Generator
) -> Dict[str, float | str]:
    """Build one CSV row for ``scenario`` starting at ``start_time`` seconds."""

    startup_s = _jitter(rng, scenario.startup_ms, 0.05) / 1000.0
    simulation_s = _jitter(rng, scenario.simulation_ms, 0.05) / 1000.0
    overhead_s = _jitter(rng, scenario.overhead_ms, 0.08) / 1000.0

    pre_engine = overhead_s * _PRE_ENGINE_OVERHEAD_FRACTION
    engine_start = start_time + pre_engine
    engine_stop = engine_start + startup_s + simulation_s
    result_send = engine_stop + (overhead_s - pre_engine)
    total = startup_s + simulation_s + overhead_s

    return {
        "Operation ID": scenario.operation_id,
        "Timestamp": start_time,
        "Request Received Time": start_time,
        f"{engine_label} Start Time": engine_start,
        f"{engine_label} Startup Duration (s)": startup_s,
        "Simulation Duration (s)": simulation_s,
        f"{engine_label} Stop Time": engine_stop,
        "Result Send Time": result_send,
        "CPU Usage (%)": _jitter(rng, scenario.cpu_percent, 0.03),
        "Memory RSS (MB)": _jitter(rng, scenario.memory_mb, 0.03),
        "Total Duration (s)": total,
    }


def _csv_headers(engine_label: str) -> List[str]:
    """Return the CSV header row for the given engine label."""

    return [
        "Operation ID",
        "Timestamp",
        "Request Received Time",
        f"{engine_label} Start Time",
        f"{engine_label} Startup Duration (s)",
        "Simulation Duration (s)",
        f"{engine_label} Stop Time",
        "Result Send Time",
        "CPU Usage (%)",
        "Memory RSS (MB)",
        "Total Duration (s)",
    ]


def generate_log(profile: AgentProfile, output_dir: Path, seed: int) -> Path:
    """Write ``profile``'s synthetic session log and return its path."""

    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / profile.csv_name

    headers = _csv_headers(profile.engine_label)
    next_start = _START_EPOCH
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for scenario in profile.scenarios:
            row = _scenario_row(scenario, profile.engine_label, next_start, rng)
            writer.writerow(row)
            next_start = float(row["Result Send Time"]) + _REQUEST_GAP_S
    return csv_path


def generate_all(output_dir: Path = DEFAULT_OUTPUT_DIR, seed: int = DEFAULT_SEED) -> List[Path]:
    """Generate session logs for every agent and return the written paths."""

    paths = []
    for index, profile in enumerate(build_profiles().values()):
        # Offset the seed per agent so the logs are distinct yet reproducible.
        paths.append(generate_log(profile, output_dir, seed + index))
    return paths


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description="Generate synthetic agent performance session logs."
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for the generated CSV logs (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for reproducible logs (default: {DEFAULT_SEED})",
    )
    return parser


def main() -> None:
    """Entry point: generate all agent session logs."""

    args = _build_parser().parse_args()
    for path in generate_all(args.output_dir, args.seed):
        print(f"Generated {path}")


if __name__ == "__main__":
    main()
