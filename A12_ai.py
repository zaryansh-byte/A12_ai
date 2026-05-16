import streamlit as st
from google import genai
from postgrest import SyncPostgrestClient
import os
from dotenv import load_dotenv

# Load secret infrastructure keys
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Connect to your Mumbai cloud database
@st.cache_resource
def init_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    return SyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

supabase = init_supabase()

# =====================================================================
# 1. PAGE SETUP & BRANDING LAYOUT
# =====================================================================
st.set_page_config(page_title="A12 AI Hub", page_icon="⚡", layout="centered")
st.markdown("<h1 style='text-align: center; color: #1e3c72;'>⚡ A12 AI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888888;'>The Hyper-Organized, Personal Premium AI Agent Engine</p>", unsafe_allow_html=True)
st.markdown("---")

# =====================================================================
# 2. CONTROL PANEL & SIDEBAR GATEWAY
# =====================================================================
with st.sidebar:
    st.header("⚙️ Control Panel")
    api_key = st.text_input("Enter Gemini API Key:", type="password", help="Grab a key from Google AI Studio")
    
    st.markdown("---")
    st.header("👤 User Account Portal")
    
    if supabase is None:
        st.error("⚠️ Database connection configurations missing in your backend environment.")
        user_authenticated = False
    else:
        if "user_email" not in st.session_state:
            st.session_state.user_email = None
            st.session_state.user_tier = "Free Account"
            st.session_state.db_messages = 0

        if st.session_state.user_email is None:
            auth_mode = st.tabs(["🔑 Log In", "📝 Sign Up"])
            
            # --- LOGIN CONTROLLER ---
            with auth_mode:
                login_email = st.text_input("Email", key="login_email")
                if st.button("Access Engine"):
                    prof = supabase.table("user_profiles").select("*").eq("email", login_email).execute()
                    if prof.data:
                        st.session_state.user_email = prof.data["email"]
                        st.session_state.user_tier = prof.data["tier"]
                        st.session_state.db_messages = prof.data["messages_sent"]
                        st.success("Access Granted!")
                        st.rerun()
                    else:
                        st.error("Account not found. Please Sign Up first!")
            
            # --- SIGN UP CONTROLLER ---
            with auth_mode:
                reg_email = st.text_input("Email", key="reg_email")
                if st.button("Create Account"):
                    supabase.table("user_profiles").insert({
                        "email": reg_email,
                        "tier": "Free Account",
                        "messages_sent": 0
                    }).execute()
                    st.session_state.user_email = reg_email
                    st.session_state.user_tier = "Free Account"
                    st.session_state.db_messages = 0
                    st.success("Account constructed successfully!")
                    st.rerun()
            user_authenticated = False
        else:
            st.success(f"📟 Connected: {st.session_state.user_email}")
            
            if st.session_state.user_tier == "Premium VIP Account":
                st.success("🔥 Tier: Premium VIP Unlocked!")
            else:
                st.info("📊 Tier: Free Account (3 Chat Limit)")
            
            st.metric(label="Messages Sent Today", value=st.session_state.db_messages)
            
            if st.button("Log Out Session"):
                st.session_state.user_email = None
                st.session_state.user_tier = "Free Account"
                st.session_state.db_messages = 0
                st.rerun()
            user_authenticated = True

# =====================================================================
# 3. RUNTIME EXECUTION
# =====================================================================
SYSTEM_INSTRUCTION = "You are the elite, premium, hyper-organized backend assistant for A12 AI. Use clear markdown headings (## or ###) and clean bullet points."

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_prompt := st.chat_input("Dispatch command to A12 AI..."):
    if not user_authenticated:
        st.error("🛑 Access Prohibited: You must log in or create an account in the sidebar.")
    elif st.session_state.user_tier == "Free Account" and st.session_state.db_messages >= 3:
        st.error("🛑 **Free Daily Limit Reached (3/3)!**")
        st.info("💡 Premium upgrade portals are currently undergoing system maintenance. Check back soon to unlock unlimited processing!")
    else:
        with st.chat_message("user"):
            st.markdown(user_prompt)
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        
        if not api_key:
            with st.chat_message("assistant"):
                st.error("⚠️ API Key Required: Input your Gemini key in the control panel sidebar.")
        else:
            try:
                st.session_state.db_messages += 1
                supabase.table("user_profiles").update({"messages_sent": st.session_state.db_messages}).eq("email", st.session_state.user_email).execute()
                
                target_model = 'gemini-2.5-flash' if st.session_state.user_tier == "Free Account" else 'gemini-2.5-pro'
                client = genai.Client(api_key=api_key)
                
                with st.chat_message("assistant"):
                    with st.spinner("Processing request..."):
                        response = client.models.generate_content(model=target_model, contents=user_prompt, config={"system_instruction": SYSTEM_INSTRUCTION})
                        st.markdown(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": response.text})
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Core Error: {e}")