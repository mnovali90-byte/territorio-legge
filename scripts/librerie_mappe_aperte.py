"""
Il territorio legge — estrazione delle librerie dalle mappe aperte.

Fonti:
  - Overture Maps, tema Places (licenze CDLA-Permissive-2.0 / Apache-2.0 / CC0 per fonte)
  - OpenStreetMap, shop=books via Overpass API (licenza ODbL)
  - ISTAT, confini comunali generalizzati (CC BY 4.0) per assegnare ogni punto a un comune

Uscite in data/librerie/:
  - fonti.json                 versione dei dati, date di estrazione, licenze
  - overture_schema.txt        struttura del file Overture (per controllo)
  - overture_candidati.csv     tutti i luoghi candidati, con il motivo per cui sono stati presi
  - overture_categorie.csv     conteggio delle categorie trovate (per decidere i filtri)
  - osm_librerie.csv           punti shop=books da OpenStreetMap
  - riepilogo_regioni.csv      conteggi per regione e fonte
Nessun numero viene scritto a mano: tutto viene da qui.
"""

import csv
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

import duckdb

OUT = "data/librerie"
os.makedirs(OUT, exist_ok=True)
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
BBOX = dict(xmin=6.6, xmax=18.6, ymin=35.4, ymax=47.1)  # rettangolo che contiene l'Italia
fonti = {"estrazione": NOW, "fonti": {}}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- Overture
def ultima_release_overture():
    out = subprocess.run(
        ["aws", "s3", "ls", "--no-sign-request", "s3://overturemaps-us-west-2/release/"],
        capture_output=True, text=True, check=True,
    ).stdout
    rel = sorted(l.split("PRE")[-1].strip().strip("/") for l in out.splitlines() if "PRE" in l)
    return rel[-1]


con = duckdb.connect()
for ext in ("httpfs", "spatial"):
    con.execute(f"INSTALL {ext}; LOAD {ext};")
con.execute("SET s3_region='us-west-2';")

release = ultima_release_overture()
log(f"Overture release: {release}")
src = f"s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"

con.execute(f"""
CREATE TABLE ov AS
SELECT * FROM read_parquet('{src}', hive_partitioning=1)
WHERE bbox.xmin BETWEEN {BBOX['xmin']} AND {BBOX['xmax']}
  AND bbox.ymin BETWEEN {BBOX['ymin']} AND {BBOX['ymax']}
""")
log(f"Luoghi Overture nel rettangolo Italia: {con.execute('SELECT count(*) FROM ov').fetchone()[0]}")

schema = con.execute("DESCRIBE ov").fetchall()
cols = {r[0] for r in schema}
with open(f"{OUT}/overture_schema.txt", "w") as f:
    for r in schema:
        f.write(f"{r[0]}\t{r[1]}\n")

cat_expr = "basic_category" if "basic_category" in cols else "categories.primary"
tax_expr = "CAST(taxonomy AS VARCHAR)" if "taxonomy" in cols else "NULL"
status_expr = "operating_status" if "operating_status" in cols else "NULL"

con.execute(f"""
CREATE TABLE cand AS
SELECT
  id,
  names.primary AS nome,
  {cat_expr} AS categoria,
  {tax_expr} AS tassonomia,
  confidence AS affidabilita,
  {status_expr} AS stato,
  ST_X(geometry) AS lon, ST_Y(geometry) AS lat,
  addresses[1].freeform AS indirizzo,
  addresses[1].locality AS localita,
  addresses[1].region AS regione_indirizzo,
  addresses[1].country AS paese,
  array_to_string(list_transform(sources, s -> s.dataset), '|') AS fonti_dato,
  array_to_string(list_transform(sources, s -> s.license), '|') AS licenze,
  CASE
    WHEN lower(coalesce({cat_expr}, '')) LIKE '%book%' THEN 'categoria'
    WHEN lower(coalesce({tax_expr}, '')) LIKE '%book%' THEN 'tassonomia'
    ELSE 'nome'
  END AS motivo
FROM ov
WHERE (addresses[1].country = 'IT' OR addresses[1].country IS NULL)
  AND (
    lower(coalesce({cat_expr}, '')) LIKE '%book%'
    OR lower(coalesce({tax_expr}, '')) LIKE '%book%'
    OR lower(coalesce(names.primary, '')) LIKE '%librer%'
  )
""")

# ---------------------------------------------------------------- confini ISTAT
comuni_ok = False
for anno in (2026, 2025):
    url = (f"https://www.istat.it/storage/cartografia/confini_amministrativi/"
           f"generalizzati/{anno}/Limiti0101{anno}_g.zip")
    try:
        log(f"Scarico confini ISTAT {anno}")
        urllib.request.urlretrieve(url, "/tmp/confini.zip")
        zipfile.ZipFile("/tmp/confini.zip").extractall("/tmp/confini")
        shp_com = shp_reg = None
        for root, _, files in os.walk("/tmp/confini"):
            for fn in files:
                if fn.endswith(".shp") and fn.startswith("Com"):
                    shp_com = os.path.join(root, fn)
                if fn.endswith(".shp") and fn.startswith("Reg"):
                    shp_reg = os.path.join(root, fn)
        # ISTAT pubblica in UTM32N (EPSG:32632): riportiamo in coordinate geografiche
        con.execute(f"""
        CREATE TABLE comuni AS
        SELECT PRO_COM_T AS pro_com, COMUNE AS comune, COD_REG AS cod_reg,
               ST_Transform(geom, 'EPSG:32632', 'EPSG:4326', always_xy := true) AS g
        FROM ST_Read('{shp_com}')
        """)
        con.execute(f"""
        CREATE TABLE regioni AS
        SELECT COD_REG AS cod_reg, DEN_REG AS regione FROM ST_Read('{shp_reg}')
        """)
        fonti["fonti"]["istat_confini"] = {"anno": anno, "url": url, "licenza": "CC BY 4.0"}
        comuni_ok = True
        break
    except Exception as e:  # noqa: BLE001
        log(f"Confini {anno} non disponibili: {e}")


def assegna_comune(tabella):
    if not comuni_ok:
        return tabella
    con.execute(f"""
    CREATE OR REPLACE TABLE {tabella}_c AS
    SELECT t.*, c.pro_com, c.comune, r.regione
    FROM {tabella} t
    LEFT JOIN comuni c ON ST_Contains(c.g, ST_Point(t.lon, t.lat))
    LEFT JOIN regioni r ON r.cod_reg = c.cod_reg
    """)
    return f"{tabella}_c"


cand = assegna_comune("cand")
if comuni_ok:
    con.execute(f"DELETE FROM {cand} WHERE pro_com IS NULL")  # fuori dall'Italia

con.execute(f"COPY (SELECT * FROM {cand} ORDER BY regione, comune, nome) TO '{OUT}/overture_candidati.csv' (HEADER)")
con.execute(f"""
COPY (SELECT motivo, categoria, count(*) AS luoghi,
             count(*) FILTER (WHERE affidabilita >= 0.7) AS affidabili
      FROM {cand} GROUP BY ALL ORDER BY luoghi DESC)
TO '{OUT}/overture_categorie.csv' (HEADER)
""")
fonti["fonti"]["overture_places"] = {
    "release": release, "url": src,
    "licenze": "per luogo, vedi colonna 'licenze' (CDLA-Permissive-2.0, Apache-2.0, CC0-1.0)",
    "attribuzione": "© Overture Maps Foundation",
}
log(f"Candidati Overture: {con.execute(f'SELECT count(*) FROM {cand}').fetchone()[0]}")

# ---------------------------------------------------------------- OpenStreetMap
query = """
[out:json][timeout:300];
area["ISO3166-1"="IT"][admin_level=2]->.it;
(node["shop"="books"](area.it); way["shop"="books"](area.it); relation["shop"="books"](area.it););
out center tags;
"""
osm_ok = False
for endpoint in ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter"):
    try:
        log(f"Interrogo OpenStreetMap: {endpoint}")
        req = urllib.request.Request(endpoint, data=("data=" + query).encode(),
                                     headers={"User-Agent": "territorio-legge/0.1"})
        data = json.load(urllib.request.urlopen(req, timeout=400))
        rows = []
        for el in data["elements"]:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            t = el.get("tags", {})
            rows.append([f"{el['type']}/{el['id']}", t.get("name"), t.get("brand"),
                         t.get("second_hand"), lon, lat])
        with open("/tmp/osm.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "nome", "marchio", "usato", "lon", "lat"])
            w.writerows(rows)
        con.execute("CREATE TABLE osm AS SELECT * FROM read_csv_auto('/tmp/osm.csv')")
        osm_ok = True
        fonti["fonti"]["openstreetmap"] = {
            "endpoint": endpoint, "filtro": "shop=books",
            "data_dati": data.get("osm3s", {}).get("timestamp_osm_base"),
            "licenza": "ODbL 1.0", "attribuzione": "© OpenStreetMap contributors",
        }
        break
    except Exception as e:  # noqa: BLE001
        log(f"OpenStreetMap non raggiungibile su {endpoint}: {e}")

if osm_ok:
    osm = assegna_comune("osm")
    con.execute(f"COPY (SELECT * FROM {osm} ORDER BY regione, comune, nome) TO '{OUT}/osm_librerie.csv' (HEADER)")
    log(f"Librerie OSM: {con.execute(f'SELECT count(*) FROM {osm}').fetchone()[0]}")

# ---------------------------------------------------------------- riepilogo
if comuni_ok:
    parti = [f"""SELECT regione, 'overture_categoria_book' AS fonte, count(*) AS n FROM {cand}
                 WHERE motivo IN ('categoria','tassonomia') GROUP BY regione""",
             f"""SELECT regione, 'overture_categoria_book_affidabili' AS fonte, count(*) FROM {cand}
                 WHERE motivo IN ('categoria','tassonomia') AND affidabilita >= 0.7 GROUP BY regione""",
             f"""SELECT regione, 'overture_solo_nome_libreria' AS fonte, count(*) FROM {cand}
                 WHERE motivo = 'nome' GROUP BY regione"""]
    if osm_ok:
        parti.append(f"SELECT regione, 'osm_shop_books' AS fonte, count(*) FROM {osm} GROUP BY regione")
    con.execute(f"""
    COPY (PIVOT ({' UNION ALL '.join(parti)}) ON fonte USING sum(n) GROUP BY regione ORDER BY regione)
    TO '{OUT}/riepilogo_regioni.csv' (HEADER)
    """)

with open(f"{OUT}/fonti.json", "w") as f:
    json.dump(fonti, f, indent=2, ensure_ascii=False)
log("Fatto.")
sys.exit(0)
