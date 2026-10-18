# DURUM — SPEC 36 Montaj sırası ve demontaj yolu

Dal: `claude/spec-36-montaj-sirasi-3h5rr8` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayı bekliyor; onaydan sonra `NotImplementedError` iskeleti (SPEC 09 dalının üstüne).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |

## Son oturum
**2026-10-18**
- `specs/36-montaj-sirasi.md` taslağı yazıldı (yol haritası Dalga 5, hat H11).
- Ek A sahnesinin beklenen sıraları, yönleri ve yol boyları depo dışı küçük bir prototiple (kutu kesişimi)
  doğrulandı.

## Açık sorular
1. Plan sınıfı: tek birim, monoton, tek doğrusal öteleme (çok parçalı / dönen yollar kapsam dışı). Önerilen: evet.
2. Aday yönler: varsayılan 6 eksen; kısıtlardan yön `mate_directions` ile isteğe bağlı. Önerilen: evet.
3. Sökülemez montaj: `AssyError` (kalan birimler mesajda) ve tanı için `blocking`. Önerilen: hata.
4. Taban verilmezse en büyük hacimli birim. Önerilen: evet.
5. Örnekleme adımı varsayılanı: en küçük yaprak `bbox` kenarı (ince özellik sınırı kabul). Önerilen: evet.
6. Alt montaj tek rijit birim (`units="cocuk"`) seçeneği bu SPEC'te. Önerilen: evet.
