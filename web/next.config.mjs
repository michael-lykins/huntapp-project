/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['react-map-gl'],
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, fs: false };
    return config;
  },
};

export default nextConfig;
