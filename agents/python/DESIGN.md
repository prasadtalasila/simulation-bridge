# Python Agent Design

## Purpose

`agents/python` provides a RabbitMQ-connected execution agent that receives batch simulation requests from the bridge, executes generic Python scripts/programs via CLI arguments, and publishes structured results back to `ex.sim.result`.

Supported modes:

- `batch` only

## Architectural Style

- **Core style**: message-driven worker, batch-only. All shared communication, config, monitoring, and response-formatting concerns are delegated to `base_agent`.
- **Transport**: RabbitMQ (via `base_agent.comm`).
- **Execution backend**: Python subprocess (`sys.executable`) with CLI argument mapping.
- **Security-first path handling**: two-layer path containment (Pydantic + `Path.resolve()`) to prevent directory traversal before any file is opened.

## Main Components

### 1. Entry point and bootstrap

- `python_agent/src/main.py`
  - CLI: `--generate-config`, `--generate-project`, `--config-file`.
  - Initializes logger and `PythonAgent`; wraps startup in `ConnectionError`/`Exception` handlers.
  - Redacts RabbitMQ password before debug logging.

### 2. Agent shell

- `PythonAgent` (`src/core/agent.py`)
  - Uses `initialize_agent_runtime` from `base_agent` to wire config, broker, connect, and monitor in one call.
  - `start()` → `run_agent_loop`; `stop()` → `shutdown_agent_runtime`; `send_result()` → `send_result_with_monitor`.
  - `ConnectionError` from broker initialization propagates up to `main.py` error handler.

### 3. Communication layer

- `Connect`, `RabbitMQManager` — fully delegated to `base_agent.comm`; re-exported from `src/comm/` shims for backward compatibility.
- `MessageHandler` (`src/comm/rabbitmq/message_handler.py`)
  - Parses YAML payload, validates against `MessagePayload` (Pydantic).
  - On success: passes `payload.simulation.model_dump()` (validated data, not raw dict) to `handle_batch_simulation`.
  - On failure: sends structured error response and nacks the delivery.

### 4. Message validation

- `SimulationData` (`src/comm/rabbitmq/message_handler.py`)
  - Extends `BaseSimulationData` with:
    - `allowed_simulation_types = ("batch",)` — rejects streaming/interactive at validation time.
    - `inputs: PythonSimulationInputs` — overrides base `SimulationInputs` to omit `stream_source`, preventing the MATLAB streaming field from being serialised into CLI arguments.
    - `timeout: Optional[int] = None` — survives `model_dump()` so `handle_batch_simulation` can clamp it.
    - `validate_file_not_traversal` field validator — rejects absolute paths and `..` path segments before execution.
- `PythonSimulationInputs` — plain extra-allow Pydantic model with no `stream_source` field.

### 5. Batch handler

- `handle_batch_simulation` (`src/core/batch.py`)
  - `data` extraction and `bridge_meta`/`request_id` capture happen **before** the `try` block so error responses always carry correct correlation identifiers.
  - Calls `_validate_simulation_data` (layer 2 containment check).
  - Clamps `timeout` to `MAX_TIMEOUT = 3600 s`.
  - Sends optional progress frame, runs simulator, sends success response with `execution_result["outputs"]` (not the raw full result dict).
  - On exception: calls `_handle_error` with the real `bridge_meta` and `request_id`.

### 6. Execution

- `PythonSimulator` (`src/core/python_simulator.py`)
  - `run(script_path, inputs, outputs)` — builds command, runs `subprocess.run`, captures stdout/stderr/exit code.
  - `_build_command(script_path, inputs)` — maps `{key: value}` to `--key value` CLI args.
  - Non-zero exit raises `PythonSimulationError`.
  - Stdout is parsed as JSON; `outputs` list selects which keys to return.
  - `get_metadata()` returns execution time, memory usage, Python version.

### 7. Path validation

- `_validate_simulation_data(data, path_simulation)` (`src/core/batch.py`)
  - Resolves `base = Path(path_simulation).resolve()`.
  - Resolves `candidate = (base / sim_file).resolve()`.
  - Asserts `candidate.is_relative_to(base)` — handles symlinks, OS normalisation, and `..` sequences that survive the Pydantic validator.
  - Returns a `Path` object; the simulator receives this resolved path directly (no second join with untrusted input).

### 8. Config management

- `ConfigManager` (`src/utils/config_manager.py`)
  - Extends `BaseConfigManager`.
  - Delegates load/validate/default lifecycle to base.
  - `Config.to_dict()` / `from_dict()` use `build_common_config` / `flatten_common_config` from `base_agent`.
  - Default `rabbitmq_tls = True`.

### 9. Performance monitoring

- `PerformanceMonitor` (`src/utils/performance_monitor.py`)
  - Extends `BasePerformanceMonitor` with `engine_label = "PYTHON"`.
  - Alias methods: `record_python_start`, `record_python_startup_complete`, `record_python_stop`.

## Security Design

| Layer | Location | Mechanism |
|-------|----------|-----------|
| 1 — model validation | `SimulationData.validate_file_not_traversal` | Rejects absolute paths and `..` parts at parse time |
| 2 — path containment | `_validate_simulation_data` in `batch.py` | `Path.resolve()` + `is_relative_to()` |
| Timeout cap | `batch.py` | `min(requested, MAX_TIMEOUT)` server-side |
| Credential safety | `main.py` | Password replaced with `"***"` before debug log |
| TLS default | `config.yaml.template` | Port 5671, `tls: true` out of the box |
| Validated data propagation | `message_handler.py` | `model_dump()` of validated payload sent downstream, not raw dict |

## Key Design Decisions

- **`PythonSimulationInputs` overrides `SimulationInputs`**: `BaseSimulationData.inputs` is typed as `SimulationInputs`, which carries `stream_source: str | None = None`. Pydantic v2 `model_dump()` emits this field even when `None`, causing `--stream_source None` to be injected into every command. Overriding with `PythonSimulationInputs` (no `stream_source` field) eliminates the injection.
- **Correlation before try**: `bridge_meta` and `request_id` are extracted before the `try/except` block so that any error — including an immediate `ValueError` from missing `file` — generates a correlated error response rather than `"unknown"` placeholders.
- **Returns extracted outputs, not raw result**: `create_response` receives `execution_result.get("outputs", {})` rather than the full dict (`stdout`, `stderr`, `command`, `exit_code`), matching the bridge's expectation of a clean simulation-output payload.
- **All shared code in `base_agent`**: communication, config management, logging, performance monitoring, and response formatting are not duplicated — the Python agent re-exports or subclasses everything from `base_agent`.
