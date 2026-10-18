// SPEC 37 — kabuk ön yüzü: proje çubuğu, komut paleti (Ctrl K), etki kartı, sekme rozetleri,
// genel kısayollar (Ctrl Z / Ctrl Shift Z / Ctrl Y / Ctrl S / Ctrl Shift S / Ctrl O).
// Hesap yapmaz: etki kartındaki sayılar /api/proje yanıtlarından gelir.
//
// Sekme değildir (sunucuda router ve tuş yok). A3 kabuğu açılışta `baslat(kabuk, komutlar, tazele)` çağırır:
// `komutlar()` etkin ekranın ve dinamik komutların listesi, `tazele()` etkin ekranın sunucudan yeniden çekilmesi.

import { desenSayisi, eslestir } from "./kabuk_ara";
import type { EkranModulu, Kabuk, Komut } from "./tip";

/** Etki satırı (sunucunun Etki biçimi). */
export interface EtkiSatiri {
  bolum: string;
  ekran: string;
  once: Record<string, number | string>;
  sonra: Record<string, number | string>;
  fark: Record<string, number>;
}

/** GET /api/proje yanıtı. */
export interface ProjeDurumu {
  sema: number;
  ad: string;
  yol: string | null;
  kirli: boolean;
  geri_al: string | null;
  yinele: string | null;
  bolumler: string[];
  uyarilar: unknown[];
  son_etki: EtkiSatiri[] | null;
}

const ONEK = "/api/proje";
const SON_ANAHTARI = "tezgah.kabuk.son";
const ONIZLEME_GECIKMESI = 250; // ms

// ------------------------------------------------------------------ saf yardımcılar

function sayiYaz(x: number): string {
  return String(Number(Math.abs(x).toFixed(3)));
}

/** Sekme rozeti metni: ekranın ozet sırasındaki ilk sayısal farkı (işaretli). */
export function rozetMetni(satir: EtkiSatiri): string | null {
  for (const anahtar of Object.keys(satir.sonra)) {
    const f = satir.fark[anahtar];
    if (typeof f !== "number") continue;
    const isaret = f < 0 ? "−" : f > 0 ? "+" : "";
    return `${anahtar} ${isaret}${sayiYaz(f)}`;
  }
  return null;
}

/** Odak metin kutusundaysa (input, textarea, contenteditable) Ctrl Z / Ctrl Y tarayıcıya bırakılır. */
export function metinOdagi(hedef: EventTarget | null): boolean {
  if (!hedef || typeof (hedef as HTMLElement).tagName !== "string") return false;
  const e = hedef as HTMLElement;
  const ad = e.tagName.toLowerCase();
  return ad === "input" || ad === "textarea" || e.isContentEditable;
}

// ------------------------------------------------------------------ SPEC 54: hata kartı, kurtarma

/** 422 / 500 gövdesindeki `hata` alanı (tezgah/hata.py). */
export interface HataKarti {
  sinif: string;
  nesne: string;
  ne_oldu: string;
  oneri: string;
  teknik: string;
}

/** Kartın gösterilecek hali; `geriAl` = "Son değişikliği geri al" düğmesi var mı. */
export interface HataKartiModeli {
  baslik: string;
  nesne: string;
  oneri: string;
  teknik: string;
  geriAl: boolean;
}

/** GET /api/proje/kurtarma `bulunan` alanı (fileio/kurtarma.py kurtarma_bul). */
export interface KurtarmaBilgisi {
  yol: string;
  okunur: boolean;
  kaynak_tutuyor: boolean;
  farkli: boolean;
  neden: string | null;
}

export type KurtarmaSecimi = "kurtar" | "yoksay" | "ikisi";

export interface KurtarmaSecenegi {
  secim: KurtarmaSecimi;
  etiket: string;
  varsayilan: boolean;
}

/** Hata kartı modeli; `geriAl` = durumdaki geri alınabilecek değişikliğin etiketi (yoksa null). */
export function hataKartiModeli(hata: HataKarti, geriAl: string | null): HataKartiModeli {
  return { baslik: hata.ne_oldu, nesne: hata.nesne, oneri: hata.oneri, teknik: hata.teknik, geriAl: geriAl !== null };
}

/** Kurtarma iletişim kutusunun seçenekleri: Kurtar / Yok say / İkisini de aç. */
export function kurtarmaSecenekleri(b: KurtarmaBilgisi): KurtarmaSecenegi[] {
  const varsayilan: KurtarmaSecimi = b.kaynak_tutuyor ? "kurtar" : "ikisi";
  const liste: [KurtarmaSecimi, string][] = [
    ["kurtar", "Kurtar"],
    ["yoksay", "Yok say"],
    ["ikisi", "İkisini de aç"],
  ];
  return liste.map(([secim, etiket]) => ({ secim, etiket, varsayilan: secim === varsayilan }));
}

