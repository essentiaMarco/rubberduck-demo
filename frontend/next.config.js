/** @type {import('next').NextConfig} */
const nextConfig = {
  // Prevent Next.js from stripping trailing slashes on API routes
  // (FastAPI expects trailing slashes on some endpoints)
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
