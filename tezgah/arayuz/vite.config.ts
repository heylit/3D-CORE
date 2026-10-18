import { defineConfig } from "vitest/config";

// Geliştirmede /api istekleri yerel Python sunucusuna (python -m tezgah) yönlendirilir.
export default defineConfig({
  server: { proxy: { "/api": "http://127.0.0.1:8724" } },
  build: { outDir: "dist", emptyOutDir: true },
  test: { include: ["tests/**/*.test.ts"] },
});
