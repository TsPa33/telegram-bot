-- Run only as migration owner using psql -v app_role=cc_app -v operator_role=cc_operator.
-- Roles MUST be distinct NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT, not schema owners.
-- Do not grant either role membership in migrator/customer/finance owner roles.
REVOKE ALL ON SCHEMA control_center FROM PUBLIC;
GRANT USAGE ON SCHEMA control_center TO :"app_role", :"operator_role";
GRANT SELECT ON ALL TABLES IN SCHEMA control_center TO :"app_role";
GRANT INSERT, UPDATE ON control_center.staff, control_center.sessions,
 control_center.login_buckets, control_center.companies, control_center.source_links,
 control_center.company_grants, control_center.notes, control_center.tasks,
 control_center.source_state TO :"app_role";
GRANT DELETE ON control_center.sessions, control_center.company_grants TO :"app_role";
GRANT INSERT ON control_center.audit TO :"app_role", :"operator_role";
GRANT SELECT, INSERT, UPDATE ON control_center.staff TO :"operator_role";
GRANT SELECT, DELETE ON control_center.sessions TO :"operator_role";
REVOKE UPDATE, DELETE, TRUNCATE ON control_center.audit FROM :"app_role", :"operator_role";
-- No DDL, schema_version writes, customer or financial table rights.
