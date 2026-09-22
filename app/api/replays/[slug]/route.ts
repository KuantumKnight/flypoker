import { get } from "@vercel/blob";

export const runtime = "nodejs";

export async function GET(request: Request, context: { params: Promise<{ slug: string }> }) {
  const { slug } = await context.params;
  if (!isSafeSlug(slug)) return new Response("Bad replay id", { status: 400 });

  const poster = new URL(request.url).searchParams.get("poster") === "1";
  const blob = await get(`${slug}.${poster ? "svg" : "json"}`, { access: "private" });
  if (!blob || blob.statusCode !== 200) return new Response("Replay not found", { status: 404 });

  return new Response(blob.stream, {
    headers: {
      "content-type": poster ? "image/svg+xml" : "application/json; charset=utf-8",
      "cache-control": slug === "latest" ? "public, max-age=15, must-revalidate" : "public, max-age=31536000, immutable",
    },
  });
}

function isSafeSlug(slug: string) {
  return /^[a-zA-Z0-9_-]+$/.test(slug) && slug.length <= 160;
}
