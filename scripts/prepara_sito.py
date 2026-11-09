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

# ---- bambini 0-14 lontani da biblioteca e libreria
import io
grezzo = open("data/grezzi/istat_elenco_comuni/Elenco-comuni-italiani.csv", "rb").read()
try:
    testo = grezzo.decode("utf-8")
except UnicodeDecodeError:
    testo = grezzo.decode("latin-1")
el = list(csv.reader(io.StringIO(testo), delimiter=";"))
h = [x.replace("\n", " ") for x in el[0]]
i_sig = next(i for i, x in enumerate(h) if x.startswith("Sigla automobilistica"))
i_nom = next(i for i, x in enumerate(h) if x.startswith("Denominazione dell'Unità territoriale sovracomunale"))
nome_prov = {r[i_sig]: r[i_nom] for r in el[1:] if len(r) > i_nom}

def bimbi(r):
    return int(r["abitanti_2026"]) * float(r["pct_0_14"] or 0) / 100

def oltre_min(r, k, s):
    return r[k] != "" and float(r[k]) > s

tot_b = sum(bimbi(r) for r in righe)
prov = {}
for r in righe:
    p_ = prov.setdefault(r["provincia"], [0, 0])
    p_[1] += bimbi(r)
    if oltre_min(r, "minuti_biblioteca", 15):
        p_[0] += bimbi(r)
