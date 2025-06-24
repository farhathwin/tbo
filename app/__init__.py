from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_session import Session
from flask_migrate import Migrate
import os

db = SQLAlchemy()
bcrypt = Bcrypt()
mail = Mail()
sess = Session()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    # Main database config
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your_secret_key_here'
    app.config['SESSION_TYPE'] = 'filesystem'

    # Mail config
    app.config['MAIL_SERVER'] = 'mail.smtp2go.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'info@mleasd.com'
    app.config['MAIL_PASSWORD'] = 'b4lCoLJnCyUJTL2Z988'
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
