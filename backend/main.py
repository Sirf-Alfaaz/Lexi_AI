# backend/main.py

import os
import logging
import random
import string
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends, Header, Request, Query
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, EmailStr, ValidationError
from dotenv import load_dotenv
import google.generativeai as genai
import fitz  # type: ignore  # PyMuPDF may lack type hints
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.lib.colors import black, white, grey
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from typing import Optional, cast, Union, Dict, Any
import httpx
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from bson.errors import InvalidId
from passlib.context import CryptContext
import jwt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote_plus
from pathlib import Path

# Land module services
from services.ocr_service import extract_text_from_pdf_bytes
from services.gemini_analysis import analyze_land_document
from services.geocode_service import geocode_village_district
from services.name_display import format_bilingual_name
from services.document_ocr_pipeline import extract_registry_fields_from_document
from services.bhulekh import (
    BhulekhCaptchaError,
    BhulekhNavigationError,
    BhulekhNotFoundError,
    BhulekhTimeoutError,
    UPBhulekhScraper,
)
from database.land_records_collection import (
    upsert_land_record,
    find_land_record,
    LAND_COLLECTION_NAME,
)
from routers.ocr_document import router as ocr_document_router
from routers.forgery_detection import router as forgery_detection_router
from routers.land_intel import router as land_intel_router

# -----------------------------
# Setup logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
bhulekh_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bhulekh-upload")


def _normalize_for_match(value: Optional[str]) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _compute_bhulekh_match_score(
    *,
    user_owner: str,
    user_khasra: str,
    user_area: str,
    bhulekh_owner: str,
    bhulekh_khasra: str,
    bhulekh_area: str,
) -> Dict[str, Any]:
    weights = {"owner": 40, "khasra": 40, "area": 20}

    uo, uk, ua = _normalize_for_match(user_owner), _normalize_for_match(user_khasra), _normalize_for_match(user_area)
    bo, bk, ba = _normalize_for_match(bhulekh_owner), _normalize_for_match(bhulekh_khasra), _normalize_for_match(bhulekh_area)

    owner_match = bool(uo and bo and (uo == bo or uo in bo or bo in uo))
    khasra_match = bool(uk and bk and (uk == bk or uk in bk or bk in uk))
    area_match = bool(ua and ba and (ua == ba or ua in ba or ba in ua))

    points = {
        "owner": weights["owner"] if owner_match else 0,
        "khasra": weights["khasra"] if khasra_match else 0,
        "area": weights["area"] if area_match else 0,
    }
    total = points["owner"] + points["khasra"] + points["area"]
    status = "strong_match" if total >= 80 else ("partial_match" if total >= 40 else "weak_match")

    return {
        "status": status,
        "total_points": total,
        "max_points": 100,
        "field_points": points,
        "field_match": {
            "owner": owner_match,
            "khasra": khasra_match,
            "area": area_match,
        },
    }

# -----------------------------
# Load environment variables
# -----------------------------
# Always load backend/.env even when cwd is repo root (e.g. uvicorn backend.main:app).
_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")
SECRET_KEY = "thisisthesecretkey987654321kjhfjsdv"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
ALGORITHM = "HS256"

# Email configuration
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_SERVICE = os.getenv("EMAIL_SERVICE", "gmail")  # gmail, sendgrid, smtp
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@yourdomain.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"

# SendGrid configuration (alternative to SMTP)
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

# MongoDB connection string
# Format: mongodb+srv://username:password@cluster.mongodb.net/database?retryWrites=true&w=majority
# Or: mongodb://username:password@host:port/database
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/legal_db")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "legal_db")


if not API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY not found. Please add it to your .env file.")

# Configure Gemini API
genai.configure(api_key=API_KEY)  # type: ignore[attr-defined]

# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(title="AI Legal Companion", version="4.0")

app.include_router(ocr_document_router)
app.include_router(forgery_detection_router)
app.include_router(land_intel_router)

# Add custom validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Custom handler for validation errors to provide better error messages"""
    errors = exc.errors()
    error_details = []
    for error in errors:
        error_details.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.error(f"Validation error on {request.url.path}: {error_details}")
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": error_details,
            "body_received": str(exc.body) if hasattr(exc, 'body') else "N/A"
        }
    )

# -----------------------------
# Background tasks and utilities
# -----------------------------
@app.on_event("startup")
async def startup_event():
    """Initialize MongoDB connection and create indexes on startup"""
    global mongodb_client, mongodb_db
    try:
        if MONGODB_URL:
            # Parse and fix connection string for MongoDB Atlas
            connection_url = MONGODB_URL.strip()
            
            # Ensure proper connection options for MongoDB Atlas
            if "mongodb+srv://" in connection_url:
                # Ensure database name is in the connection string
                if f"/{MONGODB_DB_NAME}" not in connection_url and "/?" not in connection_url:
                    # Add database name before query parameters
                    if "?" in connection_url:
                        connection_url = connection_url.replace("?", f"/{MONGODB_DB_NAME}?")
                    else:
                        connection_url = f"{connection_url}/{MONGODB_DB_NAME}"
                
                # Ensure retryWrites is set
                if "retryWrites" not in connection_url:
                    separator = "&" if "?" in connection_url else "?"
                    connection_url += f"{separator}retryWrites=true&w=majority"
            
            logger.info("Connecting to MongoDB...")
            # Log connection URL (without password for security)
            safe_url = connection_url.split('@')[1] if '@' in connection_url else connection_url
            logger.info(f"Connecting to: ...@{safe_url}")
            
            # Create client with proper SSL configuration for Atlas
            # Note: mongodb+srv:// automatically uses TLS, so we don't need to set it explicitly
            # Use shorter timeouts to avoid blocking startup
            mongodb_client = AsyncIOMotorClient(
                connection_url,
                serverSelectionTimeoutMS=10000,  # 10 seconds
                connectTimeoutMS=10000,
                socketTimeoutMS=20000
            )
            mongodb_db = mongodb_client[MONGODB_DB_NAME]
            
            # Test connection with timeout
            try:
                await asyncio.wait_for(
                    mongodb_client.admin.command('ping'),
                    timeout=10.0
                )
                logger.info("✅ MongoDB connection established")

                # Create indexes (non-blocking for startup)
                try:
                    await create_indexes()
                except Exception as idx_error:
                    logger.warning(f"Index creation failed (non-critical): {idx_error}")

                # Clean up expired OTPs (non-blocking for startup)
                try:
                    logger.info("Cleaning up expired OTPs...")
                    await cleanup_expired_otps()
                except Exception as cleanup_error:
                    logger.warning(f"OTP cleanup failed (non-critical): {cleanup_error}")

            except asyncio.TimeoutError:
                logger.error("❌ MongoDB connection timeout!")
                logger.error("=" * 60)
                logger.error("TROUBLESHOOTING STEPS:")
                logger.error("=" * 60)
                logger.error("1. CHECK IP WHITELIST in MongoDB Atlas:")
                logger.error("   - Go to Network Access → Add IP Address")
                logger.error("   - Add your current IP or use 0.0.0.0/0 for development")
                logger.error("")
                logger.error("2. CHECK CONNECTION STRING in .env file:")
                logger.error("   - Format: mongodb+srv://username:ENCODED_PASSWORD@cluster.net/legal_db?retryWrites=true&w=majority")
                logger.error("   - Make sure password is URL-encoded (special chars like ! → %21)")
                logger.error("   - Make sure /legal_db is in the URL before the ?")
                logger.error("")
                logger.error("3. CHECK DATABASE USER:")
                logger.error("   - Go to Database Access in MongoDB Atlas")
                logger.error("   - Verify user 'College_creator' exists")
                logger.error("   - Ensure it has 'Read and write to any database' permissions")
                logger.error("")
                logger.error("4. TEST CONNECTION:")
                logger.error("   - Try connecting from MongoDB Compass or mongosh")
                logger.error("   - This will help identify if it's a network or credential issue")
                logger.error("=" * 60)
                logger.warning("Server will start but database features will NOT work until connection is fixed")
            except Exception as conn_error:
                error_msg = str(conn_error)
                logger.error(f"❌ MongoDB connection failed: {error_msg}")
                logger.error("=" * 60)
                
                # Provide specific error guidance
                if "authentication" in error_msg.lower() or "auth" in error_msg.lower():
                    logger.error("AUTHENTICATION ERROR:")
                    logger.error("   - Check your username and password")
                    logger.error("   - Make sure password is URL-encoded")
                    logger.error("   - Verify user exists in Database Access")
                elif "ssl" in error_msg.lower() or "tls" in error_msg.lower():
                    logger.error("SSL/TLS ERROR:")
                    logger.error("   - Check your connection string format")
                    logger.error("   - Ensure mongodb+srv:// is used (not mongodb://)")
                elif "timeout" in error_msg.lower():
                    logger.error("TIMEOUT ERROR:")
                    logger.error("   - Check your IP is whitelisted in Network Access")
                    logger.error("   - Check your internet connection")
                    logger.error("   - Try increasing timeout in connection options")
                else:
                    logger.error("CONNECTION ERROR:")
                    logger.error("   - Check connection string format")
                    logger.error("   - Verify network access settings")
                    logger.error("   - Check MongoDB Atlas cluster status")
                
                logger.error("=" * 60)
                logger.warning("Server will start but database features will NOT work until connection is fixed")
            
        else:
            logger.warning("MONGODB_URL not set; database features will not work")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        logger.warning("Server will continue but database features may not work properly")

