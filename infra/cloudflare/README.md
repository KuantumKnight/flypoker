# Cloudflare deployment

The Worker in `src/index.ts` is the authenticated replay ingest and public R2
read path. Create the `fly-poker-replays` R2 bucket, set `INGEST_TOKEN` as a
Worker secret, and replace `PUBLIC_ORIGIN` in `wrangler.toml` with the exact
Pages origin before deploying from this directory:

```powershell
npm install
npx wrangler secret put INGEST_TOKEN
npx wrangler deploy
```

Deploy the UI and dynamic replay shell to a Cloudflare Worker through the
OpenNext adapter from the repository root. Set
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_LIVE_WS_URL`, and
`NEXT_PUBLIC_REPLAY_API_URL` to the production API/tunnel and replay Worker
origins before building:

```powershell
npm run cloudflare:build
npx wrangler deploy --config wrangler.jsonc
```

Create the `fly-poker-live-ui-opennext-cache` R2 bucket first. The live
FastAPI service is never exposed directly; configure
`infra/cloudflared/config.example.yml` with the UI hostname and run the
outbound tunnel on the supervised GPU host. The checked-in
`wrangler.jsonc` is the reproducible Worker/Pages-compatible shell;
the deployment still requires a Cloudflare account and production hostname.

Validate the Worker bundle without credentials using:

```powershell
npm run typecheck
npx wrangler deploy --dry-run
```

The replay Worker dry-run above validates `infra/cloudflare/wrangler.toml`.
For the UI adapter, run `npm run cloudflare:build` and then
`npx wrangler deploy --config wrangler.jsonc --dry-run`.
