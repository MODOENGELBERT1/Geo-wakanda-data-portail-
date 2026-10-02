#!/usr/bin/env bash
# =============================================================================
#  Ingestion d'une orthophoto dans le noeud
#  Usage : docker compose run --rm ortho /data/in/mon_vol.tif "Nom lisible du vol"
#
#  Etapes : 1) verifie le catalogue raster (le cree si besoin)
#           2) convertit le GeoTIFF en COG (Cloud Optimized GeoTIFF)
#           3) envoie le COG dans MinIO (stockage objet)
#           4) enregistre l'emprise + metadonnees dans PostGIS
# =============================================================================
set -euo pipefail

INPUT="${1:-}"
NAME="${2:-Orthophoto sans nom}"

if [ -z "$INPUT" ] || [ ! -f "$INPUT" ]; then
  echo "ERREUR : fichier introuvable."
  echo "Usage : docker compose run --rm ortho /data/in/mon_vol.tif \"Nom du vol\""
  echo "  (depose tes GeoTIFF dans le dossier ./ortho_in de ton PC)"
  exit 1
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"
BUCKET="${MINIO_BUCKET:-orthophotos}"
BASE="$(basename "${INPUT%.*}" | tr ' ' '_' | tr -cd 'A-Za-z0-9_-')"
STAMP="$(date +%Y%m%d%H%M%S)"
KEY="${BASE}_${STAMP}.tif"
COG="/data/tmp/${KEY}"
S3PATH="s3://${BUCKET}/${KEY}"

echo "==> [1/4] Verification du catalogue raster"
psql --host "$PGHOST" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     --set ON_ERROR_STOP=on --file /sql/03_raster_catalog.sql >/dev/null
echo "    Catalogue pret."

echo "==> [2/4] Conversion en COG (peut prendre un moment)"
gdal_translate "$INPUT" "$COG" \
  -of COG \
  -co COMPRESS=DEFLATE \
  -co BLOCKSIZE=512 \
  -co NUM_THREADS=ALL_CPUS
echo "    COG cree : $(du -h "$COG" | cut -f1)"

echo "==> [3/4] Envoi dans MinIO"
mc alias set cgn "$MINIO_ENDPOINT" "$MINIO_USER" "$MINIO_PASSWORD" >/dev/null
mc mb --ignore-existing "cgn/${BUCKET}" >/dev/null
mc cp "$COG" "cgn/${BUCKET}/${KEY}"
echo "    Stocke : $S3PATH"

echo "==> [4/4] Enregistrement de l'emprise dans PostGIS"
# gdalinfo -json fournit l'emprise en WGS84 (champ wgs84Extent, un polygone GeoJSON)
FOOTPRINT="$(gdalinfo -json "$COG" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(json.dumps(d["wgs84Extent"]))')"

psql --host "$PGHOST" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=on <<SQL
INSERT INTO restricted.orthophotos (nom, s3_path, date_ajout, emprise)
VALUES (
  \$\$${NAME}\$\$,
  \$\$${S3PATH}\$\$,
  now(),
  ST_SetSRID(ST_GeomFromGeoJSON(\$\$${FOOTPRINT}\$\$), 4326)
);
SQL

# Nettoyage du COG temporaire (l'original reste dans MinIO)
rm -f "$COG"

echo ""
echo "============================================================"
echo " Orthophoto ajoutee : $NAME"
echo " Elle apparait dans la couche 'Couverture orthophotos' de"
echo " la plateforme. Recharge http://localhost:8080"
echo "============================================================"
