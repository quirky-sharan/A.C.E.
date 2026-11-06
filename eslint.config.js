// @ts-check
// Shared ESLint flat config for all TypeScript in the monorepo (ESLint 10 + typescript-eslint 8).
import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["**/dist/", "**/node_modules/", "**/target/", "apps/desktop/src-tauri/", "core/"]),
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ["apps/desktop/src/**/*.{ts,tsx}"],
    extends: [reactHooks.configs.flat.recommended],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ["apps/bridge-extension/src/**/*.ts"],
    languageOptions: { globals: { ...globals.browser, ...globals.serviceworker } },
  },
  {
    files: ["eslint.config.js", "**/vite.config.ts"],
    languageOptions: { globals: globals.node },
  },
]);
