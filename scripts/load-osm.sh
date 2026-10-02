#!/usr/bin/env bash
# =============================================================================
#  Ingestion des donnees OpenStreetMap du Cameroun dans PostGIS
#  Lance par : docker compose run --rm loader
#
#  Etapes : 1) telecharge l'extrait Geofabrik Cameroun (avec cache)
#           2) importe dans PostGIS avec osm2pgsql
#           3) (re)cree les vues publiees du schema "catalog"
# =============================================================================
set -euo pipefail

PBF_FILE="/data/cameroon-latest.osm.pbf"
export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "==> [1/3] Telechargement de l'extrait OSM Cameroun"
if [ -f "$PBF_FILE" ]; then
  echo "    Fichier deja present dans le cache : $PBF_FILE"
  echo "    (supprime-le pour forcer un nouveau telechargement)"
else
  curl -fSL "$GEOFABRIK_URL" -o "$PBF_FILE"
fi
echo "    Taille : $(du -h "$PBF_FILE" | cut -f1)"

echo "==> [2/3] Import dans PostGIS avec osm2pgsql (peut prendre quelques minutes)"
osm2pgsql \
  --create \
  --slim \
  --hstore \
  --cache 512 \
  --database "$POSTGRES_DB" \
  --username "$POSTGRES_USER" \
  --host "$PGHOST" \
  --port 5432 \
  "$PBF_FILE"

echo "==> [3/3] Creation des couches publiees (schema catalog)"
psql --host "$PGHOST" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     --set ON_ERROR_STOP=on --file /sql/02_views.sql

echo ""
echo "============================================================"
echo " Import termine avec succes."
echo " DERNIERE ETAPE : redemarre l'API pour qu'elle voie les"
echo " nouvelles couches :   docker compose restart api"
echo "============================================================"
