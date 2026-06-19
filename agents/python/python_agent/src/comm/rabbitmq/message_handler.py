"""Message handler for processing incoming RabbitMQ messages."""

from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

import yaml
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from base_agent.comm.rabbitmq.interfaces import IRabbitMQMessageHandler
from base_agent.comm.rabbitmq.message_models import (
    BaseMessagePayload,
    BaseSimulationData,
    SimulationOutputs,
)
from base_agent.comm.rabbitmq.message_processing import (
    SimulationMessageContext,
    build_error_response,
    extract_source_from_routing_key,
    parse_message_body,
    validate_message_payload,
)
from base_agent.utils.create_response import create_response
from base_agent.utils.logger import get_logger
from pydantic import BaseModel, ConfigDict, field_validator

from ...core.batch import handle_batch_simulation

logger = get_logger("PYTHON-AGENT")


class PythonSimulationInputs(BaseModel):
    """CLI key/value inputs for the Python agent — no MATLAB streaming fields."""

    model_config = ConfigDict(extra="allow")


class SimulationData(BaseSimulationData):
    """Python-agent simulation data: batch-only with path-safe file validation."""

    allowed_simulation_types: ClassVar[tuple[str, ...]] = ("batch",)
    # Override base inputs to strip MATLAB-specific stream_source from model_dump output
    inputs: PythonSimulationInputs = PythonSimulationInputs()
    timeout: Optional[int] = None

    @field_validator("file", mode="before")
    @classmethod
    def validate_file_not_traversal(cls, value: str) -> str:
        """Reject absolute paths and directory traversal in the file field."""
        p = Path(value)
        # On Windows, Path("/etc/passwd").is_absolute() is False (no drive letter).
        # Check via PurePosixPath to catch Unix-style absolute paths on all platforms.
        if p.is_absolute() or str(value).startswith("/") or str(value).startswith("\\\\"):
            raise ValueError("file must be a relative path")
        if ".." in p.parts:
            raise ValueError("file must not contain '..' path traversal")
        return value


class MessagePayload(BaseMessagePayload):
    """Python-agent top-level message payload model."""

    simulation: SimulationData


class MessageHandler(IRabbitMQMessageHandler):
    """Handler for processing incoming messages from RabbitMQ."""

    def __init__(self, agent_id: str, rabbitmq_manager: Any, config: Optional[Dict]) -> None:
        self.agent_id = agent_id
        self.rabbitmq_manager = rabbitmq_manager
        self.config = config
        self.path_simulation = self.config.get("simulation", {}).get("path", None)
        self.response_templates = self.config.get("response_templates", {})

    def get_agent_id(self) -> str:
        return self.agent_id

    def _send_error_and_nack(
        self,
        ch: BlockingChannel,
        method: Basic.Deliver,
        source: str,
        context: SimulationMessageContext,
        error_payload: Dict[str, Any],
    ) -> None:
        error_response = build_error_response(
            response_builder=create_response,
            context=context,
            error=error_payload,
        )
        try:
            self.rabbitmq_manager.send_result(source, error_response)
        except Exception as send_error:  # pylint: disable=broad-except
            logger.error("Failed to send error response: %s", send_error)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def handle_message(
        self,
        ch: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> None:
        message_id = properties.message_id if properties.message_id else "unknown"
        source = extract_source_from_routing_key(method.routing_key)
        msg_dict: Any = {}

        try:
            try:
                msg_dict = parse_message_body(body, yaml.safe_load, logger)
            except yaml.YAMLError as parsing_error:
                logger.error("YAML parsing error: %s", parsing_error)
                self._send_error_and_nack(
                    ch=ch,
                    method=method,
                    source=source,
                    context=SimulationMessageContext(),
                    error_payload={
                        "message": "YAML parsing error",
                        "details": str(parsing_error),
                        "type": "yaml_parse_error",
                    },
                )
                return

            payload, message_context, validation_error = validate_message_payload(
                msg_dict=msg_dict,
                payload_factory=lambda payload_data: MessagePayload(**payload_data),
                logger=logger,
            )
            if validation_error:
                self._send_error_and_nack(
                    ch=ch,
                    method=method,
                    source=source,
                    context=message_context,
                    error_payload={
                        "message": "Message validation failed",
                        "details": validation_error,
                        "type": "validation_error",
                    },
                )
                return

            # Pass validated data — not the raw dict — to the batch handler
            validated_dict = {"simulation": payload.simulation.model_dump()}
            handle_batch_simulation(
                validated_dict,
                source,
                self.rabbitmq_manager,
                self.path_simulation,
                self.response_templates,
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(
                "Handled batch request %s for file %s",
                message_context.request_id,
                message_context.sim_file,
            )

        except Exception as processing_error:  # pylint: disable=broad-except
            logger.error("Error processing message %s: %s", message_id, processing_error)
            error_response = build_error_response(
                response_builder=create_response,
                context=SimulationMessageContext(),
                error={
                    "message": "Error processing message",
                    "details": str(processing_error),
                    "type": "execution_error",
                },
            )
            try:
                self.rabbitmq_manager.send_result(source, error_response)
            except Exception as send_error:  # pylint: disable=broad-except
                logger.error("Failed to send error response: %s", send_error)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


__all__ = [
    "PythonSimulationInputs",
    "SimulationOutputs",
    "SimulationData",
    "MessagePayload",
    "MessageHandler",
]
