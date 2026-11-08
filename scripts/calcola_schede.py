"""
Il territorio legge — calcolo della scheda di ogni comune.

Usa i file in data/grezzi/ (scarica_fonti.py), data/librerie/per_comune.csv (unifica_librerie.py)
e le matrici dei tempi ISTAT, scaricate qui al volo perché troppo grandi per il repository.

Regole (scritte anche nella pagina Metodo):
- Biblioteca = tipologia funzionale "Pubblica" nell'Anagrafe ICCU, senza stato di registrazione
  (quindi non chiusa, non più esistente, non in allestimento) e con accesso non riservato.
- Libreria = gruppi "libreria", "libreria dell'usato", "libreria universitaria", non chiusi.
- Tempo = TEP_TOT della matrice ISTAT: minuti in auto da municipio a municipio, con traffico,
  scenario di un giorno feriale alle 8:30 (ottobre 2020), comuni ai confini del 1/1/2021.
  Se il comune ha già un punto, il tempo è 0.
- Reddito medio = reddito complessivo dichiarato / numero di dichiaranti con reddito complessivo (MEF).
"""
import csv
import io
import json
import os
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone

G = "data/grezzi"
OUT = "data/schede"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (territorio-legge; open data research)"}
REGIONI_MATRICI = ["Abruzzo", "Basilicata", "Calabria", "Campania", "Emilia", "Friuli", "Lazio", "Liguria",
                   "Lombardia", "Marche", "Molise", "Piemonte", "Puglia", "Sardegna", "Sicilia", "Toscana",
                   "Trentino", "Umbria", "ValledAosta", "Veneto"]


NOMI_REGIONE = {"Emilia Romagna": "Emilia-Romagna", "Friuli Venezia Giulia": "Friuli-Venezia Giulia",
                "Valle d'Aosta": "Valle d'Aosta/Vallée d'Aoste", "Trentino Alto Adige(P.A.Bolzano)": "Trentino-Alto Adige/Südtirol",
                "Trentino Alto Adige(P.A.Trento)": "Trentino-Alto Adige/Südtirol"}


def regione_std(nome):
    """Le fonti scrivono le regioni in modi diversi: usiamo sempre la forma dei confini ISTAT."""
    return NOMI_REGIONE.get(nome, nome) if nome else nome


def pc(x):
    return str(x).strip().zfill(6)


