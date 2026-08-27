from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import shutil
import subprocess
import zipfile
import uuid
import threading
from datetime import datetime, timedelta
import jwt
import bcrypt
import secrets
import hashlib
import smtplib
from email.mime.text import MIMEText
import requests
from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    reset_token_hash = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

class SignupRequest(BaseModel):
    email: str
    username: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotUsernameRequest(BaseModel):
    email: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class Stem(Base):
    __tablename__ = "stems"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    track_name = Column(String)
    zip_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Null for a normal split (zip_path points at the full 6-stem zip).
    # Set for a single-channel save (zip_path points at just that one wav).
    instrument = Column(String, nullable=True)
    # "processing" while Demucs runs in the background, then "done" or
    # "error". Old rows (created before this column existed) default to
    # "done" via the migration below, since they only ever got saved after
    # a successful split.
    status = Column(String, nullable=True, default="done")
    error_message = Column(String, nullable=True)
    # Path to the original, un-split upload — kept so the user can download
    # the whole song back, not just the separated stems.
    orig_path = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

# One-time migration: add status/error_message columns to stems table if they
# don't exist yet, backfilling old rows as "done" so they still show up
# normally in My Stems.
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE stems ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'done'"))
        conn.execute(text("ALTER TABLE stems ADD COLUMN IF NOT EXISTS error_message VARCHAR"))
        conn.execute(text("UPDATE stems SET status = 'done' WHERE status IS NULL"))
        # zip_path was originally created NOT NULL, back when every row got
        # its zip_path set at creation time. Now a "processing" row is
        # inserted with zip_path=None before Demucs has run, which violates
        # that old constraint and crashes the request with a 500. Drop it.
        conn.execute(text("ALTER TABLE stems ALTER COLUMN zip_path DROP NOT NULL"))
        conn.commit()
except Exception as e:
    logger.warning(f"stems status/error_message column migration skipped or already applied: {e}")

# One-time migration: add username column to users table if it doesn't exist yet
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR"))
        conn.commit()
except Exception as e:
    logger.warning(f"Username column migration skipped or already applied: {e}")

# One-time migration: fix users.id so it auto-generates values (was missing a sequence/default)
try:
    with engine.connect() as conn:
        col_type = conn.execute(text(
            "SELECT data_type FROM information_schema.columns WHERE table_name='users' AND column_name='id'"
        )).scalar()
        if col_type != "integer":
            logger.warning(f"users.id has type {col_type}, converting to integer")

            # Drop any foreign keys referencing users.id so the type change isn't blocked
            fk_rows = conn.execute(text("""
                SELECT tc.constraint_name, tc.table_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'users'
            """)).fetchall()
            for constraint_name, table_name in fk_rows:
                conn.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{constraint_name}"'))
            conn.commit()

            conn.execute(text("ALTER TABLE users ALTER COLUMN id TYPE INTEGER USING id::integer"))
            conn.commit()

            # Bring stems.user_id into line so it can still be compared/joined against users.id
            stems_col_type = conn.execute(text(
                "SELECT data_type FROM information_schema.columns WHERE table_name='stems' AND column_name='user_id'"
            )).scalar()
            if stems_col_type and stems_col_type != "integer":
                conn.execute(text("ALTER TABLE stems ALTER COLUMN user_id TYPE INTEGER USING NULLIF(user_id, '')::integer"))
                conn.commit()

        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS users_id_seq OWNED BY users.id"))
        conn.execute(text("SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 0) + 1, false)"))
        conn.execute(text("ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('users_id_seq')"))
        conn.commit()
except Exception as e:
    logger.warning(f"users.id sequence migration skipped or already applied: {e}")

# One-time migration: fix stems.id the same way (was also character varying, no working default)
try:
    with engine.connect() as conn:
        col_type = conn.execute(text(
            "SELECT data_type FROM information_schema.columns WHERE table_name='stems' AND column_name='id'"
        )).scalar()
        if col_type != "integer":
            logger.warning(f"stems.id has type {col_type}, converting to integer")
            conn.execute(text("ALTER TABLE stems ALTER COLUMN id TYPE INTEGER USING id::integer"))
            conn.commit()

        conn.execute(text("CREATE SEQUENCE IF NOT EXISTS stems_id_seq OWNED BY stems.id"))
        conn.execute(text("SELECT setval('stems_id_seq', COALESCE((SELECT MAX(id) FROM stems), 0) + 1, false)"))
        conn.execute(text("ALTER TABLE stems ALTER COLUMN id SET DEFAULT nextval('stems_id_seq')"))
        conn.commit()
