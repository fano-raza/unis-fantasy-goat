import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Lets the LAN IP (used for on-device mobile preview) load dev JS chunks --
  // `next dev` 403s asset requests from origins outside this allowlist.
  allowedDevOrigins: ["192.168.1.112"],
  // The Team page's URLs moved from /profile* to /team/* -- these keep any
  // already-shared/bookmarked /profile links working instead of 404ing.
  async redirects() {
    return [
      { source: "/profile", destination: "/team/profile", permanent: true },
      { source: "/profile/comparison", destination: "/team/comparison", permanent: true },
      { source: "/profile/roster", destination: "/team/roster", permanent: true },
    ];
  },
};

export default nextConfig;
