// SPEC 62 — komut paleti (Ctrl+K, kabuk kancası): açılır katman. Sekme değildir, varsayılan dışa aktarım yok.
// Yazılan metin önce etkin ekranın komutlarında aranır; eşleşme yoksa sunucuda dilbilgisiyle çözülür
// (POST /api/ekran/komut/cozumle). Enter önizler, ikinci Enter uygular, Esc vazgeçer.
// Uygulama (POST /uygula) ikinci aşamadadır (SPEC 37 geri al bekliyor); şimdilik önizleme gösterilir.
// Tuşlar kendi öğelerimizde dinlenir: palet açıkken kabuk document tuşlarını ekranlara geçirmez.
// Saf fonksiyonlar (yanitGecerliMi, komutSuz) vitest ile sınanır.

import type { Kabuk, Komut } from "./tip";

const UC = "/api/ekran/komut/cozumle";

/** Uçuştaki isteklerden yalnız en son gönderilenin yanıtı kullanılır (sira artan). */
export function yanitGecerliMi(yanitSira: number, sonGonderilen: number): boolean {
  return yanitSira === sonGonderilen;
}

/** Komutları metne göre süzer: başlık ya da anahtar sözcük, büyük/küçük harf (Türkçe) gözetmeden; sıra korunur. */
export function komutSuz(komutlar: Komut[], metin: string): Komut[] {
  const q = metin.trim().toLocaleLowerCase("tr");
  if (q === "") return komutlar.slice();
  return komutlar.filter((k) =>
    [k.baslik, ...(k.anahtar_kelimeler ?? [])].some((s) => s.toLocaleLowerCase("tr").includes(q)),
  );
}

interface Cozum {
  sema: number;
  adim: Record<string, unknown>;
  aciklama: string;
}

interface CozumHatasi {
  detail: string;
  oneriler: string[];
  okumalar: string[];
}

interface Durum {
  kok: HTMLElement;
  girdi: HTMLInputElement;
  liste: HTMLElement;
  onizleme: HTMLElement;
  komutlar: () => Komut[];
  kabuk: Kabuk;
  onceki: Element | null;
  sira: number;
  secili: number;
  cozum: Cozum | null;
  onizlenen: string | null;
}

let D: Durum | null = null;

export function paletAcik(): boolean {
  return D !== null;
}

export function paletAc(kabuk: Kabuk, komutlar: () => Komut[]): void {
  if (D !== null) return;
  const kok = document.createElement("div");
  kok.className = "komut-palet";
  kok.setAttribute("role", "dialog");
  kok.setAttribute("aria-label", "Komut paleti");
  Object.assign(kok.style, {
    position: "fixed",
    top: "12%",
    left: "50%",
    transform: "translateX(-50%)",
    width: "min(640px, 92vw)",
    background: "var(--panel, #1e1f24)",
    color: "var(--yazi, #e8e8e8)",
    border: "1px solid var(--cizgi, #444)",
    borderRadius: "8px",
    boxShadow: "0 12px 40px rgba(0,0,0,.45)",
    zIndex: "1000",
    font: "14px system-ui, sans-serif",
  });
  const girdi = document.createElement("input");
  girdi.type = "text";
  girdi.placeholder = "Komut ya da işlem: 'Ø10 delik, 20 derin, H7'";
  girdi.setAttribute("aria-label", "Komut");
  Object.assign(girdi.style, {
    width: "100%",
    boxSizing: "border-box",
    padding: "12px 14px",
    font: "inherit",
    fontSize: "16px",
    background: "transparent",
    color: "inherit",
    border: "none",
    borderBottom: "1px solid var(--cizgi, #444)",
    outline: "none",
  });
  const liste = document.createElement("ul");
  liste.setAttribute("role", "listbox");
  Object.assign(liste.style, { listStyle: "none", margin: "0", padding: "4px 0", maxHeight: "40vh", overflowY: "auto" });
  const onizleme = document.createElement("div");
  onizleme.setAttribute("aria-live", "polite");
  Object.assign(onizleme.style, { padding: "8px 14px", minHeight: "1.4em", whiteSpace: "pre-wrap" });
  kok.append(girdi, liste, onizleme);
  document.body.append(kok);

  D = {
    kok,
    girdi,
    liste,
    onizleme,
    komutlar,
    kabuk,
    onceki: document.activeElement,
    sira: 0,
    secili: 0,
    cozum: null,
    onizlenen: null,
  };
  girdi.addEventListener("input", girdiDegisti);
  girdi.addEventListener("keydown", tusBasildi);
  kanca();
  listeyiCiz();
  girdi.focus();
}