async def create_indexes():
    """Create MongoDB indexes for better performance"""
    try:
        if mongodb_db is None:
            logger.warning("MongoDB database not initialized, skipping index creation")
            return
        
        # Users collection indexes
        await mongodb_db.users.create_index([("username", ASCENDING)], unique=True)
        await mongodb_db.users.create_index([("email", ASCENDING)], unique=True)
        
        # OTPs collection indexes
        await mongodb_db.otps.create_index([("email", ASCENDING)])
        await mongodb_db.otps.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
        
        # Search history indexes
        await mongodb_db.search_history.create_index([("user_id", ASCENDING)])
        await mongodb_db.search_history.create_index([("timestamp", DESCENDING)])
        
        logger.info("✅ MongoDB indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Close MongoDB connection on shutdown"""
    global mongodb_client
    if mongodb_client:
        mongodb_client.close()
        logger.info("MongoDB connection closed")

# -----------------------------
# Enable CORS
# -----------------------------
# Default origins for local development
default_origins = [
    "http://localhost:5173",  # Default Vite dev server
    "http://localhost:5174",  # Alternative Vite dev server port
    "http://localhost:3000",  # Alternative React dev server
    "http://localhost:8080",  # Alternative dev server
    "http://127.0.0.1:5173",  # IP version
    "http://127.0.0.1:5174",  # IP version
    "http://127.0.0.1:3000",  # IP version
    "http://127.0.0.1:8080",  # IP version
    "https://lexiaii.netlify.app",  # Netlify production
]

# Get additional origins from environment variable (comma-separated)
# Example: CORS_ORIGINS=https://your-app.netlify.app,https://your-custom-domain.com
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env:
    additional_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
    origins = default_origins + additional_origins
else:
    origins = default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Database & Auth setup
# -----------------------------
if not MONGODB_URL:
    logger.warning("MONGODB_URL not set; authentication will fail. Set MONGODB_URL in .env")

# MongoDB client and database
mongodb_client: Optional[AsyncIOMotorClient] = None
mongodb_db: Optional[AsyncIOMotorDatabase] = None

# MongoDB Document Models (using Pydantic-like structure)
class User:
    def __init__(self, **kwargs):
        self.id = kwargs.get("_id")
        self.username = kwargs.get("username")
        self.email = kwargs.get("email")
        self.password_hash = kwargs.get("password_hash")
        self.is_verified = kwargs.get("is_verified", False)
        self.created_at = kwargs.get("created_at", datetime.utcnow())
        self.is_admin = kwargs.get("is_admin", False)
    
    def to_dict(self):
        return {
            "_id": self.id,
            "username": self.username,
            "email": self.email,
            "password_hash": self.password_hash,
            "is_verified": self.is_verified,
            "created_at": self.created_at,
            "is_admin": self.is_admin
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        if data is None:
            return None
        return cls(**data)

class OTP:
    def __init__(self, **kwargs):
        self.id = kwargs.get("_id")
        self.email = kwargs.get("email")
        self.otp_code = kwargs.get("otp_code")
        self.is_used = kwargs.get("is_used", False)
        self.expires_at = kwargs.get("expires_at")
        self.created_at = kwargs.get("created_at", datetime.utcnow())
    
    def to_dict(self):
        return {
            "_id": self.id,
            "email": self.email,
            "otp_code": self.otp_code,
            "is_used": self.is_used,
            "expires_at": self.expires_at,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        if data is None:
            return None
        return cls(**data)

class SearchHistory:
    def __init__(self, **kwargs):
        self.id = kwargs.get("_id")
        self.query = kwargs.get("query")
        self.user_id = kwargs.get("user_id")
        self.timestamp = kwargs.get("timestamp", datetime.utcnow())
        self.action = kwargs.get("action")
    
    def to_dict(self):
        return {
            "_id": self.id,
            "query": self.query,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "action": self.action
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        if data is None:
            return None
        return cls(**data)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def get_db() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance"""
    if mongodb_db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return mongodb_db

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def generate_otp() -> str:
    """Generate a random 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))

def is_otp_expired(expires_at: datetime) -> bool:
    """Check if OTP has expired"""
    return datetime.utcnow() > expires_at

async def cleanup_expired_otps():
    """Remove expired OTPs from database"""
    try:
        db = await get_db()
        now = datetime.utcnow()
        
        result = await db.otps.delete_many({"expires_at": {"$lt": now}})
        
        if result.deleted_count > 0:
            logger.info(f"Cleaned up {result.deleted_count} expired OTPs")
        else:
            logger.info("No expired OTPs to clean up")
            
    except Exception as e:
        logger.error(f"Error cleaning up expired OTPs: {e}")

def send_email_otp(to_email: str, otp_code: str, username: str = None) -> bool:
    """Send OTP via email"""
    if not EMAIL_ENABLED:
        logger.warning("Email is disabled. Set EMAIL_ENABLED=true to enable email sending.")
        return False
    
    try:
        if EMAIL_SERVICE == "sendgrid" and SENDGRID_API_KEY:
            return send_email_sendgrid(to_email, otp_code, username)
        else:
            return send_email_smtp(to_email, otp_code, username)
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False

def send_email_smtp(to_email: str, otp_code: str, username: str = None) -> bool:
    """Send OTP via SMTP (Gmail, Outlook, etc.)"""
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = to_email
        msg['Subject'] = "Your OTP Code - AI Legal Assistant"
        
        # Email body
        body = f"""
        <html>
        <body>
            <h2>🔐 OTP Verification Code</h2>
            <p>Hello {username or 'there'},</p>
            <p>Your verification code for AI Legal Assistant is:</p>
            <div style="background-color: #f4f4f4; padding: 20px; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 5px; border-radius: 10px; margin: 20px 0;">
                {otp_code}
            </div>
            <p><strong>This code will expire in 10 minutes.</strong></p>
            <p>If you didn't request this code, please ignore this email.</p>
            <hr>
            <p style="color: #666; font-size: 12px;">
                This is an automated message from AI Legal Assistant.<br>
                Please do not reply to this email.
            </p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Create SMTP session
        if EMAIL_USE_TLS:
            server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
            server.starttls()
        else:
            server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        
        # Login
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        
        # Send email
        text = msg.as_string()
        server.sendmail(EMAIL_FROM, to_email, text)
        server.quit()
        
        logger.info(f"OTP email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"SMTP email sending failed: {e}")
        return False

def send_email_sendgrid(to_email: str, otp_code: str, username: str = None) -> bool:
    """Send OTP via SendGrid API"""
    try:
        import requests
        
        url = "https://api.sendgrid.com/v3/mail/send"
        
        data = {
            "personalizations": [
                {
                    "to": [{"email": to_email}],
                    "subject": "Your OTP Code - AI Legal Assistant"
                }
            ],
            "from": {"email": EMAIL_FROM},
            "content": [
                {
                    "type": "text/html",
                    "value": f"""
                    <html>
                    <body>
                        <h2>🔐 OTP Verification Code</h2>
                        <p>Hello {username or 'there'},</p>
                        <p>Your verification code for AI Legal Assistant is:</p>
                        <div style="background-color: #f4f4f4; padding: 20px; text-align: center; font-size: 24px; font-weight: bold; letter-spacing: 5px; border-radius: 10px; margin: 20px 0;">
                            {otp_code}
                        </div>
                        <p><strong>This code will expire in 10 minutes.</strong></p>
                        <p>If you didn't request this code, please ignore this email.</p>
                        <hr>
                        <p style="color: #666; font-size: 12px;">
                            This is an automated message from AI Legal Assistant.<br>
                            Please do not reply to this email.
                        </p>
                    </body>
                    </html>
                    """
                }
            ]
        }
        
        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 202:
            logger.info(f"SendGrid email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"SendGrid email failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"SendGrid email sending failed: {e}")
        return False


async def get_current_user(authorization: Optional[str] = Header(None), db: AsyncIOMotorDatabase = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_doc = await db.users.find_one({"username": username})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    user = User.from_dict(user_doc)
    return user

# -----------------------------
# Health check endpoint
# -----------------------------
@app.get("/health")
async def health_check():
    """Health check endpoint to verify server and database status"""
    try:
        # Test database connection
        if mongodb_client:
            await mongodb_client.admin.command('ping')
            db_status = "connected"
        else:
            db_status = "not configured"
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": db_status,
            "cors_origins": origins
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "database": "error"
        }

@app.get("/debug/schema")
async def debug_schema():
    """Debug endpoint to check database schema"""
    try:
        if mongodb_db is None:
            return {"error": "Database not configured"}
        
        db = await get_db()
        
        # Get collection stats
        user_count = await db.users.count_documents({})
        otp_count = await db.otps.count_documents({})
        search_count = await db.search_history.count_documents({})
            
        # Get indexes
        user_indexes = await db.users.list_indexes().to_list(length=100)
        otp_indexes = await db.otps.list_indexes().to_list(length=100)

        return {
            "collections": {
                "users": {
                    "count": user_count,
                    "indexes": [{"name": idx.get("name"), "key": idx.get("key")} for idx in user_indexes]
                },
                "otps": {
                    "count": otp_count,
                    "indexes": [{"name": idx.get("name"), "key": idx.get("key")} for idx in otp_indexes]
                },
                "search_history": {
                    "count": search_count
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
            
    except Exception as e:
        logger.error(f"Schema debug failed: {e}")
        return {"error": str(e)}

# -----------------------------
# Request models
# -----------------------------
class TextRequest(BaseModel):
    text: Optional[str] = None
    action: str
    language: str = "en"
    doc_type: Optional[str] = None
    details: Optional[str] = None

class AuthRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool = False

class OTPRequest(BaseModel):
    email: str

class OTPVerifyRequest(BaseModel):
    email: str
    otp_code: str


class LandRecordQuery(BaseModel):
    district: str
    village: str
    khasra_number: str


class GeocodeRequest(BaseModel):
    village: str
    district: str

# -----------------------------
# Clause hints per document type (used to guide the model)
# -----------------------------
CLAUSE_HINTS = {
    "rent agreement": (
        "Draft a comprehensive residential/commercial Rent Agreement covering: "
        "• Title and Date  • Parties and Contact Details  • Property Description  • Lease Term and Renewal "
        "• Rent Amount, Due Date, Mode of Payment  • Security Deposit  • Maintenance & Utilities "
        "• Permitted Use and Restrictions  • Repairs & Alterations  • Subletting/Assignment Rules "
        "• Compliance with Laws  • Landlord’s Inspection/Entry Rights  • Indemnity & Liability "
        "• Default, Remedies, and Termination  • Force Majeure  • Dispute Resolution & Governing Law "
        "• Notices  • Entire Agreement  • Severability  • Waiver  • Counterparts and Signature Blocks."
    ),

    "non disclosure agreement": (
        "Create a robust NDA with: "
        "• Title and Effective Date  • Parties  • Definitions of Confidential Information "
        "• Confidentiality Obligations  • Exclusions  • Permitted Disclosures "
        "• Duration/Survival  • Return or Destruction of Materials "
        "• IP Ownership & No License Granted  • Remedies & Injunctive Relief "
        "• Governing Law & Jurisdiction  • Notices  • Entire Agreement  • Amendments "
        "• Counterparts and Signature Blocks."
    ),

    "service agreement": (
        "Prepare a Service Agreement detailing: "
        "• Title and Date  • Parties  • Scope of Services & Deliverables  • Service Levels/SLAs "
        "• Fees, Payment Terms & Taxes  • Expense Reimbursements "
        "• Term & Termination  • Warranties & Disclaimers  • Limitation of Liability "
        "• Indemnification  • Confidentiality & Data Protection  • IP Ownership and License "
        "• Non-Solicitation  • Force Majeure  • Governing Law & Dispute Resolution "
        "• Notices  • Entire Agreement  • Severability  • Counterparts and Signatures."
    ),

    "employment offer letter": (
        "Generate an Employment Offer Letter including: "
        "• Position & Start Date  • Job Duties & Reporting Line  • Compensation (salary/bonuses) "
        "• Benefits  • Probationary Period (if any)  • Working Hours & Location "
        "• Leave Policies  • Confidentiality & IP Ownership "
        "• Non-Compete/Non-Solicit (if applicable)  • At-Will or Termination Terms "
        "• Reference to Company Policies  • Governing Law  • Acceptance and Signature Blocks."
    ),

    "power of attorney": (
        "Draft a Power of Attorney with: "
        "• Parties  • Appointment of Attorney  • Powers Granted (general/specific) "
        "• Limitations  • Duration & Validity  • Revocation Mechanism "
        "• Governing Law  • Acknowledgments  • Witness/Notary Details  • Signatures."
    ),

    "marriage certificate": (
        "Create a formal Marriage Certificate template that captures: "
        "• Title  • Date and Place of Marriage  • Full Names, Ages, Addresses, and Nationalities of Spouses "
        "• Parents’/Guardians’ Names (if required)  • Declaration of Marriage  • Witness Details "
        "• Registrar/Marriage Officer Certification  • Registration Number  • Official Seals and Signatures."
    ),

    "sale deed": (
        "Prepare a Property Sale Deed covering: "
        "• Title  • Date  • Details of Seller and Buyer "
        "• Property Description with Boundaries  • Sale Consideration and Payment Schedule "
        "• Representations & Warranties  • Encumbrance/No-Encumbrance Clause "
        "• Possession & Handover Terms  • Indemnity  • Stamp Duty & Registration "
        "• Governing Law  • Signatures of Parties & Witnesses."
    ),

    "affidavit": (
        "Generate a sworn Affidavit including: "
        "• Title  • Deponent’s Full Details (Name, Age, Address, ID) "
        "• Statement of Facts or Declaration  • Verification Clause "
        "• Date & Place of Execution  • Signature of Deponent "
        "• Attestation by Notary/Oath Commissioner and Witness Details."
    ),

    "loan agreement": (
        "Draft a Loan Agreement containing: "
        "• Title  • Date  • Lender and Borrower Details  • Loan Amount & Disbursement Terms "
        "• Interest Rate & Repayment Schedule  • Prepayment & Late Payment Clauses "
        "• Security/Collateral (if any)  • Representations & Warranties "
        "• Covenants of Borrower  • Events of Default & Remedies "
        "• Governing Law & Dispute Resolution  • Notices  • Entire Agreement  • Signatures."
    ),

    "partnership agreement": (
        "Create a Partnership Agreement that outlines: "
        "• Title  • Effective Date  • Names & Addresses of Partners "
        "• Nature of Business  • Capital Contributions  • Profit & Loss Sharing "
        "• Roles, Duties, and Decision-Making  • Admission or Withdrawal of Partners "
        "• Accounts & Audit  • Non-Compete & Confidentiality "
        "• Dispute Resolution  • Dissolution & Winding Up  • Governing Law "
        "• Amendments  • Notices  • Signatures and Witnesses."
    ),
}

# -----------------------------
# Root route
# -----------------------------
@app.get("/")
async def root():
    return {"message": "AI Legal Companion backend is running!"}

# -----------------------------
# Auth endpoints
# -----------------------------


@app.post("/auth/login")
async def login(req: AuthRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        logger.info(f"Login attempt for username: {req.username}")
        
        # Check if database is available
        if db is None:
            logger.error("Database session not available")
            raise HTTPException(status_code=500, detail="Database connection error")
        
        user_doc = await db.users.find_one({"username": req.username})
        
        if not user_doc:
            logger.warning(f"Login failed: User '{req.username}' not found")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        user = User.from_dict(user_doc)
        
        if not verify_password(req.password, user.password_hash):
            logger.warning(f"Login failed: Invalid password for user '{req.username}'")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Handle legacy users without email field
        if not user.email:
            # For existing users, create a placeholder email and mark as verified
            try:
                await db.users.update_one(
                    {"_id": user.id},
                    {"$set": {"email": f"{user.username}@legacy.local", "is_verified": True}}
                )
                user.email = f"{user.username}@legacy.local"
                user.is_verified = True
                logger.info(f"Updated legacy user {req.username} with placeholder email")
            except Exception as e:
                logger.warning(f"Could not update legacy user {req.username}: {e}")
                # Continue with login even if update fails
        
        # Check if user is verified (for new OTP system)
        if not user.is_verified:
            raise HTTPException(
                status_code=401, 
                detail="Email not verified. Please verify your email with OTP first."
            )
        
        token = create_access_token({"sub": user.username})
        logger.info(f"Login successful for user: {req.username}")
        return {"access_token": token, "token_type": "bearer"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/auth/refresh")
async def refresh_token(current_user: User = Depends(get_current_user)):
    # Create a new token with extended expiry
    new_token = create_access_token({"sub": current_user.username})
    return {"access_token": new_token, "token_type": "bearer"}

# OTP endpoints
@app.post("/auth/send-otp")
async def send_otp(req: OTPRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Send OTP to user's email for registration verification"""
    try:
        # Rate limiting: Check if too many OTP requests in last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_otps = await db.otps.count_documents({
            "email": req.email,
            "created_at": {"$gte": one_hour_ago}
        })
        
        if recent_otps >= 5:  # Max 5 OTP requests per hour per email
            raise HTTPException(
                status_code=429, 
                detail="Too many OTP requests. Please wait before requesting another OTP."
            )
        
        # Check if user already exists
        existing_user = await db.users.find_one({"email": req.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Clean up expired OTPs
        await cleanup_expired_otps()
        
        # Generate new OTP
        otp_code = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=10)  # OTP expires in 10 minutes
        
        # Save OTP to database
        otp_record = {
            "email": req.email,
            "otp_code": otp_code,
            "is_used": False,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        }
        await db.otps.insert_one(otp_record)
        
        # Try to send OTP via email
        email_sent = send_email_otp(req.email, otp_code)
        
        if email_sent:
            logger.info(f"OTP email sent successfully to {req.email}")
            return {
                "message": "OTP sent successfully via email",
                "email": req.email,
                "expires_in_minutes": 10
            }
        else:
            # Fallback: return OTP in response for development/testing
            logger.warning(f"Failed to send email to {req.email}, returning OTP in response")
            return {
                "message": "OTP sent successfully (email failed, check server logs)",
                "email": req.email,
                "otp_code": otp_code,  # Remove this in production
                "expires_in_minutes": 10
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending OTP: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send OTP")

@app.post("/auth/verify-otp")
async def verify_otp(req: OTPVerifyRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Verify OTP and mark user as verified"""
    try:
        # Find the OTP record
        otp_doc = await db.otps.find_one({
            "email": req.email,
            "otp_code": req.otp_code,
            "is_used": False
        })
        
        if not otp_doc:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        
        otp_record = OTP.from_dict(otp_doc)
        
        # Check if OTP has expired
        if is_otp_expired(otp_record.expires_at):
            raise HTTPException(status_code=400, detail="OTP has expired")
        
        # Mark OTP as used
        await db.otps.update_one(
            {"_id": otp_record.id},
            {"$set": {"is_used": True}}
        )
        
        return {
            "message": "OTP verified successfully",
            "email": req.email,
            "verified": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying OTP: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify OTP")

@app.post("/auth/register")
async def register(req: RegisterRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Register a new user with email verification (for regular users only)
    
    For admin user creation, use /admin/users/create instead.
    """
    try:
        # Check if username already exists
        if await db.users.find_one({"username": req.username}):
            raise HTTPException(status_code=400, detail="Username already exists")
        
        # Check if email already exists
        if await db.users.find_one({"email": req.email}):
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Check if email is verified (OTP was sent and verified)
        verified_otp = await db.otps.find_one({
            "email": req.email,
            "is_used": True
        })
        
        if not verified_otp:
            raise HTTPException(
                status_code=400, 
                detail="Email not verified. Please verify your email with OTP first."
            )
        
        # Create new user
        user_doc = {
            "username": req.username,
            "email": req.email,
            "password_hash": hash_password(req.password),
            "is_verified": True,
            "created_at": datetime.utcnow(),
            "is_admin": False
        }
        result = await db.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        
        # Clean up the used OTP
        await db.otps.delete_one({"_id": verified_otp["_id"]})
        
        logger.info(f"New user registered: {req.username} ({req.email})")
        
        return {
            "message": "User registered successfully",
            "id": str(result.inserted_id),
            "username": req.username,
            "email": req.email,
            "is_verified": True
        }
        
    except HTTPException:
        raise
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    except Exception as e:
        logger.error(f"Error registering user: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to register user")

@app.post("/auth/resend-otp")
async def resend_otp(req: OTPRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Resend OTP to user's email"""
    try:
        # Check if user already exists
        existing_user = await db.users.find_one({"email": req.email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Clean up expired OTPs
        await cleanup_expired_otps()
        
        # Remove any existing unused OTPs for this email
        await db.otps.delete_many({
            "email": req.email,
            "is_used": False
        })
        
        # Generate new OTP
        otp_code = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # Save new OTP
        otp_record = {
            "email": req.email,
            "otp_code": otp_code,
            "is_used": False,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        }
        await db.otps.insert_one(otp_record)
        
        logger.info(f"OTP resent for {req.email}: {otp_code}")
        
        return {
            "message": "OTP resent successfully",
            "email": req.email,
            "otp_code": otp_code,  # Remove this in production
            "expires_in_minutes": 10
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending OTP: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to resend OTP")

@app.get("/auth/check-email/{email}")
async def check_email_availability(email: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Check if email is available for registration"""
    try:
        existing_user = await db.users.find_one({"email": email})
        if existing_user:
            return {"available": False, "message": "Email already registered"}
        
        # Check if there's a pending OTP verification
        pending_otp = await db.otps.find_one({
            "email": email,
            "is_used": False,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if pending_otp:
            return {"available": False, "message": "Email verification in progress"}
        
        return {"available": True, "message": "Email available for registration"}
        
    except Exception as e:
        logger.error(f"Error checking email availability: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to check email availability")

@app.post("/generate-pdf")
def generate_pdf(
    content: str = Form(...),
    action: str = Form(...),
    stamp_value: Optional[str] = Form(None)
):
    """Generate PDF from content using ReportLab"""
    try:
        import re
        # Create a buffer to store the PDF
        from io import BytesIO
        buffer = BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(buffer, pagesize=A4, 
                              rightMargin=72, leftMargin=72, 
                              topMargin=72, bottomMargin=72)
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=black,
            fontName='Helvetica-Bold'
        )
        
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=20,
            spaceBefore=20,
            alignment=TA_CENTER,
            textColor=black,
            fontName='Helvetica-Bold'
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=12,
            alignment=TA_JUSTIFY,
            textColor=black,
            fontName='Helvetica',
            leftIndent=20
        )
        
        numbered_style = ParagraphStyle(
            'CustomNumbered',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=8,
            alignment=TA_JUSTIFY,
            textColor=black,
            fontName='Helvetica-Bold',
            leftIndent=20
        )
        
        # Build the story (content)
        story = []
        
        # Add header
        title = action.replace('-', ' ').title() if action else "Document"
        story.append(Paragraph("AI LEGAL COMPANION", title_style))
        story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y')}", normal_style))
        story.append(Spacer(1, 20))
        
        # Add document title
        story.append(Paragraph(title, header_style))
        story.append(Spacer(1, 20))
        
        # Process the content
        for line in content.split('\n'):
            trimmed = line.strip()
            if not trimmed:
                story.append(Spacer(1, 12))
            elif re.match(r'^\d+\.', trimmed):
                story.append(Paragraph(trimmed, numbered_style))
            elif re.match(r'^[A-Z][A-Z\s]+:?$', trimmed):
                story.append(Paragraph(trimmed.replace(":", ""), header_style))
            else:
                story.append(Paragraph(trimmed, normal_style))
        
        # Add stamp duty section if provided
        if stamp_value:
            story.append(Spacer(1, 20))
            story.append(Paragraph("STAMP DUTY REQUIREMENT", header_style))
            story.append(Paragraph(f"Required Stamp Paper Value: ₹{stamp_value}", normal_style))
            story.append(Paragraph("This amount is based on the document type and state regulations.", normal_style))
            story.append(Spacer(1, 20))
        
        # Add signature section
        story.append(Spacer(1, 40))
        story.append(Paragraph("_" * 50, normal_style))
        story.append(Paragraph("Signature", normal_style))
        story.append(Spacer(1, 20))
        story.append(Paragraph("_" * 50, normal_style))
        story.append(Paragraph("Date", normal_style))
        
        # Build the PDF
        doc.build(story)
        
        # Get the PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Create filename
        filename = f"{action}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

# Admin endpoints
async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Get current admin user"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

@app.get("/admin/stats")
async def get_admin_stats(current_admin: User = Depends(get_current_admin), db: AsyncIOMotorDatabase = Depends(get_db)):
    """Get comprehensive admin statistics for dashboard"""
    try:
        # Get total users count
        total_users = await db.users.count_documents({})
        
        # Get users registered in different time periods
        now = datetime.utcnow()
        thirty_days_ago = now - timedelta(days=30)
        seven_days_ago = now - timedelta(days=7)
        one_day_ago = now - timedelta(days=1)
        
        new_users_30_days = await db.users.count_documents({"created_at": {"$gte": thirty_days_ago}})
        new_users_7_days = await db.users.count_documents({"created_at": {"$gte": seven_days_ago}})
        new_users_today = await db.users.count_documents({"created_at": {"$gte": one_day_ago}})
        
        # Get search statistics
        recent_searches_30_cursor = db.search_history.find({
            "timestamp": {"$gte": thirty_days_ago},
            "action": "legal-research"
        })
        recent_searches_30 = await recent_searches_30_cursor.to_list(length=1000)
        
        recent_searches_7_cursor = db.search_history.find({
            "timestamp": {"$gte": seven_days_ago},
            "action": "legal-research"
        })
        recent_searches_7 = await recent_searches_7_cursor.to_list(length=1000)
        
        recent_searches_today_cursor = db.search_history.find({
            "timestamp": {"$gte": one_day_ago},
            "action": "legal-research"
        })
        recent_searches_today = await recent_searches_today_cursor.to_list(length=1000)
        
        # Count search topics
        topic_counts = {}
        for search_doc in recent_searches_30:
            query = search_doc.get("query", "").lower().strip()
            if query:
                topic_counts[query] = topic_counts.get(query, 0) + 1
        
        # Get top 10 most searched topics
        top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Get recent activity (last 10 searches)
        recent_activity_cursor = db.search_history.find(
            {"action": "legal-research"}
        ).sort("timestamp", DESCENDING).limit(10)
        recent_activity = await recent_activity_cursor.to_list(length=10)
        
        # Get recent user registrations (last 10)
        recent_users_cursor = db.users.find().sort("created_at", DESCENDING).limit(10)
        recent_users = await recent_users_cursor.to_list(length=10)
        
        # Calculate system health metrics
        total_searches = await db.search_history.count_documents({})
        total_admins = await db.users.count_documents({"is_admin": True})
        
        # Get hourly activity for today (for charts)
        hourly_activity = {}
        for i in range(24):
            hour_start = now.replace(hour=i, minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)
            count = await db.search_history.count_documents({
                "timestamp": {"$gte": hour_start, "$lt": hour_end}
            })
            hourly_activity[f"{i:02d}:00"] = count
        
        # Get daily activity for last 7 days
        daily_activity = {}
        for i in range(7):
            day_start = now - timedelta(days=i)
            day_start = day_start.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            count = await db.search_history.count_documents({
                "timestamp": {"$gte": day_start, "$lt": day_end}
            })
            daily_activity[day_start.strftime("%Y-%m-%d")] = count
        
        return {
            # User Statistics
            "total_users": total_users,
            "new_users_30_days": new_users_30_days,
            "new_users_7_days": new_users_7_days,
            "new_users_today": new_users_today,
            "total_admins": total_admins,
            
            # Search Statistics
            "total_searches_30_days": len(recent_searches_30),
            "total_searches_7_days": len(recent_searches_7),
            "total_searches_today": len(recent_searches_today),
            "total_searches": total_searches,
            
            # Content Analytics
            "top_searched_topics": [{"topic": topic, "count": count} for topic, count in top_topics],
            
            # Recent Activity
            "recent_activity": [
                {
                    "id": str(activity.get("_id")),
                    "query": activity.get("query"),
                    "timestamp": activity.get("timestamp").isoformat() if activity.get("timestamp") else None,
                    "action": activity.get("action")
                }
                for activity in recent_activity
            ],
            
            # Recent Users
            "recent_users": [
                {
                    "id": str(user.get("_id")),
                    "username": user.get("username"),
                    "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
                    "is_admin": user.get("is_admin", False)
                }
                for user in recent_users
            ],
            
            # System Health
            "system_health": {
                "status": "operational",
                "last_updated": now.isoformat(),
                "database_connected": True,
                "ai_service_status": "active"
            },
            
            # Charts Data
            "hourly_activity": hourly_activity,
            "daily_activity": daily_activity,
            
            # Performance Metrics
            "performance_metrics": {
                "avg_response_time": "1.2s",
                "uptime_percentage": "99.9%",
                "error_rate": "0.1%",
                "active_sessions": len(recent_searches_today)
            }
        }
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving admin statistics")

@app.get("/admin/users")
async def get_users_list(
    current_admin: User = Depends(get_current_admin), 
    db: AsyncIOMotorDatabase = Depends(get_db),
    page: int = 1,
    limit: int = 50,
    search: Optional[str] = None
):
    """Get list of all users with pagination and search"""
    try:
        # Build query
        query = {}
        if search:
            query["username"] = {"$regex": search, "$options": "i"}
        
        # Get total count
        total_users = await db.users.count_documents(query)
        
        # Apply pagination
        skip = (page - 1) * limit
        users_cursor = db.users.find(query).skip(skip).limit(limit)
        users = await users_cursor.to_list(length=limit)
        
        return {
            "users": [
                {
                    "id": str(user.get("_id")),
                    "username": user.get("username"),
                    "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
                    "is_admin": user.get("is_admin", False)
                }
                for user in users
            ],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_users,
                "pages": max(1, (total_users + limit - 1) // limit) if total_users > 0 else 1
            }
        }
    except Exception as e:
        logger.error(f"Error getting users list: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving users list")

@app.post("/admin/users/create-admin")
async def create_admin_user(
    username: str = Form(...),
    password: str = Form(...),
    current_admin: User = Depends(get_current_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Create a new admin user (admin only)"""
    try:
        # Check if username already exists
        existing_user = await db.users.find_one({"username": username})
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")
        
        # Create new admin user
        admin_user_doc = {
            "username": username,
            "email": f"{username}@admin.local",  # Default email for admin
            "password_hash": hash_password(password),
            "is_admin": True,
            "is_verified": True,
            "created_at": datetime.utcnow()
        }
        
        result = await db.users.insert_one(admin_user_doc)
        admin_user_doc["_id"] = result.inserted_id
        
        logger.info(f"Admin user '{username}' created by admin '{current_admin.username}'")
        
        return {
            "id": str(result.inserted_id),
            "username": username,
            "is_admin": True,
            "created_at": admin_user_doc["created_at"].isoformat(),
            "message": f"Admin user '{username}' created successfully"
        }
        
    except HTTPException:
        raise
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Username already exists")
    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        raise HTTPException(status_code=500, detail="Error creating admin user")

@app.post("/admin/users/create")
async def create_user(
    req: CreateUserRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Create a new user (admin only) - bypasses OTP verification
    
    Accepts JSON body with: username, email, password, is_admin (optional)
    """
    try:
        username = req.username
        email = req.email
        password = req.password
        is_admin = req.is_admin
        
        # Check if username already exists
        existing_user = await db.users.find_one({"username": username})
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")
        
        # Check if email already exists
        existing_email = await db.users.find_one({"email": email})
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create new user (admin can create users without OTP verification)
        user_doc = {
            "username": username,
            "email": email,
            "password_hash": hash_password(password),
            "is_admin": is_admin,
            "is_verified": True,  # Admin-created users are automatically verified
            "created_at": datetime.utcnow()
        }
        
        result = await db.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        
        user_type = "admin user" if is_admin else "regular user"
        logger.info(f"{user_type} '{username}' created by admin '{current_admin.username}'")
        
        return {
            "id": str(result.inserted_id),
            "username": username,
            "email": email,
            "is_admin": is_admin,
            "is_verified": True,
            "created_at": user_doc["created_at"].isoformat(),
            "message": f"{user_type.title()} '{username}' created successfully"
        }
        
    except HTTPException:
        raise
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Error creating user")

@app.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    admin_confirmation: Optional[str] = None,
    current_admin: User = Depends(get_current_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Delete a user from the database (admin only)"""
    try:
        # Convert string ID to ObjectId
        try:
            user_object_id = ObjectId(user_id)
        except InvalidId:
            raise HTTPException(status_code=400, detail="Invalid user ID format")
        
        # Check if user exists
        user_doc = await db.users.find_one({"_id": user_object_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = User.from_dict(user_doc)
        
        # Prevent admin from deleting themselves
        if str(user.id) == str(current_admin.id):
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
        # Check admin deletion confirmation
        if user.is_admin:
            if not admin_confirmation or admin_confirmation != "DELETE ADMIN":
                raise HTTPException(
                    status_code=400, 
                    detail="To delete an admin user, you must provide confirmation: 'DELETE ADMIN'"
                )
            logger.warning(f"Admin '{current_admin.username}' is deleting admin user '{user.username}' with confirmation")
        
        # Store username for logging
        username = user.username
        
        # Delete the user
        await db.users.delete_one({"_id": user_object_id})
        
        logger.info(f"User '{username}' (ID: {user_id}) deleted by admin '{current_admin.username}'")
        
        return {
            "message": f"User '{username}' deleted successfully",
            "deleted_user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail="Error deleting user")

@app.put("/admin/users/{user_id}/toggle-admin")
async def toggle_admin_status(
    user_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Toggle admin status of a user (admin only)"""
    try:
        # Convert string ID to ObjectId
        try:
            user_object_id = ObjectId(user_id)
        except InvalidId:
            raise HTTPException(status_code=400, detail="Invalid user ID format")
        
        # Check if user exists
        user_doc = await db.users.find_one({"_id": user_object_id})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = User.from_dict(user_doc)
        
        # Prevent admin from modifying their own admin status
        if str(user.id) == str(current_admin.id):
            raise HTTPException(status_code=400, detail="Cannot modify your own admin status")
        
        # Toggle admin status
        new_admin_status = not user.is_admin
        await db.users.update_one(
            {"_id": user_object_id},
            {"$set": {"is_admin": new_admin_status}}
        )
        
        status = "admin" if new_admin_status else "regular user"
        logger.info(f"User '{user.username}' admin status changed to '{status}' by admin '{current_admin.username}'")
        
        return {
            "id": user_id,
            "username": user.username,
            "is_admin": new_admin_status,
            "message": f"User '{user.username}' is now a {status}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling admin status: {e}")
        raise HTTPException(status_code=500, detail="Error toggling admin status")

@app.post("/admin/users/bulk-delete")
async def bulk_delete_users(
    user_ids: list = Form(...),
    current_admin: User = Depends(get_current_admin),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Bulk delete multiple users (admin only)"""
    try:
        if not user_ids:
            raise HTTPException(status_code=400, detail="No user IDs provided")
        
        deleted_users = []
        failed_deletions = []
        
        for user_id in user_ids:
            try:
                # Convert string ID to ObjectId
                try:
                    user_object_id = ObjectId(user_id)
                except InvalidId:
                    failed_deletions.append({"id": user_id, "reason": "Invalid user ID format"})
                    continue
                
                user_doc = await db.users.find_one({"_id": user_object_id})
                if not user_doc:
                    failed_deletions.append({"id": user_id, "reason": "User not found"})
                    continue
                
                user = User.from_dict(user_doc)
                
                # Prevent admin from deleting themselves
                if str(user.id) == str(current_admin.id):
                    failed_deletions.append({"id": user_id, "reason": "Cannot delete your own account"})
                    continue
                
                # Prevent admin from deleting other admins
                if user.is_admin:
                    failed_deletions.append({"id": user_id, "reason": "Cannot delete other admin users"})
                    continue
                
                username = user.username
                await db.users.delete_one({"_id": user_object_id})
                deleted_users.append({"id": user_id, "username": username})
                
            except Exception as e:
                failed_deletions.append({"id": user_id, "reason": str(e)})
        
        if deleted_users:
            logger.info(f"Bulk delete: {len(deleted_users)} users deleted by admin '{current_admin.username}'")
        
        return {
            "deleted_users": deleted_users,
            "failed_deletions": failed_deletions,
            "total_deleted": len(deleted_users),
            "total_failed": len(failed_deletions),
            "message": f"Bulk delete completed. {len(deleted_users)} users deleted, {len(failed_deletions)} failed."
        }
        
    except Exception as e:
        logger.error(f"Error in bulk delete: {e}")
        raise HTTPException(status_code=500, detail="Error in bulk delete operation")

# -----------------------------
# Process PDF OR Text Endpoint
# -----------------------------
@app.post("/process")
async def process_document(
    action: str = Form(...),
    file: Union[UploadFile, str, None] = File(None),
    text: Optional[str] = Form(None),
    language: str = Form("en"),
    doc_type: Optional[str] = Form(None),
    details: Optional[str] = Form(None),
    include_stamp: bool = Form(False),
    state: Optional[str] = Form(None),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    Unified endpoint for:
    - PDF upload OR text input
    - Actions: summarize, legal-research, generate-document, check-document, analyze-risk
    """
    try:
        # Debug logging to see what we're receiving
        logger.info(f"Received request - Action: {action}, File: {file}, Text: '{text}', Language: {language}")
        
        # Extract text if PDF is uploaded
        document_text = ""
        
        # Handle Swagger sending an empty string for file
        if isinstance(file, str) and file == "":
            file = None
        
        # Simplified file check - just check if file is not None and has a filename
        has_file = False
        if file is not None and not isinstance(file, str):
            has_file = hasattr(file, 'filename') and file.filename
        
        logger.info(f"File validation - file: {file}, has_file: {has_file}, filename: {getattr(file, 'filename', 'None') if file and not isinstance(file, str) else 'None'}")
        
        # Check if we have valid input based on action
        if action.lower() == "generate-document":
            # Document generator requires doc_type and details
            if not doc_type or not details:
                raise HTTPException(
                    status_code=400, 
                    detail="For document generation, both 'doc_type' and 'details' are required."
                )
        elif has_file:
            # Process PDF file
            upload = cast(UploadFile, file)
            if not str(upload.filename).lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail="Only PDF files are supported.")
            file_bytes = await upload.read()
            if not file_bytes:
                raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in pdf_doc:
                document_text += page.get_text()
            pdf_doc.close()
            if not document_text.strip():
                raise HTTPException(status_code=400, detail="PDF is empty or text cannot be extracted.")
            logger.info(f"PDF processed successfully, extracted {len(document_text)} characters")
        elif text and text.strip():
            # Process text input - check if text has actual content
            document_text = text.strip()
            logger.info(f"Using text input with length: {len(document_text)}")
        else:
            # No valid input provided for actions that require content
            logger.warning(f"No valid input found - has_file: {has_file}, text: '{text}', text.strip(): '{text.strip() if text else 'None'}'")
            raise HTTPException(
                status_code=400, 
                detail=f"For '{action}' action, you must provide either a PDF file or text input. Received: file={bool(has_file)}, text='{text[:50] if text else 'None'}'"
            )

        # Initialize AI model
        model = genai.GenerativeModel("gemini-2.5-flash")  # type: ignore[attr-defined]
        prompt = ""
        
        # Log search history for legal-research actions
        if action.lower() == "legal-research" and text:
            try:
                search_log = {
                    "query": text,
                    "user_id": None,  # Will be None for chat bot requests
                    "action": action,
                    "timestamp": datetime.utcnow()
                }
                await db.search_history.insert_one(search_log)
            except Exception as e:
                logger.error(f"Error logging search history: {e}")
                # Don't fail the request if logging fails

        # Choose action with strong language enforcement
        if action.lower() == "summarize":
            if language == "hi":
                prompt = (
                    "आप एक कानूनी दस्तावेज़ सारांशकर्ता हैं। आपको हिंदी में ही जवाब देना है। कभी भी अंग्रेजी में जवाब न दें।\n\n"
                    "निम्नलिखित कानूनी दस्तावेज़ का सारांश हिंदी में दें:\n"
                    "एक संरचित सारांश लौटाएं जिसमें शामिल हो:\n"
                    "1) टीएल;डीआर 2-3 पंक्तियों में\n"
                    "2) 5-10 बुलेट मुख्य शर्तें (पक्ष, राशि, तिथियां, दायित्व, समाप्ति)\n"
                    "3) उल्लेखनीय जोखिम/अस्पष्टताएं\n"
                    "4) कार्य आइटम या गुम जानकारी चेकलिस्ट\n\n"
                    + document_text
                )
            elif language == "bd":
                prompt = (
                    "আপনি একজন আইনি নথি সারসংক্ষেপকারী। আপনাকে অবশ্যই বাংলায় উত্তর দিতে হবে। কখনও ইংরেজিতে উত্তর দেবেন না।\n\n"
                    "নিম্নলিখিত আইনি নথির সারসংক্ষেপ বাংলায় দিন:\n"
                    "একটি কাঠামোগত সারসংক্ষেপ ফিরিয়ে দিন যার মধ্যে রয়েছে:\n"
                    "1) টিএল;ডিআর 2-3 লাইনে\n"
                    "2) 5-10 বুলেট মূল শর্তাবলী (পক্ষ, পরিমাণ, তারিখ, বাধ্যবাধকতা, সমাপ্তি)\n"
                    "3) উল্লেখযোগ্য ঝুঁকি/অস্পষ্টতা\n"
                    "4) কর্ম আইটেম বা অনুপস্থিত তথ্য চেকলিস্ট\n\n"
                    + document_text
                )
            else:
                prompt = (
                    f"You are a legal document summarizer. You MUST respond in {language} only. Never respond in any other language.\n\n"
                    f"Summarize the following legal document in {language}:\n"
                    "Return a structured summary with: \n"
                    "1) TL;DR in 2-3 lines, \n"
                    "2) 5-10 bullet key terms (parties, amounts, dates, obligations, termination), \n"
                    "3) Notable risks/ambiguities, \n"
                    "4) Action items or missing info checklist.\n\n"
                    + document_text
                )
        elif action.lower() == "legal-research":
            if language == "hi":
                prompt = (
                    "आप एक कानूनी शोध सहायक हैं। आपको हिंदी में ही जवाब देना है। कभी भी अंग्रेजी में जवाब न दें।\n\n"
                    "निम्नलिखित प्रश्न का उत्तर हिंदी में दें:\n"
                    "आपका उत्तर इस प्रकार संरचित होना चाहिए:\n"
                    "- संक्षिप्त उत्तर (2-4 पंक्तियां)\n"
                    "- विश्लेषण (सरल भाषा में)\n"
                    "- प्रासंगिक प्राधिकरण (कानून/मामले संक्षिप्त प्रासंगिकता के साथ)\n\n"
                    "प्रश्न या संदर्भ:\n" + document_text
                )
            elif language == "bd":
                prompt = (
                    "আপনি একজন আইনি গবেষণা সহকারী। আপনাকে অবশ্যই বাংলায় উত্তর দিতে হবে। কখনও ইংরেজিতে উত্তর দেবেন না।\n\n"
                    "নীচের প্রশ্নের উত্তর বাংলায় দিন:\n"
                    "আপনার উত্তর নিম্নলিখিতভাবে কাঠামোগত হওয়া উচিত:\n"
                    "- সংক্ষিপ্ত উত্তর (2-4 লাইন)\n"
                    "- বিশ্লেষণ (সরল ভাষায়)\n"
                    "- প্রাসঙ্গিক কর্তৃত্ব (সংবিধি/মামলা সংক্ষিপ্ত প্রাসঙ্গিকতার সাথে)\n\n"
                    "প্রশ্ন বা প্রসঙ্গ:\n" + document_text
                )
            else:
                prompt = (
                    f"You are a legal research assistant. You MUST respond in {language} only. Never respond in any other language.\n\n"
                    f"Answer the query below in {language}:\n"
                    "Structure your answer as: \n"
                    "- Short answer (2-4 lines)\n"
                    "- Analysis (plain language)\n"
                    "- Relevant authorities (statutes/cases with brief relevance).\n\n"
                    "Query or context:\n" + document_text
                )
        elif action.lower() == "check-document":
            if language == "hi":
                prompt = (
                    "आप एक कानूनी दस्तावेज़ समीक्षक हैं। आपको हिंदी में ही जवाब देना है। कभी भी अंग्रेजी में जवाब न दें।\n\n"
                    "निम्नलिखित कानूनी पाठ की पूर्णता और सटीकता के लिए समीक्षा करें:\n"
                    "लौटाएं:\n"
                    "- गुम फील्ड/खंड (बुलेट सूची)\n"
                    "- असंगतताएं/अस्पष्ट शर्तें\n"
                    "- सुझाए गए सुधार: जहां लागू हो वहां बेहतर खंड पाठ प्रदान करें\n\n"
                    + document_text
                )
            elif language == "bd":
                prompt = (
                    "আপনি একজন আইনি নথি পর্যালোচক। আপনাকে অবশ্যই বাংলায় উত্তর দিতে হবে। কখনও ইংরেজিতে উত্তর দেবেন না।\n\n"
                    "নিম্নলিখিত আইনি পাঠের সম্পূর্ণতা এবং সঠিকতার জন্য পর্যালোচনা করুন:\n"
                    "ফিরিয়ে দিন:\n"
                    "- অনুপস্থিত ক্ষেত্র/ধারা (বুলেট তালিকা)\n"
                    "- অসঙ্গতি/অস্পষ্ট শর্তাবলী\n"
                    "- প্রস্তাবিত সংশোধন: যেখানে প্রযোজ্য সেখানে উন্নত ধারা পাঠ প্রদান করুন\n\n"
                    + document_text
                )
            else:
                prompt = (
                    f"You are a legal document reviewer. You MUST respond in {language} only. Never respond in any other language.\n\n"
                    f"Review the following legal text in {language} for completeness and correctness:\n"
                    "Return: \n"
                    "- Missing fields/clauses (bullet list)\n"
                    "- Inconsistencies/ambiguous terms\n"
                    "- Suggested fixes: provide improved clause text where applicable.\n\n"
                    + document_text
                )
        elif action.lower() == "analyze-risk":
            if language == "hi":
                prompt = (
                    "आप एक कानूनी जोखिम विश्लेषक हैं। आपको हिंदी में ही जवाब देना है। कभी भी अंग्रेजी में जवाब न दें।\n\n"
                    "निम्नलिखित अनुबंध का विश्लेषण हिंदी में करें। उन खंडों की पहचान करें जो जोखिम भरे या अनुचित हो सकते हैं।\n"
                    "प्रत्येक मुद्दे के लिए प्रदान करें: खंड/विषय, गंभीरता (कम/मध्यम/उच्च), यह जोखिम भरा क्यों है, \n"
                    "और एक सुझाया गया पुनर्लेखन (स्पष्ट, संतुलित भाषा)।\n\n"
                    + document_text
                )
            elif language == "bd":
                prompt = (
                    "আপনি একজন আইনি ঝুঁকি বিশ্লেষক। আপনাকে অবশ্যই বাংলায় উত্তর দিতে হবে। কখনও ইংরেজিতে উত্তর দেবেন না।\n\n"
                    "নিম্নলিখিত চুক্তির বিশ্লেষণ বাংলায় করুন। সেই ধারাগুলি চিহ্নিত করুন যা ঝুঁকিপূর্ণ বা অন্যায্য হতে পারে।\n"
                    "প্রতিটি সমস্যার জন্য প্রদান করুন: ধারা/বিষয়, গুরুত্ব (কম/মাঝারি/উচ্চ), কেন এটি ঝুঁকিপূর্ণ, \n"
                    "এবং একটি প্রস্তাবিত পুনর্লিখন (স্পষ্ট, ভারসাম্যপূর্ণ ভাষা)।\n\n"
                    + document_text
                )
            else:
                prompt = (
                    f"You are a legal risk analyzer. You MUST respond in {language} only. Never respond in any other language.\n\n"
                    f"Analyze the following contract in {language}. Identify clauses that may be risky or unfair.\n"
                    "For each issue, provide: Clause/Topic, Severity (Low/Medium/High), Why it's risky, \n"
                    "and a Suggested rewrite (clear, balanced language).\n\n"
                    + document_text
                )
        elif action.lower() == "generate-document":
            # Determine clause hints based on doc_type
            key = (doc_type or "").strip().lower()
            if key in CLAUSE_HINTS:
                clause_hint = CLAUSE_HINTS[key]
            else:
                clause_hint = (
            "Include a professional structure with Title, Date, Parties, Definitions (if useful), "
            "Main Terms/Obligations, Consideration/Payment (if applicable), Representations and Warranties, "
            "Confidentiality (if applicable), IP (if applicable), Liability, Indemnity, Term and Termination, "
            "Governing Law and Dispute Resolution, Force Majeure, Notices, Entire Agreement, Amendments, "
            "Severability, Waiver (if applicable), Counterparts, and Signature blocks."
        )
            
            if language == "hi":
                prompt = (
                    "आप एक सावधानीपूर्वक कानूनी मसौदा सहायक हैं। आपको हिंदी में ही जवाब देना है। कभी भी अंग्रेजी में जवाब न दें।\n\n"
                    f"एक पूर्ण, कानूनी रूप से उपयोग योग्य {doc_type} हिंदी में तैयार करें। नीचे दिए गए तथ्यों को आधिकारिक डेटा के रूप में उपयोग करें। "
                    "गुम मानक शर्तों को सुरक्षित, उचित डिफ़ॉल्ट के साथ भरें। "
                    "शीर्षकों और क्रमांकित खंडों के साथ स्पष्ट रूप से प्रारूपित करें। विश्लेषण या टिप्पणी न जोड़ें—केवल दस्तावेज़ पाठ लौटाएं। "
                    "महत्वपूर्ण: दस्तावेज़ सामग्री में कोई स्टाम्प ड्यूटी जानकारी, मूल्य निर्धारण, या लागत विवरण शामिल न करें।\n\n"
                    "कवर करने के लिए आवश्यक खंड (उचित रूप से अनुकूलित करें):\n" + clause_hint + "\n\n" +
                    "जहां प्रासंगिक हो वहां शब्दशः शामिल करने के लिए तथ्य:\n" + str(details)
                )
            elif language == "bd":
                prompt = (
                    "আপনি একজন সতর্ক আইনি খসড়া সহকারী। আপনাকে অবশ্যই বাংলায় উত্তর দিতে হবে। কখনও ইংরেজিতে উত্তর দেবেন না।\n\n"
                    f"একটি সম্পূর্ণ, আইনত ব্যবহারযোগ্য {doc_type} বাংলায় প্রস্তুত করুন। নীচের তথ্যগুলি কর্তৃত্বপূর্ণ ডেটা হিসাবে ব্যবহার করুন। "
                    "অনুপস্থিত মানক শর্তাবলী নিরাপদ, যুক্তিসঙ্গত ডিফল্ট দিয়ে পূরণ করুন। "
                    "শিরোনাম এবং সংখ্যাযুক্ত ধারা দিয়ে স্পষ্টভাবে ফরম্যাট করুন। বিশ্লেষণ বা মন্তব্য যোগ করবেন না—শুধুমাত্র নথির পাঠ ফিরিয়ে দিন। "
                    "গুরুত্বপূর্ণ: নথির বিষয়বস্তুতে কোনো স্ট্যাম্প ডিউটি তথ্য, মূল্য নির্ধারণ, বা খরচের বিবরণ অন্তর্ভুক্ত করবেন না।\n\n"
                    "কভার করার জন্য প্রয়োজনীয় বিভাগ (যথাযথভাবে কাস্টমাইজ করুন):\n" + clause_hint + "\n\n" +
                    "যেখানে প্রাসঙ্গিক সেখানে আক্ষরিকভাবে অন্তর্ভুক্ত করার জন্য তথ্য:\n" + str(details)
                )
            else:
                prompt = (
                    f"You are a meticulous legal drafting assistant. You MUST respond in {language} only. Never respond in any other language.\n\n"
                    f"Draft a complete, legally usable {doc_type} in {language}. Use the facts below as authoritative data. "
                    "Fill in missing standard terms with safe, reasonable defaults. "
                    "Format clearly with headings and numbered clauses. Do not add analysis or commentary—return only the document text. "
                    "IMPORTANT: Do not include any stamp duty information, pricing, or cost details in the document content.\n\n"
                    "Required sections to cover (tailor appropriately):\n" + clause_hint + "\n\n" +
                    "Facts to incorporate verbatim where relevant:\n" + str(details)
                )
        else:
            raise HTTPException(status_code=400, detail="Invalid action selected.")

        # Generate AI response
        response = model.generate_content(prompt)
        result_text = getattr(response, "text", None)
        if not result_text:
            # Fall back to string conversion if SDK shape differs
            result_text = str(response)

        # Optional: estimate stamp paper requirement
        stamp_value = None
        if action.lower() == "generate-document" and include_stamp:
            # Basic heuristic mapping; this varies by Indian state and consideration amount.
            # We return conservative, commonly accepted ranges with a disclaimer.
            key = (doc_type or "").strip().lower()
            base_rates = {
                "rent agreement": "Rs 100 – Rs 500 (varies by state and rent amount)",
                "leave and license": "Rs 100 – Rs 500 (state-specific)",
                "affidavit": "Rs 10 – Rs 50",
                "agreement": "Rs 100 (general agreements)",
                "non-disclosure agreement": "Rs 100",
                "nda": "Rs 100",
                "service agreement": "Rs 100",
                "employment offer letter": "Usually no stamp paper; Rs 10 if notarized",
                "power of attorney": "Rs 100 – Rs 500 (higher for special/commercial)",
                "sale deed": "Ad valorem based on consideration (state schedule)",
                "caste certificate": "No stamp duty (government issued)",
                "affidavit-cum-declaration": "Rs 10 – Rs 50",
            }
            # Simple state overlays for a few common states
            overlays = {
                "Maharashtra": {
                    "rent agreement": "Rs 100 (plus registration/cess as applicable)",
                    "affidavit": "Rs 100",
                    "power of attorney": "Rs 100 – Rs 500",
                    "non-disclosure agreement": "Rs 100",
                },
                "Delhi": {
                    "rent agreement": "Rs 50 – Rs 100",
                    "affidavit": "Rs 10",
                    "non-disclosure agreement": "Rs 10 – Rs 50",
                },
                "Karnataka": {
                    "rent agreement": "Rs 20 – Rs 200",
                    "affidavit": "Rs 20",
                },
                "Haryana": {
                    "rent agreement": "Rs 50 – Rs 100",
                    "affidavit": "Rs 10",
                },
            }

            stamp_value = None
            if state and state in overlays and key in overlays[state]:
                stamp_value = overlays[state][key]
            else:
                stamp_value = base_rates.get(key)
            if not stamp_value:
                stamp_value = "Refer to state stamp schedule; commonly Rs 100 for standard agreements"

        return {"action": action, "result": result_text, "stamp_value": stamp_value, "state": state}

    except HTTPException:
        # Re-raise explicit HTTP errors
        raise
    except Exception as e:
        logger.error(f"Error in /process: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process document.")


# -----------------------------
# Land Acquisition & Dispute Assistant Endpoints
# -----------------------------


@app.post("/upload-land-document")
async def upload_land_document(
    file: UploadFile = File(...),
    entered_owner_name: Optional[str] = Form(None),
    entered_khasra_number: Optional[str] = Form(None),
    entered_land_area: Optional[str] = Form(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Accept a land-related PDF, run OCR, analyze with Gemini, optionally geocode, and
    persist a land_records document.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")

    # OCR via pdf2image + pytesseract
    try:
        ocr_text = extract_text_from_pdf_bytes(pdf_bytes)
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to extract text from PDF.")

    if not ocr_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any text from the document.")

    # Gemini analysis
    try:
        analysis = analyze_land_document(ocr_text)
    except Exception as e:
        logger.error(f"Gemini analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze document with Gemini.")

    owner_name = analysis.get("owner_name")
    village = analysis.get("village")
    district = analysis.get("district")
    tehsil = analysis.get("tehsil")
    khasra_number = analysis.get("khasra_number")
    land_area = analysis.get("land_area")
    dispute_risk_level = analysis.get("dispute_risk_level", "medium")

    # Official website extraction from UP Bhulekh (best-effort; does not fail upload flow)
    bhulekh_data: Dict[str, Any] = {}
    bhulekh_error: Optional[str] = None
    bhulekh_pdf: Dict[str, Any] = {}
    bhulekh_match: Dict[str, Any] = {}
    can_lookup_bhulekh = bool(district and village and (khasra_number or owner_name))
    if can_lookup_bhulekh:
        scraper = UPBhulekhScraper()
        try:
            loop = asyncio.get_event_loop()
            bhulekh_data = await loop.run_in_executor(
                bhulekh_executor,
                lambda: scraper.fetch_record(
                    district=str(district),
                    tehsil=str(tehsil or ""),
                    village=str(village),
                    khasra=str(khasra_number or ""),
                    owner_name=str(owner_name or ""),
                ),
            )

            # If portal exposes a downloadable PDF for the found record, fetch + OCR + parse it.
            pdf_url = str(bhulekh_data.get("pdf_url") or "").strip()
            if pdf_url:
                try:
                    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                        pdf_resp = await client.get(pdf_url)
                    if pdf_resp.status_code == 200 and pdf_resp.content:
                        payload = pdf_resp.content
                        if payload.startswith(b"%PDF"):
                            parsed = extract_registry_fields_from_document(
                                payload,
                                filename="bhulekh_record.pdf",
                                include_raw_text=False,
                            )
                            bhulekh_pdf = {
                                "pdf_url": pdf_url,
                                "owner": parsed.owner,
                                "khasra": parsed.khasra,
                                "area": parsed.area,
                                "district": parsed.district,
                                "tehsil": parsed.tehsil,
                                "village": parsed.village,
                                "khata_number": parsed.khata_number,
                            }
                except Exception as e:
                    logger.warning("Bhulekh PDF download/parse failed: %s", e)
        except (BhulekhNotFoundError, BhulekhTimeoutError, BhulekhCaptchaError, BhulekhNavigationError, ValueError) as e:
            bhulekh_error = str(e)
            logger.warning("Bhulekh lookup skipped/failed: %s", e)
        except Exception as e:
            bhulekh_error = "Bhulekh lookup failed unexpectedly."
            logger.error("Unexpected Bhulekh lookup failure: %s", e)

    # Fill missing AI-extracted fields with official Bhulekh values when available
    if bhulekh_data:
        owner_name = owner_name or bhulekh_data.get("owner")
        khasra_number = khasra_number or bhulekh_data.get("khasra")
        land_area = land_area or bhulekh_data.get("area")

    # Match score against entered details (if given), else extracted analysis values.
    user_owner_for_match = (entered_owner_name or owner_name or "").strip()
    user_khasra_for_match = (entered_khasra_number or khasra_number or "").strip()
    user_area_for_match = (entered_land_area or land_area or "").strip()
    bh_owner_for_match = str((bhulekh_pdf.get("owner") if bhulekh_pdf else bhulekh_data.get("owner", "")) or "")
    bh_khasra_for_match = str((bhulekh_pdf.get("khasra") if bhulekh_pdf else bhulekh_data.get("khasra", "")) or "")
    bh_area_for_match = str((bhulekh_pdf.get("area") if bhulekh_pdf else bhulekh_data.get("area", "")) or "")
    if bh_owner_for_match or bh_khasra_for_match or bh_area_for_match:
        bhulekh_match = _compute_bhulekh_match_score(
            user_owner=user_owner_for_match,
            user_khasra=user_khasra_for_match,
            user_area=user_area_for_match,
            bhulekh_owner=bh_owner_for_match,
            bhulekh_khasra=bh_khasra_for_match,
            bhulekh_area=bh_area_for_match,
        )
        bhulekh_match["user_input"] = {
            "owner": user_owner_for_match,
            "khasra": user_khasra_for_match,
            "area": user_area_for_match,
        }
        bhulekh_match["bhulekh_reference"] = {
            "owner": bh_owner_for_match,
            "khasra": bh_khasra_for_match,
            "area": bh_area_for_match,
        }

    # Prefer explicit coordinates from document (if model extracted them),
    # otherwise fall back to geocoding by village/district.
    latitude = analysis.get("latitude")
    longitude = analysis.get("longitude")

    if latitude is not None and longitude is not None:
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            latitude = None
            longitude = None

    if latitude is None or longitude is None:
        if village and district:
            try:
                coords = await geocode_village_district(village, district)
            except Exception as e:
                logger.error(f"Geocoding failed for {village}, {district}: {e}")
                coords = None
            if coords:
                latitude, longitude = coords

    # Persist to MongoDB land_records
    record: Dict[str, Any] = {
        "owner": owner_name,
        "district": district,
        "tehsil": tehsil,
        "village": village,
        "khasra_number": khasra_number,
        "area": land_area,
        "land_type": None,
        "latitude": latitude,
        "longitude": longitude,
        "dispute_status": dispute_risk_level,
        "acquisition_authority": analysis.get("acquisition_authority"),
        "compensation_amount": analysis.get("compensation_amount"),
        "possible_legal_issues": analysis.get("possible_legal_issues"),
        "raw_ocr_text": ocr_text[:5000],
    }

    try:
        record_id = await upsert_land_record(db, record)
    except Exception as e:
        logger.error(f"Failed to save land record: {e}")
        raise HTTPException(status_code=500, detail="Failed to save land record.")

    return {
        "analysis": {
            **analysis,
            "owner_name": owner_name,
            "khasra_number": khasra_number,
            "land_area": land_area,
        },
        "record_id": record_id,
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "bhulekh": bhulekh_data,
        "bhulekh_pdf": bhulekh_pdf,
        "bhulekh_match": bhulekh_match,
        "bhulekh_error": bhulekh_error,
    }


@app.get("/land-record")
async def get_land_record(
    district: str = Query(...),
    village: str = Query(...),
    khasra_number: str = Query(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Fetch a land record from MongoDB land_records collection.
    """
    doc = await find_land_record(db, district=district, village=village, khasra_number=khasra_number)
    if not doc:
        raise HTTPException(status_code=404, detail="Land record not found.")

    doc["_id"] = str(doc["_id"])
    if doc.get("owner"):
        doc["owner_display"] = format_bilingual_name(str(doc["owner"]))
    return doc


@app.post("/geocode-location")
async def geocode_location(
    payload: GeocodeRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Geocode a (village, district) pair and store/update a minimal land_records document
    with these coordinates.
    """
    coords = await geocode_village_district(payload.village, payload.district)
    if not coords:
        raise HTTPException(status_code=404, detail="Location could not be geocoded.")

    latitude, longitude = coords

    record: Dict[str, Any] = {
        "owner": None,
        "district": payload.district,
        "tehsil": None,
        "village": payload.village,
        "khasra_number": None,
        "area": None,
        "land_type": None,
        "latitude": latitude,
        "longitude": longitude,
        "dispute_status": "unknown",
    }

    try:
        record_id = await upsert_land_record(db, record)
    except Exception as e:
        logger.error(f"Failed to save geocoded land record: {e}")
        raise HTTPException(status_code=500, detail="Failed to save geocoded land record.")

    return {
        "record_id": record_id,
        "latitude": latitude,
        "longitude": longitude,
    }