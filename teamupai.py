import streamlit as st
from openai import OpenAI
import requests
import time
import uuid
import re
from supabase import create_client

# ==============================================================================
# PAGE CONFIG & SECRETS
# ==============================================================================
st.set_page_config(page_title="TEAMUPAI - Multi-Agent Platform", layout="wide", page_icon="🧠")

try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except KeyError as e:
    st.error(f"⚠️ Missing secret: {e}. Add it in Streamlit Settings → Secrets.")
    st.stop()
except Exception as e:
    st.error(f"⚠️ Supabase connection failed: {e}")
    st.stop()

# ==============================================================================
# 🔧 CONFIGURABLE AGENT MODES
# ==============================================================================
# මෙතනට ඕනෑම workflow එකක් add කරන්න පුළුවන්
AGENT_MODES = {
    "🛠️ App Builder": {
        "description": "AI team builds a web app from your idea",
        "agents": ["pm", "architect", "coder", "qa", "judge"],
        "labels": {
            "pm": "📋 PM", "architect": "🏗️ Architect",
            "coder": "💻 Coder", "qa": "🧪 QA", "judge": "⚖️ Judge"
        },
        "extract_code": True,
        "prompts": {
            "pm": """You are a Senior Product Manager.
Convert the user's idea into a clear, actionable PRD.
- Define MVP scope strictly
- Output: Overview, User Stories, Tech Requirements, MVP Boundaries""",
            "architect": """You are a Software Architect.
Design the simplest technical architecture from the PRD.
- Prefer single-file HTML/CSS/JS for MVPs
- Output: Tech Stack, File Structure, Implementation Notes""",
            "coder": """You are an Expert Developer.
Write COMPLETE, RUNNABLE code based on the architecture.
- Output ONLY code inside ```html or ```python blocks
- Single file, modern CSS, responsive
- Do NOT output explanations outside code blocks""",
            "qa": """You are a QA Engineer.
Review code against the PRD. Check: missing features, bugs, UX issues.
Output: ✅ Passed, ❌ Failed, 🔧 Fixes needed.""",
            "judge": """You are the Tech Lead. Synthesize all outputs.
If QA found issues → request fixes. If passed → confirm ready.
End with: STATUS: READY or STATUS: NEEDS_REVISION"""
        }
    },
    "📝 Content Writing": {
        "description": "Research, draft, edit, and polish any content",
        "agents": ["researcher", "writer", "editor", "factcheck", "judge"],
        "labels": {
            "researcher": "🔍 Researcher", "writer": "✍️ Writer",
            "editor": "📐 Editor", "factcheck": "✅ Fact Checker", "judge": "⚖️ Final Draft"
        },
        "extract_code": False,
        "prompts": {
            "researcher": """You are a Research Analyst.
Gather key facts, statistics, and perspectives on the topic.
Output structured research notes with sources where possible.""",
            "writer": """You are a Professional Writer.
Using the research, write a compelling first draft.
Match the tone and format requested by the user. Be engaging and clear.""",
            "editor": """You are a Senior Editor.
Improve the draft: fix grammar, improve flow, tighten structure.
Ensure readability and consistency. Show specific changes made.""",
            "factcheck": """You are a Fact Checker.
Verify claims in the edited draft against the research.
Flag any inaccuracies, unsupported claims, or misleading statements.""",
            "judge": """You are the Editor-in-Chief.
Produce the FINAL polished version incorporating all feedback.
Output only the final clean text ready for publication."""
        }
    },
    "💡 Business Strategy": {
        "description": "Analyze ideas, market fit, risks, and create action plans",
        "agents": ["analyst", "strategist", "critic", "planner", "judge"],
        "labels": {
            "analyst": "📊 Analyst", "strategist": "🎯 Strategist",
            "critic": "😈 Devil's Advocate", "planner": "📅 Planner", "judge": "⚖️ CEO Decision"
        },
        "extract_code": False,
        "prompts": {
            "analyst": """You are a Market Analyst.
Analyze the business idea: target market, competitors, trends, TAM/SAM/SOM.
Be data-driven and objective.""",
            "strategist": """You are a Business Strategist.
Based on analysis, propose a go-to-market strategy.
Cover: positioning, pricing, channels, partnerships, moat.""",
            "critic": """You are the Devil's Advocate.
Challenge EVERY assumption. Find fatal flaws, hidden risks, 
and reasons this could fail. Be brutally honest.""",
            "planner": """You are an Operations Planner.
Create a 90-day action plan with milestones, resources needed,
KPIs, and contingency plans for identified risks.""",
            "judge": """You are the CEO making the final decision.
Synthesize all perspectives into a clear GO/NO-GO recommendation.
Provide executive summary + top 3 priorities if GO."""
        }
    },
    "🎓 Learning Tutor": {
        "description": "Learn any topic through debate-style teaching",
        "agents": ["explainer", "questioner", "connector", "tester", "judge"],
        "labels": {
            "explainer": "📖 Explainer", "questioner": "❓ Questioner",
            "connector": "🔗 Connector", "tester": "📝 Tester", "judge": "🎓 Summary"
        },
        "extract_code": False,
        "prompts": {
            "explainer": """You are a Patient Teacher.
Explain the concept simply using analogies and examples.
Assume the learner is a beginner. Use ELI5 approach.""",
            "questioner": """You are a Curious Student.
Ask probing questions about gaps in the explanation.
Challenge assumptions. Ask 'why' and 'what if' questions.""",
            "connector": """You are a Knowledge Connector.
Link this concept to related topics, real-world applications,
and things the learner might already know. Build mental models.""",
            "tester": """You are a Quiz Master.
Create 3 quick questions to test understanding.
Include one trick question to check deep comprehension.""",
            "judge": """You are the Learning Coach.
Provide a concise summary of key takeaways.
Answer the quiz questions. Suggest what to learn next."""
        }
    },
    "⚖️ General Debate": {
        "description": "Two sides argue, judge decides — any topic",
        "agents": ["proponent", "opponent", "mediator", "judge"],
        "labels": {
            "proponent": "🟢 Proponent", "opponent": "🔴 Opponent",
            "mediator": "🟡 Mediator", "judge": "⚖️ Verdict"
        },
        "extract_code": False,
        "prompts": {
            "proponent": """Argue IN FAVOR of the proposition.
Present strongest evidence, logical reasoning, and examples.
Be persuasive but factual.""",
            "opponent": """Argue AGAINST the proposition.
Identify weaknesses, counter-evidence, and alternative viewpoints.
Challenge every claim made by the proponent.""",
            "mediator": """Find common ground between both sides.
Identify where they agree, where evidence is ambiguous,
and what additional information would resolve the dispute.""",
            "judge": """Deliver a balanced VERDICT.
Weigh both arguments fairly. State which side was stronger and why.
Acknowledge valid points from both sides. Be nuanced."""
        }
    }
}

