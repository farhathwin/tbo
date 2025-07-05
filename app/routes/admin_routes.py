from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash

from app import db, bcrypt
from app.models.models import Admin, MasterCompany

admin_routes = Blueprint('admin_routes', __name__)


# Helper to ensure admin account exists with predefined credentials
DEFAULT_ADMIN_EMAIL = 'farhathwin@gmail.com'
DEFAULT_ADMIN_PASSWORD = 'admin123'

@admin_routes.before_app_request
def ensure_admin_exists():
    """Ensure a default admin account exists once per app lifecycle."""
    if not current_app.config.get("_admin_initialized"):
        admin = Admin.query.filter_by(email=DEFAULT_ADMIN_EMAIL).first()
        if not admin:
            hashed = bcrypt.generate_password_hash(
                DEFAULT_ADMIN_PASSWORD
            ).decode("utf-8")
            admin = Admin(email=DEFAULT_ADMIN_EMAIL, password=hashed)
            db.session.add(admin)
            db.session.commit()
        current_app.config["_admin_initialized"] = True


@admin_routes.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        admin = Admin.query.filter_by(email=email).first()
        if admin and check_password_hash(admin.password, password):
            session['admin_id'] = admin.id
            return redirect(url_for('admin_routes.admin_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('admin_login.html')


@admin_routes.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    return redirect(url_for('admin_routes.admin_login'))


@admin_routes.route('/admin')
def admin_dashboard():
    if not session.get('admin_id'):
        return redirect(url_for('admin_routes.admin_login'))

    companies = MasterCompany.query.order_by(MasterCompany.created_at.desc()).all()
    return render_template('admin_dashboard.html', companies=companies)