// ------------------------------------------------------------------ sunucu

class KabukHatasi extends Error {
  constructor(
    mesaj: string,
    readonly kart: HataKarti | null = null,
  ) {
    super(mesaj);
  }
}

function kartAl(j: { hata?: unknown }): HataKarti | null {
  const h = j.hata as HataKarti | undefined;
  return h && typeof h.ne_oldu === "string" ? h : null;
}

async function istek<T>(yol: string, govde?: unknown): Promise<T> {
  const y = await fetch(ONEK + yol, {
    method: govde === undefined ? "GET" : "POST",
    headers: govde === undefined ? undefined : { "Content-Type": "application/json" },
    body: govde === undefined ? undefined : JSON.stringify(govde),
  });
  const j = await y.json().catch(() => ({}));
  if (!y.ok) throw new KabukHatasi(typeof j.detail === "string" ? j.detail : `${y.status}`, kartAl(j));
  return j as T;
}

interface DegisimYaniti {
  etki: EtkiSatiri[];
  proje: ProjeDurumu;
}

// ------------------------------------------------------------------ stil

const STIL = `
.kb-cubuk{position:fixed;top:8px;right:8px;z-index:40;display:flex;gap:6px;align-items:center;max-width:calc(100vw - 32px);
  font:12px/1.3 system-ui,sans-serif;background:var(--panel,#1b1d22);color:var(--metin,#e8e6e3);border:1px solid #3a3d45;
  border-radius:8px;padding:4px 8px;box-sizing:border-box}
.kb-cubuk .kb-ad{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.kb-cubuk button,.kb-palet button{font:inherit;color:inherit;background:transparent;border:1px solid #3a3d45;border-radius:6px;
  padding:2px 8px;cursor:pointer}
.kb-cubuk button:disabled{opacity:.4;cursor:default}
.kb-perde{position:fixed;inset:0;z-index:50;background:rgba(0,0,0,.35);display:flex;justify-content:center;
  align-items:flex-start;padding:10vh 16px 0;box-sizing:border-box}
.kb-palet{width:min(640px,100%);max-width:100%;box-sizing:border-box;background:var(--panel,#1b1d22);color:var(--metin,#e8e6e3);
  border:1px solid #4a4e58;border-radius:12px;box-shadow:0 18px 48px rgba(0,0,0,.45);font:14px/1.35 system-ui,sans-serif;
  overflow:hidden}
.kb-palet input{width:100%;box-sizing:border-box;border:0;border-bottom:1px solid #3a3d45;background:transparent;color:inherit;
  font:inherit;font-size:16px;padding:12px 14px}
.kb-liste{max-height:40vh;overflow:auto;margin:0;padding:4px;list-style:none}
.kb-liste li{padding:7px 10px;border-radius:8px;display:flex;justify-content:space-between;gap:8px;cursor:pointer;
  overflow-wrap:anywhere}
.kb-liste li[aria-selected="true"]{background:#2c3140}
.kb-liste .kb-ek{opacity:.6;font-size:12px;white-space:nowrap}
.kb-etki{border-top:1px solid #3a3d45;padding:8px 12px;font-size:13px;overflow-wrap:anywhere}
.kb-etki table{width:100%;border-collapse:collapse;table-layout:fixed}
.kb-etki td{padding:2px 4px;vertical-align:top;overflow-wrap:anywhere}
.kb-etki .kb-eksi{color:#7fd18b}.kb-etki .kb-arti{color:#f0a35e}
.kb-not{padding:6px 12px;font-size:12px;opacity:.75}
.kb-hata{padding:6px 12px;font-size:12px;color:#ff8a80}
.kb-bildirim{position:fixed;bottom:16px;right:16px;z-index:45;max-width:calc(100vw - 32px);box-sizing:border-box;
  background:var(--panel,#1b1d22);color:var(--metin,#e8e6e3);border:1px solid #4a4e58;border-radius:10px;
  font:13px/1.35 system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.4)}
.kb-palet :is(button,input,[role="option"],a,[tabindex]):focus,.kb-cubuk button:focus,.kb-bildirim button:focus{
  outline:2px solid #8ab4ff;outline-offset:-2px}
.kb-kart{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);z-index:46;width:min(560px,calc(100vw - 32px));
  box-sizing:border-box;background:var(--panel,#1b1d22);color:var(--metin,#e8e6e3);border:1px solid #8a4b4b;
  border-left:4px solid #ff8a80;border-radius:10px;padding:10px 12px;font:13px/1.4 system-ui,sans-serif;
  box-shadow:0 10px 30px rgba(0,0,0,.45);overflow-wrap:anywhere}
.kb-kart [data-alan="ne_oldu"]{font-weight:600;font-size:14px}
.kb-kart [data-alan="nesne"]{opacity:.7;font-size:12px}
.kb-kart [data-alan="oneri"]{margin-top:4px}
.kb-kart details{margin-top:6px;font-size:12px}
.kb-kart pre{max-height:30vh;overflow:auto;white-space:pre-wrap;margin:4px 0 0;opacity:.8}
.kb-kart .kb-eylem{display:flex;gap:6px;margin-top:8px;justify-content:flex-end}
.kb-kart button,.kb-kutu button{font:inherit;color:inherit;background:transparent;border:1px solid #4a4e58;border-radius:6px;
  padding:3px 10px;cursor:pointer}
.kb-kutu{max-width:min(480px,calc(100vw - 32px));box-sizing:border-box;background:var(--panel,#1b1d22);
  color:var(--metin,#e8e6e3);border:1px solid #4a4e58;border-radius:12px;font:14px/1.4 system-ui,sans-serif;padding:14px}
.kb-kutu::backdrop{background:rgba(0,0,0,.4)}
.kb-kutu p{margin:0 0 10px;overflow-wrap:anywhere}
.kb-kutu .kb-eylem{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.kb-kutu button[data-varsayilan]{border-color:#8ab4ff}
.kb-kart button:focus,.kb-kutu button:focus{outline:2px solid #8ab4ff;outline-offset:1px}
`;

