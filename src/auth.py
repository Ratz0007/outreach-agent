"""Authentication utilities — password hashing, session management."""

import json
from datetime import datetime
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from src.db.session import get_session
from src.db.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Secret key for signing session cookies
SESSION_SECRET = "outreach-agent-session-key-2024"
SESSION_MAX_AGE = 86400 * 7  # 7 days
serializer = URLSafeTimedSerializer(SESSION_SECRET)

COOKIE_NAME = "oa_session"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"uid": user_id})


def verify_session_token(token: str) -> int | None:
    """Returns user_id if valid, None otherwise."""
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("uid")
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(request) -> User | None:
    """Get user from session cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = verify_session_token(token)
    if not user_id:
        return None
    session = get_session()
    try:
        return session.get(User, user_id)
    finally:
        session.close()


def register_user(username: str, email: str, password: str, full_name: str = "") -> User | str:
    """Register a new user. Returns User or error string."""
    session = get_session()
    try:
        # Check duplicates
        existing = session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing:
            if existing.username == username:
                return "Username already taken"
            return "Email already registered"

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            settings=json.dumps({}),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def authenticate_user(username: str, password: str) -> User | None:
    """Authenticate and return user, or None."""
    session = get_session()
    try:
        user = session.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            return None
        user.last_login = datetime.utcnow()
        session.commit()
        return user
    finally:
        session.close()


def get_user_settings(user_id: int) -> dict:
    """Get user settings dict."""
    session = get_session()
    try:
        user = session.get(User, user_id)
        if user and user.settings:
            try:
                return json.loads(user.settings)
            except json.JSONDecodeError:
                return {}
        return {}
    finally:
        session.close()


def save_user_settings(user_id: int, settings: dict):
    """Save user settings dict."""
    session = get_session()
    try:
        user = session.get(User, user_id)
        if user:
            user.settings = json.dumps(settings)
            session.commit()
    finally:
        session.close()
