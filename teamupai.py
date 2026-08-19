import streamlit as st
from openai import OpenAI
import requests
import time
import uuid
from datetime import date
from supabase import create_client

# Page Configuration
st.set_page_config(page_title="TEAMUPAI 1.1", page_icon="logo.png", layout="wide")

# --- DAILY PROMPT LIMIT CONFIGURATION ---
DAILY_PROMPT_LIMIT = 10  # Limit per user per day

# --- SUPABASE & OPENROUTER CONFIGURATION ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("⚠️ Secrets not configured properly! Check Streamlit Settings -> Secrets.")
    st.stop()

# Initialize Centralized OpenRouter Client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "https://teamupai.streamlit.app",
        "X-Title": "TEAMUPAI",
    }
)

# --- SUPABASE AUTH & DB FUNCTIONS ---
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
        st.success("Account created successfully! You can now Sign In.")
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
        print(f"Error saving chat: {e}")

def load_user_sessions(user_email):
    try:
        res = supabase.table("chat_history").select("session_id, created_at").eq("user_email", user_email).order("created_at", desc=True).execute()
        sessions = []
        seen = set()
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
        res = supabase.table("chat_history").select("*").eq("session_id", session_id).order("created_at").execute()
        return res.data
    except Exception:
        return []

def save_anonymous_feedback(text):
    try:
        supabase.table("feedbacks").insert({"feedback_text": text}).execute()
        st.sidebar.success("Thank you for your feedback! 🙏")
    except Exception as e:
        st.sidebar.error(f"Error submitting feedback: {e}")

# --- USAGE TRACKING FUNCTIONS ---
def check_and_update_usage(user_email):
    today_str = str(date.today())
    try:
        res = supabase.table("user_usage").select("*").eq("user_email", user_email).eq("usage_date", today_str).execute()
        if res.data:
            current_count = res.data[0]["prompt_count"]
            if current_count >= DAILY_PROMPT_LIMIT:
                return False, current_count
            else:
                supabase.table("user_usage").update({"prompt_count": current_count + 1}).eq("user_email", user_email).eq("usage_date", today_str).execute()
                return True, current_count + 1
        else:
            supabase.table("user_usage").insert({"user_email": user_email, "usage_date": today_str, "prompt_count": 1}).execute()
            return True, 1
    except Exception as e:
        print(f"Usage tracking error: {e}")
        return True, 0

