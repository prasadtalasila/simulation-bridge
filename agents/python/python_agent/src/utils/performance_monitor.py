"""Performance monitoring utilities for the Python agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from base_agent.utils.logger import get_logger
from base_agent.utils.performance_monitor import (
    BasePerformanceMonitor,
    PerformanceMetrics as BasePerformanceMetrics,
)

logger = get_logger("PYTHON-AGENT")


@dataclass
class PerformanceMetrics(BasePerformanceMetrics):
    """Python agent compatibility layer for performance metric attribute names."""

    @property
    def python_start_time(self) -> float:
        """Alias for engine_start_time."""
        return self.engine_start_time

    @python_start_time.setter
    def python_start_time(self, value: float) -> None:
        self.engine_start_time = value

    @property
    def python_startup_duration(self) -> float:
        """Alias for engine_startup_duration."""
        return self.engine_startup_duration

    @python_startup_duration.setter
    def python_startup_duration(self, value: float) -> None:
        self.engine_startup_duration = value

    @property
    def python_stop_time(self) -> float:
        """Alias for engine_stop_time."""
        return self.engine_stop_time

    @python_stop_time.setter
    def python_stop_time(self, value: float) -> None:
        self.engine_stop_time = value


class PerformanceMonitor(BasePerformanceMonitor):
    """Python agent performance monitor built on shared base utilities."""

    engine_label = "PYTHON"
    metrics_class = PerformanceMetrics

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config=config, logger=logger)

    def record_python_start(self) -> None:
        """Alias for record_engine_start."""
        self.record_engine_start()

    def record_python_startup_complete(self) -> None:
        """Alias for record_engine_startup_complete."""
        self.record_engine_startup_complete()

    def record_python_stop(self) -> None:
        """Alias for record_engine_stop."""
        self.record_engine_stop()


__all__ = ["PerformanceMetrics", "PerformanceMonitor"]
