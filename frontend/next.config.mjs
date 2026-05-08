/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    serverActions: { allowedOrigins: ["localhost:3000", "sv14.bcse-vju.com"] },
  },
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${apiBase.replace(/\/api$/, "")}/api/:path*` },
    ];
  },
};

export default nextConfig;
