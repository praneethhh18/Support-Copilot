from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client
import boto3
import json
import os
import uuid
from typing import List

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
    if any(word in lower for word in ["resolution:", "resolved", "fixed", "working now", "thank you", "issue solved", "resolved in one"]):
        return "solved"
    return "unsolved"

def ask_nova(prompt: str, max_tokens: int = 800):
    response = bedrock.converse(
        modelId="us.amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens}
    )
    return response["output"]["message"]["content"][0]["text"]

def extract_issues_from_transcript(text: str):
    prompt = f"""You are a support knowledge base builder. Read this customer support chat transcript carefully.

Extract ALL distinct issues discussed in this conversation. For each issue create a structured summary.

Return a JSON array only — no markdown, no backticks, no explanation.

Each object must have:
- issue: what the customer's problem was (specific, detailed)
- root_cause: what was actually causing it
- resolution: exactly how it was fixed (step by step if possible)
- internal_steps: what the agent did internally to fix it (which tools, which settings)
- category: email / domain / network / account / billing / hosting / database / general
- was_escalated: true or false
- escalation_reason: why it was escalated (or null if not escalated)
- keywords: list of 5-10 search keywords for this issue

Transcript:
{text[:6000]}

Return ONLY valid JSON array. Nothing else."""

    response = bedrock.converse(
        modelId="us.amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2000}
    )

    raw = response["output"]["message"]["content"][0]["text"].strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    issues = json.loads(raw)
    return issues

def format_issue_as_chunk(issue: dict) -> str:
    return f"""ISSUE: {issue.get('issue', '')}
ROOT CAUSE: {issue.get('root_cause', '')}
RESOLUTION: {issue.get('resolution', '')}
INTERNAL STEPS: {issue.get('internal_steps', '')}
CATEGORY: {issue.get('category', '')}
ESCALATED: {issue.get('was_escalated', False)}
ESCALATION REASON: {issue.get('escalation_reason', 'N/A')}
KEYWORDS: {', '.join(issue.get('keywords', []))}"""

def ai_parse_products(text: str):
    prompt = f"""You are a product data extractor. Read the following messy product information and extract all products from it.

For each product you find, return a JSON array with objects containing these exact keys:
- name: product name
- description: what the product does
- price: pricing information
- discount: any discounts or offers (use "None" if not mentioned)
- best_for: what type of customer or problem this product is best for

Return ONLY a valid JSON array, nothing else. No markdown, no backticks, no explanation.

Product information:
{text}"""

    response = bedrock.converse(
        modelId="us.amazon.nova-pro-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2000}
    )

    raw = response["output"]["message"]["content"][0]["text"].strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    products = json.loads(raw)
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

    # Smart chunking — extract structured issues instead of raw word chunks
    try:
        issues = extract_issues_from_transcript(text)
        chunks_created = 0
        for issue in issues:
            chunk_text = format_issue_as_chunk(issue)
            embedding = get_embedding(chunk_text)
            supabase.table("chunks").insert({
                "transcript_id": transcript_id,
                "content": chunk_text,
                "embedding": embedding
            }).execute()
            chunks_created += 1
    except Exception as e:
        # Fallback to basic chunking if extraction fails
        words = text.split()
        chunks_created = 0
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i+300])
            embedding = get_embedding(chunk)
            supabase.table("chunks").insert({
                "transcript_id": transcript_id,
                "content": chunk,
                "embedding": embedding
            }).execute()
            chunks_created += 1
            i += 250

    return {
        "message": "Transcript uploaded successfully",
        "transcript_id": transcript_id,
        "category": category,
        "status": status,
        "chunks_created": chunks_created
    }

@app.post("/upload-products")
async def upload_products(files: List[UploadFile] = File(...)):
    all_products = []
    total_count = 0

    for file in files:
        content = await file.read()
        text = content.decode("utf-8")

        try:
            products = ai_parse_products(text)
        except Exception as e:
            return {"error": f"Failed to parse {file.filename}: {str(e)}"}

        for product in products:
            try:
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
                all_products.append(product.get("name", ""))
                total_count += 1
            except Exception:
                continue

    return {
        "message": f"{total_count} products uploaded from {len(files)} file(s)",
        "products": all_products
    }

