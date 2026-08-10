import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Lets the LAN IP (used for on-device mobile preview) load dev JS chunks --
  // `next dev` 403s asset requests from origins outside this allowlist.
  allowedDevOrigins: ["192.168.1.112"],
};

export default nextConfig;
