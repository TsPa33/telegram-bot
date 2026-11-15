-- Control Center 001. Additive, operator-only; independent of Warehouse Alembic.
CREATE SCHEMA control_center;
REVOKE ALL ON SCHEMA control_center FROM PUBLIC;
CREATE TABLE control_center.schema_version (version text PRIMARY KEY, environment text NOT NULL);

CREATE TABLE control_center.audit (
	id VARCHAR(36) NOT NULL,
	actor VARCHAR(80) NOT NULL,
	permission VARCHAR(50) NOT NULL,
	scope VARCHAR(80) NOT NULL,
	target VARCHAR(80) NOT NULL,
	request_id VARCHAR(36) NOT NULL,
	reason VARCHAR(300),
	safe_diff JSON NOT NULL,
	result VARCHAR(30) NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE control_center.login_buckets (
	key VARCHAR(64) NOT NULL,
	attempts INTEGER NOT NULL,
	until TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (key)
)

;

CREATE TABLE control_center.source_state (
	key VARCHAR(80) NOT NULL,
	environment VARCHAR(20) NOT NULL,
	schema_version VARCHAR(40) NOT NULL,
	watermark VARCHAR(160),
	fetched_at TIMESTAMP WITH TIME ZONE,
	last_success TIMESTAMP WITH TIME ZONE,
	last_error VARCHAR(80),
	coverage VARCHAR(30) NOT NULL,
	PRIMARY KEY (key)
)

;

CREATE TABLE control_center.staff (
	id VARCHAR(36) NOT NULL,
	username VARCHAR(120) NOT NULL,
	password_hash TEXT NOT NULL,
	mfa_ciphertext TEXT NOT NULL,
	last_totp_step INTEGER NOT NULL,
	role VARCHAR(20) NOT NULL,
	finance BOOLEAN NOT NULL,
	active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (role IN ('Owner','Administrator','Manager','Support')),
	UNIQUE (username)
)

;

CREATE TABLE control_center.companies (
	id VARCHAR(36) NOT NULL,
	environment VARCHAR(20) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	display_name VARCHAR(120) NOT NULL,
	search_text TEXT NOT NULL,
	manager_id VARCHAR(36),
	labels JSON NOT NULL,
	snapshot JSON NOT NULL,
	registered_at TIMESTAMP WITH TIME ZONE NOT NULL,
	fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (environment, workspace_id),
	FOREIGN KEY(manager_id) REFERENCES control_center.staff (id)
)

;
CREATE INDEX ix_control_center_companies_manager_id ON control_center.companies (manager_id);
CREATE INDEX cc_directory_order ON control_center.companies (environment, display_name, id);

CREATE TABLE control_center.sessions (
	token_hash VARCHAR(64) NOT NULL,
	staff_id VARCHAR(36) NOT NULL,
	csrf_hash VARCHAR(64) NOT NULL,
	audience VARCHAR(40) NOT NULL,
	mfa_verified BOOLEAN NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (token_hash),
	FOREIGN KEY(staff_id) REFERENCES control_center.staff (id)
)

;
CREATE INDEX ix_control_center_sessions_staff_id ON control_center.sessions (staff_id);

CREATE TABLE control_center.company_grants (
	company_id VARCHAR(36) NOT NULL,
	staff_id VARCHAR(36) NOT NULL,
	PRIMARY KEY (company_id, staff_id),
	FOREIGN KEY(company_id) REFERENCES control_center.companies (id),
	FOREIGN KEY(staff_id) REFERENCES control_center.staff (id)
)

;

CREATE TABLE control_center.notes (
	id VARCHAR(36) NOT NULL,
	company_id VARCHAR(36) NOT NULL,
	staff_id VARCHAR(36) NOT NULL,
	text TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(company_id) REFERENCES control_center.companies (id),
	FOREIGN KEY(staff_id) REFERENCES control_center.staff (id)
)

;
CREATE INDEX ix_control_center_notes_company_id ON control_center.notes (company_id);

CREATE TABLE control_center.source_links (
	id VARCHAR(36) NOT NULL,
	company_id VARCHAR(36) NOT NULL,
	system VARCHAR(40) NOT NULL,
	environment VARCHAR(20) NOT NULL,
	entity_type VARCHAR(40) NOT NULL,
	source_id VARCHAR(160) NOT NULL,
	evidence VARCHAR(200),
	status VARCHAR(20) NOT NULL,
	verified_by VARCHAR(80),
	verified_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	UNIQUE (system, environment, entity_type, source_id),
	CHECK (status IN ('proposed','verified','conflict','revoked')),
	FOREIGN KEY(company_id) REFERENCES control_center.companies (id)
)

;
CREATE INDEX ix_control_center_source_links_company_id ON control_center.source_links (company_id);

CREATE TABLE control_center.tasks (
	id VARCHAR(36) NOT NULL,
	company_id VARCHAR(36) NOT NULL,
	assignee_id VARCHAR(36) NOT NULL,
	next_action VARCHAR(500) NOT NULL,
	status VARCHAR(20) NOT NULL,
	due_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (status IN ('open','in_progress','done')),
	FOREIGN KEY(company_id) REFERENCES control_center.companies (id),
	FOREIGN KEY(assignee_id) REFERENCES control_center.staff (id)
)

;
CREATE INDEX ix_control_center_tasks_company_id ON control_center.tasks (company_id);
CREATE INDEX ix_control_center_tasks_assignee_id ON control_center.tasks (assignee_id);
CREATE FUNCTION control_center.audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Control Center audit is append only'; END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON control_center.audit FOR EACH ROW EXECUTE FUNCTION control_center.audit_immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON control_center.audit FOR EACH STATEMENT EXECUTE FUNCTION control_center.audit_immutable();
