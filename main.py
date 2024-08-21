from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from datetime import datetime
from collections import deque

from config import client, collection, prompt_message
from services import get_openai_response, save_summary_to_mongodb
from utils import generate_responses

app = FastAPI()
context = deque(maxlen=3)

@app.post("/sendquery")
async def send_query(request: Request):
    body = await request.json()
    model = body.get("model")
    user_message = body.get("user_message")

    if not model or not user_message:
        raise HTTPException(status_code=400, detail="Model and user_message must be provided.")

    context.append({"role": "user", "content": user_message})

    try:
        response = await get_openai_response(model, prompt_message, context)
        return StreamingResponse(generate_responses(response), media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.post("/endconversation")
async def end_conversation():
    if not context:
        raise HTTPException(status_code=400, detail="No conversation context available.")

    conversation_summary = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"Diskutovali jsme o: " + ", ".join([item['content'] for item in context])
    }

    try:
        summarized_text = await get_openai_response("gpt-4", "Shrň následující konverzaci do maximálně dvou vět.", [{"role": "user", "content": conversation_summary['summary']}])
        final_summary = {
            "timestamp": conversation_summary['timestamp'],
            "summary": summarized_text.strip()
        }
        result = save_summary_to_mongodb(final_summary)
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
