"""Durable API response receipts and assignment provenance; no stock/finance updates."""

from alembic import op
import sqlalchemy as sa

revision = "bd18a9f37c20"
down_revision = "ac97f052e1b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plan_parts_responses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "actor_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("vehicle_id", sa.String(36), nullable=True),
        sa.Column("resource", sa.String(30), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("normalized", sa.JSON(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("estimated_max_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"]
        ),
        sa.UniqueConstraint("account_id", "request_key", name="uq_pp_response_request"),
        sa.CheckConstraint(
            "status IN ('pending','received','validated','invalid','uncertain','rejected')",
            name="ck_pp_response_status",
        ),
        sa.CheckConstraint(
            "body IS NULL OR octet_length(body)<=2097152", name="ck_pp_response_size"
        ),
    )
    op.create_index(
        "ix_plan_parts_responses_account_id", "plan_parts_responses", ["account_id"]
    )
    op.create_index(
        "ix_pp_response_context",
        "plan_parts_responses",
        ["account_id", "context_hash", "created_at"],
    )
    op.create_index(
        "uq_pp_response_pending",
        "plan_parts_responses",
        ["account_id", "context_hash"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','uncertain')"),
    )
    op.add_column(
        "plan_parts_article_receipts",
        sa.Column(
            "response_id",
            sa.String(36),
            sa.ForeignKey("plan_parts_responses.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "plan_parts_article_receipts",
        sa.Column("response_metadata", sa.JSON(), nullable=True),
    )
    op.add_column("parts", sa.Column("article_provenance", sa.JSON(), nullable=True))
    op.add_column("parts", sa.Column("oem_provenance", sa.JSON(), nullable=True))
    op.execute(
        "CREATE FUNCTION pp_response_body_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.body IS NOT NULL AND (NEW.body IS DISTINCT FROM OLD.body OR NEW.sha256 IS DISTINCT FROM OLD.sha256) THEN RAISE EXCEPTION 'Provider response body is immutable'; END IF; RETURN NEW; END $$"
    )
    op.execute(
        "CREATE TRIGGER pp_response_body_no_change BEFORE UPDATE ON plan_parts_responses FOR EACH ROW EXECUTE FUNCTION pp_response_body_immutable()"
    )


def downgrade():
    raise RuntimeError(
        "Paid response/provenance history must be preserved; reviewed roll-forward required"
    )
