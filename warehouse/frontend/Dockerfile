FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=warehouse_ca,required=false \
    if [ -f /run/secrets/warehouse_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/warehouse_ca; fi; \
    npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--port", "5173"]
