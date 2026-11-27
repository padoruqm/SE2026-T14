# The pinned Potree release, fetched by the same script as local development
# (`scripts/` is passed as the named build context `scripts` in compose.yaml).
FROM debian:bookworm-slim AS potree

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl perl unzip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=scripts fetch-potree.sh /work/scripts/fetch-potree.sh
RUN /work/scripts/fetch-potree.sh

FROM node:24-bookworm-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
COPY --from=potree /work/frontend/public/potree ./public/potree
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
