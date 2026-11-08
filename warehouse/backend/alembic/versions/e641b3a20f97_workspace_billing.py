"""Add isolated billing ledger only; no backfill or inventory changes."""
from alembic import op
revision="e641b3a20f97"
down_revision="d5298f3b7a10"
branch_labels=None
depends_on=None

def upgrade():
    op.execute('\nCREATE TABLE warehouse_subscriptions (\n\tworkspace_id VARCHAR(36) NOT NULL, \n\tplan VARCHAR(20) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tperiod_start TIMESTAMP WITH TIME ZONE, \n\tperiod_end TIMESTAMP WITH TIME ZONE, \n\tgrace_end TIMESTAMP WITH TIME ZONE, \n\tauto_renew BOOLEAN NOT NULL, \n\tprovider_id VARCHAR(160), \n\tPRIMARY KEY (workspace_id), \n\tFOREIGN KEY(workspace_id) REFERENCES accounts (id)\n)\n\n')
    op.execute('\nCREATE TABLE warehouse_billing_payments (\n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\trequest_key VARCHAR(80) NOT NULL, \n\tproduct VARCHAR(30) NOT NULL, \n\tamount NUMERIC(12, 2) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\tprovider_id VARCHAR(160), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconfirmed_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, request_key), \n\tUNIQUE (id, workspace_id), \n\tCHECK (amount>0), \n\tFOREIGN KEY(workspace_id) REFERENCES accounts (id)\n)\n\n')
    op.execute('CREATE INDEX ix_warehouse_billing_payments_workspace_id ON warehouse_billing_payments (workspace_id)')
    op.execute('\nCREATE TABLE warehouse_dismantling_credits (\n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tpayment_id VARCHAR(36) NOT NULL, \n\tsource VARCHAR(20) NOT NULL, \n\tgranted INTEGER NOT NULL, \n\tused INTEGER NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (granted>0 AND used>=0 AND used<=granted), \n\tUNIQUE (id, workspace_id), \n\tFOREIGN KEY(payment_id, workspace_id) REFERENCES warehouse_billing_payments (id, workspace_id), \n\tFOREIGN KEY(workspace_id) REFERENCES accounts (id), \n\tUNIQUE (payment_id), \n\tFOREIGN KEY(payment_id) REFERENCES warehouse_billing_payments (id)\n)\n\n')
    op.execute('CREATE INDEX ix_warehouse_dismantling_credits_workspace_id ON warehouse_dismantling_credits (workspace_id)')
    op.execute('\nCREATE TABLE warehouse_dismantling_usage (\n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tvehicle_id VARCHAR(36) NOT NULL, \n\tktype INTEGER NOT NULL, \n\toperation_key VARCHAR(80) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tcredit_id VARCHAR(36), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(vehicle_id, workspace_id) REFERENCES vehicles (id, account_id), \n\tFOREIGN KEY(credit_id, workspace_id) REFERENCES warehouse_dismantling_credits (id, workspace_id), \n\tUNIQUE (workspace_id, vehicle_id, ktype), \n\tUNIQUE (workspace_id, operation_key), \n\tFOREIGN KEY(workspace_id) REFERENCES accounts (id), \n\tFOREIGN KEY(vehicle_id) REFERENCES vehicles (id), \n\tFOREIGN KEY(credit_id) REFERENCES warehouse_dismantling_credits (id)\n)\n\n')
    op.execute('CREATE INDEX ix_warehouse_dismantling_usage_workspace_id ON warehouse_dismantling_usage (workspace_id)')
    op.execute('\nCREATE TABLE warehouse_billing_events (\n\tid VARCHAR(64) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tpayment_id VARCHAR(36) NOT NULL, \n\tkind VARCHAR(40) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\treceived_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES accounts (id), \n\tFOREIGN KEY(payment_id) REFERENCES warehouse_billing_payments (id), \n\tFOREIGN KEY(payment_id, workspace_id) REFERENCES warehouse_billing_payments (id, workspace_id)\n)\n\n')
    op.execute('CREATE INDEX ix_warehouse_billing_events_workspace_id ON warehouse_billing_events (workspace_id)')

def downgrade():
    raise RuntimeError("Payment evidence: downgrade requires manual review")