def call_openrouter(model_id, prompt):
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        st.warning(f"⚠️ Model `{model_id}` faced an issue. Retrying with fallback model...")
        time.sleep(1.5)
        
        fallback_model = "google/gemini-2.0-flash-lite-001:free"
        if model_id == fallback_model:
            fallback_model = "meta-llama/llama-3.3-70b-instruct:free"

        try:
            response = client.chat.completions.create(
                model=fallback_model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except Exception as inner_e:
            return f"Error generating response: {str(inner_e)}"

# --- CUSTOM DARK THEME STYLING ---
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d !important; color: #ffffff !important; }
    [data-testid="stSidebar"] { background-color: #1a1a1a !important; color: #ffffff !important; }
    
    [data-testid="stChatInput"] { background-color: #21262d !important; border: 1px solid #404040 !important; border-radius: 12px !important; }
    [data-testid="stChatInput"] > div, [data-testid="stChatInput"] div[data-baseweb="textarea"], [data-testid="stChatInput"] div[data-baseweb="base-input"] { background-color: #21262d !important; color: #ffffff !important; }
    [data-testid="stChatInput"] textarea { background-color: #21262d !important; color: #ffffff !important; font-size: 16px !important; -webkit-text-fill-color: #ffffff !important; }
    [data-testid="stChatInput"] textarea::placeholder { color: #8b949e !important; -webkit-text-fill-color: #8b949e !important; }

    .stTextInput input, .stTextArea textarea { background-color: #262626 !important; color: #ffffff !important; border: 1px solid #404040 !important; }

    .chat-card { padding: 15px; border-radius: 10px; margin-bottom: 15px; color: #ffffff; }
    .chat-user { background-color: #21262d; border-left: 5px solid #8b949e; }
    .chat-model-a { background-color: #3b1111; border-left: 5px solid #ff4d4d; }
    .chat-model-b { background-color: #3b3311; border-left: 5px solid #ffcc00; }
    .chat-judge { background-color: #113b19; border-left: 5px solid #2ea043; border-radius: 10px; padding: 20px; margin-top: 15px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATES ---
if "user" not in st.session_state:
    st.session_state.user = None
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "editing_idx" not in st.session_state:
    st.session_state.editing_idx = None

# --- SPLASH SCREEN ---
if "splash_done" not in st.session_state:
    splash_placeholder = st.empty()
    with splash_placeholder.container():
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image("logo.png", width=220)
            st.markdown("<h2 style='text-align: center; color: white;'>TEAMUPAI 1.1</h2>", unsafe_allow_html=True)
            st.progress(100)
    time.sleep(3)
    st.session_state.splash_done = True
    splash_placeholder.empty()

# ==============================================================================
# 🔒 SCENARIO 1: USER IS NOT LOGGED IN
# ==============================================================================
if st.session_state.user is None:
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    
    with col2:
        st.image("logo.png", width=100)
        st.title("🔐 Login to TEAMUPAI 1.1")
        st.caption("Sign in with your email to access the Multi-Model Debate Arena.")
        
        tab1, tab2 = st.tabs(["🔑 Sign In", "📝 Sign Up"])
        
        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Sign In", type="primary", use_container_width=True):
                if email and password:
                    user = login_with_email(email, password)
                    if user:
                        st.session_state.user = {"email": user.email}
                        st.session_state.current_session_id = str(uuid.uuid4())
                        st.session_state.messages = []
                        st.rerun()
                else:
                    st.error("Please enter Email & Password!")

        with tab2:
            new_email = st.text_input("Email", key="reg_email")
            new_pass = st.text_input("Password", type="password", key="reg_pass")
            if st.button("Create Account", use_container_width=True):
                if new_email and new_pass:
                    register_with_email(new_email, new_pass)
                else:
                    st.error("Please fill in both Email and Password!")

# ==============================================================================
# 🚀 SCENARIO 2: USER IS LOGGED IN
# ==============================================================================
else:
    # Header & Logo
    h_col1, h_col2 = st.columns([0.08, 0.92])
    with h_col1:
        st.image("logo.png", width=50)
    with h_col2:
        st.title("⚔️ TEAMUPAI 1.1")

    # --- SIDEBAR CONFIGURATION ---
    st.sidebar.header("⚙️ Settings")
    st.sidebar.write(f"👤 **{st.session_state.user['email']}**")
    
    if st.sidebar.button("🚪 Logout", type="secondary"):
        st.session_state.user = None
        st.session_state.messages = []
        st.rerun()

    st.sidebar.markdown("---")
    
    # NEW CHAT BUTTON & CHAT HISTORY
    if st.sidebar.button("➕ New Chat", use_container_width=True, type="primary"):
        st.session_state.current_session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.editing_idx = None
        st.rerun()

    user_sessions = load_user_sessions(st.session_state.user['email'])
    if user_sessions:
        st.sidebar.subheader("📜 Chat History")
        selected_session = st.sidebar.selectbox(
            "Select Session:", 
            user_sessions, 
            format_func=lambda x: f"Session: {x[:8]}..."
        )
        if st.sidebar.button("📂 Load Selected Chat"):
            st.session_state.current_session_id = selected_session
            history_data = load_chat_by_session(selected_session)
            st.session_state.messages = [
                {"role": row["role"], "content": row["content"], "type": row["msg_type"]}
                for row in history_data
            ]
            st.session_state.editing_idx = None
            st.rerun()

    st.sidebar.markdown("---")

    # Fetch Active Free Models
    @st.cache_data(ttl=3600)
    def get_active_free_models():
        try:
            res = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
            if res.status_code == 200:
                data = res.json().get("data", [])
                free_models = {}
                for m in data:
                    if m.get("id", "").endswith(":free") or (
                        m.get("pricing", {}).get("prompt") == "0" and m.get("pricing", {}).get("completion") == "0"
                    ):
                        free_models[m.get("name", m["id"])] = m["id"]
                if free_models:
                    return free_models
        except Exception:
            pass
        return {
            "Gemini 2.0 Flash Lite": "google/gemini-2.0-flash-lite-001:free",
            "Llama 3.3 70B Instruct": "meta-llama/llama-3.3-70b-instruct:free",
            "Qwen 2.5 Coder 32B": "qwen/qwen-2.5-coder-32b-instruct:free",
        }

    FREE_MODELS = get_active_free_models()
    model_a_name = st.sidebar.selectbox("🔴 Fighter 1 (Model A)", list(FREE_MODELS.keys()), index=0)
    model_b_name = st.sidebar.selectbox("🟡 Fighter 2 (Model B)", list(FREE_MODELS.keys()), index=min(1, len(FREE_MODELS)-1))
    judge_model_name = st.sidebar.selectbox("🟢 Final Judge", list(FREE_MODELS.keys()), index=min(2, len(FREE_MODELS)-1))

    model_a = FREE_MODELS[model_a_name]
    model_b = FREE_MODELS[model_b_name]
    judge_model = FREE_MODELS[judge_model_name]

    # --- ANONYMOUS FEEDBACK SECTION ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("💬 Anonymous Feedback")
    fb_text = st.sidebar.text_area("How can we improve TEAMUPAI?", height=80, placeholder="Write your thoughts...")
    if st.sidebar.button("Submit Feedback", use_container_width=True):
        if fb_text.strip():
            save_anonymous_feedback(fb_text.strip())
        else:
            st.sidebar.warning("Please enter your feedback first!")

    def process_debate_round(user_query, truncate_from_idx=None):
        user_email = st.session_state.user['email']
        
        # Check usage limit
        allowed, count = check_and_update_usage(user_email)
        if not allowed:
            st.error(f"🛑 Daily limit reached ({DAILY_PROMPT_LIMIT}/{DAILY_PROMPT_LIMIT} prompts)! Please come back tomorrow.")
            return

        session_id = st.session_state.current_session_id

        # Truncate messages if editing or regenerating
        if truncate_from_idx is not None:
            st.session_state.messages = st.session_state.messages[:truncate_from_idx]
        
        st.session_state.messages.append({"role": "User", "content": user_query, "type": "user"})
        save_chat_to_db(user_email, session_id, "User", user_query, "user")
        
        full_history = "".join([f"[{m['role']}]: {m['content']}\n\n" for m in st.session_state.messages[:-1]])

        # Step 1: Model A
        with st.spinner(f"🔴 {model_a_name} generating..."):
            prompt_a = f"History:\n{full_history}\nUser Request: {user_query}\nProvide analysis/solution."
            res_a = call_openrouter(model_a, prompt_a)
            st.session_state.messages.append({"role": model_a_name, "content": res_a, "type": "model_a"})
            save_chat_to_db(user_email, session_id, model_a_name, res_a, "model_a")

        # Step 2: Model B
        with st.spinner(f"🟡 {model_b_name} debating..."):
            prompt_b = f"History:\n{full_history}\nUser: {user_query}\n{model_a_name} said: '{res_a}'\nCritique and improve."
            res_b = call_openrouter(model_b, prompt_b)
            st.session_state.messages.append({"role": model_b_name, "content": res_b, "type": "model_b"})
            save_chat_to_db(user_email, session_id, model_b_name, res_b, "model_b")

        # Step 3: Judge
        with st.spinner(f"🟢 Final Judge ({judge_model_name}) synthesizing..."):
            judge_prompt = f"History:\n{full_history}\nUser: {user_query}\n[{model_a_name}]: {res_a}\n[{model_b_name}]: {res_b}\nSynthesize final truth."
            final_res = call_openrouter(judge_model, judge_prompt)
            st.session_state.messages.append({"role": judge_model_name, "content": final_res, "type": "judge"})
            save_chat_to_db(user_email, session_id, judge_model_name, final_res, "judge")

    # Main Arena Output
    for i, msg in enumerate(st.session_state.messages):
        if msg["type"] == "user":
            col_msg, col_btn = st.columns([0.9, 0.1])
            with col_msg:
                st.markdown(f'<div class="chat-card chat-user"><b>🧑‍💻 User:</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)
            with col_btn:
                if st.button("✏️ Edit", key=f"edit_btn_{i}"):
                    st.session_state.editing_idx = i
                    st.rerun()

            # Display inline edit text-box if edit button clicked
            if st.session_state.editing_idx == i:
                edited_text = st.text_area("Edit your prompt:", value=msg["content"], key=f"edit_input_{i}")
                col_save, col_cancel = st.columns([0.2, 0.8])
                if col_save.button("Save & Resubmit", key=f"save_{i}", type="primary"):
                    st.session_state.editing_idx = None
                    process_debate_round(edited_text, truncate_from_idx=i)
                    st.rerun()
                if col_cancel.button("Cancel", key=f"cancel_{i}"):
                    st.session_state.editing_idx = None
                    st.rerun()

        elif msg["type"] == "model_a":
            st.markdown(f'<div class="chat-card chat-model-a"><b>🔴 {msg["role"]}:</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)
        elif msg["type"] == "model_b":
            st.markdown(f'<div class="chat-card chat-model-b"><b>🟡 {msg["role"]}:</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)
        elif msg["type"] == "judge":
            st.markdown(f'<div class="chat-judge"><h3>🟢 🏆 Final Synthesized Output ({msg["role"]}):</h3><hr>{msg["content"]}</div>', unsafe_allow_html=True)
            
            # Show Regenerate button for the latest Judge output
            if i == len(st.session_state.messages) - 1:
                if st.button("🔄 Regenerate Response", type="secondary"):
                    # Find last user prompt
                    last_user_prompt = ""
                    last_user_idx = 0
                    for u_idx in range(len(st.session_state.messages) - 1, -1, -1):
                        if st.session_state.messages[u_idx]["type"] == "user":
                            last_user_prompt = st.session_state.messages[u_idx]["content"]
                            last_user_idx = u_idx
                            break
                    if last_user_prompt:
                        process_debate_round(last_user_prompt, truncate_from_idx=last_user_idx)
                        st.rerun()

    user_input = st.chat_input("Enter your prompt or follow-up question here...")
    if user_input:
        process_debate_round(user_input)
        st.rerun()