# ==============================================================================
# SUPABASE FUNCTIONS
# ==============================================================================
def login_with_email(email, password):
    try:
        return supabase.auth.sign_in_with_password({"email": email, "password": password}).user
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
            "user_email": user_email, "session_id": session_id,
            "role": role, "content": content, "msg_type": msg_type
        }).execute()
    except Exception as e:
        print(f"DB Save Error: {e}")

def load_user_sessions(user_email):
    try:
        res = supabase.table("chat_history").select("session_id, created_at") \
            .eq("user_email", user_email).order("created_at", desc=True).execute()
        seen, sessions = set(), []
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
        return supabase.table("chat_history").select("*") \
            .eq("session_id", session_id).order("created_at").execute().data
    except Exception:
        return []

def save_project_code(session_id, code, language="html"):
    try:
        supabase.table("projects").upsert({
            "session_id": session_id, "code": code,
            "language": language, "updated_at": "now()"
        }, on_conflict="session_id").execute()
    except Exception as e:
        print(f"Project save error: {e}")

def load_project_code(session_id):
    try:
        res = supabase.table("projects").select("code, language") \
            .eq("session_id", session_id).single().execute()
        if res.data:
            return res.data["code"], res.data["language"]
    except Exception:
        pass
    return None, None

def save_anonymous_feedback(text):
    try:
        supabase.table("feedbacks").insert({"feedback_text": text}).execute()
        st.sidebar.success("🙏 Thank you!")
    except Exception as e:
        st.sidebar.error(f"Feedback error: {e}")

