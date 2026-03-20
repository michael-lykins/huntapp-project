/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['react-map-gl'],
  experimental: {
    serverComponentsExternalPackages: ['@opentelemetry/instrumentation'],
  },
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, fs: false };
    return config;
  },
};

export default nextConfig;
