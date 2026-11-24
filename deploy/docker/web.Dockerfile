# -----------------------------------------------------------------------------
# rag-web: the React SPA served by unprivileged nginx (plan §4 Phase 8).
#
#   docker build -f deploy/docker/web.Dockerfile -t rag-web:local .
#
# nginx serves the static build and reverse-proxies /api (plus /qa and the health
# endpoints) to the API, so the browser talks to one origin: no CORS, and the
# SameSite=Strict refresh cookie works (ADR-0012). The upstream is the DNS name `api`
# (Compose service, Kubernetes Service), set at build time with API_UPSTREAM.
# -----------------------------------------------------------------------------
ARG NODE_IMAGE=node:26-slim
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.30-alpine

FROM ${NODE_IMAGE} AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty base URL = same origin (nginx proxies /api). `npm run build` type-checks first.
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM ${NGINX_IMAGE} AS runtime
ARG API_UPSTREAM=api:8000
LABEL org.opencontainers.image.title="rag-web" \
      org.opencontainers.image.description="Healthcare Guidelines RAG Assistant web app (synthetic corpus, not for clinical use)" \
      org.opencontainers.image.licenses="UNLICENSED"
# Apply Alpine security fixes published after the base tag was built. Manual test F-19:
# nginx 1.30.6-r1 and brotli-libs 1.2.0-r1 carried fixed CRITICAL CVEs that a fresh pull of
# nginx-unprivileged:1.30-alpine did not include yet. The image still runs as uid 101.
USER root
RUN apk upgrade --no-cache
COPY --chown=101:101 deploy/docker/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --chown=101:101 deploy/docker/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
RUN sed -i "s|__API_UPSTREAM__|${API_UPSTREAM}|" /etc/nginx/conf.d/default.conf
COPY --from=build --chown=101:101 /src/frontend/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/nginx-health"]
