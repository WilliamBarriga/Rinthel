# pi requires Node >= 22.19
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY server/package.json server/
COPY web/package.json web/
RUN npm ci
COPY shared shared
COPY server server
COPY web web
RUN npm run build

# The server's runtime dependencies only (better-sqlite3 ships a prebuilt binary for this Node),
# pi's SDK among them: every Session runs pi in this process.
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
COPY server/package.json server/
COPY web/package.json web/
RUN npm ci --omit=dev -w @deck/server

FROM node:22-slim
WORKDIR /app
COPY --from=deps /app/node_modules node_modules
COPY --from=deps /app/package.json package.json
COPY server/package.json server/
COPY --from=build /app/server/dist server/dist
COPY --from=build /app/web/dist web/dist

# HOME lives on the data volume, so pi's agentDir (~/.pi/agent) and its packages
# survive image rebuilds. /data/bin is on PATH: a CLI dropped there survives a
# rebuild, unlike one installed into the image filesystem. pi's own CLI comes
# with its SDK (node_modules/.bin/pi), for installing packages into the agentDir.
ENV PATH=/data/bin:/app/node_modules/.bin:$PATH
ENV NODE_ENV=production \
    PORT=4200 \
    DATA_DIR=/data \
    HOME=/data/home
RUN mkdir -p /data/home /data/bin && chmod 777 /data /data/home /data/bin
EXPOSE 4200
VOLUME /data
CMD ["node", "server/dist/index.js"]
