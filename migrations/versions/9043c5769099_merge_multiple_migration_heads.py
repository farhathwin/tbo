"""Merge multiple migration heads

Revision ID: 9043c5769099
Revises: 47acffe96dd2, c45fc7cdd7c1
Create Date: 2025-06-30 22:47:23.886302

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9043c5769099'
down_revision = ('47acffe96dd2', 'c45fc7cdd7c1')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