// ------------------------------------------------------------------ kabuk

type Kip = { tur: "komut" } | { tur: "yol"; amac: "ac" | "kaydet" };

class KabukOnYuz {
  private durum: ProjeDurumu | null = null;
  private etkiGosterilen: EtkiSatiri[] | null = null;
  private kip: Kip = { tur: "komut" };
  private aday: Komut[] = [];
  private secili = 0;
  private onizSayac = 0;
  private onizUcusta = false;
  private onizBekleyen = false;
  private onizZaman: number | undefined;
  private ornekler: string[] = [];
  private sekmeler: { ad: string; baslik: string }[] = [];
  private rozetli = new Set<string>();

  private cubuk = document.createElement("div");
  private perde = document.createElement("div");
  private girdi = document.createElement("input");
  private liste = document.createElement("ul");
  private etkiKutu = document.createElement("div");
  private notKutu = document.createElement("div");
  private bildirim = document.createElement("div");
  private dosya = document.createElement("input");
  private kart = document.createElement("div");

  constructor(
    private kabuk: Kabuk,
    private ekranKomutlari: () => Komut[],
    private tazele: () => Promise<void>,
  ) {}

  baslat(): void {
    const stil = document.createElement("style");
    stil.textContent = STIL;
    document.head.append(stil);
    this.cubukKur();
    this.paletKur();
    this.bildirim.className = "kb-bildirim";
    this.bildirim.hidden = true;
    this.dosya.type = "file";
    this.dosya.accept = ".3dc";
    this.dosya.hidden = true;
    this.dosya.addEventListener("change", () => void this.dosyaYukle());
    this.kart.className = "kb-kart";
    this.kart.setAttribute("data-testid", "hata-karti");
    this.kart.setAttribute("role", "alert");
    this.kart.hidden = true;
    document.body.append(this.cubuk, this.perde, this.bildirim, this.dosya, this.kart);
    window.addEventListener("keydown", (e) => this.tus(e), true);
    window.addEventListener("beforeunload", (e) => {
      if (this.durum?.kirli) e.preventDefault();
    });
    Object.assign(this.kabuk.kanca, {
      proje: () => this.durum,
      etki: () => this.etkiGosterilen,
      palet: () => this.aday.map((k) => k.baslik),
    });
    void this.yukleBaslangic();
  }

  private async yukleBaslangic(): Promise<void> {
    try {
      this.ornekler = (await istek<{ ornekler: string[] }>("/ornekler")).ornekler;
      const e = await fetch("/api/ekranlar").then((y) => (y.ok ? y.json() : { ekranlar: [] }));
      this.sekmeler = (e.ekranlar ?? []).filter((x: { hazir: boolean }) => x.hazir);
    } catch {
      /* örnek ve sekme listesi olmadan da palet çalışır */
    }
    await this.yenile(false);
    await this.kurtarmaSor();
  }

  // ---------------------------------------------------------------- SPEC 54: hata kartı, kurtarma

