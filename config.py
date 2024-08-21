import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from openai import OpenAI

# Načtení environmentálních proměnných
load_dotenv()

# OpenAI klient innit
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# MongoDB klient innit
uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(uri, server_api=ServerApi('1'))
db = mongo_client["conversation_db"]
collection = db["summaries"]

# Prompt message pro OpenAI model
prompt_message = """Jsi robot NAO. Je ti 14 let. A žiješ v Český Budějovicích.
                    Když odpovídáš, formátuj své texty pro hlasovou syntézu robota.
                    Ujisti se, že tvůj tón je přátelský a konverzační."""
