"""Controlla che nella pagina non ci siano numeri scritti a mano.

Regola: nel testo di sito/modello.html (fuori dai segnaposto {{...}}, dagli script e dagli stili)
possono comparire solo numeri «di struttura»: anni, date di estrazione, soglie fisse come
15 o 30 minuti, classi d'età, versioni di licenza, la numerazione dei capitoli.
Tutto il resto deve arrivare da un segnaposto, cioè da un calcolo in prepara_sito.py
o da una citazione in sito/citazioni.json con la sua fonte.
Anche dentro gli script la pagina non deve contenere numeri del racconto scritti a mano.
Esce con errore se trova qualcosa.
"""
import json
import re
import sys

m = open("sito/modello.html", encoding="utf-8").read()
testi = json.load(open("sito/testi.json", encoding="utf-8"))

errori = []

# 1. ogni segnaposto ha un valore e una fonte
for k in set(re.findall(r"\{\{([a-z0-9_]+)\}\}", m)):
    if k not in testi["testi"]:
        errori.append(f"segnaposto senza valore: {k}")
    elif not testi["fonti"].get(k):
        errori.append(f"segnaposto senza fonte: {k}")

# 2. numeri nel testo visibile
corpo = m[m.index("<body"):]
corpo = re.sub(r"<script.*?</script>", " ", corpo, flags=re.S)
corpo = re.sub(r"<style.*?</style>", " ", corpo, flags=re.S)
corpo = re.sub(r"\{\{[a-z0-9_]+\}\}", " ", corpo)
corpo = re.sub(r'(href|src|id|class|aria-label|style|data-[a-z]+)="[^"]*"', " ", corpo)
testo = re.sub(r"<[^>]+>", " ", corpo)

STRUTTURA = [
    r"\b(19|20)\d\d\b",                    # anni
    r"\b\d{1,2}/\d{1,2}/20\d\d\b",          # date di estrazione
    r"\b20\d\d-\d\d-\d\d\b",                # release Overture
    r"\b(15|30)\s+minuti\b",                # soglie
    r"\b0-14\b", r"\b25-64\b", r"\b0-5\b",  # classi d'età
    r"\b\d\s+di\s+6\b",                     # numerazione capitoli
    r"\b20\s+regioni\b",                    # numero delle regioni
    r"\b8:30\b",                            # ora delle matrici ISTAT
    r"\b(CC BY|CC0|ODbL|Apache-|CDLA-Permissive-)\s*\d(\.\d)?\b", r"\b\d\.0\b",  # licenze
    r"\b(2\.000|3\.000|5\.000|10\.000|15\.000|50\.000)\s+abitanti\b",  # classi di grandezza dichiarate
    r"\bda\s+(1\.000|3\.000)\b", r"\b(1|6|25)\s+anni\b", r"\b1°", r"\bedat_lfse_04\b",
    r"\b(sotto|sopra)\s+i\s+(1\.000|3\.000|5\.000|15|6)\b", r"\btra\s+(2\.000|3\.000)\s+e\s+(10\.000)\b",
    r"\b30\s+comuni\b", r"\b-1\b", r"\b[01]\s+vuol dire\b", r"\b0\s+nessun legame\b",
    r"\b(1\.000|2\.000|3\.000|5\.000|10\.000|15\.000|50\.000)\b",  # confini delle classi di grandezza
    r"\btra\s+i\s+25\s+e\s+i\s+64\s+anni\b", r"\bCC0\b", r"github\.com/\S+",
]
pulito = testo
for r_ in STRUTTURA:
    pulito = re.sub(r_, " ", pulito)
for n in re.finditer(r"[^\s]*\d[^\s]*", pulito):
    a = max(0, n.start() - 60)
    errori.append("numero scritto a mano nel testo: «…" + " ".join(pulito[a:n.end() + 30].split()) + "…»")

# 3. negli script: niente percentuali o conteggi del racconto scritti a mano
for sc in re.findall(r"<script>(.*?)</script>", m, flags=re.S):
    for riga in sc.splitlines():
        if re.search(r"\b\d{2,}[.,]\d+\s*%|\bv:\s*\d+(\.\d+)?\b", riga) and "{{" not in riga:
            errori.append("numero del racconto scritto a mano nello script: " + riga.strip()[:120])

rapporto = {"errori": errori, "segnaposto": len(set(re.findall(r"\{\{([a-z0-9_]+)\}\}", m)))}
json.dump(rapporto, open("sito/verifica_pagina.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for e in errori:
    print("ERRORE:", e)
print(f"Verifica pagina: {len(errori)} errori, {rapporto['segnaposto']} segnaposto.")
sys.exit(1 if errori else 0)
