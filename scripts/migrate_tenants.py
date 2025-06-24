from app import create_app, db
from flask_migrate import Migrate, upgrade
from sqlalchemy import text
from app.utils.database_utils import get_tenant_db_path

CENTRAL_DB_URI = "sqlite:///app.db"


def get_all_tenants():
    app = create_app(db_uri_override=CENTRAL_DB_URI)
    with app.app_context():
        result = db.session.execute(text("SELECT domain FROM master_company"))
        return [row.domain for row in result.fetchall()]


def migrate_tenant(domain):
    db_uri = f"sqlite:///{get_tenant_db_path(domain)}"
    print(f"🔁 Migrating tenant: {domain}")
    app = create_app(db_uri_override=db_uri)
    migrate = Migrate(app, db)
    with app.app_context():
        upgrade()


if __name__ == "__main__":
    tenants = get_all_tenants()
    for domain in tenants:
        migrate_tenant(domain)
