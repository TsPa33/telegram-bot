-- Warehouse DB only. psql -v reader_role=cc_warehouse_reader, executed by source owner.
-- Reader is a separate unprivileged role; never use Warehouse runtime/owner credentials.
GRANT USAGE ON SCHEMA public TO :"reader_role";
GRANT SELECT (id,name,email,role,workspace_account_id,is_active,created_at,last_login_at)
 ON public.accounts TO :"reader_role";
GRANT SELECT ON public.alembic_version TO :"reader_role";
-- This role is dedicated to Control Center; clear earlier table-level grants.
REVOKE ALL ON public.vehicles, public.parts, public.warehouse_donor_provenance FROM :"reader_role";
GRANT SELECT ON public.warehouse_entitlement_workspaces TO :"reader_role";
GRANT SELECT (id,account_id,archived) ON public.vehicles TO :"reader_role";
GRANT SELECT (id,account_id,vehicle_id,quantity,reserved_quantity) ON public.parts TO :"reader_role";
GRANT SELECT (part_id,vehicle_id,workspace_id) ON public.warehouse_donor_provenance TO :"reader_role";
GRANT SELECT (account_id,created_at) ON public.operations TO :"reader_role";
-- Apply ALTER ROLE <reader> SET default_transaction_read_only=on and
-- statement_timeout='5s' as operator. No grants on auth sessions or password hashes.
