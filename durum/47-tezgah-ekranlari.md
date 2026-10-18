# DURUM — SPEC 47 tezgah-ekranlari

Dal: `claude/spec-47-tezgah-ekranlari-59jujx` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayı bekliyor (açık sorular SPEC sonunda). Onaydan sonra: NotImplementedError iskeleti
(A3 ve bağımlılık dallarının üstünde), ayrı test oturumunun test commit'i, kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |

## Son oturum
**2026-10-18**
- SPEC 47 taslağı yazıldı: Plan (SPEC 29), Çok eksen (41–44), Analiz (11–13) ekranları; A3 ekran kaydından
  beklenen arayüz SPEC'te "Ekran kaydı (A3) beklentisi" bölümünde.
- Arayüz (`*/model.py`) değişikliği gerekmiyor; paylaşılan Tezgah dosyalarına dokunulmuyor.

## Açık sorular
1. Üç alt PR (47a/b/c) mı, tek PR mı? Öneri: üç alt PR.
2. Analizde silindir seçimi elle mi? Öneri: düzlem tıklamayla, silindir elle.
3. Tri-dexel yalnız işlem sonu anlık görüntüleri mi? Öneri: evet.
4. Çok eksende G-code yerine eklem tablosu mu? Öneri: evet.
5. Analitik sapma %10, yakınsama %5 uyarı eşikleri. Öneri: evet.
