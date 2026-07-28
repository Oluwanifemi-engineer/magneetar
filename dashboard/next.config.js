/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'export',
  images: {
    unoptimized: true,
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
    ],
  },
  // Transpile leaflet packages for Next.js compatibility
  transpilePackages: ['react-leaflet', 'leaflet'],
};

module.exports = nextConfig;
