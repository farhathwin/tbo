from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_session import Session
from flask_migrate import Migrate
import os
from dotenv import load_dotenv


# Absolute path to the repository root.  Used to locate the migrations
# directory and the optional ``.env`` file.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Load environment variables from ".env".  Some older setups used a file
# named just "env" so fall back to that if the new file does not exist.
dotenv_path = os.path.join(BASE_DIR, ".env")
if not os.path.exists(dotenv_path):
    legacy_env = os.path.join(BASE_DIR, "env")
    if os.path.exists(legacy_env):
        dotenv_path = legacy_env
load_dotenv(dotenv_path)

db = SQLAlchemy()
bcrypt = Bcrypt()
mail = Mail()
sess = Session()
migrations_dir = os.path.join(BASE_DIR, "migrations")
migrate = Migrate(directory=migrations_dir)

def create_app(db_uri_override=None):
    app = Flask(__name__)

    # Main database config
    env_db = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri_override or env_db
    if not app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError('SQLALCHEMY_DATABASE_URI must be configured')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key_here')
    app.config['SESSION_TYPE'] = 'filesystem'

    # Mail config
    app.config['MAIL_SERVER'] = 'mail.smtp2go.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
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

    from app.routes.admin_routes import admin_routes
    app.register_blueprint(admin_routes)

    # Shell context
    @app.shell_context_processor
    def make_shell_context():
        return {'db': db}

    return app
