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

def ask_nova(prompt: str, max_tokens: int = 1000):
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
- issue: what the customer problem was (specific, detailed)
- root_cause: what was actually causing it
- resolution: exactly how it was fixed step by step
- internal_steps: what the agent did internally to fix it which tools which settings
- category: email / domain / network / account / billing / hosting / database / general
- was_escalated: true or false
- escalation_reason: why it was escalated or null if not escalated
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

For each product return a JSON array with objects containing:
- name: product name
- description: what the product does
- price: pricing information
- discount: any discounts or offers use None if not mentioned
- best_for: what type of customer or problem this product is best for

Return ONLY valid JSON array. No markdown, no backticks, no explanation.

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
    except Exception:
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

@app.post("/upload-tools")
async def upload_tools(files: List[UploadFile] = File(...)):
    total_count = 0
    tool_names = []

    for file in files:
        content = await file.read()
        text = content.decode("utf-8")

        embedding = get_embedding(text[:8000])

        supabase.table("tools").insert({
            "filename": file.filename,
            "raw_content": text,
            "embedding": embedding
        }).execute()

        total_count += 1
        tool_names.append(file.filename)

    return {
        "message": f"{total_count} tool(s) uploaded successfully",
        "tools": tool_names
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

    tools_result = supabase.rpc("match_tools", {
        "query_embedding": query_embedding,
        "match_count": 2
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

    tools_context = ""
    if tools_result.data:
        for t in tools_result.data:
            tools_context += f"\n--- Tool: {t['filename']} ---\n{t['raw_content']}\n"

    pitch_section = ""
    if product_context:
        pitch_section = f"""
AVAILABLE PRODUCTS FOR PITCH:
{product_context}"""

    tools_section = ""
    if tools_context:
        tools_section = f"""
=== INTERNAL TOOLS AVAILABLE ===
{tools_context}"""

    prompt = f"""You are an expert customer support co-pilot for a company providing network solutions, email hosting, domain management, and account services.

You are helping a live support agent handle a customer chat in real time.

The agent's KPIs are:
- FCR (First Contact Resolution): Resolve in ONE interaction — always push toward this
- AHT: Target is 1350 seconds (22.5 minutes) — help agent be fast and efficient  
- CSAT: 5 star customer satisfaction — guide tone and resolution quality
- Sales: Pitch relevant products customer does NOT already own, or renew expiring domains/services
- Escalation accuracy: Only escalate when truly necessary — wrong escalation kills KPI

=== FULL CONVERSATION SO FAR ===
{history if history else "This is the first customer message."}

{"=== AGENT INTERNAL NOTE ===" if is_internal_note else "=== LATEST CUSTOMER MESSAGE ==="}
{latest_message.replace("//", "").strip()}
{"[Agent internal note — skip REPLY TO CUSTOMER section. Answer agent question directly using conversation context and KB.]" if is_internal_note else ""}

=== SIMILAR PAST CASES FROM KNOWLEDGE BASE ===
{kb_context if kb_context else "NO SIMILAR CASES FOUND IN KB."}

{tools_section}

{pitch_section}

=== YOUR RESPONSE FORMAT ===

REPLY TO CUSTOMER (copy-paste directly):
[Short 1-2 line professional reply following EAR — Empathy + Acknowledgment + Reassurance.
- If customer is frustrated or angry: use calm warm de-escalation language. Acknowledge their specific frustration. Never be defensive.
- If customer is calm: be warm professional action-oriented
- Never say "That's frustrating" / "Oh no" / "I sincerely apologize" / "I understand your concern"
- Never apologize unless issue is clearly your company's fault
- Personalize to exactly what they said — mention their specific issue and situation
- Max 2 lines. End with a positive action statement showing you are on it.]

TONE & URGENCY:
Emotion: [Angry / Frustrated / Calm / Confused]
Urgency: [High / Medium / Low — based on business impact]
AHT: [Simple / Moderate / Complex — warn if this may exceed 22.5 min target]

SITUATION SO FAR:
[1-2 lines — exact summary of what we know from full conversation]

LIKELY ISSUE:
[Specific root cause — reference KB past case if available. Never generic.]

WHAT TO DO INTERNALLY:
[Step by step exact navigation using internal tools if available:
- Which tool to open
- Exact path to get there
- What to look for
- What to change or check
- Reference KB internal steps if similar case found]

FCR GUIDANCE:
[What you still need to gather or verify to close this in ONE interaction.
What to confirm before closing. Push agent toward FCR.]

NEXT PROBE TO ASK CUSTOMER:
[ONE specific question not yet answered — or "Enough info — proceed to resolution now" if ready to close]

ESCALATION SIGNAL:
[Based on KB patterns and issue type:
- Abuse issue → Create Abuse Case
- Fraud suspicion → Create Fraud Case
- Billing dispute beyond agent authority → Create Billing Case
- Customer threatening to leave → Create Retention Case
- Technical issue beyond agent tool access → Technical Escalation
- If KB shows similar cases were escalated: state reason
- If KB shows agent resolved similar cases: "Handle yourself at agent level"
- If unclear: "Attempt resolution first — escalate only if tools insufficient"]

PITCH OPPORTUNITY:
[Assess based on conversation:
- Only pitch what customer likely does NOT already own
- If domain or service expiry mentioned: suggest renewal
- If issue caused by missing product: suggest it as solution
- Suggest ONE product with price and discount
- Frame as helpful not pushy — "This would prevent this issue in future"
- If nothing fits naturally: "No pitch opportunity this interaction"]

CLOSING MESSAGE (copy-paste after resolution):
[Warm short professional closing. Thank them by situation. Confirm what was resolved. Invite them to reach out anytime. Naturally encourage feedback without directly asking for rating.]

=== STRICT RULES ===
- Never ask about something customer already told you in this conversation
- Every response must move conversation forward toward FCR
- If KB case found: use its exact resolution steps and internal steps
- If no KB case: help based on conversation and tools context
- Be specific — no generic advice ever
- Frustrated customer: de-escalate first then resolve
- Always assess pitch opportunity even if answer is no pitch
- Always push toward resolving in this single interaction
- REPLY TO CUSTOMER is always the first section — agent copies and pastes this immediately"""

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