def numero(s):
    s = (s or "").strip().replace(".", "").replace(",", ".") if "," in (s or "") else (s or "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- comuni e abitanti (ISTAT 2026)
comuni = {}
eta = defaultdict(lambda: [0, 0])  # [0-14 anni, 65 anni e più]
for r in csv.reader(open(f"{G}/istat_popolazione_2026/POSAS_2026_it_Comuni.csv", encoding="utf-8-sig"), delimiter=";"):
    if len(r) != 6:
        continue
    if r[2] == "999":
        comuni[pc(r[0])] = {"pro_com": pc(r[0]), "comune": r[1], "abitanti": int(r[5])}
    elif r[2].isdigit():
        if int(r[2]) <= 14:
            eta[pc(r[0])][0] += int(r[5])
        elif int(r[2]) >= 65:
            eta[pc(r[0])][1] += int(r[5])

# provincia e regione dall'anagrafe ICCU dove c'è, poi dalle librerie
# ---------------------------------------------------------------- biblioteche (ICCU)
bib = json.load(open(f"{G}/iccu_biblioteche/biblioteche.json", encoding="utf-8"))
estrazione_iccu = bib["metadati"].get("data-estrazione")
# Biblioteca aperta a tutti: di pubblica lettura, ma anche di conservazione, «importante non specializzata»
# e nazionale (es. la Biblioteca provinciale di Matera è registrata come «di conservazione»), purché
# attiva e con accesso non riservato. Le specializzate, scolastiche e universitarie restano fuori.
TIPI_APERTI = {"Pubblica", "Di conservazione", "Importante non specializzata", "Nazionale"}
# Le non «pubbliche» contano solo se gestite da un ente pubblico territoriale o dallo Stato: così entra la
# Provinciale di Matera, ma restano fuori biblioteche di diocesi, fondazioni private, ospedali e centri di ricerca.
ENTI_PUBBLICI = {"Comune", "Provincia", "Città metropolitana", "Regione", "Ministero della Cultura",
                 "Direzione generale Biblioteche e istituti culturali",
                 "Consorzio e/o associazioni di regioni, province, comuni e comunità montane"}
bib_per_comune = defaultdict(list)
pubbliche_per_comune = defaultdict(int)
luogo = {}
for b in bib["biblioteche"]:
    com = b["indirizzo"]["comune"]
    luogo.setdefault(pc(com["istat"]), (b["indirizzo"].get("provincia", {}).get("nome"),
                                        b["indirizzo"].get("regione", {}).get("nome") if isinstance(b["indirizzo"].get("regione"), dict) else b["indirizzo"].get("regione")))
    attiva = b.get("stato-registrazione") is None and not (b.get("accesso") or {}).get("riservato")
    tipo, ente = b.get("tipologia-funzionale"), b.get("tipologia-amministrativa")
    aperta = tipo == "Pubblica" or (tipo in TIPI_APERTI and ente in ENTI_PUBBLICI)
    if attiva and aperta:
        bib_per_comune[pc(com["istat"])].append(b["denominazioni"]["ufficiale"])
        if b.get("tipologia-funzionale") == "Pubblica":
            pubbliche_per_comune[pc(com["istat"])] += 1

# ---------------------------------------------------------------- librerie (mappe aperte)
GRUPPI_LIBRERIA = ["libreria", "libreria dell'usato", "libreria universitaria"]
lib_per_comune = {}
regione_lib = {}
for r in csv.DictReader(open("data/librerie/per_comune.csv", encoding="utf-8")):
    n = sum(int(r.get(g) or 0) for g in GRUPPI_LIBRERIA)
    regione_lib[pc(r["pro_com"])] = r["regione"]
    if n:
        lib_per_comune[pc(r["pro_com"])] = n
nomi_librerie = defaultdict(list)
for r in csv.DictReader(open("data/librerie/punti_vendita.csv", encoding="utf-8")):
    if r["gruppo"] in GRUPPI_LIBRERIA and r["stato"] not in ("permanently_closed", "doppione") and r["nome"]:
        nomi_librerie[pc(r["pro_com"])].append(r["nome"])

# I confini 2026 usano i codici delle nuove province sarde, il file degli abitanti ancora quelli vecchi:
# ricolleghiamo per nome del comune, solo quando il nome è unico in Italia.
per_nome = defaultdict(list)
for p, c in comuni.items():
    per_nome[c["comune"].lower()].append(p)
nomi_lib_com = {pc(r["pro_com"]): r["comune"] for r in csv.DictReader(open("data/librerie/per_comune.csv", encoding="utf-8"))}
ricodificati = {}
for vecchio in list(nomi_lib_com):
    if vecchio not in comuni:
        cand = per_nome.get((nomi_lib_com[vecchio] or "").lower(), [])
        if len(cand) == 1:
            ricodificati[vecchio] = cand[0]
for diz in (lib_per_comune, regione_lib, nomi_librerie):
    for vecchio, nuovo in ricodificati.items():
        if vecchio in diz:
            v = diz.pop(vecchio)
            diz[nuovo] = (diz.get(nuovo, 0) + v) if isinstance(v, int) else v
print("codici comune ricollegati per nome:", len(ricodificati), flush=True)

# ---------------------------------------------------------------- redditi (MEF, anno d'imposta 2024)
redditi = {}
with open(f"{G}/mef_redditi_2024/Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_2024.csv", encoding="latin-1") as f:
    for r in csv.DictReader(f, delimiter=";"):
        freq = numero(r.get("Reddito complessivo - Frequenza"))
        amm = numero(r.get("Reddito complessivo - Ammontare in euro"))
        if freq and amm:
            redditi[pc(r["Codice Istat Comune"])] = {"reddito_medio": round(amm / freq),
                                                     "dichiaranti": int(numero(r.get("Numero contribuenti")) or 0),
                                                     "provincia": r.get("Sigla Provincia"), "regione": r.get("Regione")}

# ---------------------------------------------------------------- tempi (ISTAT, matrici 2021)
con_bib = set(bib_per_comune)
con_lib = set(lib_per_comune)
best_bib, best_lib = {}, {}
origini_matrice = set()
for reg in REGIONI_MATRICI:
    url = f"https://www.istat.it/storage/cartografia/matrici_distanze/{reg}.zip"
    print("matrice", reg, flush=True)
    dati = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=900).read()
    with zipfile.ZipFile(io.BytesIO(dati)) as z:
        for nome in z.namelist():
            if not nome.lower().endswith(".csv"):
                continue
            with z.open(nome) as fb:
                f = io.TextIOWrapper(fb, encoding="latin-1")
                testa = next(f).strip().split(";")
                i_o, i_d, i_t = testa.index("OR_PROCOM"), testa.index("DEST_PROCOM"), testa.index("TEP_TOT")
                for riga in f:
                    c = riga.rstrip("\n").split(";")
                    o, d = pc(c[i_o]), pc(c[i_d])
                    origini_matrice.add(o)
                    t = numero(c[i_t])
                    if t is None:
                        continue
                    if d in con_bib and t < best_bib.get(o, (1e9,))[0]:
                        best_bib[o] = (t, d)
                    if d in con_lib and t < best_lib.get(o, (1e9,))[0]:
                        best_lib[o] = (t, d)
    del dati

