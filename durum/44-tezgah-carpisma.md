# DURUM — SPEC 44 Tezgâh çarpışma denetimi

Dal: `claude/spec-06-cam-3d-09jwcj` · Oturum: bulut

## Sıradaki adım
Ayrı test oturumunun test commit'ini cherry-pick edip kodu testlere karşı koşmak.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: tüm işlevler NotImplementedError |
| 2026-10-18 | — | — | Kod yazıldı; elle denemeler: K3 düşey temas 1e-7, K4 dönen fikstür t kapalı formdan 3e-11, K6 A=121° → t=120/121 |

## Son oturum
**2026-10-18**
- `cam/multiaxis/machine.py` (Box, Capsule, Body, MachineModel, poses) ve `cam/multiaxis/collision.py`
  (uzaklıklar, MachineEvent, check) iskeletleri; kurallar docstring'lerde.
- Örnek tezgâh: `examples/tezgah_ac_besik.json` (AC beşik, uydurma geometri).
- Kod: kapsül–kapsül Ericson kapalı form; kapsül–kutu altın oran (Lipschitz alt sınırıyla erken çıkış);
  kutu–kutu 15 eksen SAT. Ön eleme sınır küresi + eksene hizalı kutu; uzak çiftlerde boşluk/σ kadar örnek atlanır.
- Yorumlar (docstring'lerde, koordinatöre bildirildi): masa zinciri × taban da denetlenir (K4 kolon tabanda);
  kayıt ihlalin başlangıcıdır (süren temas yeni kayıt açmaz); kutu–kutu değme kesişim sayılır;
  tutucu basamakları dilimsiz (`body_steps(dz=∞)`); sınır içinde ters kinematik çözümü yoksa sınırsız çözüm.

## Açık sorular
_(yok)_
