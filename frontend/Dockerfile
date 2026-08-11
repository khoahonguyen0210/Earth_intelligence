# Multi-stage: build the Vite/React static bundle, then serve it with
# nginx. The frontend calls the backend at the browser's own
# http://localhost:8080 (src/api/client.ts, unchanged) rather than a
# Docker-internal service name -- the browser runs on the host, not
# inside the compose network, and docker-compose.yml maps the backend's
# port 8080 straight through to the host for exactly this reason.

FROM node:22-alpine AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 80
