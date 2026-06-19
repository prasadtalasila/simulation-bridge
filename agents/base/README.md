# Base Agent

Shared foundation package for all simulation agents (MATLAB, Python, Simul8, and future agents).

This package is consumed as a local Poetry path dependency and is **not** published to PyPI.

## Package Structure

```
base_agent/
├── comm/
│   ├── connect.py            # Broker abstraction (Connect)
│   ├── interfaces.py         # IMessageBroker, IMessageHandler
│   ├── main_helpers.py       # Shared main/startup helpers
│   └── rabbitmq/
│       ├── interfaces.py         # IRabbitMQManager, IRabbitMQMessageHandler
│       ├── message_models.py     # BaseMessagePayload, BaseSimulationData, SimulationInputs/Outputs
│       ├── message_processing.py # parse_message_body, validate_message_payload, build_error_response
│       └── rabbitmq_manager.py   # RabbitMQManager — connect/retry, exchange setup, consume loop
├── interfaces/
│   ├── agent.py              # IAgent base interface
│   └── config_manager.py     # IConfigManager interface
└── utils/
    ├── agent_runtime.py      # initialize_agent_runtime, run_agent_loop, shutdown_agent_runtime
    ├── batch_helpers.py      # Shared batch processing helpers
    ├── config_loader.py      # load_config, substitute_env_vars, default_config_path
    ├── config_manager.py     # BaseConfigManager, build_common_config, flatten_common_config
    ├── create_response.py    # create_response — standardised success/error/progress payloads
    ├── logger.py             # setup_logger, configure_logger, get_logger
    └── performance_monitor.py# BasePerformanceMonitor (singleton per subclass)
```

## Using in an Agent

Add to the consuming agent's `pyproject.toml`:

```toml
[tool.poetry.dependencies]
base-agent = { path = "../base", develop = true }
```

Then install:

```bash
cd agents/<your-agent>
poetry install --with dev
```

Subclass the base types to extend them for your agent:

```python
from base_agent.comm.rabbitmq.message_models import BaseSimulationData
from base_agent.utils.config_manager import BaseConfigManager
from base_agent.utils.performance_monitor import BasePerformanceMonitor
from base_agent.utils.agent_runtime import initialize_agent_runtime, run_agent_loop

class SimulationData(BaseSimulationData):
    allowed_simulation_types: ClassVar[tuple[str, ...]] = ("batch",)

class ConfigManager(BaseConfigManager): ...
class PerformanceMonitor(BasePerformanceMonitor):
    engine_label = "MYAGENT"
```

## Development Commands

All commands run from `agents/base/`:

```bash
# Install all dependencies (including dev)
poetry install --with dev

# Run the test suite
poetry run pytest -q

# Lint (10/10 target)
poetry run pylint base_agent

# Build wheel and sdist
poetry build
```

## Tests

Unit tests live in `test/unit/`. Coverage includes: config loader, config manager, performance monitor, logger, create_response, RabbitMQ manager, connect, agent runtime, message models, and message processing.

```bash
poetry run pytest -q          # all tests
poetry run pytest test/unit/  # unit tests only
```
