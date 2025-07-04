from app import create_app, db
from flask_migrate import Migrate


app = create_app()
migrate = Migrate(app, db)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    # ``app.run`` defaults to enabling the debugger's automatic reloader
    # when ``debug=True``.  In some SSH environments ``stdin`` is not a
    # real TTY which causes Werkzeug's reloader to fail with a
    # ``termios.error``.  Disable the reloader so the server starts
    # reliably when launched remotely.
    app.run(
        host="0.0.0.0",  # allow external connections if the port is open
        port=5000,
        debug=True,
        use_reloader=False,
    )
