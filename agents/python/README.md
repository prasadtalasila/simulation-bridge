# Python Agent

The Python Agent executes generic Python scripts and programs via CLI parameters received in batch simulation requests from RabbitMQ.

## What it does

- Receives a batch simulation message over RabbitMQ
- Validates `simulation.file` is a safe relative path within the configured simulation directory
- Maps `simulation.inputs` key/value pairs to `--key value` CLI arguments
- Executes the target script as a subprocess using the system Python interpreter
- Captures stdout (expected to be JSON), stderr, and exit code
- Extracts the requested output keys from parsed stdout
- Forwards the result or a structured error response back to the caller

## Security

- **Path containment (layer 1)**: `SimulationData.file` Pydantic validator rejects absolute paths and any path segment containing `..` before the request reaches execution.
- **Path containment (layer 2)**: `_validate_simulation_data` resolves both the base directory and the candidate path with `Path.resolve()` and asserts `candidate.is_relative_to(base)`, preventing symlink and other OS-level traversal.
- **Timeout clamping**: requested timeouts are clamped to `MAX_TIMEOUT = 3600 s` server-side.
- **Credential safety**: RabbitMQ password is redacted before debug logging.
- **TLS by default**: the config template defaults to port 5671 and `tls: true`; credentials are injected from environment variables (`RABBITMQ_USERNAME`, `RABBITMQ_PASSWORD`).

## Quick Start

```bash
cd agents/python

# Install dependencies
poetry install

# Generate a config file in the current directory
poetry run python-agent --generate-config

# Generate a minimal project scaffold (config + example script + client)
poetry run python-agent --generate-project

# Run with an explicit config
poetry run python-agent --config-file config.yaml
```

Generated scaffold:
- `scripts/example_cli_program.py` — sample CLI program
- `client/use_python_agent_batch.py` — simple RabbitMQ publisher
- `client/simulation.yaml` — example simulation request payload

## Configuration

Copy and edit the template:

```bash
cp python_agent/config/config.yaml.template config.yaml
```

Key settings:

```yaml
rabbitmq:
  host: localhost
  port: 5671                          # TLS port
  username: ${RABBITMQ_USERNAME:guest}
  password: ${RABBITMQ_PASSWORD:guest}
  tls: true

simulation:
  path: ${SIMULATION_PATH:.}          # Base directory for scripts
```

`${VAR:default}` placeholders are substituted from environment variables at startup.

## Simulation Request Format

```yaml
simulation:
  request_id: "req-1"
  client_id: "client-1"
  simulator: "python"
  type: "batch"
  file: "scripts/my_script.py"       # Relative path within simulation.path
  inputs:
    value: "42"
    mode: "fast"
  outputs:
    - result
    - status
  timeout: 30                        # Optional; clamped to 3600 s
```

`inputs` become `--value 42 --mode fast` CLI arguments. The script is expected to print a JSON object to stdout; `outputs` selects which keys to include in the response.

## Development Commands

All commands run from `agents/python/`:

```bash
# Install all dependencies (including dev)
poetry install --with dev

# Run test suite
poetry run pytest -q

# Lint (min score 9.0)
poetry run pylint python_agent --fail-under=9

# Build wheel and sdist
poetry build

# Format check (non-blocking)
poetry run autopep8 --recursive --diff python_agent
```

## Tests

Unit tests live in `python_agent/tests/unit/`:

- `test_batch.py` — `handle_batch_simulation` happy path
- `test_python_simulator.py` — CLI execution, output extraction, non-zero exit
- `test_path_security.py` — path containment and Pydantic model validation; regression test for `--stream_source` injection

## Dependencies

- `base-agent` (local path dependency `../base`) — all shared communication, config, logging, and runtime utilities
- `pika` — RabbitMQ client
- `pydantic` — message model validation
- `click` — CLI entry point
- `pyyaml` — YAML config parsing
