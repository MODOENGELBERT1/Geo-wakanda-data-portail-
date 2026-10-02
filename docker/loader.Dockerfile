FROM debian:bookworm-slim

# Outils d'ingestion OSM : osm2pgsql (import), le client PostgreSQL (psql pour jouer les vues),
# et curl (telechargement de l'extrait Geofabrik Cameroun).
RUN apt-get update && apt-get install -y --no-install-recommends \
      osm2pgsql \
      osm2pgsql-replication \
      python3-pyosmium \
      postgresql-client \
      curl \
      ca-certificates \
      bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data
