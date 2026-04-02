/**
 * Cloudflare Worker — *.chal.haucsia.com idle redirect
 * =====================================================
 * Deploy this worker with the route:
 *   *.chal.haucsia.com/*
 *
 * Behaviour:
 *   - Forwards the request to the origin server.
 *   - If the origin returns 503 (no container running on that port),
 *     redirects the browser to https://gym.haucsia.com instead.
 *   - All other responses (200, 404, etc.) are passed through unchanged.
 *
 * Setup (Cloudflare dashboard → Workers & Pages → Create Worker):
 *   1. Paste this script.
 *   2. Add a route:  *.chal.haucsia.com/*  → this worker.
 *   3. Make sure the 7 subdomain A records are set to DNS-only (grey cloud)
 *      so raw TCP on ports 10000-11999 reaches your server directly.
 *      The worker only handles HTTP/HTTPS traffic on port 80/443.
 *
 * Note: Cloudflare free tier does NOT proxy non-standard ports (10000-11999).
 * Those ports bypass Cloudflare entirely and hit your server directly — which
 * is exactly what we want for challenge instances. This worker only fires for
 * requests on port 80/443 to the chal subdomains (e.g. a browser navigating
 * to http://nathanael.chal.haucsia.com without a port).
 */

const REDIRECT_TARGET = "https://gym.haucsia.com";

export default {
  async fetch(request) {
    let response;
    try {
      response = await fetch(request);
    } catch {
      // Network error reaching origin — redirect
      return Response.redirect(REDIRECT_TARGET, 302);
    }

    if (response.status === 503) {
      return Response.redirect(REDIRECT_TARGET, 302);
    }

    return response;
  },
};
