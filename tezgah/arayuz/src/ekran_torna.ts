// SPEC 25 — torna ekranı: kademeli mil işi; yol, çap programlı G-code, devir şeridi, dönel kesit, kanıtlar.
// Sayıların hepsi sunucudan; burada yalnız biçim, görsel ara değer ve iki sunucu sayısının farkı var.

import { SunucuHatasi, tornaIsAl, tornaNoktalarAl, tornaParametreGonder, tornaSimAl } from "./api";
import { DevirSeridi } from "./devir_serit";
import { satirUcNoktasi } from "./gcode";
import { DURAKLAT_SVG, type Komut, OYNAT_SVG, anahtarSayi } from "./komut";
import { GcodePaneli, kacis, kanitlarCiz, sayi } from "./paneller";
import { TornaSahne } from "./sahne_torna";
import { Serit, sureYaz } from "./serit";
import type { Is, Nokta3, TornaIs, TornaIslem, TornaNoktalar } from "./tipler";
import { type TornaSim, capBicim, kesitAt, tornaHareketKonum } from "./torna";
import { idxAt } from "./zaman";

const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;

export const TORNA_IS = "kademeli_mil";
const ONDALIK = 3; // G-code yazıcısının ondalığı (SPEC 21)

const ISLEM_RENKLERI: Record<string, string> = {
  alin: "#93a6ba",
  kaba: "#d6a54e",
  ince: "#5cb8dc",
  kanal: "#b98ae0",
  dis: "#e3795d",
  boy: "#55c08f",
};
const YEDEK = ["#e3795d", "#55c08f", "#93a6ba", "#5cb8dc"];
const islemRengi = (isl: TornaIslem) => ISLEM_RENKLERI[isl.anahtar] ?? YEDEK[isl.i % YEDEK.length];

interface Aralik {
  ad: string;
  min: number;
  max: number;
  adim: number;
  birim: string;
}

const PARAMETRE: Record<string, Aralik> = {
  a_p: { ad: "Paso derinliği", min: 0.2, max: 6, adim: 0.1, birim: "mm" },
  ap: { ad: "Paso derinliği", min: 0.2, max: 6, adim: 0.1, birim: "mm" },
  f: { ad: "İlerleme", min: 0.02, max: 0.8, adim: 0.01, birim: "mm/dev" },
  Vc: { ad: "Kesme hızı", min: 20, max: 500, adim: 5, birim: "m/dk" },
  n_max: { ad: "Devir sınırı (G50)", min: 300, max: 6000, adim: 50, birim: "dev/dk" },
  rpm: { ad: "Devir (G97)", min: 100, max: 6000, adim: 50, birim: "dev/dk" },
  r: { ad: "Burun yarıçapı", min: 0.1, max: 2.4, adim: 0.1, birim: "mm" },
};

/** Komut çubuğu eşanlamlıları → olası parametre anahtarları. */
const ESANLAMLI: Record<string, string[]> = {
  paso: ["a_p", "ap"],
  derinlik: ["a_p", "ap"],
  ap: ["a_p", "ap"],
  a_p: ["a_p", "ap"],
  ilerleme: ["f"],
  f: ["f"],
  vc: ["Vc"],
  hiz: ["Vc"],
  hız: ["Vc"],
  nmax: ["n_max"],
  n_max: ["n_max"],
  devir: ["rpm", "n_max"],
  rpm: ["rpm"],
};

export class TornaEkrani {
  private is: TornaIs | null = null;
  private nk: TornaNoktalar | null = null;
  private sim: TornaSim | null = null;
  /** Montajdan gelen (henüz yüklenmemiş) iş ve seçilecek işlem. */
  private bekleyen: { is: TornaIs; islem: number | null } | null = null;
  private renkler: string[] = [];
  private t = 0;
  private oynuyor = false;
  private hiz = 20;
  private secili: number | null = null;
  private sekme: "gcode" | "kanit" = "gcode";
  private cap = true;
  private uzerindeSatir = -1;
  private hata: string | null = null;
  private yukHata: string | null = null;
  private fark: number | null = null;
  private dro: Nokta3 = [0, 0, 0];
  private mesgul = false;
  private yuklendi = false;
  private gorunur = false;
  private sahne: TornaSahne;
  private serit: Serit;
  private devir: DevirSeridi;
  private gcode: GcodePaneli;

