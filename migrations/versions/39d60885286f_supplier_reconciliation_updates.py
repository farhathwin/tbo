"""Add statement amount to reconciliation"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '39d60885286f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('supplier_reconciliations', sa.Column('statement_amount', sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column('supplier_reconciliations', 'statement_amount')
