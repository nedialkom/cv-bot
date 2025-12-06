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

# Gemini client for evaluation
gemini_client = OpenAI(
    api_key=os.getenv("GOOGLE_API_KEY"), 
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

class Evaluation(BaseModel):
    is_acceptable: bool
    feedback: str

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
        self.name = "Nedyalko Mihaylov"
        
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
        
        # System prompt from notebook
        self.system_prompt = f"""You are acting as {self.name}. You are answering questions on {self.name}'s website, particularly questions related to {self.name}'s career, background, skills and experience. Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible. You are given a summary of {self.name}'s background and LinkedIn profile which you can use to answer questions. Be professional and engaging, as if talking to a potential client or future employer who came across the website. If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool.

## Summary:
{self.summary}

## LinkedIn Profile:
{self.linkedin}

With this context, please chat with the user, always staying in character as {self.name}."""

        self.evaluator_system_prompt = f"""You are an evaluator that decides whether a response to a question is acceptable. You are provided with a conversation between a User and an Agent. Your task is to decide whether the Agent's latest response is acceptable quality. The Agent is playing the role of {self.name} and is representing {self.name} on their website. The Agent has been instructed to be professional and engaging, as if talking to a potential client or future employer who came across the website. The Agent has been provided with context on {self.name} in the form of their summary and LinkedIn details. Here's the information:

## Summary:
{self.summary}

## LinkedIn Profile:
{self.linkedin}

With this context, please evaluate the latest response, replying with whether the response is acceptable and your feedback."""

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "record_user_details",
                    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "description": "The email address of this user"},
                            "name": {"type": "string", "description": "The user's name, if they provided it"},
                            "notes": {"type": "string", "description": "Any additional information about the conversation that's worth recording to give context"}
                        },
                        "required": ["email"],
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "record_unknown_question",
                    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "The question that couldn't be answered"}
                        },
                        "required": ["question"],
                        "additionalProperties": False
                    }
                }
            }
        ]

    def evaluate(self, reply: str, message: str, history: List[Dict]) -> Evaluation:
        user_prompt = f"""Here's the conversation between the User and the Agent:

{history}

Here's the latest message from the User:

{message}

Here's the latest response from the Agent:

{reply}

Please evaluate the response, replying with whether it is acceptable and your feedback."""
        
        messages = [
            {"role": "system", "content": self.evaluator_system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            response = gemini_client.beta.chat.completions.parse(
                model="gemini-2.0-flash", 
                messages=messages, 
                response_format=Evaluation
            )
            return response.choices[0].message.parsed
        except Exception as e:
            print(f"Evaluation error: {e}")
            return Evaluation(is_acceptable=True, feedback="Evaluation failed, accepting response")

    def rerun(self, reply: str, message: str, history: List[Dict], feedback: str) -> str:
        updated_system_prompt = self.system_prompt + "\n\n## Previous answer rejected\nYou just tried to reply, but the quality control rejected your reply\n"
        updated_system_prompt += f"## Your attempted answer:\n{reply}\n\n"
        updated_system_prompt += f"## Reason for rejection:\n{feedback}\n\n"
        
        messages = [{"role": "system", "content": updated_system_prompt}] + history + [{"role": "user", "content": message}]
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=self.tools
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Rerun error: {e}")
            return reply

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
            
            # Evaluate response with Gemini
            evaluation = self.evaluate(assistant_message, message, conversations[session_id][1:-1])  # Exclude system prompt and current user message
            
            if evaluation.is_acceptable:
                print("Passed evaluation - returning reply")
                conversations[session_id].append({"role": "assistant", "content": assistant_message})
                return assistant_message
            else:
                print("Failed evaluation - retrying")
                print(f"Feedback: {evaluation.feedback}")
                # Rerun with feedback
                improved_response = self.rerun(assistant_message, message, conversations[session_id][1:-1], evaluation.feedback)
                conversations[session_id].append({"role": "assistant", "content": improved_response})
                return improved_response
            
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