  constructor() {
    this.sahne = new TornaSahne($("#tGorunum"));
    this.serit = new Serit($<HTMLCanvasElement>("#tSeritTuval"), (t) => this.zamanAyarla(t, true));
    this.devir = new DevirSeridi($<HTMLCanvasElement>("#tDevirTuval"), (t) => this.zamanAyarla(t, true));
    this.gcode = new GcodePaneli(
      $("#tBolme"),
      (s) => this.satirUstunde(s),
      (s) => this.satiraGit(s),
    );
    this.oynat(false);
    $("#tOynat").addEventListener("click", () => this.oynat(!this.oynuyor));
    $("#tGorunum").addEventListener("pointermove", (e) => this.buyutec(e.clientX, e.clientY));
    $("#tGorunum").addEventListener("pointerleave", () => ($("#tBuyutec").hidden = true));
  }

  // ----------------------------------------------------------------- kabuk arayüzü

  get hazir(): boolean {
    return this.yuklendi && !this.mesgul && this.bekleyen === null;
  }

  /** Ekran açılınca: gerekirse yükle, panelleri çiz. */
  async ac(): Promise<void> {
    this.gorunur = true;
    if (this.bekleyen) {
      const { is, islem } = this.bekleyen;
      await this.yukle(is, false, islem);
    } else if (!this.yuklendi) {
      await this.yukle();
    } else {
      this.panelleriCiz();
      this.guncelle(true);
    }
  }

  /** Ekran kapanınca: dinamik panelleri boşalt (test kimlikleri tek kalsın). */
  kapat(): void {
    this.gorunur = false;
    this.oynat(false);
    this.satirUstunde(-1);
    $("#tSol").innerHTML = "";
    $("#tMufettis").innerHTML = "";
    $("#tSekmeler").innerHTML = "";
    $("#tBolme").innerHTML = "";
  }

  /** Montajdan gelen güncel iş (POST yanıtı); ekran açılınca bu iş gösterilir, `islem` seçili. */
  isAyarla(is: TornaIs, islem: number | null, fark?: number): void {
    if (this.bekleyen?.is === is) return;
    this.bekleyen = { is, islem };
    this.fark = fark ?? null;
    if (this.gorunur) void this.yukle(is, true, islem);
  }

  /** Gösterilen (ya da yüklenmekte olan) iş. */
  mevcutIs(): TornaIs | null {
    return this.bekleyen?.is ?? this.is;
  }

  // ----------------------------------------------------------------- yükleme

  /**
   * İki aşama: (1) `Is` gelince durum, paneller ve yol hazır (ekran açılır); (2) nokta ve sim dizileri gelince
   * zaman şeridi, devir şeridi ve dönel kesit güncellenir. Diziler gelmezse ekran yolu ve G-code ile çalışır.
   */
  private async yukle(hazirIs?: TornaIs, kameraKoru = false, islem: number | null = null): Promise<void> {
    this.mesgul = true;
    let is: TornaIs;
    try {
      is = hazirIs ?? (await tornaIsAl(TORNA_IS));
    } catch (e) {
      this.yukHata = e instanceof SunucuHatasi ? e.message : String(e);
      this.yuklendi = true;
      this.mesgul = false;
      if (this.gorunur) this.panelleriCiz();
      return;
    }
    this.is = is;
    this.nk = null;
    this.sim = null;
    this.yukHata = null;
    this.renkler = is.islemler.map(islemRengi);
    const n = is.islemler.length;
    if (islem !== null && islem >= 0 && islem < n) this.secili = islem;
    else if (this.secili === null || this.secili >= n) this.secili = n ? 0 : null;
    this.t = islem !== null && this.secili !== null ? is.islemler[this.secili].t0 : Math.min(this.t, is.sure.toplam);
    this.sahne.isKur(is, null, null, this.renkler, kameraKoru);
    this.devir.kur(is, null);
    this.yuklendi = true;
    if (this.bekleyen?.is === is) this.bekleyen = null;
    this.mesgul = false;
    if (this.gorunur) this.panelleriCiz();
    this.guncelle(true);
    void this.dizilerYukle(is);
  }

