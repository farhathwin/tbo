from decimal import Decimal
from app.models.models import CompanyProfile


def get_company_currency(session, company_id):
    """Return the company's default currency code."""
    company = session.query(CompanyProfile).filter_by(company_id=company_id).first()
    return company.currency_code if company and company.currency_code else "LKR"


def convert_to_default(amount, currency, company_currency, rate=None):
    """Convert amount from given currency to company currency using rate.

    If currency matches company currency or no rate is provided, the amount
    is returned unchanged.
    """
    if currency == company_currency or rate is None:
        return Decimal(str(amount))
    return Decimal(str(amount)) * Decimal(str(rate))
