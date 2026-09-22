import { defineCloudflareConfig } from "@opennextjs/cloudflare";
import r2IncrementalCache from "@opennextjs/cloudflare/overrides/incremental-cache/r2-incremental-cache";

/** Cloudflare adapter for the live UI and dynamic /replay/[slug] shell. */
export default defineCloudflareConfig({
  incrementalCache: r2IncrementalCache,
});
