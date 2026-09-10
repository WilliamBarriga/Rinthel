# pi requires Node >= 22.19
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
COPY server/package.json server/
COPY web/package.json web/
RUN npm install
COPY server server
COPY web web
RUN npm run build

FROM node:22-slim
WORKDIR /app

# git and openssh so pi can work with real repos; ca-certificates for HTTPS.
# curl and wget because install scripts and the /data/bin workflow assume them.
# Installed here rather than into a running container, where they look like they
# stuck — a restart keeps them — and then vanish on the next rebuild.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git openssh-client ca-certificates curl wget \
    && rm -rf /var/lib/apt/lists/*

# Python 3.14, via uv's prebuilt python-build-standalone binaries — seconds
# instead of the ~10-15min a from-source compile took, and no build-essential
# or -dev headers needed in this image. uv itself is copied in below (right
# before its own comment); this stage just borrows the binary early.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/
RUN uv python install 3.14 --install-dir /usr/local/python-managed \
    && ln -sf /usr/local/python-managed/cpython-3.14-linux-x86_64-gnu/bin/python3.14 /usr/local/bin/python3 \
    && ln -sf /usr/local/python-managed/cpython-3.14-linux-x86_64-gnu/bin/python3.14 /usr/local/bin/python3.14 \
    && ln -sf /usr/local/python-managed/cpython-3.14-linux-x86_64-gnu/bin/pip3.14 /usr/local/bin/pip3 \
    && python3 --version

# Utility tools — prebuilt .deb binaries for ripgrep and fd, apt for the rest.
# ripgrep (fast search), fd-find (modern find), jq (JSON parser),
# sqlite3 (database CLI), nmap (network scanning).
RUN apt-get update && apt-get install -y --no-install-recommends \
      sqlite3 nmap jq \
    && wget -qO /tmp/ripgrep.deb https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/ripgrep_15.2.0-1_amd64.deb \
    && wget -qO /tmp/fd.deb https://github.com/sharkdp/fd/releases/download/v10.5.0/fd-musl_10.5.0_amd64.deb \
    && dpkg -i /tmp/ripgrep.deb /tmp/fd.deb \
    && apt-get install -f -y \
    && rm -f /tmp/ripgrep.deb /tmp/fd.deb \
    && rm -rf /var/lib/apt/lists/* \
    && jq --version && rg --version | head -1 && fd --version && sqlite3 --version && nmap --version | head -1

# uv, so the agent can run Python tooling — a large share of MCP servers are
# Python and are launched with uvx. Static musl binaries, no Python needed to
# install them; uv fetches a managed interpreter on first use, into HOME on the
# data volume. Pinned so a rebuild does not silently change the toolchain.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

RUN npm install -g @earendil-works/pi-coding-agent@latest

COPY package.json package-lock.json* ./
COPY server/package.json server/
RUN npm install --omit=dev -w server

COPY --from=build /app/server/dist server/dist
COPY --from=build /app/web/dist web/dist

# The builtin channel packages. Loaded from here at runtime; third-party ones
# are installed into CHANNELS_DIR on the data volume instead, so they survive
# an image rebuild.
COPY channels channels

# Skills the portal ships. Loaded from here for every session; anything the
# agent writes goes to the data volume instead.
COPY skills skills

# HOME lives on the data volume so pi packages and settings (~/.pi/agent)
# survive image rebuilds instead of being silently wiped.
# /data/bin is the escape hatch: anything dropped there is on PATH for pi and
# every tool it launches, and survives an image rebuild. Installing a CLI into
# the image filesystem instead looks like it worked — it survives a restart —
# and then vanishes on the next deploy, which rebuilds.
ENV PATH=/data/bin:$PATH
ENV NODE_ENV=production \
    PORT=4100 \
    DATA_DIR=/data \
    SESSION_DIR=/data/sessions \
    WORKSPACE_ROOT=/workspaces \
    CHANNELS_DIR=/data/channels \
    AGENT_HOME=/data/agent-home \
    HOME=/data/home
RUN mkdir -p /data/home /data/bin
EXPOSE 4100
VOLUME /data
CMD ["node", "server/dist/index.js"]
