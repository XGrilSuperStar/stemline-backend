"""
Stemline Backend — Upload a song, get back split stems
=========================================================

This is a real, working backend. It accepts an audio file upload,
runs it through Demucs (the AI stem separator), and lets the person
download a zip of the 4 separated tracks.

HOW TO RUN LOCALLY (one-time setup):
    pip install fastapi uvicorn python-multipart demucs torchcodec

THEN:
    python main.py

Then open http://localhost:8000/docs to test uploads directly, or
point the Stemline landing page's upload form at this server.

DEPLOYMENT NOTE:
This is built the same way as DataShred101's backend (FastAPI +
Railway). To go live, this deploys to Railway the same way — push
to a GitHub repo connected to a Railway service.

Processing is CPU-heavy: expect roughly 1x the song's length in
processing time on a normal server (a 3-minute song takes about
3 minutes). For a real paid product, an upgraded Railway plan or a
GPU-backed service would speed this up a lot.
"""

import os
import subprocess
import sys
import uuid
import shutil
import zipfile
import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

import bcrypt
import jwt
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session

app = FastAPI(title="Stemline API")

# Allow the landing page (running on any origin during testing) to call this API.
# In production, lock this down to just your real domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Simple in-memory job tracking. A real production version would use
# a database or Redis instead, so jobs survive a server restart.
jobs = {}

# ---------------------------------------------------------------------------
# Database setup (Postgres on Railway). DATABASE_URL is provided automatically
# by Railway once a Postgres database is attached to this project.
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/stemline_db")
if DATABASE_URL.startswith("postgres://"):
    # Railway sometimes gives the old-style prefix; SQLAlchemy needs postgresql://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-railway")
JWT_ALGORITHM = "HS256"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Stem(Base):
    """A saved split job, tied to the user who created it."""
    __tablename__ = "stems"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    track_name = Column(String, nullable=False)
    zip_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    """Reads the 'Authorization: Bearer <token>' header and returns the logged-in user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not logged in.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again.")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user:
        raise HTTPException(status_code=401, detail="Account not found.")
    return user


# ---------------------------------------------------------------------------
# Signup / Login
# ---------------------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def make_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


@app.post("/api/v1/signup")
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="An account with that email already exists.")
    password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    return {"token": make_token(user.id), "email": user.email}


@app.post("/api/v1/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not bcrypt.checkpw(req.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"token": make_token(user.id), "email": user.email}


@app.get("/")
def root():
    return {"status": "Stemline API is running"}


@app.post("/api/v1/split")
async def split_song(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Accepts an uploaded audio file, saves it, and kicks off stem separation.
    Requires a logged-in user (Authorization: Bearer <token> header).
    Returns a job_id the frontend can use to check status and download results.
    """
    allowed_extensions = {".mp3", ".wav", ".m4a", ".flac"}
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_ext}'. Use MP3, WAV, M4A, or FLAC."
        )

    job_id = str(uuid.uuid4())
    saved_path = UPLOADS_DIR / f"{job_id}{file_ext}"

    with open(saved_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    jobs[job_id] = {"status": "processing", "filename": file.filename}

    try:
        # Run Demucs using the 6-stem model — this gives back all 6 stems
        # separately: vocals, drums, bass, guitar, piano, other.
        result = subprocess.run(
            [sys.executable, "-m", "demucs", "-n", "htdemucs_6s", "-o", str(OUTPUT_DIR), str(saved_path)],
            capture_output=True,
            text=True,
            timeout=900  # 15 minute safety limit
        )

        if result.returncode != 0:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = result.stderr[-500:]
            raise HTTPException(status_code=500, detail="Stem separation failed.")

        song_name = saved_path.stem
        stems_folder = OUTPUT_DIR / "htdemucs_6s" / song_name

        if not stems_folder.exists():
            jobs[job_id]["status"] = "error"
            raise HTTPException(status_code=500, detail="Output not found after processing.")

        # Zip all 6 stem files together for a single download
        zip_path = OUTPUT_DIR / f"{job_id}_stems.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for stem_file in stems_folder.glob("*.wav"):
                zf.write(stem_file, arcname=stem_file.name)

        jobs[job_id]["status"] = "complete"
        jobs[job_id]["zip_path"] = str(zip_path)

        # Permanently save this split to the database, tied to this user,
        # so it survives a server restart and shows up in their tape rack.
        stem_row = Stem(
            user_id=user.id,
            track_name=file.filename,
            zip_path=str(zip_path),
        )
        db.add(stem_row)
        db.commit()
        jobs[job_id]["stem_id"] = stem_row.id

    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = "Processing timed out (song may be too long)."
        raise HTTPException(status_code=504, detail="Processing timed out.")

    return {"job_id": job_id, "status": jobs[job_id]["status"]}


@app.get("/api/v1/status/{job_id}")
def check_status(job_id: str, user: User = Depends(get_current_user)):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    return jobs[job_id]


@app.get("/api/v1/download/{job_id}")
def download_stems(job_id: str, user: User = Depends(get_current_user)):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")

    job = jobs[job_id]
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail=f"Job is not complete yet (status: {job['status']}).")

    zip_path = job["zip_path"]
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="stems.zip"
    )


@app.get("/api/v1/my-stems")
def my_stems(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns this user's saved split history — this is what will power the
    'tape rack' in the Remix Room (real saved songs instead of fake demo data).
    """
    rows = db.query(Stem).filter(Stem.user_id == user.id).order_by(Stem.created_at.desc()).all()
    return [
        {"id": s.id, "track_name": s.track_name, "created_at": s.created_at.isoformat()}
        for s in rows
    ]


@app.get("/api/v1/my-stems/{stem_id}/download")
def download_saved_stem(stem_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lets a logged-in user re-download any of their past saved splits."""
    stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user.id).first()
    if not stem_row:
        raise HTTPException(status_code=404, detail="Saved stem not found.")
    return FileResponse(
        stem_row.zip_path,
        media_type="application/zip",
        filename=f"{stem_row.track_name}_stems.zip"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
