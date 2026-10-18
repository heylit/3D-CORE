// SPEC 24 — zaman şeridi: işlem klipleri, takım yükü kıvılcım grafiği, onay işaretleri, oynatma başı.

import type { Is, Noktalar } from "./tipler";
import { kivilcim, pxZaman, tickAdimi, zamanPx } from "./zaman";

export function sureYaz(t: number): string {
  t = Math.max(0, t);
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export class Serit {
  private is?: Is;
  private nk?: Noktalar;
  private renkler: string[] = [];
  private t = 0;
  private suruk = false;
  private ctx: CanvasRenderingContext2D;
  private yukOrnek: Float32Array = new Float32Array(0);
  private hataT: number[] = [];

  private zamanDegisti: (t: number) => void = () => {};

  constructor(private tuval: HTMLCanvasElement) {
    this.ctx = tuval.getContext("2d")!;
    new ResizeObserver(() => this.ciz()).observe(tuval);
    const tut = (e: PointerEvent) => {
      if (!this.is) return;
      const r = tuval.getBoundingClientRect();
      const T = this.sure();
      if (T > 0) this.zamanDegisti(pxZaman(e.clientX - r.left - 12, 0, T, r.width - 24));
    };
    tuval.addEventListener("pointerdown", (e) => {
      this.suruk = true;
      tuval.setPointerCapture(e.pointerId);
      tut(e);
    });
    tuval.addEventListener("pointermove", (e) => this.suruk && tut(e));
    const bitir = () => (this.suruk = false);
    tuval.addEventListener("pointerup", bitir);
    tuval.addEventListener("pointercancel", bitir);
  }

  /** Şeritte sürüklenince çağrılır (etkin ekran ayarlar). */
  dinle(cb: (t: number) => void): void {
    this.zamanDegisti = cb;
  }

  /** Ekran kapanınca: şerit boşalır. */
  bosalt(): void {
    this.is = undefined;
    this.nk = undefined;
    this.zamanDegisti = () => {};
    this.ciz();
  }

  sure(): number {
    return this.is ? this.is.sure.toplam : 0;
  }

  kur(is: Is, nk: Noktalar, renkler: string[], hataNoktalari: number[]): void {
    this.is = is;
    this.nk = nk;
    this.renkler = renkler;
    this.hataT = hataNoktalari.map((k) => nk.zaman[Math.min(k, nk.n - 1)]);
    this.yukOrnek = new Float32Array(0);
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
    if (!this.is || !this.nk) return;
    const css = getComputedStyle(document.documentElement);
    const tok = (n: string) => css.getPropertyValue(n).trim();
    const T = this.sure();
    if (!(T > 0)) return;
    const x0 = 12;
    const w = W - 24;
    const X = (t: number) => x0 + zamanPx(t, 0, T, w);
    // onay işaretleri
    const adim = tickAdimi(T, w, 64);
    c.font = `600 10.5px ${tok("--mono")}`;
    c.textBaseline = "top";
    for (let t = 0; t <= T + 1e-9; t += adim) {
      const x = X(t);
      c.fillStyle = tok("--cizgi");
      c.fillRect(Math.round(x), 18, 1, H - 22);
      c.fillStyle = tok("--silik");
      c.fillText(sureYaz(t), x + 3, 4);
    }
    // işlem klipleri
    const yb = 24;
    const yh = 22;
    c.font = `600 11px ${tok("--govde")}`;
    c.textBaseline = "middle";
    for (const isl of this.is.islemler) {
      const a = X(isl.t0);
      const b = X(isl.t1);
      const r = this.renkler[isl.i];
      c.fillStyle = r + "33";
      c.fillRect(a, yb, Math.max(b - a - 1, 1), yh);
      c.fillStyle = r;
      c.fillRect(a, yb, 3, yh);
      c.save();
      c.beginPath();
      c.rect(a, yb, Math.max(b - a - 4, 0), yh);
      c.clip();
      c.fillStyle = tok("--yazi");
      c.fillText(isl.ad, a + 8, yb + yh / 2);
      c.restore();
    }
    // takım yükü kıvılcım grafiği (sunucunun normalize yükü)
    const ys = yb + yh + 6;
    const hs = H - ys - 6;
    const kova = Math.max(1, Math.floor(w / 2));
    if (this.yukOrnek.length !== kova) this.yukOrnek = kivilcim(this.nk.zaman, this.nk.yuk, kova);
    c.fillStyle = tok("--pirinc") + "99";
    for (let b = 0; b < kova; b++) {
      const v = this.yukOrnek[b];
      if (v > 0) c.fillRect(x0 + (b * w) / kova, ys + hs * (1 - v), Math.max(w / kova - 0.5, 0.5), hs * v);
    }
    // ihlaller
    c.fillStyle = tok("--hata");
    for (const t of this.hataT) {
      const x = X(t);
      c.beginPath();
      c.moveTo(x, yb - 6);
      c.lineTo(x + 5, yb - 1);
      c.lineTo(x - 5, yb - 1);
      c.fill();
    }
    // oynatma başı
    const x = X(this.t);
    c.fillStyle = tok("--pirinc");
    c.fillRect(Math.round(x) - 1, 14, 2, H - 16);
    c.beginPath();
    c.moveTo(x - 6, 12);
    c.lineTo(x + 6, 12);
    c.lineTo(x, 19);
    c.fill();
  }
}
