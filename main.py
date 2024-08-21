from typing import Deque
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from collections import deque
import os
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from openai import OpenAI
from datetime import datetime
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# Načtení environmentálních proměnných ze souboru .env
load_dotenv()

# OpenAI client initialization
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MongoDB client initialization
uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(uri, server_api=ServerApi('1'))
db = mongo_client["conversation_db"]
collection = db["summaries"]

# Prompt message for the OpenAI model
prompt_message = """Jsi robot NAO. Je ti 14 let. A žiješ v Český Budějovicích.
                    Když odpovídáš, formátuj své texty pro hlasovou syntézu robota.
                    Ujisti se, že tvůj tón je přátelský a konverzační."""

app = FastAPI()

# Uchovávání kontextu posledních 3 dotazů v paměti
context: Deque[dict] = deque(maxlen=3)

@app.post("/sendquery")
async def send_query(request: Request):
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
async def end_conversation():
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