  /** (2) nokta ve sim dizileri; yüklenmeyen dizi null kalır (ekran yol ve G-code ile çalışır). */
  private async dizilerYukle(is: TornaIs): Promise<void> {
    const [nk, sim] = await Promise.all([
      tornaNoktalarAl(TORNA_IS).catch(() => null),
      tornaSimAl(TORNA_IS).catch(() => null),
    ]);
    if (this.is !== is) return; // bu arada başka iş geldi
    this.nk = nk && nk.n > 0 ? nk : null;
    this.sim = sim;
    this.sahne.isKur(is, this.nk, sim, this.renkler, true);
    if (this.nk) {
      const hatalar = is.kontroller
        .filter((k) => k.durum === "hata")
        .map((k) => /nokta (\d+)/.exec(k.aciklama))
        .filter((m): m is RegExpExecArray => m !== null)
        .map((m) => Number(m[1]));
      this.serit.kur(is as unknown as Is, this.nk, this.renkler, hatalar);
    }
    this.devir.kur(is, this.nk);
    if (this.uzerindeSatir >= 0) this.satirUstunde(this.uzerindeSatir);
    else this.guncelle(true);
  }

  // ----------------------------------------------------------------- çizim

  private panelleriCiz(): void {
    const is = this.is;
    if (!is) {
      $("#tSol").innerHTML = `<section class="bolum"><h2 class="ust-baslik">Torna</h2>
        <div class="hata-kutu" role="alert"><b>Torna işi yüklenemedi</b>${kacis(this.yukHata ?? "")}</div></section>`;
      return;
    }
    this.solCiz();
    this.mufettisCiz();
    this.sekmeleriCiz();
    if (this.sekme === "gcode") this.gcode.kur(is as unknown as Is);
    else kanitlarCiz($("#tBolme"), is.kontroller);
    this.hudCiz();
  }

