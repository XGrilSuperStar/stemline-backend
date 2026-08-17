from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import shutil
import subprocess
import zipfile
import uuid
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

Base.metadata.create_all(bind=engine)

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
    return FileResponse("stemline_landing_page.html", media_type="text/html")

@app.get("/reset-password")
def reset_password_page():
    return FileResponse("stemline_landing_page.html", media_type="text/html")

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

@app.post("/api/v1/split")
def split_stem(file: UploadFile = File(...), token: str = None, db: Session = Depends(get_db)):
    logger.info(f"Split request received: {file.filename}")
    user_id = get_current_user(token)
    check_split_allowance(db, user_id)

    try:
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
        
        logger.info(f"File saved, starting Demucs processing...")
        
        # Run Demucs
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
        overlap = os.getenv("DEMUCS_OVERLAP", "0.5")

        cmd = [
            "demucs", "-n", "htdemucs_6s",
            "-j", str(jobs),
            "--shifts", str(shifts),
            "--overlap", overlap,
            "-o", output_dir, file_path,
        ]
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )
        
        logger.info(f"Demucs stdout: {result.stdout}")
        logger.info(f"Demucs stderr: {result.stderr}")
        logger.info(f"Demucs return code: {result.returncode}")
        
        if result.returncode != 0:
            logger.error(f"Demucs failed with return code {result.returncode}")
            raise Exception(f"Demucs processing failed: {result.stderr}")
        
        # Find output stems
        stem_dir = None
        for root, dirs, files in os.walk(output_dir):
            if any(f.endswith(".wav") for f in files):
                stem_dir = root
                break
        
        if not stem_dir:
            logger.error("No stem files found after Demucs processing")
            raise Exception("No stem files generated")
        
        # Create zip in a permanent stems folder, keyed by this request's
        # uuid so it can never collide with any other split's zip — past or
        # future, same filename or not.
        stems_dir = "/data/stemline_uploads/saved_splits"
        os.makedirs(stems_dir, exist_ok=True)
        zip_path = os.path.join(stems_dir, f"{request_id}_{file.filename.rsplit('.', 1)[0]}_stems.zip")
        logger.info(f"Creating zip file: {zip_path}")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, dirs, files in os.walk(stem_dir):
                for f in files:
                    file_full_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_full_path, stem_dir)
                    zf.write(file_full_path, arcname)

        # The raw upload and Demucs output are no longer needed now that the
        # zip is safely saved elsewhere — clean up this request's work dir
        # so /tmp doesn't fill up over time.
        try:
            shutil.rmtree(upload_dir, ignore_errors=True)
        except Exception as cleanup_err:
            logger.warning(f"Cleanup of {upload_dir} failed: {cleanup_err}")
        
        # Save to DB
        stem_record = Stem(
            user_id=user_id,
            track_name=file.filename.rsplit('.', 1)[0],
            zip_path=zip_path
        )
        db.add(stem_record)
        db.commit()
        db.refresh(stem_record)
        
        logger.info(f"Stem split successful, saved as ID {stem_record.id}")
        return {"stem_id": stem_record.id, "track_name": stem_record.track_name}
    
    except Exception as e:
        logger.error(f"Split error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Split failed: {str(e)}")

@app.get("/api/v1/my-stems")
def get_my_stems(token: str = None, db: Session = Depends(get_db)):
    user_id = get_current_user(token)
    try:
        stems = db.query(Stem).filter(Stem.user_id == user_id).all()
        return [{"id": s.id, "track_name": s.track_name, "created_at": s.created_at, "instrument": s.instrument} for s in stems]
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
            # not a zip. Only serve it if it actually matches the
            # instrument being asked for.
            if stem_row.instrument != instrument:
                raise HTTPException(status_code=404, detail=f"This saved stem is {stem_row.instrument}, not {instrument}.")
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
    track_name: str

@app.patch("/api/v1/my-stems/{stem_id}")
def rename_stem(stem_id: int, body: RenameStemRequest, token: str = None, db: Session = Depends(get_db)):
    user_id = get_current_user(token)
    try:
        new_name = body.track_name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Name can't be empty.")
        if len(new_name) > 200:
            raise HTTPException(status_code=400, detail="Name is too long.")
        stem_row = db.query(Stem).filter(Stem.id == stem_id, Stem.user_id == user_id).first()
        if not stem_row:
            raise HTTPException(status_code=404, detail="Saved stem not found.")
        stem_row.track_name = new_name
        db.commit()
        return {"id": stem_row.id, "track_name": stem_row.track_name}
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
