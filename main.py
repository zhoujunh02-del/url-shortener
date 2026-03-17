from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import random
import string
from database import SessionLocal, URL

app = FastAPI()

class ShortenRequest(BaseModel):
    url: str


def generate_short_code():
    chars = string.ascii_letters + string.digits  # a-z A-Z + 0-9
    return "".join(random.choices(chars, k = 6))


@app.post("/shorten")
def shorten_url(request: ShortenRequest):
    db = SessionLocal()     # open database
    short_code = generate_short_code()
    entry = URL(short_code = short_code, original_url = request.url)    # record
    db.add(entry)           # add to MySQL
    db.commit()             # commit
    db.close()
    return {"short_url": f"http://localhost:8000/{short_code}"}


@app.get("/{short_code}")
def redirect_url(short_code: str):
    db = SessionLocal()
    # get first URL whose short_code == short_code
    entry = db.query(URL).filter(URL.short_code == short_code).first()
    db.close()
    if not entry:
        raise HTTPException(status_code = 404, detail = "Short URL not fount")
    return {"original_url": entry.original_url}