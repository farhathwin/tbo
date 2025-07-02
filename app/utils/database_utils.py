import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.engine.url import make_url, URL
from app import db
from app.models import Base, TenantUser, TenantOTP, TenantUserInvite, Customer  # Ensure all models are imported!

# Absolute path to the repository root. This allows database paths to be
# resolved correctly even when scripts are executed from different
# working directories.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))




COMPANY_DATABASES = {}  # domain => scoped_session instance


def _use_mysql():
    """Return ``True`` when the application is configured for MySQL."""
    try:
        return db.engine.url.drivername.startswith("mysql")
    except Exception:
        pass

    uri = os.environ.get("SQLALCHEMY_DATABASE_URI", "")
    return uri.startswith("mysql")


def _get_admin_base_url() -> URL:
    """Return the SQLAlchemy URL used for admin-level operations."""
    admin_uri = os.environ.get("SQLALCHEMY_ADMIN_URI")
    uri = admin_uri or os.environ.get("SQLALCHEMY_DATABASE_URI")
    return make_url(uri).set(database=None)


def get_tenant_db_uri(domain: str) -> str:
    """Return the full SQLAlchemy URI for a tenant database."""
    if _use_mysql():
        base_url = make_url(os.environ["SQLALCHEMY_DATABASE_URI"])
        db_name = domain.replace(".", "_")
        return base_url.set(database=db_name).render_as_string(hide_password=False)
    db_path = get_tenant_db_path(domain)
    return f"sqlite:///{db_path}"




def get_tenant_db_path(domain):
    """Return the absolute path for a tenant's SQLite database."""
    db_name = domain.replace(".", "_")
    return os.path.join(BASE_DIR, "tenant_dbs", f"{db_name}.db")

def create_company_schema(domain):
    """Create the tenant schema and return a scoped session factory."""
    if _use_mysql():
        base_url = _get_admin_base_url()
        db_name = domain.replace(".", "_")

        # Ensure the database exists before creating tables
        admin_engine = create_engine(base_url.render_as_string(hide_password=False))
        with admin_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`"))

        engine = create_engine(
            base_url.set(database=db_name).render_as_string(hide_password=False),
            echo=True,
        )
    else:
        db_path = get_tenant_db_path(domain)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}", echo=True)

    Base.metadata.create_all(engine)

    session_factory = scoped_session(sessionmaker(bind=engine))
    COMPANY_DATABASES[domain] = session_factory
    return session_factory  # ✅ Important: return this to be used right away



def get_db_for_domain(domain):
    """Return (and cache) a scoped session for the specified domain."""
    if domain in COMPANY_DATABASES:
        return COMPANY_DATABASES[domain]

    if _use_mysql():
        base_url = make_url(os.environ["SQLALCHEMY_DATABASE_URI"])
        db_name = domain.replace(".", "_")
        engine = create_engine(
            base_url.set(database=db_name).render_as_string(hide_password=False)
        )
    else:
        db_path = get_tenant_db_path(domain)
        if not os.path.exists(db_path):
            raise Exception(f"No database found for domain: {db_path}")
        engine = create_engine(f"sqlite:///{db_path}")

    session_factory = scoped_session(sessionmaker(bind=engine))
    COMPANY_DATABASES[domain] = session_factory
    return session_factory


def get_company_db_session(domain):
    """Return a plain SQLAlchemy session bound to the tenant database."""
    if _use_mysql():
        print(f"[DEBUG] Tenant DB URI (OTP Validation): {get_tenant_db_uri(domain)}")
    else:
        db_path = get_tenant_db_path(domain)
        print(f"[DEBUG] Tenant DB Session Path (OTP Validation): {db_path}")

    session_factory = get_db_for_domain(domain)
    engine = session_factory.bind
    return sessionmaker(bind=engine)()


