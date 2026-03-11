# ☁ CloudStore — Your Personal Cloud Storage

A self-hosted cloud storage web app built with **FastAPI** (Python) + a sleek dark frontend.

## Features
- 🔐 User authentication (JWT tokens)
- ⬆️ Upload files (drag & drop or click)
- ⬇️ Download files
- 📁 Folder organization with full navigation
- 🔗 Share files via public links
- 🔍 Search files by name
- 👁 Preview images, videos, and text files
- ✏️ Rename and delete files/folders
- 📊 Storage usage dashboard
- 🎨 Filter by type (images, videos, documents, archives)

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Open in browser
```
http://localhost:8000
```

### Default Login
- **Username:** `admin`
- **Password:** `admin123`

> ⚠️ Change the default password after first login by registering a new account.

## Project Structure
```
cloudstore/
├── main.py           # FastAPI backend (all routes)
├── requirements.txt  # Python dependencies
├── users.json        # User store (auto-created)
├── shares.json       # Share links (auto-created)
├── uploads/          # Your files live here
│   └── {username}/   # Per-user storage
└── static/
    └── index.html    # Full frontend
```

## Security Notes
- Change `SECRET_KEY` in `main.py` before deploying
- For production, use HTTPS (e.g., put Nginx in front)
- The `uploads/` directory is protected — files only accessible to their owner
- Share links are public but random (8-char UUID prefix)

## Running in Production
```bash
# With Gunicorn
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Or with Docker
docker run -p 8000:8000 -v ./uploads:/app/uploads your-image
```
