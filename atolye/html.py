"""SPEC 38 — İş föyünün HTML çıktısı ve dosyaya yazımı (§8).

Tek dosya, UTF-8, dış kaynaksız; PDF tarayıcının "Yazdır"ıyla alınır. Bağlama resimleri yanındaki
baglama-<i>.svg dosyalarıdır (SPEC 16 write_svg). Aynı JobSheet → bayt bayt aynı HTML.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

from atolye.is_foyu import JobSheet, SetupSheet, sayi
from geometry.drawing.dimensions import format_value
from geometry.drawing.svg import write_svg

STIL = """\
@page { size: A4; margin: 12mm }
body { font-family: sans-serif; font-size: 10pt; color: #000; background: #fff; margin: 0 }
h1 { font-size: 16pt; margin: 0 0 4mm }
h2 { font-size: 12pt; margin: 6mm 0 2mm }
table { border-collapse: collapse; margin: 0 0 3mm; width: 100% }
th, td { border: 0.3mm solid #444; padding: 1mm 1.5mm; text-align: left; vertical-align: top }
th { background: #eee }
tr, li, img { break-inside: avoid; page-break-inside: avoid }
section { break-before: page }
img { max-width: 100%; max-height: 110mm }
ul { padding-left: 4mm; list-style: none }
.not { font-size: 8pt; color: #444 }
"""


def sure_metni(t: float) -> str:
    """Saniye → d:ss (≥ 1 saat: s:dd:ss); ⌊t + 0,5⌋ saniyeye yuvarlanır."""
    n = math.floor(t + 0.5)
    s, d, sa = n % 60, (n // 60) % 60, n // 3600
    return f"{sa}:{d:02d}:{s:02d}" if sa else f"{n // 60}:{s:02d}"


def _f(v: float | None) -> str:
    return "—" if v is None else format_value(v)


def _tablo(sinif: str, basliklar: list[str], satirlar: list[list[str]], id_: str | None = None) -> str:
    nitelik = f' id="{id_}"' if id_ else f' class="{sinif}"'
    out = [f"<table{nitelik}>", "<tr>" + "".join(f"<th>{escape(b)}</th>" for b in basliklar) + "</tr>"]
    for r in satirlar:
        out.append("<tr>" + "".join(f"<td>{escape(h)}</td>" for h in r) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def _etiketli(sinif: str, satirlar: list[tuple[str, str]], id_: str | None = None) -> str:
    nitelik = f' id="{id_}"' if id_ else f' class="{sinif}"'
    out = [f"<table{nitelik}>"]
    out += [f"<tr><th>{escape(a)}</th><td>{escape(b)}</td></tr>" for a, b in satirlar]
    out.append("</table>")
    return "\n".join(out)


def _baglama(s: SetupSheet, job: JobSheet) -> str:
    d = job.dialect.decimals
    st, w = s.setup.stock, s.setup.wcs
    ox, oy, oz = (sayi(v, d) for v in w.origin)
    ofset_adi = "H (Fanuc)" if job.dialect.tool_length_comp else f"G43.1 ΔL (referans T{s.ref_id})"
    wcs = _etiketli(
        "wcs",
        [
            ("Kayıt", w.code),
            ("Makine koordinatı", f"X{ox} Y{oy} Z{oz}"),
            ("X0", s.wcs[0]),
            ("Y0", s.wcs[1]),
            ("Z0", s.wcs[2]),
            (
                "Ham malzeme",
                f"{format_value(st.xmax - st.xmin)} × {format_value(st.ymax - st.ymin)} × "
                f"{format_value(st.zmax - st.zmin)} mm",
            ),
            ("Bağlama elemanı", str(len(s.setup.fixtures))),
            ("Süre (tahmin)", sure_metni(s.time)),
            ("Takım değişimi", str(s.tool_changes)),
        ],
    )
    takimlar = _tablo(
        "takimlar",
        [
            "T",
            "Ad",
            "Tür",
            "D",
            "Köşe r",
            "Kesici boy",
            "Taşma",
            "Tutucu",
            "L",
            ofset_adi,
            "Gerekli kesici boy",
            "En yüksek devir",
            "İşlemler",
            "Süre",
        ],
        [
            [
                f"T{t.T}",
                t.name,
                t.kind,
                _f(t.D),
                _f(t.corner_r),
                _f(t.flute_length),
                _f(t.stickout),
                t.holder or "—",
                _f(t.L),
                "—" if t.offset is None else sayi(t.offset, d),
                _f(t.need),
                str(t.rpm_max),
                ", ".join(t.ops),
                sure_metni(t.time),
            ]
            for t in s.tools
        ],
    )
    islemler = _tablo(
        "islemler",
        ["No", "İşlem", "Takım", "Devir", "İlerleme", "En alçak Z", "Süre", "Bitiş"],
        [
            [
                str(o.no),
                o.name,
                f"T{o.T}",
                str(o.rpm),
                _f(o.F),
                _f(o.z_min),
                sure_metni(o.time),
                sure_metni(o.t_end),
            ]
            for o in s.ops
        ],
    )
    return "\n".join(
        [
            f'<section id="baglama-{s.index}">',
            f"<h2>Bağlama {s.index}: {escape(s.setup.name)}</h2>",
            f'<img src="baglama-{s.index}.svg" alt="Bağlama {s.index} resmi">',
            wcs,
            "<h3>Takımlar</h3>",
            takimlar,
            "<h3>İşlemler</h3>",
            islemler,
            "</section>",
        ]
    )


def render_html(job: JobSheet) -> str:
    """Tek dosyalık, dış kaynaksız, yazdırılabilir HTML; aynı girdi → bayt bayt aynı çıktı."""
    ozet = [
        ("Parça", job.title),
        ("Malzeme", job.material),
        ("Program no", str(job.program_no)),
        ("Kontrol", job.dialect.name),
        ("Bağlama sayısı", str(len(job.setups))),
        ("Toplam süre", sure_metni(job.total_time)),
    ]
    if job.date is not None:
        ozet.append(("Tarih", job.date))
    olcum = _tablo(
        "olcum",
        ["No", "Ölçü", "Nominal", "Alt", "Üst", "Ölçülen"],
        [[str(i.no), i.text, _f(i.nominal), _f(i.lower), _f(i.upper), ""] for i in job.inspection],
        id_="olcum",
    )
    parcalar = [
        "<!DOCTYPE html>",
        '<html lang="tr">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{escape(job.title)} — iş föyü</title>",
        f"<style>\n{STIL}</style>",
        "</head>",
        "<body>",
        f"<h1>{escape(job.title)}</h1>",
        _etiketli("ozet", ozet, id_="ozet"),
        '<p class="not">Süreler SPEC 05 modeline göre tahmindir '
        "(güvenli Z geri çekmeleri ve bağlama değişimi hariç).</p>",
    ]
    if job.warnings:
        parcalar += ["<h2>Uyarılar</h2>", '<ul id="uyarilar">']
        parcalar += [f"<li>{escape(w)}</li>" for w in job.warnings]
        parcalar.append("</ul>")
    parcalar += [_baglama(s, job) for s in job.setups]
    parcalar += ["<h2>İlk parça ölçüm listesi (ISO 2768-1)</h2>", olcum]
    parcalar += ["<h2>Tezgâh doğrulama (docs/tezgah-dogrulama.md)</h2>", '<ul id="dogrulama">']
    parcalar += [f'<li data-bolum="{c.section}">☐ {escape(c.text)}</li>' for c in job.checks]
    parcalar += ["</ul>", "</body>", "</html>", ""]
    return "\n".join(parcalar)


def write_job_sheet(job: JobSheet, folder: str | Path) -> Path:
    """`folder`'a is-foyu.html ve baglama-<i>.svg yazar; HTML'in yolunu döndürür."""
    klasor = Path(folder)
    klasor.mkdir(parents=True, exist_ok=True)
    for s in job.setups:
        write_svg(s.drawing, klasor / f"baglama-{s.index}.svg")
    yol = klasor / "is-foyu.html"
    yol.write_bytes(render_html(job).encode("utf-8"))
    return yol
