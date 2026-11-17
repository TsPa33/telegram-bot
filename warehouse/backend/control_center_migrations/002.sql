-- Additive staff onboarding; run only with the approved migrator.
ALTER TABLE control_center.staff DROP CONSTRAINT staff_role_check;
ALTER TABLE control_center.staff ADD CONSTRAINT staff_role_check
 CHECK (role IN ('Owner','Administrator','Manager','Support','Moderator'));
ALTER TABLE control_center.staff ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE control_center.staff ADD COLUMN temporary_expires_at TIMESTAMP WITH TIME ZONE;
-- Keep existing usernames/IDs intact. Refuse ambiguous legacy canonical names.
CREATE UNIQUE INDEX staff_username_canonical ON control_center.staff (lower(btrim(username)));
UPDATE control_center.schema_version SET version='002' WHERE version='001';
