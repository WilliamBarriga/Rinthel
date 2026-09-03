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

# Python 3.14.7 — latest stable, compiled from source so it survives rebuilds,
# in its own stage so build-essential and the -dev headers never land in the
# final image. Installed to its own prefix (not /usr/local directly) so the
# COPY below can't collide with anything node:22-slim itself keeps there.
FROM node:22-slim AS python-build
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates zlib1g-dev libncurses5-dev libgdbm-dev \
      libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget \
      libbz2-dev liblzma-dev tk-dev \
    && rm -rf /var/lib/apt/lists/* \
    && wget -qO Python-3.14.7.tgz https://www.python.org/ftp/python/3.14.7/Python-3.14.7.tgz \
    && tar -xzf Python-3.14.7.tgz \
    && cd Python-3.14.7 \
    && ./configure --enable-optimizations --prefix=/usr/local/python3.14 \
    && make -j$(nproc) \
    && make install \
    && cd .. \
    && rm -rf Python-3.14.7 Python-3.14.7.tgz

FROM node:22-slim
WORKDIR /app

# git and openssh so pi can work with real repos; ca-certificates for HTTPS.
# curl and wget because install scripts and the /data/bin workflow assume them.
# Installed here rather than into a running container, where they look like they
# stuck — a restart keeps them — and then vanish on the next rebuild.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git openssh-client ca-certificates curl wget \
    && rm -rf /var/lib/apt/lists/*

# Python 3.14.7, built in the python-build stage above. Only its installed
# prefix is copied in — build-essential and the -dev headers stay out of this
# image. The -dev packages' shared libs still need their runtime counterparts
# here explicitly: those live in /usr/lib, not /usr/local, so copying the
# prefix alone doesn't bring them along.
COPY --from=python-build /usr/local/python3.14 /usr/local/python3.14
RUN apt-get update && apt-get install -y --no-install-recommends \
      zlib1g libtinfo6 libncursesw6 libgdbm6 libnss3 libssl3 libreadline8 \
      libffi8 libsqlite3-0 libbz2-1.0 liblzma5 tk \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/python3.14/bin/python3.14 /usr/local/bin/python3 \
    && ln -sf /usr/local/python3.14/bin/python3.14 /usr/local/bin/python3.14 \
    && ln -sf /usr/local/python3.14/bin/pip3.14 /usr/local/bin/pip3 \
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
