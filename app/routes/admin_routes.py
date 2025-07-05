
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
import os
import re
from datetime import datetime
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
        if admin and bcrypt.check_password_hash(admin.password, password):
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


def _parse_airfile_metadata(path: str):
    """Return dict with PNR and date from an AIR file."""
    pnr = None
    dt = None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not pnr and line.startswith("MUC1A"):
                    m = re.search(r"MUC1A\s+([A-Z0-9]{6})", line)
                    if m:
                        pnr = m.group(1)
                if not dt and line.startswith("D-"):
                    m = re.search(r"D-(\d{6})", line)
                    if m:
                        try:
                            dt = datetime.strptime(m.group(1), "%y%m%d").date()
                        except ValueError:
                            dt = None
                if pnr and dt:
                    break
    except OSError:
        pass
    return {"pnr": pnr, "date": dt}



def _parse_filename(name: str):
    info = {"agent_code": None, "pnr": None, "date": None, "filename": name}
    m = re.match(r"([^\-]+)-([A-Z0-9]+)-(\d{6})-(.+)", name)
    if m:
        info["agent_code"] = m.group(1)
        info["pnr"] = m.group(2)
        date_part = m.group(3)
        for fmt in ("%d%m%y", "%y%m%d"):
            try:
                info["date"] = datetime.strptime(date_part, fmt).date()
                break
            except ValueError:
                continue
    return info

def _load_airfiles(agent_code: str | None = None):
    folder = os.path.join(current_app.root_path, "..", "airfiles")
    files = []
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if not name.lower().endswith(".air"):
                continue

            info = _parse_filename(name)
            if agent_code and info["agent_code"] and info["agent_code"] != str(agent_code):
                continue
            if not info["pnr"] or not info["date"]:
                meta = _parse_airfile_metadata(os.path.join(folder, name))
                info["pnr"] = info["pnr"] or meta.get("pnr")
                info["date"] = info["date"] or meta.get("date")
            files.append(info)
    return files


@admin_routes.route("/admin/gds-tray")
def gds_tray():
    if not session.get("admin_id"):
        return redirect(url_for("admin_routes.admin_login"))
    files = _load_airfiles()
    files.sort(key=lambda x: (x["agent_code"], x["filename"]))
    return render_template("gds_tray.html", files=files)
