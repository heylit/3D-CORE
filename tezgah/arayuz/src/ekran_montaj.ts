// SPEC 25 — montaj ekranı: ağaç + serbestlik çipleri, BOM ve kütle, montaj sırası şeridi (patlat / topla),
// girişim (iplik) kartı: Öner → Uygula → torna işinin süre farkı ve "Tornada göster".
// Dönüşümler, serbestlik, girişim, öneri sunucudan; burada yalnız u ara değeri (sira.ts) ve biçim var.

import { SunucuHatasi, agAl, montajAl, montajParametre, oneriAl, tornaIsAl } from "./api";
import { DURAKLAT_SVG, type Komut, OYNAT_SVG } from "./komut";
import { kacis, kanitlarCiz, sayi } from "./paneller";
import { MontajSahne } from "./sahne_montaj";
import { type Mat4, type Serbestlik, adimU, cip, poz } from "./sira";
import type { Ag, Bag, Montaj, MontajDugum, Oneri, TornaIs } from "./tipler";

const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;

export const MONTAJ = "yatak_grubu";
const PATLAT_HIZ = 1.2; // tam şerit / s (E)
const OYNAT_HIZ = 0.8; // adım / s (Boşluk)

/** Sunucu 4x4'ü düz (16) ya da iç içe gönderebilir: düz satır öncelikli diziye. */
const duz = (T: number[] | number[][]): Mat4 => (T as (number | number[])[]).flat() as number[];

/** Torna işinde değişen ilk işlem: işlem süresi, parametreleri ya da G-code satırları farklı olan. */
function degisenIslem(eski: TornaIs | null, yeni: TornaIs): number | null {
  const n = yeni.islemler.length;
  if (!n) return null;
  if (!eski) return 0;
  for (let i = 0; i < n; i++) {
    const a = eski.islemler[i];
    const b = yeni.islemler[i];
    if (!a || eski.sure.islem[i] !== yeni.sure.islem[i]) return i;
    if (JSON.stringify(a.parametreler) !== JSON.stringify(b.parametreler)) return i;
    const sa = eski.gcode.filter((g) => g.islem === i).map((g) => g.metin);
    const sb = yeni.gcode.filter((g) => g.islem === i).map((g) => g.metin);
    if (sa.join("\n") !== sb.join("\n")) return i;
  }
  return 0;
}

export interface TornaBaglanti {
  /** Torna ekranının elindeki iş (yoksa null). */
  mevcutIs(): TornaIs | null;
  /** Montajdan gelen güncel iş; `islem` seçili açılır, `fark` süre farkı rozeti. */
  isAyarla(is: TornaIs, islem: number | null, fark?: number): void;
}

class MontajSeridi {
  private ctx: CanvasRenderingContext2D;
  private suruk = false;
  private N = 0;
  private adlar: string[] = [];
  private u = 0;

