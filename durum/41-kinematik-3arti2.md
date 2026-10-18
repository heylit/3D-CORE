# Durum — SPEC 41 Tezgâh kinematiği ve 3+2

- SPEC: onaylandı (2026-10-18 10:38 UTC). Dal: `claude/project-thread-w648u9` (PR #51).
- Arayüz: `cam/model.py` çok eksen ekleri PR #60 dalından merge edildi (82cdb27); #60 birleşince `main` alınır.
  PR #51, #60 birleşmeden birleşmemeli (yoksa #60'ın değişiklikleri onaysız main'e girer).
- Testler: f21f7f2 (ayrı oturum, `claude/project-thread-dompr6`), 42 test.
- Kod: `cam/multiaxis/kinematics.py` (Rodrigues, ileri kinematik, Paden–Kahan ters kinematik, çözüm seçimi),
  `cam/multiaxis/indexed.py` (Frame kurucuları, ZXZ/XYZ açıları, local_stock/mesh, to_world, to_machine,
  machine_toolpath). 42/42 yeşil.
- Sıradaki: SPEC 42 ve 43 (43, SPEC 05 main'e girince).
