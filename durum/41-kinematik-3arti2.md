# Durum — SPEC 41 Tezgâh kinematiği ve 3+2

- SPEC: onaylandı (2026-10-18 10:38 UTC). Dal: `claude/project-thread-w648u9` (PR #51).
- Arayüz: `cam/model.py` çok eksen ekleri PR #60 dalından merge edildi (82cdb27); #60 birleşince `main` alınır.
- İskelet: `cam/multiaxis/kinematics.py`, `cam/multiaxis/indexed.py` (`NotImplementedError`).
- Sıradaki: testler ayrı thread'de (dogrulayici), sonra kod ayrı commit'te.
