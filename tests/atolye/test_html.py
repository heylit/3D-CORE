"""SPEC 38 K8 — iş föyünün HTML çıktısı (§8) ve dosyaya yazımı.

HTML stdlib `html.parser` ile küçük bir ağaca ayrıştırılır; öğeler §8 tablosundaki `id` / sınıflardan bulunur.
Testler yalnız SPEC 38 metninden yazıldı; `atolye` uygulama kodu okunmadı.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser

import pytest

from atolye import build_job_sheet, render_html, write_job_sheet
from cam.gcode import FANUC
from tests.atolye import ek_a

BOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


@dataclass
class Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)  # Node veya str

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def find_all(self, tag: str, **attrs) -> list[Node]:
        out = []
        for n in self.iter():
            if n.tag != tag:
                continue
            ok = True
            for k, v in attrs.items():
                k = k.rstrip("_")
                if k == "class":
                    ok &= v in (n.attrs.get("class") or "").split()
                else:
                    ok &= n.attrs.get(k) == v
            if ok:
                out.append(n)
        return out

    def by_id(self, id_: str) -> Node | None:
        bulunan = [n for n in self.iter() if n.attrs.get("id") == id_]
        assert len(bulunan) <= 1, f"id '{id_}' birden çok"
        return bulunan[0] if bulunan else None


class Agac(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.stack = [self.root]
        self.doctype = None

    def handle_decl(self, decl):
        self.doctype = decl

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs))
        self.stack[-1].children.append(n)
        if tag not in BOS:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(html: str) -> tuple[Node, Agac]:
    p = Agac()
    p.feed(html)
    p.close()
    return p.root, p


def satirlar(tablo: Node) -> list[list[str]]:
    """Veri satırları: <td> içeren <tr>'ler, hücre metinleri kırpılmış."""
    out = []
    for tr in tablo.find_all("tr"):
        tds = tr.find_all("td")
        if tds:
            out.append([" ".join(td.text().split()) for td in tds])
    return out


def satir_hucreleri(tablo: Node) -> list[list[str]]:
    """Tüm hücreler (th + td) satır başına, başlık satırı dahil."""
    out = []
    for tr in tablo.find_all("tr"):
        hucre = [n for n in tr.iter() if n.tag in ("th", "td")]
        out.append([" ".join(h.text().split()) for h in hucre])
    return out


def job_ek_a(**kw):
    args = dict(machine=ek_a.machine())
    args.update(kw)
    title = args.pop("title", "Ek A işi")
    return build_job_sheet(title, [ek_a.setup()], [ek_a.ops()], ek_a.lib(), ek_a.MATERIAL, **args)


def test_belge_yapisi():
    job = job_ek_a(date="2026-10-18")
    html = render_html(job)
    root, p = parse(html)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert root.find_all("html", lang="tr")
    assert [" ".join(h.text().split()) for h in root.find_all("h1")] == ["Ek A işi"]
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html.lower()
    assert "@page" in html and "A4" in html and "12mm" in html.replace(" ", "")
    assert "break-inside" in html and "avoid" in html


def test_ozet_tablosu():
    job = job_ek_a(date="2026-10-18")
    root, _ = parse(render_html(job))
    ozet = root.by_id("ozet")
    assert ozet is not None and ozet.tag == "table"
    hucre = [r for r in satir_hucreleri(ozet) if r]
    etiketler = [r[0] for r in hucre]
    assert etiketler == [
        "Parça",
        "Malzeme",
        "Program no",
        "Kontrol",
        "Bağlama sayısı",
        "Toplam süre",
        "Tarih",
    ]
    deger = {r[0]: r[-1] for r in hucre}
    assert deger["Parça"] == "Ek A işi"
    assert deger["Malzeme"] == "al"
    assert deger["Program no"] == "1"
    assert deger["Kontrol"] == "GRBL"
    assert deger["Bağlama sayısı"] == "1"
    assert deger["Toplam süre"] == "0:30"  # 29,92 s → ⌊30,42⌋ = 30 s
    assert deger["Tarih"] == "2026-10-18"

    # Tarih verilmezse satır yok; Fanuc kontrol adı
    root, _ = parse(render_html(job_ek_a(dialect=FANUC)))
    hucre = [r for r in satir_hucreleri(root.by_id("ozet")) if r]
    assert [r[0] for r in hucre][-1] == "Toplam süre"
    assert {r[0]: r[-1] for r in hucre}["Kontrol"] == "Fanuc"


