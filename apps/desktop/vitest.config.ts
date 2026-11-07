import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// UI tests run in jsdom; CSS (Tailwind, fonts) is not processed in tests.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
  },
});
