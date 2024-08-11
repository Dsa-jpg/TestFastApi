from typing import Optional, Union
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv


app = FastAPI()

# OAuth2PasswordBearer pro získání tokenu z hlavičky Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Načtení environmentálních proměnných ze souboru .env
load_dotenv()

app = FastAPI()

# OAuth2PasswordBearer pro získání tokenu z hlavičky Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Načtení tajného klíče z environmentálních proměnných
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class Item(BaseModel):
    name: str
    price: float
    is_offer: Union[bool, None] = None

class User(BaseModel):
    username: str

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_jwt(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_jwt(token)
    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return User(username=username)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Optional[str] = None, current_user: User = Depends(get_current_user)):
    return {"item_id": item_id, "q": q, "user": current_user.username}

@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item, current_user: User = Depends(get_current_user)):
    return {"item_name": item.name, "item_id": item_id, "user": current_user.username}

@app.post("/token")
def login(username: str):
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
