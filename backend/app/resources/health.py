from flask_smorest import Blueprint

blp = Blueprint("health", "health", url_prefix="/api", description="Health checks")


@blp.route("/health")
def health():
    return {"status": "ok", "service": "bright-scaff-api"}
