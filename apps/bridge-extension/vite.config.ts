import { defineConfig } from "vite";

// Builds the MV3 service worker as one ES module; public/manifest.json is copied to dist/ unchanged.
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2022",
    rolldownOptions: {
      input: { "service-worker": "src/service-worker.ts" },
      output: { entryFileNames: "[name].js", format: "es" },
    },
  },
});
