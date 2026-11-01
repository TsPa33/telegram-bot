FROM node:22-alpine AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
# Verify every deployed Alembic head is accepted by the frontend readiness gates.
# Tests and migration sources stay in the builder stage, never the public nginx image.
COPY frontend/tests ./tests
COPY backend/alembic/versions ./backend/alembic/versions
RUN npm run build > /tmp/warehouse-build.log 2>&1 || ((grep -n -A 24 -B 6 '^not ok' /tmp/warehouse-build.log || tail -n 100 /tmp/warehouse-build.log) && exit 1)
RUN tail -n 12 /tmp/warehouse-build.log

FROM nginx:1.28-alpine
COPY --from=build /build/dist /usr/share/nginx/html
COPY deploy/railway/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/railway/nginx/server.conf.template /etc/nginx/warehouse-server.conf.template
COPY deploy/railway/frontend-start.sh /usr/local/bin/warehouse-frontend
RUN chmod 755 /usr/local/bin/warehouse-frontend && \
    chmod -R a=rX /usr/share/nginx/html /etc/nginx/nginx.conf /etc/nginx/warehouse-server.conf.template
USER nginx
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/warehouse-frontend"]
