from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response, render_template_string, Response
from datetime import datetime, date
from app.models.models import (
    FiscalYear,
    Account,
    AccountType,
    CompanyProfile,
    JournalEntry,
    JournalLine,
    Customer,
    Supplier,
    CashBank,
    Invoice,
    InvoiceLine,
    PaxDetail,
    TenantUser,
    Receipt,
    SupplierReconciliation,
    SupplierReconciliationLine,
    SupplierPaymentDue,
    Expense,
    SupplierPayment,
)
from app.routes.register_routes import current_tenant_session
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload
from math import ceil
from io import BytesIO
from xhtml2pdf import pisa
from markupsafe import Markup
import pandas as pd
from sqlalchemy.orm import scoped_session
import phonenumbers
from phonenumbers import parse, is_valid_number, format_number, PhoneNumberFormat, NumberParseException
from sqlalchemy.exc import SQLAlchemyError
from decimal import Decimal
from app.utils.currency_utils import get_company_currency
import uuid

from app.utils.email_utils import send_email
from app import mail



accounting_routes = Blueprint('accounting_routes', __name__)



@accounting_routes.route('/fiscal-years', methods=['GET', 'POST'])
def manage_fiscal_years():
    if 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    if request.method == 'POST':
        if 'set_active' in request.form:
            # Handle activation form
            selected_id = request.form.get('active_fiscal_id')
            if selected_id:
                # Set all to inactive first
                tenant_session.query(FiscalYear).filter_by(company_id=company_id).update({FiscalYear.is_closed: False})
                # Set selected to active
                tenant_session.query(FiscalYear).filter_by(company_id=company_id, id=selected_id).update({FiscalYear.is_closed: True})
                tenant_session.commit()
                flash("✅ Fiscal year updated successfully.", "success")
            else:
                flash("❌ Please select a fiscal year to activate.", "danger")

        elif request.form.get("action") == "add":
            # Handle add new fiscal year
            name = request.form['name']
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')

            fiscal = FiscalYear(
                company_id=company_id,
                name=name,
                year_name=name,
                start_date=start_date,
                end_date=end_date,
                is_closed=False  # default new fiscal years as inactive
            )
            tenant_session.add(fiscal)
            tenant_session.commit()
            flash("✅ Fiscal year created successfully.", "success")

        return redirect(url_for('accounting_routes.manage_fiscal_years'))

    fiscal_years = tenant_session.query(FiscalYear).filter_by(company_id=company_id).order_by(FiscalYear.start_date.desc()).all()
    return render_template('accounting/fiscal_years.html', fiscal_years=fiscal_years)




def build_account_type_tree(account_types):
    tree = []
    lookup = {atype.id: {"node": atype, "children": []} for atype in account_types}
    root_ids = []

    for atype in account_types:
        if atype.parent_id:
            lookup[atype.parent_id]["children"].append(lookup[atype.id])
        else:
            root_ids.append(atype.id)

    for rid in root_ids:
        tree.append(lookup[rid])
    return tree


@accounting_routes.route('/chart-of-accounts', methods=['GET', 'POST'])
def chart_of_accounts():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    # Handle form submission to create a new account
    if request.method == 'POST':
        account_type = request.form['account_type']
        account_code = request.form['account_code']
        account_name = request.form['account_name']
        is_reconcilable = 'is_reconcilable' in request.form
        

        # 🔒 Check for duplicate account_code in the same company
        existing = tenant_session.query(Account).filter_by(
            company_id=company_id,
            account_code=account_code
        ).first()

        if existing:
            flash("❌ Account code already exists. Please use a unique code.", "danger")
            return redirect(url_for('accounting_routes.chart_of_accounts'))

        # ✅ If no duplicate, insert new account
        account = Account(
            company_id=company_id,
            account_type=account_type,
            account_code=account_code,
            account_name=account_name,
            is_reconcilable=is_reconcilable,
            created_by=session['user_id']
        )
        tenant_session.add(account)
        tenant_session.commit()
        flash("✅ Account added successfully", "success")
        return redirect(url_for('accounting_routes.chart_of_accounts'))

    # Retrieve company profile
    company = tenant_session.query(CompanyProfile).filter_by(company_id=company_id).first()
    if not company:
        flash("❌ Company profile not found. Please complete company setup first.", "danger")
        return redirect(url_for('register_routes.profile_settings'))

    # Seed account types if not initialized
    if not company.account_types_initialized:
        seed_default_account_types(tenant_session, company_id)
    
    # Fetch all account types (including headers)
    all_account_types = tenant_session.query(AccountType)\
        .filter_by(company_id=company_id)\
        .order_by(AccountType.parent_id, AccountType.name).all()

    # Split into selectable and non-selectable (headers)
    selectable_types = [t for t in all_account_types if not t.is_header]
    accounts = tenant_session.query(Account).filter_by(company_id=company_id).all()

    
    account_types_raw = tenant_session.query(AccountType)\
        .filter_by(company_id=company_id).order_by(AccountType.sort_order).all()
    account_types_tree = build_account_type_tree(account_types_raw)

    return render_template(
        'accounting/chart_of_accounts.html',
        accounts=accounts,
        account_types_tree=account_types_tree
    )


def seed_default_account_types(session, company_id):
    default_data = [
        {"name": "Balance Sheet", "is_header": True},
        {"name": "Assets", "parent": "Balance Sheet"},
        {"name": "Receivable", "parent": "Assets"},
        {"name": "Bank, Cash & Wallets", "parent": "Assets"},
        {"name": "Current Assets", "parent": "Assets"},
        {"name": "Non Current Assets", "parent": "Assets"},
        {"name": "Pre Payments", "parent": "Assets"},
        {"name": "Fixed Assets", "parent": "Assets"},
        {"name": "Liability", "parent": "Balance Sheet"},
        {"name": "Payable", "parent": "Liability"},
        {"name": "Credit Card", "parent": "Liability"},
        {"name": "Current Liability", "parent": "Liability"},
        {"name": "Non Current Liability", "parent": "Liability"},
        {"name": "Equity", "parent": "Balance Sheet"},
        {"name": "Equity", "parent": "Equity"},
        {"name": "Current Year Profit", "parent": "Equity"},
        {"name": "Profit & Loss", "is_header": True},
        {"name": "Income", "parent": "Profit & Loss"},
        {"name": "Other Income", "parent": "Income"},
        {"name": "Expenses", "parent": "Profit & Loss"},
        {"name": "Other Expenses", "parent": "Expenses"},
        {"name": "Depreciation", "parent": "Expenses"},
        {"name": "Cost of Sales", "parent": "Expenses"},
    ]

    created = {}

    for index, item in enumerate(default_data, start=1):
        parent_obj = created.get(item.get("parent"))
        acct_type = AccountType(
            company_id=company_id,
            name=item["name"],
            is_header=item.get("is_header", False),
            parent_id=parent_obj.id if parent_obj else None,
            sort_order=index  # Set order explicitly
        )
        session.add(acct_type)
        session.flush()  # Ensures .id is available for children
        created[item["name"]] = acct_type

    company = session.query(CompanyProfile).filter_by(company_id=company_id).first()
    company.account_types_initialized = True
    session.commit()

def get_account_type_hierarchy(session, company_id):
    all_types = session.query(AccountType).filter_by(company_id=company_id).order_by(AccountType.sort_order).all()
    tree = []

    def build_branch(parent, level):
        for node in [x for x in all_types if x.parent_id == (parent.id if parent else None)]:
            node.level = level
            tree.append(node)
            build_branch(node, level + 1)

    build_branch(None, 0)
    return tree

@accounting_routes.route('/account/view/<int:account_id>', methods=['GET', 'POST'])
def view_account(account_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session['user_id']

    account = tenant_session.query(Account).filter_by(id=account_id, company_id=company_id).first()
    if not account:
        flash("❌ Account not found", "danger")
        return redirect(url_for('accounting_routes.chart_of_accounts'))

    # Calculate balance
    balance = 0
    for line in account.journal_lines:
        balance += (line.debit or 0) - (line.credit or 0)

    if request.method == 'POST':
        amount = float(request.form['opening_balance'])
        side = request.form['side']
        if amount <= 0:
            flash("❌ Amount must be greater than zero.", "danger")
            return redirect(request.url)

        # Get or create Opening Balance Suspense account
        suspense = tenant_session.query(Account).filter_by(
            company_id=company_id,
            account_name='Opening Balance Suspense'
        ).first()

        if not suspense:
            suspense = Account(
                company_id=company_id,
                account_type='Equity',
                account_code='9999',
                account_name='Opening Balance Suspense',
                is_active=True,
                is_reconcilable=False,
                created_by=user_id
            )
            tenant_session.add(suspense)
            tenant_session.flush()

        # Create a journal entry
        fiscal_year = tenant_session.query(FiscalYear).filter_by(company_id=company_id, is_closed=True).first()
        if not fiscal_year:
            flash("⚠️ No active fiscal year.", "warning")
            return redirect(request.url)

        journal = JournalEntry(
            company_id=company_id,
            date=datetime.today().date(),
            reference="OPENING_BALANCE",
            narration=f"Opening Balance for {account.account_name}",
            created_by=user_id,
            fiscal_year_id=fiscal_year.id
        )
        tenant_session.add(journal)
        tenant_session.flush()

        # Post lines: one for the account, one for the suspense
        if side == "debit":
            lines = [
                JournalLine(entry_id=journal.id, account_id=account.id, debit=amount, credit=0, narration="Opening"),
                JournalLine(entry_id=journal.id, account_id=suspense.id, debit=0, credit=amount, narration="Opening")
            ]
        else:
            lines = [
                JournalLine(entry_id=journal.id, account_id=account.id, debit=0, credit=amount, narration="Opening"),
                JournalLine(entry_id=journal.id, account_id=suspense.id, debit=amount, credit=0, narration="Opening")
            ]
        tenant_session.add_all(lines)
        tenant_session.commit()

        flash("✅ Opening balance posted.", "success")
        return redirect(request.url)

    return render_template('accounting/account_view.html', account=account, account_balance=balance)



@accounting_routes.route('/accounts/<int:account_id>/edit', methods=['GET', 'POST'])
def edit_account(account_id):
    tenant_session = current_tenant_session()
    account = tenant_session.query(Account).get(account_id)

    if not account:
        flash("❌ Account not found", "danger")
        return redirect(url_for('accounting_routes.chart_of_accounts'))

    account_types = tenant_session.query(AccountType).filter_by(company_id=account.company_id).all()
    account_types = sorted(account_types, key=lambda at: (not at.is_header, at.name.lower()))

    if request.method == 'POST':
        account.account_type = request.form['account_type']
        account.account_code = request.form['account_code']
        account.account_name = request.form['account_name']
        account.is_reconcilable = 'is_reconcilable' in request.form

        tenant_session.commit()
        flash("✅ Account updated successfully", "success")
        return redirect(url_for('accounting_routes.chart_of_accounts'))

    return render_template('accounting/account_edit.html', account=account, account_types=account_types)

@accounting_routes.route('/chart-of-accounts/<int:account_id>/toggle-status', methods=['GET'])
def toggle_account_status(account_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    account = tenant_session.query(Account).filter_by(id=account_id, company_id=company_id).first()
    if not account:
        flash("❌ Account not found", "danger")
        return redirect(url_for('accounting_routes.chart_of_accounts'))

    account.is_active = not account.is_active
    tenant_session.commit()

    flash(f"✅ Account {'enabled' if account.is_active else 'disabled'} successfully.", "success")
    return redirect(url_for('accounting_routes.view_account', account_id=account.id))


def generate_journal_reference(session, company_id):
    last_entry = (
        session.query(JournalEntry)
        .filter_by(company_id=company_id)
        .order_by(JournalEntry.id.desc())
        .first()
    )

    if last_entry and last_entry.reference and last_entry.reference.startswith("JO"):
        try:
            number = int(last_entry.reference[2:]) + 1
        except ValueError:
            number = 1
    else:
        number = 1

    return f"JO{number:06d}"


def generate_allocation_reference(session):
    """Return next allocation reference like CA0001."""
    last_entry = (
        session.query(JournalEntry)
        .filter(JournalEntry.reference.like("CA%"))
        .order_by(JournalEntry.id.desc())
        .first()
    )

    if last_entry and last_entry.reference[2:].isdigit():
        next_num = int(last_entry.reference[2:]) + 1
    else:
        next_num = 1

    return f"CA{next_num:04d}"


@accounting_routes.route('/journal-entry', methods=['GET', 'POST'])
def journal_entry():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session['user_id']

    accounts = tenant_session.query(Account).filter_by(company_id=company_id, is_active=True).all()
    fiscal_year = tenant_session.query(FiscalYear).filter(
        FiscalYear.company_id == company_id,
        FiscalYear.is_closed == True
    ).first()

    if not fiscal_year:
        flash("⚠️ Active fiscal year not found. Please configure it before journal entries.", "danger")
        return redirect(url_for('accounting_routes.chart_of_accounts'))

    if request.method == 'POST':
        date_str = request.form.get('date')
        ref = request.form.get('reference', '').strip()
        if not ref:
            ref = generate_journal_reference(tenant_session, company_id)
        narration = request.form.get('narration', '').strip()
        account_ids = request.form.getlist('account_id[]')
        debits = request.form.getlist('debit[]')
        credits = request.form.getlist('credit[]')
        line_narrations = request.form.getlist('line_narration[]')

        print("account_ids:", account_ids)
        print("debits:", debits)
        print("credits:", credits)
        print("line_narrations:", line_narrations)

        # Only keep rows where account and either debit or credit are provided (not both zero or blank)
        valid_rows = []
        total_debit = 0.0
        total_credit = 0.0
        row_count = len(account_ids)

        for idx in range(row_count):
            acc_id = (account_ids[idx] or "").strip()
            debit_raw = (debits[idx] if idx < len(debits) else "").strip()
            credit_raw = (credits[idx] if idx < len(credits) else "").strip()
            narr = (line_narrations[idx] if idx < len(line_narrations) else "").strip()
            try:
                debit = float(debit_raw or 0)
            except (ValueError, TypeError):
                debit = 0.0
            try:
                credit = float(credit_raw or 0)
            except (ValueError, TypeError):
                credit = 0.0
            narr = (narr or '').strip()

            if not acc_id or (debit == 0.0 and credit == 0.0):
                continue  # skip rows with no account or both zero

            valid_rows.append({
                "account_id": acc_id,
                "debit": debit,
                "credit": credit,
                "narration": narr
            })
            total_debit += debit
            total_credit += credit

        print("VALID ROWS:", valid_rows)
        print("Total debit:", total_debit)
        print("Total credit:", total_credit)

        # for form refill on error
        form_data = {
            "date": date_str,
            "reference": ref,
            "narration": narration,
            "account_id": [row["account_id"] for row in valid_rows] or [""],
            "debit": [str(row["debit"]) for row in valid_rows] or [""],
            "credit": [str(row["credit"]) for row in valid_rows] or [""],
            "line_narration": [row["narration"] for row in valid_rows] or [""],
        }

        # Date validation
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash("❌ Invalid date format.", "danger")
            return render_template("accounting/journal_entry.html", accounts=accounts, fiscal_year=fiscal_year, form_data=form_data)

        if not (fiscal_year.start_date <= date <= fiscal_year.end_date):
            flash("❌ Date not within active fiscal year.", "danger")
            return render_template("accounting/journal_entry.html", accounts=accounts, fiscal_year=fiscal_year, form_data=form_data)

        if not valid_rows:
            flash("❌ No valid journal lines found.", "danger")
            return render_template("accounting/journal_entry.html", accounts=accounts, fiscal_year=fiscal_year, form_data=form_data)

        # Use round to avoid floating point errors (1.1+2.2 != 3.3 due to float)
        if round(total_debit, 2) != round(total_credit, 2):
            flash("❌ Debit and Credit must balance.", "danger")
            return render_template("accounting/journal_entry.html", accounts=accounts, fiscal_year=fiscal_year, form_data=form_data)

        # Create entry and lines
        new_entry = JournalEntry(
            company_id=company_id,
            date=date,
            reference=ref,
            narration=narration,
            created_by=user_id,
            fiscal_year_id=fiscal_year.id
        )
        tenant_session.add(new_entry)
        tenant_session.flush()

        lines = []
        for row in valid_rows:
            line = JournalLine(
                entry_id=new_entry.id,
                account_id=row["account_id"],
                debit=row["debit"],
                credit=row["credit"],
                narration=row["narration"]
            )
            lines.append(line)

        

        tenant_session.add_all(lines)
        tenant_session.commit()

        flash("✅ Journal Entry saved successfully.", "success")
        return redirect(url_for('accounting_routes.journal_entry'))

    # GET method
    empty_form = {
        "date": datetime.today().strftime('%Y-%m-%d'),
        "reference": generate_journal_reference(tenant_session, company_id),
        "narration": "",
        "account_id": [""],
        "debit": [""],
        "credit": [""],
        "line_narration": [""]
    }

    return render_template("accounting/journal_entry.html", accounts=accounts, fiscal_year=fiscal_year, form_data=empty_form)




@accounting_routes.route('/journal-list', methods=['GET'])
def journal_list():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    
    # Pagination params
    page = int(request.args.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page

    # Base query
    query = tenant_session.query(JournalEntry).options(
        joinedload(JournalEntry.lines).joinedload(JournalLine.account)
    ).filter(JournalEntry.company_id == company_id)

    # Filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search', '')

    if start_date:
        query = query.filter(JournalEntry.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(JournalEntry.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if search:
        query = query.filter(
            or_(
                JournalEntry.reference.ilike(f"%{search}%"),
                JournalEntry.narration.ilike(f"%{search}%")
            )
        )

    total_entries = query.count()
    total_pages = ceil(total_entries / per_page)

    journal_entries = query.order_by(JournalEntry.id.desc()).offset(offset).limit(per_page).all()

    # Prepare query params without page for pagination links
    query_params = request.args.to_dict(flat=True)
    query_params.pop('page', None)

    return render_template(
        "accounting/journal_list.html",
        journal_entries=journal_entries,
        page=page,
        total_pages=total_pages,
        total_entries=total_entries,
        per_page=per_page,
        query_params=query_params
    )


@accounting_routes.route('/journal/reverse/<int:entry_id>', methods=['POST'])
def reverse_journal_entry(entry_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session['user_id']

    original_entry = tenant_session.query(JournalEntry).filter_by(id=entry_id, company_id=company_id).first()
    if not original_entry:
        flash("❌ Journal entry not found.", "danger")
        return redirect(url_for('accounting_routes.journal_list'))

    fiscal_year = tenant_session.query(FiscalYear).filter(
        FiscalYear.company_id == company_id,
        FiscalYear.is_closed == True
    ).first()

    if not fiscal_year:
        flash("⚠️ Active fiscal year not found.", "danger")
        return redirect(url_for('accounting_routes.journal_list'))

    # Validation: Cannot reverse a reversal or reverse twice
    if original_entry.reversal_of:
        flash("❌ This journal entry is already a reversal.", "danger")
        return redirect(url_for('accounting_routes.journal_list'))

    if original_entry.reversed_by:
        flash("⚠️ This journal entry has already been reversed.", "warning")
        return redirect(url_for('accounting_routes.journal_list'))

    # Create reversal journal entry
    reverse_entry = JournalEntry(
        company_id=company_id,
        date=datetime.today().date(),
        reference=f"REV-{original_entry.reference}",
        narration=f"Reversal of Entry #{original_entry.id}",
        created_by=user_id,
        fiscal_year_id=fiscal_year.id
    )
    tenant_session.add(reverse_entry)
    tenant_session.flush()  # Get reverse_entry.id before linking

    # Link the original entry to the reversal
    original_entry.reversed_entry_id = reverse_entry.id

    # Reverse each journal line
    for line in original_entry.lines:
        reversed_line = JournalLine(
            entry_id=reverse_entry.id,
            account_id=line.account_id,
            debit=line.credit,
            credit=line.debit,
            narration=f"Reversal: {line.narration}",
            partner_id=line.partner_id
        )
        tenant_session.add(reversed_line)

    tenant_session.commit()
    flash(f"✅ Entry #{entry_id} reversed successfully.", "success")
    return redirect(url_for('accounting_routes.journal_list'))

@accounting_routes.route('/export/journals/pdf', methods=['GET'])
def export_journals_pdf():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    entries = (
        tenant_session.query(JournalEntry)
        .options(joinedload(JournalEntry.lines).joinedload(JournalLine.account))
        .filter(JournalEntry.company_id == company_id)
        .order_by(JournalEntry.date.desc())
        .all()
    )

    html = render_template_string("""
    <h2>Journal Entries</h2>
    <table border="1" cellspacing="0" cellpadding="5">
      <thead>
        <tr>
          <th>Date</th>
          <th>Reference</th>
          <th>Narration</th>
          <th>Account</th>
          <th>Debit</th>
          <th>Credit</th>
        </tr>
      </thead>
      <tbody>
        {% for entry in entries %}
          {% for line in entry.lines %}
          <tr>
            <td>{{ entry.date.strftime('%Y-%m-%d') }}</td>
            <td>{{ entry.reference }}</td>
            <td>{{ entry.narration }}</td>
            <td>{{ line.account.account_code }} - {{ line.account.account_name }}</td>
            <td>{{ line.debit or 0 }}</td>
            <td>{{ line.credit or 0 }}</td>
          </tr>
          {% endfor %}
        {% endfor %}
      </tbody>
    </table>
    """, entries=entries)

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)

    if pisa_status.err:
        return "PDF generation error", 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=journal_entries.pdf'
    return response


@accounting_routes.route('/trial-balance', methods=['GET'])
def trial_balance():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    fiscal_years = tenant_session.query(FiscalYear)\
        .filter_by(company_id=company_id)\
        .order_by(FiscalYear.start_date.desc())\
        .all()

    selected_fiscal_year_id = request.args.get('fiscal_year_id', type=int)
    trial_data = []
    total_debit = 0.0
    total_credit = 0.0

    if selected_fiscal_year_id:
        fiscal_year = tenant_session.query(FiscalYear)\
            .filter_by(id=selected_fiscal_year_id, company_id=company_id)\
            .first()

        if not fiscal_year:
            flash("❌ Invalid fiscal year selected", "danger")
            return redirect(url_for('accounting_routes.trial_balance'))

        accounts = tenant_session.query(Account)\
            .filter_by(company_id=company_id)\
            .options(joinedload(Account.journal_lines).joinedload(JournalLine.entry))\
            .all()

        for acc in accounts:
            debit_sum = 0
            credit_sum = 0
            for line in acc.journal_lines:
                if line.entry and line.entry.fiscal_year_id == fiscal_year.id:
                    debit_sum += line.debit or 0
                    credit_sum += line.credit or 0

            if debit_sum != 0 or credit_sum != 0:
                trial_data.append({
                    "code": acc.account_code,
                    "name": acc.account_name,
                    "debit": round(debit_sum, 2),
                    "credit": round(credit_sum, 2)
                })
                total_debit += debit_sum
                total_credit += credit_sum

    return render_template("accounting/trial_balance.html",
        fiscal_years=fiscal_years,
        selected_fiscal_year_id=selected_fiscal_year_id,
        trial_data=trial_data,
        total_debit=round(total_debit, 2),
        total_credit=round(total_credit, 2)
    )

@accounting_routes.route('/trial-balance/export/excel', methods=['GET'])
def export_trial_balance_excel():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    fiscal_year_id = request.args.get('fiscal_year_id', type=int)

    fiscal_year = tenant_session.query(FiscalYear).filter_by(id=fiscal_year_id, company_id=company_id).first()
    if not fiscal_year:
        flash("❌ Invalid fiscal year", "danger")
        return redirect(url_for('accounting_routes.trial_balance'))

    accounts = tenant_session.query(Account)\
        .filter_by(company_id=company_id)\
        .options(joinedload(Account.journal_lines).joinedload(JournalLine.entry))\
        .all()

    rows = []
    total_debit = 0.0
    total_credit = 0.0

    for acc in accounts:
        debit = credit = 0.0
        for line in acc.journal_lines:
            if line.entry and line.entry.fiscal_year_id == fiscal_year.id:
                debit += line.debit or 0
                credit += line.credit or 0

        if debit != 0 or credit != 0:
            rows.append({
                "Account Code": acc.account_code,
                "Account Name": acc.account_name,
                "Debit": round(debit, 2),
                "Credit": round(credit, 2)
            })
            total_debit += debit
            total_credit += credit

    # Append total row
    rows.append({
        "Account Code": "",
        "Account Name": "Total",
        "Debit": round(total_debit, 2),
        "Credit": round(total_credit, 2)
    })

    df = pd.DataFrame(rows)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    response = make_response(output.read())
    response.headers['Content-Disposition'] = f'attachment; filename=trial_balance_{fiscal_year.name}.xlsx'
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return response


@accounting_routes.route('/export/trial-balance/pdf', methods=['GET'])
def export_trial_balance_pdf():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    fiscal_year_id = request.args.get("fiscal_year_id", type=int)

    accounts = tenant_session.query(Account)\
        .filter_by(company_id=company_id, is_active=True)\
        .options(joinedload(Account.journal_lines).joinedload(JournalLine.entry))\
        .all()

    trial_data = []
    total_debit = 0.0
    total_credit = 0.0

    for acc in accounts:
        debit = credit = 0.0
        for line in acc.journal_lines:
            if line.entry and line.entry.fiscal_year_id == fiscal_year_id:
                debit += line.debit or 0
                credit += line.credit or 0

        if debit != 0 or credit != 0:
            trial_data.append({
                'code': acc.account_code,
                'name': acc.account_name,
                'debit': round(debit, 2),
                'credit': round(credit, 2)
            })
            total_debit += debit
            total_credit += credit

    html = render_template_string("""
    <h2 style="text-align:center;">Trial Balance Report</h2>
    <table border="1" cellspacing="0" cellpadding="5" width="100%">
      <thead>
        <tr>
          <th>Account Code</th>
          <th>Account Name</th>
          <th>Debit</th>
          <th>Credit</th>
        </tr>
      </thead>
      <tbody>
        {% for row in trial_data %}
        <tr>
          <td>{{ row.code }}</td>
          <td>{{ row.name }}</td>
          <td style="text-align:right;">{{ "%.2f"|format(row.debit) }}</td>
          <td style="text-align:right;">{{ "%.2f"|format(row.credit) }}</td>
        </tr>
        {% endfor %}
        <tr style="font-weight:bold; background-color:#eee;">
          <td></td>
          <td>Total</td>
          <td style="text-align:right;">{{ "%.2f"|format(total_debit) }}</td>
          <td style="text-align:right;">{{ "%.2f"|format(total_credit) }}</td>
        </tr>
      </tbody>
    </table>
    """, trial_data=trial_data, total_debit=total_debit, total_credit=total_credit)

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    if pisa_status.err:
        return "❌ PDF generation error", 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=trial_balance.pdf'
    return response



@accounting_routes.route('/financial-reports')
def financial_reports():
    return render_template('accounting/financial_reports.html')


@accounting_routes.route('/customer-outstanding', methods=['GET'])
def customer_outstanding():
    """Standard customer outstanding report with optional filters."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    customers = tenant_session.query(Customer).filter_by(company_id=company_id).all()

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    customer_id = request.args.get('customer_id', type=int)
    service_type = request.args.get('service_type')

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = None

    report_rows = []
    for cust in customers:
        if customer_id and cust.id != customer_id:
            continue
        dues = get_customer_dues(
            tenant_session,
            company_id,
            cust,
            start_date=start_date,
            end_date=end_date,
            service_type=service_type,
        )
        for inv in dues:
            report_rows.append({
                'customer_name': cust.full_name or cust.business_name,
                'invoice_number': inv.invoice_number,
                'invoice_date': inv.invoice_date,
                'service_type': getattr(inv, 'service_type', ''),
                'total_amount': inv.total_amount,
                'amount_paid': getattr(inv, 'amount_paid', 0),
                'balance_due': getattr(inv, 'balance_due', 0),
            })

    return render_template(
        'accounting/customer_outstanding.html',
        customers=customers,
        report_rows=report_rows,
        selected_customer_id=customer_id,
        start_date=start_date_str or '',
        end_date=end_date_str or '',
        service_type=service_type or ''
    )


@accounting_routes.route('/journal-report', methods=['GET'])
def journal_report():
    """List invoice purchase lines with optional date filters."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    query = (
        tenant_session.query(InvoiceLine)
        .join(Invoice)
        .filter(Invoice.company_id == company_id)
    )

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(InvoiceLine.service_date >= start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(InvoiceLine.service_date <= end_date)
        except ValueError:
            pass

    lines = (
        query.options(
            joinedload(InvoiceLine.invoice),
            joinedload(InvoiceLine.supplier),
            joinedload(InvoiceLine.pax)
        )
        .order_by(InvoiceLine.service_date.desc(), InvoiceLine.id.desc())
        .all()
    )

    return render_template(
        'accounting/journal_report.html',
        lines=lines,
        start_date=start_date_str or '',
        end_date=end_date_str or ''
    )


@accounting_routes.route('/customers', methods=['GET', 'POST'])
def customer_list():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    if request.method == 'POST':
        customer_type = request.form.get('customer_type')
        title = request.form.get('title')
        full_name = request.form.get('full_name')
        business_name = request.form.get('business_name')
        raw_phone = request.form.get('phone')

        # --- Phone Number Parsing/Validation ---
        try:
            phone_obj = phonenumbers.parse(raw_phone, "LK")  # Default region if not present
            if not phonenumbers.is_valid_number(phone_obj):
                flash("❌ Invalid phone number format.", "danger")
                return redirect(url_for('accounting_routes.customer_list'))
            formatted_phone = phonenumbers.format_number(phone_obj, phonenumbers.PhoneNumberFormat.E164)
        except NumberParseException:
            flash("❌ Could not parse phone number.", "danger")
            return redirect(url_for('accounting_routes.customer_list'))

        # --- Duplicate Phone Check ---
        existing = tenant_session.query(Customer).filter_by(
            company_id=session['company_id'],
            phone_number=formatted_phone
        ).first()
        if existing:
            flash("❌ This phone number is already registered.", "danger")
            return redirect(url_for('accounting_routes.customer_list'))

        # --- Get or Create Account Receivable Control ---
        company_id = session['company_id']
        user_id = session.get('user_id')

        control_account = tenant_session.query(Account).filter(
            Account.company_id == company_id,
            Account.account_type.ilike("Receivable"),
            Account.account_code == "1000",
            Account.account_name.ilike("Account Receivable Control%")
        ).first()
        if not control_account:
            control_account = Account(
                company_id=company_id,
                account_type="Receivable",
                account_code="1000",
                account_name="Account Receivable Control",
                created_by=user_id
            )
            tenant_session.add(control_account)
            tenant_session.flush()  # To get id before commit
            tenant_session.commit()  # Now control_account.id is set

        if not control_account or not control_account.id:
            flash("❌ Failed to create or fetch Account Receivable Control account.", "danger")
            return redirect(url_for('accounting_routes.customer_list'))

        # --- Create the Customer (with AR control account linked) ---
        new_customer = Customer(
            company_id=company_id,
            customer_type=customer_type,
            title=title if customer_type == 'Customer' else None,
            full_name=full_name if customer_type == 'Customer' else None,
            business_name=business_name if customer_type in ['Agent', 'Corporate'] else None,
            phone_number=formatted_phone,
            account_receivable_id=control_account.id,
            created_by=user_id
        )

        tenant_session.add(new_customer)
        tenant_session.commit()
        flash("✅ Customer created and linked to Account Receivable Control", "success")
        return redirect(url_for('accounting_routes.customer_list'))

    customers = tenant_session.query(Customer).order_by(Customer.created_at.desc()).all()
    return render_template('accounting/customer_list.html', customers=customers)





@accounting_routes.route('/customers/view/<int:customer_id>')
def view_customer(customer_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    customer = tenant_session.query(Customer).filter_by(id=customer_id).first()
    if not customer:
        flash("❌ Customer not found", "danger")
        return redirect(url_for('accounting_routes.customer_list'))

    # ✅ Calculate balance using Account Receivable Control + Partner ID
    from sqlalchemy import func

    balance = tenant_session.query(
        func.sum(JournalLine.debit - JournalLine.credit)
    ).filter(
        JournalLine.account_id == customer.account_receivable_id,
        JournalLine.partner_id == customer.id
    ).scalar() or 0.0

    # Unallocated deposit balance
    deposit_balance = get_customer_deposit_balance(
        tenant_session, company_id, customer
    )

    # Customer related transactions
    transactions = (
        tenant_session.query(JournalLine)
        .join(JournalEntry)
        .join(Account)
        .filter(
            JournalEntry.company_id == company_id,
            JournalLine.partner_id == customer.id,
        )
        .order_by(JournalEntry.date.desc(), JournalEntry.id.desc())
        .all()
    )

    return render_template(
        'accounting/customer_view.html',
        customer=customer,
        balance=balance,
        deposit_balance=deposit_balance,
        transactions=transactions,
        current_date=date.today().isoformat(),
        staff_json=[{"email": s.email} for s in tenant_session.query(TenantUser).filter_by(is_suspended=False, company_id=company_id).all()],
    )

@accounting_routes.route('/customers/edit/<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    customer = tenant_session.query(Customer).filter_by(id=customer_id).first()
    if not customer:
        flash("❌ Customer not found", "danger")
        return redirect(url_for('accounting_routes.customer_list'))

    if request.method == 'POST':
        customer_type = request.form.get('customer_type')
        customer.customer_type = customer_type
        customer.title = request.form.get('title') if customer_type == 'Customer' else None
        customer.full_name = request.form.get('full_name') if customer_type == 'Customer' else None
        customer.business_name = request.form.get('business_name') if customer_type in ['Agent', 'Corporate'] else None
        customer.phone_number = request.form.get('phone')

        tenant_session.commit()
        flash("✅ Customer updated successfully", "success")
        return redirect(url_for('accounting_routes.customer_list'))

    return render_template('accounting/customer_edit.html', customer=customer)


def create_default_accounts(tenant_session, company_id, created_by):
    default_accounts = [
        {"account_type": "Equity", "account_code": "9999", "account_name": "Opening Balance Suspense"},
        {"account_type": "Payable", "account_code": "2000", "account_name": "Account Payable Control"},
        {"account_type": "Payable", "account_code": "2010", "account_name": "Unallocated Deposit Balane"},
        {"account_type": "Receivable", "account_code": "1000", "account_name": "Account Receivable Control "},
        {"account_type": "Bank, Cash & Wallets", "account_code": "1100", "account_name": "Bank, Cash & Wallets Control"},
        {"account_type": "Revenue", "account_code": "4000", "account_name": "Sales"},
        {"account_type": "Expense", "account_code": "5000", "account_name": "Purchase"},
    ]

    for acc in default_accounts:
        exists = tenant_session.query(Account).filter_by(
            company_id=company_id,
            account_code=acc["account_code"]
        ).first()

        if not exists:
            new_acc = Account(
                company_id=company_id,
                account_type=acc["account_type"],
                account_code=acc["account_code"],
                account_name=acc["account_name"],
                created_by=created_by
            )
            tenant_session.add(new_acc)
    tenant_session.commit()

@accounting_routes.route('/setup-default-accounts', methods=['POST'])
def setup_default_accounts():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()

    try:
        create_default_accounts(
            tenant_session=tenant_session,
            company_id=session['company_id'],
            created_by=session['user_id']
        )
        flash("✅ Default accounts created successfully.", "success")
    except Exception as e:
        tenant_session.rollback()
        flash(f"❌ Failed to create default accounts: {str(e)}", "danger")

    return redirect(url_for('register_routes.profile_settings'))


def generate_opening_balance_invoice(session, company_id, customer, amount, user_id, fiscal_year, suspense_account):
    today = date.today()
    invoice_number = f"OB-{customer.id}"

    existing = session.query(Invoice).filter_by(
        invoice_number=invoice_number,
        company_id=company_id
    ).first()
    if existing:
        return None  # Skip duplicate creation

    invoice = Invoice(
        company_id=company_id,
        invoice_number=invoice_number,
        invoice_date=today,
        transaction_date=today,
        customer_id=customer.id,
        service_type="Opening Balance",
        total_amount=amount,
        currency="LKR",
        status="Finalised",
        created_by=user_id,
        created_at=datetime.utcnow()
    )
    session.add(invoice)
    session.flush()

    journal = JournalEntry(
        company_id=company_id,
        date=today,
        reference=f"Opening Balance - {customer.full_name or customer.business_name}",
        narration=f"Opening balance for customer ID {customer.id}",
        fiscal_year_id=fiscal_year.id,
        created_by=user_id,
        created_at=datetime.utcnow()
    )
    session.add(journal)
    session.flush()

    session.add_all([
        JournalLine(
            entry_id=journal.id,
            account_id=customer.account_receivable_id,
            debit=amount,
            credit=0,
            narration="Opening Balance Receivable",
            partner_id=customer.id
        ),
        JournalLine(
            entry_id=journal.id,
            account_id=suspense_account.id,
            debit=0,
            credit=amount,
            narration="Opening Balance Suspense"
        )
    ])
    return invoice

@accounting_routes.route('/customers/<int:customer_id>/add-opening-balance', methods=['POST'])
def add_opening_balance(customer_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get("user_id")
    default_currency = get_company_currency(tenant_session, company_id)
    today = date.today()

    try:
        amount = Decimal(request.form.get("opening_balance", "0").strip())
    except:
        amount = Decimal(0)

    if amount <= 0:
        flash("❌ Amount must be greater than zero", "danger")
        return redirect(url_for("accounting_routes.view_customer", customer_id=customer_id))

    customer = tenant_session.query(Customer).filter_by(id=customer_id, company_id=company_id).first()
    if not customer:
        flash("❌ Customer not found", "danger")
        return redirect(url_for("accounting_routes.customer_list"))

    # Ensure customer has a receivable account
    if not customer.account_receivable_id:
        control_account = tenant_session.query(Account).filter_by(
            company_id=company_id,
            account_type="Receivable",
            account_code="1000",
            account_name="Account Receivable Control"
        ).first()
        if not control_account:
            flash("❌ Receivable control account not found", "danger")
            return redirect(url_for("accounting_routes.view_customer", customer_id=customer_id))
        customer.account_receivable_id = control_account.id
        tenant_session.commit()

    # Check if OB journal entry already exists (avoid duplicate)
    existing_journal = tenant_session.query(JournalEntry).join(JournalLine).filter(
        JournalEntry.company_id == company_id,
        JournalLine.account_id == customer.account_receivable_id,
        JournalLine.partner_id == customer.id,
        JournalEntry.reference == f"Opening Balance - {customer.full_name or customer.business_name}"
    ).first()

    if existing_journal:
        flash("⚠️ Opening balance already exists.", "warning")
        return redirect(url_for("accounting_routes.view_customer", customer_id=customer_id))

    # Suspense account
    suspense = tenant_session.query(Account).filter_by(
        company_id=company_id,
        account_code="9999",
        account_name="Opening Balance Suspense"
    ).first()
    if not suspense:
        flash("❌ Opening Balance Suspense account not found", "danger")
        return redirect(url_for("accounting_routes.view_customer", customer_id=customer_id))

    # Fiscal year
    fiscal_year = tenant_session.query(FiscalYear).filter_by(
        company_id=company_id, is_closed=True
    ).first()
    if not fiscal_year:
        flash("❌ Active fiscal year not found", "danger")
        return redirect(url_for("accounting_routes.view_customer", customer_id=customer_id))

    # Create Journal Entry
    journal = JournalEntry(
        company_id=company_id,
        date=today,
        reference=f"Opening Balance - {customer.full_name or customer.business_name}",
        narration=f"Opening balance for customer ID {customer.id}",
        fiscal_year_id=fiscal_year.id,
        created_by=user_id,
        created_at=datetime.utcnow()
    )
    tenant_session.add(journal)
    tenant_session.flush()

    # Add Journal Lines
    tenant_session.add_all([
        JournalLine(
            entry_id=journal.id,
            account_id=customer.account_receivable_id,
            debit=amount,
            credit=0,
            narration="Opening Balance Receivable",
            partner_id=customer.id
        ),
        JournalLine(
            entry_id=journal.id,
            account_id=suspense.id,
            debit=0,
            credit=amount,
            narration="Opening Balance Suspense"
        )
    ])

    tenant_session.commit()
    flash("✅ Opening balance journal posted successfully", "success")
    return redirect(url_for("accounting_routes.view_customer", customer_id=customer_id))






@accounting_routes.route('/customers/<int:customer_id>/toggle-status')
def toggle_customer_status(customer_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    customer = tenant_session.query(Customer).filter_by(id=customer_id).first()

    if not customer:
        flash("❌ Customer not found.", "danger")
        return redirect(url_for('accounting_routes.customer_list'))

    customer.is_active = not customer.is_active
    tenant_session.commit()

    flash(f"✅ Customer {'enabled' if customer.is_active else 'disabled'} successfully.", "success")
    return redirect(url_for('accounting_routes.view_customer', customer_id=customer_id))


@accounting_routes.route('/customers/<int:customer_id>/update-settings', methods=['POST'])
def update_customer_settings(customer_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    customer = tenant_session.query(Customer).filter_by(id=customer_id).first()
    if not customer:
        flash('❌ Customer not found', 'danger')
        return redirect(url_for('accounting_routes.customer_list'))

    customer.email = request.form.get('email')
    customer.address_line_1 = request.form.get('address_line_1')
    customer.address_line_2 = request.form.get('address_line_2')
    customer.city = request.form.get('city')
    customer.country = request.form.get('country')

    try:
        customer.due_term = int(request.form.get('due_term') or 0)
    except ValueError:
        customer.due_term = 0

    try:
        customer.markup = float(request.form.get('markup') or 0)
    except ValueError:
        customer.markup = 0.0

    consultant_email = request.form.get('staff_email')
    if consultant_email:
        staff = tenant_session.query(TenantUser).filter_by(
            email=consultant_email,
            company_id=session['company_id'],
            is_suspended=False
        ).first()
        customer.consultant_id = staff.id if staff else None
    else:
        customer.consultant_id = None

    tenant_session.commit()
    flash('✅ Customer settings updated', 'success')
    return redirect(url_for('accounting_routes.view_customer', customer_id=customer_id))

@accounting_routes.route('/suppliers', methods=['GET', 'POST'])
def supplier_list():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    if request.method == 'POST':
        supplier_type = request.form.get('supplier_type')
        business_name = request.form.get('business_name')
        raw_phone = request.form.get('phone')
        email = request.form.get('email') or None
        is_reconcilable = bool(request.form.get('is_reconcilable'))

        # ✅ Phone validation
        try:
            phone_obj = parse(raw_phone, "LK")
            if not is_valid_number(phone_obj):
                flash("❌ Invalid phone number.", "danger")
                return redirect(url_for('accounting_routes.supplier_list'))
            formatted_phone = format_number(phone_obj, PhoneNumberFormat.E164)
        except NumberParseException:
            flash("❌ Could not parse phone number.", "danger")
            return redirect(url_for('accounting_routes.supplier_list'))

        # ✅ Duplicate check
        existing = tenant_session.query(Supplier).filter_by(
            company_id=company_id,
            phone_number=formatted_phone
        ).first()
        if existing:
            flash("❌ This phone number is already registered.", "danger")
            return redirect(url_for('accounting_routes.supplier_list'))

        # ✅ Get or create payable account
        payable_account = tenant_session.query(Account).filter_by(
            company_id=company_id,
            account_type='Payable',
            account_code='2000',
            account_name='Account Payable Control'
        ).first()

        if not payable_account:
            payable_account = Account(
                company_id=company_id,
                account_type='Payable',
                account_code='2000',
                account_name='Account Payable Control',
                created_by=user_id
            )
            tenant_session.add(payable_account)
            tenant_session.flush()

        # ✅ Create supplier
        new_supplier = Supplier(
            company_id=company_id,
            supplier_type=supplier_type,
            business_name=business_name,
            phone_number=formatted_phone,
            email=email,
            is_reconcilable=is_reconcilable,
            is_active=True,  # ✅ Always default active
            account_payable_id=payable_account.id,
            created_by=user_id
        )
        tenant_session.add(new_supplier)
        tenant_session.flush()

        # ✅ Set supplier_code like SUP0001
        new_supplier.supplier_code = f"SUP{str(new_supplier.id).zfill(4)}"
        tenant_session.commit()

        flash("✅ Supplier created successfully.", "success")
        return redirect(url_for('accounting_routes.supplier_list'))

    # GET request
    suppliers = tenant_session.query(Supplier).order_by(Supplier.created_at.desc()).all()
    return render_template('accounting/supplier_list.html', suppliers=suppliers)



@accounting_routes.route('/suppliers/edit/<int:supplier_id>', methods=['GET', 'POST'])
def edit_supplier(supplier_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    supplier = tenant_session.query(Supplier).filter_by(id=supplier_id).first()
    if not supplier:
        flash("❌ Supplier not found", "danger")
        return redirect(url_for('accounting_routes.supplier_list'))

    if request.method == 'POST':
        supplier.supplier_type = request.form.get('supplier_type')
        supplier.business_name = request.form.get('business_name')
        supplier.email = request.form.get('email') or None
        supplier.is_reconcilable = bool(request.form.get('is_reconcilable'))

        try:
            raw_phone = request.form.get('phone')
            phone_obj = parse(raw_phone, "LK")
            if not is_valid_number(phone_obj):
                flash("❌ Invalid phone number.", "danger")
                return redirect(url_for('accounting_routes.edit_supplier', supplier_id=supplier.id))
            supplier.phone_number = format_number(phone_obj, PhoneNumberFormat.E164)
        except NumberParseException:
            flash("❌ Could not parse phone number.", "danger")
            return redirect(url_for('accounting_routes.edit_supplier', supplier_id=supplier.id))

        tenant_session.commit()
        flash("✅ Supplier updated successfully.", "success")
        return redirect(url_for('accounting_routes.supplier_list'))

    return render_template('accounting/supplier_edit.html', supplier=supplier)

@accounting_routes.route('/suppliers/view/<int:supplier_id>', methods=['GET'])
def view_supplier(supplier_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    supplier = tenant_session.query(Supplier).filter_by(id=supplier_id).first()
    if not supplier:
        flash("❌ Supplier not found", "danger")
        return redirect(url_for('accounting_routes.supplier_list'))

    
    # Get current balance
    balance = tenant_session.query(
        func.sum(JournalLine.debit - JournalLine.credit)
    ).filter(
        JournalLine.account_id == supplier.account_payable_id,
        JournalLine.partner_id == supplier.id
    ).scalar() or 0.0

    current_date = datetime.now().date().isoformat()
    return render_template(
        'accounting/supplier_view.html',
        supplier=supplier,
        balance=balance,
        current_date=current_date
    )


@accounting_routes.route('/suppliers/toggle_status/<int:supplier_id>')
def toggle_supplier_status(supplier_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    supplier = tenant_session.query(Supplier).filter_by(id=supplier_id).first()
    if not supplier:
        flash("❌ Supplier not found", "danger")
        return redirect(url_for('accounting_routes.supplier_list'))

    supplier.is_active = not supplier.is_active
    tenant_session.commit()
    flash(f"{'✅ Supplier enabled' if supplier.is_active else '⚠️ Supplier disabled'}", "info")
    return redirect(url_for('accounting_routes.view_supplier', supplier_id=supplier_id))


@accounting_routes.route('/suppliers/opening_balance/<int:supplier_id>', methods=['POST'])
def add_supplier_opening_balance(supplier_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    supplier = tenant_session.query(Supplier).filter_by(id=supplier_id).first()
    if not supplier:
        flash("❌ Supplier not found", "danger")
        return redirect(url_for('accounting_routes.supplier_list'))

    try:
        amount = Decimal(request.form.get('opening_balance'))
        date_str = request.form.get('date')
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        flash("❌ Invalid amount or date", "danger")
        return redirect(url_for('accounting_routes.view_supplier', supplier_id=supplier_id))

    # ✅ Check for active fiscal year (is_closed should be False)
    fiscal_year = tenant_session.query(FiscalYear).filter_by(
        company_id=company_id, is_closed=True
    ).first()

    if not fiscal_year:
        flash("❌ Active fiscal year not found", "danger")
        return redirect(url_for('accounting_routes.view_supplier', supplier_id=supplier_id))

    # ✅ Get Opening Balance Suspense account
    suspense_account = tenant_session.query(Account).filter_by(
        company_id=company_id,
        account_code="9999",
        account_name="Opening Balance Suspense"
    ).first()

    if not suspense_account:
        flash("❌ Opening Balance Suspense account not found", "danger")
        return redirect(url_for('accounting_routes.view_supplier', supplier_id=supplier_id))

    try:
        # ✅ Create journal entry
        journal_entry = JournalEntry(
            company_id=company_id,
            date=date_obj,
            reference=f"Opening Balance - {supplier.business_name}",
            narration=f"Opening balance for supplier ID {supplier.id}",
            fiscal_year_id=fiscal_year.id,
            created_by=user_id,
            created_at=datetime.utcnow()
        )
        tenant_session.add(journal_entry)
        tenant_session.flush()

        # ✅ Create journal lines (DO NOT use 'created_by')
        tenant_session.add_all([
            JournalLine(
                entry_id=journal_entry.id,
                account_id=supplier.account_payable_id,
                debit=Decimal(0),
                credit=amount,
                partner_id=supplier.id,
                narration="Opening balance (Credit)"
            ),
            JournalLine(
                entry_id=journal_entry.id,
                account_id=suspense_account.id,
                debit=amount,
                credit=Decimal(0),
                narration="Opening balance (Debit)"
            )
        ])

        tenant_session.commit()
        flash("✅ Opening balance posted successfully.", "success")
    except SQLAlchemyError as e:
        tenant_session.rollback()
        flash(f"❌ Failed to post opening balance: {str(e)}", "danger")

    return redirect(url_for('accounting_routes.view_supplier', supplier_id=supplier_id))

@accounting_routes.route('/cashbank', methods=['GET', 'POST'])
def cash_bank_list():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    if request.method == 'POST':
        cb_type = request.form.get('type')

        # Get or create Bank/Cash/Wallet Control Account
        control_account = tenant_session.query(Account).filter_by(
            company_id=company_id,
            account_type="Bank, Cash & Wallets",
            account_code="1100",
            account_name="Bank, Cash & Wallets Control"
        ).first()

        if not control_account:
            flash("❌ Bank, Cash & Wallets Control account missing.", "danger")
            return redirect(url_for('accounting_routes.cash_bank_list'))

        if cb_type == 'Cash':
            cb = CashBank(
                company_id=company_id,
                type='Cash',
                account_name=request.form.get('account_name'),
                account_cashandbank_id=control_account.id,
                created_by=user_id
            )
        elif cb_type == 'Bank':
            cb = CashBank(
                company_id=company_id,
                type='Bank',
                bank_name=request.form.get('bank_name'),
                account_name=request.form.get('account_name'),
                account_number=request.form.get('account_number'),
                account_cashandbank_id=control_account.id,
                created_by=user_id
            )
        elif cb_type == 'Wallet':
            supplier_id = request.form.get('supplier_id')
            if not supplier_id:
                flash("❌ Wallet must be assigned to a supplier.", "danger")
                return redirect(url_for('accounting_routes.cash_bank_list'))

            cb = CashBank(
                company_id=company_id,
                type='Wallet',
                wallet_name=request.form.get('wallet_name'),
                supplier_id=supplier_id,
                account_cashandbank_id=control_account.id,
                created_by=user_id
            )
        else:
            flash("❌ Invalid type.", "danger")
            return redirect(url_for('accounting_routes.cash_bank_list'))

        tenant_session.add(cb)
        tenant_session.commit()
        flash("✅ Entry added successfully", "success")
        return redirect(url_for('accounting_routes.cash_bank_list'))

    suppliers = tenant_session.query(Supplier).filter_by(is_active=True).all()
    records = tenant_session.query(CashBank).order_by(CashBank.created_at.desc()).all()
    return render_template('accounting/cash_bank_list.html', records=records, suppliers=suppliers)


@accounting_routes.route('/cashbank/view/<int:cb_id>')
def view_cashbank(cb_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    cb = tenant_session.query(CashBank).filter_by(id=cb_id).first()
    if not cb:
        flash("❌ Entry not found", "danger")
        return redirect(url_for('accounting_routes.cash_bank_list'))

    from sqlalchemy import func
    balance = tenant_session.query(
        func.sum(JournalLine.debit - JournalLine.credit)
    ).filter(
        JournalLine.account_id == cb.account_cashandbank_id,
        JournalLine.partner_id == cb.id
    ).scalar() or 0.0

    return render_template('accounting/cash_bank_view.html', cb=cb, balance=balance, current_date=date.today().isoformat())


@accounting_routes.route('/cashbank/edit/<int:cb_id>', methods=['GET', 'POST'])
def edit_cashbank(cb_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    cb = tenant_session.query(CashBank).filter_by(id=cb_id).first()
    if not cb:
        flash("❌ Entry not found", "danger")
        return redirect(url_for('accounting_routes.cash_bank_list'))

    if request.method == 'POST':
        cb.type = request.form.get('type')
        cb.account_name = request.form.get('account_name')
        cb.bank_name = request.form.get('bank_name')
        cb.account_number = request.form.get('account_number')
        cb.wallet_name = request.form.get('wallet_name')
        cb.supplier_id = request.form.get('supplier_id')
        tenant_session.commit()
        flash("✅ Updated successfully", "success")
        return redirect(url_for('accounting_routes.cash_bank_list'))

    suppliers = tenant_session.query(Supplier).filter_by(is_active=True).all()
    return render_template('accounting/cash_bank_edit.html', cb=cb, suppliers=suppliers)


@accounting_routes.route('/cashbank/<int:cb_id>/add-opening-balance', methods=['POST'])
def add_cashbank_opening_balance(cb_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    cb = tenant_session.query(CashBank).filter_by(id=cb_id).first()
    company_id = session['company_id']
    user_id = session.get('user_id')
    today = date.today()

    amount = float(request.form.get("opening_balance", 0))
    if amount == 0:
        flash("❌ Amount must be greater than zero", "danger")
        return redirect(url_for("accounting_routes.view_cashbank", cb_id=cb_id))

    suspense_account = tenant_session.query(Account).filter_by(
        company_id=company_id,
        account_type="Equity",
        account_code="9999",
        account_name="Opening Balance Suspense"
    ).first()

    fiscal_year = tenant_session.query(FiscalYear).filter_by(
        company_id=company_id, is_closed=True
    ).first()

    journal = JournalEntry(
        company_id=company_id,
        date=today,
        reference=f"Opening Balance - {cb.account_name or cb.bank_name or cb.wallet_name}",
        narration=f"Opening balance for CashBank ID {cb.id}",
        fiscal_year_id=fiscal_year.id,
        created_by=user_id,
        created_at=datetime.utcnow()
    )
    tenant_session.add(journal)
    tenant_session.flush()

    tenant_session.add_all([
        JournalLine(
            entry_id=journal.id,
            account_id=cb.account_cashandbank_id,
            debit=amount,
            credit=0,
            narration="Opening balance (Debit)",
            partner_id=cb.id
        ),
        JournalLine(
            entry_id=journal.id,
            account_id=suspense_account.id,
            debit=0,
            credit=amount,
            narration="Opening balance (Credit)"
        )
    ])
    tenant_session.commit()
    flash("✅ Opening balance recorded successfully", "success")
    return redirect(url_for("accounting_routes.view_cashbank", cb_id=cb_id))

# ---Invoice  routes  ---

def generate_invoice_number(session):
    """Return next invoice number in the format I000001."""
    last_invoice = session.query(Invoice).order_by(Invoice.id.desc()).first()
    if last_invoice and last_invoice.invoice_number.startswith("I") and last_invoice.invoice_number[1:].isdigit():
        next_num = int(last_invoice.invoice_number[1:]) + 1
    else:
        next_num = 1
    return f"I{next_num:06d}"

def generate_receipt_number(session):
    """Return next receipt number in the format R00001."""
    last_receipt = session.query(Receipt).order_by(Receipt.id.desc()).first()
    if last_receipt and last_receipt.reference and last_receipt.reference.startswith("R") and last_receipt.reference[1:].isdigit():
        next_num = int(last_receipt.reference[1:]) + 1
    else:
        next_num = 1
    return f"R{next_num:05d}"


def generate_supplier_payment_number(session):
    """Return next supplier payment reference like SP00001."""
    last_pay = session.query(SupplierPayment).order_by(SupplierPayment.id.desc()).first()
    if last_pay and last_pay.reference and last_pay.reference.startswith("SP") and last_pay.reference[2:].isdigit():
        next_num = int(last_pay.reference[2:]) + 1
    else:
        next_num = 1
    return f"SP{next_num:05d}"


def generate_purchase_number(invoice_id: int, line_id: int) -> str:
    """Return purchase number like P000100 for given invoice and line IDs."""
    return f"P{invoice_id:04}{line_id:02}"


def get_supplier_balance(session, company_id, supplier):
    """Return payable balance for a supplier."""
    credit_total = session.query(func.coalesce(func.sum(JournalLine.credit), 0)).join(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalLine.account_id == supplier.account_payable_id,
        JournalLine.partner_id == supplier.id,
    ).scalar() or 0

    debit_total = session.query(func.coalesce(func.sum(JournalLine.debit), 0)).join(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalLine.account_id == supplier.account_payable_id,
        JournalLine.partner_id == supplier.id,
    ).scalar() or 0

    return Decimal(str(credit_total)) - Decimal(str(debit_total))


def get_supplier_dues(session, company_id, supplier):
    """Return payable items for a supplier."""
    from decimal import Decimal

    if supplier.is_reconcilable:
        dues = (
            session.query(SupplierPaymentDue)
            .join(SupplierReconciliation)
            .filter(SupplierReconciliation.supplier_id == supplier.id)
            .all()
        )
        return [
            {
                "id": due.id,
                "reference": due.reference,
                "date": due.reconciliation.recon_date,
                "amount": due.amount,
            }
            for due in dues
        ]

    if supplier.supplier_type == "Expenses":
        expenses = session.query(Expense).filter_by(
            company_id=company_id, supplier_id=supplier.id
        ).all()
        return [
            {
                "id": f"EXP-{e.id}",
                "reference": e.description or "Expense",
                "date": e.expense_date,
                "amount": e.amount,
            }
            for e in expenses
        ]

    lines = (
        session.query(InvoiceLine)
        .join(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.status == "Finalised",
            InvoiceLine.supplier_id == supplier.id,
            InvoiceLine.is_reconciled == False,
        )
        .all()
    )
    items = []
    for line in lines:
        amt = Decimal(str(line.base_fare or 0)) + Decimal(str(line.tax or 0))
        items.append(
            {
                "id": line.id,
                "reference": line.invoice.invoice_number,
                "date": line.invoice.invoice_date,
                "amount": amt,
            }
        )
    return items

@accounting_routes.route('/invoices', methods=['GET', 'POST'])
def invoice_list():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')
    default_currency = get_company_currency(tenant_session, company_id)

    # Get the logged-in user's email (for default consultant selection)
    session_user = tenant_session.query(TenantUser).filter_by(id=user_id).first()
    session_user_email = session_user.email if session_user else ''

    if request.method == 'POST':
        customer_id = request.form.get('customer_id')

        # ✅ Validate customer_id
        if not customer_id or not customer_id.isdigit():
            flash("❌ Invalid customer selected.", "danger")
            return redirect(url_for('accounting_routes.invoice_list'))

        # ✅ Check if customer exists
        customer = tenant_session.query(Customer).filter_by(id=customer_id).first()
        if not customer:
            flash("❌ Selected customer does not exist.", "danger")
            return redirect(url_for('accounting_routes.invoice_list'))

        service_type = request.form.get('service_type')
        invoice_date = request.form.get('invoice_date')
        transaction_date = date.today()
        staff_email = request.form.get('staff_email') or session_user_email
        destination = request.form.get('destination')
        due_term = request.form.get('due_term') or 0
        currency = request.form.get('currency') or default_currency

        # ✅ Validate staff_email (must be a known user in company)
        staff = tenant_session.query(TenantUser).filter_by(
            email=staff_email,
            is_suspended=False,
            company_id=company_id
        ).first()

        if not staff:
            flash("❌ Invalid travel consultant selected.", "danger")
            return redirect(url_for('accounting_routes.invoice_list'))

        invoice_number = generate_invoice_number(tenant_session)
        invoice = Invoice(
            company_id=company_id,
            invoice_number=invoice_number,
            invoice_date=datetime.strptime(invoice_date, '%Y-%m-%d').date(),
            transaction_date=transaction_date,
            customer_id=customer_id,
            service_type=service_type,
            currency=currency,
            total_amount=0.00,
            destination=destination,
            due_term=int(due_term),
            staff_id=staff.id,
            created_by=user_id
        )
        tenant_session.add(invoice)
        tenant_session.commit()
        flash("✅ Invoice created. You can now add line items.", "success")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    # For GET requests
    customers = tenant_session.query(Customer).filter_by(is_active=True).all()
    customers_json = [
        {
            "id": c.id,
            "name": c.full_name or c.business_name,
            "phone": c.phone_number,
            "due_term": c.due_term or 0,
            "consultant_email": c.consultant.email if c.consultant else "",
            "markup": c.markup or 0,
            "email": c.email or "",
            "address_line_1": c.address_line_1 or "",
            "address_line_2": c.address_line_2 or "",
            "city": c.city or "",
            "country": c.country or "",
        }
        for c in customers
    ]

    
    staff_list = tenant_session.query(TenantUser).filter_by(
        is_suspended=False, company_id=company_id
    ).all()
    staff_json = [{"email": s.email} for s in staff_list]
    invoices = tenant_session.query(Invoice).order_by(Invoice.created_at.desc()).all()

    return render_template(
        'accounting/invoice_list.html',
        invoices=invoices,
        customers=customers,
        customers_json=customers_json,
        staff_list=staff_list,
        staff_json=staff_json,
        current_date=date.today().isoformat(),
        session_user_email=session_user_email,
        default_currency=default_currency
    )







@accounting_routes.route('/invoices/edit/<int:invoice_id>', methods=['GET', 'POST'])
def edit_invoice(invoice_id):
    if 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()

    # Fetch the invoice
    invoice = tenant_session.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        flash("❌ Invoice not found.", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    if request.method == 'POST':
        if invoice.status == 'Finalised':
            flash("⚠️ Invoice is finalised and cannot be edited.", "warning")
            return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))
        invoice.invoice_date = datetime.strptime(
            request.form.get('invoice_date'), '%Y-%m-%d'
        ).date()
        invoice.service_type = request.form.get('service_type')
        invoice.destination = request.form.get('destination')
        invoice.due_term = int(request.form.get('due_term') or 0)
        invoice.currency = request.form.get('currency') or invoice.currency

        customer_id = request.form.get('customer_id') or invoice.customer_id
        if customer_id and str(customer_id).isdigit():
            customer = tenant_session.query(Customer).filter_by(id=customer_id).first()
            if customer:
                invoice.customer_id = int(customer_id)
            else:
                flash("❌ Invalid customer selected.", "danger")
                return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))
        else:
            flash("❌ Invalid customer selected.", "danger")
            return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

        staff_email = request.form.get('staff_email')
        staff = tenant_session.query(TenantUser).filter_by(
            email=staff_email,
            is_suspended=False,
            company_id=invoice.company_id
        ).first()
        if staff:
            invoice.staff_id = staff.id
        else:
            flash("❌ Invalid travel consultant selected.", "danger")
            return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

        tenant_session.commit()
        flash("✅ Invoice header updated", "success")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    # Fetch all active suppliers (you can later filter based on invoice.service_type if needed)
    suppliers = tenant_session.query(Supplier).filter_by(is_active=True).order_by(Supplier.business_name).all()

    customers = tenant_session.query(Customer).filter_by(is_active=True).all()
    customers_json = [
        {
            "id": c.id,
            "name": c.full_name or c.business_name,
            "phone": c.phone_number,
            "due_term": c.due_term or 0,
            "consultant_email": c.consultant.email if c.consultant else "",
            "markup": c.markup or 0,
            "email": c.email or "",
            "address_line_1": c.address_line_1 or "",
            "address_line_2": c.address_line_2 or "",
            "city": c.city or "",
            "country": c.country or "",
        }
        for c in customers
    ]

    staff_list = tenant_session.query(TenantUser).filter_by(
        is_suspended=False, company_id=invoice.company_id
    ).all()
    staff_json = [{"email": s.email} for s in staff_list]

    return render_template(
        'accounting/invoice_edit.html',
        invoice=invoice,
        suppliers=suppliers,
        customers_json=customers_json,
        staff_json=staff_json,
    )



@accounting_routes.route('/invoices/<int:invoice_id>/add-line', methods=['POST'])
def add_invoice_line(invoice_id):
    if 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    invoice = tenant_session.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        flash("❌ Invoice not found", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    if invoice.status == 'Finalised':
        flash("⚠️ Invoice is finalised and cannot be edited.", "warning")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    if invoice.status == 'Finalised':
        flash("⚠️ Invoice is finalised and cannot be edited.", "warning")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    try:
        type = request.form.get('type')
        sub_type = request.form.get('sub_type')
        pax_id = request.form.get('pax_id') or None
        base_fare = Decimal(request.form.get('base_fare') or 0)
        tax = Decimal(request.form.get('tax') or 0)
        sell_price = Decimal(request.form.get('sell_price') or 0)
        profit = sell_price - (base_fare + tax) if type == 'Air Ticket' else sell_price - base_fare
        pnr = request.form.get('pnr')
        service_date_str = request.form.get('service_date')
        service_date = (
            datetime.strptime(service_date_str, '%Y-%m-%d').date()
            if service_date_str
            else None
        )
        designator = request.form.get('designator') if sub_type == 'IATA' else None
        ticket_no = request.form.get('ticket_no') if sub_type == 'IATA' else None
        supplier_id = request.form.get('supplier_id') or None

        # Check for duplicate ticket number within the tenant
        if ticket_no:
            existing_line = (
                tenant_session.query(InvoiceLine)
                .join(Invoice)
                .filter(
                    InvoiceLine.ticket_no == ticket_no,
                    Invoice.company_id == invoice.company_id,
                )
                .first()
            )
            if existing_line:
                link = url_for(
                    'accounting_routes.edit_invoice',
                    invoice_id=existing_line.invoice_id,
                )
                flash(
                    Markup(
                        f"❌ Ticket number already used on invoice <a href='{link}'>"
                        f"{existing_line.invoice.invoice_number}</a>."
                    ),
                    "danger",
                )
                return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

        line = InvoiceLine(
            invoice_id=invoice.id,
            type=type,
            sub_type=sub_type,
            pax_id=int(pax_id) if pax_id else None,
            base_fare=base_fare,
            tax=tax,
            sell_price=sell_price,
            profit=profit,
            service_date=service_date,
            pnr=pnr,
            designator=designator,
            ticket_no=ticket_no,
            supplier_id=int(supplier_id) if supplier_id else None,
        )

        tenant_session.add(line)
        tenant_session.commit()
        flash("✅ Line item added", "success")

    except Exception as e:
        tenant_session.rollback()
        flash(f"❌ Error adding invoice line: {str(e)}", "danger")

    return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))





@accounting_routes.route('/invoice-lines/edit/<int:line_id>', methods=['GET', 'POST'])
def edit_invoice_line(line_id):
    if 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    line = tenant_session.query(InvoiceLine).filter_by(id=line_id).first()
    if not line:
        flash("❌ Invoice line not found", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    if line.invoice.status == 'Finalised':
        flash("⚠️ Invoice is finalised and cannot be edited.", "warning")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=line.invoice_id))

    if line.invoice.status == 'Finalised':
        flash("⚠️ Invoice is finalised and cannot be edited.", "warning")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=line.invoice_id))

    suppliers = tenant_session.query(Supplier).filter_by(is_active=True).order_by(Supplier.business_name).all()
    pax_list = tenant_session.query(PaxDetail).filter_by(invoice_id=line.invoice_id).all()

    if request.method == 'POST':
        try:
            line.type = request.form.get('type')
            line.sub_type = request.form.get('sub_type')
            line.pax_id = int(request.form.get('pax_id') or 0) or None
            line.base_fare = Decimal(request.form.get('base_fare') or 0)
            line.tax = Decimal(request.form.get('tax') or 0)
            line.sell_price = Decimal(request.form.get('sell_price') or 0)
            line.profit = line.sell_price - (line.base_fare + line.tax) if line.type == 'Air Ticket' else line.sell_price - line.base_fare
            line.pnr = request.form.get('pnr')
            sd_str = request.form.get('service_date')
            line.service_date = (
                datetime.strptime(sd_str, '%Y-%m-%d').date() if sd_str else None
            )
            line.designator = request.form.get('designator') if line.sub_type == 'IATA' else None
            new_ticket_no = request.form.get('ticket_no') if line.sub_type == 'IATA' else None

            if new_ticket_no:
                existing_line = (
                    tenant_session.query(InvoiceLine)
                    .join(Invoice)
                    .filter(
                        InvoiceLine.ticket_no == new_ticket_no,
                        Invoice.company_id == line.invoice.company_id,
                        InvoiceLine.id != line.id,
                    )
                    .first()
                )
                if existing_line:
                    link = url_for(
                        'accounting_routes.edit_invoice',
                        invoice_id=existing_line.invoice_id,
                    )
                    flash(
                        Markup(
                            f"❌ Ticket number already used on invoice <a href='{link}'>"
                            f"{existing_line.invoice.invoice_number}</a>."
                        ),
                        "danger",
                    )
                    return redirect(url_for('accounting_routes.edit_invoice_line', line_id=line.id))

            line.ticket_no = new_ticket_no
            line.supplier_id = int(request.form.get('supplier_id')) if request.form.get('supplier_id') else None

            tenant_session.commit()
            flash("✅ Line item updated", "success")
            return redirect(url_for('accounting_routes.edit_invoice', invoice_id=line.invoice_id))

        except Exception as e:
            tenant_session.rollback()
            flash(f"❌ Error updating line: {str(e)}", "danger")

    return render_template('accounting/invoice_line_edit.html', line=line, suppliers=suppliers, pax_list=pax_list)
@accounting_routes.route('/invoice-lines/delete/<int:line_id>')
def delete_invoice_line(line_id):
    if 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()

    line = tenant_session.query(InvoiceLine).filter_by(id=line_id).first()
    if not line:
        flash("❌ Invoice line not found", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    invoice_id = line.invoice_id
    tenant_session.delete(line)
    tenant_session.commit()
    invoice = tenant_session.query(Invoice).filter_by(id=invoice_id).first()
    if invoice:
        recalculate_invoice_totals(invoice, tenant_session)

    flash("🗑️ Invoice line deleted", "info")
    return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice_id))


def recalculate_invoice_totals(invoice, session):
    total = sum(line.sell_price or 0 for line in invoice.lines)
    invoice.total_amount = total
    session.commit()


def validate_invoice_lines(invoice):
    """Ensure all invoice line fields are filled appropriately before finalisation."""
    for line in invoice.lines:
        # Basic required fields
        if not line.type or not line.sub_type:
            return False, "Line item missing type or sub type."
        if not line.sell_price or not line.supplier_id:
            return False, "Missing sell price or supplier in a line item."
        if not line.service_date:
            return False, "Service date required for all line items."

        # Additional validations based on type
        if line.type == "Air Ticket":
            if not line.pnr:
                return False, "Air Ticket lines require PNR."
            if line.sub_type == "IATA" and (not line.designator or not line.ticket_no):
                return False, "IATA ticket lines require designator and ticket number."
        else:  # Other services
            if not line.pnr:
                return False, "Reference is required for service lines."

    return True, ""


@accounting_routes.route('/invoices/<int:invoice_id>/add-pax', methods=['POST'])
def add_pax_detail(invoice_id):
    if 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    invoice = tenant_session.query(Invoice).filter_by(id=invoice_id).first()

    if not invoice:
        flash("❌ Invoice not found", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    if invoice.status == 'Finalised':
        flash("⚠️ Invoice is finalised and cannot be edited.", "warning")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    try:
        dob_str = request.form.get('dob')
        dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
        exp_str = request.form.get('passport_expiry_date')
        exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date() if exp_str else None

        pax = PaxDetail(
            invoice_id=invoice.id,
            pax_type=request.form.get('pax_type'),
            last_name=request.form.get('last_name'),
            first_name=request.form.get('first_name'),
            date_of_birth=dob,
            passport_no=request.form.get('passport_no'),
            nationality=request.form.get('nationality'),
            passport_expiry_date=exp_date
        )

        tenant_session.add(pax)
        tenant_session.commit()

        flash("✅ Pax added successfully", "success")

    except Exception as e:
        tenant_session.rollback()
        flash(f"❌ Error adding pax: {str(e)}", "danger")

    return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice_id))

@accounting_routes.route('/invoices/<int:invoice_id>/save', methods=['POST'])
def save_invoice(invoice_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()

    invoice = tenant_session.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        flash("❌ Invoice not found", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    # ✅ Recalculate total from all line items
    total = sum(line.sell_price or 0 for line in invoice.lines)
    invoice.total_amount = total

    tenant_session.commit()

    flash("✅ Invoice saved successfully", "success")
    return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice_id))

@accounting_routes.route('/invoices/finalise/<int:invoice_id>', methods=['POST'])
def finalise_invoice(invoice_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    invoice = tenant_session.query(Invoice).filter_by(id=invoice_id, company_id=company_id).first()
    if not invoice:
        flash("❌ Invoice not found.", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    if invoice.status == 'Finalised':
        flash("⚠️ Invoice is already finalised.", "warning")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    # ✅ Validate active fiscal year
    fiscal_year = tenant_session.query(FiscalYear).filter_by(
        company_id=company_id, is_closed=True
    ).first()

    if not fiscal_year:
        flash("❌ No active fiscal year found.", "danger")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    # ✅ Fetch required accounts
    sales_account = tenant_session.query(Account).filter_by(
        company_id=company_id, account_code='4000', account_type='Revenue'
    ).first()
    purchase_account = tenant_session.query(Account).filter_by(
        company_id=company_id, account_code='5000', account_type='Expense'
    ).first()
    receivable_control = tenant_session.query(Account).filter_by(
        company_id=company_id, account_code='1000', account_type='Receivable'
    ).first()
    payable_control = tenant_session.query(Account).filter_by(
        company_id=company_id, account_code='2000', account_type='Payable'
    ).first()

    if not all([sales_account, purchase_account, receivable_control, payable_control]):
        flash("❌ One or more required control accounts missing (Sales, Purchase, AR, AP).", "danger")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    customer = tenant_session.query(Customer).filter_by(id=invoice.customer_id).first()
    if not customer:
        flash("❌ Customer not found.", "danger")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    if not customer.account_receivable_id:
        customer.account_receivable_id = receivable_control.id
        tenant_session.commit()

    journal_lines = []
    total_sell = 0

    if not invoice.lines:
        flash("❌ Invoice must have at least one line item before finalisation.", "danger")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    # Validate all invoice lines before proceeding
    valid, msg = validate_invoice_lines(invoice)
    if not valid:
        flash(f"❌ {msg}", "danger")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    for line in invoice.lines:

        if not line.income_account_id:
            line.income_account_id = sales_account.id
        if not getattr(line, 'expense_account_id', None):
            line.expense_account_id = purchase_account.id

        if not line.purchase_number:
            line.purchase_number = generate_purchase_number(invoice.id, line.id)

        # ✅ Credit sales account (revenue)
        journal_lines.append(JournalLine(
            account_id=line.income_account_id,
            credit=line.sell_price,
            narration=f"Sale - {line.type} {line.sub_type or ''} ({line.pnr or ''})"
        ))

        total_sell += float(line.sell_price)

        # ✅ Purchase (if any)
        purchase_total = float(line.base_fare or 0) + float(line.tax or 0)
        if purchase_total > 0:
            supplier = tenant_session.query(Supplier).filter_by(id=line.supplier_id).first()
            if not supplier:
                flash(f"❌ Supplier ID {line.supplier_id} not found.", "danger")
                return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

            if not supplier.account_payable_id:
                supplier.account_payable_id = payable_control.id
                tenant_session.commit()

            # ✅ Credit payable
            journal_lines.append(JournalLine(
                account_id=supplier.account_payable_id,
                credit=purchase_total,
                narration=f"Payable - {line.type} {line.sub_type or ''} ({line.pnr or ''})",
                partner_id=supplier.id
            ))

            # ✅ Debit expense
            journal_lines.append(JournalLine(
                account_id=line.expense_account_id,
                debit=purchase_total,
                narration=f"Purchase - {line.type} {line.sub_type or ''} ({line.pnr or ''})"
            ))

    # ✅ Debit receivable
    journal_lines.append(JournalLine(
        account_id=customer.account_receivable_id,
        debit=total_sell,
        narration=f"Receivable - {invoice.invoice_number}",
        partner_id=customer.id
    ))

    # ✅ Create journal entry
    journal_entry = JournalEntry(
        company_id=company_id,
        date=date.today(),
        reference=invoice.invoice_number,
        narration=f"Invoice Finalised - {invoice.invoice_number}",
        fiscal_year_id=fiscal_year.id,
        created_by=user_id,
        lines=journal_lines
    )

    tenant_session.add(journal_entry)

    invoice.status = 'Finalised'
    invoice.total_amount = total_sell
    tenant_session.commit()

    flash("✅ Invoice finalised, journal entries with Receivable/Payable & fiscal year recorded.", "success")
    return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))


@accounting_routes.route('/invoices/reverse/<int:invoice_id>', methods=['POST'])
def reverse_invoice(invoice_id):
    """Reverse a finalised invoice and move any payments to unallocated deposit."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    invoice = tenant_session.query(Invoice).filter_by(id=invoice_id, company_id=company_id).first()
    if not invoice:
        flash("❌ Invoice not found.", "danger")
        return redirect(url_for('accounting_routes.invoice_list'))

    if invoice.status != 'Finalised':
        flash("⚠️ Only finalised invoices can be reversed.", "warning")
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    reconciled = (
        tenant_session.query(SupplierReconciliationLine)
        .join(SupplierReconciliation)
        .join(InvoiceLine)
        .filter(
            InvoiceLine.invoice_id == invoice.id,
            SupplierReconciliation.status == 'Reconciled'
        )
        .first()
    )
    if reconciled:
        flash('❌ Cannot reverse invoice with reconciled lines.', 'danger')
        return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))

    # Find the original journal entry
    entry = tenant_session.query(JournalEntry).filter_by(company_id=company_id, reference=invoice.invoice_number).first()

    fiscal_year = tenant_session.query(FiscalYear).filter(
        FiscalYear.company_id == company_id,
        FiscalYear.is_closed == True
    ).first()

    customer = tenant_session.query(Customer).filter_by(id=invoice.customer_id).first()
    deposit_account = tenant_session.query(Account).filter_by(company_id=company_id, account_code='2010').first()

    total_paid = 0
    if customer and deposit_account and customer.account_receivable_id:
        payment_lines = tenant_session.query(JournalLine).join(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalLine.account_id == customer.account_receivable_id,
            JournalLine.partner_id == customer.id,
            JournalLine.credit > 0,
            JournalLine.narration.ilike(f"%{invoice.invoice_number}%")
        ).all()

        total_paid = sum(line.credit or 0 for line in payment_lines)

    if entry and not entry.reversed_entry_id:
        reverse_entry = JournalEntry(
            company_id=company_id,
            date=date.today(),
            reference=f"REV-{entry.reference}",
            narration=f"Reversal of Invoice {invoice.invoice_number}",
            created_by=user_id,
            fiscal_year_id=fiscal_year.id if fiscal_year else None
        )
        tenant_session.add(reverse_entry)
        tenant_session.flush()
        entry.reversed_entry_id = reverse_entry.id

        for line in entry.lines:
            tenant_session.add(JournalLine(
                entry_id=reverse_entry.id,
                account_id=line.account_id,
                debit=line.credit,
                credit=line.debit,
                narration=f"Reversal: {line.narration}",
                partner_id=line.partner_id
            ))

    if total_paid > 0 and customer and deposit_account and customer.account_receivable_id:
        realloc_entry = JournalEntry(
            company_id=company_id,
            date=date.today(),
            reference=f"REV-ALLOC-{invoice.invoice_number}",
            narration=f"Reallocate payment for {invoice.invoice_number}",
            created_by=user_id,
            fiscal_year_id=fiscal_year.id if fiscal_year else None
        )
        tenant_session.add(realloc_entry)
        tenant_session.flush()

        tenant_session.add(JournalLine(
            entry_id=realloc_entry.id,
            account_id=customer.account_receivable_id,
            debit=total_paid,
            narration=f"Reverse payment for {invoice.invoice_number}",
            partner_id=customer.id
        ))
        tenant_session.add(JournalLine(
            entry_id=realloc_entry.id,
            account_id=deposit_account.id,
            credit=total_paid,
            narration="Unallocated Deposit",
            partner_id=customer.id
        ))

    invoice.status = 'Draft'
    tenant_session.commit()

    flash("✅ Invoice reversed. Journal entry created and payments moved to unallocated deposit.", "success")
    return redirect(url_for('accounting_routes.edit_invoice', invoice_id=invoice.id))


@accounting_routes.route('/receipts/customer', methods=['GET', 'POST'])
def customer_receipt():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get("user_id")
    default_currency = get_company_currency(tenant_session, company_id)

    customers = tenant_session.query(Customer).filter_by(is_active=True).all()
    selected_customer = None
    open_invoices = []

    deposit_options = tenant_session.query(CashBank).filter(
        CashBank.company_id == company_id,
        CashBank.type.in_(['Cash', 'Bank']),
        CashBank.is_active == True
    ).all()

    if request.method == 'POST':
        if 'select_customer' in request.form:
            customer_id = int(request.form.get('customer_id'))
            selected_customer = tenant_session.query(Customer).filter_by(id=customer_id, company_id=company_id).first()

        elif 'submit_receipt' in request.form:
            try:
                customer_id = int(request.form.get('customer_id'))
                selected_customer = tenant_session.query(Customer).filter_by(id=customer_id, company_id=company_id).first()

                cashbank_id = int(request.form.get("payment_account_id"))
                payment_method = request.form.get("payment_method")
                cheque_number = request.form.get("payment_ref")
                payment_date = datetime.strptime(request.form.get("payment_date"), "%Y-%m-%d").date()
                payment_ref = request.form.get("payment_ref")
                total_received = Decimal(request.form.get("total_received", 0))

                if not selected_customer or not selected_customer.account_receivable_id:
                    flash("❌ Invalid customer or missing receivable account.", "danger")
                    return redirect(request.url)

                selected_cashbank = tenant_session.query(CashBank).filter_by(
                    account_cashandbank_id=cashbank_id, company_id=company_id
                ).first()

                if not selected_cashbank or not selected_cashbank.account_cashandbank_id:
                    flash("❌ Invalid 'Deposit to' account selected.", "danger")
                    return redirect(request.url)

                payment_account_id = selected_cashbank.account_cashandbank_id
                total_payment = Decimal(0)
                lines = []

                dues = get_customer_dues(tenant_session, company_id, selected_customer)

                for due in dues:
                    field_name = f"pay_invoice_{due.id}"
                    amount_str = request.form.get(field_name)
                    if amount_str:
                        amount = Decimal(amount_str or 0)
                        if amount > 0:
                            pay_amount = min(amount, due.balance_due)
                            lines.append(JournalLine(
                                account_id=selected_customer.account_receivable_id,
                                credit=pay_amount,
                                narration=f"Payment for {due.invoice_number}",
                                partner_id=selected_customer.id
                            ))
                            total_payment += pay_amount

                unallocated_amount = total_received - total_payment

                if total_payment <= 0 and unallocated_amount <= 0:
                    flash("❌ No payment amount entered.", "danger")
                    return redirect(request.url)

                # Bank/Cash debit for total received
                lines.append(JournalLine(
                    account_id=payment_account_id,
                    debit=total_received,
                    narration=f"Customer Receipt via {payment_method} - {payment_ref}"
                ))

                # Credit Unallocated Deposit if any remaining amount
                if unallocated_amount > 0:
                    unalloc_acc = tenant_session.query(Account).filter_by(company_id=company_id, account_code='2010').first()
                    if not unalloc_acc:
                        flash("❌ Unallocated Deposit account not found.", "danger")
                        return redirect(request.url)
                    lines.append(JournalLine(
                        account_id=unalloc_acc.id,
                        credit=unallocated_amount,
                        narration="Unallocated Deposit",
                        partner_id=selected_customer.id
                    ))

                fiscal_year = tenant_session.query(FiscalYear).filter_by(company_id=company_id, is_closed=True).first()
                if not fiscal_year:
                    flash('⚠️ Active fiscal year not found.', 'danger')
                    return redirect(request.url)

                receipt_number = generate_receipt_number(tenant_session)

                journal_entry = JournalEntry(
                    company_id=company_id,
                    date=payment_date,
                    reference=receipt_number,
                    narration=f"Receipt from {selected_customer.full_name or selected_customer.business_name}",
                    created_by=user_id,
                    fiscal_year_id=fiscal_year.id if fiscal_year else None,
                    lines=lines
                )

                tenant_session.add(journal_entry)
                tenant_session.flush()

                receipt = Receipt(
                    customer_id=selected_customer.id,
                    receipt_date=payment_date,
                    payment_method=payment_method,
                    reference=receipt_number,
                    notes=payment_ref,
                    total_amount=total_received,
                    account_id=payment_account_id,
                    journal_entry_id=journal_entry.id
                )

                tenant_session.add(receipt)
                tenant_session.commit()
                flash("✅ Receipt recorded successfully.", "success")
                return redirect(url_for("accounting_routes.customer_receipt"))

            except Exception as e:
                tenant_session.rollback()
                flash(f"❌ Error: {str(e)}", "danger")
                return redirect(request.url)

    if request.method == 'POST' and 'customer_id' in request.form and not selected_customer:
        try:
            customer_id = int(request.form.get('customer_id'))
            selected_customer = tenant_session.query(Customer).filter_by(id=customer_id, company_id=company_id).first()
        except:
            selected_customer = None

    if selected_customer:
        dues = get_customer_dues(tenant_session, company_id, selected_customer)
        open_invoices = dues

        for invoice in open_invoices:
            if hasattr(invoice, 'journal_lines'):
                invoice.payment_history = [
                    {
                        "date": line.entry.date,
                        "amount": line.credit,
                        "method": line.entry.reference,
                        "ref": line.entry.narration
                    }
                    for line in invoice.journal_lines
                    if line.credit and line.account_id == selected_customer.account_receivable_id
                ]
            else:
                invoice.payment_history = invoice.payment_history if hasattr(invoice, 'payment_history') else []



    return render_template(
        'accounting/receipt_customer.html',
        customers=customers,
        selected_customer=selected_customer,
        open_invoices=open_invoices,
        cash_bank_accounts=deposit_options,
        current_date=date.today(),
        default_currency=default_currency
    )


@accounting_routes.route('/receipts/allocate', methods=['GET', 'POST'])
def allocate_unallocated_deposit():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    customers = tenant_session.query(Customer).filter_by(is_active=True).all()
    selected_customer = None
    open_invoices = []
    deposit_balance = Decimal('0.00')

    if request.method == 'POST':
        if 'select_customer' in request.form:
            customer_id = int(request.form.get('customer_id'))
            selected_customer = tenant_session.query(Customer).filter_by(id=customer_id, company_id=company_id).first()
        elif 'submit_allocation' in request.form:
            try:
                customer_id = int(request.form.get('customer_id'))
                selected_customer = tenant_session.query(Customer).filter_by(id=customer_id, company_id=company_id).first()

                allocation_date = datetime.strptime(request.form.get('allocation_date'), '%Y-%m-%d').date()

                open_invoices = get_customer_dues(tenant_session, company_id, selected_customer)
                deposit_balance = get_customer_deposit_balance(tenant_session, company_id, selected_customer)
                lines = []
                total_alloc = Decimal('0.00')

                for inv in open_invoices:
                    field_name = f"pay_invoice_{inv.id}"
                    amount_str = request.form.get(field_name)
                    if amount_str:
                        amount = Decimal(amount_str or 0)
                        if amount > 0:
                            alloc_amt = min(amount, inv.balance_due)
                            lines.append(JournalLine(
                                account_id=selected_customer.account_receivable_id,
                                credit=alloc_amt,
                                narration=f"Deposit Allocation for {inv.invoice_number}",
                                partner_id=selected_customer.id
                            ))
                            total_alloc += alloc_amt

                if total_alloc <= 0:
                    flash('❌ No allocation amount entered.', 'danger')
                    return redirect(request.url)

                if total_alloc > deposit_balance:
                    flash('❌ Allocation exceeds available deposit.', 'danger')
                    return redirect(request.url)

                deposit_account = tenant_session.query(Account).filter_by(company_id=company_id, account_code='2010').first()

                lines.append(JournalLine(
                    account_id=deposit_account.id,
                    debit=total_alloc,
                    narration='Deposit Allocation',
                    partner_id=selected_customer.id
                ))

                fiscal_year = tenant_session.query(FiscalYear).filter_by(company_id=company_id, is_closed=True).first()
                if not fiscal_year:
                    flash('⚠️ Active fiscal year not found.', 'danger')
                    return redirect(request.url)

                allocation_ref = generate_allocation_reference(tenant_session)

                je = JournalEntry(
                    company_id=company_id,
                    date=allocation_date,
                    reference=allocation_ref,
                    narration=f'Deposit allocation for {selected_customer.full_name or selected_customer.business_name}',
                    created_by=user_id,
                    fiscal_year_id=fiscal_year.id if fiscal_year else None,
                    lines=lines
                )

                tenant_session.add(je)
                tenant_session.commit()

                super_user = (
                    tenant_session.query(TenantUser)
                    .filter(func.lower(TenantUser.role) == 'superxuser', TenantUser.company_id == company_id)
                    .first()
                )
                if super_user:
                    subject = f'Allocation {allocation_ref} created'
                    body = f'A deposit allocation with reference {allocation_ref} was created.'
                    send_email(mail, super_user.email, subject, body)

                flash('✅ Deposit allocated successfully.', 'success')
                return redirect(url_for('accounting_routes.allocate_unallocated_deposit'))
            except Exception as e:
                tenant_session.rollback()
                flash(f'❌ Error: {str(e)}', 'danger')
                return redirect(request.url)

    if request.method == 'POST' and 'customer_id' in request.form and not selected_customer:
        try:
            customer_id = int(request.form.get('customer_id'))
            selected_customer = tenant_session.query(Customer).filter_by(id=customer_id, company_id=company_id).first()
        except:
            selected_customer = None

    if selected_customer:
        open_invoices = get_customer_dues(tenant_session, company_id, selected_customer)
        deposit_balance = get_customer_deposit_balance(tenant_session, company_id, selected_customer)

    return render_template(
        'accounting/allocate_deposit.html',
        customers=customers,
        selected_customer=selected_customer,
        open_invoices=open_invoices,
        deposit_balance=deposit_balance,
        current_date=date.today()
    )

def get_customer_dues(session, company_id, customer, start_date=None, end_date=None, service_type=None):
    """Return list of invoices with outstanding balance for a customer.

    Optional filters can limit by invoice date range and service type.
    Existing callers continue to work as the additional parameters are
    optional.
    """
    from decimal import Decimal
    dues = []

    # ✅ Get Finalised Invoices with optional filters
    invoices_query = session.query(Invoice).filter_by(
        customer_id=customer.id,
        company_id=company_id,
        status='Finalised'
    )
    if start_date:
        invoices_query = invoices_query.filter(Invoice.invoice_date >= start_date)
    if end_date:
        invoices_query = invoices_query.filter(Invoice.invoice_date <= end_date)
    if service_type:
        invoices_query = invoices_query.filter(Invoice.service_type == service_type)

    invoices = invoices_query.all()

    for invoice in invoices:
        payment_lines = (
            session.query(JournalLine)
            .join(JournalEntry)
            .filter(
                JournalEntry.company_id == company_id,
                JournalLine.account_id == customer.account_receivable_id,
                JournalLine.partner_id == customer.id,
                or_(
                    JournalLine.narration.ilike(
                        f"Payment for {invoice.invoice_number}%"
                    ),
                    JournalLine.narration.ilike(
                        f"Deposit Allocation for {invoice.invoice_number}%"
                    ),
                    JournalLine.narration.ilike(
                        f"Reverse payment for {invoice.invoice_number}%"
                    ),
                ),
            )
            .filter(
                or_(JournalEntry.reversed_entry_id.is_(None), JournalEntry.reversed_entry_id == 0)
            )
            .all()
        )

        paid = Decimal(
            sum(
                [Decimal(str(line.credit or 0)) - Decimal(str(line.debit or 0)) for line in payment_lines]
            )
        )
        balance_due = Decimal(str(invoice.total_amount or 0)) - paid

        if balance_due > 0:
            invoice.amount_paid = paid
            invoice.balance_due = balance_due
            invoice.payment_history = [
                {
                    "date": line.entry.date,
                    "amount": line.credit,
                    "method": line.entry.reference,
                    "ref": line.entry.narration
                }
                for line in payment_lines
            ]
            dues.append(invoice)

    # ✅ Add Opening Balance as Virtual Invoice if not settled
    ob_entries = session.query(JournalEntry).join(JournalLine).filter(
        JournalEntry.company_id == company_id,
        JournalLine.account_id == customer.account_receivable_id,
        JournalLine.partner_id == customer.id,
        JournalEntry.reference.like("Opening Balance%")
    ).all()

    for entry in ob_entries:
        debit_line = next((line for line in entry.lines if line.account_id == customer.account_receivable_id), None)
        if not debit_line:
            continue

        credit_lines = session.query(JournalLine).join(JournalEntry).filter(
            JournalEntry.company_id == company_id,
            JournalLine.partner_id == customer.id,
            JournalLine.account_id == customer.account_receivable_id,
            JournalLine.credit > 0,
            JournalEntry.date >= entry.date,
            JournalEntry.reference != entry.reference,
            JournalLine.narration.ilike("Payment for Opening Balance%")
        ).all()

        paid = sum([Decimal(line.credit or 0) for line in credit_lines])
        balance_due = Decimal(str(debit_line.debit or "0")) - paid

        if balance_due > 0:
            dues.append(type('VirtualInvoice', (), {
                'id': f"OB-{entry.id}",
                'invoice_number': "Opening Balance",
                'invoice_date': entry.date,
                'total_amount': debit_line.debit,
                'amount_paid': paid,
                'balance_due': balance_due,
                'is_ob_virtual': True,
                'payment_history': [
                    {
                        "date": line.entry.date,
                        "amount": line.credit,
                        "method": line.entry.reference,
                        "ref": line.entry.narration
                    }
                    for line in credit_lines
                ]
            }))

    return dues


def get_customer_deposit_balance(session, company_id, customer):
    from decimal import Decimal
    deposit_account = session.query(Account).filter_by(company_id=company_id, account_code='2010').first()
    if not deposit_account:
        return Decimal('0.00')

    credit_total = session.query(func.coalesce(func.sum(JournalLine.credit), 0)).join(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalLine.account_id == deposit_account.id,
        JournalLine.partner_id == customer.id
    ).scalar() or 0

    debit_total = session.query(func.coalesce(func.sum(JournalLine.debit), 0)).join(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalLine.account_id == deposit_account.id,
        JournalLine.partner_id == customer.id
    ).scalar() or 0

    return Decimal(str(credit_total)) - Decimal(str(debit_total))


@accounting_routes.route('/receipts', methods=['GET'])
def receipt_list():
    """List customer receipts with option to reverse."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    default_currency = get_company_currency(tenant_session, company_id)

    receipts = (
        tenant_session.query(Receipt)
        .join(Customer, Receipt.customer_id == Customer.id)
        .join(JournalEntry, Receipt.journal_entry_id == JournalEntry.id)
        .filter(Customer.company_id == company_id)
        .order_by(Receipt.id.desc())
        .all()
    )

    return render_template('accounting/receipt_list.html', receipts=receipts, default_currency=default_currency)


@accounting_routes.route('/receipts/reverse/<int:receipt_id>', methods=['POST'])
def reverse_receipt(receipt_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    receipt = tenant_session.query(Receipt).join(Customer).filter(
        Receipt.id == receipt_id,
        Customer.company_id == company_id,
    ).first()

    if not receipt:
        flash('❌ Receipt not found.', 'danger')
        return redirect(url_for('accounting_routes.receipt_list'))

    entry = tenant_session.query(JournalEntry).filter_by(
        id=receipt.journal_entry_id,
        company_id=company_id
    ).first()

    if not entry:
        flash('❌ Journal entry not found.', 'danger')
        return redirect(url_for('accounting_routes.receipt_list'))

    fiscal_year = tenant_session.query(FiscalYear).filter(
        FiscalYear.company_id == company_id,
        FiscalYear.is_closed == True
    ).first()

    if entry.reversal_of or entry.reversed_by:
        flash('⚠️ This receipt has already been reversed.', 'warning')
        return redirect(url_for('accounting_routes.receipt_list'))

    reverse_entry = JournalEntry(
        company_id=company_id,
        date=datetime.today().date(),
        reference=f"REV-{entry.reference}",
        narration=f"Reversal of Receipt {entry.reference}",
        created_by=user_id,
        fiscal_year_id=fiscal_year.id if fiscal_year else None
    )
    tenant_session.add(reverse_entry)
    tenant_session.flush()

    entry.reversed_entry_id = reverse_entry.id

    for line in entry.lines:
        tenant_session.add(JournalLine(
            entry_id=reverse_entry.id,
            account_id=line.account_id,
            debit=line.credit,
            credit=line.debit,
            narration=f"Reversal: {line.narration}",
            partner_id=line.partner_id,
        ))

    tenant_session.commit()

    super_user = (
        tenant_session.query(TenantUser)
        .filter(func.lower(TenantUser.role) == 'superxuser', TenantUser.company_id == company_id)
        .first()
    )
    if super_user:
        subject = f'Receipt {receipt.reference} reversed'
        body = f'Receipt {receipt.reference} for {receipt.customer.full_name or receipt.customer.business_name} was reversed.'
        send_email(mail, super_user.email, subject, body)

    flash('✅ Receipt reversed successfully.', 'success')
    return redirect(url_for('accounting_routes.receipt_list'))


@accounting_routes.route('/allocations', methods=['GET'])
def allocation_list():
    """List customer deposit allocations with option to reverse."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    allocations = (
        tenant_session.query(JournalEntry)
        .filter(
            JournalEntry.company_id == company_id,
            JournalEntry.reference.like('CA%')
        )
        .order_by(JournalEntry.id.desc())
        .all()
    )

    alloc_data = []
    for entry in allocations:
        cust_name = '-'
        amount = sum([line.credit or 0 for line in entry.lines])
        if entry.lines:
            partner_id = entry.lines[0].partner_id
            if partner_id:
                cust = tenant_session.query(Customer).filter_by(id=partner_id).first()
                if cust:
                    cust_name = cust.full_name or cust.business_name or '-'
        alloc_data.append({'entry': entry, 'customer': cust_name, 'amount': amount})

    return render_template('accounting/allocation_list.html', allocations=alloc_data)


@accounting_routes.route('/receipts/view/<int:receipt_id>')
def view_receipt(receipt_id):
    """Display a single receipt with print and PDF options."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    receipt = (
        tenant_session.query(Receipt)
        .join(Customer, Receipt.customer_id == Customer.id)
        .join(JournalEntry, Receipt.journal_entry_id == JournalEntry.id)
        .options(
            joinedload(Receipt.customer),
            joinedload(Receipt.journal_entry).joinedload(JournalEntry.lines).joinedload(JournalLine.account),
        )
        .filter(Receipt.id == receipt_id, Customer.company_id == company_id)
        .first()
    )

    if not receipt:
        flash('❌ Receipt not found.', 'danger')
        return redirect(url_for('accounting_routes.receipt_list'))

    company = tenant_session.query(CompanyProfile).filter_by(company_id=company_id).first()

    return render_template('accounting/receipt_detail.html', receipt=receipt, company=company)


@accounting_routes.route('/receipts/pdf/<int:receipt_id>')
def receipt_pdf(receipt_id):
    """Generate a PDF for a single receipt."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    receipt = (
        tenant_session.query(Receipt)
        .join(Customer, Receipt.customer_id == Customer.id)
        .join(JournalEntry, Receipt.journal_entry_id == JournalEntry.id)
        .options(
            joinedload(Receipt.customer),
            joinedload(Receipt.journal_entry).joinedload(JournalEntry.lines).joinedload(JournalLine.account),
        )
        .filter(Receipt.id == receipt_id, Customer.company_id == company_id)
        .first()
    )

    if not receipt:
        flash('❌ Receipt not found.', 'danger')
        return redirect(url_for('accounting_routes.receipt_list'))

    company = tenant_session.query(CompanyProfile).filter_by(company_id=company_id).first()

    html = render_template('accounting/receipt_pdf.html', receipt=receipt, company=company)

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    if pisa_status.err:
        return 'PDF generation error', 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = (
        f'attachment; filename=receipt_{receipt.reference}.pdf'
    )
    return response


# ---------------- Supplier Features -----------------

@accounting_routes.route('/suppliers/reconcile', methods=['GET', 'POST'])
def supplier_reconcile():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    suppliers = (
        tenant_session.query(Supplier)
        .filter_by(is_active=True, is_reconcilable=True)
        .all()
    )

    rec_id = request.form.get('rec_id', type=int) or request.args.get('rec_id', type=int)
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        supplier_id = request.form.get('supplier_id', type=int)
        if not supplier_id:
            flash('❌ Supplier is required.', 'danger')
            return redirect(request.url)
        recon_date = datetime.strptime(request.form.get('recon_date'), '%Y-%m-%d').date()
        reference = request.form.get('reference') or None
        statement_amount = Decimal(request.form.get('statement_amount', '0'))
        notes = request.form.get('notes') or None
        line_ids = [int(i) for i in request.form.getlist('line_ids')]

        lines = tenant_session.query(InvoiceLine).filter(InvoiceLine.id.in_(line_ids)).all()
        line_data = []
        total_cost = Decimal('0')
        total_supplier_amt = Decimal('0')
        for line in lines:
            line_total = (line.base_fare or 0) + (line.tax or 0)
            supplier_amt = Decimal(request.form.get(f'supplier_amount_{line.id}', '0'))
            line_data.append((line, supplier_amt, line_total))
            total_cost += Decimal(str(line_total))
            total_supplier_amt += supplier_amt

        total_discrepancy = total_cost - total_supplier_amt

        if action == 'reconcile' and total_discrepancy != Decimal('0'):
            flash('❌ Discrepancies must be zero to reconcile.', 'danger')
            return redirect(request.url)

        if rec_id:
            rec = tenant_session.query(SupplierReconciliation).filter_by(id=rec_id).first()
            if not rec:
                flash('❌ Reconciliation not found.', 'danger')
                return redirect(url_for('accounting_routes.supplier_reconciliation_list'))
            # reset previous lines
            for l in rec.lines:
                inv_line = l.invoice_line
                inv_line.is_reconciled = False
            tenant_session.query(SupplierReconciliationLine).filter_by(reconciliation_id=rec.id).delete()
            if rec.payment_due:
                tenant_session.delete(rec.payment_due)
        else:
            rec = SupplierReconciliation(
                supplier_id=supplier_id,
                recon_date=recon_date,
            )
            tenant_session.add(rec)

        rec.amount = total_cost
        rec.statement_amount = statement_amount
        rec.reference = reference
        rec.notes = notes
        rec.status = 'Reconciled' if action == 'reconcile' else 'Saved'

        # Flush after setting required fields so the INSERT does not violate
        # NOT NULL constraints when creating a new reconciliation
        tenant_session.flush()

        for line, supplier_amt, _line_total in line_data:
            line.is_reconciled = True
            tenant_session.add(SupplierReconciliationLine(
                reconciliation_id=rec.id,
                invoice_line_id=line.id,
                supplier_amount=supplier_amt
            ))

        if action == 'reconcile':
            tenant_session.add(SupplierPaymentDue(
                reconciliation_id=rec.id,
                reference=reference,
                amount=statement_amount
            ))

        tenant_session.commit()
        flash('✅ Reconciliation saved.' if action == 'save' else '✅ Reconciled and payment due created.', 'success')
        return redirect(url_for('accounting_routes.supplier_reconciliation_list'))

    supplier_id = request.args.get('supplier_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    supplier_amounts = {}
    if rec_id and request.method == 'GET':
        rec = (
            tenant_session.query(SupplierReconciliation)
            .options(
                joinedload(SupplierReconciliation.lines).joinedload(SupplierReconciliationLine.invoice_line).joinedload(InvoiceLine.pax),
                joinedload(SupplierReconciliation.supplier),
            )
            .filter_by(id=rec_id)
            .first()
        )
        if not rec:
            flash('❌ Reconciliation not found.', 'danger')
            return redirect(url_for('accounting_routes.supplier_reconciliation_list'))
        if rec.status == 'Reconciled':
            flash('❌ Reconciliation already finalized.', 'danger')
            return redirect(url_for('accounting_routes.supplier_reconciliation_list'))
        supplier_id = rec.supplier_id
        lines = [l.invoice_line for l in rec.lines]
        for l in rec.lines:
            supplier_amounts[l.invoice_line_id] = l.supplier_amount
        selected_supplier = rec.supplier
        start_date_str = end_date_str = ''
        reference = rec.reference or ''
        statement_amount = rec.statement_amount
    else:
        lines = []
        selected_supplier = None
        if supplier_id:
            query = (
                tenant_session.query(InvoiceLine)
                .join(Invoice)
                .filter(Invoice.company_id == company_id)
                .filter(InvoiceLine.supplier_id == supplier_id)
            )

            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    query = query.filter(InvoiceLine.service_date >= start_date)
                except ValueError:
                    start_date = None
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    query = query.filter(InvoiceLine.service_date <= end_date)
                except ValueError:
                    end_date = None

            lines = (
                query.options(joinedload(InvoiceLine.invoice), joinedload(InvoiceLine.pax))
                .filter(InvoiceLine.is_reconciled == False)
                .all()
            )
            selected_supplier = tenant_session.query(Supplier).get(supplier_id)

    return render_template(
        'accounting/supplier_reconcile.html',
        suppliers=suppliers,
        lines=lines,
        selected_supplier_id=supplier_id or '',
        selected_supplier=selected_supplier,
        start_date=start_date_str or '',
        end_date=end_date_str or '',
        current_date=date.today(),
        rec_id=rec_id or '',
        supplier_amounts=supplier_amounts,
        reference=locals().get('reference', ''),
        statement_amount=locals().get('statement_amount', 0),
    )



@accounting_routes.route('/suppliers/reconciliations')
def supplier_reconciliation_list():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    recs = (
        tenant_session.query(SupplierReconciliation)
        .options(joinedload(SupplierReconciliation.supplier))
        .order_by(SupplierReconciliation.recon_date.desc())
        .all()
    )
    return render_template('accounting/supplier_reconciliation_list.html', recs=recs)


@accounting_routes.post('/suppliers/reconciliation/<int:rec_id>/reverse')
def reverse_supplier_reconciliation(rec_id):
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    rec = (
        tenant_session.query(SupplierReconciliation)
        .options(joinedload(SupplierReconciliation.lines).joinedload(SupplierReconciliationLine.invoice_line))
        .filter_by(id=rec_id)
        .first()
    )
    if not rec or rec.status != 'Reconciled':
        flash('❌ Reconciliation not found or not reconciled.', 'danger')
        return redirect(url_for('accounting_routes.supplier_reconciliation_list'))

    for line in rec.lines:
        line.invoice_line.is_reconciled = False
        tenant_session.delete(line)
    if rec.payment_due:
        tenant_session.delete(rec.payment_due)
    tenant_session.delete(rec)
    tenant_session.commit()
    flash('✅ Reconciliation reversed.', 'success')
    return redirect(url_for('accounting_routes.supplier_reconciliation_list'))


@accounting_routes.route('/expenses/post', methods=['GET', 'POST'])
def post_expense():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    suppliers = tenant_session.query(Supplier).filter_by(supplier_type='Expenses', is_active=True).all()
    expense_accounts = tenant_session.query(Account).filter_by(company_id=company_id, account_type='Expense').all()

    if request.method == 'POST':
        supplier_id = int(request.form.get('supplier_id'))
        account_id = int(request.form.get('account_id'))
        expense_date = datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d').date()
        description = request.form.get('description')
        amount = Decimal(request.form.get('amount', '0'))

        supplier = tenant_session.query(Supplier).filter_by(id=supplier_id).first()
        if not supplier:
            flash('❌ Supplier not found.', 'danger')
            return redirect(request.url)

        fiscal_year = tenant_session.query(FiscalYear).filter_by(company_id=company_id, is_closed=True).first()
        if not fiscal_year:
            flash('⚠️ Active fiscal year not found.', 'danger')
            return redirect(request.url)

        entry = JournalEntry(
            company_id=company_id,
            date=expense_date,
            reference='EXP',
            narration=description,
            fiscal_year_id=fiscal_year.id,
            created_by=user_id,
        )
        tenant_session.add(entry)
        tenant_session.flush()

        tenant_session.add_all([
            JournalLine(
                entry_id=entry.id,
                account_id=account_id,
                debit=amount,
                narration=description,
            ),
            JournalLine(
                entry_id=entry.id,
                account_id=supplier.account_payable_id,
                credit=amount,
                narration=description,
                partner_id=supplier.id,
            ),
        ])

        expense = Expense(
            supplier_id=supplier.id,
            company_id=company_id,
            expense_date=expense_date,
            description=description,
            amount=amount,
            account_id=account_id,
            journal_entry_id=entry.id,
        )
        tenant_session.add(expense)
        tenant_session.commit()
        flash('✅ Expense posted.', 'success')
        return redirect(url_for('accounting_routes.post_expense'))

    return render_template(
        'accounting/expense_post.html',
        suppliers=suppliers,
        expense_accounts=expense_accounts,
        current_date=date.today(),
    )


@accounting_routes.route('/suppliers/payment', methods=['GET', 'POST'])
def supplier_payment():
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_id = session.get('user_id')

    suppliers = tenant_session.query(Supplier).filter_by(is_active=True).all()
    cash_banks = tenant_session.query(CashBank).filter(
        CashBank.company_id == company_id,
        CashBank.type.in_(['Cash', 'Bank', 'Wallet']),
        CashBank.is_active == True,
    ).all()

    selected_supplier = None
    selected_account = None
    due_items = []

    if request.method == 'POST':
        if 'submit_payment' in request.form:
            supplier_id = int(request.form.get('supplier_id'))
            payment_account_id = int(request.form.get('payment_account_id'))
            payment_method = request.form.get('payment_method')
            payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
            notes = request.form.get('notes') or None

            supplier = tenant_session.query(Supplier).filter_by(id=supplier_id).first()
            if not supplier:
                flash('❌ Supplier not found.', 'danger')
                return redirect(request.url)

            selected_account = tenant_session.query(CashBank).filter_by(account_cashandbank_id=payment_account_id, company_id=company_id).first()
            if selected_account and selected_account.type == 'Wallet' and selected_account.supplier_id != supplier.id:
                flash('❌ This wallet is not assigned to the selected supplier.', 'danger')
                return redirect(request.url)

            if supplier.supplier_type in ['BSP', 'Airlines']:
                has_rec = tenant_session.query(SupplierReconciliation).filter_by(supplier_id=supplier_id).first()
                if not has_rec:
                    flash('❌ Reconciliation required before payment for this supplier.', 'danger')
                    return redirect(request.url)

            if supplier.supplier_type == 'Expenses':
                has_exp = tenant_session.query(Expense).filter_by(supplier_id=supplier_id).first()
                if not has_exp:
                    flash('❌ Please post expenses before paying this supplier.', 'danger')
                    return redirect(request.url)

            fiscal_year = tenant_session.query(FiscalYear).filter_by(company_id=company_id, is_closed=True).first()
            if not fiscal_year:
                flash('⚠️ Active fiscal year not found.', 'danger')
                return redirect(request.url)

            reference = generate_supplier_payment_number(tenant_session)

            total_amount = Decimal('0.00')
            for k, v in request.form.items():
                if k.startswith('pay_item_'):
                    total_amount += Decimal(v or '0')

            if total_amount <= 0:
                flash('❌ No payment amount entered.', 'danger')
                return redirect(request.url)

            entry = JournalEntry(
                company_id=company_id,
                date=payment_date,
                reference=reference,
                narration=f'Supplier Payment - {supplier.business_name}',
                fiscal_year_id=fiscal_year.id,
                created_by=user_id,
            )
            tenant_session.add(entry)
            tenant_session.flush()

            tenant_session.add_all([
                JournalLine(
                    entry_id=entry.id,
                    account_id=supplier.account_payable_id,
                    debit=total_amount,
                    narration='Supplier Payment',
                    partner_id=supplier.id,
                ),
                JournalLine(
                    entry_id=entry.id,
                    account_id=payment_account_id,
                    credit=total_amount,
                    narration='Supplier Payment',
                ),
            ])

            pay = SupplierPayment(
                supplier_id=supplier.id,
                company_id=company_id,
                payment_date=payment_date,
                payment_method=payment_method,
                reference=reference,
                notes=notes,
                total_amount=total_amount,
                account_id=payment_account_id,
                journal_entry_id=entry.id,
            )
            tenant_session.add(pay)
            tenant_session.commit()
            flash('✅ Supplier payment recorded.', 'success')
            return redirect(url_for('accounting_routes.supplier_payment'))

        else:
            supplier_id = request.form.get('supplier_id')
            account_id = request.form.get('payment_account_id')
            if supplier_id and supplier_id.isdigit():
                selected_supplier = tenant_session.query(Supplier).filter_by(id=int(supplier_id)).first()
            if account_id and account_id.isdigit():
                selected_account = tenant_session.query(CashBank).filter_by(account_cashandbank_id=int(account_id), company_id=company_id).first()

    if selected_supplier:
        due_items = get_supplier_dues(tenant_session, company_id, selected_supplier)

    return render_template(
        'accounting/supplier_payment.html',
        suppliers=suppliers,
        cash_banks=cash_banks,
        selected_supplier=selected_supplier,
        selected_account=selected_account,
        due_items=due_items,
        cash_banks_info=[{'id': cb.account_cashandbank_id, 'type': cb.type, 'supplier_id': cb.supplier_id} for cb in cash_banks],
        current_date=date.today(),
    )


@accounting_routes.route('/suppliers/payments', methods=['GET'])
def supplier_payment_list():
    """List supplier payments."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    payments = (
        tenant_session.query(SupplierPayment)
        .join(Supplier, SupplierPayment.supplier_id == Supplier.id)
        .filter(Supplier.company_id == company_id)
        .order_by(SupplierPayment.id.desc())
        .all()
    )

    return render_template('accounting/supplier_payment_list.html', payments=payments)


@accounting_routes.route('/suppliers/payment/view/<int:payment_id>')
def view_supplier_payment(payment_id):
    """Display a single supplier payment."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    payment = (
        tenant_session.query(SupplierPayment)
        .join(Supplier, SupplierPayment.supplier_id == Supplier.id)
        .join(JournalEntry, SupplierPayment.journal_entry_id == JournalEntry.id)
        .options(
            joinedload(SupplierPayment.supplier),
            joinedload(SupplierPayment.journal_entry).joinedload(JournalEntry.lines).joinedload(JournalLine.account),
        )
        .filter(SupplierPayment.id == payment_id, Supplier.company_id == company_id)
        .first()
    )

    if not payment:
        flash('❌ Payment not found.', 'danger')
        return redirect(url_for('accounting_routes.supplier_payment_list'))

    company = tenant_session.query(CompanyProfile).filter_by(company_id=company_id).first()

    return render_template('accounting/supplier_payment_detail.html', payment=payment, company=company)


@accounting_routes.route('/suppliers/payment/pdf/<int:payment_id>')
def supplier_payment_pdf(payment_id):
    """Generate a PDF for a supplier payment."""
    if 'domain' not in session or 'company_id' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']

    payment = (
        tenant_session.query(SupplierPayment)
        .join(Supplier, SupplierPayment.supplier_id == Supplier.id)
        .join(JournalEntry, SupplierPayment.journal_entry_id == JournalEntry.id)
        .options(
            joinedload(SupplierPayment.supplier),
            joinedload(SupplierPayment.journal_entry).joinedload(JournalEntry.lines).joinedload(JournalLine.account),
        )
        .filter(SupplierPayment.id == payment_id, Supplier.company_id == company_id)
        .first()
    )

    if not payment:
        flash('❌ Payment not found.', 'danger')
        return redirect(url_for('accounting_routes.supplier_payment_list'))

    company = tenant_session.query(CompanyProfile).filter_by(company_id=company_id).first()

    html = render_template('accounting/supplier_payment_pdf.html', payment=payment, company=company)

    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    if pisa_status.err:
        return 'PDF generation error', 500

    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = (
        f'attachment; filename=payment_{payment.reference}.pdf'
    )
    return response