  private solCiz(): void {
    const is = this.is!;
    const s = is.kurulum.stok;
    const tamam = is.kontroller.filter((k) => k.durum === "tamam").length;
    const fark = this.fark;
    const kap = $("#tSol");
    kap.innerHTML = `
      <section class="bolum">
        <h2 class="ust-baslik">Torna işi <span>${kacis(is.kurulum.wcs ?? "")}</span></h2>
        ${this.yukHata ? `<div class="hata-kutu" role="alert"><b>Sunucu</b>${kacis(this.yukHata)}</div>` : ""}
        <dl class="kv">
          <dt>Ad</dt><dd>${kacis(is.ad)}</dd>
          <dt>Malzeme</dt><dd>${kacis(is.kurulum.malzeme ?? "—")}</dd>
          <dt>Ham</dt><dd>Ø${sayi(s.D, 1)}${s.d > 0 ? ` / Ø${sayi(s.d, 1)}` : ""} × ${sayi(s.zmax - s.zmin, 1)} mm</dd>
          <dt>Devir sınırı</dt><dd>${is.sure.n_max === null || is.sure.n_max === undefined ? "—" : `G50 S${is.sure.n_max}`}</dd>
          <dt>Hareket</dt><dd>${is.hareketler.length} · ${is.gcode.length} satır</dd>
          <dt>Kanıt</dt><dd>${tamam}/${is.kontroller.length} tamam</dd>
        </dl>
        <div class="cevrim">
          <div><small>Çevrim süresi</small><span class="buyuk">${sureYaz(is.sure.toplam)}</span></div>
          <span class="fark ${fark === null ? "" : "acik"} ${fark !== null && fark <= 0 ? "iyi" : "kotu"}">${
            fark === null ? "" : `${fark <= 0 ? "−" : "+"}${Math.abs(fark).toFixed(1)} s`
          }</span>
        </div>
      </section>
      <section class="bolum">
        <h2 class="ust-baslik">İşlemler <span>${is.islemler.length}</span></h2>
        <div class="islemler" id="tIslemListe"></div>
      </section>`;
    const liste = kap.querySelector<HTMLElement>("#tIslemListe")!;
    for (const isl of is.islemler) {
      const b = document.createElement("button");
      b.className = "islem";
      b.dataset.testid = "torna-islem";
      b.dataset.islem = String(isl.i);
      b.style.setProperty("--r", islemRengi(isl));
      b.setAttribute("aria-current", String(isl.i === this.secili));
      const kip = isl.css ? `G96 Vc ${isl.css === true ? "" : isl.css}` : isl.rpm ? `G97 S${isl.rpm}` : "";
      b.innerHTML = `<span class="serit-renk"></span>
        <span class="ad"><i>${String(isl.i + 1).padStart(2, "0")}</i>${kacis(isl.ad)}</span>
        <span class="sure">${sureYaz(is.sure.islem[isl.i] ?? isl.t1 - isl.t0)}</span>
        <span class="alt"><span>T${isl.takim.T} · r ${sayi(isl.takim.r, 1)}</span><span>${kacis(kip)}</span></span>`;
      b.addEventListener("click", () => this.islemSec(isl.i));
      liste.appendChild(b);
    }
  }

  private mufettisCiz(): void {
    const kap = $("#tMufettis");
    const is = this.is!;
    const isl = this.secili === null ? undefined : is.islemler[this.secili];
    if (!isl) {
      kap.innerHTML = "";
      return;
    }
    const t = isl.takim;
    const kip = isl.css ? `G96 · Vc ${isl.css === true ? "—" : isl.css} m/dk` : `G97 · ${isl.rpm ?? "—"} dev/dk`;
    kap.innerHTML = `<section class="bolum">
        <h2 class="ust-baslik">Müfettiş <span style="color:${islemRengi(isl)}">${kacis(isl.ad)}</span></h2>
        <div class="takim-kart"><svg viewBox="0 0 42 42" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <path d="M8 34 L20 22 L34 26 L22 38 Z" /><circle cx="10" cy="33" r="3" /><path d="M20 22 L30 6 L38 10 L34 26" /></svg>
          <div><b>T${t.T} · ${kacis(t.ad)}</b>
          <span>uç ${kacis(String(t.uc))} · burun r ${sayi(t.r, 2)} mm · ${kacis(kip)} · ${sureYaz(isl.t0)}–${sureYaz(isl.t1)}</span></div></div>
        ${this.hata ? `<div class="hata-kutu" role="alert"><b>Çekirdek reddetti</b>${kacis(this.hata)}</div>` : ""}
        <div id="tKaydiricilar"></div>
      </section>`;
    const k = kap.querySelector<HTMLElement>("#tKaydiricilar")!;
    for (const [anahtar, deger] of Object.entries(isl.parametreler)) {
      const a = PARAMETRE[anahtar] ?? { ad: anahtar, min: 0, max: deger * 3 || 1, adim: 0.01, birim: "" };
      const kimlik = `tp-${anahtar}`;
      const d = document.createElement("div");
      d.className = "kaydirici";
      d.innerHTML = `<label for="${kimlik}">${a.ad} <small>(${kacis(anahtar)})</small></label>
        <output for="${kimlik}">${deger} ${a.birim}</output>
        <input type="range" id="${kimlik}" data-testid="torna-parametre" data-anahtar="${kacis(anahtar)}" min="${Math.min(a.min, deger)}" max="${Math.max(a.max, deger)}" step="${a.adim}" value="${deger}">`;
      const girdi = d.querySelector("input")!;
      const cikti = d.querySelector("output")!;
      girdi.addEventListener("input", () => (cikti.textContent = `${girdi.value} ${a.birim}`));
      girdi.addEventListener("change", () => void this.parametreDegistir(anahtar, Number(girdi.value)));
      k.appendChild(d);
    }
  }