  private hataKartiGoster(hata: HataKarti): void {
    const m = hataKartiModeli(hata, this.durum?.geri_al ?? null);
    const alan = (ad: string, metin: string): HTMLDivElement => {
      const d = document.createElement("div");
      d.setAttribute("data-alan", ad);
      d.textContent = metin;
      return d;
    };
    const ayrinti = document.createElement("details");
    ayrinti.setAttribute("data-alan", "teknik");
    const ozet = document.createElement("summary");
    ozet.textContent = "Ayrıntı";
    const pre = document.createElement("pre");
    pre.textContent = m.teknik;
    ayrinti.append(ozet, pre);
    const eylem = document.createElement("div");
    eylem.className = "kb-eylem";
    if (m.geriAl) {
      const g = document.createElement("button");
      g.setAttribute("data-eylem", "geri-al");
      g.textContent = "Son değişikliği geri al";
      g.addEventListener("click", () => {
        this.kart.hidden = true;
        void this.geriAl();
      });
      eylem.append(g);
    }
    const kapat = document.createElement("button");
    kapat.textContent = "Kapat";
    kapat.addEventListener("click", () => (this.kart.hidden = true));
    eylem.append(kapat);
    this.kart.replaceChildren(alan("ne_oldu", m.baslik), alan("nesne", m.nesne), alan("oneri", m.oneri), ayrinti, eylem);
    this.kart.hidden = false;
  }

  /** Açılışta ve proje açıldıktan sonra: kurtarma dosyası önerisi ve uyarıları. */
  private async kurtarmaSor(): Promise<void> {
    let d: { bulunan: KurtarmaBilgisi | null; uyarilar: string[] };
    try {
      d = await istek("/kurtarma");
    } catch {
      return; // kurtarma ucu yoksa (eski sunucu) açılış sürer
    }
    for (const u of d.uyarilar ?? []) this.bildir(u);
    const b = d.bulunan;
    if (b && b.okunur && b.farkli) this.kurtarmaKutusu(b);
  }

  private kurtarmaKutusu(b: KurtarmaBilgisi): void {
    const kutu = document.createElement("dialog");
    kutu.className = "kb-kutu";
    kutu.setAttribute("data-testid", "kurtarma");
    kutu.setAttribute("aria-label", "Kurtarma dosyası bulundu");
    const metin = document.createElement("p");
    metin.textContent = b.kaynak_tutuyor
      ? "Bu proje için kaydedilmemiş değişiklikler içeren bir kurtarma dosyası bulundu."
      : "Bir kurtarma dosyası bulundu, ama proje dosyası o yazıldıktan sonra başka yerde değişmiş. " +
        "İkisini de açmanız önerilir.";
    const eylem = document.createElement("div");
    eylem.className = "kb-eylem";
    const dugmeler: HTMLButtonElement[] = [];
    for (const s of kurtarmaSecenekleri(b)) {
      const d = document.createElement("button");
      d.type = "button";
      d.setAttribute("data-secim", s.secim);
      d.textContent = s.etiket;
      if (s.varsayilan) d.setAttribute("data-varsayilan", "");
      d.addEventListener("click", () => {
        kutu.close();
        void this.kurtarmaSec(s.secim);
      });
      dugmeler.push(d);
      eylem.append(d);
    }
    kutu.append(metin, eylem);
    kutu.addEventListener("keydown", (e) => {
      if (e.key !== "Tab") return;
      e.preventDefault(); // odak kutunun düğmeleri arasında döner
      const i = dugmeler.indexOf(document.activeElement as HTMLButtonElement);
      const n = dugmeler.length;
      dugmeler[(i + (e.shiftKey ? n - 1 : 1) + n) % n].focus();
    });
    kutu.addEventListener("close", () => kutu.remove());
    document.body.append(kutu);
    kutu.showModal();
    (dugmeler.find((d) => d.hasAttribute("data-varsayilan")) ?? dugmeler[0]).focus();
  }

  private async kurtarmaSec(secim: KurtarmaSecimi): Promise<void> {
    await this.dene(async () => {
      const r = await istek<{ proje: ProjeDurumu; kopya: string | null }>("/kurtarma", { secim });
      const not = secim === "kurtar" ? "Kurtarıldı" : r.kopya ? `Kurtarılan kopya: ${r.kopya}` : "Yok sayıldı";
      await this.sonrasi(null, not);
    });
  }

  // ---------------------------------------------------------------- proje çubuğu

  private cubukKur(): void {
    this.cubuk.className = "kb-cubuk";
    this.cubuk.setAttribute("role", "toolbar");
    this.cubuk.setAttribute("aria-label", "Proje");
  }

