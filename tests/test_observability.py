"""Tests for the observability module: tracing, metrics, alerts."""


from brompt.observability import (
    Alert,
    AlertManager,
    AlertRule,
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    Span,
    Tracer,
)


class TestSpan:
    def test_finish_sets_duration(self):
        span = Span(name="llm_call", trace_id="t1")
        assert span.duration_ms == 0.0
        span.finish()
        assert span.end_time is not None
        assert span.duration_ms >= 0.0
        assert span.status == "ok"

    def test_finish_with_error(self):
        span = Span(name="llm_call", trace_id="t1")
        span.finish(status="error", error="timeout")
        assert span.status == "error"
        assert span.error == "timeout"

    def test_to_dict(self):
        span = Span(name="x", trace_id="t", attributes={"model": "gpt-4o"})
        d = span.to_dict()
        assert d["name"] == "x"
        assert d["trace_id"] == "t"
        assert d["attributes"] == {"model": "gpt-4o"}
        assert "span_id" in d


class TestTracer:
    def test_start_span_and_filter(self):
        t = Tracer()
        s1 = t.start_span("a", trace_id="trace-1")
        t.start_span("b", trace_id="trace-2")
        assert len(t.get_spans()) == 2
        assert t.get_spans("trace-1") == [s1]
        t.clear()
        assert t.get_spans() == []

    def test_parent_child(self):
        t = Tracer()
        parent = t.start_span("root", trace_id="t")
        child = t.start_span("child", trace_id="t", parent_span_id=parent.span_id)
        assert child.parent_span_id == parent.span_id


class TestMetricTypes:
    def test_counter(self):
        c = Counter()
        c.inc()
        c.inc(5)
        assert c.value == 6
        c.reset()
        assert c.value == 0

    def test_gauge(self):
        g = Gauge()
        g.set(10.0)
        g.inc(2.0)
        g.dec(1.0)
        assert g.value == 11.0

    def test_histogram(self):
        h = Histogram()
        h.observe(1.0)
        h.observe(3.0)
        assert h.count == 2
        assert h.sum == 4.0
        assert h.avg == 2.0
        assert h.min == 1.0
        assert h.max == 3.0


class TestMetricsCollector:
    def test_collect_and_snapshot(self):
        m = MetricsCollector()
        m.inc("api_calls")
        m.inc("api_calls", 4)
        m.gauge_set("workers", 3)
        m.observe("latency_ms", 100.0)
        m.observe("latency_ms", 300.0)
        snap = m.snapshot()
        assert snap["counters"]["api_calls"] == 5
        assert snap["gauges"]["workers"] == 3
        assert snap["histograms"]["latency_ms"]["avg"] == 200.0

    def test_export_prometheus(self):
        m = MetricsCollector()
        m.inc("api-calls")
        m.gauge_set("workers", 3)
        m.observe("latency_ms", 10.0)
        out = m.export_prometheus()
        assert "# TYPE api_calls counter" in out
        assert "api_calls 1" in out
        assert "# TYPE workers gauge" in out
        assert "latency_ms_count 1" in out

    def test_reset(self):
        m = MetricsCollector()
        m.inc("api_calls")
        m.reset()
        assert m.snapshot()["counters"] == {}


class TestAlertManager:
    def test_evaluate_fires_and_handlers(self):
        fired = []
        am = AlertManager()
        am.add_rule(AlertRule(
            name="high_errors",
            condition=lambda ctx: ctx.get("errors", 0) > 10,
            message="Too many errors",
            severity="critical",
        ))
        am.add_handler(lambda alert: fired.append(alert.rule_name))
        new = am.evaluate({"errors": 15})
        assert len(new) == 1
        assert new[0].rule_name == "high_errors"
        assert new[0].severity == "critical"
        assert fired == ["high_errors"]

    def test_rule_not_fired_when_condition_false(self):
        am = AlertManager()
        am.add_rule(AlertRule(
            name="high_errors",
            condition=lambda ctx: ctx.get("errors", 0) > 10,
            message="Too many errors",
        ))
        assert am.evaluate({"errors": 1}) == []

    def test_disabled_rule_skipped(self):
        am = AlertManager()
        am.add_rule(AlertRule(
            name="off", condition=lambda ctx: True, message="x", enabled=False,
        ))
        assert am.evaluate({}) == []

    def test_get_alerts_and_resolve(self):
        am = AlertManager()
        alert = Alert(rule_name="r", message="m", severity="warning")
        am._alerts.append(alert)
        assert len(am.get_alerts()) == 1
        am.resolve(alert)
        assert am.get_alerts(unresolved_only=True) == []
        am.clear()
        assert am.get_alerts() == []

    def test_remove_rule(self):
        am = AlertManager()
        am.add_rule(AlertRule(name="a", condition=lambda c: True, message="m"))
        am.remove_rule("a")
        assert am._rules == []
