import type { NextConfig } from "next";
import path from "node:path";

const UPSTREAM = process.env.CHANGEGUARD_API_URL ?? "http://127.0.0.1:8000";

// Pragmatic CSP: everything same-origin. 'unsafe-inline' is required for Next's
// inline bootstrap scripts without per-request nonces (which would make every
// page dynamic). No third-party script, frame, or connect origins are allowed.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""),
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Self-contained server bundle for container images (set by the Dockerfile); `next start` otherwise.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  poweredByHeader: false,
  // Let the dev server's hot reload work when opened as http://127.0.0.1:3000 as well as localhost.
  allowedDevOrigins: ["127.0.0.1"],
  turbopack: {
    // The app is self-contained in this directory (also inside Docker builds).
    root: path.join(__dirname),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    // The engine's interactive API reference, served on this origin.
    return [
      { source: "/api/docs", destination: `${UPSTREAM}/api/docs` },
      { source: "/api/redoc", destination: `${UPSTREAM}/api/redoc` },
      { source: "/api/openapi.json", destination: `${UPSTREAM}/api/openapi.json` },
    ];
  },
  async headers() {
    return [
      {
        source: "/((?!api/).*)",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