top_prov = sorted(((k, a / t, a) for k, (a, t) in prov.items() if t), key=lambda x: -x[1])[:6]
lontani_bib = sorted((r for r in righe if oltre_min(r, "minuti_biblioteca", 15)), key=lambda r: -bimbi(r))
bambini = {
    "totale": round(tot_b),
    "oltre15_biblioteca": round(sum(bimbi(r) for r in righe if oltre_min(r, "minuti_biblioteca", 15))),
    "oltre15_libreria": round(sum(bimbi(r) for r in righe if oltre_min(r, "minuti_libreria", 15))),
    "oltre30_libreria": round(sum(bimbi(r) for r in righe if oltre_min(r, "minuti_libreria", 30))),
    "province": [{"sigla": k, "nome": nome_prov.get(k, k), "quota": round(100 * q, 1), "bambini": round(a)} for k, q, a in top_prov],
    "comuni": [{"comune": r["comune"], "provincia": r["provincia"], "bambini": round(bimbi(r)),
                "minuti": int(float(r["minuti_biblioteca"])), "verso": r["comune_biblioteca_piu_vicina"]} for r in lontani_bib[:5]],
}
json.dump(bambini, open(f"{OUT}/bambini.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# =====================================================================================
# TESTI: ogni numero che compare nelle frasi della pagina viene da qui.
# T[chiave] = stringa già formattata all'italiana; FONTE[chiave] = da dove viene.
# La pagina è sito/modello.html con segnaposto {{chiave}}; qui sotto la si compone in sito/index.html.
# =====================================================================================
import openpyxl
import re

T, FONTE = {}, {}

def it_int(v):
    return f"{round(v):,}".replace(",", ".")

def it_dec(v, d=1):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def metti(k, testo, fonte):
    T[k] = testo
    FONTE[k] = fonte

def su_dieci(q):
    """0.62 -> '6 su 10'"""
    return f"{round(q * 10)} su 10"

LET = "data/grezzi/istat_lettura/"
F25 = LET + "Tavole_lettura_libri_prelettura_biblioteche_2024_2025.xlsx"
F24 = LET + "Tavole_lettura_scrittura-libri_prelettura_podcast_2024.xlsx"

def righe_tav(f, foglio):
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    return [[c for c in r if c is not None] for r in wb[foglio].iter_rows(values_only=True)]

def riga_che_inizia(rr, testo):
    """La riga la cui prima cella è esattamente `testo` (spazi esclusi), altrimenti la prima che inizia così."""
    for r in rr:
        if r and str(r[0]).strip().lower() == testo.strip().lower():
            return r
    for r in rr:
        if r and str(r[0]).strip().lower().startswith(testo.strip().lower()):
            return r
    raise KeyError(testo)

# --- apertura
metti("pct_entro_15_libreria", it_dec(numeri["pct_entro_15_libreria"], 0), "matrici ISTAT + librerie mappe aperte")
metti("italia_lettori", it_dec(numeri["italia_lettori_tempo_libero"], 0), "ISTAT tavola 2 (2024), lettori nel tempo libero")
metti("italia_lettori_1d", it_dec(numeri["italia_lettori_tempo_libero"]), "ISTAT tavola 2 (2024)")
metti("italia_legge_largo", it_dec(numeri["italia_legge_qualsiasi_motivo"]), "ISTAT tavola 2 (2024), colonna «Sì»")

# --- capitolo 1
metti("comuni_senza_nulla", it_int(numeri["comuni_senza_nulla"]), "comuni.csv")
metti("abitanti_senza_nulla_mln", it_dec(numeri["abitanti_senza_nulla"] / 1e6), "comuni.csv")
deserti = [r for r in righe if not int(r["librerie_note"] or 0) and not int(r["biblioteche_aperte"] or 0)]
ab_d = sum(int(r["abitanti_2026"]) for r in deserti)
q_bib = sum(int(r["abitanti_2026"]) for r in deserti if r["minuti_biblioteca"] != "" and float(r["minuti_biblioteca"]) <= 15) / ab_d
q_lib = sum(int(r["abitanti_2026"]) for r in deserti if r["minuti_libreria"] != "" and float(r["minuti_libreria"]) <= 15) / ab_d
lontani_d = sum(int(r["abitanti_2026"]) for r in deserti if r["minuti_libreria"] == "" or float(r["minuti_libreria"]) > 15)
metti("deserti_bib15", su_dieci(q_bib), "comuni.csv")
metti("deserti_lib15", su_dieci(q_lib), "comuni.csv")
metti("deserti_lontani_mln", it_dec(lontani_d / 1e6), "comuni.csv")

# --- capitolo 2 (regioni)
RJ = {x["regione"]: x for x in A["regioni"]}
for nome, k in (("Puglia", "pug"), ("Trentino-Alto Adige", "taa"), ("Lazio", "laz"), ("Campania", "cam"), ("Valle d'Aosta", "vda")):
    x = RJ[nome]
    metti(f"{k}_l15", it_dec(x["pct_abitanti_libreria_entro_15_min"], 0), "regioni.json")
    metti(f"{k}_let", it_dec(x["pct_lettori"], 0), "regioni.json")
    metti(f"{k}_lau", it_dec(x["pct_laureati_25_64"]), "Eurostat edat_lfse_04")
    metti(f"{k}_ub", it_dec(x["ultimo_libro_da_biblioteca"]), "ISTAT tavola 18 (2024)")
t34 = righe_tav(F24, "tavola 34")
it34 = riga_che_inizia(t34, "Italia")
metti("motivo_noia", it_dec(it34[10], 0), "ISTAT tavola 34 (2024), «Mi annoia, non mi appassiona»")
metti("motivo_tempo", it_dec(it34[6], 0), "ISTAT tavola 34 (2024), «Ho poco tempo libero»")
metti("motivo_librerie", it_dec(it34[2]), "ISTAT tavola 34 (2024), «Non ci sono librerie o edicole vicino casa»")
# graduatoria lettura e laureati
ord_let = sorted(A["regioni"], key=lambda x: -x["pct_lettori"])
assert ord_let[0]["regione"] == "Trentino-Alto Adige", "il testo dice che il Trentino-Alto Adige legge di più"
ord_lau = sorted(A["regioni"], key=lambda x: -x["pct_laureati_25_64"])
assert ord_lau[0]["regione"] == "Lazio", "il testo dice che il Lazio ha più laureati"
assert RJ["Trentino-Alto Adige"]["pct_laureati_25_64"] < min(RJ["Lombardia"]["pct_laureati_25_64"], RJ["Emilia-Romagna"]["pct_laureati_25_64"])
NORD = {"Piemonte", "Valle d'Aosta", "Lombardia", "Trentino-Alto Adige", "Veneto", "Friuli-Venezia Giulia", "Liguria", "Emilia-Romagna"}
n_nord_sopra_lazio = sum(1 for x in A["regioni"] if x["regione"] in NORD and x["pct_lettori"] > RJ["Lazio"]["pct_lettori"])
metti("nord_sopra_lazio", {5: "cinque", 6: "sei", 4: "quattro", 3: "tre", 7: "sette", 8: "otto"}.get(n_nord_sopra_lazio, str(n_nord_sopra_lazio)), "regioni.json")

# --- capitolo 3: lettura nel tempo libero per titolo di studio (25+, maschi e femmine, migliaia)
t4 = righe_tav(F25, "tavola 4 segue")
inizio = next(i for i, r in enumerate(t4) if r and str(r[0]).strip().upper().startswith("MASCHI E FEMMINE"))
tot = next(i for i in range(inizio, len(t4)) if t4[i] and str(t4[i][0]).strip() == "TOTALE")
studio = {}
for r in [x for x in t4[tot:tot + 10] if x][:5]:
    titolo = r[1] if str(r[0]).strip() == "TOTALE" else r[0]
    v = r[2:] if str(r[0]).strip() == "TOTALE" else r[1:]
    no, si, solo_lib, sia = v[0], v[1], v[2], v[3]
    studio[str(titolo).strip()] = 100 * (solo_lib + sia) / (no + si)
G3 = [("Laurea", studio["Laurea"]), ("Diploma", studio["Diploma superiore"]),
      ("Licenza media", studio["Licenza media"]), ("Licenza elementare", studio["Licenza elementare"])]
metti("g3_dati", json.dumps([{"l": l, "v": round(v, 1)} for l, v in G3], ensure_ascii=False), "ISTAT tavola 4 segue (2024)")
metti("laureati_leggono", {7: "sette su dieci", 6: "due su tre", 8: "otto su dieci"}.get(round(studio["Laurea"] / 10), su_dieci(studio["Laurea"] / 100)), "ISTAT tavola 4 segue")
if 63 <= studio["Laurea"] <= 70:
    T["laureati_leggono"] = "due laureati su tre"
else:
    T["laureati_leggono"] = su_dieci(studio["Laurea"] / 100) + " laureati"
metti("elementare_leggono", ("poco più di una persona su dieci" if 10 <= studio["Licenza elementare"] < 15
                           else su_dieci(studio["Licenza elementare"] / 100) + " persone"), "ISTAT tavola 4 segue")

# --- capitolo biblioteca: ultimo libro da biblioteca per tipo di comune
t18 = righe_tav(F24, "tavola 18")
metti("ub_2_10mila", it_dec(riga_che_inizia(t18, "Da 2.001 a 10.000")[4]), "ISTAT tavola 18 (2024), «In prestito da una biblioteca»")
metti("ub_centri", it_dec(riga_che_inizia(t18, "Comune centro dell'area metropolitana")[4]), "ISTAT tavola 18 (2024)")

# --- metodo
bib_grezze = json.load(open("data/grezzi/iccu_biblioteche/biblioteche.json", encoding="utf-8"))["biblioteche"]
pubbl = [x for x in bib_grezze if x.get("tipologia-funzionale") == "Pubblica" and x.get("stato-registrazione") is None
         and not (x.get("accesso") or {}).get("riservato")]
quota_com = sum(1 for x in pubbl if x.get("tipologia-amministrativa") == "Comune") / len(pubbl)
metti("bib_comunali_su10", su_dieci(quota_com), "ICCU anagrafe")
import pandas as pd
pv = pd.read_csv("data/librerie/punti_vendita.csv")
LB = pv[pv.gruppo.isin(["libreria", "libreria dell'usato", "libreria universitaria"]) & ~pv.stato.isin(["permanently_closed", "doppione"]) & pv.pro_com.notna()]
conf = LB[(pd.to_numeric(LB.affidabilita, errors="coerce") >= 0.9) | (LB.anche_in_osm == "sì")]
metti("librerie_totali", it_int(numeri["librerie_totali"]), "per_comune.csv")
metti("comuni_con_libreria", it_int(numeri["comuni_con_libreria"]), "per_comune.csv")
metti("librerie_confermate_circa", it_int(round(len(conf), -2)), "punti_vendita.csv, affidabilità ≥ 0,9 o presenti anche in OSM")
metti("comuni_senza_tempi", str(numeri["comuni_senza_tempi"]), "comuni.csv")
metti("abitanti_senza_tempi", it_int(numeri["abitanti_senza_tempi"]), "comuni.csv")
for k, v in numeri["legami"].items():
    chiave = "leg_" + re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_")
    metti(chiave, it_dec(v, 2), "regioni.json, correlazione per ranghi")
Cj = json.load(open("data/schede/confronti.json", encoding="utf-8"))
def red(f, p):
    return next(t["reddito_medio"] for t in Cj["tabella"] if t["fascia"] == f and t["profilo"] == p)
r_n, r_lb = red("3.000-9.999", "Nessuna delle due"), red("3.000-9.999", "Libreria e biblioteca")
metti("red_3_10_nulla", it_int(r_n), "confronti.json")
metti("red_3_10_tutto", it_int(r_lb), "confronti.json")
metti("red_3_10_diff", it_int(round(r_lb - r_n, -2)), "confronti.json")

# --- quote dette a parole («poco più di una persona su quattro»), calcolate e non scritte a mano
NUM_P = {2: "due", 3: "tre", 4: "quattro", 5: "cinque", 6: "sei", 7: "sette", 8: "otto", 9: "nove", 10: "dieci", 100: "cento"}

def a_parole(pct, uno):
    """pct in percento -> «circa una persona su due», «poco più di una persona su quattro»…"""
    best = min(NUM_P, key=lambda n: abs(pct - 100 / n) / (100 / n))
    rif = 100 / best
    scarto = (pct - rif) / rif
    pre = "circa" if abs(scarto) <= 0.06 else ("poco più di" if scarto > 0 else "poco meno di")
    if abs(scarto) > 0.25:
        raise ValueError(f"{pct}% non si dice bene a parole")
    return f"{pre} {uno} su {NUM_P[best]}"

def piu_di_su_dieci(q):
    return f"più di {int(q * 10)} su 10"

metti("pug_let_parole", a_parole(RJ["Puglia"]["pct_lettori"], "una persona"), "regioni.json")
metti("taa_let_parole", a_parole(RJ["Trentino-Alto Adige"]["pct_lettori"], "una persona"), "regioni.json")
metti("deserti_bib15", piu_di_su_dieci(q_bib), "comuni.csv")
metti("deserti_lib15", piu_di_su_dieci(q_lib), "comuni.csv")
top_ub = sorted(A["regioni"], key=lambda x: -x["ultimo_libro_da_biblioteca"])[:2]
assert {x["regione"] for x in top_ub} == {"Trentino-Alto Adige", "Valle d'Aosta"}, "il testo dice che TAA e VdA usano di più la biblioteca"
assert RJ["Valle d'Aosta"]["pct_laureati_25_64"] < RJ["Lombardia"]["pct_laureati_25_64"]
metti("taa_vda_ub_parole", a_parole(sum(x["ultimo_libro_da_biblioteca"] for x in top_ub) / 2, "un lettore"), "ISTAT tavola 18 (2024)")
assert it34[2] < 1, "il testo dice «meno di 1 su 100»"
metti("motivo_librerie_parole", "meno di 1 su 100", "ISTAT tavola 34 (2024), «Non ci sono librerie o edicole vicino casa»: " + it_dec(it34[2]) + "%")
q_b = bambini["oltre15_biblioteca"] / bambini["totale"] * 100
metti("bambini_bib15_parole", a_parole(q_b, "un bambino"), "comuni.csv, quota 0-14 ISTAT 2026")
metti("bambini_lib15_parole", a_parole(bambini["oltre15_libreria"] / bambini["totale"] * 100, "un bambino"), "comuni.csv")

# --- date delle fonti (dai registri scritti dagli script di scaricamento)
from email.utils import parsedate_to_datetime
from datetime import datetime
reg = json.load(open("data/grezzi/registro.json", encoding="utf-8"))
d_iccu = parsedate_to_datetime(reg["file"]["iccu_biblioteche"]["ultima_modifica_alla_fonte"])
fl = json.load(open("data/librerie/fonti.json", encoding="utf-8"))
d_osm = datetime.fromisoformat(fl["estrazione"])
data_it = lambda d: f"{d.day}/{d.month}/{d.year}"
metti("data_iccu", data_it(d_iccu), "data/grezzi/registro.json")
metti("data_osm", data_it(d_osm), "data/librerie/fonti.json")
metti("release_overture", fl["fonti"]["overture_places"]["release"].removesuffix(".0"), "data/librerie/fonti.json")

# --- numeri presi da studi esterni: sono nella pagina come citazioni, con la loro fonte
CIT = json.load(open("sito/citazioni.json", encoding="utf-8"))
for k, c in CIT.items():
    metti(k, c["testo"], c["fonte"] + " · " + c["url"])

json.dump(numeri, open(f"{OUT}/numeri.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"testi": T, "fonti": FONTE}, open(f"{OUT}/testi.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# --- composizione della pagina
modello = open("sito/modello.html", encoding="utf-8").read()
mancanti = sorted(set(re.findall(r"\{\{([a-z0-9_]+)\}\}", modello)) - set(T))
if mancanti:
    raise SystemExit("Segnaposto senza valore: " + ", ".join(mancanti))
pagina = re.sub(r"\{\{([a-z0-9_]+)\}\}", lambda m: T[m.group(1)], modello)
open(f"{OUT}/index.html", "w", encoding="utf-8").write(pagina)
print("Pagina composta:", len(T), "valori disponibili")
