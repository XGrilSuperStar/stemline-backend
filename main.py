from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta
import jwt
import bcrypt
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

class SignupRequest(BaseModel):
    email: str
    username: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class Stem(Base):
    __tablename__ = "stems"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    track_name = Column(String)
    zip_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

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

@app.post("/api/v1/split")
def split_stem(file: UploadFile = File(...), token: str = None, db: Session = Depends(get_db)):
    logger.info(f"Split request received: {file.filename}")
    user_id = get_current_user(token)
    
    try:
        # Save uploaded file
        upload_dir = "/tmp/stemline_uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, file.filename)
        
        logger.info(f"Saving uploaded file to: {file_path}")
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        
        logger.info(f"File saved, starting Demucs processing...")
        
        # Run Demucs
        output_dir = os.path.join(upload_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Running: demucs -n htdemucs_6s -o {output_dir} {file_path}")
        result = subprocess.run(
            ["demucs", "-n", "htdemucs_6s", "-o", output_dir, file_path],
            capture_output=True,
            text=True,
            timeout=300
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
        
        # Create zip
        zip_path = os.path.join(upload_dir, f"{file.filename.rsplit('.', 1)[0]}_stems.zip")
        logger.info(f"Creating zip file: {zip_path}")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, dirs, files in os.walk(stem_dir):
                for f in files:
                    file_full_path = os.path.join(root, f)
                    arcname = os.path.relpath(file_full_path, stem_dir)
                    zf.write(file_full_path, arcname)
        
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
        return [{"id": s.id, "track_name": s.track_name, "created_at": s.created_at} for s in stems]
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
        return FileResponse(
            stem_row.zip_path,
            media_type="application/zip",
            filename=f"{stem_row.track_name}_stems.zip"
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
