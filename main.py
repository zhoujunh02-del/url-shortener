from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import random
import string
from database import SessionLocal, URL
from redis_client import redis_client

app = FastAPI()

class ShortenRequest(BaseModel):
    url: str

def generate_short_code():
    chars = string.ascii_letters + string.digits  # a-z A-Z + 0-9
    return "".join(random.choices(chars, k = 6))

def is_rate_limited(ip: str) -> bool:
    key = f"rate:{ip}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 60)
    return count > 10

@app.post("/shorten")
def shorten_url(request: Request, body: ShortenRequest):
    ip = request.client.host
    if is_rate_limited(ip):
        raise HTTPException(status_code=429, detail="Too many requests")
    
    db = SessionLocal()     # open database
    try:
        short_code = generate_short_code()
        entry = URL(short_code = short_code, original_url = body.url)    # record
        db.add(entry)           # add to MySQL
        db.commit()             # commit
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    redis_client.setex(short_code, 3600, body.url)
    return {"short_url": f"http://localhost:8000/{short_code}"}


@app.get("/{short_code}")
def redirect_url(short_code: str):
    orginal_url = redis_client.get(short_code)
    if orginal_url:
        redis_client.incr(f"clicks:{short_code}")
        return RedirectResponse(url=orginal_url, status_code=302)
    db = SessionLocal()
    # get first URL whose short_code == short_code
    entry = db.query(URL).filter(URL.short_code == short_code).first()
    db.close()
    if not entry:
        raise HTTPException(status_code = 404, detail = "Short URL not found")
    redis_client.setex(short_code, 3600, entry.original_url)
    redis_client.incr(f"clicks:{short_code}")
    return RedirectResponse(url=entry.original_url, status_code=302)

@app.get("/stats/{short_code}")
def get_stats(short_code: str):
    clicks = redis_client.get(f"clicks:{short_code}")
    return {"short_code": short_code, "clicks": int(clicks) if clicks else 0}