  private sekmeleriCiz(): void {
    const is = this.is!;
    const sorun = is.kontroller.filter((k) => k.durum !== "tamam").length;
    const s = $("#tSekmeler");
    s.innerHTML = `<button role="tab" data-sekme="gcode" aria-selected="${this.sekme === "gcode"}">G-code <span class="sayi">${is.gcode.length}</span></button>
      <button role="tab" data-sekme="kanit" aria-selected="${this.sekme === "kanit"}">Kanıtlar <span class="sayi">${sorun ? `${sorun} sorun` : "tamam"}</span></button>`;
    s.querySelectorAll<HTMLButtonElement>("button").forEach((b) =>
      b.addEventListener("click", () => this.sekmeSec(b.dataset.sekme as "gcode" | "kanit")),
    );
  }

  sekmeSec(sekme: "gcode" | "kanit"): void {
    this.sekme = sekme;
    if (!this.is) return;
    this.sekmeleriCiz();
    if (sekme === "gcode") this.gcode.kur(this.is as unknown as Is);
    else kanitlarCiz($("#tBolme"), this.is.kontroller);
    this.guncelle(true);
  }

  private hudCiz(): void {
    const is = this.is!;
    const isl = this.secili === null ? undefined : is.islemler[this.secili];
    $("#tHudBaslik").innerHTML = `<b>${kacis(isl ? isl.ad : is.ad)}</b><span>${kacis(is.ad)} · ${kacis(is.kurulum.malzeme ?? "")} · torna</span>`;
    const kesit = this.sahne.kesit();
    $("#tHudKatman").innerHTML = `<div class="parca" role="group" aria-label="Görünüm">
        <button data-k="kesit" aria-pressed="${kesit}" title="S">Kesit 270° <kbd>S</kbd></button>
        <button data-k="cap" aria-pressed="${this.cap}" title="R">${this.cap ? "Ø çap" : "R yarıçap"} <kbd>R</kbd></button>
      </div><div class="lejant"><span class="cizgi-ornek hedef"></span> hedef profil · <span class="cizgi-ornek ham"></span> ham</div>`;
    $("#tHudKatman")
      .querySelectorAll<HTMLButtonElement>("button")
      .forEach((b) =>
        b.addEventListener("click", () => (b.dataset.k === "kesit" ? this.kesitDegistir() : this.capDegistir())),
      );
    const hatalar = is.kontroller.filter((k) => k.durum === "hata");
    $("#tHudUyari").innerHTML = hatalar.length
      ? hatalar.map((k) => `<div class="uyari-kutu hata"><b>${kacis(k.baslik)}</b>${kacis(k.aciklama)}</div>`).join("")
      : `<div class="uyari-kutu tamam"><b>Kanıtlar tamam</b>${is.kontroller.length} kontrol, ihlal yok</div>`;
  }

