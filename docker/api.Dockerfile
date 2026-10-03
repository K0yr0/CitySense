# CityEcho API image (also used by the one-shot `seed` and `simulator` services).
# Build context: repo root (see ../.dockerignore). Only backend/requirements.txt is
# installed: no osmnx / geopandas / torch, so the image stays small. The map is loaded
# from a pre-built GeoJSON (data/osm/segments_demo.geojson), which needs only shapely.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libglib2.0-0: some opencv-python-headless wheels still link libgthread.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so code edits do not invalidate the pip layer.
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Source is baked in so the image also runs without bind mounts; in docker-compose.yml
# backend/, db/, scripts/ and data/ are mounted over these for live reload.
COPY backend ./backend
COPY db ./db
COPY scripts ./scripts
COPY data ./data
COPY pytest.ini ./

# Strip CR (a Windows checkout with core.autocrlf=true turns LF into CRLF, which breaks
# the shebang) and set the executable bit (lost on some Windows checkouts).
COPY docker/api-entrypoint.sh /usr/local/bin/cityecho-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/cityecho-entrypoint \
    && chmod +x /usr/local/bin/cityecho-entrypoint \
    && mkdir -p /app/data/cache

EXPOSE 8000

# Entrypoint: wait for db -> init_db.py -> load map (optional) -> exec CMD.
ENTRYPOINT ["cityecho-entrypoint"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
