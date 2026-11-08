"""Esplora le pagine ufficiali e registra quali file scaricabili espongono. Non scarica i dati."""
import json
import re
import urllib.request
from urllib.parse import urljoin

PAGINE = {
    "iccu_opendata": "https://anagrafe.iccu.sbn.it/it/open-data/",
    "iccu_opendata_vecchio": "https://opendata.anagrafe.iccu.sbn.it/",
    "mef_dichiarazioni": "https://www1.finanze.gov.it/finanze/pagina_dichiarazioni/public/dichiarazioni.php",
    "mef_opendata": "https://www1.finanze.gov.it/finanze/pagina_dichiarazioni/public/dichiarazioni.php?d=d&opendata=yes",
    "istat_matrici": "https://www.istat.it/notizia/matrici-di-contiguita-distanza-e-pendolarismo/",
    "istat_demo": "https://demo.istat.it/",
    "istat_demo_posas": "https://demo.istat.it/app/?i=POS&l=it",
    "istat_codici_comuni": "https://www.istat.it/classificazione/codici-dei-comuni-delle-province-e-delle-regioni/",
}
CANDIDATI = [
    "https://opendata.anagrafe.iccu.sbn.it/territorio.zip",
    "https://opendata.anagrafe.iccu.sbn.it/biblioteche.zip",
    "https://opendata.anagrafe.iccu.sbn.it/tipologie.zip",
    "https://opendata.anagrafe.iccu.sbn.it/tipologia-funzionale.zip",
    "https://www1.finanze.gov.it/finanze/analisi_stat/public/v_4_0_0/contenuti/Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.zip",
    "https://demo.istat.it/data/posas/POSAS_2026_it_Comuni.zip",
    "https://demo.istat.it/data/posas/POSAS_2025_it_Comuni.zip",
    "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv",
]
UA = {"User-Agent": "Mozilla/5.0 (territorio-legge; open data research)"}
rapporto = {"pagine": {}, "candidati": {}}

for nome, url in PAGINE.items():
    try:
        html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "ignore")
        links = sorted({urljoin(url, h) for h in re.findall(r'href=["\']([^"\']+)', html)
                        if re.search(r"\.(zip|csv|xlsx?|json|7z|gz)(\?|$)", h, re.I) or "download" in h.lower()})
        rapporto["pagine"][nome] = {"url": url, "ok": True, "link_file": links[:300]}
    except Exception as e:  # noqa: BLE001
        rapporto["pagine"][nome] = {"url": url, "ok": False, "errore": str(e)}

for url in CANDIDATI:
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=60)
        rapporto["candidati"][url] = {"stato": r.status, "tipo": r.headers.get("Content-Type"),
                                      "byte": r.headers.get("Content-Length"),
                                      "modificato": r.headers.get("Last-Modified")}
    except Exception as e:  # noqa: BLE001
        rapporto["candidati"][url] = {"errore": str(e)}

import os
os.makedirs("data/esplorazione", exist_ok=True)
json.dump(rapporto, open("data/esplorazione/fonti.json", "w"), indent=2, ensure_ascii=False)
print(json.dumps(rapporto, indent=2, ensure_ascii=False)[:5000])
