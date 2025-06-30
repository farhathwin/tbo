"""Add tables for supplier reconciliation lines and payment due, and is_reconciled column"""

from alembic import op
import sqlalchemy as sa

revision = 'c45fc7cdd7c1'
down_revision = '39d60885286f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoice_lines', sa.Column('is_reconciled', sa.Boolean(), nullable=True, server_default=sa.text('false')))

    op.alter_column('supplier_reconciliations', 'statement_amount', nullable=False, server_default=sa.text('0'))

    op.create_table(
        'supplier_reconciliation_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reconciliation_id', sa.Integer(), sa.ForeignKey('supplier_reconciliations.id'), nullable=False),
        sa.Column('invoice_line_id', sa.Integer(), sa.ForeignKey('invoice_lines.id'), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
    )

    op.create_table(
        'supplier_payment_dues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reconciliation_id', sa.Integer(), sa.ForeignKey('supplier_reconciliations.id'), nullable=False),
        sa.Column('reference', sa.String(), nullable=True),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
    )


def downgrade():
    op.drop_table('supplier_payment_dues')
    op.drop_table('supplier_reconciliation_lines')
    op.drop_column('invoice_lines', 'is_reconciled')
