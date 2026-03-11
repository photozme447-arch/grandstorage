from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import bcrypt as _bcrypt
from datetime import datetime, timedelta
from pathlib import Path
import aiofiles
import os, shutil, mimetypes, uuid, json, time

app = FastAPI(title="CloudStore")

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
SECRET_KEY = "533289"
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24

# On Railway: set UPLOAD_ROOT=/data in env vars → uses persistent volume
# Locally: falls back to ./uploads
UPLOAD_ROOT = Path(os.environ.get("UPLOAD_ROOT", str(BASE_DIR / "uploads")))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# users.json and shares.json also live in the persistent volume on Railway
DATA_DIR = UPLOAD_ROOT.parent

# ── Auth ────────────────────────────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

def verify_password(plain, hashed): return _bcrypt.checkpw(plain.encode(), hashed.encode())
def hash_password(password): return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

# Simple file-based user store
USERS_FILE = DATA_DIR / "users.json"

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    users = {"admin": {"hashed_password": hash_password("admin123"), "email": "admin@cloudstore.local"}}
    USERS_FILE.write_text(json.dumps(users), encoding="utf-8")
    return users

def save_users(users):
    USERS_FILE.write_text(json.dumps(users), encoding="utf-8")

def create_token(username: str):
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

def require_user(username: str = Depends(get_current_user)):
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return username

def user_root(username: str) -> Path:
    p = UPLOAD_ROOT / username
    p.mkdir(exist_ok=True)
    return p

# ── Share links ─────────────────────────────────────────────────────────────────
SHARES_FILE = DATA_DIR / "shares.json"

def load_shares():
    if SHARES_FILE.exists():
        return json.loads(SHARES_FILE.read_text(encoding="utf-8"))
    return {}

def save_shares(shares):
    SHARES_FILE.write_text(json.dumps(shares), encoding="utf-8")

# ── Routes: Auth ────────────────────────────────────────────────────────────────
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    users = load_users()
    user = users.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_token(form_data.username)
    return {"access_token": token, "token_type": "bearer"}

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...), email: str = Form(...)):
    users = load_users()
    if username in users:
        raise HTTPException(status_code=400, detail="Username already exists")
    users[username] = {"hashed_password": hash_password(password), "email": email}
    save_users(users)
    user_root(username)
    token = create_token(username)
    return {"access_token": token, "token_type": "bearer"}

# ── Routes: Files ───────────────────────────────────────────────────────────────
@app.get("/api/files")
async def list_files(path: str = "", username: str = Depends(require_user)):
    root = user_root(username)
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=403)
    if not target.exists():
        raise HTTPException(status_code=404)
    items = []
    for item in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        rel = str(item.relative_to(root))
        stat = item.stat()
        items.append({
            "name": item.name,
            "path": rel,
            "is_dir": item.is_dir(),
            "size": stat.st_size if item.is_file() else 0,
            "modified": stat.st_mtime,
            "mime": mimetypes.guess_type(item.name)[0] or "application/octet-stream" if item.is_file() else None
        })
    return {"items": items, "current_path": path}

@app.post("/api/upload")
async def upload(path: str = Form(""), files: list[UploadFile] = File(...), username: str = Depends(require_user)):
    root = user_root(username)
    target_dir = (root / path).resolve()
    if not str(target_dir).startswith(str(root)):
        raise HTTPException(status_code=403)
    target_dir.mkdir(parents=True, exist_ok=True)
    uploaded = []
    for file in files:
        dest = target_dir / file.filename
        async with aiofiles.open(dest, "wb") as f:
            content = await file.read()
            await f.write(content)
        uploaded.append(file.filename)
    return {"uploaded": uploaded}

@app.get("/api/download")
async def download(path: str, username: str = Depends(require_user)):
    root = user_root(username)
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target, filename=target.name)

@app.delete("/api/delete")
async def delete_item(path: str, username: str = Depends(require_user)):
    root = user_root(username)
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.exists():
        raise HTTPException(status_code=404)
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"deleted": path}

@app.post("/api/mkdir")
async def make_dir(path: str = Form(...), name: str = Form(...), username: str = Depends(require_user)):
    root = user_root(username)
    new_dir = (root / path / name).resolve()
    if not str(new_dir).startswith(str(root)):
        raise HTTPException(status_code=403)
    new_dir.mkdir(parents=True, exist_ok=True)
    return {"created": name}

@app.post("/api/rename")
async def rename(old_path: str = Form(...), new_name: str = Form(...), username: str = Depends(require_user)):
    root = user_root(username)
    old = (root / old_path).resolve()
    new = (old.parent / new_name).resolve()
    if not str(old).startswith(str(root)) or not old.exists():
        raise HTTPException(status_code=404)
    old.rename(new)
    return {"renamed": new_name}

@app.get("/api/search")
async def search(q: str, username: str = Depends(require_user)):
    root = user_root(username)
    results = []
    for item in root.rglob(f"*{q}*"):
        rel = str(item.relative_to(root))
        results.append({
            "name": item.name,
            "path": rel,
            "is_dir": item.is_dir(),
            "size": item.stat().st_size if item.is_file() else 0,
            "mime": mimetypes.guess_type(item.name)[0] or "" if item.is_file() else None
        })
    return {"results": results[:50]}

# ── Routes: Sharing ─────────────────────────────────────────────────────────────
@app.post("/api/share")
async def create_share(path: str = Form(...), username: str = Depends(require_user)):
    root = user_root(username)
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(status_code=404)
    shares = load_shares()
    link_id = str(uuid.uuid4())[:8]
    shares[link_id] = {"username": username, "path": path, "created": time.time()}
    save_shares(shares)
    return {"link_id": link_id}

@app.get("/share/{link_id}")
async def access_share(link_id: str):
    shares = load_shares()
    share = shares.get(link_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share link not found or expired")
    root = user_root(share["username"])
    target = (root / share["path"]).resolve()
    if not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target, filename=target.name)

# ── Routes: Stats ────────────────────────────────────────────────────────────────
@app.get("/api/stats")
async def stats(username: str = Depends(require_user)):
    root = user_root(username)
    total_size = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    total_files = sum(1 for f in root.rglob("*") if f.is_file())
    total_folders = sum(1 for f in root.rglob("*") if f.is_dir())
    return {"total_size": total_size, "total_files": total_files, "total_folders": total_folders}

# ── Serve Frontend ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static") 