# ---------------------------------------------------------------- scheda per comune
righe = []
for p, c in sorted(comuni.items()):
    prov, reg = luogo.get(p, (None, None))
    red = redditi.get(p, {})
    nb, nl = len(bib_per_comune.get(p, [])), lib_per_comune.get(p, 0)

    def tempo(n, best):
        if n:
            return 0, p
        if p not in origini_matrice:
            return None, None  # comune nato dopo il 2021: non c'è nella matrice
        v = best.get(p)
        return (round(v[0]), v[1]) if v else (None, None)

    tb, db = tempo(nb, best_bib)
    tl, dl = tempo(nl, best_lib)
    righe.append({
        "pro_com": p, "comune": c["comune"], "provincia": red.get("provincia") or prov,
        "regione": regione_std(regione_lib.get(p) or red.get("regione") or reg), "abitanti_2026": c["abitanti"],
        "biblioteche_aperte": nb, "di_cui_pubblica_lettura": pubbliche_per_comune.get(p, 0), "minuti_biblioteca": tb,
        "comune_biblioteca_piu_vicina": comuni.get(db, {}).get("comune") if db else None,
        "librerie_note": nl, "minuti_libreria": tl,
        "comune_libreria_piu_vicina": comuni.get(dl, {}).get("comune") if dl else None,
        "reddito_medio_dichiarato_2024": red.get("reddito_medio"),
        "pct_0_14": round(100 * eta[p][0] / c["abitanti"], 1) if c["abitanti"] else None,
        "pct_65_piu": round(100 * eta[p][1] / c["abitanti"], 1) if c["abitanti"] else None,
        "biblioteche_nomi": " | ".join(sorted(bib_per_comune.get(p, []))),
        "librerie_nomi": " | ".join(sorted(set(nomi_librerie.get(p, [])))),
    })

