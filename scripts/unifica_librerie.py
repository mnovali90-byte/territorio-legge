"""
Il territorio legge — unione dei punti vendita di libri da Overture e OpenStreetMap.

Legge i file prodotti da librerie_mappe_aperte.py e scrive:
  data/librerie/punti_vendita.csv   un punto per riga, con tipo, fonte, affidabilità e stato: niente viene scartato
  data/librerie/per_comune.csv      conteggi per comune e per gruppo di negozio
I filtri (cosa conta come "libreria") si applicano dopo, sulla mappa.
"""

import csv
import math
from collections import Counter, defaultdict

D = "data/librerie"
RAGGIO_M = 150  # due punti più vicini di così sono considerati lo stesso negozio

GRUPPI = {
    "bookstore": "libreria",
    "used_bookstore": "libreria dell'usato",
    "academic_bookstore": "libreria universitaria",
    "comic_books_store": "fumetteria",
    "newspaper_and_magazines_store": "edicola",
    "video_game_store": "videogiochi",
    "music_and_dvd_store": "musica e video",
    "vinyl_record_store": "musica e video",
    "video_and_video_game_rental": "musica e video",
    "books_music_and_video_store": "libri, musica e video (generico)",
    "book_magazine_distribution": "distribuzione libri e riviste",
    "bookbinding": "legatoria",
    "bookkeeper": "contabile (non è una libreria)",
}


def primario(tassonomia):
    if "'primary': " not in (tassonomia or ""):
        return ""
    return tassonomia.split("'primary': ")[1].split(",")[0].strip()


def gruppo(r):
    p = primario(r["tassonomia"])
    if r["motivo"] == "nome":
        return "altro, con 'libreria' nel nome"
    return GRUPPI.get(p, "altro")  # i tipi nuovi finiscono qui finché non li etichettiamo


def cartoleria(nome):
    n = (nome or "").lower()
    return "sì" if ("cartol" in n) else "no"


def cella(lat, lon):
    return (round(lat * 100), round(lon * 100))


ov = [r for r in csv.DictReader(open(f"{D}/overture_candidati.csv", encoding="utf-8")) if r["pro_com"]]
osm = [r for r in csv.DictReader(open(f"{D}/osm_librerie.csv", encoding="utf-8")) if r["pro_com"]]

griglia = defaultdict(list)
for i, r in enumerate(ov):
    griglia[cella(float(r["lat"]), float(r["lon"]))].append(i)


def vicino(lat, lon):
    k = cella(lat, lon)
    best, best_d = None, RAGGIO_M
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            for i in griglia[(k[0] + a, k[1] + b)]:
                r = ov[i]
                if gruppo(r) not in ("libreria", "libreria dell'usato", "libreria universitaria",
                                     "fumetteria", "libri, musica e video (generico)",
                                     "altro, con 'libreria' nel nome"):
                    continue
                dy = (float(r["lat"]) - lat) * 111_000
                dx = (float(r["lon"]) - lon) * 111_000 * math.cos(math.radians(lat))
                d = math.hypot(dx, dy)
                if d < best_d:
                    best, best_d = i, d
    return best


in_osm = set()
solo_osm = []
for r in osm:
    i = vicino(float(r["lat"]), float(r["lon"]))
    if i is None:
        solo_osm.append(r)
    else:
        in_osm.add(i)

CAMPI = ["id", "nome", "gruppo", "tipo_originale", "cartoleria_nel_nome", "fonte", "anche_in_osm",
         "affidabilita", "stato", "pro_com", "comune", "regione", "lon", "lat", "licenza"]
righe = []
for i, r in enumerate(ov):
    righe.append({
        "id": f"overture:{r['id']}", "nome": r["nome"], "gruppo": gruppo(r),
        "tipo_originale": primario(r["tassonomia"]) or r["categoria"],
        "cartoleria_nel_nome": cartoleria(r["nome"]), "fonte": "Overture",
        "anche_in_osm": "sì" if i in in_osm else "no",
        "affidabilita": r["affidabilita"], "stato": r["stato"] or "non indicato",
        "pro_com": r["pro_com"], "comune": r["comune"], "regione": r["regione"],
        "lon": r["lon"], "lat": r["lat"], "licenza": r["licenze"],
    })
for r in solo_osm:
    righe.append({
        "id": f"osm:{r['id']}", "nome": r["nome"],
        "gruppo": "libreria dell'usato" if r.get("usato") in ("only", "yes") else "libreria",
        "tipo_originale": "shop=books", "cartoleria_nel_nome": cartoleria(r["nome"]),
        "fonte": "OpenStreetMap", "anche_in_osm": "sì", "affidabilita": "",
        "stato": "non indicato", "pro_com": r["pro_com"], "comune": r["comune"],
        "regione": r["regione"], "lon": r["lon"], "lat": r["lat"], "licenza": "ODbL-1.0",
    })

righe.sort(key=lambda x: (x["regione"], x["comune"], x["gruppo"], x["nome"] or ""))
with open(f"{D}/punti_vendita.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=CAMPI)
    w.writeheader()
    w.writerows(righe)

# conteggi per comune: solo punti non chiusi, per gruppo
gruppi = sorted({r["gruppo"] for r in righe})
conti = defaultdict(Counter)
info = {}
for r in righe:
    if r["stato"] == "permanently_closed":
        continue
    conti[r["pro_com"]][r["gruppo"]] += 1
    info[r["pro_com"]] = (r["comune"], r["regione"])
with open(f"{D}/per_comune.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["pro_com", "comune", "regione"] + gruppi)
    for pc in sorted(conti):
        w.writerow([pc, *info[pc]] + [conti[pc][g] for g in gruppi])

print(f"Punti totali: {len(righe)}  (Overture {len(ov)}, solo OSM {len(solo_osm)})")
print("Per gruppo:", Counter(r["gruppo"] for r in righe).most_common())
print("Stato:", Counter(r["stato"] for r in righe).most_common())
print("Comuni con almeno un punto:", len(conti))
