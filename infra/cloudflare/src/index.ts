interface ReplayBucket {
  get(key: string): Promise<{ body: ReadableStream<Uint8Array> } | null>;
  put(key: string, value: string, options?: { httpMetadata?: { contentType?: string } }): Promise<void>;
}

export interface Env {
  REPLAYS: ReplayBucket;
  INGEST_TOKEN?: string;
  /** Public Pages origin allowed to read replay JSON/SVG cross-origin. */
  PUBLIC_ORIGIN?: string;
}

function corsHeaders(request: Request, env: Env): Record<string, string> {
  const origin = request.headers.get("origin");
  const allowed = env.PUBLIC_ORIGIN?.trim();
  if (!origin || !allowed || origin !== allowed) return {};
  return {
    "access-control-allow-origin": allowed,
    "access-control-allow-methods": "GET, OPTIONS",
    "access-control-allow-headers": "content-type, authorization",
    "vary": "Origin",
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      const headers = corsHeaders(request, env);
      return headers["access-control-allow-origin"]
        ? new Response(null, { status: 204, headers })
        : new Response("Origin not allowed", { status: 403 });
    }
    if (request.method === "POST" && url.pathname === "/ingest") {
      if (!env.INGEST_TOKEN || request.headers.get("authorization") !== `Bearer ${env.INGEST_TOKEN}`) return new Response("Unauthorized", { status: 401 });
      const body = await request.json() as { slug?: string; replay?: unknown; posterSvg?: string };
      if (!body.slug || body.slug.includes("..") || !body.replay) return new Response("Bad replay", { status: 400 });
      await env.REPLAYS.put(`${body.slug}.json`, JSON.stringify(body.replay), { httpMetadata: { contentType: "application/json" } });
      await env.REPLAYS.put("latest.json", JSON.stringify(body.replay), { httpMetadata: { contentType: "application/json" } });
      if (body.posterSvg) {
        await env.REPLAYS.put(`${body.slug}.svg`, body.posterSvg, { httpMetadata: { contentType: "image/svg+xml" } });
        await env.REPLAYS.put("latest.svg", body.posterSvg, { httpMetadata: { contentType: "image/svg+xml" } });
      }
      return new Response("ok", { status: 201 });
    }
    if (request.method !== "GET" || !url.pathname.startsWith("/replays/")) {
      return new Response("Not found", { status: 404 });
    }

    const requested = url.pathname.replace(/^\/replays\//, "");
    if (!requested || requested.includes("..")) return new Response("Bad replay id", { status: 400 });
    const poster = requested.endsWith(".svg");
    const slug = poster ? requested.slice(0, -4) : requested;
    const object = await env.REPLAYS.get(`${slug}.${poster ? "svg" : "json"}`);
    if (!object) return new Response("Replay not found", { status: 404 });
    const cors = corsHeaders(request, env);
    const cacheControl = slug === "latest"
      ? "public, max-age=15, must-revalidate"
      : "public, max-age=31536000, immutable";
    return new Response(object.body, {
      headers: { "content-type": poster ? "image/svg+xml" : "application/json; charset=utf-8", "cache-control": cacheControl, ...cors },
    });
  },
};
