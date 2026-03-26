"""Integration tests verifying OpenTelemetry span creation and attributes."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ReadableSpan,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from recipe_mcp_server.observability.tracing import traced


class _InMemoryExporter(SpanExporter):
    """Minimal in-memory span exporter for test assertions."""

    def __init__(self) -> None:
        self.spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 0) -> bool:
        return True


@pytest.fixture(autouse=True)
def span_exporter():
    """Set up an in-memory span exporter for test assertions.

    Resets the global tracer provider for each test to avoid the
    "Overriding of current TracerProvider is not allowed" warning.
    """
    exporter = _InMemoryExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # The OTel SDK does not expose a public reset API for the global
    # TracerProvider.  The opentelemetry.test.globals helper does not
    # exist in our SDK version, so we reset private attributes directly.
    # If the OTel SDK changes these internals, the fixture will fail
    # loudly rather than silently.
    trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace.set_tracer_provider(provider)
    yield exporter
    provider.shutdown()


@pytest.mark.integration
class TestOTelSpans:
    """Tests for OpenTelemetry span instrumentation."""

    async def test_traced_decorator_creates_span(self, span_exporter: _InMemoryExporter) -> None:
        """The @traced decorator should create a span with the function name."""

        @traced()
        async def my_service_call() -> str:
            return "ok"

        result = await my_service_call()
        assert result == "ok"

        assert len(span_exporter.spans) == 1
        span = span_exporter.spans[0]
        assert "my_service_call" in span.name

    async def test_traced_decorator_custom_span_name(
        self, span_exporter: _InMemoryExporter
    ) -> None:
        """The @traced decorator should use a custom span name when provided."""

        @traced(span_name="custom.operation")
        async def do_work() -> int:
            return 42

        result = await do_work()
        assert result == 42

        assert len(span_exporter.spans) == 1
        assert span_exporter.spans[0].name == "custom.operation"

    async def test_traced_decorator_records_exception(
        self, span_exporter: _InMemoryExporter
    ) -> None:
        """The @traced decorator should record exceptions on the span."""

        @traced()
        async def failing_call() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await failing_call()

        assert len(span_exporter.spans) == 1
        span = span_exporter.spans[0]
        assert span.status.status_code == trace.StatusCode.ERROR
        events = span.events
        assert any(e.name == "exception" for e in events)

    async def test_traced_decorator_with_attributes(self, span_exporter: _InMemoryExporter) -> None:
        """The @traced decorator should set custom attributes on the span."""

        @traced(attributes={"service": "recipe", "operation": "search"})
        async def search_op() -> str:
            return "results"

        await search_op()

        assert len(span_exporter.spans) == 1
        attrs = dict(span_exporter.spans[0].attributes or {})
        assert attrs["service"] == "recipe"
        assert attrs["operation"] == "search"

    async def test_no_spans_without_provider(self) -> None:
        """When no TracerProvider is configured, spans are no-ops."""
        original = trace.get_tracer_provider()
        try:
            trace.set_tracer_provider(trace.NoOpTracerProvider())

            @traced()
            async def noop_call() -> str:
                return "no spans"

            result = await noop_call()
            assert result == "no spans"
        finally:
            trace.set_tracer_provider(original)