export function paletKapat(): void {
  if (D === null) return;
  const { kok, onceki } = D;
  D = null;
  kok.remove();
  kanca();
  if (onceki instanceof HTMLElement && document.contains(onceki)) onceki.focus();
}

function kanca(): void {
  const k = window as unknown as { __tezgah?: Record<string, unknown> };
  const t = (k.__tezgah ??= {});
  t.komut = { acik: D !== null, sira: D?.sira ?? 0, cozum: D?.cozum ?? null };
}

function eslesenler(): Komut[] {
  return D === null ? [] : komutSuz(D.komutlar(), D.girdi.value);
}

function listeyiCiz(): void {
  if (D === null) return;
  const L = eslesenler();
  D.secili = Math.min(D.secili, Math.max(L.length - 1, 0));
  D.liste.replaceChildren(
    ...L.map((k, i) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(i === D!.secili));
      li.textContent = k.kisayol ? `${k.baslik}   ${k.kisayol}` : k.baslik;
      Object.assign(li.style, {
        padding: "6px 14px",
        cursor: "pointer",
        background: i === D!.secili ? "var(--secili, #2f4f7f)" : "transparent",
      });
      li.addEventListener("mousedown", (e) => {
        e.preventDefault();
        void calistir(k);
      });
      return li;
    }),
  );
}

function girdiDegisti(): void {
  if (D === null) return;
  D.cozum = null;
  D.onizlenen = null;
  D.secili = 0;
  D.onizleme.textContent = "";
  listeyiCiz();
}

function tusBasildi(e: KeyboardEvent): void {
  if (D === null) return;
  const L = eslesenler();
  if (e.key === "Escape") {
    e.preventDefault();
    paletKapat();
  } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (L.length === 0) return;
    D.secili = (D.secili + (e.key === "ArrowDown" ? 1 : L.length - 1)) % L.length;
    listeyiCiz();
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (L.length > 0 && D.girdi.value.trim() !== "") void calistir(L[D.secili]);
    else if (D.girdi.value.trim() !== "") void enter(D.girdi.value);
  }
  e.stopPropagation();
}

async function calistir(k: Komut): Promise<void> {
  paletKapat();
  await k.calistir();
}

async function enter(metin: string): Promise<void> {
  if (D === null) return;
  if (D.cozum !== null && D.onizlenen === metin) {
    // ikinci Enter: uygulama ikinci aşamada (SPEC 37 geri al); önizleme yerinde kalır
    D.onizleme.textContent = `${D.cozum.aciklama}\nUygulama henüz yok (SPEC 62 ikinci aşama).`;
    return;
  }
  const sira = ++D.sira;
  D.onizleme.textContent = "Çözümleniyor…";
  let govde: Cozum | CozumHatasi;
  let ok: boolean;
  try {
    const r = await fetch(UC, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metin, secim: null }),
    });
    ok = r.ok;
    govde = await r.json();
  } catch (err) {
    if (D !== null && yanitGecerliMi(sira, D.sira)) D.onizleme.textContent = `Sunucuya ulaşılamadı: ${String(err)}`;
    return;
  }
  if (D === null || !yanitGecerliMi(sira, D.sira) || D.girdi.value !== metin) return;
  if (ok) {
    D.cozum = govde as Cozum;
    D.onizlenen = metin;
    D.onizleme.textContent = `${D.cozum.aciklama}\nEnter: uygula · Esc: vazgeç`;
  } else {
    const h = govde as CozumHatasi;
    const satirlar = [typeof h.detail === "string" ? h.detail : "Komut çözümlenemedi"];
    if (h.oneriler?.length) satirlar.push(`Bunu mu demek istediniz: ${h.oneriler.join(", ")}?`);
    if (h.okumalar?.length) satirlar.push(`Olası okumalar: ${h.okumalar.join(" | ")}`);
    D.onizleme.textContent = satirlar.join("\n");
  }
  kanca();
}
