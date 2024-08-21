from config import client, collection

async def get_openai_response(model: str, prompt_message: str, context):
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt_message},
            *context
        ],
        stream=True
    )
    return response

def save_summary_to_mongodb(summary: dict):
    result = collection.insert_one(summary)
    return result
