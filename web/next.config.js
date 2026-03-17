/** @type {import('next').NextConfig} */
if (
  process.env.NODE_ENV === "production" &&
  process.env.NEXT_PUBLIC_DEV_AUTH === "true"
) {
  throw new Error(
    "NEXT_PUBLIC_DEV_AUTH must never be enabled for production builds.",
  );
}

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
  // Security headers (CSP is handled by middleware with per-request nonces)
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
