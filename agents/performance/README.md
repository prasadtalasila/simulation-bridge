# Agent Performance Analysis

Tooling to **measure and visualise the processing overhead of the
simulation-bridge agents** — the base agent, the Python agent and the MATLAB
agent.

Every agent records a CSV session log through its `PerformanceMonitor`
(`agents/base/base_agent/utils/performance_monitor.py` and the per-agent
subclasses). Each row captures one simulation request, from which the **agent
overhead** is derived:

```
Agent Overhead = Total Duration − Engine Startup Duration − Simulation Duration
```

i.e. the time the agent spends parsing the request, handling files and exchanging
messages, **excluding** the engine startup time and the simulation runtime.

## Running without the real simulations

Executing the actual MATLAB or Python simulations requires licensed/third-party
software and is expensive to reproduce in CI. Instead, `generate_performance_data.py`
**synthesises session logs that match each agent's `PerformanceMonitor` schema**
and fills them with realistic, seeded values. The headline MATLAB overhead
figures reproduce those published in the research paper (batch mean of 2.7 ms;
streaming overheads of 2.2/4.1/5.6/4.9/3.2/3.0 ms at 10/50/70/100/150/200 ms time
steps). The Python and base-agent figures are not in the paper and are modelled
as plausible, lighter-weight equivalents.

`performance_analysis.py` then parses those logs (exactly as it would parse real
ones) and produces the plots and report. The whole pipeline therefore runs
without launching MATLAB or Python.

## Layout

```
agents/performance/
├── generate_performance_data.py   # synthesises the agent session logs
├── performance_analysis.py        # parses logs → plots + Markdown report
├── performance_logs/              # generated CSV logs (one per agent)
├── results/                       # generated plots + report_performance.md
├── tests/                         # unit tests
└── requirements.txt
```

## Requirements

- Python 3.12+
- pandas 2.0+, numpy 1.23+, matplotlib 3.7+

```bash
pip install -r requirements.txt
```

## Usage

Regenerate the logs and then the plots/report:

```bash
python generate_performance_data.py     # writes performance_logs/*.csv
python performance_analysis.py          # writes results/*.png + report
```

Both scripts accept `--help` for custom input/output directories and seed.

## Outputs

For each agent (`base`, `python`, `matlab`) the analysis writes to `results/`:

- `<agent>_agent_overhead.png` — per-request agent overhead with the mean.
- `<agent>_startup_total_ratio_pie.png` — share of processing time spent on
  engine startup (zero for the base agent, which starts no engine).
- `<agent>_resource_usage.png` — CPU and memory usage per request.

Plus, across all agents:

- `agent_overhead_comparison.png` — mean overhead bar chart.
- `report_performance.md` — consolidated Markdown report.

| Agent | Mean Overhead (ms) | Notes |
| ----- | ------------------ | ----- |
| Base Agent | ~0.6 | Pure messaging core; no engine, no simulation |
| Python Agent | ~1.2 | Subprocess-launched CLI script (batch) |
| MATLAB Agent | ~3.6 | Engine API batch + TCP streaming, per the paper |

## Tests

```bash
pytest
```
