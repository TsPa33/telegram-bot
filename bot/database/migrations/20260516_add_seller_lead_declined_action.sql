ALTER TABLE seller_lead_actions
    DROP CONSTRAINT IF EXISTS seller_lead_actions_action_check;

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT con.conname INTO constraint_name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'seller_lead_actions'
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%action%'
      AND pg_get_constraintdef(con.oid) LIKE '%viewed%'
      AND pg_get_constraintdef(con.oid) LIKE '%skipped%'
      AND pg_get_constraintdef(con.oid) LIKE '%offered%'
    LIMIT 1;

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE seller_lead_actions DROP CONSTRAINT %I', constraint_name);
    END IF;
END $$;

ALTER TABLE seller_lead_actions
    ADD CONSTRAINT seller_lead_actions_action_check
    CHECK (action IN ('viewed', 'skipped', 'offered', 'declined'));
