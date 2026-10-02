#!/usr/bin/env bash
# =============================================================================
#  Mise a jour OSM par differentiels (quasi-temps-reel)
#  Applique les changements OSM survenus depuis le dernier import/MAJ.
#
#  A lancer manuellement :  docker compose run --rm sync
#  Ou automatiquement via une tache planifiee (voir README : "Synchro planifiee").
#
#  Pre-requis : l'import initial (loader) a ete fait en mode --slim (c'est le cas).
# =============================================================================
set -euo pipefail

export PGPASSWORD="${POSTGRES_PASSWORD}"
DBARGS=(--database "$POSTGRES_DB" --username "$POSTGRES_USER" --host "$PGHOST")

echo "==> Initialisation de la replication (une seule fois ; ignoree si deja faite)"
# Se cale sur l'horodatage des donnees deja importees.
osm2pgsql-replication init "${DBARGS[@]}" || true

echo "==> Application des differentiels OSM"
# 'update' telecharge les diffs depuis le dernier etat et les applique en mode append.
osm2pgsql-replication update "${DBARGS[@]}" -- --hstore

echo ""
echo "============================================================"
echo " Mise a jour OSM terminee."
echo " Les vues du schema 'catalog' refletent automatiquement les"
echo " changements (pas besoin de les recreer)."
echo "============================================================"
