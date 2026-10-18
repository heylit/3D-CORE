"""SPEC 64 testlerinin ortak yardımcıları (test değildir).

Testler yalnız SPEC 64 metninden, `tezgah/mes/sema.py` modellerinden, `tezgah/mes/depo.py` ve `uclar.py`
imzalarından, `durum/64-mes-baglantisi.md` varsayılanlarından ve SPEC 31 `cam.post.post` arayüzünden yazıldı;
`tezgah/mes/` gövdeleri okunmadı.

Varsayılanlar (koordinatör onaylı, durum/64): yollar çalışma klasörüne göre
(`yerel_parcalar/mes/is-emirleri.json`, `yerel_parcalar/gonderim-kaydi.jsonl`); program = `post` çıktısı +
POST yorumunun hemen ardından tek satır `MES <mes_id> REV <revizyon>` yorumu;
`program_ozeti` = programın UTF-8 sha256'sı = `X-Sha256` (tam gövde).

Örnek iş: depodaki `flans-plakasi` işinin takımlarında tutucu yok, hazır profillerle post edilemez. Bu yüzden
SPEC 31 test yardımcılarıyla (tutuculu takım, SPEC 04 altın yolu + G83 delik) uydurma bir iş kurulur ve
`tezgah.depo.kaydet` ile eklenir.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from atolye.html import render_html
from atolye.is_foyu import JobSheet, build_job_sheet
from cam.gcode import FANUC
from cam.model import ToolLibrary
from cam.post import builtin_machines, dialect_for, post
from tests.cam.post31_ortak import KURULUM, L, drill
from tests.cam.post_ortak import altin_yol, takim
from tezgah.kopru import Islem, IsTanimi

IS_ADI = "mes-ornek"
HAAS_M = "ORNEK-HAAS-DIK"
SIN_M = "ORNEK-SINUMERIK-DIK"
HEI_M = "ORNEK-HEIDENHAIN-DIK"
DEPO = Path("yerel_parcalar/mes/is-emirleri.json")
KAYIT = Path("yerel_parcalar/gonderim-kaydi.jsonl")
API = "/api/mes/v1"


def ornek_tanim(F: float = 300.0) -> IsTanimi:
    """İki takımlı uydurma iş: T1 kontur (altın yol, kesme ilerlemesi F), T2 G83 delik."""
    yol = altin_yol(takim(1, L=L))
    yol = replace(yol, moves=[replace(m, feed=F) if m.feed == 300.0 else m for m in yol.moves])
    delik = replace(drill("G83", "G98"), tool=takim(2, L=L, D=5.0))
    return IsTanimi(
        ad=IS_ADI,
        kurulum=KURULUM,
        malzeme="AlMg3",
        islemler=[Islem("kontur", "Kontur", yol, {"F": F}), Islem("delik", "Delikler G83", delik, {})],
        dialect=FANUC,
        safe_z=5.0,
    )


def beklenen_post(tanim: IsTanimi, profil: str) -> str:
    """SPEC 31 post çıktısı (K4 referansı, kodlayıcıyla sabitlenen çağrı); profil builtin_machines()'ten."""
    m = builtin_machines()[profil]
    return post([i.op for i in tanim.islemler], m, setup=tanim.kurulum, safe_z=tanim.safe_z, program_no=1)


def beklenen_foy(tanim: IsTanimi, profil: str, parca_no: str = "P-4711", parca_rev: str = "B") -> JobSheet:
    """SPEC 38 föyü (K4 referansı, sabitlenen çağrı); takımlar ilk görünüş sırasıyla, yinelenmeden."""
    ops = [i.op for i in tanim.islemler]
    araclar = []
    for op in ops:
        if op.tool.id not in [a.id for a in araclar]:
            araclar.append(op.tool)
    return build_job_sheet(
        f"{parca_no} rev {parca_rev}",
        [tanim.kurulum],
        [ops],
        ToolLibrary(tools=araclar),
        tanim.malzeme,
        dialect=dialect_for(builtin_machines()[profil]),
        program_no=1,
        names=[[i.ad for i in tanim.islemler]],
    )


def beklenen_foy_html(tanim: IsTanimi, profil: str) -> str:
    return render_html(beklenen_foy(tanim, profil))


def govde(mes_id: str = "IE-1001", revizyon: int = 1, **kw) -> dict:
    d = dict(
        mes_id=mes_id,
        revizyon=revizyon,
        parca_no="P-4711",
        parca_rev="B",
        adet=25,
        malzeme_id="AlMg3",
        tezgah=HAAS_M,
        termin="2026-11-30",
        notlar="uydurma iş emri",
        proje=None,
    )
    d.update(kw)
    return d


def sha(metin: str) -> str:
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def mes_satiri(program: str, profil: str, mes_id: str, rev: int) -> tuple[int, list[str]]:
    """POST yorumunun hemen ardındaki MES satırının indisi ve o satır çıkarılmış program satırları."""
    satirlar = program.split("\n")
    k = next(i for i, s in enumerate(satirlar) if f"POST {profil}" in s)
    assert f"MES {mes_id} REV {rev}" in satirlar[k + 1], satirlar[k : k + 2]
    return k + 1, satirlar[: k + 1] + satirlar[k + 2 :]


def gonderim_satiri(program_ozeti: str, program_ad: str = "O0001", **kw) -> str:
    """SPEC 63 §5 biçiminde bir gönderim kaydı satırı (JSON Lines)."""
    d = dict(
        zaman="2026-10-18T12:00:00Z",
        operator="op1",
        profil=dict(ad=HAAS_M, ozet="0" * 64),
        program=dict(ad=program_ad, ozet=program_ozeti, lehce="haas", program_no=1),
        hedef="C:/dnc/O0001.nc",
        sonuc="yazildi",
    )
    d.update(kw)
    return json.dumps(d, ensure_ascii=False, sort_keys=True)
