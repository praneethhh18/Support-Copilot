from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client
import boto3
import json
import os
import uuid

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

def get_embedding(text: str):
    body = json.dumps({"inputText": text})
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=body,
        contentType="application/json",
        accept="application/json"
    )
    result = json.loads(response["body"].read())
    return result["embedding"]

def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i+chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks

def scrub_pii(text: str):
    import re
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
    text = re.sub(r'\b\d{10}\b', '[PHONE]', text)
    text = re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]', text)
    return text

def auto_detect_category(text: str):
    preview = " ".join(text.split()[:200])
    prompt = f"""Read this customer support transcript and reply with ONLY one word from this list:
email, network, domain, account, general

Transcript:
{preview}

Reply with only one word, nothing else."""

    response = bedrock.converse(
        modelId="us.amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 10}
    )
    category = response["output"]["message"]["content"][0]["text"].strip().lower()
    valid = ["email", "network", "domain", "account", "general"]
    return category if category in valid else "general"

def auto_detect_status(text: str):
    lower = text.lower()
    if any(word in lower for word in ["resolution:", "resolved", "fixed", "working now", "thank you", "issue solved"]):
        return "solved"
    return "unsolved"

def ask_nova(prompt: str, max_tokens: int = 600):
    response = bedrock.converse(
        modelId="us.amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens}
    )
    return response["output"]["message"]["content"][0]["text"]

def parse_product_file(text: str):
    products = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        product = {}
        for line in block.strip().split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().upper()
                value = value.strip()
                if key == "PRODUCT":
                    product["name"] = value
                elif key == "DESCRIPTION":
                    product["description"] = value
                elif key == "PRICE":
                    product["price"] = value
                elif key == "DISCOUNT":
                    product["discount"] = value
                elif key == "BEST FOR":
                    product["best_for"] = value
        if "name" in product:
            products.append(product)
    return products

@app.get("/")
def root():
    return {"status": "Support Copilot API is running"}

@app.get("/test-bedrock")
def test_bedrock():
    response = bedrock.converse(
        modelId="us.amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": "Say hello in one sentence."}]}],
        inferenceConfig={"maxTokens": 100}
    )
    result = response["output"]["message"]["content"][0]["text"]
    return {"response": result}

