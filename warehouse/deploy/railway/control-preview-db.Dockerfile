FROM postgres:16-bookworm
COPY warehouse/backend/control_center_migrations/001.sql /opt/control/001.sql
COPY warehouse/backend/control_center_migrations/grants.sql /opt/control/grants.sql
COPY warehouse/deploy/railway/control-preview-init.sh /docker-entrypoint-initdb.d/10-control-preview.sh
COPY warehouse/deploy/railway/control-preview-seed.sql /opt/control/seed.sql
COPY warehouse/deploy/railway/control-preview-db-start.sh /usr/local/bin/control-preview-db-start
RUN chmod 755 /usr/local/bin/control-preview-db-start && chmod 644 /docker-entrypoint-initdb.d/10-control-preview.sh
ENTRYPOINT ["/usr/local/bin/control-preview-db-start"]