  private cubukCiz(): void {
    const d = this.durum;
    if (!d) return;
    this.cubuk.replaceChildren();
    const ad = document.createElement("span");
    ad.className = "kb-ad";
    ad.textContent = `${d.ad}${d.kirli ? " •" : ""}`;
    ad.title = d.yol ?? "kaydedilmedi";
    const geri = this.dugme("↶", `Geri al${d.geri_al ? `: ${d.geri_al}` : ""} (Ctrl Z)`, () => this.geriAl());
    geri.disabled = d.geri_al === null;
    const ileri = this.dugme("↷", `Yinele${d.yinele ? `: ${d.yinele}` : ""} (Ctrl Shift Z)`, () => this.yinele());
    ileri.disabled = d.yinele === null;
    const palet = this.dugme("⌘K", "Komut paleti (Ctrl K)", () => this.paletAc());
    this.cubuk.append(ad, geri, ileri, palet);
    const temel = document.title.replace(/^.* — /, "").replace(/ •$/, "") || "Tezgah";
    document.title = `${d.ad}${d.kirli ? " •" : ""} — ${temel === d.ad ? "Tezgah" : temel}`;
  }

  private dugme(metin: string, ipucu: string, f: () => void): HTMLButtonElement {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = metin;
    b.title = ipucu;
    b.setAttribute("aria-label", ipucu);
    b.addEventListener("click", f);
    return b;
  }

  // ---------------------------------------------------------------- palet

  private paletKur(): void {
    this.perde.className = "kb-perde";
    this.perde.hidden = true;
    this.perde.addEventListener("mousedown", (e) => {
      if (e.target === this.perde) this.paletKapat();
    });
    const kutu = document.createElement("div");
    kutu.className = "kb-palet";
    kutu.dataset.testid = "komut-paleti";
    kutu.setAttribute("role", "dialog");
    kutu.setAttribute("aria-label", "Komut paleti");
    this.girdi.dataset.testid = "palet-girdi";
    this.girdi.setAttribute("aria-label", "Komut ara");
    this.girdi.autocomplete = "off";
    this.girdi.spellcheck = false;
    this.girdi.addEventListener("input", () => this.sorguDegisti());
    this.girdi.addEventListener("keydown", (e) => this.paletTusu(e));
    this.liste.className = "kb-liste";
    this.liste.setAttribute("role", "listbox");
    this.etkiKutu.className = "kb-etki";
    this.etkiKutu.dataset.testid = "etki-karti";
    this.etkiKutu.hidden = true;
    this.notKutu.className = "kb-not";
    kutu.append(this.girdi, this.liste, this.notKutu, this.etkiKutu);
    this.perde.append(kutu);
  }

  private paletAcik(): boolean {
    return !this.perde.hidden;
  }

  private paletAc(kip: Kip = { tur: "komut" }): void {
    this.kip = kip;
    this.perde.hidden = false;
    this.girdi.value = kip.tur === "yol" && kip.amac === "kaydet" ? (this.durum?.yol ?? "") : "";
    this.girdi.placeholder =
      kip.tur === "komut" ? "Komut ya da parametre yazın (ör. L 9.5)" : "Dosya yolu (.3dc), Enter";
    this.etkiGoster(null);
    this.sorguDegisti();
    this.girdi.focus();
  }

  private paletKapat(): void {
    this.perde.hidden = true;
    this.onizSayac++;
    this.etkiGoster(null);
  }

  private tumKomutlar(): Komut[] {
    return [...this.kabukKomutlari(), ...this.ekranKomutlari()];
  }

  /** Kabuğun kendi komutları (Yeni, Aç, Kaydet, Farklı kaydet, İndir, Yükle, Geri al, Yinele, geçiş, örnekler). */
  private kabukKomutlari(): Komut[] {
    const k: Komut[] = [
      { kimlik: "kabuk.yeni", baslik: "Yeni proje", anahtar_kelimeler: ["new"], calistir: () => this.yeni() },
      { kimlik: "kabuk.ac", baslik: "Aç…", kisayol: "Ctrl+O", anahtar_kelimeler: ["open", "dosya"],
        calistir: () => this.paletAc({ tur: "yol", amac: "ac" }) },
      { kimlik: "kabuk.kaydet", baslik: "Kaydet", kisayol: "Ctrl+S", anahtar_kelimeler: ["save"],
        calistir: () => this.kaydet(false) },
      { kimlik: "kabuk.farkli", baslik: "Farklı kaydet…", kisayol: "Ctrl+Shift+S", anahtar_kelimeler: ["save as"],
        calistir: () => this.kaydet(true) },
      { kimlik: "kabuk.indir", baslik: "Dosyayı indir", anahtar_kelimeler: ["download", ".3dc"],
        calistir: () => this.indir() },
      { kimlik: "kabuk.yukle", baslik: "Dosya yükle", anahtar_kelimeler: ["upload", ".3dc"],
        calistir: () => this.dosya.click() },
      { kimlik: "kabuk.geri", baslik: "Geri al", kisayol: "Ctrl+Z", anahtar_kelimeler: ["undo"],
        calistir: () => this.geriAl() },
      { kimlik: "kabuk.yinele", baslik: "Yinele", kisayol: "Ctrl+Shift+Z", anahtar_kelimeler: ["redo"],
        calistir: () => this.yinele() },
    ];
    for (const s of this.sekmeler) {
      k.push({ kimlik: `kabuk.git.${s.ad}`, baslik: `${s.baslik} ekranına geç`, anahtar_kelimeler: [s.ad],
               calistir: () => this.kabuk.git(`#/${s.ad}`) });
    }
    for (const o of this.ornekler) {
      k.push({ kimlik: `kabuk.ornek.${o}`, baslik: `Örnek proje: ${o.replace(/_/g, " ")}`,
               anahtar_kelimeler: ["örnek", o], calistir: () => this.ornek(o) });
    }
    return k;
  }

