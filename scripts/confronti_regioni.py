"""
Il territorio legge — confronto tra regioni: accesso ai libri, lettura, reddito, istruzione.

Fonti: data/schede/comuni.csv (calcola_schede.py), tavole ISTAT sulla lettura 2024, Eurostat edat_lfse_04.
Metodo: correlazione per ranghi (Spearman) tra le 20 regioni; correlazione parziale ottenuta
togliendo dai ranghi la parte spiegata dalle variabili di controllo (regressione lineare).
Con 20 regioni i risultati sono indicativi: nessuna conclusione causale.
"""
import csv
import json
import math
import os
import re
from collections import defaultdict

import openpyxl

OUT = "data/analisi"
os.makedirs(OUT, exist_ok=True)
G = "data/grezzi"
NOMI = {"Emilia Romagna": "Emilia-Romagna", "Friuli Venezia Giulia": "Friuli-Venezia Giulia",
        "Valle d'Aosta/Vallée d'Aoste": "Valle d'Aosta", "Valle d'Aosta-Vallée d'Aoste": "Valle d'Aosta",
        "Valle d’Aosta/Vallée d’Aoste": "Valle d'Aosta", "Trentino-Alto Adige/Südtirol": "Trentino-Alto Adige"}
std = lambda n: NOMI.get(n, n)


def tavola(file, foglio, colonne):
    out = {}
    for r in openpyxl.load_workbook(file, read_only=True, data_only=True)[foglio].iter_rows(values_only=True):
        if r[0] and len(r) > 2 and isinstance(r[2], (int, float)):
            out[std(re.sub(r"\s+", " ", str(r[0])).strip().lstrip("- ").strip())] = [r[c] for c in colonne]
    return out


lettura = tavola(f"{G}/istat_lettura/Tavole_lettura_libri_prelettura_biblioteche_2024_2025.xlsx", "tavola 2", [2])
acquisto = tavola(f"{G}/istat_lettura/Tavole_lettura_scrittura-libri_prelettura_podcast_2024.xlsx", "tavola 18", [4, 9, 8])

reg = defaultdict(lambda: {"ab": 0, "ab_lib": 0, "ab_bib": 0, "red": 0, "ab_red": 0})
prov = defaultdict(int)
for r in csv.DictReader(open("data/schede/comuni.csv", encoding="utf-8")):
    g, a = std(r["regione"]), int(r["abitanti_2026"])
    s = reg[g]
    s["ab"] += a
    s["ab_lib"] += a if int(r["librerie_note"]) else 0
    s["ab_bib"] += a if int(r["biblioteche_aperte"]) else 0
    if r["reddito_medio_dichiarato_2024"]:
        s["red"] += a * int(r["reddito_medio_dichiarato_2024"]); s["ab_red"] += a
    prov[r["provincia"]] += a

edu_righe = json.load(open(f"{G}/eurostat_istruzione/terziario_regioni.json", encoding="utf-8"))["righe"]
anno_edu = "2024"
edu = {std(x["nome"]): x["pct_terziario_25_64"] for x in edu_righe if x["anno"] == anno_edu}
bz, tn = prov["BZ"], prov["TN"]
edu["Trentino-Alto Adige"] = (edu["Provincia Autonoma di Bolzano/Bozen"] * bz + edu["Provincia Autonoma di Trento"] * tn) / (bz + tn)

righe = []
for g, s in sorted(reg.items()):
    righe.append({"regione": g,
                  "pct_abitanti_con_libreria_nel_comune": round(100 * s["ab_lib"] / s["ab"], 1),
                  "pct_abitanti_con_biblioteca_nel_comune": round(100 * s["ab_bib"] / s["ab"], 1),
                  "reddito_medio_dichiarato": round(s["red"] / s["ab_red"]),
                  "pct_laureati_25_64": round(edu[g], 1),
                  "pct_lettori": lettura[g][0],
                  "ultimo_libro_da_biblioteca": acquisto[g][0],
                  "ultimo_libro_in_libreria": acquisto[g][1],
                  "ultimo_libro_in_centro_commerciale": acquisto[g][2]})


def ranghi(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v)
    i = 0
    while i < len(o):  # ranghi medi in caso di pari merito
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def pearson(a, b):
    n = len(a); ma, mb = sum(a) / n, sum(b) / n
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def residui(y, controlli):
    n = len(y); cols = [[1.0] * n] + controlli; k = len(cols)
    M = [[sum(cols[i][t] * cols[j][t] for t in range(n)) for j in range(k)] + [sum(cols[i][t] * y[t] for t in range(n))] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]; M[r] = [a - f * c for a, c in zip(M[r], M[i])]
    beta = [M[i][k] / M[i][i] for i in range(k)]
    return [y[t] - sum(beta[i] * cols[i][t] for i in range(k)) for t in range(n)]


col = lambda c: [r[c] for r in righe]


def legame(x, y, controlli=()):
    rx, ry = ranghi(col(x)), ranghi(col(y))
    if controlli:
        rc = [ranghi(col(c)) for c in controlli]
        rx, ry = residui(rx, rc), residui(ry, rc)
    return round(pearson(rx, ry), 2)


L, R, E = "pct_lettori", "reddito_medio_dichiarato", "pct_laureati_25_64"
legami = [
    {"cosa": "reddito ~ lettori", "valore": legame(R, L)},
    {"cosa": "laureati ~ lettori", "valore": legame(E, L)},
    {"cosa": "libreria nel comune ~ lettori", "valore": legame("pct_abitanti_con_libreria_nel_comune", L)},
    {"cosa": "libreria nel comune ~ lettori, a parità di reddito e laureati", "valore": legame("pct_abitanti_con_libreria_nel_comune", L, [R, E])},
    {"cosa": "ultimo libro da biblioteca ~ lettori", "valore": legame("ultimo_libro_da_biblioteca", L)},
    {"cosa": "ultimo libro da biblioteca ~ lettori, a parità di laureati", "valore": legame("ultimo_libro_da_biblioteca", L, [E])},
    {"cosa": "ultimo libro da biblioteca ~ lettori, a parità di reddito", "valore": legame("ultimo_libro_da_biblioteca", L, [R])},
    {"cosa": "ultimo libro da biblioteca ~ lettori, a parità di reddito e laureati", "valore": legame("ultimo_libro_da_biblioteca", L, [R, E])},
]
json.dump({"nota": "Correlazione per ranghi tra 20 regioni (da -1 a +1). Indicativa, non causale.",
           "anno_laureati": anno_edu, "anno_lettura": "2024", "regioni": righe, "legami": legami},
          open(f"{OUT}/regioni.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
for x in legami:
    print(x)
