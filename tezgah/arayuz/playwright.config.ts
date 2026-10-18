import { defineConfig } from "@playwright/test";

// Node türleri (@types/node) bağımlılık olarak eklenmedi; yalnızca ortam değişkenleri okunur.
declare const process: { env: Record<string, string | undefined> };

// Uçtan uca (K8): Python sunucusu derlenmiş dist/ ile açılır. Yalnızca yerelde (pre-push) çalışır.
export default defineConfig({
  testDir: "tests",
  testMatch: "**/*.spec.ts",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:8725",
    // Tarayıcı Playwright'ın indirdiğinden farklıysa (ör. bulutta hazır Chromium) yolu buradan verilir.
    launchOptions: process.env.TEZGAH_CHROMIUM ? { executablePath: process.env.TEZGAH_CHROMIUM } : {},
  },
  webServer: {
    // Python: etkin sanal ortam (TEZGAH_PYTHON ile değiştirilebilir)
    command: `${process.env.TEZGAH_PYTHON ?? "python"} -m tezgah --port 8725 --tarayici-yok`,
    cwd: "../..",
    url: "http://127.0.0.1:8725/api/isler",
    reuseExistingServer: false,
  },
});
