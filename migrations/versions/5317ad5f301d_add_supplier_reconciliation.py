"""Add supplier reconciliation tables and is_reconciled column

Revision ID: 5317ad5f301d
Revises: df0745a851cf
Create Date: 2025-06-29 18:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5317ad5f301d'
down_revision = 'df0745a851cf'
branch_labels = None
depends_on = None


def upgrade():
    # Add column to invoice_lines
    op.add_column('invoice_lines', sa.Column('is_reconciled', sa.Boolean(), server_default=sa.text('0')))

    # Add status column to supplier_reconciliations
    op.add_column('supplier_reconciliations', sa.Column('status', sa.String(), server_default='Saved'))

    # New table supplier_reconciliation_lines
    op.create_table(
        'supplier_reconciliation_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reconciliation_id', sa.Integer(), sa.ForeignKey('supplier_reconciliations.id'), nullable=False),
        sa.Column('invoice_line_id', sa.Integer(), sa.ForeignKey('invoice_lines.id'), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False)
    )

    # New table supplier_payment_dues
    op.create_table(
        'supplier_payment_dues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reconciliation_id', sa.Integer(), sa.ForeignKey('supplier_reconciliations.id'), nullable=False),
        sa.Column('reference', sa.String()),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False)
    )


def downgrade():
    op.drop_table('supplier_payment_dues')
    op.drop_table('supplier_reconciliation_lines')
    op.drop_column('supplier_reconciliations', 'status')
    op.drop_column('invoice_lines', 'is_reconciled')
