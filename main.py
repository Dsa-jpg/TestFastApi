from fastapi import FastAPI, Depends, HTTPException, status, Body, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import ObjectId
from datetime import datetime, timedelta
from typing import Optional, Deque
from collections import deque
from fastapi.responses import StreamingResponse
from openai import OpenAI
import os
from dotenv import load_dotenv


# Načtení environmentálních proměnných ze souboru .env
load_dotenv()

# OpenAI client initialization
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MongoDB client initialization
uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(uri, server_api=ServerApi('1'))
db1 = mongo_client["conversation_db"]
db = mongo_client["login_db"]
collection = db1["summaries"]
users_collection = db["users"] 

# Prompt message for the OpenAI model
prompt_message = """Jsi robot NAO. Je ti 14 let. A žiješ v Český Budějovicích.
                    Když odpovídáš, formátuj své texty pro hlasovou syntézu robota.
                    Ujisti se, že tvůj tón je přátelský a konverzační."""


# JWT settings
SECRET_KEY = os.getenv("JWT_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 password flow
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()



# Pydantic models
class User(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    hashed_password: str

class UserInDB(User):
    id: str

def get_user(username: str) -> Optional[UserInDB]:
    user = users_collection.find_one({"username": username})
    if user:
        return UserInDB(**user, id=str(user["_id"]))
    return None

def create_user(username: str, hashed_password: str) -> UserInDB:
    user_data = {"username": username, "hashed_password": hashed_password}
    result = users_collection.insert_one(user_data)
    return UserInDB(**user_data, id=str(result.inserted_id))


# Helper functions for MongoDB
def get_user(username: str) -> Optional[UserInDB]:
    user = users_collection.find_one({"username": username})
    if user:
        return UserInDB(**user, id=str(user["_id"]))
    return None

def create_user(username: str, hashed_password: str) -> UserInDB:
    user_data = {"username": username, "hashed_password": hashed_password}
    result = users_collection.insert_one(user_data)
    return UserInDB(**user_data, id=str(result.inserted_id))

# Helper functions for JWT
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Dependency to get the current user
async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# Uchovávání kontextu posledních 3 dotazů v paměti
context: Deque[dict] = deque(maxlen=3)

# Endpoint to register a new user
@app.post("/register")
async def register(username: str = Body(...), password: str = Body(...)):
    existing_user = get_user(username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    hashed_password = get_password_hash(password)
    new_user = create_user(username, hashed_password)
    return {"message": "User registered successfully", "user_id": new_user.id}

# Endpoint to obtain a JWT token
@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# Protected endpoint example
@app.get("/protected-endpoint")
async def protected_endpoint(current_user: UserInDB = Depends(get_current_user)):
    return {"message": f"Hello {current_user.username}, you have access to this protected endpoint!"}

@app.post("/sendquery")
async def send_query(request: Request,current_user: dict = Depends(get_current_user)):
    body = await request.json()
    model = body.get("model")
    user_message = body.get("user_message")
    if not model or not user_message:
        raise HTTPException(status_code=400, detail="Model and user_message must be provided.")
    # Přidání nového dotazu do kontextu
    context.append({"role": "user", "content": user_message})
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_message},
                *context  # Vložíme celý kontext
            ],
            stream=True  # Streaming responses from OpenAI API
        )
        async def generate_responses(response):
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        return StreamingResponse(generate_responses(response), media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
      
@app.post("/endconversation")
async def end_conversation(current_user: dict = Depends(get_current_user)):
    if not context:
        raise HTTPException(status_code=400, detail="No conversation context available.")
    # Připravíme shrnutí konverzace
    conversation_summary = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"Diskutovali jsme o: "
                   + ", ".join([item['content'] for item in context])
    }
    # Získáme shrnutí pomocí OpenAI
    try:
        summary_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Shrň následující konverzaci do maximálně dvou vět."},
                {"role": "user", "content": conversation_summary['summary']}
            ]
        )
        
        # Opravený přístup k obsahu odpovědi
        summarized_text = summary_response.choices[0].message.content
        # Vytvoříme konečný výstup pro uložení
        final_summary = {
            "timestamp": conversation_summary['timestamp'],
            "summary": summarized_text.strip()
        }

        # Uložení do MongoDB
        result = collection.insert_one(final_summary)

        # Vrátíme shrnutí a ID nového dokumentu jako potvrzení
        return {
            "message": "Summary saved successfully",
            "id": str(result.inserted_id),
            "summary": final_summary["summary"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving summary to MongoDB: {str(e)}")
      
@app.get("/")
async def root():
    return {"message": "NAO robot API is running"}



@app.get("/time")
async def time():
    now = datetime.now().__format__('%Y-%m-%d %H:%M:%S')
    return {"Current time":f"{now}"}
