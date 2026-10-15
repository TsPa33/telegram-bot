FROM node:22-alpine AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=warehouse_ca,required=false \
    if [ -f /run/secrets/warehouse_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/warehouse_ca; fi; \
    npm ci
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

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
