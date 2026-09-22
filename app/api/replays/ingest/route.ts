import { put } from "@vercel/blob";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const expectedToken = process.env.FLYPOKER_REPLAY_UPLOAD_TOKEN || process.env.BLOB_READ_WRITE_TOKEN;
  if (!expectedToken || request.headers.get("authorization") !== `Bearer ${expectedToken}`) {
    return new Response("Unauthorized", { status: 401 });
  }

  const body = await request.json() as { slug?: string; replay?: unknown; posterSvg?: string };
  if (!body.slug || !isSafeSlug(body.slug) || !body.replay) return new Response("Bad replay", { status: 400 });

  const json = JSON.stringify(body.replay);
  await Promise.all([
    saveBlob(`${body.slug}.json`, json, "application/json"),
    saveBlob("latest.json", json, "application/json"),
    ...(body.posterSvg ? [saveBlob(`${body.slug}.svg`, body.posterSvg, "image/svg+xml"), saveBlob("latest.svg", body.posterSvg, "image/svg+xml")] : []),
  ]);
  return Response.json({ ok: true, slug: body.slug }, { status: 201 });
}

function saveBlob(pathname: string, value: string, contentType: string) {
  return put(pathname, value, {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType,
    cacheControlMaxAge: pathname === "latest.json" || pathname === "latest.svg" ? 15 : 31536000,
  });
}

function isSafeSlug(slug: string) {
  return /^[a-zA-Z0-9_-]+$/.test(slug) && slug.length <= 160;
}
