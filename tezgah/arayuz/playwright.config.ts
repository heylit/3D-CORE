import { defineConfig } from "@playwright/test";

// Uçtan uca (K8): Python sunucusu derlenmiş dist/ ile açılır. Yalnızca yerelde (pre-push) çalışır.
export default defineConfig({
  testDir: "tests",
  testMatch: "**/*.spec.ts",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:8725" },
  webServer: {
    command: "python -m tezgah --port 8725 --tarayici-yok",
    cwd: "../..",
    url: "http://127.0.0.1:8725/api/isler",
    reuseExistingServer: false,
  },
});
