import streamlit as st
from openai import OpenAI
import requests
import time
from supabase import create_client

# Page Configuration
st.set_page_config(page_title="TEAMUPAI 1.0", page_icon="⚔️", layout="wide")

# --- SUPABASE SECURE CONFIGURATION ---
# Streamlit Secrets වලින් automatic Keys ලබා ගනී
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error("⚠️ Supabase Secrets configured නැත! Streamlit Settings -> Secrets බලන්න.")
    st.stop()

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
        st.success("Account එක සාර්ථකව සෑදුවා! දැන් Sign In වෙන්න.")
        return res.user
    except Exception as e:
        st.error(f"Registration Error: {e}")
        return None

def login_with_provider(provider_name):
    """Triggers OAuth Login for Google / GitHub"""
    try:
        res = supabase.auth.sign_in_with_oauth({
            "provider": provider_name,
            "options": {
                "redirect_to": "https://teamupai.streamlit.app" # ඔයාගේ App URL එක
            }
        })
        st.info(f"Redirecting to {provider_name.capitalize()} Login...")
    except Exception as e:
        st.error(f"{provider_name} Login Error: {e}")

def save_chat_to_db(user_email, role, content, msg_type):
    try:
        supabase.table("chat_history").insert({
            "user_email": user_email,
            "role": role,
            "content": content,
            "msg_type": msg_type
        }).execute()
    except Exception as e:
        print(f"Error saving to DB: {e}")