def test_baglama_bolumu():
    job = job_ek_a()
    root, _ = parse(render_html(job))
    sec = root.by_id("baglama-1")
    assert sec is not None and sec.tag == "section"
    assert root.by_id("baglama-2") is None
    assert [i.attrs.get("src") for i in sec.find_all("img")] == ["baglama-1.svg"]
    s = job.setups[0]
    for cls in ("wcs", "takimlar", "islemler"):
        assert len(sec.find_all("table", class_=cls)) == 1, cls
    takim = satirlar(sec.find_all("table", class_="takimlar")[0])
    islem = satirlar(sec.find_all("table", class_="islemler")[0])
    assert len(takim) == len(s.tools) == 2
    assert len(islem) == len(s.ops) == 2
    # T2 satırı: L "105" (format_value), GRBL ofseti "15,000" (dialect.decimals, virgül)
    assert "105" in takim[1]
    assert "15,000" in takim[1]
    assert "0,000" in takim[0] and "90" in takim[0]
    # İşlem satırları: ad, devir tam sayı
    assert "cep" in islem[0] and "10000" in islem[0]
    assert "delik" in islem[1] and "3000" in islem[1]
    # WCS tablosu: kayıt kodu, makine koordinatı ve eksen tarifleri
    wcs = " ".join(" ".join(r) for r in satir_hucreleri(sec.find_all("table", class_="wcs")[0]))
    for parca in ("G55", "-250,000", "-190,000", "-80,000", "sol kenar", "ön kenar", "üst yüz"):
        assert parca in wcs, parca


def test_saat_bicimi():
    """≥ 1 saat → s:dd:ss."""
    from cam.model import Move, MoveType, Toolpath

    # 40 mm × 100 geçiş + 1 mm dalma = 4001 mm, F60 → 4001 s = 1:06:41
    moves = [Move(MoveType.LINEAR, (5, 5, -1), 60)]
    for i in range(100):
        moves.append(Move(MoveType.LINEAR, (45 if i % 2 == 0 else 5, 5, -1), 60))
    tp = Toolpath("saat", ek_a.T1(), start=(5, 5, 0), moves=moves, rpm=10000)
    job = build_job_sheet("t", [ek_a.setup()], [[tp]], ek_a.lib(), "al", machine=ek_a.machine())
    assert job.total_time == pytest.approx(4001, rel=1e-12)
    root, _ = parse(render_html(job))
    assert {r[0]: r[-1] for r in satir_hucreleri(root.by_id("ozet")) if r}["Toplam süre"] == "1:06:41"


def test_olcum_ve_dogrulama_listesi():
    job = job_ek_a(n_max=12000)
    root, _ = parse(render_html(job))
    olcum = root.by_id("olcum")
    assert olcum is not None and olcum.tag == "table"
    rows = satirlar(olcum)
    assert len(rows) == len(job.inspection)
    for r, item in zip(rows, job.inspection, strict=True):
        assert r[0] == str(item.no)
        assert item.text in r
        assert r[-1] == ""  # Ölçülen sütunu boş
    ul = root.by_id("dogrulama")
    assert ul is not None and ul.tag == "ul"
    lis = ul.find_all("li")
    assert len(lis) == len(job.checks)
    assert [li.attrs.get("data-bolum") for li in lis] == [str(c.section) for c in job.checks]
    assert [" ".join(li.text().split()) for li in lis] == [
        " ".join(f"☐ {c.text}".split()) for c in job.checks
    ]


def test_uyarilar():
    root, _ = parse(render_html(job_ek_a()))
    assert root.by_id("uyarilar") is None  # uyarı yoksa öğe yok
    job = job_ek_a(warnings=["dikkat: <ince> & duvar"])
    html = render_html(job)
    root, _ = parse(html)
    ul = root.by_id("uyarilar")
    assert ul is not None and ul.tag == "ul"
    assert [" ".join(li.text().split()) for li in ul.find_all("li")] == list(job.warnings)
    assert "dikkat: <ince>" not in html


def test_kacis_ve_determinizm():
    job = job_ek_a(title="Parça <&> 1")
    html = render_html(job)
    assert "<&>" not in html
    assert "&lt;&amp;&gt;" in html
    root, _ = parse(html)
    assert [" ".join(h.text().split()) for h in root.find_all("h1")] == ["Parça <&> 1"]
    assert render_html(job) == html
    # Aynı girdiden kurulan iki föy de aynı HTML'i verir (saat / rastgelelik yok)
    assert render_html(job_ek_a(title="Parça <&> 1")) == html


def test_write_job_sheet(tmp_path):
    job = job_ek_a()
    klasor = tmp_path / "yeni"
    yol = write_job_sheet(job, klasor)
    assert yol == klasor / "is-foyu.html"
    assert yol.read_bytes() == render_html(job).encode("utf-8")
    svg = klasor / "baglama-1.svg"
    assert svg.is_file()
    assert ET.parse(svg).getroot().tag.endswith("svg")
    # Üstüne yazar; str klasör yolu da kabul
    yol2 = write_job_sheet(job, str(klasor))
    assert yol2 == yol and yol.read_bytes() == render_html(job).encode("utf-8")