except Exception as e:
    logger.warning(f"stems.id sequence migration skipped or already applied: {e}")

# One-time migration: add instrument column to stems table if missing
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE stems ADD COLUMN IF NOT EXISTS instrument VARCHAR"))
        conn.commit()
except Exception as e:
    logger.warning(f"Instrument column migration skipped or already applied: {e}")

# One-time migration: add orig_path column to stems table if missing
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE stems ADD COLUMN IF NOT EXISTS orig_path VARCHAR"))
        conn.commit()
except Exception as e:
    logger.warning(f"orig_path column migration skipped or already applied: {e}")

# One-time migration: add password-reset columns to users table if missing
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_hash VARCHAR"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP"))
        conn.commit()
except Exception as e:
    logger.warning(f"Reset token column migration skipped or already applied: {e}")

# Email config (set these in Railway env vars to enable real email delivery)
# Railway blocks outbound SMTP ports, so we send email over HTTPS via Resend
# instead of raw SMTP. Sign up at resend.com, verify a sending domain (or use
# their onboarding@resend.dev for testing), and set RESEND_API_KEY in Railway.
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://stemline101.com")

def send_email(to_email: str, subject: str, body: str):
    if not RESEND_API_KEY:
        # Not configured yet — log it instead of failing, so the flow still works in dev
        logger.warning(f"RESEND_API_KEY not configured. Would have emailed {to_email}: {subject}\n{body}")
        return
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        if response.status_code >= 400:
            logger.error(f"Failed to send email to {to_email}: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")

# JWT config
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "default-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 720

# Dependency: get current user from token
def get_current_user(token: str = None):
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Admin/free-access check. Set the ADMIN_EMAIL environment variable on
# Railway to your account's email (Variables tab on the service) — no code
# change or redeploy needed to change who it is. Comparison is
# case-insensitive.
def is_admin_user(db: Session, user_id: int) -> bool:
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        return False
    user = db.query(User).filter(User.id == user_id).first()
    return bool(user and user.email and user.email.lower() == admin_email.lower())

# Free tier: 2 splits per calendar month, per the pricing page. Admin
# account (see is_admin_user) always bypasses this.
FREE_SPLITS_PER_MONTH = 2

def check_split_allowance(db: Session, user_id: int):
    if is_admin_user(db, user_id):
        return
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    count = db.query(Stem).filter(
        Stem.user_id == user_id,
        Stem.instrument.is_(None),  # only full splits count, not per-channel saves
        Stem.created_at >= month_start,
    ).count()
    if count >= FREE_SPLITS_PER_MONTH:
        raise HTTPException(
            status_code=402,
            detail=f"Free plan is {FREE_SPLITS_PER_MONTH} songs a month. Upgrade to Pro for unlimited splits."
        )

# Helper: get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def root():
    return FileResponse("stemline101_landing_page.html", media_type="text/html")

@app.get("/reset-password")
def reset_password_page():
    return FileResponse("stemline101_landing_page.html", media_type="text/html")

@app.get("/api/v1/health")
def health():
    return {"status": "Stemline API is running"}