  private son(): string[] {
    try {
      return JSON.parse(localStorage.getItem(SON_ANAHTARI) ?? "[]");
    } catch {
      return [];
    }
  }

  private sonaEkle(kimlik: string): void {
    try {
      const s = [kimlik, ...this.son().filter((x) => x !== kimlik)].slice(0, 20);
      localStorage.setItem(SON_ANAHTARI, JSON.stringify(s));
    } catch {
      /* depolama yoksa sıra yalnız bu oturumda */
    }
  }

  private sorguDegisti(): void {
    if (this.kip.tur === "yol") {
      this.aday = [];
      this.liste.replaceChildren();
      this.notKutu.textContent =
        this.kip.amac === "ac" ? "Açılacak .3dc dosyasının yolu" : "Kaydedilecek .3dc dosyasının yolu";
      return;
    }
    this.aday = eslestir(this.girdi.value, this.tumKomutlar(), this.son());
    this.secili = 0;
    this.listeCiz();
    this.onizlemeZamanla();
  }

  private listeCiz(): void {
    this.liste.replaceChildren();
    this.notKutu.textContent = "";
    const q = this.girdi.value;
    this.aday.slice(0, 50).forEach((k, i) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.tabIndex = -1;
      li.setAttribute("aria-selected", String(i === this.secili));
      const ad = document.createElement("span");
      ad.textContent = k.baslik;
      const ek = document.createElement("span");
      ek.className = "kb-ek";
      if (k.desen) {
        const s = desenSayisi(k.desen, q);
        ek.textContent = s === null ? k.desen : `= ${s}`;
      } else ek.textContent = k.kisayol ?? "";
      li.append(ad, ek);
      li.addEventListener("mousemove", () => this.sec(i));
      li.addEventListener("click", () => void this.calistir(i));
      this.liste.append(li);
    });
    if (this.aday.length === 0 && q.trim()) this.notKutu.textContent = "Eşleşen komut yok";
    else if (this.aday[0]?.desen && desenSayisi(this.aday[0].desen, q) === null && q.trim())
      this.notKutu.textContent = `Geçersiz değer: ${this.aday[0].desen}`;
  }

  private sec(i: number): void {
    if (i === this.secili) return;
    this.secili = i;
    this.liste.querySelectorAll("li").forEach((li, j) => li.setAttribute("aria-selected", String(j === i)));
    (this.liste.children[i] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest" });
    this.onizlemeZamanla();
  }

  private paletTusu(e: KeyboardEvent): void {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = Math.min(this.aday.length, 50);
      if (n) this.sec((this.secili + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
    } else if (e.key === "Enter") {
      e.preventDefault();
      void this.calistir(this.secili);
    } else if (e.key === "Escape") {
      e.preventDefault();
      this.paletKapat();
    }
  }

  /** Seçili komut parametreli ve önizlenebilirse yamaları; değilse null. */
  private yamalar(k: Komut | undefined): { sayi: number; yama: ReturnType<NonNullable<Komut["yama"]>> } | null {
    if (!k?.desen || !k.yama) return null;
    const sayi = desenSayisi(k.desen, this.girdi.value);
    return sayi === null ? null : { sayi, yama: k.yama(sayi) };
  }

  private onizlemeZamanla(): void {
    window.clearTimeout(this.onizZaman);
    const sayac = ++this.onizSayac;
    if (!this.yamalar(this.aday[this.secili])) {
      this.etkiGoster(null);
      return;
    }
    this.onizZaman = window.setTimeout(() => void this.onizle(sayac), ONIZLEME_GECIKMESI);
  }

  private async onizle(sayac: number): Promise<void> {
    if (this.onizUcusta) {
      this.onizBekleyen = true;
      return;
    }
    const y = this.yamalar(this.aday[this.secili]);
    if (!y || sayac !== this.onizSayac) return;
    this.onizUcusta = true;
    try {
      const r = await istek<DegisimYaniti>("/degistir", {
        etiket: this.girdi.value.trim(),
        yamalar: y.yama,
        onizle: true,
      });
      if (sayac === this.onizSayac && this.paletAcik()) this.etkiGoster(r.etki, "Önizleme (uygulanmadı)");
    } catch (e) {
      if (sayac === this.onizSayac) this.hataGoster(e);
    } finally {
      this.onizUcusta = false;
      if (this.onizBekleyen) {
        this.onizBekleyen = false;
        void this.onizle(this.onizSayac);
      }
    }
  }

  private async calistir(i: number): Promise<void> {
    if (this.kip.tur === "yol") {
      const yol = this.girdi.value.trim();
      if (!yol) return;
      await this.dene(async () => {
        const acildi = this.kip.tur === "yol" && this.kip.amac === "ac";
        if (acildi) await istek("/ac", { yol });
        else await istek("/kaydet", { yol });
        this.paletKapat();
        await this.yenile(true);
        if (acildi) await this.kurtarmaSor();
      });
      return;
    }
    const k = this.aday[i];
    if (!k) return;
    this.sonaEkle(k.kimlik);
    const y = this.yamalar(k);
    if (y) {
      this.onizSayac++;
      await this.dene(async () => {
        const r = await istek<DegisimYaniti>("/degistir", {
          etiket: this.girdi.value.trim(),
          yamalar: y.yama,
          onizle: false,
        });
        this.paletKapat();
        await this.sonrasi(r.etki, null);
      });
      return;
    }
    if (k.desen) {
      const sayi = desenSayisi(k.desen, this.girdi.value);
      if (sayi === null) return;
      this.paletKapat();
      await this.dene(async () => k.calistir(sayi));
      return;
    }
    this.paletKapat();
    await this.dene(async () => k.calistir());
  }

  // ---------------------------------------------------------------- etki kartı ve rozetler

  private etkiGoster(etki: EtkiSatiri[] | null, baslik = ""): void {
    this.etkiGosterilen = etki;
    this.etkiKutu.replaceChildren();
    this.etkiKutu.hidden = etki === null;
    if (!etki) return;
    const b = document.createElement("div");
    b.className = "kb-not";
    b.textContent = etki.length ? baslik : "Değişiklik yok";
    const tablo = document.createElement("table");
    for (const s of etki) {
      for (const [anahtar, f] of Object.entries(s.fark)) {
        const tr = tablo.insertRow();
        tr.insertCell().textContent = `${s.ekran} · ${anahtar}`;
        tr.insertCell().textContent = `${s.once[anahtar]} → ${s.sonra[anahtar]}`;
        const c = tr.insertCell();
        c.textContent = f === 0 ? "0" : `${f < 0 ? "−" : "+"}${sayiYaz(f)}`;
        c.className = f < 0 ? "kb-eksi" : f > 0 ? "kb-arti" : "";
      }
      for (const anahtar of Object.keys(s.sonra)) {
        if (anahtar in s.fark || s.once[anahtar] === s.sonra[anahtar]) continue;
        const tr = tablo.insertRow();
        tr.insertCell().textContent = `${s.ekran} · ${anahtar}`;
        tr.insertCell().textContent = `${s.once[anahtar] ?? "—"} → ${s.sonra[anahtar]}`;
        tr.insertCell();
      }
    }
    this.etkiKutu.append(b, tablo);
  }

  private hataGoster(e: unknown): void {
    this.etkiKutu.hidden = false;
    this.etkiGosterilen = null;
    const d = document.createElement("div");
    d.className = "kb-hata";
    d.textContent = e instanceof Error ? e.message : String(e);
    this.etkiKutu.replaceChildren(d);
  }

  private rozetle(etki: EtkiSatiri[] | null): void {
    for (const ekran of this.rozetli) this.kabuk.rozet(ekran, null);
    this.rozetli.clear();
    for (const s of etki ?? []) {
      const m = rozetMetni(s);
      if (m === null || this.rozetli.has(s.ekran)) continue;
      this.kabuk.rozet(s.ekran, m);
      this.rozetli.add(s.ekran);
    }
  }

  private bildir(metin: string): void {
    this.bildirim.replaceChildren();
    const s = document.createElement("div");
    s.className = "kb-not";
    s.textContent = metin;
    this.bildirim.append(s);
    this.bildirim.hidden = false;
    window.setTimeout(() => (this.bildirim.hidden = true), 4000);
  }

  // ---------------------------------------------------------------- işlemler

  private async dene(f: () => Promise<unknown>): Promise<void> {
    try {
      await f();
    } catch (e) {
      if (this.paletAcik()) this.hataGoster(e);
      else if (e instanceof KabukHatasi && e.kart) this.hataKartiGoster(e.kart);
      else this.bildir(e instanceof Error ? e.message : String(e));
    }
  }

  /** Sunucu durumu değişti: proje durumunu çek, rozetleri ve etkin ekranı tazele. */
  async yenile(ekraniTazele: boolean): Promise<void> {
    this.durum = await istek<ProjeDurumu>("");
    this.cubukCiz();
    if (ekraniTazele) await this.tazele();
  }

  private async sonrasi(etki: EtkiSatiri[] | null, not: string | null): Promise<void> {
    this.rozetle(etki);
    await this.yenile(true);
    if (not) this.bildir(not);
  }

  private async geriAl(): Promise<void> {
    const etiket = this.durum?.geri_al;
    if (!etiket) return;
    await this.dene(async () => {
      const r = await istek<DegisimYaniti>("/geri-al", {});
      await this.sonrasi(r.etki, `Geri alındı: ${etiket}`);
    });
  }

  private async yinele(): Promise<void> {
    const etiket = this.durum?.yinele;
    if (!etiket) return;
    await this.dene(async () => {
      const r = await istek<DegisimYaniti>("/yinele", {});
      await this.sonrasi(r.etki, `Yinelendi: ${etiket}`);
    });
  }

  private async kaydet(farkli: boolean): Promise<void> {
    if (farkli || !this.durum?.yol) {
      this.paletAc({ tur: "yol", amac: "kaydet" });
      return;
    }
    await this.dene(async () => {
      await istek("/kaydet", {});
      await this.yenile(false);
      this.bildir(`Kaydedildi: ${this.durum?.yol ?? ""}`);
    });
  }

  private async yeni(): Promise<void> {
    await this.dene(async () => {
      await istek("/yeni", { ad: "adsız" });
      await this.sonrasi(null, null);
    });
  }

  private async ornek(ad: string): Promise<void> {
    await this.dene(async () => {
      await istek(`/ornek/${encodeURIComponent(ad)}`, {});
      await this.sonrasi(null, null);
    });
  }

  private indir(): void {
    const a = document.createElement("a");
    a.href = `${ONEK}/indir`;
    a.download = "";
    document.body.append(a);
    a.click();
    a.remove();
  }

  private async dosyaYukle(): Promise<void> {
    const f = this.dosya.files?.[0];
    this.dosya.value = "";
    if (!f) return;
    await this.dene(async () => {
      const y = await fetch(`${ONEK}/yukle`, { method: "POST", body: await f.arrayBuffer() });
      if (!y.ok) {
        const j = await y.json().catch(() => ({}));
        throw new KabukHatasi(j.detail ?? `${y.status}`, kartAl(j));
      }
      await this.sonrasi(null, `Açıldı: ${f.name}`);
    });
  }

  /** Bir ekranın kendi ucundan sonra (A3 `degisiklikSonrasi`): son etkinin rozetleri ve proje çubuğu. */
  async ekranDegisti(): Promise<void> {
    await this.dene(async () => {
      this.durum = await istek<ProjeDurumu>("");
      this.cubukCiz();
      this.rozetle(this.durum.son_etki);
    });
  }

  // ---------------------------------------------------------------- genel kısayollar

  private tus(e: KeyboardEvent): void {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const t = e.key.toLowerCase();
    if (t === "k") {
      e.preventDefault();
      if (this.paletAcik()) this.paletKapat();
      else this.paletAc();
    } else if (t === "z" || t === "y") {
      if (metinOdagi(e.target)) return;
      e.preventDefault();
      if (t === "z" && !e.shiftKey) void this.geriAl();
      else void this.yinele();
    } else if (t === "s") {
      e.preventDefault();
      void this.kaydet(e.shiftKey);
    } else if (t === "o") {
      e.preventDefault();
      this.paletAc({ tur: "yol", amac: "ac" });
    }
  }
}

let etkin: KabukOnYuz | null = null;

/**
 * Kabuğu başlatır (A3 kabuğu açılışta bir kez çağırır). `komutlar`: etkin ekranın ve dinamik komutların
 * listesi; `tazele`: geri al / aç sonrası etkin ekranın sunucudan yeniden çekilmesi.
 */
export function baslat(kabuk: Kabuk, komutlar: () => Komut[], tazele: () => Promise<void>): void {
  if (etkin) return;
  etkin = new KabukOnYuz(kabuk, komutlar, tazele);
  etkin.baslat();
}

/** Ekranların durum değiştiren isteklerinden sonra (A3 `degisiklikSonrasi` aboneliği). */
export function ekranDegisti(): Promise<void> {
  return etkin ? etkin.ekranDegisti() : Promise.resolve();
}

// Sekme değildir: sunucu kabuğu sekme olarak listelemez (router ve tuş yok), bu modül yalnız A3 kaydına uyar.
const ekran: EkranModulu = {
  ad: "kabuk",
  baslik: "Proje",
  async ac() {
    /* sekme açılmaz */
  },
  kapat() {
    /* sekme kapanmaz */
  },
};

export default ekran;
