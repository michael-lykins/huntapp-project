/**
 * Minimal browser RUM — no npm OTel dependencies.
 *
 * Sends OTLP/HTTP JSON directly to the local collector (port 4318).
 * Patches window.fetch to create client spans with W3C traceparent headers
 * so browser→API traces are stitched in Elastic APM.
 */

const COLLECTOR = 'http://localhost:4318/v1/traces';
const SERVICE = 'ridgeline-web';
const API_ORIGIN = 'localhost:8000';

let initialized = false;

// ── Helpers ─────────────────────────────────────────────────────────────────

function randHex(bytes: number): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr, b => b.toString(16).padStart(2, '0')).join('');
}

function nowNs(): string {
  return String(BigInt(Math.round(performance.timeOrigin * 1e6 + performance.now() * 1e6)) * 1000n);
}

function attr(key: string, value: string | number) {
  return typeof value === 'number'
    ? { key, value: { intValue: String(value) } }
    : { key, value: { stringValue: value } };
}

function sendSpan(span: object) {
  const body = JSON.stringify({
    resourceSpans: [{
      resource: {
        attributes: [
          attr('service.name', SERVICE),
          attr('service.version', '0.1.0'),
          attr('deployment.environment', 'dev'),
          attr('service.namespace', 'ridgeline'),
          attr('telemetry.sdk.name', 'ridgeline-rum'),
        ],
      },
      scopeSpans: [{ scope: { name: SERVICE }, spans: [span] }],
    }],
  });
  // fire-and-forget; don't let telemetry errors surface
  fetch(COLLECTOR, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  }).catch(() => {});
}

// ── fetch instrumentation ────────────────────────────────────────────────────

function patchFetch() {
  const original = window.fetch.bind(window);
  window.fetch = async function patchedFetch(input, init) {
    const url = typeof input === 'string' ? input : (input as Request).url;

    // Only instrument calls to our own API
    if (!url.includes(API_ORIGIN)) {
      return original(input, init);
    }

    const traceId = randHex(16);
    const spanId = randHex(8);
    const traceparent = `00-${traceId}-${spanId}-01`;
    const startNs = nowNs();
    const startMs = performance.now();

    // Inject W3C trace context so the backend span becomes a child
    const headers = new Headers((init?.headers as HeadersInit) ?? {});
    headers.set('traceparent', traceparent);

    let status = 0;
    let ok = false;
    try {
      const response = await original(input, { ...init, headers });
      status = response.status;
      ok = response.ok;
      return response;
    } catch (err) {
      throw err;
    } finally {
      const durationMs = Math.round(performance.now() - startMs);
      const method = (init?.method ?? 'GET').toUpperCase();
      const pathname = new URL(url, location.href).pathname;

      sendSpan({
        traceId,
        spanId,
        name: `${method} ${pathname}`,
        kind: 3, // SPAN_KIND_CLIENT
        startTimeUnixNano: startNs,
        endTimeUnixNano: nowNs(),
        attributes: [
          attr('http.method', method),
          attr('http.url', url),
          attr('http.status_code', status),
          attr('http.duration_ms', durationMs),
        ],
        status: ok ? { code: 1 } : { code: 2, message: `HTTP ${status}` },
      });
    }
  };
}

// ── Document load span ───────────────────────────────────────────────────────

function sendDocumentLoad() {
  const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
  if (!nav) return;
  const traceId = randHex(16);
  sendSpan({
    traceId,
    spanId: randHex(8),
    name: 'document load',
    kind: 1, // SPAN_KIND_INTERNAL
    startTimeUnixNano: String(BigInt(Math.round(performance.timeOrigin * 1e6)) * 1000n),
    endTimeUnixNano: String(BigInt(Math.round((performance.timeOrigin + nav.loadEventEnd) * 1e6)) * 1000n),
    attributes: [
      attr('http.url', location.href),
      attr('browser.load_event_end_ms', Math.round(nav.loadEventEnd)),
      attr('browser.dom_interactive_ms', Math.round(nav.domInteractive)),
      attr('browser.ttfb_ms', Math.round(nav.responseStart)),
    ],
    status: { code: 1 },
  });
}

// ── Entry point ──────────────────────────────────────────────────────────────

export function initOtel() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  patchFetch();

  if (document.readyState === 'complete') {
    sendDocumentLoad();
  } else {
    window.addEventListener('load', sendDocumentLoad, { once: true });
  }
}
