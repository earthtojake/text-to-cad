# syntax=docker/dockerfile:1

ARG NODE_VERSION=24.14.0
FROM node:${NODE_VERSION}-bookworm AS build

RUN apt-get update \
  && apt-get install --yes --no-install-recommends build-essential python3 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /runtime-deps
COPY package.json ./package.json
RUN npm install --omit=dev --no-audit --no-fund

FROM scratch
COPY --from=build /runtime-deps/node_modules /node_modules
