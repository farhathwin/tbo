from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_session import Session
from flask_migrate import Migrate
import os

# Absolute path to the repository root. This ensures that the default
# SQLite database path is resolved correctly regardless of the current
# working directory.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

db = SQLAlchemy()
bcrypt = Bcrypt()
mail = Mail()
sess = Session()
migrations_dir = os.path.join(BASE_DIR, "migrations")
migrate = Migrate(directory=migrations_dir)

def create_app(db_uri_override=None):
    app = Flask(__name__)

    # Main database config
    # Default to the central database stored under ``instance/app.db`` unless
    # overridden by an explicit URI or the ``SQLALCHEMY_DATABASE_URI``
    # environment variable.
    default_db_path = os.path.join(INSTANCE_DIR, 'app.db')
    default_db = f"sqlite:///{default_db_path}"

    env_db = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri_override or env_db or default_db
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your_secret_key_here'
    app.config['SESSION_TYPE'] = 'filesystem'

    # Mail config
    app.config['MAIL_SERVER'] = 'mail.smtp2go.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'buvindu@pepmytrip.com'
    app.config['MAIL_PASSWORD'] = 'viX5o9qBXFAWYXtu'
    app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    sess.init_app(app)
    migrate.init_app(app, db)

    # Register Blueprints
    from app.routes.register_routes import register_routes
    app.register_blueprint(register_routes)

    from app.routes.accounting_routes import accounting_routes
    app.register_blueprint(accounting_routes)

    from app.routes.account_type_routes import account_type_routes
    app.register_blueprint(account_type_routes)

    # Shell context
    @app.shell_context_processor
    def make_shell_context():
        return {'db': db}

    return app
