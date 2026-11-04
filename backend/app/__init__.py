import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_smorest import Api
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()
db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config.update(
        API_TITLE="BRIGHT SCAFF Rental Management API",
        API_VERSION="v1",
        OPENAPI_VERSION="3.0.3",
        OPENAPI_URL_PREFIX="/",
        OPENAPI_SWAGGER_UI_PATH="/docs",
        OPENAPI_SWAGGER_UI_URL="https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://bright_app:change_me@127.0.0.1:3306/bright_scaff?charset=utf8mb4",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-this"),
    )
    CORS(
        app,
        resources={r"/api/*": {"origins": os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")}},
        # The frontend sends the JWT in an Authorization header, which must be
        # allowed explicitly for cross-origin requests from the Vite dev server.
        allow_headers=["Content-Type", "Authorization"],
    )
    db.init_app(app)
    api = Api(app)
    from .resources.health import blp as health_blp
    from .resources.auth import blp as auth_blp
    from .resources.customers import blp as customers_blp
    from .resources.items import blp as items_blp
    from .resources.dashboard import blp as dashboard_blp
    from .resources.rentals import blp as rentals_blp
    from .resources.ledgers import blp as ledgers_blp
    from .resources.reports import blp as reports_blp

    for blueprint in (
        health_blp,
        auth_blp,
        customers_blp,
        items_blp,
        dashboard_blp,
        rentals_blp,
        ledgers_blp,
        reports_blp,
    ):
        api.register_blueprint(blueprint)

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"message": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(_):
        db.session.rollback()
        return jsonify({"message": "Internal server error"}), 500

    return app
