"""
SPEC 64 — MES bağlantısı: MES'in iş emri verip imalat çıktılarını çektiği yerel REST API (/api/mes/v1).

Yön tek taraflı çekmedir: Tezgah MES'e istek göndermez, MES veritabanına bağlanmaz.
    sema.py  pydantic modelleri (OpenAPI şemasının kaynağı)
    depo.py  iş emri saklama (yerel_parcalar/mes/is-emirleri.json) ve durum makinesi
    uclar.py router (A3'te sayfasız "mes" ekranı olarak bağlanır: tezgah/ekranlar/mes.py)
"""
