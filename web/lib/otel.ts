/**
 * Browser-side OpenTelemetry initialization.
 *
 * Instruments fetch calls and document load, then exports spans to the local
 * OTel collector (http://localhost:4318) which forwards them to Elastic Cloud.
 * This creates distributed traces that stitch browser actions to backend spans.
 *
 * Call initOtel() once from a client component — it is safe to call multiple
 * times (subsequent calls are no-ops).
 */

import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-web';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

let initialized = false;

export function initOtel() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  const resource = new Resource({
    [ATTR_SERVICE_NAME]: 'ridgeline-web',
    [ATTR_SERVICE_VERSION]: '0.1.0',
    'deployment.environment': 'dev',
    'service.namespace': 'ridgeline',
  });

  const exporter = new OTLPTraceExporter({
    url: 'http://localhost:4318/v1/traces',
  });

  const provider = new WebTracerProvider({ resource });
  provider.addSpanProcessor(new BatchSpanProcessor(exporter));
  provider.register();

  registerInstrumentations({
    tracerProvider: provider,
    instrumentations: [
      new FetchInstrumentation({
        // Propagate trace context to the API so backend spans are children
        propagateTraceHeaderCorsUrls: [/localhost:8000/],
        clearTimingResources: true,
      }),
      new DocumentLoadInstrumentation(),
    ],
  });
}
