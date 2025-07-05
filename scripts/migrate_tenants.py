import sys
import os
from sqlalchemy import text
from flask_migrate import Migrate, upgrade, stamp

# Add parent directory to path so imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app, db  # ✅ FIXED
from app.utils.database_utils import get_tenant_db_uri, create_company_schema


app = create_app()
# Determine the absolute path to the repository root so database files
# can be resolved regardless of the current working directory.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Base revision for initial tenant schema. If a tenant database doesn't have
# an Alembic version, we stamp it with this revision before upgrading.
BASE_REVISION = "df0745a851cf"

# Central database URI comes from the environment
CENTRAL_DB_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")


def get_all_tenants():
    app = create_app(db_uri_override=CENTRAL_DB_URI)
    with app.app_context():
        result = db.session.execute(text("SELECT domain FROM master_company"))
        return [row.domain for row in result.fetchall()]


def migrate_tenant(domain):
    db_uri = get_tenant_db_uri(domain)
    create_company_schema(domain)
    print(f"🔁 Migrating tenant: {domain}")
    app = create_app(db_uri_override=db_uri)
    migrations_dir = os.path.join(BASE_DIR, "migrations")
    migrate = Migrate(app, db, directory=migrations_dir)
    with app.app_context():

        try:
            version = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            version = None

        if version is None:
            # If the alembic_version table is missing, stamp the DB to the base
            # revision so that initial tables are not recreated. The "revision"
            # argument must be specified by keyword so the migration directory
            # configured above is used.
            stamp(revision=BASE_REVISION)

        upgrade()


if __name__ == "__main__":
    tenants = get_all_tenants()
    for domain in tenants:
        migrate_tenant(domain)
