"""
Tezgah: kullanıcıya dönük web arayüzü (SPEC 24). Köprü (`kopru`), örnek işler (`isler`),
FastAPI sunucusu (`sunucu`) ve `tezgah` komutu (`__main__`).

Hiçbir paket `tezgah`'a bağımlı olamaz (viz/ gibi). `tezgah` diğer paketlerin yalnızca `model.py`
arayüzlerini ve herkese açık fonksiyonlarını kullanır. Arayüz hesap yapmaz: ön yüzde görülen her
mühendislik sayısı buradaki köprünün çekirdekten aldığı değerdir.
"""

SEMA = 1  # JSON ve ikili dizilerin biçim sürümü
