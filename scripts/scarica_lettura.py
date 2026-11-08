"""Scarica le tavole ISTAT sulla lettura di libri (indagine Multiscopo 'I cittadini e il tempo libero')."""
import json
import os
import re
import urllib.request
from urllib.parse import urljoin

UA = {"User-Agent": "Mozilla/5.0 (territorio-legge; open data research)"}
OUT = "data/grezzi/istat_lettura"
os.makedirs(OUT, exist_ok=True)
PAGINE = [
    "https://www.istat.it/tavole-di-dati/lettura-di-libri-e-generi-di-libri-letti-scrittura-di-libri-prelettura-dei-bambini-di-0-5-anni-ascolto-di-podcast-anno-2024/",
    "https://www.istat.it/it/archivio/lettura",
]


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()


def link(html, base):
    return sorted({urljoin(base, h) for h in re.findall(r'href=["\']([^"\']+)', html)})


registro = {"pagine": {}, "file": {}}
coda = list(PAGINE)
viste = set()
while coda:
    url = coda.pop(0)
    if url in viste:
        continue
    viste.add(url)
    try:
        html = get(url).decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        registro["pagine"][url] = str(e)
        continue
    tutti = link(html, url)
    registro["pagine"][url] = [l for l in tutti if re.search(r"\.(xlsx?|zip|csv|pdf)$", l, re.I)]
    # segue la pagina del comunicato "Libri e biblioteche ... 2024 e 2025"
    for l in tutti:
        if "libri-e-biblioteche" in l and l not in viste:
            coda.append(l)

for pagina, files in registro["pagine"].items():
    if not isinstance(files, list):
        continue
    for f in files:
        if re.search(r"\.(xlsx?|zip|csv)$", f, re.I) and ("2024" in f or "2025" in f or "2026" in f or "tavol" in f.lower()):
            nome = os.path.basename(f.split("?")[0])
            try:
                dati = get(f)
                open(os.path.join(OUT, nome), "wb").write(dati)
                registro["file"][nome] = {"url": f, "byte": len(dati)}
            except Exception as e:  # noqa: BLE001
                registro["file"][nome] = {"url": f, "errore": str(e)}
json.dump(registro, open(os.path.join(OUT, "registro.json"), "w"), indent=2, ensure_ascii=False)
print(json.dumps(registro, indent=2, ensure_ascii=False)[:4000])