# ==============================================================================
# AUTO-DETECT FREE MODELS
# ==============================================================================
@st.cache_data(ttl=3600)
def get_free_models():
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        if res.status_code == 200:
            free = {}
            for m in res.json().get("data", []):
                mid = m.get("id", "")
                p = m.get("pricing", {})
                if (mid.endswith(":free") or
                    (str(p.get("prompt")) == "0" and str(p.get("completion")) == "0")) and mid:
                    free[m.get("name", mid)] = mid
            if len(free) >= 3:
                return free
    except Exception as e:
        print(f"Model fetch failed: {e}")
    return {
        "Gemini 2.0 Flash Exp": "google/gemini-2.0-flash-exp:free",
        "Llama 3.3 70B Instruct": "meta-llama/llama-3.3-70b-instruct:free",
        "Qwen 2.5 Coder 32B": "qwen/qwen-2.5-coder-32b-instruct:free",
        "Gemma 2 9B IT": "google/gemma-2-9b-it:free",
        "Mistral 7B Instruct": "mistralai/mistral-7b-instruct:free",
    }

FREE_MODELS = get_free_models()
MODEL_LIST = list(FREE_MODELS.values())

# ==============================================================================
# STYLING
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
    .chat-scroll-container {
        height: calc(100vh - 280px); overflow-y: auto;
        padding-right: 8px; scroll-behavior: smooth;
    }
    .chat-scroll-container::-webkit-scrollbar { width: 6px; }
    .chat-scroll-container::-webkit-scrollbar-track { background: #1a1a1a; border-radius: 3px; }
    .chat-scroll-container::-webkit-scrollbar-thumb { background: #404040; border-radius: 3px; }
    .chat-scroll-container::-webkit-scrollbar-thumb:hover { background: #58a6ff; }
    .chat-card {
        padding: 15px 18px; border-radius: 10px; margin-bottom: 12px;
        color: #e6e6e6; line-height: 1.7; word-wrap: break-word;
        overflow-wrap: break-word; white-space: pre-wrap; font-size: 14px;
    }
    .chat-card * { max-width: 100%; overflow-wrap: break-word; }
    .chat-card code { background: rgba(255,255,255,0.08); padding: 2px 6px; border-radius: 4px; font-size: 13px; word-break: break-all; }
    .chat-card pre { background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; overflow-x: auto; margin: 8px 0; }
    .chat-card pre code { background: none; padding: 0; word-break: normal; }
    .chat-user { background-color: #21262d; border-left: 4px solid #8b949e; }
    .agent-msg { background-color: #1a2332; border-left: 4px solid #58a6ff; }
    .chat-judge {
        background: linear-gradient(135deg, #113b19, #1a4a25);
        border-left: 4px solid #2ea043; border-radius: 12px; padding: 20px; margin: 15px 0;
    }
    .agent-label { font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px; opacity: 0.6; margin-bottom: 4px; font-weight: 600; }
    .preview-header {
        background: #21262d; padding: 10px 15px; font-weight: bold;
        display: flex; justify-content: space-between; align-items: center;
        border-radius: 12px 12px 0 0; border: 1px solid #30363d;
    }
    .status-badge { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }
    .status-building { background: #d29922; color: #000; }
    .status-ready { background: #2ea043; color: #fff; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# SESSION STATE
# ==============================================================================
for key, default in [
    ("user", None), ("current_session_id", str(uuid.uuid4())),
    ("messages", []), ("generated_code", None),
    ("code_language", "html"), ("build_status", None),
    ("selected_mode", "🛠️ App Builder")
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ==============================================================================
# SPLASH SCREEN
# ==============================================================================
if "splash_done" not in st.session_state:
    splash = st.empty()
    with splash.container():
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            try: st.image("logo.png", width=220)
            except Exception: st.markdown("<h1 style='text-align:center'>🧠</h1>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align:center; color:white;'>TEAMUPAI</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align:center; color:#8b949e;'>Multi-Agent Debate Platform</p>", unsafe_allow_html=True)
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
    default_headers={"HTTP-Referer": "https://teamupai.streamlit.app", "X-Title": "TEAMUPAI"}
)


def call_model(agent_role, prompt, current_mode):
    """Call model with fallback chain using mode-specific prompts"""
    mode_config = AGENT_MODES[current_mode]
    system_prompt = mode_config["prompts"].get(agent_role, "You are a helpful assistant.")
    
    # Assign models round-robin across available free models
    agent_list = mode_config["agents"]
    idx = agent_list.index(agent_role) % len(MODEL_LIST)
    model_id = MODEL_LIST[idx]
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    try:
        resp = client.chat.completions.create(model=model_id, messages=messages)
        return resp.choices[0].message.content
    except Exception as e:
        st.warning(f"⚠️ {agent_role.upper()} failed: {e}. Trying fallback...")
        time.sleep(1)

    for fb_id in MODEL_LIST:
        if fb_id == model_id:
            continue
        try:
            resp = client.chat.completions.create(model=fb_id, messages=messages)
            return resp.choices[0].message.content
        except Exception:
            continue
    return f"❌ All models failed for {agent_role}. Please try again."


def extract_code_block(text):
    patterns = [
        (r'```html\s*\n(.*?)```', "html"), (r'```htm\s*\n(.*?)```', "html"),
        (r'```python\s*\n(.*?)```', "python"), (r'```py\s*\n(.*?)```', "python"),
        (r'```\s*\n(.*?)```', "html"),
    ]
    for pattern, lang in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip(), lang
    return None, None


def render_chat_messages():
    """Render chat in scrollable container"""
    html_parts = ['<div class="chat-scroll-container" id="chatContainer">']
    for msg in st.session_state.messages:
        content = msg["content"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        
        if msg["type"] == "user":
            css = "chat-user"
            label = "🧑‍💻 User"
        elif msg["type"] == "judge":
            css = "chat-judge"
            label = msg["role"]
        else:
            css = "agent-msg"
            label = msg["role"]
        
        html_parts.append(f'<div class="agent-label">{label}</div>')
        html_parts.append(f'<div class="chat-card {css}">{content}</div>')
    
    html_parts.append('</div>')
    html_parts.append('<script>setTimeout(function(){var c=document.getElementById("chatContainer");if(c)c.scrollTop=c.scrollHeight;},100);</script>')
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def run_pipeline(user_query, session_id, user_email, current_mode):
    """Generic multi-agent pipeline for ANY mode"""
    mode_config = AGENT_MODES[current_mode]
    st.session_state.build_status = "building"

    st.session_state.messages.append({"role": "User", "content": user_query, "type": "user"})
    save_chat_to_db(user_email, session_id, "User", user_query, "user")

    history = "\n\n".join([f"[{m['role']}]: {m['content']}" for m in st.session_state.messages[:-1]])
    context = f"CONVERSATION HISTORY:\n{history}\n\nUSER REQUEST: {user_query}" if history else f"USER REQUEST: {user_query}"

    responses = {}
    agents = mode_config["agents"]
    labels = mode_config["labels"]

    for i, agent in enumerate(agents):
        label = labels[agent]
        with st.spinner(f"{label} working..."):
            # Build contextual prompt: include ALL previous agent outputs
            prev_outputs = "\n\n".join(
                [f"{labels[a]} OUTPUT:\n{responses[a]}" for a in agents[:i] if a in responses]
            )
            prompt = f"{context}\n\n{prev_outputs}" if prev_outputs else context

            result = call_model(agent, prompt, current_mode)
            responses[agent] = result

            msg_type = "judge" if agent == agents[-1] else agent
            st.session_state.messages.append({"role": label, "content": result, "type": msg_type})
            save_chat_to_db(user_email, session_id, label, result, msg_type)

            # Extract code only if mode supports it
            if mode_config.get("extract_code") and agent == "coder":
                code, lang = extract_code_block(result)
                if code:
                    st.session_state.generated_code = code
                    st.session_state.code_language = lang
                    save_project_code(session_id, code, lang)

    st.session_state.build_status = "ready"
    return responses


# ==============================================================================
# 🔒 LOGIN / REGISTER
# ==============================================================================
if st.session_state.user is None:
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        try: st.image("logo.png", width=100)
        except Exception: st.markdown("<h1 style='text-align:center'>🧠</h1>", unsafe_allow_html=True)
        st.title("🔐 Login to TEAMUPAI")
        st.caption("Multi-Agent AI Platform — Choose your workflow")

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
# 🚀 MAIN APP
# ==============================================================================
else:
    hc1, hc2 = st.columns([0.06, 0.94])
    with hc1:
        try: st.image("logo.png", width=45)
        except Exception: st.markdown("🧠")
    with hc2:
        st.title("TEAMUPAI — Multi-Agent Platform")

    # --- SIDEBAR ---
    st.sidebar.header("⚙️ Configuration")
    st.sidebar.write(f"👤 **{st.session_state.user['email']}**")

    # MODE SELECTOR — Core generalization feature
    st.sidebar.subheader("🎯 Select Mode")
    mode_names = list(AGENT_MODES.keys())
    selected = st.sidebar.radio(
        "Workflow:",
        mode_names,
        index=mode_names.index(st.session_state.selected_mode) if st.session_state.selected_mode in mode_names else 0,
        label_visibility="collapsed"
    )
    if selected != st.session_state.selected_mode:
        st.session_state.selected_mode = selected
        st.session_state.messages = []
        st.session_state.generated_code = None
        st.session_state.build_status = None
        st.session_state.current_session_id = str(uuid.uuid4())
        st.rerun()

    # Show mode description
    current_mode = st.session_state.selected_mode
    mode_config = AGENT_MODES[current_mode]
    st.sidebar.caption(f"_{mode_config['description']}_")

    with st.sidebar.expander("🤖 Active Agents"):
        for agent in mode_config["agents"]:
            label = mode_config["labels"][agent]
            idx = mode_config["agents"].index(agent) % len(MODEL_LIST)
            st.caption(f"**{label}:** `{MODEL_LIST[idx]}`")

    if st.sidebar.button("🚪 Logout", type="secondary"):
        for key in ["user", "messages", "generated_code", "build_status"]:
            st.session_state.pop(key, None)
        st.rerun()

    st.sidebar.markdown("---")
    if st.sidebar.button("➕ New Session", use_container_width=True, type="primary"):
        st.session_state.current_session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.generated_code = None
        st.session_state.build_status = None
        st.rerun()

    sessions = load_user_sessions(st.session_state.user['email'])
    if sessions:
        st.sidebar.subheader("📜 History")
        sel = st.sidebar.selectbox("Load:", sessions, format_func=lambda x: f"📁 {x[:8]}...")
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
        if fb.strip(): save_anonymous_feedback(fb.strip())
        else: st.sidebar.warning("Enter feedback first!")

    # --- MAIN CONTENT ---
    has_preview = mode_config.get("extract_code", False)
    if has_preview:
        chat_col, preview_col = st.columns([1, 1], gap="medium")
    else:
        chat_col = st.container()
        preview_col = None

    with chat_col:
        st.subheader(f"🤖 {current_mode}")
        render_chat_messages()

        placeholder_texts = {
            "🛠️ App Builder": "💡 Describe the app you want to build...",
            "📝 Content Writing": "✍️ What content do you need? (blog, email, report...)",
            "💡 Business Strategy": "🚀 Describe your business idea or challenge...",
            "🎓 Learning Tutor": "📚 What topic do you want to learn?",
            "⚖️ General Debate": "⚖️ State the proposition to debate..."
        }
        user_input = st.chat_input(placeholder_texts.get(current_mode, "Type your request..."))
        if user_input:
            run_pipeline(user_input, st.session_state.current_session_id, st.session_state.user['email'], current_mode)
            st.rerun()

    # Preview panel (only for App Builder mode)
    if preview_col and has_preview:
        with preview_col:
            st.subheader("👁️ Live Preview")
            if st.session_state.generated_code:
                status = st.session_state.build_status
                badge_class = "status-ready" if status == "ready" else "status-building"
                badge_text = "✅ READY" if status == "ready" else "🔨 BUILDING..."
                st.markdown(
                    f'<div class="preview-header"><span>🖥️ Preview</span>'
                    f'<span class="status-badge {badge_class}">{badge_text}</span></div>',
                    unsafe_allow_html=True
                )
                if st.session_state.code_language == "html":
                    st.components.v1.html(st.session_state.generated_code, height=600, scrolling=True)
                else:
                    st.code(st.session_state.generated_code, language="python")
                    st.info("🐍 Python apps require a backend runtime.")
            else:
                st.markdown("""
                <div style="border:2px dashed #30363d; border-radius:12px; padding:60px 20px; text-align:center; color:#8b949e;">
                    <h3>🚀 No Preview Yet</h3>
                    <p>Build an app to see live preview here.</p>
                </div>""", unsafe_allow_html=True)
