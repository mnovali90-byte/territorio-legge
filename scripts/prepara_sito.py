"""Prepara i file leggeri che la pagina carica, a partire dai dati calcolati.

Uscite in sito/:
  comuni.json    {pro_com: [nome, prov, regione, abitanti, n_bib, min_bib, n_lib, min_lib,
                  comune_lib_vicina, comune_bib_vicina, reddito, nomi_bib, nomi_lib, pct_65]}
  regioni.json   una riga per regione con sigla e indicatori
  confronti.json copia di data/schede/confronti.json
  numeri.json    i numeri che la pagina cita nei testi, calcolati qui e non scritti a mano
"""
import csv
import json
import os
import shutil

OUT = "sito"
os.makedirs(OUT, exist_ok=True)

SIGLE = {"Abruzzo": "ABR", "Basilicata": "BAS", "Calabria": "CAL", "Campania": "CAM", "Emilia-Romagna": "EMR",
         "Friuli-Venezia Giulia": "FVG", "Lazio": "LAZ", "Liguria": "LIG", "Lombardia": "LOM", "Marche": "MAR",
         "Molise": "MOL", "Piemonte": "PIE", "Puglia": "PUG", "Sardegna": "SAR", "Sicilia": "SIC",
         "Toscana": "TOS", "Trentino-Alto Adige": "TAA", "Umbria": "UMB", "Valle d'Aosta": "VDA", "Veneto": "VEN"}


def num(x, tipo=int):
    return tipo(float(x)) if x not in ("", None) else None


righe = list(csv.DictReader(open("data/schede/comuni.csv", encoding="utf-8")))

# La mappa usa i codici ISTAT dei confini 2026. In Sardegna le province sono cambiate e alcuni dati
# arrivano ancora con i codici vecchi: li ricolleghiamo al codice nuovo tramite il nome del comune.
geo = json.load(open("data/geo/italia.topojson", encoding="utf-8"))["objects"]["comuni"]["geometries"]
codici_mappa = {g["properties"]["PRO_COM_T"] for g in geo}
per_nome = {}
for g in geo:
    per_nome.setdefault(g["properties"]["COMUNE"].strip().lower(), []).append(g["properties"]["PRO_COM_T"])
ricollegati, senza_mappa = 0, []
for r in righe:
    if r["pro_com"] in codici_mappa:
        continue
    usati = {x["pro_com"] for x in righe}
    cand = [c for c in per_nome.get(r["comune"].strip().lower(), []) if c not in usati]
    if len(cand) == 1:
        r["pro_com"] = cand[0]
        ricollegati += 1
    else:
        senza_mappa.append(r["comune"])
print("Codici ricollegati per nome:", ricollegati, "· senza corrispondenza sulla mappa:", senza_mappa)

comuni = {}
for r in righe:
    comuni[r["pro_com"]] = [
        r["comune"], r["provincia"], r["regione"], num(r["abitanti_2026"]),
        num(r["biblioteche_aperte"]), num(r["minuti_biblioteca"]),
        num(r["librerie_note"]), num(r["minuti_libreria"]),
        r["comune_libreria_piu_vicina"] or None, r["comune_biblioteca_piu_vicina"] or None,
        num(r["reddito_medio_dichiarato_2024"]),
        [x for x in r["biblioteche_nomi"].split(" | ") if x],
        [x for x in r["librerie_nomi"].split(" | ") if x],
        num(r["pct_65_piu"], float),
    ]
json.dump(comuni, open(f"{OUT}/comuni.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

A = json.load(open("data/analisi/regioni.json", encoding="utf-8"))
reg = [{"r": x["regione"], "s": SIGLE[x["regione"]], "lib": x["pct_abitanti_con_libreria_nel_comune"],
        "l15": x["pct_abitanti_libreria_entro_15_min"], "bib": x["pct_abitanti_con_biblioteca_nel_comune"],
        "let": x["pct_lettori"], "ub": x["ultimo_libro_da_biblioteca"], "ul": x["ultimo_libro_in_libreria"],
        "uc": x["ultimo_libro_in_centro_commerciale"], "lau": x["pct_laureati_25_64"],
        "red": x["reddito_medio_dichiarato"]} for x in A["regioni"]]
json.dump(reg, open(f"{OUT}/regioni.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
shutil.copy("data/schede/confronti.json", f"{OUT}/confronti.json")

# numeri citati nei testi
ab = lambda r: num(r["abitanti_2026"]) or 0
tot = sum(ab(r) for r in righe)
oltre = lambda campo, m: sum(ab(r) for r in righe if r[campo] and float(r[campo]) > m)
entro = lambda campo, m: sum(ab(r) for r in righe if r[campo] != "" and float(r[campo]) <= m)
senza_tempo = [r for r in righe if r["minuti_libreria"] == "" and not int(r["librerie_note"] or 0)]
nulla = [r for r in righe if not int(r["librerie_note"] or 0) and not int(r["biblioteche_aperte"] or 0)]
legami = {x["cosa"]: x["valore"] for x in A["legami"]}
numeri = {
    "abitanti_totali": tot,
    "librerie_totali": sum(int(r["librerie_note"] or 0) for r in righe),
    "comuni_con_libreria": sum(1 for r in righe if int(r["librerie_note"] or 0)),
    "lontani_libreria_30": oltre("minuti_libreria", 30),
    "lontani_biblioteca_30": oltre("minuti_biblioteca", 30),
    "pct_entro_15_libreria": round(100 * entro("minuti_libreria", 15) / tot, 1),
    "comuni_senza_tempi": len(senza_tempo),
    "abitanti_senza_tempi": sum(ab(r) for r in senza_tempo),
    "comuni_senza_nulla": len(nulla),
    "abitanti_senza_nulla": sum(ab(r) for r in nulla),
    "italia_lettori_tempo_libero": A["italia"]["pct_lettori"],
    "italia_legge_qualsiasi_motivo": A["italia"]["pct_legge_libri_qualsiasi_motivo"],
    "legami": legami,
}
json.dump(numeri, open(f"{OUT}/numeri.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(numeri, ensure_ascii=False, indent=1))
