import streamlit as st
from openai import OpenAI
import requests
import time
import uuid
import json
from supabase import create_client

# ==============================================================================
# PAGE CONFIG & SECRETS
# ==============================================================================
st.set_page_config(page_title="TEAMUPAI - AI App Builder", layout="wide", page_icon="🚀")

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    OPENROUTER_KEY = st.secrets["OPENROUTER_API_KEY"]  # Server-side key
    E2B_API_KEY = st.secrets.get("E2B_API_KEY", "")     # Optional sandbox
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except KeyError as e:
    st.error(f"⚠️ Missing secret: {e}. Add it in Streamlit Settings → Secrets.")
    st.stop()

# ==============================================================================
# SUPABASE AUTH & DB FUNCTIONS (Same as before + project table)
# ==============================================================================
def login_with_email(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return res.user
    except Exception as e:
        st.error(f"Login Error: {e}")
        return None

def register_with_email(email, password):
    try:
        res = supabase.auth.sign_up({"email": email, "password": password})
        st.success("✅ Account created! Please verify your email.")
        return res.user
    except Exception as e:
        st.error(f"Registration Error: {e}")
        return None

def save_chat_to_db(user_email, session_id, role, content, msg_type):
    try:
        supabase.table("chat_history").insert({
            "user_email": user_email,
            "session_id": session_id,
            "role": role,
            "content": content,
            "msg_type": msg_type
        }).execute()
    except Exception as e:
        print(f"DB Save Error: {e}")

def load_user_sessions(user_email):
    try:
        res = supabase.table("chat_history") \
            .select("session_id, created_at") \
            .eq("user_email", user_email) \
            .order("created_at", desc=True) \
            .execute()
        seen = set()
        sessions = []
        for row in res.data:
            sid = row["session_id"]
            if sid not in seen:
                seen.add(sid)
                sessions.append(sid)
        return sessions
    except Exception:
        return []

def load_chat_by_session(session_id):
    try:
        res = supabase.table("chat_history") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("created_at") \
            .execute()
        return res.data
    except Exception:
        return []

def save_project_code(session_id, code, language="html"):
    """Save generated code to Supabase for preview/deployment"""
    try:
        supabase.table("projects").upsert({
            "session_id": session_id,
            "code": code,
            "language": language,
            "updated_at": "now()"
        }, on_conflict="session_id").execute()
    except Exception as e:
        print(f"Project save error: {e}")

def load_project_code(session_id):
    try:
        res = supabase.table("projects") \
            .select("code, language") \
            .eq("session_id", session_id) \
            .single() \
            .execute()
        if res.data:
            return res.data["code"], res.data["language"]
    except Exception:
        pass
    return None, None

def save_anonymous_feedback(text):
    try:
        supabase.table("feedbacks").insert({"feedback_text": text}).execute()
        st.sidebar.success("🙏 Thank you for your feedback!")
    except Exception as e:
        st.sidebar.error(f"Feedback error: {e}")

# ==============================================================================
# DARK THEME STYLING
# ==============================================================================
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d !important; color: #ffffff !important; }
    [data-testid="stSidebar"] { background-color: #1a1a1a !important; color: #ffffff !important; }
    [data-testid="stChatInput"] textarea {
        background-color: #21262d !important; color: #ffffff !important;
        font-size: 16px !important; -webkit-text-fill-color: #ffffff !important;
    }
    [data-testid="stChatInput"] textarea::placeholder {
        color: #8b949e !important; -webkit-text-fill-color: #8b949e !important;
    }
    .stTextInput input, .stTextArea textarea {
        background-color: #262626 !important; color: #ffffff !important;
        border: 1px solid #404040 !important;
    }
    .chat-card { padding: 15px; border-radius: 10px; margin-bottom: 12px; color: #fff; line-height: 1.6; }
    .chat-user { background-color: #21262d; border-left: 5px solid #8b949e; }
    .chat-pm { background-color: #1a2332; border-left: 5px solid #58a6ff; }
    .chat-architect { background-color: #2d1f33; border-left: 5px solid #bc8cff; }
    .chat-coder { background-color: #1c2d1f; border-left: 5px solid #3fb950; }
    .chat-qa { background-color: #332b1a; border-left: 5px solid #d29922; }
    .chat-judge { 
        background: linear-gradient(135deg, #113b19, #1a4a25); 
        border-left: 5px solid #2ea043; border-radius: 12px; 
        padding: 20px; margin: 15px 0; 
    }
    .preview-container {
        border: 1px solid #30363d; border-radius: 12px; overflow: hidden;
        margin-top: 15px; background: #ffffff;
    }
    .preview-header {
        background: #21262d; padding: 10px 15px; font-weight: bold;
        display: flex; justify-content: space-between; align-items: center;
    }
    .status-badge {
        padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold;
    }
    .status-building { background: #d29922; color: #000; }
    .status-ready { background: #2ea043; color: #fff; }
    .agent-label { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.7; margin-bottom: 5px; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# SYSTEM PROMPTS FOR APP BUILDER WORKFLOW
# ==============================================================================
SYSTEM_PROMPTS = {
    "pm": """You are a Senior Product Manager at TEAMUPAI.
Your job: Convert the user's idea into a clear, actionable PRD.
- Ask clarifying questions if the idea is vague
- Define MVP scope strictly (no feature creep)
- Output a structured markdown PRD with: Overview, User Stories, Tech Requirements, MVP Boundaries
- Be concise and practical. This PRD will be used by architects and coders.""",

    "architect": """You are a Senior Software Architect at TEAMUPAI.
Review the PM's PRD and design the technical architecture.
- Choose the simplest tech stack that works (prefer single-file HTML/CSS/JS for MVPs)
- Identify potential issues or missing requirements
- Output: Tech Stack Decision, File Structure, Key Implementation Notes, Risk Assessment
- If the PM's PRD is unclear, say so explicitly.""",

    "coder": """You are an Expert Full-Stack Developer at TEAMUPAI.
Based on the approved architecture, write COMPLETE, RUNNABLE code.
CRITICAL RULES:
- Output ONLY code inside ```html or ```python code blocks
- For web apps: Single HTML file with embedded CSS + JS (no build tools needed)
- Include all functionality described in the PRD
- Add comments explaining complex logic
- Make it visually polished (modern CSS, responsive)
- The code MUST run immediately when opened in a browser
- Do NOT output explanations outside code blocks""",

    "qa": """You are a QA Engineer at TEAMUPAI.
Review the generated code against the original PRD.
Check for: Missing features, UI/UX issues, JavaScript errors, accessibility problems, mobile responsiveness.
Output a brief test report: ✅ Passed items, ❌ Failed items, 🔧 Suggested fixes.
If critical issues exist, say "REBUILD NEEDED" and list exact problems.""",

    "judge": """You are the Tech Lead & Final Decision Maker at TEAMUPAI.
Synthesize ALL agent outputs into a final deliverable.
- If QA found critical issues → Request specific fixes from Coder
- If everything passes → Confirm the app is ready
- Provide a 2-sentence summary of what was built
- Always end with: STATUS: READY or STATUS: NEEDS_REVISION"""
}

# ==============================================================================
# SESSION STATE INITIALIZATION
# ==============================================================================
if "user" not in st.session_state:
    st.session_state.user = None
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "generated_code" not in st.session_state:
    st.session_state.generated_code = None
if "code_language" not in st.session_state:
    st.session_state.code_language = "html"
if "build_status" not in st.session_state:
    st.session_state.build_status = None

# ==============================================================================
# SPLASH SCREEN
# ==============================================================================
if "splash_done" not in st.session_state:
    splash = st.empty()
    with splash.container():
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            try:
                st.image("logo.png", width=220)
            except Exception:
                st.markdown("<h1 style='text-align:center'>🚀</h1>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align:center; color:white;'>TEAMUPAI 1.0</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align:center; color:#8b949e;'>Multi-Agent AI App Builder</p>", unsafe_allow_html=True)
            st.progress(100)
    time.sleep(2.5)
    st.session_state.splash_done = True
    splash.empty()

# ==============================================================================
# OPENROUTER CLIENT (Server-Side Key)
# ==============================================================================
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_KEY,
    default_headers={
        "HTTP-Referer": "https://teamupai.streamlit.app",
        "X-Title": "TEAMUPAI App Builder",
    }
)

MODELS = {
    "pm": "google/gemini-2.0-flash-lite-001:free",
    "architect": "meta-llama/llama-3.3-70b-instruct:free",
    "coder": "qwen/qwen-2.5-coder-32b-instruct:free",
    "qa": "google/gemini-2.0-flash-lite-001:free",
    "judge": "meta-llama/llama-3.3-70b-instruct:free",
}

def call_model(agent_role, prompt, fallback_model=None):
    model_id = MODELS.get(agent_role, MODELS["judge"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPTS[agent_role]},
        {"role": "user", "content": prompt}
    ]
    try:
        resp = client.chat.completions.create(model=model_id, messages=messages)
        return resp.choices[0].message.content
    except Exception as e:
        st.warning(f"⚠️ {agent_role.upper()} failed: {e}. Retrying...")
        time.sleep(1)
        fb = fallback_model or "google/gemini-2.0-flash-lite-001:free"
        try:
            resp = client.chat.completions.create(model=fb, messages=messages)
            return resp.choices[0].message.content
        except Exception as e2:
            return f"❌ Error: {str(e2)}"

def extract_code_block(text):
    """Extract code from markdown code blocks"""
    import re
    patterns = [r'```html\s*\n(.*?)```', r'```python\s*\n(.*?)```', r'```\s*\n(.*?)```']
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            code = match.group(1).strip()
            lang = "html" if "html" in pattern else "python"
            return code, lang
    return None, None

def run_app_builder_pipeline(user_query, session_id, user_email):
    """Full multi-agent app building pipeline"""
    st.session_state.build_status = "building"
    
    # Save user message
    st.session_state.messages.append({"role": "User", "content": user_query, "type": "user"})
    save_chat_to_db(user_email, session_id, "User", user_query, "user")
    
    history = "\n\n".join([f"[{m['role']}]: {m['content']}" for m in st.session_state.messages[:-1]])
    context = f"CONVERSATION HISTORY:\n{history}\n\nUSER REQUEST: {user_query}" if history else f"USER REQUEST: {user_query}"

    agents = ["pm", "architect", "coder", "qa", "judge"]
    agent_labels = {"pm": "📋 PM", "architect": "🏗️ Architect", "coder": "💻 Coder", "qa": "🧪 QA", "judge": "⚖️ Judge"}
    agent_types = {"pm": "pm", "architect": "architect", "coder": "coder", "qa": "qa", "judge": "judge"}
    
    responses = {}
    
    for agent in agents:
        label = agent_labels[agent]
        with st.spinner(f"{label} working..."):
            if agent == "architect":
                prompt = f"{context}\n\nPM OUTPUT:\n{responses.get('pm', 'N/A')}"
            elif agent == "coder":
                prompt = f"{context}\n\nPM OUTPUT:\n{responses.get('pm', '')}\n\nARCHITECT OUTPUT:\n{responses.get('architect', '')}"
            elif agent == "qa":
                prompt = f"{context}\n\nPM OUTPUT:\n{responses.get('pm', '')}\n\nGENERATED CODE:\n{responses.get('coder', '')}"
            elif agent == "judge":
                prompt = f"{context}\n\nPM: {responses.get('pm','')}\nARCHITECT: {responses.get('architect','')}\nCODER: {responses.get('coder','')}\nQA: {responses.get('qa','')}"
            else:
                prompt = context
            
            result = call_model(agent, prompt)
            responses[agent] = result
            
            st.session_state.messages.append({
                "role": agent_labels[agent],
                "content": result,
                "type": agent_types[agent]
            })
            save_chat_to_db(user_email, session_id, agent_labels[agent], result, agent_types[agent])
            
            # Extract code from coder output
            if agent == "coder":
                code, lang = extract_code_block(result)
                if code:
                    st.session_state.generated_code = code
                    st.session_state.code_language = lang
                    save_project_code(session_id, code, lang)
    
    st.session_state.build_status = "ready"
    return responses

# ==============================================================================
# 🔒 LOGIN / REGISTER SCREEN
# ==============================================================================
if st.session_state.user is None:
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        try:
            st.image("logo.png", width=100)
        except Exception:
            st.markdown("<h1 style='text-align:center'>🚀</h1>", unsafe_allow_html=True)
        st.title("🔐 Login to TEAMUPAI")
        st.caption("Describe your app idea. Our AI team builds it for you.")
        
        tab1, tab2 = st.tabs(["🔑 Sign In", "📝 Sign Up"])
        with tab1:
            email = st.text_input("Email", key="login_email")
            pwd = st.text_input("Password", type="password", key="login_pass")
            if st.button("Sign In", type="primary", use_container_width=True):
                if email and pwd:
                    user = login_with_email(email, pwd)
                    if user:
                        st.session_state.user = {"email": user.email}
                        st.session_state.current_session_id = str(uuid.uuid4())
                        st.session_state.messages = []
                        st.session_state.generated_code = None
                        st.rerun()
                else:
                    st.error("Please enter Email & Password!")
        with tab2:
            ne = st.text_input("Email", key="reg_email")
            np_ = st.text_input("Password", type="password", key="reg_pass")
            if st.button("Create Account", use_container_width=True):
                if ne and np_:
                    register_with_email(ne, np_)
                else:
                    st.error("Please fill in both fields!")

# ==============================================================================
# 🚀 MAIN APP (Logged In)
# ==============================================================================
else:
    # Header
    hc1, hc2 = st.columns([0.06, 0.94])
    with hc1:
        try:
            st.image("logo.png", width=45)
        except Exception:
            st.markdown("🚀")
    with hc2:
        st.title("TEAMUPAI — AI App Builder")

    # --- SIDEBAR ---
    st.sidebar.header("⚙️ Settings")
    st.sidebar.write(f"👤 **{st.session_state.user['email']}**")
    if st.sidebar.button("🚪 Logout", type="secondary"):
        for key in ["user", "messages", "generated_code", "build_status"]:
            st.session_state.pop(key, None)
        st.rerun()

    st.sidebar.markdown("---")
    if st.sidebar.button("➕ New Project", use_container_width=True, type="primary"):
        st.session_state.current_session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.generated_code = None
        st.session_state.build_status = None
        st.rerun()

    sessions = load_user_sessions(st.session_state.user['email'])
    if sessions:
        st.sidebar.subheader("📜 Projects")
        sel = st.sidebar.selectbox("Load Project:", sessions, format_func=lambda x: f"📁 {x[:8]}...")
        if st.sidebar.button("📂 Load"):
            st.session_state.current_session_id = sel
            hist = load_chat_by_session(sel)
            st.session_state.messages = [{"role": r["role"], "content": r["content"], "type": r["msg_type"]} for r in hist]
            code, lang = load_project_code(sel)
            st.session_state.generated_code = code
            st.session_state.code_language = lang or "html"
            st.session_state.build_status = "ready" if code else None
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("💬 Feedback")
    fb = st.sidebar.text_area("Suggestions?", height=70, placeholder="Tell us...")
    if st.sidebar.button("Submit", use_container_width=True):
        if fb.strip():
            save_anonymous_feedback(fb.strip())
        else:
            st.sidebar.warning("Enter feedback first!")

    # --- MAIN CONTENT: Two Column Layout ---
    chat_col, preview_col = st.columns([1, 1], gap="medium")

    # LEFT: Chat Arena
    with chat_col:
        st.subheader("🤖 AI Team Discussion")
        
        type_styles = {
            "user": "chat-user", "pm": "chat-pm", "architect": "chat-architect",
            "coder": "chat-coder", "qa": "chat-qa", "judge": "chat-judge"
        }
        type_icons = {
            "user": "🧑‍💻", "pm": "📋", "architect": "🏗️",
            "coder": "💻", "qa": "🧪", "judge": "⚖️"
        }
        
        for msg in st.session_state.messages:
            css_class = type_styles.get(msg["type"], "chat-user")
            icon = type_icons.get(msg["type"], "💬")
            label = msg["role"]
            if msg["type"] != "user":
                st.markdown(f'<div class="agent-label">{icon} {label}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="chat-card {css_class}">{msg["content"]}</div>',
                unsafe_allow_html=True
            )

        user_input = st.chat_input("💡 Describe the app you want to build...")
        if user_input:
            run_app_builder_pipeline(user_input, st.session_state.current_session_id, st.session_state.user['email'])
            st.rerun()

    # RIGHT: Live Preview
    with preview_col:
        st.subheader("👁️ Live App Preview")
        
        if st.session_state.generated_code:
            status = st.session_state.build_status
            badge_class = "status-ready" if status == "ready" else "status-building"
            badge_text = "✅ READY" if status == "ready" else "🔨 BUILDING..."
            
            st.markdown(
                f'<div class="preview-header">'
                f'<span>🖥️ App Preview</span>'
                f'<span class="status-badge {badge_class}">{badge_text}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
            
            if st.session_state.code_language == "html":
                st.components.v1.html(st.session_state.generated_code, height=600, scrolling=True)
            else:
                st.code(st.session_state.generated_code, language="python")
                st.info("🐍 Python apps require a backend runtime. HTML apps preview instantly above.")
        else:
            st.markdown("""
            <div style="border: 2px dashed #30363d; border-radius: 12px; padding: 60px 20px; text-align: center; color: #8b949e;">
                <h3>🚀 No App Built Yet</h3>
                <p>Describe your app idea in the chat and our AI team will build it!</p>
                <p style="font-size: 14px; margin-top: 15px;">
                    Try: <em>"Build me a pomodoro timer with dark mode"</em><br>
                    or: <em>"Create a personal finance tracker with charts"</em>
                </p>
            </div>
            """, unsafe_allow_html=True)
