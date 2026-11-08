"""Scarica i file ufficiali grezzi in data/grezzi/ e registra data e dimensione di ognuno.

Le matrici dei tempi ISTAT sono troppo grandi per il repository: qui ne salviamo solo un campione
per capirne la struttura. Il calcolo completo dei tempi avviene in un passo successivo.
"""
import io
import json
import os
import urllib.request
import zipfile
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (territorio-legge; open data research)"}
OUT = "data/grezzi"
os.makedirs(OUT, exist_ok=True)

FONTI = {
    "iccu_biblioteche": ("https://opendata.anagrafe.iccu.sbn.it/biblioteche.zip", "CC0 1.0", "ICCU, Anagrafe delle biblioteche italiane"),
    "iccu_territorio": ("https://opendata.anagrafe.iccu.sbn.it/territorio.zip", "CC0 1.0", "ICCU, Anagrafe delle biblioteche italiane"),
    "iccu_tipologie": ("https://opendata.anagrafe.iccu.sbn.it/tipologie.zip", "CC0 1.0", "ICCU, Anagrafe delle biblioteche italiane"),
    "mef_redditi_2024": ("https://www1.finanze.gov.it/finanze/analisi_stat/public/v_4_0_0/contenuti/Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.zip", "da verificare", "MEF, Dipartimento delle Finanze"),
    "istat_popolazione_2026": ("https://demo.istat.it/data/posas/POSAS_2026_it_Comuni.zip", "CC BY 4.0", "ISTAT, demo.istat.it"),
    "istat_elenco_comuni": ("https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv", "CC BY 4.0", "ISTAT"),
}
registro = {"scaricato": datetime.now(timezone.utc).isoformat(timespec="seconds"), "file": {}}


def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300)
    return r.read(), r.headers.get("Last-Modified")


for nome, (url, licenza, ente) in FONTI.items():
    dati, modificato = get(url)
    cartella = os.path.join(OUT, nome)
    os.makedirs(cartella, exist_ok=True)
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(dati)) as z:
            z.extractall(cartella)
            contenuto = z.namelist()
    else:
        fn = os.path.join(cartella, os.path.basename(url))
        open(fn, "wb").write(dati)
        contenuto = [os.path.basename(url)]
    registro["file"][nome] = {"url": url, "ente": ente, "licenza": licenza,
                              "ultima_modifica_alla_fonte": modificato, "byte": len(dati), "contenuto": contenuto}
    print(nome, len(dati), contenuto[:10])

# campione della matrice dei tempi (Lombardia): solo le prime righe
dati, modificato = get("https://www.istat.it/storage/cartografia/matrici_distanze/Lombardia.zip")
with zipfile.ZipFile(io.BytesIO(dati)) as z:
    nomi = z.namelist()
    righe = []
    with z.open(nomi[0]) as f:
        for i, riga in enumerate(f):
            righe.append(riga.decode("latin-1"))
            if i >= 40:
                break
os.makedirs(f"{OUT}/istat_matrici_campione", exist_ok=True)
open(f"{OUT}/istat_matrici_campione/Lombardia_prime_righe.txt", "w").write("".join(righe))
registro["file"]["istat_matrici_campione"] = {"url": "https://www.istat.it/storage/cartografia/matrici_distanze/Lombardia.zip",
                                              "ultima_modifica_alla_fonte": modificato, "byte_zip": len(dati), "contenuto": nomi}
json.dump(registro, open(f"{OUT}/registro.json", "w"), indent=2, ensure_ascii=False)