  /** t anına göre takım, kesit, DRO, saat, G-code vurgusu. */
  private guncelle(zorla = false): void {
    const is = this.is;
    if (!is) return;
    const nk = this.nk;
    let p: Nokta3;
    let islem = this.secili ?? 0;
    let satir = -1;
    let n: number | null = null;
    let k = 0;
    if (nk) {
      k = idxAt(this.t, nk.zaman);
      p = [nk.konum[3 * k], nk.konum[3 * k + 1], nk.konum[3 * k + 2]];
      islem = nk.islem[k];
      n = nk.devir[k];
      if (k + 1 < nk.n && nk.zaman[k + 1] > nk.zaman[k]) {
        const u = (this.t - nk.zaman[k]) / (nk.zaman[k + 1] - nk.zaman[k]);
        const hk = nk.hareket[k + 1];
        islem = nk.islem[k + 1];
        if (hk >= 0) p = tornaHareketKonum(is.hareketler[hk], u);
        else p = [0, 1, 2].map((i) => nk.konum[3 * k + i] + (nk.konum[3 * (k + 1) + i] - nk.konum[3 * k + i]) * u) as Nokta3;
      }
      satir = k + 1 < nk.n && nk.satir[k + 1] >= 0 ? nk.satir[k + 1] : nk.satir[k];
      this.sahne.ilerleme(k);
      this.serit.zaman(this.t);
      this.devir.zaman(this.t);
    } else {
      const h = is.hareketler[is.hareketler.length - 1];
      p = h ? [...h.b] : [0, 0, 0];
      this.sahne.ilerleme(0);
    }
    this.sahne.takimKonum(p, islem);
    if (this.gorunur && this.sekme === "gcode") this.gcode.vurgula(satir, this.oynuyor || zorla);
    if (this.uzerindeSatir < 0) {
      this.dro = [this.cap ? 2 * p[0] : p[0], p[1], p[2]];
      this.droCiz(p, satir, islem, n);
    }
    $("#tSaat").innerHTML = `${sureYaz(this.t)} <span>/ ${sureYaz(is.sure.toplam)}</span>`;
  }

  /** DRO: X çap (G-code sözcüğüyle aynı sayı) ya da yarıçap; Z; satır, ilerleme, devir. */
  private droCiz(p: Nokta3, satir: number, islem: number, n: number | null, xMetin?: string): void {
    if (!this.gorunur || !this.is) return;
    const is = this.is;
    const X = xMetin ?? capBicim(p[0], this.cap, ONDALIK);
    const hk = this.nk ? this.nk.hareket[Math.min(idxAt(this.t, this.nk.zaman) + 1, this.nk.n - 1)] : -1;
    const F = hk >= 0 ? is.hareketler[hk].F : null;
    $("#tHudDro").innerHTML = `<div class="dro" data-test="dro">
      <div><i>${this.cap ? "XØ" : "XR"}</i><span>${X}</span></div><div><i>Z</i><span>${capBicim(p[2], false, ONDALIK)}</span></div>
      <div><i>n</i><span>${n === null ? "—" : Math.round(n)}</span></div>
      <div class="alt">${satir >= 0 ? `N${satir + 1}` : "—"} · ${F === null ? "G0 hızlı" : `F${F} mm/dev`} · T${is.islemler[islem]?.takim.T ?? "-"} · ${this.cap ? "çap" : "yarıçap"}</div></div>`;
  }

  private zamanAyarla(t: number, durdur: boolean): void {
    if (!this.is) return;
    if (durdur) this.oynat(false);
    this.t = Math.min(Math.max(t, 0), this.is.sure.toplam);
    this.guncelle();
  }

  // ----------------------------------------------------------------- etkileşim

  islemSec(i: number): void {
    if (!this.is) return;
    this.secili = i;
    this.hata = null;
    this.zamanAyarla(this.is.islemler[i].t0, true);
    this.panelleriCiz();
  }

  private satirUstunde(satir: number): void {
    this.uzerindeSatir = satir;
    this.gcode.ustundeki(satir);
    const is = this.is;
    if (!is) return;
    const p = satir >= 0 ? satirUcNoktasi(satir, is.satir_hareket, is.hareketler) : null;
    const ar = satir >= 0 ? is.satir_hareket[satir] : null;
    const islem = ar ? is.hareketler[ar[1]].islem : 0;
    this.sahne.hayalet(p, islem);
    if (p) {
      // DRO satırın uç noktasını gösterir; çap modunda X sunucunun DRO değeri (G-code sözcüğüyle aynı sayı)
      const sd = is.gcode[satir]?.dro;
      const X = this.cap && sd ? sd.X : this.cap ? 2 * p[0] : p[0];
      this.dro = [X, p[1], p[2]];
      this.droCiz(p, satir, islem, null, this.cap && sd ? capBicim(sd.X, false, ONDALIK) : undefined);
    } else {
      this.uzerindeSatir = -1;
      this.guncelle();
    }
  }

