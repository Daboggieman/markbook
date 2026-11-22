/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // Playwright owns the e2e dir; vitest only runs component tests.
    exclude: ["**/node_modules/**", "e2e/**"],
  },
});
