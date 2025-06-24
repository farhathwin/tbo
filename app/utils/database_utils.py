import os
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from app import db
from app.models import Base, TenantUser, TenantOTP, TenantUserInvite, Customer  # Ensure all models are imported!




COMPANY_DATABASES = {}  # domain => scoped_session instance




def get_tenant_db_path(domain):
    """Converts a domain like 'farhath.benztravels.com' to 'tenant_dbs/farhath_benztravels_com.db'."""
    db_name = domain.replace(".", "_")
    return f"tenant_dbs/{db_name}.db"

def create_company_schema(domain):
    """
    Creates SQLite DB schema for the given domain and stores the session in COMPANY_DATABASES.
    """
    db_path = get_tenant_db_path(domain)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}", echo=True)

    # Ensures all models are available
    Base.metadata.create_all(engine)

    session_factory = scoped_session(sessionmaker(bind=engine))
    COMPANY_DATABASES[domain] = session_factory
    return session_factory  # ✅ Important: return this to be used right away



def get_db_for_domain(domain):
    """
    Retrieves the scoped session for a given domain. Raises an error if DB is missing.
    """
    db_path = get_tenant_db_path(domain)

    if domain in COMPANY_DATABASES:
        return COMPANY_DATABASES[domain]

    if not os.path.exists(db_path):
        raise Exception(f"No database found for domain: {db_path}")

    engine = create_engine(f"sqlite:///{db_path}")
    session_factory = scoped_session(sessionmaker(bind=engine))
    COMPANY_DATABASES[domain] = session_factory
    return session_factory


def get_company_db_session(domain):
    """
    Returns a plain SQLAlchemy session bound to the correct domain's database engine.
    Use this when you need a raw session for querying.
    """
    db_path = get_tenant_db_path(domain)
    print(f"[DEBUG] Tenant DB Session Path (OTP Validation): {db_path}")

    session_factory = get_db_for_domain(domain)
    engine = session_factory.bind
    return sessionmaker(bind=engine)()


