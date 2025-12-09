from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import requests
from pypdf import PdfReader
from typing import List, Dict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv('settings/.env')
openai_client = OpenAI()

# Pushover configuration
pushover_user = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_url = "https://api.pushover.net/1/messages.json"

def push(message):
    if pushover_user and pushover_token:
        print(f"Push: {message}")
        payload = {"user": pushover_user, "token": pushover_token, "message": message}
        try:
            requests.post(pushover_url, data=payload)
        except Exception as e:
            print(f"Push notification failed: {e}")
    else:
        print(f"Push notification not configured: {message}")

# Store conversations in memory
conversations: Dict[str, List[Dict]] = {}

class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"

def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"Recording interest from {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}

def record_unknown_question(question):
    push(f"Recording {question} asked that I couldn't answer")
    return {"recorded": "ok"}

def handle_tool_calls(tool_calls):
    results = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        
        if tool_name == "record_user_details":
            result = record_user_details(**arguments)
        elif tool_name == "record_unknown_question":
            result = record_unknown_question(**arguments)
        else:
            result = {}
            
        results.append({
            "role": "tool",
            "content": json.dumps(result),
            "tool_call_id": tool_call.id
        })
    return results

class Me:
    def __init__(self):
        # Load prompts and configuration from settings
        try:
            with open("settings/config.txt", "r", encoding="utf-8") as c:
                config = json.load(c)
                self.name = config.get("name", "Assistant")

            with open("settings/prompts.txt", "r", encoding="utf-8") as f:
                prompts_config = json.load(f)
            
            #self.name = prompts_config.get("name", "Assistant")
        except Exception as e:
            print(f"Error loading name from prompts: {e}")
            self.name = "Assistant"
        
        # Load LinkedIn and summary from settings volume
        try:
            reader = PdfReader("settings/linkedin.pdf")
            self.linkedin = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    self.linkedin += text
        except:
            self.linkedin = "LinkedIn profile not available"
        
        try:
            with open("settings/summary.txt", "r", encoding="utf-8") as f:
                self.summary = f.read()
        except:
            self.summary = "Summary not available"
        
        # Load prompts and tools from settings
        try:
            self.system_prompt = prompts_config["system_prompt"].format(
                name=self.name, summary=self.summary, linkedin=self.linkedin
            )
            self.tools = prompts_config["tools"]
        except Exception as e:
            print(f"Error loading prompts: {e}")
            self.system_prompt = f"You are {self.name}. Answer questions professionally."
            self.tools = []

    def get_response(self, message: str, session_id: str = "default"):
        # Get or create conversation history
        if session_id not in conversations:
            conversations[session_id] = [{"role": "system", "content": self.system_prompt}]
        
        # Add user message
        conversations[session_id].append({"role": "user", "content": message})
        
        try:
            done = False
            while not done:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=conversations[session_id],
                    tools=self.tools
                )
                
                finish_reason = response.choices[0].finish_reason
                
                if finish_reason == "tool_calls":
                    message_obj = response.choices[0].message
                    tool_calls = message_obj.tool_calls
                    results = handle_tool_calls(tool_calls)
                    conversations[session_id].append(message_obj)
                    conversations[session_id].extend(results)
                else:
                    done = True
            
            # Add assistant response to conversation
            assistant_message = response.choices[0].message.content
            
            # Return response directly without evaluation
            conversations[session_id].append({"role": "assistant", "content": assistant_message})
            return assistant_message
            
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return "I'm having trouble processing your request right now. Please try again later."

me = Me()

@app.post("/chat")
async def chat(chat_message: ChatMessage):
    response = me.get_response(chat_message.message, chat_message.session_id)
    return {"response": response}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)