from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import os
import random
import string
import time
import uuid
from pybloom_live import ScalableBloomFilter
from database import SessionLocal, URL, User
from redis_client import redis_client
from auth import (
    hash_password, verify_password,
    create_access_token,
    get_current_user, get_optional_user,
)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

app = FastAPI()

# Bloom filter seeded from existing short codes on startup
bloom = ScalableBloomFilter(mode=ScalableBloomFilter.SMALL_SET_GROWTH, error_rate=0.001)

def _init_bloom():
    db = SessionLocal()
    try:
        for (code,) in db.query(URL.short_code).all():
            bloom.add(code)
    finally:
        db.close()

_init_bloom()


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


RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('zremrangebyscore', key, 0, now - window)
redis.call('zadd', key, now, member)
local count = redis.call('zcard', key)
redis.call('expire', key, window)
return count
"""

def is_rate_limited(ip: str) -> bool:
    key = f"rate:{ip}"
    now = time.time()
    window = 60
    limit = 10
    count = redis_client.eval(RATE_LIMIT_SCRIPT, 1, key, now, window, limit, str(uuid.uuid4()))
    return count > limit


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
        if len(body.custom_code) > 6:
            raise HTTPException(status_code=422, detail="Custom code must be 6 characters or fewer")
        short_code = body.custom_code
        if short_code in bloom:
            db = SessionLocal()
            existing = db.query(URL).filter(URL.short_code == short_code).first()
            db.close()
            if existing:
                raise HTTPException(status_code=409, detail="Custom code already taken")
    else:
        for _ in range(5):
            short_code = generate_short_code()
            if short_code not in bloom:
                break
        else:
            raise HTTPException(status_code=500, detail="Failed to generate unique short code")

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

    bloom.add(short_code)
    redis_client.setex(short_code, 3600, body.url)
    return {"short_url": f"{BASE_URL}/{short_code}"}


@app.get("/{short_code}")
def redirect_url(short_code: str):
    if short_code not in bloom:
        raise HTTPException(status_code=404, detail="Short URL not found")
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
