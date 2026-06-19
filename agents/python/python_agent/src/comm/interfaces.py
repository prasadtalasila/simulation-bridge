"""Backward-compatible Python agent comm interface imports backed by base_agent."""

from base_agent.comm.interfaces import IMessageBroker, IMessageHandler

__all__ = ["IMessageBroker", "IMessageHandler"]
