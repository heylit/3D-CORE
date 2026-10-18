// SPEC 25 — devir şeridi: zaman şeridinin altında iş mili devri n(t) (sunucunun nokta başına devri),
// n = n_max (G50) bölgeleri taralı, G96 / G97 geçişleri işaretli. Yalnızca çizim.

import { pxZaman, zamanPx } from "./zaman";
import type { TornaIs, TornaNoktalar } from "./tipler";
import { devirSinirBolgeleri } from "./torna";

export class DevirSeridi {
  private is?: TornaIs;
  private nk: TornaNoktalar | null = null;
  private bolgeler: [number, number][] = [];
  private t = 0;
  private ctx: CanvasRenderingContext2D;

  constructor(
    private tuval: HTMLCanvasElement,
    zamanDegisti: (t: number) => void,
  ) {
    this.ctx = tuval.getContext("2d")!;
    new ResizeObserver(() => this.ciz()).observe(tuval);
    tuval.addEventListener("pointerdown", (e) => {
      const T = this.is?.sure.toplam ?? 0;
      if (!(T > 0)) return;
      const r = tuval.getBoundingClientRect();
      zamanDegisti(pxZaman(e.clientX - r.left - 12, 0, T, r.width - 24));
    });
  }

  kur(is: TornaIs, nk: TornaNoktalar | null): void {
    this.is = is;
    this.nk = nk;
    const nMax = is.sure.n_max;
    try {
      this.bolgeler = nk && nMax ? devirSinirBolgeleri(nk.zaman, nk.devir, nMax) : [];
    } catch {
      this.bolgeler = [];
    }
    this.ciz();
  }

  zaman(t: number): void {
    this.t = t;
    this.ciz();
  }

  ciz(): void {
    const tv = this.tuval;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = tv.clientWidth;
    const H = tv.clientHeight;
    if (!W || !H) return;
    if (tv.width !== Math.round(W * dpr) || tv.height !== Math.round(H * dpr)) {
      tv.width = Math.round(W * dpr);
      tv.height = Math.round(H * dpr);
    }
    const c = this.ctx;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    const is = this.is;
    const nk = this.nk;
    if (!is || !(is.sure.toplam > 0)) return;
    const css = getComputedStyle(document.documentElement);
    const tok = (n: string) => css.getPropertyValue(n).trim();
    const T = is.sure.toplam;
    const x0 = 12;
    const w = W - 24;
    const X = (t: number) => x0 + zamanPx(t, 0, T, w);
    const y0 = 3;
    const h = H - 6;
    c.font = `600 10px ${tok("--mono")}`;
    c.textBaseline = "top";
    if (!nk || nk.n === 0) {
      c.fillStyle = tok("--silik");
      c.fillText("devir verisi yok", x0, y0);
      return;
    }
    let nUst = is.sure.n_max ?? 0;
    for (let k = 0; k < nk.n; k++) nUst = Math.max(nUst, nk.devir[k]);
    if (!(nUst > 0)) nUst = 1;
    const Y = (n: number) => y0 + h * (1 - n / nUst);
    // n_max bölgeleri: taralı
    c.save();
    c.strokeStyle = tok("--uyari") + "aa";
    c.lineWidth = 1;
    for (const [ta, tb] of this.bolgeler) {
      const a = X(ta);
      const b = Math.max(X(tb), a + 2);
      c.save();
      c.beginPath();
      c.rect(a, y0, b - a, h);
      c.clip();
      for (let x = a - h; x < b; x += 5) {
        c.beginPath();
        c.moveTo(x, y0 + h);
        c.lineTo(x + h, y0);
        c.stroke();
      }
      c.restore();
    }
    c.restore();
    // G96 / G97 geçişleri: işlem sınırında css değişirse
    c.fillStyle = tok("--mor");
    let onceki: boolean | null = null;
    for (const isl of is.islemler) {
      const g96 = !!isl.css;
      if (onceki !== null && g96 !== onceki) {
        const x = X(isl.t0);
        c.fillRect(Math.round(x), y0, 1, h);
        c.fillText(g96 ? "G96" : "G97", x + 3, y0);
      }
      onceki = g96;
    }
    // n(t) eğrisi
    c.strokeStyle = tok("--camgobegi");
    c.lineWidth = 1.5;
    c.beginPath();
    for (let k = 0; k < nk.n; k++) {
      const x = X(nk.zaman[k]);
      const y = Y(nk.devir[k]);
      if (k === 0) c.moveTo(x, y);
      else c.lineTo(x, y);
    }
    c.stroke();
    c.fillStyle = tok("--soluk");
    c.textAlign = "right";
    c.fillText(`n ≤ ${Math.round(nUst)} dev/dk`, W - 14, y0);
    c.textAlign = "left";
    // oynatma başı
    c.fillStyle = tok("--pirinc");
    c.fillRect(Math.round(X(this.t)) - 1, 0, 2, H);
  }
}