@app.post("/api/v1/signup")
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    email = body.email
    username = body.username
    password = body.password
    logger.info(f"Signup attempt for email: {email}")
    try:
        email = email.lower()
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        new_user = User(email=email, username=username, password_hash=password_hash)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        token = jwt.encode(
            {"user_id": new_user.id, "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)},
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM
        )
        logger.info(f"User {new_user.id} signed up successfully")
        return {"user_id": new_user.id, "email": new_user.email, "username": new_user.username, "token": token}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    email = body.email
    password = body.password
    logger.info(f"Login attempt for email: {email}")
    try:
        email = email.lower()
        user = db.query(User).filter(User.email == email).first()
        if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        token = jwt.encode(
            {"user_id": user.id, "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)},
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM
        )
        logger.info(f"User {user.id} logged in successfully")
        return {"user_id": user.id, "email": user.email, "username": user.username, "token": token}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/forgot-username")
def forgot_username(body: ForgotUsernameRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        send_email(
            email,
            "Your Stemline username",
            f"Hi,\n\nYour Stemline username is: {user.username}\n\nIf you didn't request this, you can ignore this email.",
        )
    # Same response either way, so we don't reveal which emails are registered
    return {"message": "If that email is registered, we've sent the username to it."}

@app.post("/api/v1/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        user.reset_token_hash = token_hash
        user.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
        reset_link = f"{FRONTEND_URL}/reset-password?token={raw_token}"
        send_email(
            email,
            "Reset your Stemline password",
            f"Hi,\n\nClick the link below to reset your Stemline password. This link expires in 30 minutes.\n\n{reset_link}\n\nIf you didn't request this, you can ignore this email.",
        )
    return {"message": "If that email is registered, we've sent a password reset link to it."}

@app.post("/api/v1/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    user = db.query(User).filter(User.reset_token_hash == token_hash).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user.password_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    user.reset_token_hash = None
    user.reset_token_expires = None
    db.commit()
    logger.info(f"Password reset successfully for user {user.id}")
    return {"message": "Password updated. You can now log in with your new password."}

def run_split_job(stem_id: int, request_id: str, upload_dir: str, file_path: str, filename: str, stem_count: str = "6"):
    """
    Runs Demucs and finishes the split for an already-created Stem row.
    Runs in a background thread so the HTTP request that kicked it off can
    return immediately instead of holding the connection open for the
    full 3+ minutes Demucs takes — that long open connection was getting
    killed by a proxy/browser network timeout before the response came
    back, even though the split itself succeeded on the backend every time.
    Opens its own DB session since the request-scoped one is gone by now.
    """
    db = SessionLocal()
    try:
        output_dir = os.path.join(upload_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # -j splits the track into chunks and processes them across CPU cores
        # in parallel instead of one long single-threaded pass. More jobs
        # multiplies memory use, and os.cpu_count() in a container often
        # reports the host's full core count rather than what Railway
        # actually allocates to this service — so default conservatively to
        # 2 and let DEMUCS_JOBS override once you've confirmed how much
        # headroom the Hobby plan actually gives this service.
        jobs = int(os.getenv("DEMUCS_JOBS", "2"))

        # --shifts runs the model N times on randomly time-shifted copies of
        # the input and averages the results. This is the main quality/bleed
        # lever Demucs exposes: more shifts = less bleed between stems and
        # cleaner isolation, at the cost of N times the processing time.
        # Default 1 = no shifting (what was running before). 2 roughly
        # doubles split time but is the standard quality tradeoff people use
        # to cut down bleed without it getting too slow to be usable.
        shifts = int(os.getenv("DEMUCS_SHIFTS", "2"))

        # --overlap controls how much adjacent processing chunks overlap.
        # Higher overlap smooths the seams between chunks (less "stitching"
        # artifacts contributing to bleed) at a smaller speed cost than
        # shifts. Demucs' own default is 0.25; bumping to 0.5 trades a bit
        # more compute for real reduction in edge artifacts.
        overlap = os.getenv("DEMUCS_OVERLAP", "0.75")

        # Mobile uploads request the 4-stem model (vocals/drums/bass/other) —
        # faster and lighter than the 6-stem model, which also splits out
        # guitar/piano. Any value other than "4" falls back to 6-stem.
        model_name = "htdemucs_ft" if stem_count == "4" else "htdemucs_6s"

        cmd = [
            "demucs", "-n", model_name,
            "-j", str(jobs),
            "--shifts", str(shifts),
            "--overlap", overlap,
            "-o", output_dir, file_path,
        ]
        logger.info(f"[job {request_id}] Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

        logger.info(f"[job {request_id}] Demucs stdout: {result.stdout}")
        logger.info(f"[job {request_id}] Demucs stderr: {result.stderr}")
        logger.info(f"[job {request_id}] Demucs return code: {result.returncode}")

        if result.returncode != 0:
            raise Exception(f"Demucs processing failed: {result.stderr}")

        # Find output stems
        stem_dir = None
        for root, dirs, files in os.walk(output_dir):
            if any(f.endswith(".wav") for f in files):
                stem_dir = root
                break

        if not stem_dir:
            raise Exception("No stem files generated")

        # Create zip in a permanent stems folder, keyed by this request's
        # uuid so it can never collide with any other split's zip — past or
        # future, same filename or not.
        stems_dir = "/data/stemline_uploads/saved_splits"
        os.makedirs(stems_dir, exist_ok=True)
        zip_path = os.path.join(stems_dir, f"{request_id}_{filename.rsplit('.', 1)[0]}_stems.zip")
        logger.info(f"[job {request_id}] Creating zip file: {zip_path}")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, dirs, files in os.walk(stem_dir):
                for f in files:
                    file_full_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_full_path, stem_dir)
                    zf.write(file_full_path, arcname)

        # Keep the original, un-split upload too, so the user can still get
        # the whole song back — not just the separated stems. Move it (not
        # copy) into the same permanent folder as the zip.
        orig_ext = filename.rsplit('.', 1)[-1] if '.' in filename else 'audio'
        orig_path = os.path.join(stems_dir, f"{request_id}_{filename.rsplit('.', 1)[0]}_original.{orig_ext}")
        try:
            shutil.move(file_path, orig_path)
        except Exception as orig_err:
            logger.warning(f"[job {request_id}] Could not preserve original upload: {orig_err}")
            orig_path = None

        # The Demucs output dir is no longer needed now that the zip (and
        # original) are safely saved elsewhere — clean up this request's
        # work dir so /tmp doesn't fill up over time.
        try:
            shutil.rmtree(upload_dir, ignore_errors=True)
        except Exception as cleanup_err:
            logger.warning(f"[job {request_id}] Cleanup of {upload_dir} failed: {cleanup_err}")

        stem_record = db.query(Stem).filter(Stem.id == stem_id).first()
        if stem_record:
            stem_record.zip_path = zip_path
            stem_record.orig_path = orig_path
            stem_record.status = "done"
            db.commit()
        logger.info(f"[job {request_id}] Stem split successful, saved as ID {stem_id}")

    except Exception as e:
        logger.error(f"[job {request_id}] Split error: {str(e)}", exc_info=True)
        try:
            shutil.rmtree(upload_dir, ignore_errors=True)
        except Exception:
            pass
        stem_record = db.query(Stem).filter(Stem.id == stem_id).first()
        if stem_record:
            stem_record.status = "error"
            stem_record.error_message = str(e)
            db.commit()
    finally:
        db.close()


@app.post("/api/v1/split")
def split_stem(file: UploadFile = File(...), token: str = None, stems: str = Form("6"), db: Session = Depends(get_db)):
    logger.info(f"Split request received: {file.filename} (stems={stems})")
    user_id = get_current_user(token)
    check_split_allowance(db, user_id)

    # Each split gets its own uuid-keyed work directory so concurrent or
    # repeated splits never share a folder or filename. Before this,
    # every split used the same shared "/tmp/stemline_uploads" folder
    # and named its zip after the uploaded filename — so a second split
    # (even of a different song) could overwrite the zip file that an
    # earlier saved stem's database row still pointed at, or the "find
    # stem folder" walk could pick up leftover files from a prior run.
    request_id = uuid.uuid4().hex
    upload_dir = os.path.join("/tmp/stemline_uploads", request_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)

    logger.info(f"Saving uploaded file to: {file_path}")
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Create the DB row up front in "processing" state, then hand the actual
    # Demucs run off to a background thread and return right away. Demucs
    # takes 3+ minutes on a real song — holding the HTTP request open that
    # whole time meant a proxy or browser network timeout could kill the
    # connection before the response ever came back, even though the split
    # itself always finished successfully server-side. Now the frontend
    # polls /api/v1/split/status/{stem_id} instead of waiting on one long
    # request.
    stem_record = Stem(
        user_id=user_id,
        track_name=file.filename.rsplit('.', 1)[0],
        zip_path=None,
        status="processing",
    )
    db.add(stem_record)
    db.commit()
    db.refresh(stem_record)

    thread = threading.Thread(
        target=run_split_job,
        args=(stem_record.id, request_id, upload_dir, file_path, file.filename, stems),
        daemon=True,
    )
    thread.start()

    logger.info(f"Split job {request_id} started in background as stem ID {stem_record.id}")
    return {"stem_id": stem_record.id, "track_name": stem_record.track_name, "status": "processing"}


@app.get("/api/v1/split/status/{stem_id}")
def get_split_status(stem_id: int, token: str = None, db: Session = Depends(get_db)):
    user_id = get_current_user(token)
    stem_record = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
    if not stem_record:
        raise HTTPException(status_code=404, detail="Stem not found")
    return {
        "stem_id": stem_record.id,
        "track_name": stem_record.track_name,
        "status": stem_record.status or "done",
        "error": stem_record.error_message,
    }

@app.get("/api/v1/my-stems")
def get_my_stems(token: str = None, db: Session = Depends(get_db)):
    user_id = get_current_user(token)
    try:
        # Only list stems that finished successfully — rows still
        # "processing" (or that ended in "error") don't have a usable
        # zip_path yet and would 404/500 if the frontend tried to load them.
        stems = db.query(Stem).filter(Stem.user_id == user_id, Stem.status == "done").all()
        return [{"id": s.id, "track_name": s.track_name, "created_at": s.created_at, "instrument": s.instrument, "has_original": bool(s.orig_path)} for s in stems]
    except Exception as e:
        logger.error(f"Get stems error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/my-stems/{stem_id}/download")
def download_stem(stem_id: int, token: str = None, db: Session = Depends(get_db)):
    user_id = get_current_user(token)
    try:
        stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
        if not stem_row:
            raise HTTPException(status_code=404, detail="Saved stem not found.")
        if stem_row.instrument:
            # Single-channel save — zip_path points at a lone wav, not a zip.
            return FileResponse(
                stem_row.zip_path,
                media_type="audio/wav",
                filename=f"{stem_row.track_name}.wav"
            )
        return FileResponse(
            stem_row.zip_path,
            media_type="application/zip",
            filename=f"{stem_row.track_name}_stems.zip"
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/my-stems/{stem_id}/download-original")
def download_stem_original(stem_id: int, token: str = None, db: Session = Depends(get_db)):
    # Serves the whole, un-split song back — not the separated stems.
    user_id = get_current_user(token)
    stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
    if not stem_row:
        raise HTTPException(status_code=404, detail="Saved stem not found.")
    if not stem_row.orig_path or not os.path.exists(stem_row.orig_path):
        raise HTTPException(status_code=404, detail="Original song isn't available for this split.")
    ext = stem_row.orig_path.rsplit('.', 1)[-1]
    return FileResponse(
        stem_row.orig_path,
        media_type="audio/" + ext,
        filename=f"{stem_row.track_name}.{ext}"
    )

# Instrument names Demucs' htdemucs_6s model actually outputs, and the only
# values the mixer's channel keys ever send here.
STEM_INSTRUMENTS = {"vocals", "drums", "bass", "guitar", "piano", "other"}

@app.get("/api/v1/my-stems/{stem_id}/download/{instrument}")
def download_stem_instrument(stem_id: int, instrument: str, token: str = None, db: Session = Depends(get_db)):
    # A split saves all six instruments zipped together as one row. The mixer
    # channels each need just ONE instrument's audio, so this pulls a single
    # wav back out of that zip on demand instead of the whole bundle.
    user_id = get_current_user(token)
    try:
        if instrument not in STEM_INSTRUMENTS:
            raise HTTPException(status_code=400, detail=f"Unknown instrument: {instrument}")
        stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
        if not stem_row:
            raise HTTPException(status_code=404, detail="Saved stem not found.")
        if stem_row.instrument:
            # Single-channel save -- zip_path already points at a lone wav,
            # not a zip. The `instrument` path param here is really just the
            # mixer channel the frontend wants to load it into, which the
            # user can now freely reassign from the saved stem's own label,
            # so it no longer has to match stem_row.instrument.
            with open(stem_row.zip_path, "rb") as f:
                wav_bytes = f.read()
        else:
            with zipfile.ZipFile(stem_row.zip_path) as zf:
                match = next((n for n in zf.namelist() if n.lower().endswith(instrument + ".wav")), None)
                if not match:
                    raise HTTPException(status_code=404, detail=f"No {instrument} track in this split.")
                wav_bytes = zf.read(match)
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"Content-Disposition": f'attachment; filename="{stem_row.track_name}_{instrument}.wav"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Instrument download error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/my-stems/{stem_id}/save-instrument/{instrument}")
def save_stem_instrument(stem_id: int, instrument: str, token: str = None, db: Session = Depends(get_db)):
    # Pulls one instrument's wav out of an existing split's zip and saves it
    # as its own standalone stem row, so a mixer channel can be kept without
    # having to keep the whole 6-stem bundle.
    user_id = get_current_user(token)
    try:
        if instrument not in STEM_INSTRUMENTS:
            raise HTTPException(status_code=400, detail=f"Unknown instrument: {instrument}")
        stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
        if not stem_row:
            raise HTTPException(status_code=404, detail="Saved stem not found.")
        if stem_row.instrument:
            raise HTTPException(status_code=400, detail="That save is already a single instrument.")

        with zipfile.ZipFile(stem_row.zip_path) as zf:
            match = next((n for n in zf.namelist() if n.lower().endswith(instrument + ".wav")), None)
            if not match:
                raise HTTPException(status_code=404, detail=f"No {instrument} track in this split.")
            wav_bytes = zf.read(match)

        save_dir = "/data/stemline_uploads/saved"
        os.makedirs(save_dir, exist_ok=True)
        wav_path = os.path.join(save_dir, f"{stem_id}_{instrument}_{secrets.token_hex(4)}.wav")
        with open(wav_path, "wb") as f:
            f.write(wav_bytes)

        new_row = Stem(
            user_id=user_id,
            track_name=f"{stem_row.track_name} ({instrument.capitalize()})",
            zip_path=wav_path,
            instrument=instrument
        )
        db.add(new_row)
        db.commit()
        db.refresh(new_row)

        logger.info(f"Saved single instrument, new stem ID {new_row.id}")
        return {"id": new_row.id, "track_name": new_row.track_name, "instrument": new_row.instrument}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save instrument error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class RenameStemRequest(BaseModel):
    track_name: Optional[str] = None
    instrument: Optional[str] = None

@app.patch("/api/v1/my-stems/{stem_id}")
def rename_stem(stem_id: int, body: RenameStemRequest, token: str = None, db: Session = Depends(get_db)):
    user_id = get_current_user(token)
    try:
        stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
        if not stem_row:
            raise HTTPException(status_code=404, detail="Saved stem not found.")
        if body.track_name is not None:
            new_name = body.track_name.strip()
            if not new_name:
                raise HTTPException(status_code=400, detail="Name can't be empty.")
            if len(new_name) > 200:
                raise HTTPException(status_code=400, detail="Name is too long.")
            stem_row.track_name = new_name
        if body.instrument is not None:
            # Re-categorize a saved single-instrument stem (e.g. relabel a
            # saved "guitar" as "other"). Only meaningful for per-instrument
            # saves, not whole-song split rows.
            if not stem_row.instrument:
                raise HTTPException(status_code=400, detail="Only a saved single stem can be re-categorized.")
            if body.instrument not in STEM_INSTRUMENTS:
                raise HTTPException(status_code=400, detail=f"Unknown category: {body.instrument}")
            stem_row.instrument = body.instrument
        db.commit()
        return {"id": stem_row.id, "track_name": stem_row.track_name, "instrument": stem_row.instrument}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rename error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/my-stems/{stem_id}")
def delete_stem(stem_id: int, token: str = None, db: Session = Depends(get_db)):
    user_id = get_current_user(token)
    try:
        stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
        if not stem_row:
            raise HTTPException(status_code=404, detail="Saved stem not found.")
        # Remove the file on disk first — if this fails we still don't want
        # a dangling DB row pointing at nothing, but we also don't want to
        # silently leak files, so log any cleanup failure rather than hide it.
        try:
            if stem_row.zip_path and os.path.exists(stem_row.zip_path):
                os.remove(stem_row.zip_path)
        except Exception as file_err:
            logger.warning(f"Could not remove file for stem {stem_id}: {file_err}")
        db.delete(stem_row)
        db.commit()
        return {"deleted": True, "id": stem_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete stem error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
"""
Add this route to your FastAPI backend (main.py or wherever your other
page routes like the landing page live). Serves the Terms of Service
page at /terms, matching the link already in the landing page footer.
"""

from fastapi.responses import HTMLResponse

TERMS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Terms of Service — Stemline101</title>
<style>
  body { background:#111; color:#eee; font-family: system-ui, sans-serif;
         max-width: 720px; margin: 0 auto; padding: 2rem 1.5rem 4rem; line-height: 1.6; }
  h1 { color: #f0a500; }
  h2 { color: #f0a500; margin-top: 2rem; }
  a { color: #f0a500; }
</style>
</head>
<body>
<h1>Stemline101 Terms of Service</h1>
<p><em>Last Updated: [Date]</em></p>

<h2>1. Acceptance of Terms</h2>
<p>By accessing or using Stemline101 ("the Service"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree, do not use the Service.</p>

<h2>2. Description of Service</h2>
<p>Stemline101 provides AI-powered audio stem separation and mixing tools. Users may upload audio files, which the Service processes to generate separated audio components ("stems").</p>

<h2>3. User Responsibility for Uploaded Content</h2>
<p><strong>You are solely responsible for the audio content you upload to Stemline101.</strong></p>
<p>By uploading any audio file, you represent and warrant that:</p>
<ul>
  <li>You own the copyright to the audio, OR</li>
  <li>You have obtained all necessary rights, licenses, and permissions from the copyright holder(s) to upload, process, and separate the audio using this Service, OR</li>
  <li>Your use of the audio falls under a valid exception to copyright law (such as fair use) in your jurisdiction.</li>
</ul>
<p>Stemline101 does not review, verify, or monitor the copyright status of uploaded content. The Service is a neutral tool for audio processing, comparable to other audio software. <strong>Stemline101 is not responsible for copyright infringement resulting from a user's upload, separation, download, distribution, or commercial use of audio content that the user did not have the right to process.</strong></p>

<h2>4. Prohibited Use</h2>
<p>You may not use Stemline101 to:</p>
<ul>
  <li>Upload copyrighted audio you do not have rights to, for the purpose of extracting, redistributing, or commercially exploiting stems from that work</li>
  <li>Circumvent copyright protections</li>
  <li>Violate any applicable local, state, national, or international law</li>
</ul>

<h2>5. DMCA / Copyright Complaints</h2>
<p>Stemline101 will respond to valid copyright infringement notices in accordance with the Digital Millennium Copyright Act (DMCA) and will remove or disable access to infringing content upon receipt of a proper notice. Repeat infringers may have their accounts terminated.</p>
<p><strong>Copyright agent contact:</strong> [email/address to be added]</p>

<h2>6. No Warranty</h2>
<p>The Service is provided "as is" without warranties of any kind. Stemline101 does not guarantee the accuracy, quality, or legality of separated stems.</p>

<h2>7. Limitation of Liability</h2>
<p>To the maximum extent permitted by law, Stemline101 and its owners/operators shall not be liable for any indirect, incidental, special, or consequential damages, including but not limited to copyright claims arising from user-uploaded content.</p>

<h2>8. Indemnification</h2>
<p>You agree to indemnify and hold harmless Stemline101, its owners, and operators from any claims, damages, or liabilities (including legal fees) arising from your use of the Service or your uploaded content, including third-party claims that your uploaded content infringes their rights.</p>

<h2>9. Account Termination</h2>
<p>Stemline101 reserves the right to suspend or terminate accounts that violate these Terms, including repeated copyright infringement.</p>

<h2>10. Changes to Terms</h2>
<p>Stemline101 may update these Terms at any time. Continued use of the Service after changes constitutes acceptance of the new Terms.</p>

<h2>11. Contact</h2>
<p>Questions about these Terms can be directed to: [contact email]</p>

<p style="margin-top:3rem; opacity:0.6; font-size:0.9rem;">
This document is a general template and not a substitute for legal advice.
</p>
</body>
</html>
"""


@app.get("/terms", response_class=HTMLResponse)
async def terms_of_service():
    return TERMS_HTML
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

