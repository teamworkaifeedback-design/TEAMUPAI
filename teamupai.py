import streamlit as st
from openai import OpenAI
import requests
import time
import uuid
import re
from supabase import create_client

# ==============================================================================
# PAGE CONFIG & SECRETS VALIDATION
# ==============================================================================
st.set_page_config(page_title="TEAMUPAI - AI App Builder", layout="wide", page_icon="🚀")

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except KeyError as e:
    st.error(f"⚠️ Missing secret: {e}. Go to Streamlit Settings → Secrets and add it.")
    st.stop()
except Exception as e:
    st.error(f"⚠️ Supabase connection failed: {e}")
    st.stop()

# ==============================================================================
# SUPABASE AUTH & DB FUNCTIONS
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
        st.success("✅ Account created! Please check your email to verify.")
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
# AUTO-DETECT FREE MODELS FROM OPENROUTER
# ==============================================================================
@st.cache_data(ttl=3600)
def get_free_models():
    """Auto-fetch active free models from OpenRouter API"""
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        if res.status_code == 200:
            models = res.json().get("data", [])
            free = {}
            for m in models:
                mid = m.get("id", "")
                pricing = m.get("pricing", {})
                is_free = mid.endswith(":free") or (
                    str(pricing.get("prompt")) == "0"
                    and str(pricing.get("completion")) == "0"
                )
                if is_free and mid:
                    name = m.get("name", mid)
                    free[name] = mid
            if len(free) >= 3:
                return free
    except Exception as e:
        print(f"Failed to fetch free models: {e}")

    return {
        "Gemini 2.0 Flash Exp": "google/gemini-2.0-flash-exp:free",
        "Llama 3.3 70B Instruct": "meta-llama/llama-3.3-70b-instruct:free",
        "Qwen 2.5 Coder 32B": "qwen/qwen-2.5-coder-32b-instruct:free",
        "Gemma 2 9B IT": "google/gemma-2-9b-it:free",
        "Mistral 7B Instruct": "mistralai/mistral-7b-instruct:free",
    }


FREE_MODELS = get_free_models()
MODEL_LIST = list(FREE_MODELS.values())

MODELS = {
    "pm": MODEL_LIST[0],
    "architect": MODEL_LIST[1] if len(MODEL_LIST) > 1 else MODEL_LIST[0],
    "coder": MODEL_LIST[2] if len(MODEL_LIST) > 2 else MODEL_LIST[0],
    "qa": MODEL_LIST[3] if len(MODEL_LIST) > 3 else MODEL_LIST[0],
    "judge": MODEL_LIST[4] if len(MODEL_LIST) > 4 else (MODEL_LIST[1] if len(MODEL_LIST) > 1 else MODEL_LIST[0]),
}

# ==============================================================================
# SYSTEM PROMPTS
# ==============================================================================
SYSTEM_PROMPTS = {
    "pm": """You are a Senior Product Manager at TEAMUPAI.
Your job: Convert the user's idea into a clear, actionable PRD.
- Ask clarifying questions if the idea is vague
- Define MVP scope strictly (no feature creep)
- Output a structured markdown PRD with: Overview, User Stories, Tech Requirements, MVP Boundaries
- Be concise and practical.""",

    "architect": """You are a Senior Software Architect at TEAMUPAI.
Review the PM's PRD and design the technical architecture.
- Choose the simplest tech stack (prefer single-file HTML/CSS/JS for MVPs)
- Identify potential issues or missing requirements
- Output: Tech Stack Decision, File Structure, Key Implementation Notes, Risk Assessment""",

    "coder": """You are an Expert Full-Stack Developer at TEAMUPAI.
Based on the approved architecture, write COMPLETE, RUNNABLE code.
CRITICAL RULES:
- Output ONLY code inside ```html or ```python code blocks
- For web apps: Single HTML file with embedded CSS + JS
- Include all functionality described in the PRD
- Make it visually polished (modern CSS, responsive)
- The code MUST run immediately when opened in a browser
- Do NOT output explanations outside code blocks""",

    "qa": """You are a QA Engineer at TEAMUPAI.
Review the generated code against the original PRD.
Check for: Missing features, UI/UX issues, JS errors, accessibility, mobile responsiveness.
Output: ✅ Passed items, ❌ Failed items, 🔧 Suggested fixes.
If critical issues exist, say "REBUILD NEEDED".""",

    "judge": """You are the Tech Lead & Final Decision Maker at TEAMUPAI.
Synthesize ALL agent outputs into a final deliverable.
- If QA found critical issues → Request specific fixes
- If everything passes → Confirm ready
- Provide a 2-sentence summary
- Always end with: STATUS: READY or STATUS: NEEDS_REVISION"""
}