  private satiraGit(satir: number): void {
    const is = this.is;
    const nk = this.nk;
    if (!is || !nk) return;
    const ar = is.satir_hareket[satir];
    if (!ar) return;
    for (let k = 0; k < nk.n; k++) {
      if (nk.hareket[k] === ar[1]) {
        this.zamanAyarla(nk.zaman[k], true);
        return;
      }
    }
  }

  private async parametreDegistir(anahtar: string, deger: number): Promise<void> {
    if (this.mesgul || !this.is || this.secili === null) return;
    this.mesgul = true;
    try {
      const y = await tornaParametreGonder(TORNA_IS, this.secili, anahtar, deger);
      this.fark = y.sure_farki;
      this.hata = null;
      this.mesgul = false;
      await this.yukle(y.is, true);
    } catch (e) {
      this.hata = e instanceof SunucuHatasi ? e.message : String(e);
      this.mesgul = false;
      if (this.gorunur) this.mufettisCiz();
    }
  }

  kesitDegistir(): void {
    this.sahne.kesit(!this.sahne.kesit());
    if (this.is && this.gorunur) this.hudCiz();
  }

  capDegistir(): void {
    this.cap = !this.cap;
    if (!this.is || !this.gorunur) return;
    this.hudCiz();
    if (this.uzerindeSatir >= 0) this.satirUstunde(this.uzerindeSatir);
    else this.guncelle();
  }

  private buyutec(x: number, y: number): void {
    const kutu = $("#tBuyutec");
    const sim = this.sim;
    const is = this.is;
    if (!sim || !is || !this.nk) {
      kutu.hidden = true;
      return;
    }
    const q = this.sahne.duzlemNokta(x, y);
    const h = q ? Math.floor((q.z - sim.z0) / sim.dz) : -1;
    if (!q || h < 0 || h >= sim.nz || q.r > is.kurulum.stok.D / 2 + 5) {
      kutu.hidden = true;
      return;
    }
    const k = idxAt(this.t, this.nk.zaman);
    const { dis } = kesitAt(sim, k);
    const hedef = sim.hedef[h];
    const zc = sim.z0 + (h + 0.5) * sim.dz;
    const r = $("#tGorunum").getBoundingClientRect();
    kutu.hidden = false;
    kutu.style.left = `${Math.min(x - r.left + 14, r.width - 190)}px`;
    kutu.style.top = `${Math.max(y - r.top - 70, 4)}px`;
    kutu.innerHTML = `<b>z ${capBicim(zc, false, 2)}</b>
      <span>güncel Ø ${capBicim(dis[h], true, ONDALIK)}</span>
      <span>hedef Ø ${Number.isFinite(hedef) ? capBicim(hedef, true, ONDALIK) : "—"}</span>
      <span>fark ${Number.isFinite(hedef) ? capBicim(dis[h] - hedef, true, ONDALIK) : "—"} mm</span>`;
  }

  // ----------------------------------------------------------------- oynatma, klavye, komutlar

  oynat(acik: boolean): void {
    if (acik && this.is && this.t >= this.is.sure.toplam) this.t = 0;
    this.oynuyor = acik;
    const b = $("#tOynat");
    b.innerHTML = acik ? DURAKLAT_SVG : OYNAT_SVG;
    b.setAttribute("aria-label", acik ? "Duraklat (Boşluk)" : "Oynat (Boşluk)");
  }

