/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: [
    'react-map-gl',
    '@opentelemetry/sdk-trace-web',
    '@opentelemetry/sdk-trace-base',
    '@opentelemetry/exporter-trace-otlp-http',
    '@opentelemetry/otlp-transformer',
    '@opentelemetry/instrumentation-fetch',
    '@opentelemetry/instrumentation-document-load',
    '@opentelemetry/instrumentation',
    '@opentelemetry/resources',
    '@opentelemetry/semantic-conventions',
    '@opentelemetry/core',
    '@opentelemetry/api',
  ],
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, fs: false };
    return config;
  },
};

export default nextConfig;