# ==============================================================================
# STYLING WITH SCROLL FIX
# ==============================================================================
st.markdown("""
<style>
    /* Base dark theme */
    .stApp { background-color: #0d0d0d !important; color: #ffffff !important; }
    [data-testid="stSidebar"] { background-color: #1a1a1a !important; color: #ffffff !important; }
    
    /* Chat input styling */
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

    /* ===== SCROLLABLE CHAT CONTAINER ===== */
    .chat-scroll-container {
        height: calc(100vh - 280px);
        overflow-y: auto;
        padding-right: 8px;
        scroll-behavior: smooth;
    }
    
    /* Custom scrollbar for chat */
    .chat-scroll-container::-webkit-scrollbar { width: 6px; }
    .chat-scroll-container::-webkit-scrollbar-track { background: #1a1a1a; border-radius: 3px; }
    .chat-scroll-container::-webkit-scrollbar-thumb { background: #404040; border-radius: 3px; }
    .chat-scroll-container::-webkit-scrollbar-thumb:hover { background: #58a6ff; }

    /* Chat card base styles with proper overflow handling */
    .chat-card {
        padding: 15px 18px;
        border-radius: 10px;
        margin-bottom: 12px;
        color: #e6e6e6;
        line-height: 1.7;
        word-wrap: break-word;
        overflow-wrap: break-word;
        white-space: pre-wrap;
        font-size: 14px;
    }
    
    /* Ensure long words/URLs don't break layout */
    .chat-card * { max-width: 100%; overflow-wrap: break-word; }
    .chat-card code { 
        background: rgba(255,255,255,0.08); padding: 2px 6px; 
        border-radius: 4px; font-size: 13px; word-break: break-all;
    }
    .chat-card pre { 
        background: rgba(0,0,0,0.3); padding: 12px; 
        border-radius: 8px; overflow-x: auto; margin: 8px 0;
    }
    .chat-card pre code { background: none; padding: 0; word-break: normal; }

    /* Agent-specific colors */
    .chat-user { background-color: #21262d; border-left: 4px solid #8b949e; }
    .chat-pm { background-color: #1a2332; border-left: 4px solid #58a6ff; }
    .chat-architect { background-color: #2d1f33; border-left: 4px solid #bc8cff; }
    .chat-coder { background-color: #1c2d1f; border-left: 4px solid #3fb950; }
    .chat-qa { background-color: #332b1a; border-left: 4px solid #d29922; }
    .chat-judge {
        background: linear-gradient(135deg, #113b19, #1a4a25);
        border-left: 4px solid #2ea043; border-radius: 12px;
        padding: 20px; margin: 15px 0;
    }

    /* Agent label */
    .agent-label {
        font-size: 11px; text-transform: uppercase;
        letter-spacing: 1.2px; opacity: 0.6; margin-bottom: 4px;
        font-weight: 600;
    }

    /* Preview panel */
    .preview-header {
        background: #21262d; padding: 10px 15px; font-weight: bold;
        display: flex; justify-content: space-between; align-items: center;
        border-radius: 12px 12px 0 0; border: 1px solid #30363d;
    }
    .status-badge {
        padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold;
    }
    .status-building { background: #d29922; color: #000; }
    .status-ready { background: #2ea043; color: #fff; }

    /* Hide default streamlit footer */
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)

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
# OPENROUTER CLIENT
# ==============================================================================
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://teamupai.streamlit.app",
        "X-Title": "TEAMUPAI App Builder",
    }
)


def call_model(agent_role, prompt):
    """Call OpenRouter model with automatic fallback chain"""
    model_id = MODELS.get(agent_role, MODEL_LIST[0])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPTS[agent_role]},
        {"role": "user", "content": prompt}
    ]
    try:
        resp = client.chat.completions.create(model=model_id, messages=messages)
        return resp.choices[0].message.content
    except Exception as e:
        st.warning(f"⚠️ {agent_role.upper()} ({model_id}) failed: {e}. Trying fallback...")
        time.sleep(1)

    for fallback_id in MODEL_LIST:
        if fallback_id == model_id:
            continue
        try:
            resp = client.chat.completions.create(model=fallback_id, messages=messages)
            st.info(f"✅ Fallback succeeded with `{fallback_id}`")
            return resp.choices[0].message.content
        except Exception:
            continue

    return f"❌ All models failed for {agent_role}. Please try again later."


def extract_code_block(text):
    """Extract code from markdown code blocks"""
    patterns = [
        (r'```html\s*\n(.*?)```', "html"),
        (r'```htm\s*\n(.*?)```', "html"),
        (r'```python\s*\n(.*?)```', "python"),
        (r'```py\s*\n(.*?)```', "python"),
        (r'```\s*\n(.*?)```', "html"),
    ]
    for pattern, lang in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip(), lang
    return None, None


def render_chat_messages():
    """Render all chat messages inside a scrollable container"""
    type_styles = {
        "user": "chat-user", "pm": "chat-pm", "architect": "chat-architect",
        "coder": "chat-coder", "qa": "chat-qa", "judge": "chat-judge"
    }
    type_icons = {
        "user": "🧑‍💻 User", "pm": "📋 PM", "architect": "🏗️ Architect",
        "coder": "💻 Coder", "qa": "🧪 QA", "judge": "⚖️ Judge"
    }

    html_parts = ['<div class="chat-scroll-container" id="chatContainer">']

    for msg in st.session_state.messages:
        css_class = type_styles.get(msg["type"], "chat-user")
        icon_label = type_icons.get(msg["type"], "💬")
        
        # Escape HTML special chars in content but preserve markdown-like formatting
        content = msg["content"]
        # Convert newlines to <br> for proper display in HTML div
        content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        content = content.replace("\n", "<br>")

        html_parts.append(f'<div class="agent-label">{icon_label}</div>')
        html_parts.append(f'<div class="chat-card {css_class}">{content}</div>')

    html_parts.append('</div>')

    # Auto-scroll to bottom script
    html_parts.append("""
    <script>
        setTimeout(function() {
            var container = document.getElementById('chatContainer');
            if (container) { container.scrollTop = container.scrollHeight; }
        }, 100);
    </script>
    """)

    st.markdown("".join(html_parts), unsafe_allow_html=True)


def run_app_builder_pipeline(user_query, session_id, user_email):
    """Full multi-agent pipeline: PM → Architect → Coder → QA → Judge"""
    st.session_state.build_status = "building"

    st.session_state.messages.append({"role": "User", "content": user_query, "type": "user"})
    save_chat_to_db(user_email, session_id, "User", user_query, "user")

    history = "\n\n".join(
        [f"[{m['role']}]: {m['content']}" for m in st.session_state.messages[:-1]]
    )
    context = (
        f"CONVERSATION HISTORY:\n{history}\n\nUSER REQUEST: {user_query}"
        if history
        else f"USER REQUEST: {user_query}"
    )

    agents = ["pm", "architect", "coder", "qa", "judge"]
    agent_labels = {
        "pm": "📋 PM", "architect": "🏗️ Architect",
        "coder": "💻 Coder", "qa": "🧪 QA", "judge": "⚖️ Judge"
    }
    responses = {}

    for agent in agents:
        label = agent_labels[agent]
        with st.spinner(f"{label} working..."):
            if agent == "pm":
                prompt = context
            elif agent == "architect":
                prompt = f"{context}\n\nPM OUTPUT:\n{responses.get('pm', 'N/A')}"
            elif agent == "coder":
                prompt = (
                    f"{context}\n\n"
                    f"PM OUTPUT:\n{responses.get('pm', '')}\n\n"
                    f"ARCHITECT OUTPUT:\n{responses.get('architect', '')}"
                )
            elif agent == "qa":
                prompt = (
                    f"{context}\n\n"
                    f"PM OUTPUT:\n{responses.get('pm', '')}\n\n"
                    f"GENERATED CODE:\n{responses.get('coder', '')}"
                )
            elif agent == "judge":
                prompt = (
                    f"{context}\n\n"
                    f"PM: {responses.get('pm', '')}\n\n"
                    f"ARCHITECT: {responses.get('architect', '')}\n\n"
                    f"CODER: {responses.get('coder', '')}\n\n"
                    f"QA: {responses.get('qa', '')}"
                )
            else:
                prompt = context

            result = call_model(agent, prompt)
            responses[agent] = result

            st.session_state.messages.append({
                "role": label, "content": result, "type": agent
            })
            save_chat_to_db(user_email, session_id, label, result, agent)

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
                        st.session_state.build_status = None
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

    with st.sidebar.expander("🤖 Active Models"):
        for role, mid in MODELS.items():
            st.caption(f"**{role.upper()}:** `{mid}`")

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
        sel = st.sidebar.selectbox(
            "Load Project:", sessions,
            format_func=lambda x: f"📁 {x[:8]}..."
        )
        if st.sidebar.button("📂 Load"):
            st.session_state.current_session_id = sel
            hist = load_chat_by_session(sel)
            st.session_state.messages = [
                {"role": r["role"], "content": r["content"], "type": r["msg_type"]}
                for r in hist
            ]
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

    # LEFT: Scrollable Chat Arena
    with chat_col:
        st.subheader("🤖 AI Team Discussion")
        render_chat_messages()

        user_input = st.chat_input("💡 Describe the app you want to build...")
        if user_input:
            run_app_builder_pipeline(
                user_input,
                st.session_state.current_session_id,
                st.session_state.user['email']
            )
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
                st.components.v1.html(
                    st.session_state.generated_code,
                    height=600,
                    scrolling=True
                )
            else:
                st.code(st.session_state.generated_code, language="python")
                st.info("🐍 Python apps require a backend runtime. HTML apps preview instantly.")
        else:
            st.markdown("""
            <div style="border: 2px dashed #30363d; border-radius: 12px; 
                        padding: 60px 20px; text-align: center; color: #8b949e;">
                <h3>🚀 No App Built Yet</h3>
                <p>Describe your app idea and our AI team will build it!</p>
                <p style="font-size: 14px; margin-top: 15px;">
                    Try: <em>"Build me a pomodoro timer with dark mode"</em><br>
                    or: <em>"Create a personal finance tracker with charts"</em><br>
                    or: <em>"Make a todo app with local storage"</em>
                </p>
            </div>
            """, unsafe_allow_html=True)
