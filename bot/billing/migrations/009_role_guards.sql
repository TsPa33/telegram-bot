-- Stable account/member identities stay immutable even for a row-lock capable app role.
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON billing.accounts FOR EACH ROW EXECUTE FUNCTION billing.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON billing.accounts FOR EACH STATEMENT EXECUTE FUNCTION billing.immutable();
CREATE FUNCTION billing.membership_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-'permissions') IS DISTINCT FROM (to_jsonb(OLD)-'permissions') THEN RAISE EXCEPTION 'immutable membership identity'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER membership_identity_guard BEFORE UPDATE OR DELETE ON billing.memberships FOR EACH ROW EXECUTE FUNCTION billing.membership_identity_guard();