@app.post("/upload-transcript")
async def upload_transcript(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8")
    text = scrub_pii(text)

    category = auto_detect_category(text)
    status = auto_detect_status(text)

    transcript_id = str(uuid.uuid4())
    supabase.table("transcripts").insert({
        "id": transcript_id,
        "filename": file.filename,
        "content": text,
        "category": category,
        "status": status
    }).execute()

    chunks = chunk_text(text)
    for chunk in chunks:
        embedding = get_embedding(chunk)
        supabase.table("chunks").insert({
            "transcript_id": transcript_id,
            "content": chunk,
            "embedding": embedding
        }).execute()

    return {
        "message": "Transcript uploaded successfully",
        "transcript_id": transcript_id,
        "category": category,
        "status": status,
        "chunks_created": len(chunks)
    }

@app.post("/upload-products")
async def upload_products(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8")

    products = parse_product_file(text)

    if not products:
        return {"error": "No products found. Check file format."}

    count = 0
    for product in products:
        embed_text = f"{product.get('name','')} {product.get('description','')} {product.get('best_for','')}"
        embedding = get_embedding(embed_text)
        supabase.table("products").insert({
            "name": product.get("name", ""),
            "description": product.get("description", ""),
            "price": product.get("price", ""),
            "discount": product.get("discount", ""),
            "best_for": product.get("best_for", ""),
            "embedding": embedding
        }).execute()
        count += 1

    return {
        "message": f"{count} products uploaded successfully",
        "products": [p["name"] for p in products]
    }

@app.post("/search")
async def search(payload: dict):
    customer_message = payload.get("message", "")

    if not customer_message:
        return {"error": "No message provided"}

    query_embedding = get_embedding(customer_message)

    result = supabase.rpc("match_chunks", {
        "query_embedding": query_embedding,
        "match_count": 5
    }).execute()

    product_result = supabase.rpc("match_products", {
        "query_embedding": query_embedding,
        "match_count": 3
    }).execute()

    if not result.data:
        return {
            "nova_response": "No similar cases found. Please escalate.",
            "sources": [],
            "chunks_found": 0
        }

    context = ""
    sources = []
    for i, chunk in enumerate(result.data):
        context += f"\nCase {i+1}:\n{chunk['content']}\n"
        sources.append(chunk.get("transcript_id", "unknown"))

    product_context = ""
    if product_result.data:
        for p in product_result.data:
            product_context += f"\n- {p['name']}: {p['description']} | Price: {p['price']} | Discount: {p['discount']} | Best for: {p['best_for']}\n"

    pitch_section = ""
    if product_context:
        pitch_section = f"""
RELEVANT PRODUCTS TO PITCH:
{product_context}
4. PITCH OPPORTUNITY - Suggest only if genuinely relevant."""

    prompt = f"""You are an expert customer support assistant for a company providing network solutions, email, domain, and account management services.

A customer has sent this message:
\"\"\"{customer_message}\"\"\"

Based ONLY on the following similar past support cases, help the support agent by identifying:
1. LIKELY ISSUE - What is probably wrong
2. PROBE QUESTIONS - What to ask the customer next (3 questions max)
3. RESOLUTION PATH - Steps to resolve based on past cases
{pitch_section}

Similar past cases:
{context}

IMPORTANT: Only use information from the past cases above. If nothing is relevant say "No similar case found, please escalate." Do not make up information. Be concise and practical."""

    nova_response = ask_nova(prompt)

    return {
        "nova_response": nova_response,
        "sources": sources,
        "chunks_found": len(result.data)
    }

@app.post("/chat")
async def chat(payload: dict):
    messages = payload.get("messages", [])

    if not messages:
        return {"error": "No messages provided"}

    latest_message = messages[-1]["content"]

    query_embedding = get_embedding(latest_message)

    result = supabase.rpc("match_chunks", {
        "query_embedding": query_embedding,
        "match_count": 5
    }).execute()

    product_result = supabase.rpc("match_products", {
        "query_embedding": query_embedding,
        "match_count": 3
    }).execute()

    context = ""
    sources = []
    if result.data:
        for i, chunk in enumerate(result.data):
            context += f"\nCase {i+1}:\n{chunk['content']}\n"
            sources.append(chunk.get("transcript_id", "unknown"))

    product_context = ""
    if product_result.data:
        for p in product_result.data:
            product_context += f"\n- {p['name']}: {p['description']} | Price: {p['price']} | Discount: {p['discount']} | Best for: {p['best_for']}\n"

    history = ""
    for msg in messages[:-1]:
        role = "Support Agent" if msg["role"] == "agent" else "Customer"
        history += f"{role}: {msg['content']}\n"

    pitch_section = ""
    if product_context:
        pitch_section = f"""
RELEVANT PRODUCTS TO PITCH:
{product_context}
4. PITCH OPPORTUNITY - Suggest only if genuinely relevant."""

    prompt = f"""You are an expert customer support assistant for a company providing network solutions, email, domain, and account management services.

CONVERSATION SO FAR:
{history}

LATEST CUSTOMER MESSAGE:
\"\"\"{latest_message}\"\"\"

Based ONLY on similar past support cases below, help the support agent:
1. LIKELY ISSUE - What is probably wrong based on full conversation context
2. PROBE QUESTIONS - What to ask next (max 3, don't repeat already asked questions)
3. RESOLUTION PATH - Steps to resolve based on past cases
{pitch_section}

Similar past cases:
{context if context else "No similar cases found in KB."}

STRICT RULE: If no similar cases are provided above, you MUST respond with exactly:
"No similar case in knowledge base. Please probe manually:
- What exactly is the issue?
- When did it start?
- Any recent changes made?"

Do NOT answer from general knowledge. Only use provided cases."""

    nova_response = ask_nova(prompt)

    return {
        "nova_response": nova_response,
        "sources": sources,
        "chunks_found": len(result.data) if result.data else 0
    }
@app.get("/notes")
async def get_notes():
    result = supabase.table("notes").select("*").limit(1).execute()
    if result.data:
        return {"content": result.data[0]["content"], "id": result.data[0]["id"]}
    return {"content": "", "id": None}

@app.post("/notes")
async def save_notes(payload: dict):
    content = payload.get("content", "")
    note_id = payload.get("id", None)
    
    if note_id:
        supabase.table("notes").update({
            "content": content,
            "updated_at": "now()"
        }).eq("id", note_id).execute()
    else:
        supabase.table("notes").insert({"content": content}).execute()
    
    return {"status": "saved"}

    