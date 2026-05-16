import streamlit as st
from google import genai
from postgrest import AsyncPostgrestClient
import os
from dotenv import load_dotenv
import stripe
from datetime import datetime, timezone

# Load infrastructure credentials
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY

@st.cache_resource
def init_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    # Using AsyncPostgrestClient for better compatibility with Streamlit
    return AsyncPostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)

supabase = init_supabase()

# =====================================================================
# PAGE SETUP & BRANDING LAYOUT
# =====================================================================
st.set_page_config(page_title="A12 AI Hub", page_icon="⚡", layout="centered")
st.markdown("<h1 style='text-align: center; color: #1e3c72;'>⚡ A12 AI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888888;'>The Hyper-Organized, Personal Premium AI Agent Engine</p>", unsafe_allow_html=True)
st.markdown("---")

# =====================================================================
# CONTROL PANEL & SIDEBAR GATEWAY
# =====================================================================
with st.sidebar:
    st.header("⚙️ Control Panel")
    api_key = st.text_input("Enter Gemini API Key:", type="password")
    
    st.markdown("---")
    st.header("👤 User Account Portal")
    
    if supabase is None:
        st.error("⚠️ Database configuration missing.")
        user_authenticated = False
    else:
        if "user_email" not in st.session_state:
            st.session_state.user_email = None
            st.session_state.user_tier = "Free Account"
            st.session_state.db_messages = 0
            st.session_state.window_started = None

        if st.session_state.user_email is None:
            auth_mode = st.tabs(["🔑 Log In", "📝 Sign Up"])
            
            # --- LOG IN TAB ---
            with auth_mode[0]:
                login_email = st.text_input("Email", key="login_email")
                if st.button("Access Engine", key="login_btn"):
                    try:
                        prof = supabase.table("user_profiles").select("*").eq("email", login_email).execute()
                        if prof.data and len(prof.data) > 0:
                            user_data = prof.data[0]
                            st.session_state.user_email = user_data.get("email")
                            st.session_state.user_tier = user_data.get("tier", "Free Account")
                            st.session_state.db_messages = user_data.get("messages_sent", 0)
                            st.session_state.window_started = user_data.get("window_started_at")
                            st.success("Access Granted!")
                            st.rerun()
                        else:
                            st.error("Account not found.")
                    except Exception as e:
                        st.error(f"Login error: {e}")
            
            # --- SIGN UP TAB ---
            with auth_mode[1]:
                reg_email = st.text_input("Email", key="reg_email")
                if st.button("Create Account", key="signup_btn"):
                    try:
                        # Check if email already exists
                        existing = supabase.table("user_profiles").select("*").eq("email", reg_email).execute()
                        if existing.data and len(existing.data) > 0:
                            st.error("Email already registered.")
                        else:
                            current_now = datetime.now(timezone.utc).isoformat()
                            supabase.table("user_profiles").insert({
                                "email": reg_email,
                                "tier": "Free Account",
                                "messages_sent": 0,
                                "window_started_at": current_now
                            }).execute()
                            st.session_state.user_email = reg_email
                            st.session_state.user_tier = "Free Account"
                            st.session_state.db_messages = 0
                            st.session_state.window_started = current_now
                            st.success("Account constructed!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Signup error: {e}")
            
            user_authenticated = False
        else:
            st.success(f"📟 Connected: {st.session_state.user_email}")
            
            # Check 24-hour window expiration and reset counter dynamically
            if st.session_state.window_started:
                try:
                    start_time = datetime.fromisoformat(st.session_state.window_started.replace('Z', '+00:00'))
                    hours_passed = (datetime.now(timezone.utc) - start_time).total_seconds() / 3600
                    
                    if hours_passed >= 24:
                        st.session_state.db_messages = 0
                        st.session_state.window_started = datetime.now(timezone.utc).isoformat()
                        supabase.table("user_profiles").update({
                            "messages_sent": 0,
                            "window_started_at": st.session_state.window_started
                        }).eq("email", st.session_state.user_email).execute()
                except ValueError:
                    # Handle malformed timestamp
                    st.warning("Timestamp format issue. Resetting window.")
                    st.session_state.window_started = datetime.now(timezone.utc).isoformat()
            
            if st.session_state.user_tier == "Premium VIP Account":
                st.success("🔥 Tier: Premium VIP Unlocked!")
            else:
                st.info("📊 Tier: Free Account (100 Chats / 24hrs)")
                
                if st.button("👑 Upgrade to Premium VIP ($9.99/mo)"):
                    with st.spinner("Generating secure Stripe checkout..."):
                        try:
                            checkout_session = stripe.checkout.Session.create(
                                line_items=[{'price': 'price_1TXeia15kpBKA014lFmG5yGW', 'quantity': 1}],
                                mode='subscription',
                                success_url='https://a12-ai.streamlit.app/?success=true',
                                cancel_url='https://a12-ai.streamlit.app/?canceled=true',
                                customer_email=st.session_state.user_email
                            )
                            st.markdown(f"[👉 Click Here to Pay Securely via Stripe]({checkout_session.url})")
                        except Exception as e:
                            st.error(f"Stripe error: {e}")
            
            st.metric(label="Messages Sent (Current 24h Window)", value=f"{st.session_state.db_messages} / 100")
            
            if st.button("Log Out Session"):
                st.session_state.user_email = None
                st.session_state.user_tier = "Free Account"
                st.session_state.db_messages = 0
                st.session_state.window_started = None
                st.rerun()
            user_authenticated = True

# =====================================================================
# RUNTIME CHAT CORE
# =====================================================================
SYSTEM_INSTRUCTION = "You are the elite, premium, hyper-organized backend assistant for A12 AI. Use headings and bullet points."

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_prompt := st.chat_input("Dispatch command..."):
    if not user_authenticated:
        st.error("🛑 Access Prohibited: Log in first.")
    elif st.session_state.user_tier == "Free Account" and st.session_state.db_messages >= 100:
        st.error("🛑 **Daily Limit Reached (100/100)!**")
        st.info("Bypass this 24-hour cooldown instantly by clicking 'Upgrade to Premium VIP' in the control panel!")
    else:
        with st.chat_message("user"):
            st.markdown(user_prompt)
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        
        if not api_key:
            with st.chat_message("assistant"):
                st.error("⚠️ Gemini API Key Required in Sidebar.")
        else:
            try:
                st.session_state.db_messages += 1
                supabase.table("user_profiles").update({"messages_sent": st.session_state.db_messages}).eq("email", st.session_state.user_email).execute()
                
                target_model = 'gemini-2.5-flash' if st.session_state.user_tier == "Free Account" else 'gemini-2.5-pro'
                client = genai.Client(api_key=api_key)
                
                with st.chat_message("assistant"):
                    with st.spinner("Processing..."):
                        response = client.models.generate_content(
                            model=target_model,
                            contents=user_prompt,
                            config={"system_instruction": SYSTEM_INSTRUCTION}
                        )
                        st.markdown(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": response.text})
                        st.rerun()
            except Exception as e:
                with st.chat_message("assistant"):
                    st.error(f"❌ Core Error: {e}")
