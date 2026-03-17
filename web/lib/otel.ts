/**
 * Browser-side OpenTelemetry initialization.
 *
 * Uses require() inside the function body to avoid Next.js/Webpack ESM→CJS
 * interop issues. Uses the v2 @opentelemetry/resources API (resourceFromAttributes
 * instead of the removed Resource class constructor).
 */

let initialized = false;

export function initOtel() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  /* eslint-disable @typescript-eslint/no-var-requires */
  const { WebTracerProvider, BatchSpanProcessor } = require('@opentelemetry/sdk-trace-web');
  const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');
  const { resourceFromAttributes, defaultResource } = require('@opentelemetry/resources');
  const { registerInstrumentations } = require('@opentelemetry/instrumentation');
  const { FetchInstrumentation } = require('@opentelemetry/instrumentation-fetch');
  const { DocumentLoadInstrumentation } = require('@opentelemetry/instrumentation-document-load');
  /* eslint-enable @typescript-eslint/no-var-requires */

  const resource = defaultResource().merge(resourceFromAttributes({
    'service.name': 'ridgeline-web',
    'service.version': '0.1.0',
    'deployment.environment': 'dev',
    'service.namespace': 'ridgeline',
  }));

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
        propagateTraceHeaderCorsUrls: [/localhost:8000/],
        clearTimingResources: true,
      }),
      new DocumentLoadInstrumentation(),
    ],
  });
}
