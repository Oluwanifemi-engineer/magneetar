# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR DASHBOARD — Dockerfile
# Multi-stage build with Nginx serving static files
# ═══════════════════════════════════════════════════════════════════════════════

# ── Builder Stage ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

# Build argument for API URL (Next.js bakes NEXT_PUBLIC_* at build time)
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the Next.js app
RUN npm run build

# ── Production Stage ─────────────────────────────────────────────────────────
FROM nginx:alpine

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/out /usr/share/nginx/html

# Environment variable substitution support
# The dashboard is built as static export, so runtime env vars
# need to be injected via the nginx config or replaced at deploy time

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
