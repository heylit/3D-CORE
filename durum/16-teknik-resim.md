# DURUM — SPEC 16 teknik-resim

Dal: `claude/spec-16-teknik-resim-u8ylv2` · Oturum: bulut

## Sıradaki adım
SPEC metninin kullanıcı onayı (proje sohbeti); onaydan sonra ayrı bir `dogrulayici` oturumu `tests/geometry/drawing/` testlerini yazar.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Henüz test yok (SPEC taslağı) |

## Son oturum
**2026-10-18**
- `specs/16-teknik-resim.md` taslağı yazıldı (K1–K13).
- Ön deneme (build123d 0.13): `project_to_viewport` teğet (Rg1) kenarları da döndürüyor; OCP
  `HLRBRep_HLRToShape` ile sadece `VCompound` / `OutLine*` alınınca cepte `L_h = 2t + w` tutuyor.
- İzdüşen daireler dejenere B-spline doğru olarak geliyor; üst / alt kenarlar üst üste düşüyor → `clean_edges` gerekli.
- Kod `geometry/drawing/` altına (yeni üst düzey paket `pyproject.toml` değişikliği isterdi).
- `geometry/drawing/` iskeleti (veri tipleri + `NotImplementedError` gövdeli fonksiyonlar) test oturumu için push edildi.

## Açık sorular
- SPEC onayı bekleniyor. Varsayılanlar: DXF/SVG kendi yazıcımız (yeni bağımlılık yok, `ezdxf` yalnızca test
  çapraz kontrolü), ISO birinci açı yerleşimi, ondalık ayırıcı virgül.
