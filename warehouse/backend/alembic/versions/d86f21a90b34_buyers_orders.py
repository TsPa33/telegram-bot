"""Buyers and orders; additive only, no historical buyer/price backfill."""
from alembic import op
import sqlalchemy as sa
revision = 'd86f21a90b34'
down_revision = 'c24a9b71e603'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_part_id_account', 'parts', ['id', 'account_id'])
    op.execute("""CREATE TABLE buyers (
	id VARCHAR(36) NOT NULL,
	account_id VARCHAR(36) NOT NULL,
	name VARCHAR(200) NOT NULL,
	phone VARCHAR(50) NOT NULL,
	phone_normalized VARCHAR(20) NOT NULL,
	additional_phone VARCHAR(50) NOT NULL,
	additional_phone_normalized VARCHAR(20) NOT NULL,
	notes TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_buyer_id_account UNIQUE (id, account_id),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
)""")
    op.execute('CREATE INDEX ix_buyers_account_id ON buyers (account_id)')
    op.execute('CREATE INDEX ix_buyers_additional_phone_normalized ON buyers (additional_phone_normalized)')
    op.execute('CREATE INDEX ix_buyers_phone_normalized ON buyers (phone_normalized)')
    op.execute("""CREATE TABLE orders (
	id VARCHAR(36) NOT NULL,
	account_id VARCHAR(36) NOT NULL,
	number INTEGER NOT NULL,
	buyer_id VARCHAR(36) NOT NULL,
	contact_name VARCHAR(200) NOT NULL,
	contact_phone VARCHAR(50) NOT NULL,
	contact_phone_normalized VARCHAR(20) NOT NULL,
	status VARCHAR(20) NOT NULL,
	delivery_method VARCHAR(20) NOT NULL,
	city VARCHAR(150) NOT NULL,
	delivery_address VARCHAR(300) NOT NULL,
	tracking_number VARCHAR(100) NOT NULL,
	notes TEXT NOT NULL,
	sold_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_order_id_account UNIQUE (id, account_id),
	CONSTRAINT uq_order_account_number UNIQUE (account_id, number),
	CONSTRAINT fk_order_buyer_account FOREIGN KEY(buyer_id, account_id) REFERENCES buyers (id, account_id),
	CONSTRAINT ck_order_number CHECK (number > 0),
	CONSTRAINT ck_order_status CHECK (status IN ('new','reserved','shipped','completed','cancelled')),
	CONSTRAINT ck_order_delivery CHECK (delivery_method IN ('pickup','branch','address')),
	CONSTRAINT ck_order_delivery_address CHECK (delivery_method = 'pickup' OR (city <> '' AND delivery_address <> '')),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
)""")
    op.execute('CREATE INDEX ix_orders_account_id ON orders (account_id)')
    op.execute('CREATE INDEX ix_orders_contact_phone_normalized ON orders (contact_phone_normalized)')
    op.execute('CREATE INDEX ix_orders_created_at ON orders (created_at)')
    op.execute("""CREATE TABLE order_lines (
	id VARCHAR(36) NOT NULL,
	account_id VARCHAR(36) NOT NULL,
	order_id VARCHAR(36) NOT NULL,
	part_id VARCHAR(36) NOT NULL,
	name VARCHAR(200) NOT NULL,
	donor_snapshot JSON NOT NULL,
	quantity INTEGER NOT NULL,
	unit_price NUMERIC(14, 2) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	line_total NUMERIC(20, 2) NOT NULL,
	active BOOLEAN NOT NULL,
	sale_operation_id VARCHAR(36),
	PRIMARY KEY (id),
	CONSTRAINT uq_order_line_identity UNIQUE (id, account_id, part_id),
	CONSTRAINT fk_line_order_account FOREIGN KEY(order_id, account_id) REFERENCES orders (id, account_id),
	CONSTRAINT fk_line_part_account FOREIGN KEY(part_id, account_id) REFERENCES parts (id, account_id),
	CONSTRAINT ck_order_line_quantity CHECK (quantity > 0 AND quantity <= 1000000),
	CONSTRAINT ck_order_line_price CHECK (unit_price >= 0),
	CONSTRAINT ck_order_line_currency CHECK (currency IN ('UAH','USD')),
	CONSTRAINT ck_order_line_total CHECK (line_total = quantity * unit_price),
	UNIQUE (sale_operation_id),
	FOREIGN KEY(sale_operation_id) REFERENCES operations (id)
)""")
    op.execute('CREATE INDEX ix_order_lines_account_id ON order_lines (account_id)')
    op.execute('CREATE INDEX ix_order_lines_order_id ON order_lines (order_id)')
    op.execute('CREATE INDEX ix_order_lines_part_id ON order_lines (part_id)')
    op.execute('CREATE UNIQUE INDEX uq_order_active_part ON order_lines (order_id, part_id) WHERE active')
    op.execute("""CREATE TABLE order_reservations (
	id VARCHAR(36) NOT NULL,
	account_id VARCHAR(36) NOT NULL,
	order_line_id VARCHAR(36) NOT NULL,
	part_id VARCHAR(36) NOT NULL,
	quantity INTEGER NOT NULL,
	state VARCHAR(20) NOT NULL,
	reserve_operation_id VARCHAR(36) NOT NULL,
	release_operation_id VARCHAR(36),
	sale_operation_id VARCHAR(36),
	PRIMARY KEY (id),
	CONSTRAINT fk_reservation_line_account_part FOREIGN KEY(order_line_id, account_id, part_id) REFERENCES order_lines (id, account_id, part_id),
	CONSTRAINT ck_order_reservation_quantity CHECK (quantity > 0),
	CONSTRAINT ck_order_reservation_state CHECK (state IN ('active','released','consumed')),
	UNIQUE (reserve_operation_id),
	FOREIGN KEY(reserve_operation_id) REFERENCES operations (id),
	UNIQUE (release_operation_id),
	FOREIGN KEY(release_operation_id) REFERENCES operations (id),
	UNIQUE (sale_operation_id),
	FOREIGN KEY(sale_operation_id) REFERENCES operations (id)
)""")
    op.execute('CREATE INDEX ix_order_reservations_account_id ON order_reservations (account_id)')
    op.execute('CREATE INDEX ix_order_reservations_order_line_id ON order_reservations (order_line_id)')
    op.execute('CREATE INDEX ix_order_reservations_part_id ON order_reservations (part_id)')
    op.execute("CREATE UNIQUE INDEX uq_order_active_reservation ON order_reservations (order_line_id) WHERE state = 'active'")
    op.execute("""CREATE TABLE order_events (
	id VARCHAR(36) NOT NULL,
	account_id VARCHAR(36) NOT NULL,
	order_id VARCHAR(36) NOT NULL,
	actor_id VARCHAR(36) NOT NULL,
	type VARCHAR(40) NOT NULL,
	data JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_event_order_account FOREIGN KEY(order_id, account_id) REFERENCES orders (id, account_id),
	FOREIGN KEY(actor_id) REFERENCES accounts (id)
)""")
    op.execute('CREATE INDEX ix_order_events_account_id ON order_events (account_id)')
    op.execute('CREATE INDEX ix_order_events_order_id ON order_events (order_id)')
    op.execute("""CREATE TABLE order_requests (
	id VARCHAR(36) NOT NULL,
	account_id VARCHAR(36) NOT NULL,
	request_key VARCHAR(36) NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	response JSON NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_order_request_key UNIQUE (account_id, request_key),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
)""")
    op.execute('CREATE INDEX ix_order_requests_account_id ON order_requests (account_id)')


def downgrade():
    # Never discard buyers, orders, reservation ownership or replay evidence.
    db = op.get_bind()
    if db.execute(sa.text("SELECT EXISTS(SELECT 1 FROM buyers) OR EXISTS(SELECT 1 FROM orders) OR EXISTS(SELECT 1 FROM order_requests)")).scalar():
        raise RuntimeError('Cannot discard buyers, orders or order replay history; use a compatible application rollback')
    op.drop_table('order_requests')
    op.drop_table('order_events')
    op.drop_table('order_reservations')
    op.drop_table('order_lines')
    op.drop_table('orders')
    op.drop_table('buyers')
    op.drop_constraint('uq_part_id_account', 'parts', type_='unique')
