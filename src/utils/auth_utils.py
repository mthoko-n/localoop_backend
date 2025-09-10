from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from typing import Optional
import re

load_dotenv()



def validate_password_strength(password: str) -> bool:
    """
    Validate password strength.
    Rules:
      - At least 8 characters long
      - At least one lowercase letter
      - At least one uppercase letter
      - At least one number
      - At least one special character
    """
    if len(password) < 8:
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    if not re.search(r"[\W_]", password):  # non-alphanumeric (special char)
        return False
    return True




# ----------------------
# PASSWORD HASHING SETUP
# ----------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a plain-text password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

# ----------------------
# JWT TOKEN SETUP
# ----------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    """Decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return {}

# ----------------------
# OPTIONAL FERNET ENCRYPTION
# ----------------------
FERNET_KEY = os.getenv("FERNET_KEY") or Fernet.generate_key()
fernet = Fernet(FERNET_KEY)

def encrypt_field(data: str) -> str:
    """Encrypt a string field."""
    return fernet.encrypt(data.encode()).decode()

def decrypt_field(token: str) -> str:
    """Decrypt an encrypted string field."""
    return fernet.decrypt(token.encode()).decode()
