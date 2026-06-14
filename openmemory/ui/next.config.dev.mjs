/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // The API proxy route (app/api/[...path]/route.ts) must receive trailing-slash
  // paths verbatim (e.g. /api/v1/apps/) so it can forward them to FastAPI's
  // collection routes. Without this, Next's default trailingSlash:false would
  // 308-redirect /api/v1/apps/ -> /api/v1/apps BEFORE the handler runs, adding a
  // hop and reshaping body-bearing requests.
  skipTrailingSlashRedirect: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig