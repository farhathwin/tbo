from flask import Blueprint, request, render_template, redirect, url_for, flash, session,jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import string
import os
import secrets
from app import db, bcrypt, mail
from app.models.models import MasterCompany, User, UserInvite, Company,OTP
from app.models.models import TenantOTP, TenantUser , UserProfile, CompanyProfile
from app.utils.email_utils import send_otp_email, send_email
from app.utils.database_utils import create_company_schema
from app.utils.database_utils import get_company_db_session
import re


profile_routes = Blueprint('profile_routes', __name__)
register_routes = Blueprint('register_routes', __name__)


@register_routes.route('/')
def home():
    return redirect(url_for('register_routes.login'))


@register_routes.route('/register-company', methods=['GET', 'POST'])
def register_company():
    email_error = None
    domain_error = None

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        subdomain = request.form['domain'].strip().lower()

        domain = f"{subdomain}.pepmytrip.com"

        if MasterCompany.query.filter_by(domain=domain).first():
            domain_error = "This subdomain is already taken. Please choose another."

        if User.query.filter_by(email=email).first():
            email_error = "This email is already registered. Please log in."

        if email_error or domain_error:
            return render_template(
                'register_company.html',
                email=email,
                domain=subdomain,  
                email_error=email_error,
                domain_error=domain_error
            )

        code = ''.join(filter(str.isalnum, domain.upper()))[:6] + ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
        new_company = MasterCompany(domain=domain, name=domain.split('.')[0].capitalize(), code=code)
        db.session.add(new_company)
        db.session.commit()

        # 🔑 Ensure a corresponding row exists in the ``company`` table used by
        # foreign key constraints (e.g. ``OTP.company_id``). Without this the
        # OTP insert will fail on MySQL.
        core_company = Company(
            id=new_company.id,
            name=new_company.name,
            code=new_company.code,
            domain=new_company.domain,
        )
        db.session.add(core_company)
        db.session.commit()

        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        otp_code = ''.join(random.choices(string.digits, k=6))

        tenant_db = create_company_schema(domain)
        tenant_session = tenant_db()

        try:
            tenant_user = TenantUser(email=email, password=hashed_pw, role='SuperXuser', company_id=new_company.id)
            tenant_otp = TenantOTP(email=email, otp_code=otp_code, company_id=new_company.id)
            tenant_session.add(tenant_user)
            tenant_session.add(tenant_otp)
            tenant_session.commit()

            core_user = User(email=email, password=hashed_pw, role='SuperXuser', company_id=new_company.id)
            core_otp = OTP(email=email, otp_code=otp_code, company_id=new_company.id)
            db.session.add(core_user)
            db.session.add(core_otp)
            db.session.commit()
        
        except Exception as e:
            tenant_session.rollback()
            db.session.rollback()
            flash(f"Registration failed: {e}", "danger")
            return redirect(url_for('register_routes.register_company'))

        finally:
            tenant_session.close()

        send_otp_email(mail, email, otp_code)
        session['pending_user_email'] = email
        session['pending_company_domain'] = domain

        return redirect(url_for('register_routes.validate_otp'))

    return render_template('register_company.html')


@register_routes.route('/create-tenant-domain', methods=['POST'])
def create_tenant_domain():
    data = request.get_json()
    domain = data.get('domain')
    email = session.get('email')

    if not email:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    # Ensure proper domain format
    if not domain or not domain.endswith('.pepmytrip.com'):
        return jsonify({'success': False, 'message': 'Invalid domain format'}), 400

    subdomain = domain.replace('.pepmytrip.com', '')
    if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', subdomain):
        return jsonify({'success': False, 'message': 'Invalid subdomain. Use only letters/numbers'}), 400

    # Check for duplicate domain
    if MasterCompany.query.filter_by(domain=domain).first():
        return jsonify({'success': False, 'message': 'Domain already registered'}), 400

    code = ''.join(filter(str.isalnum, subdomain.upper()))[:6] + ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
    new_company = MasterCompany(domain=domain, name=subdomain.capitalize(), code=code)
    db.session.add(new_company)
    db.session.commit()

    try:
        tenant_db = create_company_schema(domain)
        tenant_session = tenant_db()
        core_user = User.query.filter_by(email=email).first()

        # No OTP logic now
        tenant_user = TenantUser(email=email, password=core_user.password, role='SuperXuser', company_id=new_company.id)
        tenant_session.add(tenant_user)
        tenant_session.commit()
        tenant_session.close()

        return jsonify({'success': True, 'message': f'Company {domain} created successfully!'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@register_routes.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if not user or not bcrypt.check_password_hash(user.password, password):
            flash("Invalid email or password", "danger")
            return redirect(url_for('register_routes.login'))

        matching_domains = []
        companies = MasterCompany.query.all()
        for company in companies:
            try:
                tenant_session = get_company_db_session(company.domain)
                tenant_user = tenant_session.query(TenantUser).filter_by(email=email).first()
                if tenant_user and not tenant_user.is_suspended:
                    tenant_user.last_login = datetime.utcnow()
                    tenant_session.commit()
                    matching_domains.append(company.domain)
            except Exception:
                continue

        if not matching_domains:
            flash("No matching tenant found for this user", "danger")
            return redirect(url_for('register_routes.login'))

        session['email'] = email
        session['user_id'] = user.id
        session['available_domains'] = matching_domains
        session['role'] = tenant_user.role  


        if len(matching_domains) == 1:
            return redirect(url_for('register_routes.select_domain') + f"?domain={matching_domains[0]}")
        else:
            return render_template('select_domain.html', domains=matching_domains)

    return render_template('login.html')


@register_routes.route('/select-domain', methods=['GET', 'POST'])
def select_domain():
    if request.method == 'POST':
        domain = request.form['domain']
    else:
        domain = request.args.get('domain')

    if not domain:
        flash("No domain selected.", "danger")
        return redirect(url_for('register_routes.login'))

    session['domain'] = domain

    tenant_session = get_company_db_session(domain)
    email = session.get('email')
    tenant_user = tenant_session.query(TenantUser).filter_by(email=email).first()

    session['user_id'] = tenant_user.id
    session['company_id'] = tenant_user.company_id
    session['role'] = tenant_user.role
    session['email'] = tenant_user.email

    tenant_user.last_login = datetime.utcnow()
    tenant_session.commit()

    return redirect(url_for('register_routes.dashboard'))


@register_routes.route('/validate-otp', methods=['GET', 'POST'])
def validate_otp():
    if request.method == 'POST':
        entered_otp = request.form['otp']
        email = session.get('pending_user_email')
        domain = session.get('pending_company_domain')

        if not email or not domain:
            flash('Session expired. Please register again.', 'danger')
            return redirect(url_for('register_routes.register_company'))

        from app.models.models import TenantOTP, TenantUser, Company
        tenant_session = get_company_db_session(domain)

        otp_record = tenant_session.query(TenantOTP)\
            .filter_by(email=email)\
            .order_by(TenantOTP.created_at.desc())\
            .first()

        if otp_record and otp_record.otp_code == entered_otp:
            # ✅ Activate company
            company = Company.query.get(otp_record.company_id)
            if company:
                company.active_key = True
                db.session.commit()

            # ✅ Store user session from tenant
            user = tenant_session.query(TenantUser)\
                .filter_by(email=email, company_id=otp_record.company_id)\
                .first()

            session['user_id'] = user.id
            session['company_id'] = user.company_id
            session['role'] = user.role

            tenant_session.close()

            # ✅ Send welcome email
            subject = "🎉 Welcome to Pepmytrip Accounting!"
            body = f"""
Hi {email},

Congratulations! Your company account has been successfully registered with Pepmytrip Accounting.

You can now log in and start managing your company's finances.

➡️ Login Page: https://yourdomain/login

Thank you for joining us.

Best regards,  
Pepmytrip Team
"""
            send_email(mail, email, subject, body)

            return redirect(url_for('register_routes.welcome'))
        else:
            flash('Invalid OTP', 'danger')
            return redirect(url_for('register_routes.validate_otp'))

    return render_template('validate_otp.html')

@register_routes.route('/welcome')
def welcome():
    return render_template('welcome.html')




# routes/register_routes.py (append logout and role-based dashboard rendering)
@register_routes.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('register_routes.login'))

@register_routes.route('/dashboard')
def dashboard():
    if 'user_id' not in session or 'domain' not in session:
        flash("Session expired. Please login again.", "danger")
        return redirect(url_for('register_routes.login'))

    domain = session['domain']
    from app.models.models import TenantUser
    tenant_session = get_company_db_session(domain)
    user = tenant_session.query(TenantUser).get(session['user_id'])

    return render_template("dashboard.html", user=user)




@register_routes.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Email not found", "danger")
            return redirect(url_for('register_routes.forgot_password'))

        otp = ''.join(random.choices(string.digits, k=6))
        otp_entry = OTP(email=email, otp_code=otp, company_id=user.company_id)
        db.session.add(otp_entry)
        db.session.commit()

        send_otp_email(mail, email, otp)
        session['reset_email'] = email
        return redirect(url_for('register_routes.reset_otp'))

    return render_template('forgot_password.html')


@register_routes.route('/reset-select-domain')
def reset_select_domain():
    domain = request.args.get('domain')
    email = session.get('reset_email')
    if not domain or not email:
        flash("Missing reset session data", "danger")
        return redirect(url_for('register_routes.forgot_password'))

    session['reset_domain'] = domain

    try:
        tenant_session = get_company_db_session(domain)
        from app.models.models import TenantUser, TenantOTP
        user = tenant_session.query(TenantUser).filter_by(email=email).first()

        if user:
            otp = ''.join(random.choices(string.digits, k=6))
            otp_entry = TenantOTP(email=email, otp_code=otp, company_id=user.company_id)
            tenant_session.add(otp_entry)
            tenant_session.commit()

            send_otp_email(mail, email, otp)
            return redirect(url_for('register_routes.reset_otp'))
        else:
            flash("Email not found in selected domain", "danger")
            return redirect(url_for('register_routes.forgot_password'))

    except Exception as e:
        flash(f"Database error: {e}", "danger")
        return redirect(url_for('register_routes.forgot_password'))



@register_routes.route('/set-new-password', methods=['GET', 'POST'])
def set_new_password():
    if request.method == 'POST':
        email = session.get('reset_email')
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user:
            user.password = bcrypt.generate_password_hash(password).decode('utf-8')
            db.session.commit()

            # Clean session
            session.pop('reset_email', None)
            session.pop('otp_validated', None)

            flash("Password updated. You can now log in.", "success")
            return redirect(url_for('register_routes.login'))

    return render_template('set_new_password.html')


@register_routes.route('/reset-otp', methods=['GET', 'POST'])
def reset_otp():
    if request.method == 'POST':
        email = session.get('reset_email')
        otp_entered = request.form['otp']

        otp_record = OTP.query.filter_by(email=email).order_by(OTP.created_at.desc()).first()

        if otp_record and otp_record.otp_code == otp_entered:
            session['otp_validated'] = True
            return redirect(url_for('register_routes.set_new_password'))
        else:
            flash("Invalid OTP", "danger")
            return redirect(url_for('register_routes.reset_otp'))

    return render_template('reset_otp.html')



@register_routes.route('/users', methods=['GET', 'POST'])
def user_list():
    if 'user_id' not in session or 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    # Only SuperXuser or Admin can view/manage users
    role = session.get('role')
    if role not in ['SuperXuser', 'Admin']:
        abort(403)

    domain = session['domain']
    company_id = session['company_id']
    tenant_session = get_company_db_session(domain)

    if request.method == 'POST':
        email = request.form['email']
        role_form = request.form['role']
        token = secrets.token_hex(32)

        invite = UserInvite(email=email, role=role_form, token=token, company_id=company_id)
        db.session.add(invite)
        db.session.commit()

        invite_link = url_for('register_routes.accept_invite', token=token, _external=True)
        send_otp_email(mail, email, f"You've been invited! Set your password: {invite_link}")
        flash("Invitation sent!", "success")

    tenant_users = tenant_session.query(TenantUser).filter_by(company_id=company_id).all()
    user_list = [
        {
            'id': u.id,
            'email': u.email,
            'role': u.role,
            'last_login': u.last_login,
            'is_suspended': u.is_suspended
        } for u in tenant_users
    ]

    invites = UserInvite.query.filter_by(company_id=company_id).all()
    return render_template('user_list.html', users=user_list, invites=invites)


@register_routes.route('/resend-invite/<int:invite_id>')
def resend_invite(invite_id):
    if 'user_id' not in session or 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    role = session.get('role')
    if role not in ['SuperXuser', 'Admin']:
        abort(403)

    invite = UserInvite.query.filter_by(id=invite_id, is_used=False).first_or_404()
    invite_link = url_for('register_routes.accept_invite', token=invite.token, _external=True)
    send_otp_email(mail, invite.email, f"You've been invited! Set your password: {invite_link}")
    flash("Invitation resent!", "info")
    return redirect(url_for('register_routes.user_list'))




@register_routes.route('/accept-invite/<token>', methods=['GET', 'POST'])
def accept_invite(token):
    invite = UserInvite.query.filter_by(token=token, is_used=False).first_or_404()
    print("DEBUG INVITE COMPANY_ID:", invite.company_id)
    
    # Try both Company and MasterCompany for safety
    company = Company.query.filter_by(id=invite.company_id).first()
    if not company:
        company = MasterCompany.query.filter_by(id=invite.company_id).first()
    print("DEBUG LOOKED UP COMPANY:", company)

    if not company:
        flash("The company associated with this invite no longer exists.", "danger")
        return redirect(url_for('register_routes.login'))

    existing_user = User.query.filter_by(email=invite.email).first()

    if request.method == 'POST':
        password = request.form['password']

        if existing_user:
            if not bcrypt.check_password_hash(existing_user.password, password):
                flash("Invalid password for existing user", "danger")
                return redirect(request.url)
        else:
            hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
            existing_user = User(
                email=invite.email,
                password=hashed_pw,
                role=invite.role,
                company_id=invite.company_id
            )
            db.session.add(existing_user)
            db.session.commit()

        domain = company.domain  # works for both Company and MasterCompany
        tenant_session = get_company_db_session(domain)
        from app.models.models import TenantUser

        existing_tenant_user = tenant_session.query(TenantUser).filter_by(email=invite.email).first()
        if not existing_tenant_user:
            tenant_user = TenantUser(
                email=invite.email,
                password=existing_user.password,
                role=invite.role,
                company_id=invite.company_id
            )
            tenant_session.add(tenant_user)
            tenant_session.commit()

        invite.is_used = True
        db.session.commit()
        flash("Access granted. You can now log in.", "success")
        return redirect(url_for('register_routes.login'))

    return render_template(
        'accept_existing_or_new.html',
        existing=bool(existing_user),
        email=invite.email
    )





@register_routes.route('/users/suspend/<int:user_id>')
def suspend_user(user_id):
    if 'domain' not in session:
        flash("Invalid session", "danger")
        return redirect(url_for('register_routes.login'))

    domain = session['domain']
    company_id = session['company_id']
    tenant_session = get_company_db_session(domain)

    user = tenant_session.query(TenantUser).filter_by(id=user_id, company_id=company_id).first()
    if not user:
        abort(404)

    # 🔐 Prevent SuperXuser (case-insensitive)
    if user.role.strip().lower() == 'superxuser':
        flash("SuperXuser cannot be suspended.", "danger")
        return redirect(url_for('register_routes.user_list'))

    user.is_suspended = True
    tenant_session.commit()
    flash("User suspended successfully.", "warning")
    return redirect(url_for('register_routes.user_list'))






@register_routes.route('/users/unsuspend/<int:user_id>')
def unsuspend_user(user_id):
    if 'domain' not in session:
        flash("Invalid session", "danger")
        return redirect(url_for('register_routes.login'))

    domain = session['domain']
    company_id = session['company_id']
    tenant_session = get_company_db_session(domain)

    user = tenant_session.query(TenantUser).filter_by(id=user_id, company_id=company_id).first()
    if not user:
        abort(404)

    user.is_suspended = False
    tenant_session.commit()
    flash("User activated successfully.", "success")
    return redirect(url_for('register_routes.user_list'))




@register_routes.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    domain = session.get('domain')
    tenant_session = get_company_db_session(domain)
    # Fetch the tenant user using the TenantUser model instead of the core User model
    user = tenant_session.get(TenantUser, user_id)
    if not user:
        abort(404)
    if request.method == 'POST':
        user.role = request.form['role']
        tenant_session.commit()
        flash('User role updated.', 'success')
        return redirect(url_for('register_routes.user_list'))
    return render_template('edit_user.html', user=user)

def current_tenant_session():
    domain = session.get('domain')
    return get_company_db_session(domain)


# Example country and currency lists
def get_country_list():
    return ['Sri Lanka', 'India', 'USA', 'UK', 'Australia']  # extend as needed

def get_currency_list():
    return ['LKR', 'INR', 'USD', 'GBP', 'AUD']  # extend as needed

@register_routes.route('/profile-settings', methods=['GET', 'POST'])
def profile_settings():
    if 'user_id' not in session or 'domain' not in session:
        return redirect(url_for('register_routes.login'))

    tenant_session = current_tenant_session()
    company_id = session['company_id']
    user_email = session['email']
    user_id = session['user_id']
    user_role = session.get('role')

    company = tenant_session.query(CompanyProfile).filter_by(company_id=company_id).first()
    user = tenant_session.query(UserProfile).filter_by(user_id=user_id).first()

    if request.method == 'POST':
        profile_type = request.form.get('profile_type')

        if profile_type == 'company':
            if not company:
                company = CompanyProfile(company_id=company_id)

            company.company_name = request.form['company_name']
            company.trading_name = request.form['trading_name']
            company.country = request.form['country']
            company.address_line_1 = request.form['address_line1']
            company.address_line_2 = request.form['address_line2']
            company.city = request.form['city']
            company.currency_code = request.form['default_currency']
            company.phone = request.form['phone']
            company.email = request.form['email']
            company.website = request.form['website']
            # TODO: Handle logo upload

            try:
                tenant_session.add(company)
                tenant_session.commit()

                # ✅ Automatically create default accounts after update
                from app.routes.accounting_routes import create_default_accounts
                create_default_accounts(
                    tenant_session=tenant_session,
                    company_id=company_id,
                    created_by=user_id
                )

                flash("✅ Company profile updated and default accounts created.", "success")
            except Exception as e:
                tenant_session.rollback()
                flash(f"❌ Failed to update company: {str(e)}", "danger")

        elif profile_type == 'user':
            if not user:
                user = UserProfile(user_id=user_id, email=user_email)

            user.full_name = request.form['full_name']
            user.dob = datetime.strptime(request.form['dob'], "%Y-%m-%d") if request.form['dob'] else None
            user.phone = request.form['phone']

            try:
                tenant_session.add(user)
                tenant_session.commit()
                flash("✅ User profile updated.", "success")
            except Exception as e:
                tenant_session.rollback()
                flash(f"❌ Failed to update user: {str(e)}", "danger")

        return redirect(url_for('register_routes.profile_settings'))

    # Dropdown data (replace with real list if dynamic)
    countries = ["Sri Lanka", "India", "Singapore", "UAE"]
    currencies = ["LKR", "INR", "SGD", "AED", "USD"]

    return render_template(
        "profile_settings.html",
        company=company,
        user=user,
        role=user_role,
        countries=countries,
        currencies=currencies
    )


