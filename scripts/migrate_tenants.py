import sys
import os
from sqlalchemy import text
from flask_migrate import Migrate, upgrade, stamp

# Add parent directory to path so imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app, db  # ✅ FIXED
from app.utils.database_utils import get_tenant_db_path, create_company_schema


app = create_app()
# Determine the absolute path to the repository root so database files
# can be resolved regardless of the current working directory.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Point to the central database that stores tenant domains. The file
# lives under the application's ``instance`` folder.
CENTRAL_DB_URI = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'app.db')}"


def get_all_tenants():
    app = create_app(db_uri_override=CENTRAL_DB_URI)
    with app.app_context():
        result = db.session.execute(text("SELECT domain FROM master_company"))
        return [row.domain for row in result.fetchall()]


def migrate_tenant(domain):
    db_path = get_tenant_db_path(domain)
    if not os.path.exists(db_path):
        # Ensure the tenant database exists before attempting migrations
        create_company_schema(domain)

    db_uri = f"sqlite:///{db_path}"
    print(f"🔁 Migrating tenant: {domain}")
    app = create_app(db_uri_override=db_uri)
    migrate = Migrate(app, db)
    with app.app_context():

        try:
            version = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            version = None

        if version is None:


        upgrade()


if __name__ == "__main__":
    tenants = get_all_tenants()
    for domain in tenants:
        migrate_tenant(domain)
