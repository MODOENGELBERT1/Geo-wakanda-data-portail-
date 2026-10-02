FROM debian:bookworm-slim

# Outils d'ingestion OSM : osm2pgsql (import), le client PostgreSQL (psql pour jouer les vues),
# et curl (telechargement de l'extrait Geofabrik Cameroun).
RUN apt-get update && apt-get install -y --no-install-recommends \
      osm2pgsql \
      postgresql-client \
      curl \
      ca-certificates \
      bash \
    && rm -rf /var/lib/apt/lists/*
# (osm2pgsql-replication / pyosmium retires : la synchro par diffs sera ajoutee
#  proprement en phase 2 ; l'import initial n'en a pas besoin.)

WORKDIR /data
