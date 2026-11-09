"""Controlli automatici sui dati, a ogni aggiornamento.

Ogni controllo ha un esito: OK, AVVISO (da guardare, non blocca) o ERRORE (blocca la pubblicazione).
Scrive sito/verifica.md (leggibile) e sito/verifica.json, ed esce con errore se c'è almeno un ERRORE.
"""
import csv
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

esiti = []


def esito(livello, nome, dettaglio):
    esiti.append({"esito": livello, "controllo": nome, "dettaglio": dettaglio})


righe = list(csv.DictReader(open("data/schede/comuni.csv", encoding="utf-8")))
sito_comuni = json.load(open("sito/comuni.json", encoding="utf-8"))
geo = json.load(open("data/geo/italia.topojson", encoding="utf-8"))["objects"]["comuni"]["geometries"]
codici_mappa = {g["properties"]["PRO_COM_T"] for g in geo}

# 1. ogni comune della mappa ha i suoi dati, e viceversa
senza_dati = sorted(codici_mappa - set(sito_comuni))
senza_mappa = sorted(set(sito_comuni) - codici_mappa)
esito("ERRORE" if senza_dati or senza_mappa else "OK", "Comuni della mappa con dati",
      f"{len(codici_mappa)} sulla mappa, {len(sito_comuni)} con dati; senza dati: {senza_dati[:10]}; senza mappa: {senza_mappa[:10]}")

# 2. abitanti: il totale torna con la fonte ISTAT
tot_posas = 0
with open("data/grezzi/istat_popolazione_2026/POSAS_2026_it_Comuni.csv", encoding="utf-8-sig") as f:
    next(f)
    for r in csv.DictReader(f, delimiter=";"):
        if r["Età"] == "999":
            tot_posas += int(r["Totale"])
tot_schede = sum(int(r["abitanti_2026"]) for r in righe)
esito("OK" if tot_posas == tot_schede else "ERRORE", "Abitanti totali uguali a ISTAT",
      f"schede {tot_schede:,} · ISTAT POSAS {tot_posas:,}".replace(",", "."))

# 3. valori dentro i limiti
fuori = []
for r in righe:
    for k in ("pct_0_14", "pct_65_piu"):
        if r[k] != "" and not 0 <= float(r[k]) <= 100:
            fuori.append((r["comune"], k, r[k]))
    for k in ("minuti_libreria", "minuti_biblioteca"):
        if r[k] != "" and float(r[k]) < 0:
            fuori.append((r["comune"], k, r[k]))
    if int(r["librerie_note"]) > 0 and r["minuti_libreria"] not in ("", "0", "0.0"):
        fuori.append((r["comune"], "libreria nel comune ma minuti > 0", r["minuti_libreria"]))
esito("ERRORE" if fuori else "OK", "Valori nei limiti (quote 0-100, minuti ≥ 0, coerenza)", f"{len(fuori)} problemi {fuori[:5]}")

senza_tempi = [r["comune"] for r in righe if r["minuti_libreria"] == "" and not int(r["librerie_note"])]
esito("AVVISO" if senza_tempi else "OK", "Comuni senza tempi di percorrenza",
      f"{len(senza_tempi)}: {', '.join(senza_tempi)} (dichiarati nel Metodo)")

# 4. librerie contate: niente editori, agenzie, doppioni
pv = list(csv.DictReader(open("data/librerie/punti_vendita.csv", encoding="utf-8")))
LIB = ("libreria", "libreria dell'usato", "libreria universitaria")
contate = [r for r in pv if r["gruppo"] in LIB and r["stato"] not in ("permanently_closed", "doppione")]
sospetti = [r["nome"] for r in contate if r["nome"] and "librer" not in r["nome"].lower() and re.search(
    r"editor|edizioni|editrice|agenzia|distribuz|tipografi|legatori|^amazon(?!.*counter)|dipartimento", r["nome"].lower())]
esito("ERRORE" if sospetti else "OK", "Nessun editore, agenzia o distributore tra le librerie contate", f"{len(sospetti)} {sospetti[:10]}")
vicini = defaultdict(list)
doppi = 0
for r in contate:
    if not r["nome"]:
        continue
    k = re.sub(r"[^a-z0-9]", "", r["nome"].lower())
    lat, lon = float(r["lat"]), float(r["lon"])
    if any(math.hypot((lat - a) * 111000, (lon - b) * 111000 * math.cos(math.radians(lat))) < 150 for a, b in vicini[k]):
        doppi += 1
    vicini[k].append((lat, lon))
esito("ERRORE" if doppi else "OK", "Nessun doppione tra le librerie contate", f"{doppi} doppioni")
senza_nome = sum(1 for r in contate if not r["nome"])
esito("AVVISO" if senza_nome else "OK", "Librerie senza nome", f"{senza_nome} punti contati senza nome sulle mappe")

# 5. biblioteche: quante escludiamo e perché
bib = json.load(open("data/grezzi/iccu_biblioteche/biblioteche.json", encoding="utf-8"))["biblioteche"]
pubbl = [x for x in bib if x.get("tipologia-funzionale") == "Pubblica"]
stati = defaultdict(int)
for x in pubbl:
    s = x.get("stato-registrazione") or "attiva"
    stati["confluita in altra" if s.startswith("Biblioteca confluita") else s] += 1
esito("AVVISO", "Biblioteche di pubblica lettura escluse per stato", "; ".join(f"{k}: {v}" for k, v in sorted(stati.items(), key=lambda x: -x[1])))

# 6. regioni complete
reg = json.load(open("sito/regioni.json", encoding="utf-8"))
vuoti = [(x["r"], k) for x in reg for k, v in x.items() if v is None]
esito("ERRORE" if len(reg) != 20 or vuoti else "OK", "Regioni complete", f"{len(reg)} regioni; valori mancanti: {vuoti}")

# 7. cambi grandi rispetto alla versione precedente
try:
    prima = json.loads(subprocess.run(["git", "show", "HEAD:sito/numeri.json"], capture_output=True, text=True, check=True).stdout)
    ora = json.load(open("sito/numeri.json", encoding="utf-8"))
    salti = []
    for k, v in ora.items():
        p = prima.get(k)
        if isinstance(v, (int, float)) and isinstance(p, (int, float)) and p:
            if abs(v - p) / abs(p) > 0.10:
                salti.append(f"{k}: {p} → {v}")
    esito("AVVISO" if salti else "OK", "Cambi oltre il 10% rispetto alla versione precedente", "; ".join(salti) or "nessuno")
except Exception as e:  # primo giro o storico non disponibile
    esito("AVVISO", "Cambi rispetto alla versione precedente", f"confronto non possibile: {e}")

# 8. la pagina non ha numeri scritti a mano
vp = subprocess.run([sys.executable, "scripts/verifica_pagina.py"], capture_output=True, text=True)
esito("OK" if vp.returncode == 0 else "ERRORE", "Numeri della pagina tutti dai dati", vp.stdout.strip().splitlines()[-1] if vp.stdout else vp.stderr[-300:])

# rapporto
ora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
json.dump({"data": ora, "esiti": esiti}, open("sito/verifica.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open("sito/verifica.md", "w", encoding="utf-8") as f:
    f.write(f"# Verifica dei dati · {ora}\n\n")
    for e in esiti:
        f.write(f"- **{e['esito']}** · {e['controllo']}: {e['dettaglio']}\n")
for e in esiti:
    print(f"{e['esito']:7} {e['controllo']}: {e['dettaglio'][:160]}")
sys.exit(1 if any(e["esito"] == "ERRORE" for e in esiti) else 0)
