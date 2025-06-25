from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Float, Date, Numeric, Text
from app import db
from sqlalchemy.orm import relationship


# Tenant DB: multiple company databases
Base = declarative_base()

# ----------------- Core Models (Single DB) -----------------

class MasterCompany(db.Model):
    __tablename__ = 'master_company'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    domain = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    domain = db.Column(db.String(100), unique=True, nullable=False)
    active_key = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    last_login = db.Column(db.DateTime)

class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'))

class UserInvite(db.Model):
    __tablename__ = 'user_invite'
    __table_args__ = (
        db.UniqueConstraint('email', 'company_id', name='unique_invite_per_company'),
    )

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    token = db.Column(db.String(64), nullable=False, unique=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChangeLog(db.Model):  
    __tablename__ = 'change_log'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    table_name = db.Column(db.String(100), nullable=False)
    record_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(255))



# ----------------- Tenant Models (Per Company DB) -----------------
class TenantUser(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False)
    company_id = Column(Integer, nullable=False)
    last_login = Column(DateTime)
    last_login = db.Column(db.DateTime, default=None)
    is_suspended = db.Column(db.Boolean, default=False)

class TenantOTP(Base):
    __tablename__ = 'otp'
    id = Column(Integer, primary_key=True)
    email = Column(String(100), nullable=False)
    otp_code = Column(String(6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    company_id = Column(Integer)

class TenantUserInvite(Base):
    __tablename__ = 'user_invite'
    id = Column(Integer, primary_key=True)
    email = Column(String(150), nullable=False, unique=True)
    role = Column(String(50), nullable=False)
    token = Column(String(64), nullable=False, unique=True)
    company_id = Column(Integer, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class CompanyProfile(Base):
    __tablename__ = 'company_profile'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    company_name = Column(String(100), nullable=False)
    trading_name = Column(String(100))
    country = Column(String(50))
    address_line_1 = Column(String(200))
    address_line_2 = Column(String(200))
    city = Column(String(100))
    currency_code = Column(String(10))
    phone = Column(String(20))
    email = Column(String(100))
    website = Column(String(100))
    logo_path = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    account_types_initialized = Column(Boolean, default=False)


class UserProfile(Base):
    __tablename__ = 'user_profile'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    email = Column(String(100), nullable=False) 
    full_name = Column(String(100))
    dob = Column(DateTime)
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)


class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    account_type = Column(String(50), nullable=False)
    account_code = Column(String(20), nullable=False)
    account_name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey('accounts.id'), nullable=True)
    currency_code = Column(String(10), nullable=True)
    is_reconcilable = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    journal_lines = relationship("JournalLine", back_populates="account")

    __table_args__ = (
        UniqueConstraint('company_id', 'account_code', name='uq_company_account_code'),
    )



    # ✅ Add this relationship
    journal_lines = relationship("JournalLine", back_populates="account")

    __table_args__ = (
        UniqueConstraint('company_id', 'account_code', name='uq_company_account_code'),
    )

class JournalEntry(Base):
    __tablename__ = 'journal_entries'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    reference = Column(String(100))
    narration = Column(String(255))
    fiscal_year_id = Column(Integer, ForeignKey('fiscal_years.id'))
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    reversed_entry_id = Column(Integer, ForeignKey('journal_entries.id'), nullable=True)  # points to the entry it reversed
    reversed_by = relationship('JournalEntry', remote_side=[id], backref='reversal_of')

    lines = relationship("JournalLine", back_populates="entry", cascade="all, delete-orphan")


class JournalLine(Base):
    __tablename__ = 'journal_lines'

    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey('journal_entries.id'))
    account_id = Column(Integer, ForeignKey('accounts.id'))
    partner_id = Column(Integer, nullable=True)
    debit = Column(Float, default=0)
    credit = Column(Float, default=0)
    narration = Column(String(255))

    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")



class FiscalYear(Base):
    __tablename__ = 'fiscal_years'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    name = Column(String(50), nullable=False)
    year_name = Column(String(20), nullable=False)  # e.g., "2024-2025"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_closed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class AccountType(Base):
    __tablename__ = 'account_types'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey('account_types.id'), nullable=True)
    is_header = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    parent = relationship("AccountType", remote_side=[id], backref="children")


class Customer(Base):
    __tablename__ = 'customers'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    customer_type = Column(String(20), nullable=False)
    account_receivable_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)  # ✅ FIXED HERE
    phone_number = Column(String(20), nullable=False)

    title = Column(String(10), nullable=True)
    full_name = Column(String(100), nullable=True)
    business_name = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", backref="customers", foreign_keys=[account_receivable_id])

    __table_args__ = (
        UniqueConstraint('company_id', 'phone_number', name='uq_company_customer_phone'),
    )

class Supplier(Base):
    __tablename__ = 'suppliers'

    id = Column(Integer, primary_key=True)
    supplier_code = Column(String, unique=True, nullable=True)  # SUP0001, SUP0002 etc.
    company_id = Column(Integer, nullable=False)
    account_payable_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    supplier_type = Column(String, nullable=False)  # e.g., Expenses, BSP, Airlines...
    business_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    email = Column(String)
    is_reconcilable = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CashBank(Base):
    __tablename__ = 'cash_bank'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    type = Column(String, nullable=False)  # Cash, Bank, Wallet
    account_name = Column(String)  # For Cash & Bank
    bank_name = Column(String)     # For Bank
    account_number = Column(String)  # For Bank
    wallet_name = Column(String)   # For Wallet
    supplier_id = Column(Integer, ForeignKey('suppliers.id'))  # Only for Wallet
    account_cashandbank_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)  # ✅ FIXED HERE
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship("Supplier")


class Invoice(Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    invoice_number = Column(String, nullable=False, unique=True)
    invoice_date = Column(Date, nullable=False)
    transaction_date = Column(Date, nullable=False, default=date.today)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    service_type = Column(String, nullable=False)  # e.g., Flight, Hotel, Visa
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String, nullable=False, default='LKR')
    status = Column(String, default='Draft')  # Draft, Finalized, Paid
    destination = Column(String(10))
    due_term = Column(Integer, default=0)
    staff_id = Column(Integer)
    staff = relationship("TenantUser", primaryjoin="Invoice.staff_id==TenantUser.id")

    created_by_user = relationship(
        "TenantUser",
        primaryjoin="Invoice.created_by==TenantUser.id",
        foreign_keys="Invoice.created_by",
        viewonly=True,
    )

    # audit
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    pax_details = relationship("PaxDetail", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceLine(Base):
    __tablename__ = 'invoice_lines'
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)

    pax_id = Column(Integer, ForeignKey('pax_details.id'), nullable=True)
    pax = relationship("PaxDetail")

    type = Column(String(20), nullable=False)  # "Air Ticket" or "Other"
    sub_type = Column(String(30))  # "IATA", "Budget", "Hotel", etc.

    base_fare = Column(Numeric(12, 2), default=0.00)
    tax = Column(Numeric(12, 2), default=0.00)
    sell_price = Column(Numeric(12, 2), nullable=False)
    profit = Column(Numeric(12, 2), default=0.00)

    pnr = Column(String(50))  # For Air or Other
    designator = Column(String(20))  # Only for IATA
    ticket_no = Column(String(50))  # Only for Air

    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    supplier = relationship("Supplier")

    invoice = relationship("Invoice", back_populates="lines")

    # Optional: audit fields
    created_at = Column(DateTime, default=datetime.utcnow)


class PaxDetail(Base):
    __tablename__ = 'pax_details'

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    pax_type = Column(String(10))
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    date_of_birth = Column(Date)
    passport_no = Column(String(50))
    nationality = Column(String(50))
    passport_expiry_date = Column(Date)

    invoice = relationship('Invoice', back_populates='pax_details')


