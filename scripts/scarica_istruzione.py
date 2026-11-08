"""Quota di persone 25-64 anni con titolo terziario (laurea o equivalente) per regione italiana.

Fonte: Eurostat, dataset edat_lfse_04 (Population aged 25-64 by educational attainment level, sex and NUTS 2 region),
ISCED 5-8, entrambi i sessi, ultimo anno disponibile. Licenza: CC BY 4.0 (riuso Eurostat).
"""
import json
import os
import urllib.request

OUT = "data/grezzi/eurostat_istruzione"
os.makedirs(OUT, exist_ok=True)
base = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/edat_lfse_04"
url = base + "?format=JSON&lang=EN&sex=T&age=Y25-64&isced11=ED5-8&unit=PC&lastTimePeriod=3"
dati = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "territorio-legge"}), timeout=120))
json.dump(dati, open(f"{OUT}/edat_lfse_04_terziario.json", "w"), indent=1)

geo = dati["dimension"]["geo"]["category"]
tempo = dati["dimension"]["time"]["category"]["index"]
ng, nt = len(geo["index"]), len(tempo)
righe = []
for codice, gi in geo["index"].items():
    if not codice.startswith("IT") or len(codice) != 4:
        continue
    for anno, ti in tempo.items():
        v = dati["value"].get(str(gi * nt + ti))
        if v is not None:
            righe.append({"nuts2": codice, "nome": geo["label"][codice], "anno": anno, "pct_terziario_25_64": v})
json.dump({"fonte": "Eurostat edat_lfse_04, ISCED 5-8, 25-64 anni, %", "url": url, "righe": righe},
          open(f"{OUT}/terziario_regioni.json", "w"), indent=2, ensure_ascii=False)
print(len(righe), righe[:5])
