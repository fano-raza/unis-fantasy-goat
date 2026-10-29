import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Lets the LAN IP (used for on-device mobile preview) load dev JS chunks --
  // `next dev` 403s asset requests from origins outside this allowlist.
  allowedDevOrigins: ["192.168.1.112"],
  // Section reorganization (2026-10-28): Weekly Stats (/weekly-stats,
  // /weekly-stats/ultra), Team (/team/roster, /team/trade-hub), League
  // (/league/standings, /league/league-wins, /league/ratings,
  // /league/draft-hub -- formerly Standings), Career (/career/profile,
  // /career/comparison, /career/stats). The bare section URLs land on each section's first
  // sub-page, and every older URL (including the even older /profile*
  // ones) keeps working instead of 404ing. Query strings carry through
  // (e.g. the Discord recap's /?year=&week= link, ?team= deep links).
  // Temporary (307) rather than permanent so browsers don't cache them
  // forever if the layout changes again.
  async redirects() {
    return [
      { source: "/", destination: "/weekly-stats", permanent: false },
      { source: "/ultra", destination: "/weekly-stats/ultra", permanent: false },
      { source: "/team", destination: "/team/roster", permanent: false },
      { source: "/team/profile", destination: "/career/profile", permanent: false },
      { source: "/team/comparison", destination: "/career/comparison", permanent: false },
      { source: "/players", destination: "/team/trade-hub", permanent: false },
      { source: "/players/draft", destination: "/league/draft-hub", permanent: false },
      { source: "/team/draft-hub", destination: "/league/draft-hub", permanent: false },
      { source: "/league", destination: "/league/standings", permanent: false },
      { source: "/standings", destination: "/league/standings", permanent: false },
      { source: "/standings/league-wins", destination: "/league/league-wins", permanent: false },
      { source: "/standings/ratings", destination: "/league/ratings", permanent: false },
      { source: "/career", destination: "/career/profile", permanent: false },
      { source: "/profile", destination: "/career/profile", permanent: false },
      { source: "/profile/comparison", destination: "/career/comparison", permanent: false },
      { source: "/profile/roster", destination: "/team/roster", permanent: false },
    ];
  },
};

export default nextConfig;
