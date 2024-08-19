from typing import Optional, Union
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse

from openai import OpenAI

# Načtení environmentálních proměnných ze souboru .env
load_dotenv()

# OpenAI client initialization
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Prompt message for the OpenAI model
prompt_message = """Jsi robot NAO. Je ti 14 let. A žiješ v Český Budějovicích. 
                    Když odpovídáš, formátuj své věty jako lidskou řeč, s přirozenými pauzami po tečkách a čárkách.
                    Ujisti se, že tvůj tón je přátelský a konverzační."""


app = FastAPI()

# OAuth2PasswordBearer pro získání tokenu z hlavičky Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


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

# Endpoint to send query to OpenAI
@app.post("/sendquery")
async def send_query(request: Request):

    body = await request.json()
    model = body.get("model")
    user_message = body.get("user_message")

    if not model or not user_message:
        raise HTTPException(status_code=400, detail="Model and user_message must be provided.")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_message},
                {"role": "user", "content": user_message}
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


