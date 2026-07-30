"""Observability — tracing spans, metrics collection, and alert management."""

import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("brompt.observability")


@dataclass
class Span:
    """A single tracing span within an execution trace."""

    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None

    def finish(self, status: str = "ok", error: str | None = None):
        self.end_time = time.time()
        self.status = status
        self.error = error

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "status": self.status,
            "error": self.error,
        }


class Tracer:
    """Simple distributed tracer."""

    def __init__(self):
        self._spans: list[Span] = []

    def start_span(self, name: str, trace_id: str | None = None, parent_span_id: str | None = None, attributes: dict | None = None) -> Span:  # noqa: E501
        span = Span(
            name=name,
            trace_id=trace_id or uuid.uuid4().hex,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        self._spans.append(span)
        return span

    def get_spans(self, trace_id: str | None = None) -> list[Span]:
        if trace_id:
            return [s for s in self._spans if s.trace_id == trace_id]
        return list(self._spans)

    def clear(self):
        self._spans.clear()


# --- Metrics -----------------------------------------------------------------

@dataclass
class Counter:
    _value: int = 0

    def inc(self, amount: int = 1):
        self._value += amount

    def reset(self):
        self._value = 0

    @property
    def value(self) -> int:
        return self._value


@dataclass
class Gauge:
    _value: float = 0.0

    def set(self, value: float):
        self._value = value

    def inc(self, amount: float = 1.0):
        self._value += amount

    def dec(self, amount: float = 1.0):
        self._value -= amount

    @property
    def value(self) -> float:
        return self._value


@dataclass
class Histogram:
    _values: list[float] = field(default_factory=list)

    def observe(self, value: float):
        self._values.append(value)

    @property
    def count(self) -> int:
        return len(self._values)

    @property
    def sum(self) -> float:
        return sum(self._values)

    @property
    def avg(self) -> float:
        return self.sum / self.count if self.count else 0.0

    @property
    def min(self) -> float:
        return min(self._values) if self._values else 0.0

    @property
    def max(self) -> float:
        return max(self._values) if self._values else 0.0


class MetricsCollector:
    """Collects application metrics with thread-safe operations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, Counter] = defaultdict(Counter)
        self._gauges: dict[str, Gauge] = defaultdict(Gauge)
        self._histograms: dict[str, Histogram] = defaultdict(Histogram)

    def counter(self, name: str) -> Counter:
        with self._lock:
            return self._counters[name]

    def gauge(self, name: str) -> Gauge:
        with self._lock:
            return self._gauges[name]

    def histogram(self, name: str) -> Histogram:
        with self._lock:
            return self._histograms[name]

    def inc(self, name: str, amount: int = 1):
        with self._lock:
            self._counters[name].inc(amount)

    def gauge_set(self, name: str, value: float):
        with self._lock:
            self._gauges[name].set(value)

    def observe(self, name: str, value: float):
        with self._lock:
            self._histograms[name].observe(value)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": {k: v.value for k, v in self._counters.items()},
                "gauges": {k: v.value for k, v in self._gauges.items()},
                "histograms": {
                    k: {"count": v.count, "sum": v.sum, "avg": v.avg, "min": v.min, "max": v.max}
                    for k, v in self._histograms.items()
                },
            }

    def reset(self):
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def export_prometheus(self) -> str:
        lines: list[str] = []
        snap = self.snapshot()
        for name, value in snap["counters"].items():
            safe = name.replace("-", "_").replace(".", "_")
            lines.append(f"# HELP {safe} Counter metric")
            lines.append(f"# TYPE {safe} counter")
            lines.append(f"{safe} {value}")
        for name, value in snap["gauges"].items():
            safe = name.replace("-", "_").replace(".", "_")
            lines.append(f"# HELP {safe} Gauge metric")
            lines.append(f"# TYPE {safe} gauge")
            lines.append(f"{safe} {value}")
        for name, h in snap["histograms"].items():
            safe = name.replace("-", "_").replace(".", "_")
            lines.append(f"# HELP {safe} Histogram metric")
            lines.append(f"# TYPE {safe} histogram")
            lines.append(f'{safe}_count {h["count"]}')
            lines.append(f'{safe}_sum {h["sum"]}')
        return "\n".join(lines)


# --- Alerts ------------------------------------------------------------------

@dataclass
class AlertRule:
    name: str
    condition: Callable[[dict], bool]
    message: str
    severity: str = "warning"
    enabled: bool = True


@dataclass
class Alert:
    rule_name: str
    message: str
    severity: str
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False


class AlertManager:
    """Evaluates alert rules and manages alert lifecycle."""

    def __init__(self):
        self._rules: list[AlertRule] = []
        self._alerts: list[Alert] = []
        self._handlers: list[Callable[[Alert], None]] = []

    def add_rule(self, rule: AlertRule):
        self._rules.append(rule)

    def remove_rule(self, name: str):
        self._rules = [r for r in self._rules if r.name != name]

    def add_handler(self, handler: Callable[[Alert], None]):
        self._handlers.append(handler)

    def evaluate(self, context: dict) -> list[Alert]:
        new_alerts: list[Alert] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            try:
                if rule.condition(context):
                    alert = Alert(rule_name=rule.name, message=rule.message, severity=rule.severity)
                    self._alerts.append(alert)
                    new_alerts.append(alert)
                    for handler in self._handlers:
                        try:
                            handler(alert)
                        except Exception as exc:
                            logger.error("Alert handler failed: %s", exc)
            except Exception as exc:
                logger.warning("Alert rule '%s' evaluation error: %s", rule.name, exc)
        return new_alerts

    def get_alerts(self, unresolved_only: bool = False) -> list[Alert]:
        if unresolved_only:
            return [a for a in self._alerts if not a.resolved]
        return list(self._alerts)

    def resolve(self, alert: Alert):
        alert.resolved = True

    def resolve_by_rule(self, rule_name: str):
        for alert in self._alerts:
            if alert.rule_name == rule_name and not alert.resolved:
                alert.resolved = True

    def clear(self):
        self._alerts.clear()


# --- Global instances --------------------------------------------------------

tracer = Tracer()
metrics = MetricsCollector()
alert_manager = AlertManager()
