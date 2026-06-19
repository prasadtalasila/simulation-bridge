# Base Agent Design

## Purpose

`agents/base` provides the shared runtime foundations that all simulation agents build on: RabbitMQ communication, Pydantic message models, config management, performance monitoring, logging, and standardised response formatting.

It is a **library**, not an executable agent. Consuming agents (MATLAB, Python, Simul8) depend on it via a local Poetry path dependency and extend its base classes for agent-specific behaviour.

## Architectural Style

- **Core style**: shared library of reusable components; no agent-level main loop or entry point.
- **Extension model**: agents subclass `BaseSimulationData`, `BaseConfigManager`, and `BasePerformanceMonitor` to add agent-specific fields, validation, and metrics.
- **Transport**: RabbitMQ via `pika` (blocking connection). The `IMessageBroker` interface allows future brokers.
- **No process control**: errors raise `RuntimeError` or `ConnectionError` — the consuming agent's entrypoint decides whether to exit.

## Main Components

### 1. Communication layer

- **`comm/interfaces.py`** — `IMessageBroker`, `IMessageHandler`
  - `IMessageBroker.connect()` returns `bool` so callers know connection status.
  - `IMessageHandler.handle_message()` processes individual deliveries.

- **`comm/rabbitmq/interfaces.py`** — `IRabbitMQManager`, `IRabbitMQMessageHandler`
  - RabbitMQ-specific extensions of the generic interfaces.

- **`comm/rabbitmq/rabbitmq_manager.py`** — `RabbitMQManager`
  - Connect with exponential-backoff retry, TLS support.
  - Exchange + queue declare/bind, QoS prefetch.
  - `start_consuming()` / `stop_consuming()`, `send_result()`.
  - Raises `RuntimeError` (not `sys.exit`) on channel failure so agents can recover.

- **`comm/connect.py`** — `Connect`
  - Single abstraction consumed by agent shells.
  - Wires broker factory + message handler factory together.
  - `connect()` → `setup()` → `register_message_handler()` → `start_consuming()` lifecycle.
  - `ConnectionError` raised on broker failure; agent entrypoint catches and shuts down.

### 2. Message models

- **`comm/rabbitmq/message_models.py`**
  - `BaseSimulationData` — common fields (`request_id`, `client_id`, `simulator`, `type`, `file`, `inputs`, `outputs`). `allowed_simulation_types` is a `ClassVar` agents override.
  - `SimulationInputs` — extra-allow Pydantic model; includes `stream_source` for MATLAB streaming. Agents that don't use streaming subclass this to omit the field.
  - `SimulationOutputs` — extra-allow Pydantic model for output specs.
  - `BaseMessagePayload` — top-level wrapper (`simulation: BaseSimulationData`).

### 3. Message processing utilities

- **`comm/rabbitmq/message_processing.py`**
  - `parse_message_body(body, yaml_load, logger)` — decodes bytes to dict.
  - `validate_message_payload(msg_dict, payload_factory, logger)` — runs Pydantic validation, returns `(payload, context, error_str)`.
  - `extract_source_from_routing_key(routing_key)` — parses `<source>.<agent_id>` format.
  - `build_error_response(response_builder, context, error)` — formats structured error payload.

### 4. Runtime utilities

- **`utils/agent_runtime.py`**
  - `initialize_agent_runtime(...)` — creates config manager, performance monitor, broker, connect; calls `connect()` + `setup()`.
  - `run_agent_loop(agent_name, comm, logger, stop_func)` — blocking consume with KeyboardInterrupt handling.
  - `shutdown_agent_runtime(agent_name, comm, performance_monitor, logger)` — stops consuming, closes broker, flushes monitor.
  - `send_result_with_monitor(comm, performance_monitor, destination, result)` — sends and records timing.

### 5. Config management

- **`utils/config_loader.py`**
  - `load_config(package_name, config_path, substitute_func)` — loads YAML from file or package template.
  - `substitute_env_vars(config)` — recursively replaces `${VAR}` and `${VAR:default}` using `re.sub`.
  - `default_config_path(package_name)` — resolves template path via `importlib.resources`.

- **`utils/config_manager.py`** — `BaseConfigManager`
  - Template-method config lifecycle: load → validate → merge defaults.
  - `build_common_config(flat)` / `flatten_common_config(nested, defaults)` — convert between flat dict and nested YAML shape.

### 6. Performance monitoring

- **`utils/performance_monitor.py`** — `BasePerformanceMonitor`
  - Singleton **per subclass** via `cls._instance` (not shared across agent types).
  - Records wall-clock + CPU/memory for: engine start, startup complete, simulation complete, result sent.
  - Exports per-operation rows to CSV when `performance.enabled = true`.
  - Subclasses set `engine_label` and `metrics_class`; alias methods (`record_engine_start`, etc.) are re-exposed under agent-specific names.

### 7. Logging

- **`utils/logger.py`**
  - `setup_logger(level, log_file)` — root logger with rotating file + coloured console handlers.
  - `configure_logger(name, level)` — per-module logger configuration.
  - `get_logger(name)` — retrieve a named logger.

### 8. Response formatting

- **`utils/create_response.py`** — `create_response(template_type, sim_file, sim_type, response_templates, **kwargs)`
  - Produces `success` / `error` / `progress` / `streaming` payloads.
  - Template-driven: keys like `include_metadata`, `include_stacktrace`, `timestamp_format` come from the agent's YAML config.
  - Success status is always `"completed"`; error codes are template-driven.

## Extension Pattern

```python
# 1. Message model
class SimulationData(BaseSimulationData):
    allowed_simulation_types: ClassVar[tuple[str, ...]] = ("batch",)

    @field_validator("file", mode="before")
    @classmethod
    def validate_file(cls, v: str) -> str: ...

# 2. Config manager
class ConfigManager(BaseConfigManager):
    def __init__(self, config_path=None):
        super().__init__(package_name="my_agent", ...)

# 3. Performance monitor
class PerformanceMonitor(BasePerformanceMonitor):
    engine_label = "MYAGENT"
    metrics_class = MyMetrics

# 4. Agent shell
runtime = initialize_agent_runtime(
    agent_name="MYAGENT", agent_id=agent_id,
    config_manager_factory=ConfigManager,
    performance_monitor_factory=PerformanceMonitor,
    connect_factory=connect_factory,
    ...
)
run_agent_loop(agent_name="MYAGENT", comm=runtime.comm, ...)
```

## Key Design Decisions

- **`sys.exit` removed**: all fatal errors raise `RuntimeError` or `ConnectionError`. Agents decide whether to terminate.
- **`connect()` returns `bool`**: `Connect.connect()` raises `ConnectionError` if the broker returns `False`, giving callers a typed failure signal.
- **Singleton per subclass**: `BasePerformanceMonitor._instance` is stored on `cls` so MATLAB and Python monitors are independent singletons rather than competing for a single shared instance.
- **`re.sub` for env-var substitution**: replaces all `${VAR}` occurrences in one pass rather than the previous single-`find()`-and-replace approach, correctly handling strings with multiple placeholders.