  adim(yon: 1 | -1): void {
    const nk = this.nk;
    if (!nk) return;
    const k = idxAt(this.t, nk.zaman);
    let j = Math.min(Math.max(k + yon, 0), nk.n - 1);
    while (j > 0 && j < nk.n - 1 && nk.zaman[j] === nk.zaman[k]) j += yon;
    this.zamanAyarla(nk.zaman[j], true);
  }

  /** Kare döngüsü (kabuktan). */
  kare(dt: number): void {
    if (!this.oynuyor || !this.is) return;
    this.t += dt * this.hiz;
    if (this.t >= this.is.sure.toplam) {
      this.t = this.is.sure.toplam;
      this.oynat(false);
    }
    this.guncelle();
  }

  /** Klavye: işlendiyse true. */
  tus(e: KeyboardEvent, hedef: HTMLElement): boolean {
    const k = e.key;
    if (k === "s" || k === "S") this.kesitDegistir();
    else if (k === "r" || k === "R") this.capDegistir();
    else if (k === " ") {
      if (hedef.matches("button")) return true;
      e.preventDefault();
      this.oynat(!this.oynuyor);
    } else if (k === "ArrowRight" || k === "ArrowLeft") {
      e.preventDefault();
      this.adim(k === "ArrowRight" ? 1 : -1);
    } else if (k === "Home") this.zamanAyarla(0, true);
    else if (k === "End" && this.is) this.zamanAyarla(this.is.sure.toplam, true);
    else if (k === "Escape") this.satirUstunde(-1);
    else return false;
    return true;
  }

  komutlar(sorgu: string): Komut[] {
    const is = this.is;
    if (!is) return [];
    const out: Komut[] = [];
    const as = anahtarSayi(sorgu);
    const isl = this.secili === null ? undefined : is.islemler[this.secili];
    if (as && isl) {
      const anahtar = (ESANLAMLI[as.anahtar] ?? []).find((a) => a in isl.parametreler);
      if (anahtar) {
        out.push({
          ad: `${PARAMETRE[anahtar]?.ad ?? anahtar} = ${as.deger}`,
          aciklama: `${isl.ad} · şu an ${isl.parametreler[anahtar]}`,
          calistir: () => void this.parametreDegistir(anahtar, as.deger),
          dinamik: true,
        });
      }
    }
    return out.concat([
      { ad: this.oynuyor ? "Duraklat" : "Oynat", aciklama: "Boşluk", calistir: () => this.oynat(!this.oynuyor) },
      { ad: "Başa dön", aciklama: "Home", calistir: () => this.zamanAyarla(0, true) },
      { ad: "Sona git", aciklama: "End · son kesit", calistir: () => this.zamanAyarla(is.sure.toplam, true) },
      { ad: this.cap ? "DRO: yarıçap" : "DRO: çap", aciklama: "R", calistir: () => this.capDegistir() },
      { ad: "G-code", aciklama: "sekme", calistir: () => this.sekmeSec("gcode") },
      { ad: "Kanıtlar", aciklama: "sekme", calistir: () => this.sekmeSec("kanit") },
      ...is.islemler.map((i) => ({
        ad: `İşlem: ${i.ad}`,
        aciklama: `${sureYaz(i.t0)} · T${i.takim.T}`,
        calistir: () => this.islemSec(i.i),
      })),
    ]);
  }

  // ----------------------------------------------------------------- kanca

  kanca() {
    return {
      kesitAcik: () => this.sahne.kesit(),
      capModu: () => this.cap,
      seciliIslem: () => (this.bekleyen ? this.bekleyen.islem : this.secili),
      dro: () => [...this.dro] as Nokta3,
      hayaletKonum: () => this.sahne.hayaletKonum(),
      zaman: () => this.t,
      gcodeSatirSayisi: () => this.mevcutIs()?.gcode.length ?? 0,
      toplamSure: () => this.mevcutIs()?.sure.toplam ?? 0,
    };
  }
}
