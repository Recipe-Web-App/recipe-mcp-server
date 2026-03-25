"""OpenTelemetry tracing configuration with OTLP/gRPC export to Jaeger.

Provides :func:`init_tracing` for SDK bootstrap, :func:`shutdown_tracing` for
graceful teardown, and the :func:`traced` decorator for adding custom spans to
async service methods.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])

_provider: TracerProvider | None = None


def init_tracing(
    service_name: str,
    service_version: str,
    otlp_endpoint: str,
) -> TracerProvider | None:
    """Initialise the OTel SDK with an OTLP/gRPC exporter.

    Returns the :class:`TracerProvider` on success, or ``None`` when the
    exporter cannot be created.  In either case the application continues
    to function — spans are simply no-ops when there is no provider.
    """
    global _provider

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
            }
        )
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider = provider
        logger.info(
            "tracing_initialised",
            endpoint=otlp_endpoint,
            service=service_name,
        )
        return provider
    except Exception:
        logger.warning("tracing_init_failed", exc_info=True)
        return None


async def shutdown_tracing() -> None:
    """Flush pending spans and shut down the :class:`TracerProvider`."""
    global _provider

    if _provider is not None:
        _provider.force_flush()
        _provider.shutdown()
        _provider = None
        logger.info("tracing_shutdown")


def traced(
    span_name: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps an async function in an OpenTelemetry span.

    If *span_name* is omitted the span is named after the function's
    ``module.qualname``.  Exceptions are automatically recorded on the
    span and the status set to ``ERROR``.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer("recipe_mcp_server")
            name = span_name or f"{func.__module__}.{func.__qualname__}"
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator
