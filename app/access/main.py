"""
=============================================================================
 Noeud national de donnees geospatiales - Cameroun
 Service d'acces : comptes, demandes de telechargement, validation admin.

 Principe :
  - Les donnees OUVERTES (schema catalog) se telechargent librement via TiPg.
  - Les donnees RESTREINTES (schema restricted : vecteur institutionnel + raster)
    ne se telechargent qu'apres une DEMANDE approuvee par un admin.
  - A l'approbation, un lien de telechargement TEMPORAIRE (jeton signe) est genere.
=============================================================================
"""
import os
import time
import shutil
import zipfile
import tempfile
import subprocess
import datetime as dt
from urllib.parse import urlparse

import bcrypt
import jwt
import psycopg
from psycopg import sql
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from minio import Minio

# --- Configuration (via variables d'environnement) ---------------------------
DATABASE_URL   = os.environ["DATABASE_URL"]
JWT_SECRET     = os.environ.get("JWT_SECRET", "change_me_jwt_secret")
ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@geowakanda.cm").lower()
MINIO_ENDPOINT = os.environ.get("MINIO_PUBLIC_ENDPOINT", "localhost:9000")  # vu par le NAVIGATEUR
MINIO_USER     = os.environ.get("MINIO_USER", "cgnadmin")
MINIO_PASSWORD = os.environ.get("MINIO_PASSWORD", "change_me_minio")
MINIO_SECURE   = os.environ.get("MINIO_SECURE", "false").lower() == "true"

AUTH_TTL     = 7 * 24 * 3600        # jeton de session : 7 jours
DOWNLOAD_TTL = 24 * 3600            # lien de telechargement : 24 h

app = FastAPI(title="GeoWakanda - Service d'acces")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def db():
    return psycopg.connect(DATABASE_URL)


# --- Initialisation du schema applicatif (idempotent) ------------------------
@app.on_event("startup")
def init_schema():
    with db() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS app;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app.users (
                id         bigserial PRIMARY KEY,
                email      text UNIQUE NOT NULL,
                pwd_hash   text NOT NULL,
                role       text NOT NULL DEFAULT 'user',
                created_at timestamptz DEFAULT now()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app.access_requests (
                id           bigserial PRIMARY KEY,
                user_id      bigint REFERENCES app.users(id),
                dataset_kind text NOT NULL,          -- 'vecteur' | 'raster'
                dataset_ref  text NOT NULL,          -- nom de table OU id d'ortho
                dataset_nom  text,
                reason       text,
                status       text NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
                created_at   timestamptz DEFAULT now(),
                decided_at   timestamptz,
                decided_by   text
            );
        """)
        # Catalogue structure des donnees institutionnelles (idempotent : marche
        # aussi sur une base deja existante, sans reimport).
        cur.execute("CREATE SCHEMA IF NOT EXISTS restricted;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS restricted.catalogue_institutionnel (
                id                   bigserial PRIMARY KEY,
                nom_jeu              text NOT NULL,
                nom_institut_source  text,
                theme                text,
                date_collecte        date,
                format_import        text,
                personne_organisme   text,
                niveau_acces         text DEFAULT 'institutionnel',
                table_ref            text,
                date_ajout           timestamptz DEFAULT now()
            );
        """)
        conn.commit()


# --- Securite ----------------------------------------------------------------
def make_token(payload: dict, ttl: int) -> str:
    data = {**payload, "exp": int(time.time()) + ttl}
    return jwt.encode(data, JWT_SECRET, algorithm="HS256")


def read_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Jeton invalide ou expire")


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentification requise")
    claims = read_token(authorization[7:])
    return {"id": claims.get("uid"), "email": claims.get("email"), "role": claims.get("role")}


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Reserve a l'administrateur")
    return user


# --- Modeles d'entree --------------------------------------------------------
class Credentials(BaseModel):
    email: str
    password: str

class NewRequest(BaseModel):
    dataset_kind: str
    dataset_ref: str
    reason: str = ""

class Decision(BaseModel):
    decision: str   # 'approve' | 'reject'


# --- Authentification --------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}

# --- Metadonnees & fraicheur des donnees (public) ----------------------------
# Permet a la plateforme ET a Urban Sanity de connaitre la date de derniere
# synchro OSM (diffs) et la liste des jeux disponibles (vecteur / raster).
@app.get("/meta")
def meta():
    out = {"osm": {}, "collections": []}
    with db() as conn, conn.cursor() as cur:
        # Fraicheur OSM : osm2pgsql enregistre les horodatages dans cette table
        try:
            cur.execute("SELECT property, value FROM public.osm2pgsql_properties")
            props = {k: v for (k, v) in cur.fetchall()}
            out["osm"] = {
                "import_timestamp": props.get("import_timestamp"),
                "replication_timestamp": props.get("replication_timestamp"),
                "replication_base_url": props.get("replication_base_url"),
            }
        except Exception:
            conn.rollback()
        # Jeux ouverts (schema catalog) + nature
        try:
            cur.execute("""SELECT table_name FROM information_schema.tables
                           WHERE table_schema='catalog' ORDER BY table_name""")
            for (t,) in cur.fetchall():
                kind = "raster-couverture" if t == "orthophotos_couverture" else "vecteur"
                out["collections"].append({"id": "catalog." + t, "kind": kind})
        except Exception:
            conn.rollback()
        # Nombre d'orthophotos (raster)
        try:
            cur.execute("SELECT count(*) FROM restricted.orthophotos")
            out["orthophotos"] = cur.fetchone()[0]
        except Exception:
            conn.rollback()
    return out

@app.post("/auth/register")
def register(c: Credentials):
    email = c.email.strip().lower()
    if not email or not c.password:
        raise HTTPException(400, "Email et mot de passe requis")
    role = "admin" if email == ADMIN_EMAIL else "user"
    pwd_hash = bcrypt.hashpw(c.password.encode(), bcrypt.gensalt()).decode()
    with db() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO app.users (email, pwd_hash, role) VALUES (%s,%s,%s) RETURNING id",
                (email, pwd_hash, role),
            )
            uid = cur.fetchone()[0]
            conn.commit()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "Ce compte existe deja")
    token = make_token({"uid": uid, "email": email, "role": role}, AUTH_TTL)
    return {"access_token": token, "email": email, "role": role}

@app.post("/auth/login")
def login(c: Credentials):
    email = c.email.strip().lower()
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, pwd_hash, role FROM app.users WHERE email=%s", (email,))
        row = cur.fetchone()
    if not row or not bcrypt.checkpw(c.password.encode(), row[1].encode()):
        raise HTTPException(401, "Identifiants incorrects")
    token = make_token({"uid": row[0], "email": email, "role": row[2]}, AUTH_TTL)
    return {"access_token": token, "email": email, "role": row[2]}

@app.get("/me")
def me(user: dict = Depends(current_user)):
    return user


# --- Catalogue des jeux restreints ------------------------------------------
@app.get("/datasets")
def datasets(user: dict = Depends(current_user)):
    out = []
    with db() as conn, conn.cursor() as cur:
        # Jeux institutionnels depuis le catalogue structure (metadonnees completes)
        try:
            cur.execute("""
                SELECT nom_jeu, nom_institut_source, theme, date_collecte,
                       format_import, personne_organisme, niveau_acces, table_ref
                FROM restricted.catalogue_institutionnel ORDER BY date_ajout DESC
            """)
            for (nom, inst, theme, dc, fmt, contact, niv, ref) in cur.fetchall():
                out.append({
                    "kind": "vecteur", "ref": ref or "", "nom": nom,
                    "institut": inst, "theme": theme,
                    "date_collecte": str(dc) if dc else None,
                    "format": fmt, "contact": contact, "niveau": niv,
                })
        except Exception:
            conn.rollback()
        # Orthophotos (raster)
        try:
            cur.execute("SELECT id, nom, date_vol, resolution_cm, niveau_acces FROM restricted.orthophotos ORDER BY id")
            for (oid, nom, dv, res, niv) in cur.fetchall():
                out.append({
                    "kind": "raster", "ref": str(oid), "nom": nom,
                    "date_collecte": str(dv) if dv else None,
                    "resolution_cm": float(res) if res is not None else None,
                    "niveau": niv,
                })
        except Exception:
            conn.rollback()
    return out


# --- Demandes ----------------------------------------------------------------
@app.post("/requests")
def create_request(r: NewRequest, user: dict = Depends(current_user)):
    if r.dataset_kind not in ("vecteur", "raster"):
        raise HTTPException(400, "Type de jeu invalide")
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO app.access_requests (user_id, dataset_kind, dataset_ref, reason, dataset_nom)
               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (user["id"], r.dataset_kind, r.dataset_ref, r.reason, r.dataset_ref),
        )
        rid = cur.fetchone()[0]
        conn.commit()
    return {"id": rid, "status": "pending"}

@app.get("/requests/mine")
def my_requests(user: dict = Depends(current_user)):
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, dataset_kind, dataset_ref, dataset_nom, reason, status, created_at
               FROM app.access_requests WHERE user_id=%s ORDER BY created_at DESC""",
            (user["id"],),
        )
        rows = cur.fetchall()
    out = []
    for (rid, kind, ref, nom, reason, status, created) in rows:
        item = {"id": rid, "kind": kind, "ref": ref, "nom": nom,
                "reason": reason, "status": status, "created_at": str(created)}
        if status == "approved":
            dl = make_token({"rid": rid, "kind": kind, "ref": ref}, DOWNLOAD_TTL)
            item["download_url"] = f"/download/{dl}"
        out.append(item)
    return out


# --- Validation (admin) ------------------------------------------------------
@app.get("/admin/requests")
def admin_list(status: str = "pending", admin: dict = Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT r.id, u.email, r.dataset_kind, r.dataset_ref, r.dataset_nom,
                      r.reason, r.status, r.created_at
               FROM app.access_requests r JOIN app.users u ON u.id = r.user_id
               WHERE (%s = 'all' OR r.status = %s) ORDER BY r.created_at DESC""",
            (status, status),
        )
        rows = cur.fetchall()
    return [{"id": a, "email": b, "kind": c, "ref": d, "nom": e,
             "reason": f, "status": g, "created_at": str(h)} for (a,b,c,d,e,f,g,h) in rows]

@app.post("/admin/requests/{rid}/decision")
def admin_decide(rid: int, d: Decision, admin: dict = Depends(require_admin)):
    status = "approved" if d.decision == "approve" else "rejected"
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE app.access_requests SET status=%s, decided_at=now(), decided_by=%s WHERE id=%s",
            (status, admin["email"], rid),
        )
        conn.commit()
    return {"id": rid, "status": status}


# --- Telechargement (jeton temporaire) --------------------------------------
@app.get("/download/{token}")
def download(token: str):
    claims = read_token(token)
    rid, kind, ref = claims.get("rid"), claims.get("kind"), claims.get("ref")
    # verifier que la demande est toujours approuvee
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM app.access_requests WHERE id=%s", (rid,))
        row = cur.fetchone()
    if not row or row[0] != "approved":
        raise HTTPException(403, "Demande non approuvee")

    if kind == "raster":
        return _download_raster(ref)
    return _download_vecteur(ref)


def _download_vecteur(table: str):
    with db() as conn, conn.cursor() as cur:
        # anti-injection : la table doit exister dans le schema restricted
        cur.execute("""SELECT 1 FROM information_schema.tables
                       WHERE table_schema='restricted' AND table_name=%s""", (table,))
        if not cur.fetchone():
            raise HTTPException(404, "Jeu introuvable")
        q = sql.SQL("""
            SELECT json_build_object(
              'type','FeatureCollection',
              'features', COALESCE(json_agg(ST_AsGeoJSON(t.*)::json), '[]'::json)
            ) FROM {}.{} t
        """).format(sql.Identifier("restricted"), sql.Identifier(table))
        cur.execute(q)
        geojson = cur.fetchone()[0]
    import json
    body = json.dumps(geojson).encode()
    return Response(
        content=body, media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{table}.geojson"'},
    )


# --- Export multi-format des donnees OUVERTES (public, schema catalog) --------
# GeoJSON et CSV sont deja servis directement par TiPg ; ici on ajoute les
# formats SIG classiques (GeoPackage, KML, Shapefile) via ogr2ogr.
EXPORT_FORMATS = {
    "gpkg": ("GPKG",            "gpkg", "application/geopackage+sqlite3"),
    "kml":  ("KML",             "kml",  "application/vnd.google-earth.kml+xml"),
    "shp":  ("ESRI Shapefile",  "shp",  "application/zip"),
}

@app.get("/export/{layer}")
def export_open(layer: str, fmt: str = "gpkg"):
    fmt = fmt.lower()
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(400, "Format non supporte (gpkg, kml, shp)")
    # Securite : uniquement les couches OUVERTES (schema catalog)
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT 1 FROM information_schema.tables
                       WHERE table_schema='catalog' AND table_name=%s""", (layer,))
        if not cur.fetchone():
            raise HTTPException(404, "Couche ouverte introuvable")

    driver, ext, media = EXPORT_FORMATS[fmt]
    u = urlparse(DATABASE_URL)
    pg = (f"host={u.hostname} port={u.port or 5432} dbname={u.path.lstrip('/')} "
          f"user={u.username} password={u.password}")
    tmp = tempfile.mkdtemp(prefix="exp_")
    src = f"catalog.{layer}"
    try:
        if fmt == "shp":
            outdir = os.path.join(tmp, layer); os.makedirs(outdir, exist_ok=True)
            subprocess.run(["ogr2ogr", "-f", driver, os.path.join(outdir, layer + ".shp"),
                            "PG:" + pg, src], check=True)
            path = os.path.join(tmp, layer + ".zip")
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for f in os.listdir(outdir):
                    z.write(os.path.join(outdir, f), f)
            fname = layer + ".zip"
        else:
            path = os.path.join(tmp, f"{layer}.{ext}")
            subprocess.run(["ogr2ogr", "-f", driver, path, "PG:" + pg, src], check=True)
            fname = f"{layer}.{ext}"
    except subprocess.CalledProcessError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(500, "Echec de la conversion")
    return FileResponse(path, media_type=media, filename=fname,
                        background=BackgroundTask(shutil.rmtree, tmp, True))


# --- Export d'une ZONE : donnees OSM ouvertes decoupees a une emprise ----------
# Deux facons de definir l'emprise :
#   * /export/aoi  : un rectangle dessine sur la carte (bbox, decoupe rapide -spat)
#   * /export/clip : un contour GeoJSON importe (decoupe EXACTE au polygone -clipsrc)
# Les deux exportent les couches OUVERTES (schema catalog) dans le format choisi.
AOI_DEFAULT_LAYERS = ["batiments", "routes", "cours_eau", "limites_admin",
                      "lieux", "points_interet", "usage_sol"]
AOI_EXCLUDE = {"orthophotos_couverture", "pays"}


def _resolve_layers(layers: str):
    """Couches ouvertes reellement presentes, filtrees sur la demande."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT table_name FROM information_schema.tables
                       WHERE table_schema='catalog'""")
        present = {t for (t,) in cur.fetchall()}
    wanted = [l.strip() for l in layers.split(",") if l.strip()] or AOI_DEFAULT_LAYERS
    sel = [l for l in wanted if l in present and l not in AOI_EXCLUDE]
    if not sel:
        raise HTTPException(404, "Aucune couche ouverte a exporter dans cette zone")
    return sel


def _pg_conn_str():
    u = urlparse(DATABASE_URL)
    return (f"host={u.hostname} port={u.port or 5432} dbname={u.path.lstrip('/')} "
            f"user={u.username} password={u.password}")


def _run_export(sel, clip_args, fmt, tmp):
    """Lance ogr2ogr pour chaque couche avec l'argument de decoupe (clip_args),
    assemble le fichier de sortie et renvoie la reponse HTTP."""
    pg = _pg_conn_str()
    if fmt == "gpkg":
        out = os.path.join(tmp, "zone_osm.gpkg")
        for i, lyr in enumerate(sel):
            cmd = ["ogr2ogr"] + (["-update", "-append"] if i else []) + \
                  ["-f", "GPKG", out, "PG:" + pg, f"catalog.{lyr}", "-nln", lyr] + clip_args
            subprocess.run(cmd, check=True)
        return FileResponse(out, media_type="application/geopackage+sqlite3",
                            filename="zone_osm.gpkg",
                            background=BackgroundTask(shutil.rmtree, tmp, True))

    outdir = os.path.join(tmp, "zone_osm"); os.makedirs(outdir, exist_ok=True)
    driver, ext = ("ESRI Shapefile", "shp") if fmt == "shp" else ("GeoJSON", "geojson")
    for lyr in sel:
        subprocess.run(["ogr2ogr", "-f", driver,
                        os.path.join(outdir, f"{lyr}.{ext}"),
                        "PG:" + pg, f"catalog.{lyr}"] + clip_args, check=True)
    path = os.path.join(tmp, "zone_osm.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(outdir):
            z.write(os.path.join(outdir, f), f)
    return FileResponse(path, media_type="application/zip",
                        filename=f"zone_osm_{ext}.zip",
                        background=BackgroundTask(shutil.rmtree, tmp, True))


@app.get("/export/aoi")
def export_aoi(bbox: str, fmt: str = "gpkg", layers: str = ""):
    fmt = fmt.lower()
    if fmt not in ("gpkg", "shp", "geojson"):
        raise HTTPException(400, "Format non supporte (gpkg, shp, geojson)")
    try:
        xmin, ymin, xmax, ymax = [float(v) for v in bbox.split(",")]
    except Exception:
        raise HTTPException(400, "bbox invalide (attendu xmin,ymin,xmax,ymax)")
    if not (xmin < xmax and ymin < ymax):
        raise HTTPException(400, "bbox invalide (xmin<xmax et ymin<ymax)")
    sel = _resolve_layers(layers)
    clip = ["-spat", str(xmin), str(ymin), str(xmax), str(ymax)]
    tmp = tempfile.mkdtemp(prefix="aoi_")
    try:
        return _run_export(sel, clip, fmt, tmp)
    except subprocess.CalledProcessError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(500, "Echec de l'export de la zone")


class ClipReq(BaseModel):
    geojson: dict           # geometrie, Feature ou FeatureCollection (EPSG:4326)
    fmt: str = "gpkg"
    layers: str = ""

@app.post("/export/clip")
def export_clip(req: ClipReq):
    """Decoupe EXACTE des couches ouvertes sur un contour GeoJSON importe."""
    import json as _json
    fmt = req.fmt.lower()
    if fmt not in ("gpkg", "shp", "geojson"):
        raise HTTPException(400, "Format non supporte (gpkg, shp, geojson)")
    gj = req.geojson or {}
    t = gj.get("type")
    if t == "FeatureCollection":
        fc = gj
    elif t == "Feature":
        fc = {"type": "FeatureCollection", "features": [gj]}
    elif t in ("Polygon", "MultiPolygon"):
        fc = {"type": "FeatureCollection",
              "features": [{"type": "Feature", "properties": {}, "geometry": gj}]}
    else:
        raise HTTPException(400, "GeoJSON invalide")
    types = [((f or {}).get("geometry") or {}).get("type") for f in fc.get("features", [])]
    if not any(x in ("Polygon", "MultiPolygon") for x in types):
        raise HTTPException(400, "Le contour doit contenir un polygone")

    sel = _resolve_layers(req.layers)
    tmp = tempfile.mkdtemp(prefix="clip_")
    clip_file = os.path.join(tmp, "clip.geojson")
    with open(clip_file, "w") as fh:
        _json.dump(fc, fh)
    clip = ["-clipsrc", clip_file]
    try:
        return _run_export(sel, clip, fmt, tmp)
    except subprocess.CalledProcessError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(500, "Echec du decoupage sur le contour")


def _download_raster(ortho_id: str):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT s3_path FROM restricted.orthophotos WHERE id=%s", (ortho_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Orthophoto introuvable")
    # s3://bucket/key -> bucket, key
    parsed = urlparse(row[0])
    bucket, key = parsed.netloc, parsed.path.lstrip("/")
    client = Minio(MINIO_ENDPOINT, access_key=MINIO_USER,
                   secret_key=MINIO_PASSWORD, secure=MINIO_SECURE)
    url = client.presigned_get_object(bucket, key, expires=dt.timedelta(seconds=DOWNLOAD_TTL))
    return RedirectResponse(url)