# --- CUSTOM DARK THEME & STYLING ---
st.markdown("""
<style>
    .stApp { background-color: #0d0d0d !important; color: #ffffff !important; }
    [data-testid="stSidebar"] { background-color: #1a1a1a !important; color: #ffffff !important; }
    
    [data-testid="stChatInput"] { background-color: #21262d !important; border: 1px solid #404040 !important; border-radius: 12px !important; }
    [data-testid="stChatInput"] > div, [data-testid="stChatInput"] div[data-baseweb="textarea"], [data-testid="stChatInput"] div[data-baseweb="base-input"] { background-color: #21262d !important; color: #ffffff !important; }
    [data-testid="stChatInput"] textarea { background-color: #21262d !important; color: #ffffff !important; font-size: 16px !important; -webkit-text-fill-color: #ffffff !important; }
    [data-testid="stChatInput"] textarea::placeholder { color: #8b949e !important; -webkit-text-fill-color: #8b949e !important; }

    .stTextInput input { background-color: #262626 !important; color: #ffffff !important; border: 1px solid #404040 !important; }

    .chat-card { padding: 15px; border-radius: 10px; margin-bottom: 15px; color: #ffffff; }
    .chat-user { background-color: #21262d; border-left: 5px solid #8b949e; }
    .chat-model-a { background-color: #3b1111; border-left: 5px solid #ff4d4d; }
    .chat-model-b { background-color: #3b3311; border-left: 5px solid #ffcc00; }
    .chat-judge { background-color: #113b19; border-left: 5px solid #2ea043; border-radius: 10px; padding: 20px; margin-top: 15px; margin-bottom: 20px; }

    .openrouter-btn {
        display: inline-block; width: 100%; text-align: center; background-color: #2b2b2b;
        color: #61afef !important; padding: 8px 0px; border-radius: 5px; text-decoration: none;
        font-weight: bold; border: 1px solid #404040; margin-top: 5px; margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATES ---
if "user" not in st.session_state:
    st.session_state.user = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 1. SPLASH SCREEN (5 SECONDS LOGO) ---
if "splash_done" not in st.session_state:
    splash_placeholder = st.empty()
    with splash_placeholder.container():
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image("logo.png", width=220)
            st.markdown("<h2 style='text-align: center; color: white;'>TEAMUPAI 1.0</h2>", unsafe_allow_html=True)
            st.progress(100)
    time.sleep(5)
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
        st.title("🔐 Login to TEAMUPAI")
        st.caption("You must log in to access the Multi-Model Debate Arena.")
        
        # --- SOCIAL OAUTH LOGIN BUTTONS ---
        st.subheader("Quick Social Login")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🌐 Sign in with Google", use_container_width=True):
                login_with_provider("google")
        with c2:
            if st.button("🐙 Sign in with GitHub", use_container_width=True):
                login_with_provider("github")
                
        st.markdown("---")
        
        # --- STANDARD EMAIL LOGIN / SIGNUP ---
        st.subheader("Or Sign in with Email")
        tab1, tab2 = st.tabs(["🔑 Sign In", "📝 Sign Up"])
        
        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Sign In", type="primary", use_container_width=True):
                if email and password:
                    user = login_with_email(email, password)
                    if user:
                        st.session_state.user = {"email": user.email}
                        st.success("Logged in successfully!")
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
        st.title("⚔️ TEAMUPAI 1.0")

    # Sidebar Options
    st.sidebar.header("⚙️ Settings")
    st.sidebar.write(f"👤 Logged in as: **{st.session_state.user['email']}**")
    
    if st.sidebar.button("🚪 Logout", type="secondary"):
        st.session_state.user = None
        st.session_state.messages = []
        st.rerun()

    st.sidebar.markdown("---")
    api_key = st.sidebar.text_input("OpenRouter API Key:", type="password")

    st.sidebar.markdown(
        '<a href="https://openrouter.ai/settings/keys" target="_blank" class="openrouter-btn">🔑 Get OpenRouter API Key (Free)</a>',
        unsafe_allow_html=True
    )

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

    if st.sidebar.button("🗑️ Reset Debate Arena"):
        st.session_state.messages = []
        st.rerun()

    def call_openrouter(client, model_id, prompt):
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "rate-limited" in error_msg or "404" in error_msg or "unavailable" in error_msg:
                fallback_models = [m for m in FREE_MODELS.values() if m != model_id]
                fallback_model = fallback_models[0] if fallback_models else "google/gemini-2.0-flash-lite-001:free"
                st.warning(f"⚠️ Model `{model_id}` busy. Switching to `{fallback_model}`...")
                time.sleep(1)
                response = client.chat.completions.create(
                    model=fallback_model,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            else:
                raise e

    def process_debate_round(user_query, client):
        user_email = st.session_state.user['email']
        
        st.session_state.messages.append({"role": "User", "content": user_query, "type": "user"})
        save_chat_to_db(user_email, "User", user_query, "user")
        
        full_history = "".join([f"[{m['role']}]: {m['content']}\n\n" for m in st.session_state.messages[:-1]])

        # Step 1: Model A
        with st.spinner(f"🔴 {model_a_name} generating..."):
            prompt_a = f"History:\n{full_history}\nUser Request: {user_query}\nProvide analysis/solution."
            res_a = call_openrouter(client, model_a, prompt_a)
            st.session_state.messages.append({"role": model_a_name, "content": res_a, "type": "model_a"})
            save_chat_to_db(user_email, model_a_name, res_a, "model_a")

        # Step 2: Model B
        with st.spinner(f"🟡 {model_b_name} debating..."):
            prompt_b = f"History:\n{full_history}\nUser: {user_query}\n{model_a_name} said: '{res_a}'\nCritique and improve."
            res_b = call_openrouter(client, model_b, prompt_b)
            st.session_state.messages.append({"role": model_b_name, "content": res_b, "type": "model_b"})
            save_chat_to_db(user_email, model_b_name, res_b, "model_b")

        # Step 3: Judge
        with st.spinner(f"🟢 Final Judge ({judge_model_name}) synthesizing..."):
            judge_prompt = f"History:\n{full_history}\nUser: {user_query}\n[{model_a_name}]: {res_a}\n[{model_b_name}]: {res_b}\nSynthesize final truth."
            final_res = call_openrouter(client, judge_model, judge_prompt)
            st.session_state.messages.append({"role": judge_model_name, "content": final_res, "type": "judge"})
            save_chat_to_db(user_email, judge_model_name, final_res, "judge")

    # Main Arena Output
    if api_key:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

        for msg in st.session_state.messages:
            if msg["type"] == "user":
                st.markdown(f'<div class="chat-card chat-user"><b>🧑‍💻 User:</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)
            elif msg["type"] == "model_a":
                st.markdown(f'<div class="chat-card chat-model-a"><b>🔴 {msg["role"]}:</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)
            elif msg["type"] == "model_b":
                st.markdown(f'<div class="chat-card chat-model-b"><b>🟡 {msg["role"]}:</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)
            elif msg["type"] == "judge":
                st.markdown(f'<div class="chat-judge"><h3>🟢 🏆 Final Synthesized Output ({msg["role"]}):</h3><hr>{msg["content"]}</div>', unsafe_allow_html=True)

        user_input = st.chat_input("Enter your prompt or follow-up question here...")
        if user_input:
            process_debate_round(user_input, client)
            st.rerun()

    else:
        st.info("👈 Please enter your OpenRouter API Key in the sidebar to start.")
