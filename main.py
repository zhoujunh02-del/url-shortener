from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import random
import string
from database import SessionLocal, URL, User
from redis_client import redis_client
from auth import (
    hash_password, verify_password,
    create_access_token,
    get_current_user, get_optional_user,
)

app = FastAPI()


class ShortenRequest(BaseModel):
    url: str
    custom_code: str | None = None


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


def generate_short_code():
    chars = string.ascii_letters + string.digits  # a-z A-Z 0-9
    return "".join(random.choices(chars, k=6))


def is_rate_limited(ip: str) -> bool:
    key = f"rate:{ip}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 60)
    return count > 10


@app.post("/register", status_code=201)
def register(body: RegisterRequest):
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == body.username).first():
            raise HTTPException(status_code=409, detail="Username already taken")
        if db.query(User).filter(User.email == body.email).first():
            raise HTTPException(status_code=409, detail="Email already registered")
        user = User(
            username=body.username,
            email=body.email,
            hashed_password=hash_password(body.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"user_id": user.id}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == form.username).first()
        if not user or not verify_password(form.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        token = create_access_token(user_id=user.id, username=user.username)
        return {"access_token": token, "token_type": "bearer"}
    finally:
        db.close()


@app.post("/shorten")
def shorten_url(
    request: Request,
    body: ShortenRequest,
    current_user: dict | None = Depends(get_optional_user),
):
    ip = request.client.host
    if is_rate_limited(ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    if body.custom_code:
        short_code = body.custom_code
        db = SessionLocal()
        existing = db.query(URL).filter(URL.short_code == short_code).first()
        db.close()
        if existing:
            raise HTTPException(status_code=409, detail="Custom code already taken")
    else:
        short_code = generate_short_code()

    user_id = current_user["id"] if current_user else None

    db = SessionLocal()
    try:
        entry = URL(short_code=short_code, original_url=body.url, user_id=user_id)
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    redis_client.setex(short_code, 3600, body.url)
    return {"short_url": f"http://52.205.252.119:8000/{short_code}"}


@app.get("/{short_code}")
def redirect_url(short_code: str):
    original_url = redis_client.get(short_code)
    if original_url:
        redis_client.incr(f"clicks:{short_code}")
        return RedirectResponse(url=original_url, status_code=302)
    db = SessionLocal()
    entry = db.query(URL).filter(URL.short_code == short_code).first()
    db.close()
    if not entry:
        raise HTTPException(status_code=404, detail="Short URL not found")
    redis_client.setex(short_code, 3600, entry.original_url)
    redis_client.incr(f"clicks:{short_code}")
    return RedirectResponse(url=entry.original_url, status_code=302)


@app.get("/stats/{short_code}")
def get_stats(short_code: str):
    clicks = redis_client.get(f"clicks:{short_code}")
    return {"short_code": short_code, "clicks": int(clicks) if clicks else 0}
