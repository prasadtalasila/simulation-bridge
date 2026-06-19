"""Backward-compatible Python agent RabbitMQ interface imports backed by base_agent."""

from base_agent.comm.rabbitmq.interfaces import IRabbitMQManager, IRabbitMQMessageHandler

__all__ = ["IRabbitMQManager", "IRabbitMQMessageHandler"]
