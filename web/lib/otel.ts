/**
 * Browser-side OpenTelemetry initialization.
 * OTel packages are listed in transpilePackages in next.config.mjs so that
 * Next.js/Webpack handles their ESM↔CJS interop correctly.
 */

import { WebTracerProvider, BatchSpanProcessor } from '@opentelemetry/sdk-trace-web';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes, defaultResource } from '@opentelemetry/resources';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load';

let initialized = false;

export function initOtel() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

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
