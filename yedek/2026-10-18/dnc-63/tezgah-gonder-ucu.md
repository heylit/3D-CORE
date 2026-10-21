# SPEC 63 K8 — Tezgah "gönder" ucu (Tezgah thread'ine devir)

SPEC 63 kodu (`atolye/dnc.py`, PR #130) hazır. Bu uç Tezgah thread'inin dosyalarına (`tezgah/sunucu.py`, ekran
router'ı) dokunduğu için orada yazılmalı. Gereken:

## Uç
`POST /api/ekran/freze/{is}/gonder` (torna karşılığı `/api/ekran/torna/{is}/gonder`)

Gövde: `{"tezgah": str, "operator": str, "zaman": "YYYY-AA-GGTSS:DD:SSZ", "program_no": int, "ad": str | null,
"ezme": bool = false, "gerekce": str = ""}`. `zaman` istemciden gelebilir ya da uçta
`datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` ile üretilir (çekirdek saat okumaz).

## Akış
1. `yerel_parcalar/dnc-hedefleri.json` oku: `{"tezgahlar": {"<ad>": {"klasor": "D:/...", "profil": "<profil adı>"}}}`.
   Ad yoksa → 422, metin: `dnc-hedefleri.json'da <ad> yok`. Dosya yoksa da aynı 422.
2. Profil: `cam.post.builtin_machines()[profil]` ya da `cam.post.load_machine(yol)`.
3. İş: `tanim = depo.al(is)`; yollar `[isl.op for isl in tanim.islemler]` (DrillOp'lar `to_toolpath` ile), metin
   `cam.post.post(ops, profil, tanim.kurulum, program_no=..., safe_z=tanim.safe_z)`.
4. Kontroller: `kopru.kontroller(tanim)` (Ö1, `durum == "hata"` gönderimi durdurur).
5. `atolye.dnc.gonder(metin, profil, yollar, kontroller, hedef=klasor, operator=..., zaman=..., program_no=...,
   ad=..., ezme=..., gerekce=..., kayit_dosyasi="yerel_parcalar/gonderim-kaydi.jsonl")`.
6. Başarı → 200, `{"yol": str(g.yol), "sonuc": g.sonuc, "kayit": g.kayit}`. `CamError` → 422, `detail` = metin
   (sunucudaki ortak 422 eşlemesi zaten bunu yapıyor).

## Arayüz notu (karar 2)
Onay penceresinde profil `verified: false` ise "DOĞRULANMAMIŞ PROFİL" kırmızı yazılır; `g.kayit["dogrulanmis"]` bunu
taşır. Üzerine yazma hatasında (mesaj "… var ve farklı …") pencere `ezme` + zorunlu `gerekce` ister.

## Test (K8)
`tests/tezgah/test_gonder_ucu.py` (bağımsız test oturumu): `tmp_path` hedef klasörü ve `monkeypatch` ile
`dnc-hedefleri.json` yolu; başarılı → 200 ve Gonderim JSON; ön koşul hatası → 422 ve metin; tanımsız tezgâh → 422.
