"""Security tests asserting path traversal and absolute paths are rejected."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from python_agent.src.core.batch import _validate_simulation_data
from python_agent.src.comm.rabbitmq.message_handler import MessagePayload, SimulationData
from python_agent.src.core.python_simulator import PythonSimulator


class TestPathContainmentInValidator:
    def test_absolute_path_raises(self, tmp_path: Path):
        data = {"file": "/etc/passwd"}
        with pytest.raises(ValueError, match="escapes base directory"):
            _validate_simulation_data(data, str(tmp_path))

    def test_dotdot_traversal_raises(self, tmp_path: Path):
        data = {"file": "../outside.py"}
        with pytest.raises(ValueError, match="escapes base directory"):
            _validate_simulation_data(data, str(tmp_path))

    def test_nested_dotdot_traversal_raises(self, tmp_path: Path):
        data = {"file": "subdir/../../outside.py"}
        with pytest.raises(ValueError, match="escapes base directory"):
            _validate_simulation_data(data, str(tmp_path))

    def test_valid_relative_path_accepted(self, tmp_path: Path):
        script = tmp_path / "ok.py"
        script.write_text("print('ok')\n", encoding="utf-8")
        result = _validate_simulation_data({"file": "ok.py"}, str(tmp_path))
        assert result == script.resolve()

    def test_missing_file_raises_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            _validate_simulation_data({"file": "missing.py"}, str(tmp_path))


class TestSimulationDataModelValidator:
    def test_absolute_path_rejected_by_model(self):
        with pytest.raises(Exception):
            SimulationData(
                request_id="r1",
                client_id="c1",
                simulator="python",
                type="batch",
                file="/etc/passwd",
                inputs={},
            )

    def test_dotdot_rejected_by_model(self):
        with pytest.raises(Exception):
            SimulationData(
                request_id="r1",
                client_id="c1",
                simulator="python",
                type="batch",
                file="../traversal.py",
                inputs={},
            )

    def test_valid_file_accepted_by_model(self):
        data = SimulationData(
            request_id="r1",
            client_id="c1",
            simulator="python",
            type="batch",
            file="scripts/run.py",
            inputs={},
        )
        assert data.file == "scripts/run.py"


class TestStreamSourceNotInjected:
    """Regression: model_dump must not emit stream_source into CLI args."""

    def test_no_stream_source_in_inputs_dump(self):
        payload = MessagePayload(
            **{
                "simulation": {
                    "request_id": "r",
                    "client_id": "c",
                    "simulator": "python",
                    "type": "batch",
                    "file": "ok.py",
                    "inputs": {"value": "42"},
                }
            }
        )
        inputs_dict = payload.simulation.model_dump()["inputs"]
        assert "stream_source" not in inputs_dict

    def test_no_stream_source_flag_in_command(self):
        payload = MessagePayload(
            **{
                "simulation": {
                    "request_id": "r",
                    "client_id": "c",
                    "simulator": "python",
                    "type": "batch",
                    "file": "ok.py",
                    "inputs": {"value": "42"},
                }
            }
        )
        inputs_dict = payload.simulation.model_dump()["inputs"]
        cmd = PythonSimulator()._build_command(Path("ok.py"), inputs_dict)
        assert "--stream_source" not in cmd

    def test_timeout_passes_through_model_dump(self):
        payload = MessagePayload(
            **{
                "simulation": {
                    "request_id": "r",
                    "client_id": "c",
                    "simulator": "python",
                    "type": "batch",
                    "file": "ok.py",
                    "timeout": 30,
                }
            }
        )
        assert payload.simulation.model_dump()["timeout"] == 30
