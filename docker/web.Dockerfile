# CityEcho web admin (Next.js) image.
# Build context: web-admin/ (see web-admin/.dockerignore); this file is referenced from
# docker-compose.yml as ../docker/web.Dockerfile.
#
# NEXT_PUBLIC_* values are inlined into the browser bundle at BUILD time, so they are
# build args. NEXT_PUBLIC_API_URL must be reachable from the user's browser
# (http://localhost:8000), not the compose-internal http://api:8000.
# BACKEND_URL is used by the server-side /api/* rewrite in next.config.ts; rewrites are
# fixed at build time, so it is a build arg too (and set again at runtime).
# Debian (glibc) base on purpose: the lockfile carries the linux-*-gnu native binaries
# (next swc, lightningcss, tailwind oxide) for both amd64 and arm64.

FROM node:22-bookworm-slim AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
# postinstall runs scripts/copy-maplibre-worker.mjs, so the script must exist before npm ci.
COPY scripts ./scripts
RUN npm ci --no-audit --no-fund

FROM node:22-bookworm-slim AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_USE_MOCK=0
ARG BACKEND_URL=http://api:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_USE_MOCK=$NEXT_PUBLIC_USE_MOCK \
    BACKEND_URL=$BACKEND_URL \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `npm run build` triggers the prebuild script, which copies the maplibre worker into public/maplibre.
RUN npm run build

FROM node:22-bookworm-slim AS run
WORKDIR /app
ARG BACKEND_URL=http://api:8000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    BACKEND_URL=$BACKEND_URL \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# node_modules is kept whole (not pruned) so `next start` can load next.config.ts safely.
COPY --from=build --chown=node:node /app/package.json /app/package-lock.json /app/next.config.ts ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/.next ./.next
USER node
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
