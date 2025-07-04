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


class Admin(db.Model):
    __tablename__ = 'admin'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



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
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=True)

    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")
    customer = relationship("Customer", backref="journal_lines")
    supplier = relationship("Supplier", backref="journal_lines")


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

    # --- Contact & Defaults ---
    email = Column(String(100))
    address_line_1 = Column(String(200))
    address_line_2 = Column(String(200))
    city = Column(String(100))
    country = Column(String(50))
    due_term = Column(Integer, default=0)
    consultant_id = Column(Integer, ForeignKey('users.id'))
    markup = Column(Float, default=0.0)

    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", backref="customers", foreign_keys=[account_receivable_id])
    consultant = relationship("TenantUser", foreign_keys=[consultant_id])

    __table_args__ = (
        UniqueConstraint('company_id', 'phone_number', name='uq_company_customer_phone'),
    )

class Supplier(Base):
    __tablename__ = 'suppliers'

    id = Column(Integer, primary_key=True)
    supplier_code = Column(String(20), unique=True, nullable=True)  # SUP0001, SUP0002 etc.
    company_id = Column(Integer, nullable=False)
    account_payable_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    supplier_type = Column(String(20), nullable=False)  # e.g., Expenses, BSP, Airlines...
    business_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)
    email = Column(String(100))
    is_reconcilable = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CashBank(Base):
    __tablename__ = 'cash_bank'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    type = Column(String(20), nullable=False)  # Cash, Bank, Wallet
    account_name = Column(String(100))  # For Cash & Bank
    bank_name = Column(String(100))     # For Bank
    account_number = Column(String(50))  # For Bank
    wallet_name = Column(String(50))   # For Wallet
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
    invoice_number = Column(String(50), nullable=False, unique=True)
    invoice_date = Column(Date, nullable=False)
    transaction_date = Column(Date, nullable=False, default=date.today)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    service_type = Column(String(50), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), nullable=False, default='LKR')
    status = Column(String(20), default='Draft')
    destination = Column(String(10))
    due_term = Column(Integer, default=0)
    created_by_user = relationship(
        "TenantUser",
        primaryjoin="Invoice.created_by==TenantUser.id",
        foreign_keys="Invoice.created_by",
        viewonly=True,)
    staff_id = Column(Integer, ForeignKey('users.id'))  # ✅ FIXED
    staff = relationship("TenantUser", backref="invoices")  # ✅ FIXED
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    pax_details = relationship("PaxDetail", back_populates="invoice", cascade="all, delete-orphan")
    journal_lines = relationship(
        "JournalLine",
        primaryjoin="foreign(JournalLine.partner_id)==Invoice.customer_id",
        viewonly=True
)

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
    service_date = Column(Date, nullable=False)

    pnr = Column(String(50))   
    designator = Column(String(20))   
    ticket_no = Column(String(50))   

    supplier_id = Column(Integer, ForeignKey('suppliers.id'))
    supplier = relationship("Supplier")

    purchase_number = Column(String(50))  
    income_account_id = Column(Integer, ForeignKey('accounts.id'))   
    expense_account_id = Column(Integer, ForeignKey('accounts.id'))
    invoice = relationship("Invoice", back_populates="lines")

    created_at = Column(DateTime, default=datetime.utcnow)
    is_reconciled = Column(Boolean, default=False)


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

class Receipt(Base):
    __tablename__ = "receipts"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    receipt_date = Column(Date)
    payment_method = Column(String(50))
    reference = Column(String(100))
    notes = Column(Text)
    total_amount = Column(Numeric(12, 2))
    account_id = Column(Integer, ForeignKey("accounts.id"))  # deposit to
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"))

    customer = relationship("Customer")
    journal_entry = relationship("JournalEntry")


class SupplierReconciliation(Base):
    __tablename__ = 'supplier_reconciliations'

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    recon_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)  # total cost of selected lines
    statement_amount = Column(Numeric(12, 2), nullable=False)
    reference = Column(String(100))  # invoice/statement number
    notes = Column(Text)
    status = Column(String(20), default='Saved')

    supplier = relationship('Supplier')
    lines = relationship('SupplierReconciliationLine', back_populates='reconciliation', cascade='all, delete-orphan')
    payment_due = relationship('SupplierPaymentDue', uselist=False, back_populates='reconciliation')

    @property
    def rc_number(self) -> str:
        """Return the reconciliation number like RC0001."""
        if self.id is None:
            return None
        return f"RC{self.id:04d}"


class SupplierReconciliationLine(Base):
    __tablename__ = 'supplier_reconciliation_lines'

    id = Column(Integer, primary_key=True)
    reconciliation_id = Column(Integer, ForeignKey('supplier_reconciliations.id'), nullable=False)
    invoice_line_id = Column(Integer, ForeignKey('invoice_lines.id'), nullable=False)
    # amount payable to the supplier for this line item
    supplier_amount = Column('amount', Numeric(12, 2), nullable=False)
    reconciliation = relationship('SupplierReconciliation', back_populates='lines')
    invoice_line = relationship('InvoiceLine')


class SupplierPaymentDue(Base):
    __tablename__ = 'supplier_payment_dues'

    id = Column(Integer, primary_key=True)
    reconciliation_id = Column(Integer, ForeignKey('supplier_reconciliations.id'), nullable=False)
    reference = Column(String(100))
    amount = Column(Numeric(12, 2), nullable=False)

    reconciliation = relationship('SupplierReconciliation', back_populates='payment_due')


class Expense(Base):
    __tablename__ = 'expenses'

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    company_id = Column(Integer, nullable=False)
    expense_date = Column(Date, nullable=False)
    description = Column(String(255))
    amount = Column(Numeric(12, 2), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'))
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id'))

    supplier = relationship('Supplier')
    account = relationship('Account')
    journal_entry = relationship('JournalEntry')


class SupplierPayment(Base):
    __tablename__ = 'supplier_payments'

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.id'), nullable=False)
    company_id = Column(Integer, nullable=False)
    payment_date = Column(Date, nullable=False)
    payment_method = Column(String(50))
    reference = Column(String(100))
    notes = Column(Text)
    total_amount = Column(Numeric(12, 2))
    account_id = Column(Integer, ForeignKey('accounts.id'))  # paid from
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id'))

    supplier = relationship('Supplier')
    journal_entry = relationship('JournalEntry')


class BankTransfer(Base):
    __tablename__ = 'bank_transfers'

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, nullable=False)
    transfer_date = Column(Date, nullable=False)
    from_cashbank_id = Column(Integer, ForeignKey('cash_bank.id'), nullable=False)
    to_cashbank_id = Column(Integer, ForeignKey('cash_bank.id'), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    reference = Column(String(100))
    narration = Column(String(255))
    journal_entry_id = Column(Integer, ForeignKey('journal_entries.id'))

    from_cashbank = relationship('CashBank', foreign_keys=[from_cashbank_id])
    to_cashbank = relationship('CashBank', foreign_keys=[to_cashbank_id])
    journal_entry = relationship('JournalEntry')

