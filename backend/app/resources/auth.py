"""Authentication and user administration.

Endpoints
---------
POST /api/auth/login            - exchange username + password for a JWT
POST /api/auth/logout           - record the logout in the audit trail
GET  /api/auth/me               - the signed-in user
POST /api/auth/change-password  - change your own password
GET  /api/auth/users            - list accounts                 (ADMIN)
POST /api/auth/users            - create an account             (ADMIN)
PUT  /api/auth/users/<id>       - update / deactivate an account (ADMIN)
POST /api/auth/users/<id>/reset-password - set a new password   (ADMIN)
GET  /api/auth/login-audit      - recent login activity         (ADMIN)
"""

from datetime import datetime

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields, validate
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..security import create_access_token, current_user, login_required, roles_required

blp = Blueprint("auth", "auth", url_prefix="/api/auth", description="Authentication and users")

ROLES = ("ADMIN", "MANAGER", "STAFF")
MIN_PASSWORD_LENGTH = 8
# Keep the audit list small enough to render without paging.
AUDIT_LIMIT = 100


class LoginSchema(Schema):
    username = fields.String(required=True, validate=validate.Length(min=1, max=80))
    password = fields.String(required=True, validate=validate.Length(min=1))


class UserCreateSchema(Schema):
    username = fields.String(required=True, validate=validate.Length(min=3, max=80))
    full_name = fields.String(required=True, validate=validate.Length(min=1, max=180))
    email = fields.Email(allow_none=True, load_default=None)
    password = fields.String(required=True, validate=validate.Length(min=MIN_PASSWORD_LENGTH))
    role = fields.String(load_default="STAFF", validate=validate.OneOf(ROLES))
    must_change_password = fields.Boolean(load_default=False)


class UserUpdateSchema(Schema):
    full_name = fields.String(validate=validate.Length(min=1, max=180))
    email = fields.Email(allow_none=True)
    role = fields.String(validate=validate.OneOf(ROLES))
    is_active = fields.Boolean()


class PasswordResetSchema(Schema):
    password = fields.String(required=True, validate=validate.Length(min=MIN_PASSWORD_LENGTH))
    must_change_password = fields.Boolean(load_default=False)


class PasswordChangeSchema(Schema):
    current_password = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=MIN_PASSWORD_LENGTH))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hash_password(raw):
    return generate_password_hash(raw, method="pbkdf2:sha256")


def public_user(row):
    """A user record with the password hash stripped out."""
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "full_name": row["full_name"],
        "email": row.get("email"),
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "must_change_password": bool(row.get("must_change_password")),
        "last_login_at": str(row["last_login_at"]) if row.get("last_login_at") else None,
    }


def find_user(username):
    row = db.session.execute(
        text("SELECT * FROM app_users WHERE username=:u"), {"u": username}
    ).fetchone()
    return dict(row._mapping) if row else None