@app.post("/chat")
async def chat(payload: dict):
    messages = payload.get("messages", [])

    if not messages:
        return {"error": "No messages provided"}

    history = ""
    all_customer_info = []
    for msg in messages[:-1]:
        if msg["role"] == "customer":
            history += f"Customer: {msg['content']}\n"
            all_customer_info.append(msg['content'])
        else:
            history += f"Agent Co-Pilot: {msg['content']}\n"

    latest_message = messages[-1]["content"]
    is_internal_note = latest_message.startswith("//")

    if not is_internal_note:
        all_customer_info.append(latest_message)

    full_context_query = " ".join(all_customer_info)
    query_embedding = get_embedding(full_context_query)

    result = supabase.rpc("match_chunks", {
        "query_embedding": query_embedding,
        "match_count": 5
    }).execute()

    product_result = supabase.rpc("match_products", {
        "query_embedding": query_embedding,
        "match_count": 3
    }).execute()

    kb_context = ""
    sources = []
    if result.data:
        for i, chunk in enumerate(result.data):
            kb_context += f"\n--- Past Case {i+1} ---\n{chunk['content']}\n"
            sources.append(chunk.get("transcript_id", "unknown"))

    product_context = ""
    if product_result.data:
        for p in product_result.data:
            product_context += f"\n- {p['name']}: {p['description']} | Price: {p['price']} | Discount: {p['discount']} | Best for: {p['best_for']}\n"

    pitch_section = ""
    if product_context:
        pitch_section = f"""
RELEVANT PRODUCTS (suggest only if genuinely fits customer problem):
{product_context}"""

    prompt = f"""You are an expert customer support assistant for a company providing network solutions, email hosting, domain management, and account services.

Your job is to help the support agent handle this live customer chat. Read everything carefully before responding.

=== FULL CONVERSATION SO FAR ===
{history if history else "This is the first customer message."}

{"=== YOUR INTERNAL NOTE ===" if is_internal_note else "=== LATEST CUSTOMER MESSAGE ==="}
{latest_message.replace("//", "").strip()}
{"[This is an internal note from the agent — do NOT generate REPLY TO CUSTOMER. Just answer the agent question directly based on conversation and KB.]" if is_internal_note else ""}

=== SIMILAR PAST CASES FROM KNOWLEDGE BASE ===
{kb_context if kb_context else "NO SIMILAR CASES FOUND IN KB."}
{pitch_section}

=== YOUR RESPONSE RULES ===
1. Read the ENTIRE conversation history first
2. Note everything the customer has ALREADY told you — never ask about it again
3. Use past cases from KB as reference — if KB has relevant cases, base your answer on them
4. If KB has NO relevant cases, help based on conversation context only

=== YOUR RESPONSE FORMAT ===

REPLY TO CUSTOMER (copy-paste this directly):
[Write a short 1-2 line professional reply personalized to exactly what this customer said.
Follow EAR — Empathy + Acknowledgment + Reassurance.
- Empathy: show you understand their specific situation
- Acknowledgment: reference exactly what they told you (their product, their issue)
- Reassurance: assure them you are on it right now
Rules for the reply:
- Never start with "That's really frustrating" or "Oh no" or "I sincerely apologize"
- Never apologize unless the issue is clearly on your company's side
- Never use generic phrases like "I understand your concern"
- Be warm, professional, personalized, short — max 2 lines
- End with positive energy showing you are taking action
- Personalize to their exact situation — mention what they specifically said]

TONE & URGENCY:
[Detect customer emotional state: Angry / Frustrated / Calm / Confused]
[Urgency: High / Medium / Low — based on business impact]

SITUATION SO FAR:
[Summarize what we know from full conversation in 1-2 lines]

LIKELY ISSUE:
[Most probable cause based on ALL information gathered — be specific, not generic]

WHAT TO DO INTERNALLY:
[Exact steps to check or fix on your end — reference specific tools and settings from past cases if available]

NEXT PROBE TO ASK CUSTOMER:
[ONE specific question not yet answered — or say "Enough info, proceed with resolution" if you have everything]

ESCALATION SIGNAL:
[Based on similar past cases in KB:
- If past cases show this was escalated: warn with reason why and when to escalate
- If past cases show agent resolved it: say "Handle yourself — similar cases resolved at agent level"
- If no past cases found: say "No escalation pattern found — use your judgment"]

CLOSING MESSAGE (copy-paste after resolution):
[Short warm professional closing — invite feedback naturally without directly asking for rating]

{"PITCH: [Suggest relevant product only if it directly solves their problem — include price and discount]" if product_context else ""}

=== STRICT RULES ===
- If customer already mentioned their email client — do NOT ask again
- If customer mentioned when issue started — do NOT ask again
- Each response must MOVE THE CONVERSATION FORWARD
- If KB cases found: reference them explicitly in resolution
- If NO KB cases: say "No matching case in KB" but still help
- Never give generic advice — be specific to what this customer told you
- If issue resolved: say "Issue resolved: [what fixed it]"
- REPLY TO CUSTOMER must always be first section"""

    nova_response = ask_nova(prompt)

    return {
        "nova_response": nova_response,
        "sources": sources,
        "chunks_found": len(result.data) if result.data else 0
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

    prompt = f"""You are an expert customer support assistant for a company providing network solutions, email, domain, and account management services.

Customer message: \"\"\"{customer_message}\"\"\"

Past cases from KB:
{context}

{"Products: " + product_context if product_context else ""}

Help the agent with:
1. LIKELY ISSUE
2. PROBE QUESTIONS (max 3)
3. RESOLUTION PATH
{"4. PITCH OPPORTUNITY" if product_context else ""}

Only use KB cases above. If nothing relevant say "No similar case found, please escalate." """

    nova_response = ask_nova(prompt)

    return {
        "nova_response": nova_response,
        "sources": sources,
        "chunks_found": len(result.data)
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