/** @type {import('next').NextConfig} */
const nextConfig = {
  // react-leaflet v4's MapContainer doesn't clean up its Leaflet instance
  // correctly under React 18 Strict Mode's dev-only double-invoked effects,
  // which throws "Map container is already initialized" on every mount.
  reactStrictMode: false,
};

module.exports = nextConfig;
