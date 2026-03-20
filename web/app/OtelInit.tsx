'use client';

import { initSDK } from '@embrace-io/web-sdk';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';

const COLLECTOR = 'http://localhost:4318';

initSDK({
  appID: 'hk5hi',          // Embrace cloud — session replay, crash reporting, network waterfall
  appVersion: '0.1.0',
  spanExporters: [
    new OTLPTraceExporter({ url: `${COLLECTOR}/v1/traces` }),
  ],
  logExporters: [
    new OTLPLogExporter({ url: `${COLLECTOR}/v1/logs` }),
  ],
  defaultInstrumentationConfig: {
    network: {
      // Prevent circular spans from the collector and Embrace endpoints
      ignoreUrls: [
        `${COLLECTOR}/v1/traces`,
        `${COLLECTOR}/v1/logs`,
        /embrace\.io/,
      ],
    },
  },
});

export default function OtelInit() {
  return null;
}