  constructor(
    private tuval: HTMLCanvasElement,
    uDegisti: (u: number) => void,
  ) {
    this.ctx = tuval.getContext("2d")!;
    new ResizeObserver(() => this.ciz()).observe(tuval);
    const tut = (e: PointerEvent) => {
      if (!this.N) return;
      const r = tuval.getBoundingClientRect();
      const w = r.width - 24;
      const u = ((e.clientX - r.left - 12) / w) * this.N;
      uDegisti(Math.min(Math.max(u, 0), this.N));
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

  kur(adlar: string[]): void {
    this.adlar = adlar;
    this.N = adlar.length;
    this.ciz();
  }

  zaman(u: number): void {
    this.u = u;
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
    if (!this.N) return;
    const css = getComputedStyle(document.documentElement);
    const tok = (n: string) => css.getPropertyValue(n).trim();
    const x0 = 12;
    const w = W - 24;
    const X = (u: number) => x0 + (u / this.N) * w;
    const renkler = [tok("--celik"), tok("--pirinc"), tok("--camgobegi"), tok("--mor"), tok("--tamam"), tok("--mercan")];
    const yb = 26;
    const yh = Math.min(30, H - yb - 10);
    c.font = `600 10.5px ${tok("--mono")}`;
    c.textBaseline = "top";
    for (let i = 0; i <= this.N; i++) {
      c.fillStyle = tok("--cizgi");
      c.fillRect(Math.round(X(i)), 18, 1, H - 22);
      c.fillStyle = tok("--silik");
      c.fillText(String(i), X(i) + 3, 4);
    }
    c.font = `600 11px ${tok("--govde")}`;
    c.textBaseline = "middle";
    this.adlar.forEach((ad, i) => {
      const a = X(i);
      const b = X(i + 1);
      const r = renkler[i % renkler.length];
      c.fillStyle = r + "33";
      c.fillRect(a, yb, Math.max(b - a - 1, 1), yh);
      c.fillStyle = r;
      c.fillRect(a, yb, 3, yh);
      c.save();
      c.beginPath();
      c.rect(a, yb, Math.max(b - a - 4, 0), yh);
      c.clip();
      c.fillStyle = tok("--yazi");
      c.fillText(ad, a + 8, yb + yh / 2);
      c.restore();
    });
    const x = X(this.u);
    c.fillStyle = tok("--pirinc");
    c.fillRect(Math.round(x) - 1, 14, 2, H - 16);
    c.beginPath();
    c.moveTo(x - 6, 12);
    c.lineTo(x + 6, 12);
    c.lineTo(x, 19);
    c.fill();
  }
}

export class MontajEkrani {
  private M: Montaj | null = null;
  private u = 0;
  private hedefU: number | null = null;
  private hiz = PATLAT_HIZ;
  private secili: string | null = null;
  private aglar = new Map<string, Ag>(); // parça kimliği → ağ
  private girisimAglari: Ag[] = [];
  private oneri: Oneri | null = null;
  private oneriBag: Bag | null = null;
  private uygulama: { sure_farki: number; is: TornaIs; islem: number | null } | null = null;
  private hata: string | null = null;
  private mesgul = false;
  private yuklendi = false;
  private gorunur = false;
  private yukHata: string | null = null;
  private pozDurum = new Map<string, Mat4>();
  private sahne: MontajSahne;
  private serit: MontajSeridi;

  constructor(private torna: TornaBaglanti) {
    this.sahne = new MontajSahne($("#mGorunum"), (yol) => this.sec(yol));
    this.serit = new MontajSeridi($<HTMLCanvasElement>("#mSeritTuval"), (u) => {
      this.hedefU = null;
      this.oynatDugmesi();
      this.uAyarla(u);
    });
    $("#mOynat").addEventListener("click", () => this.oynat());
    this.oynatDugmesi();
  }

  get hazir(): boolean {
    return this.yuklendi && !this.mesgul;
  }

  async ac(): Promise<void> {
    this.gorunur = true;
    if (!this.yuklendi) await this.yukle();
    else this.panelleriCiz();
  }

  kapat(): void {
    this.gorunur = false;
    this.hedefU = null;
    $("#mSol").innerHTML = "";
    $("#mSag").innerHTML = "";
  }

  // ----------------------------------------------------------------- yükleme

  /**
   * İki aşama: (1) Montaj JSON gelince durum, paneller ve pozlar hazır (ekran açılır); (2) parça ve girişim
   * ağları gelince sahne kurulur. `yenidenAg`: ağı değişen parça kimlikleri (önbellekten silinir).
   */
  private async yukle(hazir?: Montaj, yenidenAg: string[] = []): Promise<void> {
    this.mesgul = true;
    let M: Montaj;
    try {
      M = hazir ?? (await montajAl(MONTAJ));
    } catch (e) {
      this.yukHata = e instanceof SunucuHatasi ? e.message : String(e);
      this.yuklendi = true;
      this.mesgul = false;
      if (this.gorunur) this.panelleriCiz();
      return;
    }
    for (const b of M.bilesenler) b.T = duz(b.T);
    for (const a of M.sira) {
      for (const y of Object.keys(a.T_once)) a.T_once[y] = duz(a.T_once[y]);
      for (const y of Object.keys(a.T_sonra)) a.T_sonra[y] = duz(a.T_sonra[y]);
    }
    const ilk = this.M === null;
    this.M = M;
    this.yukHata = null;
    if (ilk) this.u = M.sira.length;
    this.u = Math.min(this.u, M.sira.length);
    if (this.secili && !M.bilesenler.some((b) => b.yol === this.secili)) this.secili = null;
    this.serit.kur(M.sira.map((a) => a.ad));
    this.yuklendi = true;
    this.mesgul = false;
    this.uAyarla(this.u);
    if (this.gorunur) this.panelleriCiz();
    void this.aglarYukle(M, yenidenAg, !ilk);
  }

  private async aglarYukle(M: Montaj, yenidenAg: string[], kameraKoru: boolean): Promise<void> {
    for (const k of yenidenAg) this.aglar.delete(k);
    const eksik = [...new Set(M.bilesenler.map((b) => b.parca))].filter((k) => !this.aglar.has(k));
    const [gelen, girisim] = await Promise.all([
      Promise.all(eksik.map((k) => agAl(M.ad, k).catch(() => null))),
      Promise.all(M.girisimler.map((g, i) => agAl(M.ad, g.ag || `girisim/${g.i ?? i}`).catch(() => null))),
    ]);
    eksik.forEach((k, i) => gelen[i] && this.aglar.set(k, gelen[i]!));
    if (this.M !== M) return; // bu arada yeni montaj geldi
    this.girisimAglari = girisim.filter((a): a is Ag => a !== null);
    this.sahne.kur(M.bilesenler, this.aglar, kameraKoru);
    this.sahne.girisimler(this.girisimAglari);
    this.uAyarla(this.u);
  }

  // ----------------------------------------------------------------- u, poz

  private uAyarla(u: number): void {
    const M = this.M;
    if (!M || !M.sira.length) return;
    const N = M.sira.length;
    this.u = Math.min(Math.max(u, 0), N);
    for (const b of M.bilesenler) {
      try {
        this.pozDurum.set(b.yol, poz(M.sira, b.yol, this.u));
      } catch {
        this.pozDurum.set(b.yol, b.T);
      }
    }
    this.sahne.pozlar(this.pozDurum);
    this.sahne.girisimGorunur(this.u >= N);
    this.seciliGlif();
    this.serit.zaman(this.u);
    const { i, s } = adimU(this.u, N);
    const adim = this.u >= N ? N : s > 0 ? i + 1 : i;
    $("#mSaat").innerHTML = `Adım ${adim} <span>/ ${N}</span>`;
    $("#mSaat").title = this.u >= N ? "tam montaj" : M.sira[Math.min(i, N - 1)].ad;
  }

  /** E: patlat (u → 0) / topla (u → N). */
  patlatTopla(): void {
    const M = this.M;
    if (!M) return;
    const simdi = this.hedefU ?? this.u;
    this.hiz = PATLAT_HIZ * M.sira.length;
    this.hedefU = simdi > 0 ? 0 : M.sira.length;
    this.oynatDugmesi();
  }

  /** Komut "patlat": u → 0. */
  patlat(): void {
    const M = this.M;
    if (!M) return;
    this.hiz = PATLAT_HIZ * M.sira.length;
    this.hedefU = 0;
    this.oynatDugmesi();
  }

  /** Boşluk: montaj sırasını oynat (sondaysa baştan). */
  oynat(): void {
    const M = this.M;
    if (!M) return;
    if (this.hedefU !== null) {
      this.hedefU = null;
    } else {
      if (this.u >= M.sira.length) this.uAyarla(0);
      this.hiz = OYNAT_HIZ;
      this.hedefU = M.sira.length;
    }
    this.oynatDugmesi();
  }

  private oynatDugmesi(): void {
    const b = $("#mOynat");
    const oynuyor = this.hedefU !== null;
    b.innerHTML = oynuyor ? DURAKLAT_SVG : OYNAT_SVG;
    b.setAttribute("aria-label", oynuyor ? "Durdur (Boşluk)" : "Montaj sırasını oynat (Boşluk)");
  }

  kare(dt: number): void {
    if (this.hedefU === null || !this.M) return;
    const d = this.hedefU - this.u;
    const adim = this.hiz * dt;
    if (Math.abs(d) <= adim) {
      const h = this.hedefU;
      this.hedefU = null;
      this.oynatDugmesi();
      this.uAyarla(h);
    } else this.uAyarla(this.u + Math.sign(d) * adim);
  }

  // ----------------------------------------------------------------- seçim

  private sec(yol: string | null): void {
    this.secili = yol;
    this.seciliGlif();
    if (this.gorunur && this.M) {
      this.agacCiz();
      this.sagCiz();
    }
  }

  /** Bir yaprağın serbestliği: son adımdaki (tam montaj) kayıt; yoksa kendi adımındaki. */
  private serbestlik(yol: string): Serbestlik | null {
    const sira = this.M?.sira ?? [];
    for (let i = sira.length - 1; i >= 0; i--) if (sira[i].serbestlik[yol]) return sira[i].serbestlik[yol];
    return null;
  }

  private seciliGlif(): void {
    const yol = this.secili;
    const T = yol ? this.pozDurum.get(yol) : undefined;
    const ol = this.olcek();
    this.sahne.secili(yol, yol ? this.serbestlik(yol) : null, T ? [T[3], T[7], T[11]] : null, ol);
    this.sahne.kutleMerkezi(this.M && this.u >= this.M.sira.length ? this.M.kutle.merkez : null, ol);
  }

  private olcek(): number {
    let enBuyuk = 0;
    for (const ag of this.aglar.values()) {
      for (let i = 0; i < ag.V.length; i++) enBuyuk = Math.max(enBuyuk, Math.abs(ag.V[i]));
    }
    return Math.max(enBuyuk * 0.5, 10);
  }

  // ----------------------------------------------------------------- paneller

  private panelleriCiz(): void {
    if (!this.M) {
      $("#mSol").innerHTML = `<section class="bolum"><h2 class="ust-baslik">Montaj</h2>
        <div class="hata-kutu" role="alert"><b>Montaj yüklenemedi</b>${kacis(this.yukHata ?? "")}</div></section>`;
      $("#mSag").innerHTML = `<section class="bolum"><div class="girisim-kart" data-testid="girisim-karti">Montaj yok</div></section>`;
      return;
    }
    this.agacCiz();
    this.sagCiz();
    this.hudCiz();
  }

  private hudCiz(): void {
    const M = this.M!;
    $("#mHudBaslik").innerHTML = `<b>${kacis(M.ad)}</b><span>${M.bilesenler.length} bileşen · ${M.sira.length} adım · ${kacis(
      M.parcalar.map((p) => p.ad).join(", "),
    )}</span>`;
    $("#mHudKatman").innerHTML = `<div class="lejant"><span class="kare-ornek girisim"></span> girişim · <span class="kare-ornek km"></span> kütle merkezi</div>`;
    $("#mHudUyari").innerHTML = M.girisimler.length
      ? `<div class="uyari-kutu hata"><b>Girişim</b>${M.girisimler.length} çift, toplam ${sayi(
          M.girisimler.reduce((a, g) => a + g.hacim, 0),
          1,
        )} mm³</div>`
      : `<div class="uyari-kutu tamam"><b>Girişim yok</b>tam montaj temiz</div>`;
  }

  private agacCiz(): void {
    const M = this.M!;
    const kap = $("#mSol");
    const yollar = new Set(M.bilesenler.map((b) => b.yol));
    const parcaAd = (k: string | null) => M.parcalar.find((p) => p.kimlik === k)?.ad ?? k ?? "";
    const dugum = (n: MontajDugum, yol: string): string => {
      if (n.part !== null && n.part !== undefined && yollar.has(yol)) {
        const s = this.serbestlik(yol);
        const sabit = M.bilesenler.find((b) => b.yol === yol)?.sabit;
        const kareler = s ? cip(s) : null;
        const cipHtml = sabit
          ? `<span class="cip-metin">sabit</span>`
          : kareler
            ? `<span class="cip" aria-hidden="true">${kareler.map((q) => `<i class="${q.kilitli ? "dolu" : ""}"></i>`).join("")}</span>
               <span class="cip-metin">${s!.sayi === 0 ? "kilitli" : `${s!.sayi} serbest: ${kacis(s!.etiketler.join(" "))}`}</span>`
            : `<span class="cip-metin">—</span>`;
        return `<li><button class="yaprak" data-yol="${kacis(yol)}" aria-pressed="${this.secili === yol}">
          <span class="ad">${kacis(n.name)} <small>${kacis(parcaAd(n.part))}</small></span>${cipHtml}</button></li>`;
      }
      const cocuk = n.children.map((c) => dugum(c, yol ? `${yol}/${c.name}` : c.name)).join("");
      if (!yol) return cocuk;
      return `<li><details open><summary>${kacis(n.name)} <small>alt montaj</small></summary><ul>${cocuk}</ul></details></li>`;
    };
    const kg = (t: number | null) => (t === null ? "—" : `${sayi(t * 1000, 3)} kg`);
    kap.innerHTML = `
      <section class="bolum">
        <h2 class="ust-baslik">Montaj ağacı <span>${kacis(M.agac.name)}</span></h2>
        <ul class="agac">${dugum(M.agac, "")}</ul>
        <p class="not-kucuk">Çip: 6 kare, dolu = kilitli serbestlik derecesi (SPEC 08).</p>
      </section>
      <section class="bolum">
        <h2 class="ust-baslik">BOM <span>${M.bom.length} satır</span></h2>
        <table class="bom"><thead><tr><th>Kalem</th><th>Adet</th><th>Birim</th><th>Toplam</th></tr></thead><tbody>
        ${M.bom
          .map(
            (b) =>
              `<tr><td>${kacis(parcaAd(b.item))}</td><td>${b.qty}</td><td>${kg(b.unit_mass)}</td><td>${kg(b.total_mass)}</td></tr>`,
          )
          .join("")}</tbody></table>
        <dl class="kv"><dt>Toplam kütle</dt><dd>${kg(M.kutle.toplam)}</dd>
          <dt>Kütle merkezi</dt><dd>${M.kutle.merkez.map((v) => sayi(v, 1)).join(", ")} mm</dd></dl>
      </section>`;
    kap.querySelectorAll<HTMLButtonElement>("button.yaprak").forEach((b) =>
      b.addEventListener("click", () => this.sec(this.secili === b.dataset.yol ? null : b.dataset.yol!)),
    );
  }

  private sagCiz(): void {
    const M = this.M!;
    const kap = $("#mSag");
    kap.innerHTML = `<section class="bolum"><h2 class="ust-baslik">Girişim <span>SPEC 09</span></h2><div id="mKart"></div></section>
      ${this.secili ? `<section class="bolum" id="mSecili"></section>` : ""}
      <section class="bolum kanit-bolum"><h2 class="ust-baslik">Kanıtlar <span>${M.kontroller.length}</span></h2><div id="mKanit"></div></section>`;
    this.kartCiz();
    if (this.secili) this.seciliCiz();
    kanitlarCiz($("#mKanit"), M.kontroller);
  }

  private seciliCiz(): void {
    const M = this.M!;
    const yol = this.secili!;
    const b = M.bilesenler.find((x) => x.yol === yol);
    const p = M.parcalar.find((x) => x.kimlik === b?.parca);
    const s = this.serbestlik(yol);
    $("#mSecili").innerHTML = `<h2 class="ust-baslik">Seçili <span>${kacis(yol)}</span></h2>
      <dl class="kv">
        <dt>Parça</dt><dd>${kacis(p?.ad ?? b?.parca ?? "")}</dd>
        <dt>Malzeme</dt><dd>${kacis(p?.malzeme ?? "—")}</dd>
        <dt>Hacim</dt><dd>${p ? `${sayi(p.hacim, 1)} mm³` : "—"}</dd>
        <dt>Kaynak</dt><dd>${p?.kaynak ? `${kacis(p.kaynak.tur)}: ${kacis(p.kaynak.is)}` : "CAD"}</dd>
        <dt>Serbestlik</dt><dd>${b?.sabit ? "sabit" : s ? `${s.sayi} · ${kacis(s.etiketler.join(" ") || "—")}` : "—"}</dd>
      </dl>
      ${s && s.sayi > 0 ? `<p class="not-kucuk">Sahnede: yeşil ok = öteleme yönü, pirinç halka + çizgi = dönme / vida ekseni.</p>` : ""}`;
  }

  /** Girişim çiftindeki parçalara bağlı parametreler. */
  private baglar(a: string, b: string): Bag[] {
    const M = this.M!;
    const parca = (yol: string) => M.bilesenler.find((x) => x.yol === yol)?.parca ?? yol;
    const kume = new Set([a, b, parca(a), parca(b)]);
    return M.baglar.filter((g) => g.parcalar.some((k) => kume.has(k)));
  }

  private kartCiz(): void {
    const M = this.M!;
    const kap = $("#mKart");
    const sonuc = this.uygulama
      ? `<div class="sonuc"><span class="rozet ${this.uygulama.sure_farki <= 0 ? "iyi" : "kotu"}" data-testid="sure-farki">torna süresi ${
          this.uygulama.sure_farki <= 0 ? "−" : "+"
        }${Math.abs(this.uygulama.sure_farki).toFixed(2)} s</span>
        <a href="#/torna" class="baglanti" data-testid="tornada-goster">Tornada göster →</a></div>`
      : "";
    if (!M.girisimler.length) {
      kap.innerHTML = `<div class="girisim-kart temiz" data-testid="girisim-karti" role="status">
        <b><span class="ik tamam" aria-hidden="true">✓</span> Girişim yok: temiz</b>
        <span>Tam montajda hacmi sıfırdan büyük kesişim yok.</span>${sonuc}</div>`;
    } else {
      const g = M.girisimler[0];
      const baglar = this.baglar(g.a, g.b);
      const bag = baglar[0] ?? null;
      const p = bag?.parametre;
      const o = this.oneri && this.oneriBag === bag ? this.oneri : null;
      kap.innerHTML = `<div class="girisim-kart" data-testid="girisim-karti" role="status">
        <b><span class="ik hata" aria-hidden="true">×</span> Girişim: ${kacis(g.a)} ↔ ${kacis(g.b)}</b>
        <span>hacim ${sayi(g.hacim, 2)} mm³${M.girisimler.length > 1 ? ` · ${M.girisimler.length - 1} çift daha` : ""}</span>
        ${
          p
            ? `<div class="bag">Bağlı parametre: <b>${kacis(p.is)} · ${kacis(p.anahtar)} = ${p.deger}</b> <small>(${p.min}–${p.max})</small></div>
          ${o ? `<div class="oneri">${o.deger === null ? `Öneri yok: ${kacis(o.neden)}` : `Öneri: ${kacis(p.anahtar)} = ${sayi(o.deger, 4)} (hacim ${sayi(o.hacim, 3)} mm³)`}</div>` : ""}
          <div class="dugmeler">
            <button data-testid="oner" ${this.mesgul ? "disabled" : ""}>Öner</button>
            <button data-testid="uygula" ${o && o.deger !== null && !this.mesgul ? "" : "disabled"}>Uygula</button>
          </div>`
            : `<div class="bag">Bu çifte bağlı parametre yok.</div>`
        }
        ${this.hata ? `<div class="hata-kutu" role="alert"><b>Sunucu</b>${kacis(this.hata)}</div>` : ""}
        ${sonuc}</div>`;
      kap.querySelector('[data-testid="oner"]')?.addEventListener("click", () => void this.oner(bag!, [g.a, g.b]));
      kap.querySelector('[data-testid="uygula"]')?.addEventListener("click", () => void this.uygula(bag!));
    }
    kap.querySelector('[data-testid="tornada-goster"]')?.addEventListener("click", () => {
      if (this.uygulama) this.torna.isAyarla(this.uygulama.is, this.uygulama.islem, this.uygulama.sure_farki);
    });
  }

  private async oner(bag: Bag, cift: [string, string]): Promise<void> {
    if (!this.M || this.mesgul) return;
    this.mesgul = true;
    this.hata = null;
    this.kartCiz();
    try {
      this.oneri = await oneriAl(this.M.ad, bag.parametre.is, bag.parametre.anahtar, cift);
      this.oneriBag = bag;
    } catch (e) {
      this.hata = e instanceof SunucuHatasi ? e.message : String(e);
    } finally {
      this.mesgul = false;
      if (this.gorunur) this.kartCiz();
    }
  }

  private async uygula(bag: Bag, deger?: number): Promise<void> {
    const v = deger ?? (this.oneri && this.oneri.deger !== null ? this.oneri.deger : null);
    if (!this.M || this.mesgul || v === null) return;
    this.mesgul = true;
    this.hata = null;
    if (this.gorunur) this.kartCiz();
    try {
      const eski = this.torna.mevcutIs() ?? (await tornaIsAl(bag.parametre.is).catch(() => null));
      const y = await montajParametre(this.M.ad, bag.parametre.is, bag.parametre.anahtar, v);
      const islem = degisenIslem(eski, y.is);
      this.uygulama = { sure_farki: y.sure_farki, is: y.is, islem };
      this.torna.isAyarla(y.is, islem, y.sure_farki);
      this.oneri = null;
      this.oneriBag = null;
      this.mesgul = false;
      await this.yukle(y.montaj, bag.parcalar);
    } catch (e) {
      this.hata = e instanceof SunucuHatasi ? e.message : String(e);
      this.mesgul = false;
      if (this.gorunur) this.kartCiz();
    }
  }

  /** Komut çubuğundan bağlı parametre (ör. "L 9.5"): montaj gerekirse yüklenir, bağ bulunursa uygulanır. */
  async parametreAyarla(anahtar: string, deger: number): Promise<void> {
    if (!this.M) await this.yukle();
    const bag = this.M?.baglar.find((b) => b.parametre.anahtar.toLowerCase() === anahtar.toLowerCase());
    if (!bag) {
      this.hata = `Montajda "${anahtar}" adlı bağlı parametre yok`;
      if (this.gorunur && this.M) this.kartCiz();
      return;
    }
    await this.uygula(bag, deger);
  }

  // ----------------------------------------------------------------- klavye, komutlar, kanca

  tus(e: KeyboardEvent, hedef: HTMLElement): boolean {
    const k = e.key;
    const N = this.M?.sira.length ?? 0;
    if (k === "e" || k === "E") this.patlatTopla();
    else if (k === " ") {
      if (hedef.matches("button, a, summary")) return true;
      e.preventDefault();
      this.oynat();
    } else if (k === "ArrowRight" || k === "ArrowLeft") {
      e.preventDefault();
      this.hedefU = null;
      const u = k === "ArrowRight" ? Math.floor(this.u + 1e-9) + 1 : Math.ceil(this.u - 1e-9) - 1;
      this.uAyarla(Math.min(Math.max(u, 0), N));
    } else if (k === "Home") this.uAyarla(0);
    else if (k === "End") this.uAyarla(N);
    else if (k === "Escape") this.sec(null);
    else return false;
    return true;
  }

  komutlar(): Komut[] {
    const M = this.M;
    if (!M) return [];
    return [
      { ad: "Patlat / topla", aciklama: "E", calistir: () => this.patlatTopla() },
      { ad: "Montaj sırasını oynat", aciklama: "Boşluk", calistir: () => this.oynat() },
      ...M.sira.map((a) => ({ ad: `Adım ${a.i + 1}: ${a.ad}`, aciklama: a.yol, calistir: () => this.uAyarla(a.i + 1) })),
    ];
  }

  kanca() {
    return {
      montajU: () => this.u,
      montajPoz: (yol: string) => [...(this.pozDurum.get(yol) ?? [])],
    };
  }
}