campi = list(righe[0].keys())
with open(f"{OUT}/comuni.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=campi)
    w.writeheader()
    w.writerows(righe)


# ---------------------------------------------------------------- sintesi
def classi(chiave):
    fasce = [("nel proprio comune", lambda t: t == 0), ("1-15 minuti", lambda t: 0 < t <= 15),
             ("16-30 minuti", lambda t: 15 < t <= 30), ("oltre 30 minuti", lambda t: t > 30)]
    out = []
    for nome, fn in fasce:
        sel = [r for r in righe if r[chiave] is not None and fn(r[chiave])]
        out.append({"fascia": nome, "comuni": len(sel), "abitanti": sum(r["abitanti_2026"] for r in sel)})
    nd = [r for r in righe if r[chiave] is None]
    out.append({"fascia": "non calcolabile", "comuni": len(nd), "abitanti": sum(r["abitanti_2026"] for r in nd)})
    return out


registro = json.load(open(f"{G}/registro.json", encoding="utf-8"))
sintesi = {
    "calcolato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "comuni": len(righe), "abitanti": sum(r["abitanti_2026"] for r in righe),
    "biblioteche_aperte": sum(r["biblioteche_aperte"] for r in righe),
    "comuni_con_biblioteca": sum(1 for r in righe if r["biblioteche_aperte"]),
    "librerie_note": sum(r["librerie_note"] for r in righe),
    "comuni_con_libreria": sum(1 for r in righe if r["librerie_note"]),
    "distanza_biblioteca": classi("minuti_biblioteca"),
    "distanza_libreria": classi("minuti_libreria"),
    "fonti": {
        "biblioteche": {"ente": "ICCU, Anagrafe delle biblioteche italiane", "licenza": "CC0 1.0", "estrazione": estrazione_iccu},
        "abitanti": {"ente": "ISTAT, popolazione residente al 1° gennaio 2026 (stima)", "licenza": "CC BY 4.0",
                     "ultima_modifica": registro["file"]["istat_popolazione_2026"]["ultima_modifica_alla_fonte"]},
        "redditi": {"ente": "MEF, Dipartimento delle Finanze, anno d'imposta 2024", "licenza": "da verificare",
                    "ultima_modifica": registro["file"]["mef_redditi_2024"]["ultima_modifica_alla_fonte"]},
        "tempi": {"ente": "ISTAT, matrici dei tempi di percorrenza tra comuni (confini 1/1/2021)", "licenza": "CC BY 4.0",
                  "colonna": "TEP_TOT, minuti in auto con traffico"},
        "librerie": {"ente": "Overture Maps + OpenStreetMap", "licenza": "CDLA-Permissive-2.0 / Apache-2.0 / ODbL"},
    },
}
json.dump(sintesi, open(f"{OUT}/sintesi.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- confronti a parità di grandezza
# I comuni senza libri sono quasi tutti piccoli: confrontarli con le città mescola l'effetto «libro»
# con l'effetto «grandezza». Qui ogni profilo è confrontato solo con comuni della stessa fascia,
# e la media nazionale «standardizzata» ripesa ogni profilo con la stessa distribuzione per fascia.
def profilo(r):
    b, l = r["biblioteche_aperte"] > 0, r["librerie_note"] > 0
    return "Libreria e biblioteca" if b and l else "Solo biblioteca" if b else "Solo libreria" if l else "Nessuna delle due"


FASCE = [("meno di 1.000", 0, 1000), ("1.000-2.999", 1000, 3000), ("3.000-9.999", 3000, 10000),
         ("10.000-49.999", 10000, 50000), ("50.000 e più", 50000, 10**9)]
fascia = lambda a: next(n for n, lo, hi in FASCE if lo <= a < hi)
celle = defaultdict(lambda: {"comuni": 0, "abitanti": 0, "red_x_ab": 0, "ab_red": 0, "giovani": 0, "anziani": 0})
for r in righe:
    k = (fascia(r["abitanti_2026"]), profilo(r))
    c, a = celle[k], r["abitanti_2026"]
    c["comuni"] += 1; c["abitanti"] += a
    c["giovani"] += eta[r["pro_com"]][0]; c["anziani"] += eta[r["pro_com"]][1]
    if r["reddito_medio_dichiarato_2024"]:
        c["red_x_ab"] += r["reddito_medio_dichiarato_2024"] * a; c["ab_red"] += a
tabella = []
for (f, p), c in celle.items():
    tabella.append({"fascia": f, "profilo": p, "comuni": c["comuni"], "abitanti": c["abitanti"],
                    "reddito_medio": round(c["red_x_ab"] / c["ab_red"]) if c["ab_red"] else None,
                    "pct_0_14": round(100 * c["giovani"] / c["abitanti"], 1) if c["abitanti"] else None,
                    "pct_65_piu": round(100 * c["anziani"] / c["abitanti"], 1) if c["abitanti"] else None,
                    "affidabile": c["comuni"] >= 30})
peso = defaultdict(int)
for r in righe:
    peso[fascia(r["abitanti_2026"])] += r["abitanti_2026"]
tot = sum(peso.values())
standard = {}
for p in ["Libreria e biblioteca", "Solo biblioteca", "Solo libreria", "Nessuna delle due"]:
    num = den = 0
    for f, _, _ in FASCE:
        c = celle.get((f, p))
        if c and c["ab_red"] and c["comuni"] >= 30:
            num += peso[f] * c["red_x_ab"] / c["ab_red"]; den += peso[f]
    standard[p] = round(num / den) if den else None
json.dump({"nota": "Celle con meno di 30 comuni marcate come non affidabili e escluse dalla media standardizzata.",
           "fasce": [n for n, _, _ in FASCE], "tabella": tabella,
           "reddito_standardizzato_per_grandezza": standard},
          open(f"{OUT}/confronti.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(json.dumps(sintesi, indent=2, ensure_ascii=False))
