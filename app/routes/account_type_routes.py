# routes/account_type_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.models import AccountType
from app.routes.register_routes import current_tenant_session
from datetime import datetime
from sqlalchemy.orm import joinedload

account_type_routes = Blueprint('account_type_routes', __name__)

@account_type_routes.route('/account-types', methods=['GET', 'POST'])
def manage_account_types():
    if 'domain' not in session:
        return redirect(url_for('register_routes.login'))


    company_id = session.get('company_id')
    if not company_id:
        flash("Company ID is missing in session", "danger")
        return redirect(url_for('register_routes.login'))
    tenant_session = current_tenant_session()

    valid_parents = (
        tenant_session.query(AccountType)
        .options(joinedload(AccountType.children))
        .filter(AccountType.company_id == company_id)
        .all()
    )
    valid_parents = [atype for atype in valid_parents if atype.children]


    if request.method == 'POST':
        name = request.form['name']
        parent_id = request.form.get('parent_id') or None
        is_header = True if request.form.get('is_header') else False

        new_type = AccountType(
            name=name,
            parent_id=parent_id,
            is_header=is_header,
            company_id=company_id,  # ✅ Assign company_id
            created_at=datetime.utcnow()
        )
        tenant_session.add(new_type)
        tenant_session.commit()

        flash("✅ Account type added successfully.", "success")
        return redirect(url_for('account_type_routes.manage_account_types'))
    
    all_types = tenant_session.query(AccountType).all()
    return render_template('accounting/account_types.html', account_types=all_types, valid_parents=valid_parents)