def record_audit(username, event_type, success, user_id=None, detail=None):
    """Write one row to the login audit trail.

    Auditing must never break the request that triggered it, so failures here are
    swallowed; the caller's own transaction is rolled back to stay usable.
    """
    try:
        db.session.execute(
            text(
                """INSERT INTO user_login_audit
                    (user_id, username, event_type, success, ip_address, user_agent, detail)
                   VALUES (:uid, :username, :event, :success, :ip, :ua, :detail)"""
            ),
            {
                "uid": user_id,
                "username": username[:80],
                "event": event_type,
                "success": success,
                "ip": (request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:64],
                "ua": (request.headers.get("User-Agent") or "")[:255],
                "detail": (detail or "")[:255] or None,
            },
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@blp.route("/login")
class Login(MethodView):
    @blp.arguments(LoginSchema)
    @blp.response(200)
    def post(self, data):
        username = data["username"].strip()
        user = find_user(username)
        # The same message is returned for an unknown user and a wrong password so
        # the response cannot be used to enumerate valid usernames.
        invalid = "Incorrect username or password"

        if not user or not check_password_hash(user["password_hash"], data["password"]):
            record_audit(
                username,
                "LOGIN_FAILED",
                False,
                user_id=user["id"] if user else None,
                detail="Bad credentials",
            )
            abort(401, message=invalid)

        if not user["is_active"]:
            record_audit(username, "LOGIN_FAILED", False, user_id=user["id"], detail="Inactive")
            abort(403, message="This account has been deactivated")

        token, expires_at = create_access_token(user)
        # Bound as a parameter rather than NOW() so the statement is portable.
        db.session.execute(
            text("UPDATE app_users SET last_login_at=:now WHERE id=:id"),
            {"now": datetime.now(), "id": user["id"]},
        )
        db.session.commit()
        record_audit(username, "LOGIN", True, user_id=user["id"])
        return {"access_token": token, "expires_at": expires_at, "user": public_user(user)}


@blp.route("/logout")
class Logout(MethodView):
    @login_required
    @blp.response(200)
    def post(self):
        user = current_user()
        record_audit(user["username"], "LOGOUT", True, user_id=user["id"])
        # Tokens are stateless, so logout is an audit event; the client discards it.
        return {"message": "Signed out"}


@blp.route("/me")
class Me(MethodView):
    @login_required
    @blp.response(200)
    def get(self):
        return public_user(current_user())


@blp.route("/change-password")
class ChangePassword(MethodView):
    @login_required
    @blp.arguments(PasswordChangeSchema)
    @blp.response(200)
    def post(self, data):
        user = find_user(current_user()["username"])
        if not check_password_hash(user["password_hash"], data["current_password"]):
            abort(400, message="Your current password is incorrect")
        if data["current_password"] == data["new_password"]:
            abort(400, message="The new password must be different")
        db.session.execute(
            text(
                """UPDATE app_users
                   SET password_hash=:h, must_change_password=0 WHERE id=:id"""
            ),
            {"h": hash_password(data["new_password"]), "id": user["id"]},
        )
        db.session.commit()
        record_audit(user["username"], "PASSWORD_CHANGED", True, user_id=user["id"])
        return {"message": "Password updated"}


# ---------------------------------------------------------------------------
# User administration
# ---------------------------------------------------------------------------


@blp.route("/users")
class UserCollection(MethodView):
    @roles_required("ADMIN")
    @blp.response(200)
    def get(self):
        rows = db.session.execute(
            text(
                """SELECT id, username, full_name, email, role, is_active,
                       must_change_password, last_login_at
                   FROM app_users ORDER BY username"""
            )
        ).fetchall()
        return {"items": [public_user(dict(r._mapping)) for r in rows]}

    @roles_required("ADMIN")
    @blp.arguments(UserCreateSchema)
    @blp.response(201)
    def post(self, data):
        username = data["username"].strip().lower()
        if find_user(username):
            abort(409, message="That username is already taken")
        db.session.execute(
            text(
                """INSERT INTO app_users
                    (username, full_name, email, password_hash, role,
                     must_change_password, created_by)
                   VALUES (:u, :n, :e, :h, :r, :mcp, :by)"""
            ),
            {
                "u": username,
                "n": data["full_name"].strip(),
                "e": data.get("email"),
                "h": hash_password(data["password"]),
                "r": data["role"],
                "mcp": data["must_change_password"],
                "by": current_user()["id"],
            },
        )
        db.session.commit()
        return public_user(find_user(username))


@blp.route("/users/<int:user_id>")
class UserResource(MethodView):
    @roles_required("ADMIN")
    @blp.arguments(UserUpdateSchema)
    @blp.response(200)
    def put(self, data, user_id):
        row = db.session.execute(
            text("SELECT * FROM app_users WHERE id=:id"), {"id": user_id}
        ).fetchone()
        if not row:
            abort(404, message="User not found")
        existing = dict(row._mapping)

        # Guard against an admin locking themselves, or everyone, out.
        if user_id == current_user()["id"]:
            if data.get("is_active") is False:
                abort(400, message="You cannot deactivate your own account")
            if data.get("role") and data["role"] != existing["role"]:
                abort(400, message="You cannot change your own role")
        if (data.get("is_active") is False or data.get("role") not in (None, "ADMIN")) and existing[
            "role"
        ] == "ADMIN":
            remaining = db.session.execute(
                text(
                    "SELECT COUNT(*) FROM app_users WHERE role='ADMIN' AND is_active=1 AND id<>:id"
                ),
                {"id": user_id},
            ).scalar()
            if not remaining:
                abort(400, message="At least one active administrator must remain")

        fields_to_set = {k: v for k, v in data.items() if k in UserUpdateSchema().fields}
        if not fields_to_set:
            return public_user(existing)
        assignments = ", ".join(f"{k}=:{k}" for k in fields_to_set)
        db.session.execute(
            text(f"UPDATE app_users SET {assignments} WHERE id=:id"),
            {**fields_to_set, "id": user_id},
        )
        db.session.commit()
        updated = db.session.execute(
            text("SELECT * FROM app_users WHERE id=:id"), {"id": user_id}
        ).fetchone()
        return public_user(dict(updated._mapping))


@blp.route("/users/<int:user_id>/reset-password")
class UserPasswordReset(MethodView):
    @roles_required("ADMIN")
    @blp.arguments(PasswordResetSchema)
    @blp.response(200)
    def post(self, data, user_id):
        row = db.session.execute(
            text("SELECT username FROM app_users WHERE id=:id"), {"id": user_id}
        ).fetchone()
        if not row:
            abort(404, message="User not found")
        db.session.execute(
            text("UPDATE app_users SET password_hash=:h, must_change_password=:mcp WHERE id=:id"),
            {
                "h": hash_password(data["password"]),
                "mcp": data["must_change_password"],
                "id": user_id,
            },
        )
        db.session.commit()
        record_audit(
            row._mapping["username"],
            "PASSWORD_CHANGED",
            True,
            user_id=user_id,
            detail=f"Reset by {current_user()['username']}",
        )
        return {"message": "Password reset"}


@blp.route("/login-audit")
class LoginAudit(MethodView):
    @roles_required("ADMIN")
    @blp.response(200)
    def get(self):
        rows = db.session.execute(
            text(
                """SELECT id, user_id, username, event_type, success,
                       ip_address, detail, created_at
                   FROM user_login_audit
                   ORDER BY created_at DESC, id DESC
                   LIMIT :lim"""
            ),
            {"lim": AUDIT_LIMIT},
        ).fetchall()
        return {
            "items": [
                {
                    **dict(r._mapping),
                    "id": int(r._mapping["id"]),
                    "success": bool(r._mapping["success"]),
                    "created_at": str(r._mapping["created_at"]),
                }
                for r in rows
            ]
        }
