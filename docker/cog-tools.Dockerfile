FROM ghcr.io/osgeo/gdal:ubuntu-small-latest

# Outils pour ingerer une orthophoto :
#  - GDAL (fourni par l'image) : conversion GeoTIFF -> COG, lecture de l'emprise
#  - postgresql-client : enregistrer l'emprise dans le catalogue PostGIS
#  - mc (client MinIO) : envoyer le COG dans le stockage objet
RUN apt-get update && apt-get install -y --no-install-recommends \
      postgresql-client curl ca-certificates bash \
    && curl -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc \
    && chmod +x /usr/local/bin/mc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data
