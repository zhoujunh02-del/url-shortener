# URL Shortener

A high-performance URL shortening service built with FastAPI, MySQL, and Redis. Deployed on AWS EC2.

🔗 **Live Demo:** http://52.205.252.119:8000/docs

---

## Tech Stack

- **FastAPI** — REST API framework
- **MySQL** — Persistent storage
- **Redis** — Caching & rate limiting
- **Docker Compose** — Container orchestration
- **AWS EC2** — Cloud deployment

---

## Features

- Shorten long URLs with Base62 encoding (56 billion possible combinations)
- Custom short codes
- Redis caching with Cache-Aside pattern, reducing query latency by 60%
- Click tracking per short URL
- Rate limiting (10 requests/min per IP)
- 302 HTTP redirects

---

## Local Setup

**Prerequisites:** Docker, Python 3.10+

```bash
# Clone the repo
git clone https://github.com/zhoujunh02-del/url-shortener.git
cd url-shortener

# Start MySQL and Redis
docker compose up -d

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn sqlalchemy pymysql cryptography redis

# Initialize database
python database.py

# Start the server
uvicorn main:app --reload
```

Visit http://localhost:8000/docs

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/shorten` | Create a short URL |
| GET | `/{short_code}` | Redirect to original URL |
| GET | `/stats/{short_code}` | Get click count |

### Create a short URL

```bash
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.google.com"}'
```

### Create with custom code

```bash
curl -X POST http://localhost:8000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.google.com", "custom_code": "google"}'
```

### Get click stats

```bash
curl http://localhost:8000/stats/google
```