import streamlit as st
from google import genai
import openai
from postgrest import PostgrestClient
import os
from dotenv import load_dotenv
import stripe
from datetime import datetime, timezone
import hashlib

# Load infrastructure credentials
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY

# =====================================================================
# DATABASE INITIALIZATION
# =====================================================================
@st.cache_resource
def init_supabase():
    """Initialize Supabase client with proper error handling."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    
    try:
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY
        }
        client = PostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)
        return client
    except Exception as e:
        return None

supabase = init_supabase()

# =====================================================================
# PAGE SETUP & BRANDING
# =====================================================================
st.set_page_config(page_title="A12 AI Hub", page_icon="⚡", layout="wide")
st.markdown("<h1 style='text-align: center; color: #1e3c72;'>⚡ A12 AI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888888;'>The Hyper-Organized, Personal Premium AI Agent Engine</p>", unsafe_allow_html=True)
st.markdown("---")

# =====================================================================
# SESSION STATE INITIALIZATION
# =====================================================================
def init_session_state():
    """Initialize all required session state variables."""
    defaults = {
        "user_email": None,
        "user_tier": "Free Account",
        "db_messages": 0,
        "window_started": None,
        "ai_model": "Gemini 2.5 Flash",
        "messages": [],
        "user_authenticated": False,
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# =====================================================================
# AUTHENTICATION FUNCTIONS
# =====================================================================
def validate_email(email):
    """Validate email format."""
    return email and "@" in email and "." in email.split("@")[1]

def handle_login(login_email):
    """Handle user login with proper error handling."""
    if not validate_email(login_email):
        st.error("❌ Please enter a valid email address.")
        return False
    
    if supabase is None:
        st.error("❌ Database connection failed.")
        return False
    
    try:
        # Query the database
        response = supabase.table("user_profiles").select("*").eq("email", login_email).execute()
        
        # Check if data exists
        if response and hasattr(response, 'data') and response.data and len(response.data) > 0:
            user_data = response.data[0]
            st.session_state.user_email = user_data.get("email")
            st.session_state.user_tier = user_data.get("tier", "Free Account")
            st.session_state.db_messages = user_data.get("messages_sent", 0)
            st.session_state.window_started = user_data.get("window_started_at")
            st.session_state.user_authenticated = True
            st.success("✅ Access Granted!")
            st.rerun()
            return True
        else:
            st.error("❌ Account not found. Please sign up.")
            return False
            
    except Exception as e:
        st.error(f"❌ Login error: {str(e)}")
        return False

def handle_signup(reg_email):
    """Handle user signup with proper error handling."""
    if not validate_email(reg_email):
        st.error("❌ Please enter a valid email address.")
        return False
    
    if supabase is None:
        st.error("❌ Database connection failed.")
        return False
    
    try:
        # Check if email already exists
        check_response = supabase.table("user_profiles").select("*").eq("email", reg_email).execute()
        
        if check_response and hasattr(check_response, 'data') and check_response.data and len(check_response.data) > 0:
            st.error("❌ Email already registered.")
            return False
        
        # Create new account
        current_now = datetime.now(timezone.utc).isoformat()
        insert_response = supabase.table("user_profiles").insert({
            "email": reg_email,
            "tier": "Free Account",
            "messages_sent": 0,
            "window_started_at": current_now
        }).execute()
        
        if insert_response and hasattr(insert_response, 'data') and insert_response.data:
            st.session_state.user_email = reg_email
            st.session_state.user_tier = "Free Account"
            st.session_state.db_messages = 0
            st.session_state.window_started = current_now
            st.session_state.user_authenticated = True
            st.success("✅ Account created successfully!")
            st.rerun()
            return True
        else:
            st.error("❌ Failed to create account. Please try again.")
            return False
            
    except Exception as e:
        st.error(f"❌ Signup error: {str(e)}")
        return False

def check_24hr_window():
    """Check and reset 24-hour message window if expired."""
    if not st.session_state.window_started or supabase is None:
        return
    
    try:
        start_time = datetime.fromisoformat(
            st.session_state.window_started.replace('Z', '+00:00')
        )
        hours_passed = (datetime.now(timezone.utc) - start_time).total_seconds() / 3600
        
        if hours_passed >= 24:
            st.session_state.db_messages = 0
            new_window = datetime.now(timezone.utc).isoformat()
            st.session_state.window_started = new_window
            
            supabase.table("user_profiles").update({
                "messages_sent": 0,
                "window_started_at": new_window
            }).eq("email", st.session_state.user_email).execute()
            
            st.info("🔄 24-hour window reset. Message counter refreshed!")
            
    except (ValueError, TypeError):
        st.warning("⚠️ Timestamp format issue. Resetting window.")
        st.session_state.window_started = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        st.warning(f"⚠️ Window check error: {str(e)}")

def update_message_count():
    """Update message count in database."""
    if supabase is None or not st.session_state.user_email:
        return False
    
    try:
        st.session_state.db_messages += 1
        supabase.table("user_profiles").update({
            "messages_sent": st.session_state.db_messages
        }).eq("email", st.session_state.user_email).execute()
        return True
    except Exception as e:
        st.warning(f"⚠️ Could not update message count: {str(e)}")
        return False

# =====================================================================
# CONTROL PANEL & SIDEBAR
# =====================================================================
with st.sidebar:
    st.header("⚙️ Control Panel")
    
    # API Keys Section
    st.subheader("🔑 API Keys")
    gemini_key = st.text_input("Gemini API Key:", type="password", key="gemini_input", placeholder="Enter your Gemini API key")
    openai_key = st.text_input("OpenAI API Key:", type="password", key="openai_input", placeholder="Enter your OpenAI API key")
    
    st.divider()
    
    # User Account Portal
    st.header("👤 Account Portal")
    
    if supabase is None:
        st.error("⚠️ Database not configured. Check your .env file.")
        st.session_state.user_authenticated = False
    else:
        if st.session_state.user_email is None:
            # Authentication Tabs
            auth_tab1, auth_tab2 = st.tabs(["🔑 Log In", "📝 Sign Up"])
            
            # --- LOG IN TAB ---
            with auth_tab1:
                st.markdown("**Access your account**")
                login_email = st.text_input("Email:", key="login_email", placeholder="you@example.com")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔓 Access Engine", key="login_btn", use_container_width=True):
                        handle_login(login_email)
                with col2:
                    st.write("")  # Spacer
            
            # --- SIGN UP TAB ---
            with auth_tab2:
                st.markdown("**Create a new account**")
                signup_email = st.text_input("Email:", key="signup_email", placeholder="you@example.com")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✨ Create Account", key="signup_btn", use_container_width=True):
                        handle_signup(signup_email)
                with col2:
                    st.write("")  # Spacer
            
        else:
            # Authenticated User Panel
            st.success(f"✅ Connected: {st.session_state.user_email}")
            st.divider()
            
            # Check 24-hour window
            check_24hr_window()
            
            # AI Model Selection
            st.subheader("🤖 AI Model")
            model_options = ["Gemini 2.5 Flash", "Gemini 2.5 Pro", "ChatGPT 4o"]
            
            # Find current index
            current_index = model_options.index(st.session_state.ai_model) if st.session_state.ai_model in model_options else 0
            
            selected_model = st.radio(
                "Choose your AI model:",
                model_options,
                index=current_index,
                key="model_selector"
            )
            st.session_state.ai_model = selected_model
            
            st.divider()
            
            # Tier Display & Upgrade
            st.subheader("💎 Subscription Tier")
            if st.session_state.user_tier == "Premium VIP Account":
                st.success("🔥 **Premium VIP Unlocked!**")
                st.info("✨ Unlimited messages across all AI models")
            else:
                st.warning("📊 **Free Account**")
                st.info(f"📈 {st.session_state.db_messages} / 100 messages used in current 24h window")
                
                if st.button("👑 Upgrade to Premium VIP ($9.99/mo)", use_container_width=True):
                    with st.spinner("🔐 Generating secure Stripe checkout..."):
                        try:
                            checkout_session = stripe.checkout.Session.create(
                                line_items=[{
                                    'price': 'price_1TXeia15kpBKA014lFmG5yGW',
                                    'quantity': 1
                                }],
                                mode='subscription',
                                success_url='https://a12-ai.streamlit.app/?success=true',
                                cancel_url='https://a12-ai.streamlit.app/?canceled=true',
                                customer_email=st.session_state.user_email
                            )
                            st.markdown(f"[👉 **Click to Pay via Stripe**]({checkout_session.url})")
                            st.success("🎉 Stripe link generated! Click above to complete payment.")
                        except Exception as e:
                            st.error(f"❌ Stripe error: {str(e)}")
            
            st.divider()
            
            # Usage Metrics
            st.subheader("📊 Usage")
            if st.session_state.user_tier == "Free Account":
                remaining = max(0, 100 - st.session_state.db_messages)
                st.metric(
                    label="Messages Remaining (24h)",
                    value=remaining,
                    delta=f"{st.session_state.db_messages} used"
                )
            else:
                st.metric(
                    label="Messages Sent Today",
                    value=st.session_state.db_messages,
                    delta="Unlimited (Premium)"
                )
            
            st.divider()
            
            # Account Info
            st.subheader("ℹ️ Account Info")
            st.caption(f"Email: {st.session_state.user_email}")
            st.caption(f"Tier: {st.session_state.user_tier}")
            
            st.divider()
            
            # Logout
            if st.button("🚪 Log Out", use_container_width=True):
                st.session_state.user_email = None
                st.session_state.user_tier = "Free Account"
                st.session_state.db_messages = 0
                st.session_state.window_started = None
                st.session_state.messages = []
                st.session_state.user_authenticated = False
                st.rerun()

# =====================================================================
# AI MODEL FUNCTIONS
# =====================================================================
def call_gemini(user_prompt, api_key, use_pro=False):
    """Call Gemini API (Flash or Pro)."""
    try:
        client = genai.Client(api_key=api_key)
        model = 'gemini-2.5-pro' if use_pro else 'gemini-2.5-flash'
        
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config={"system_instruction": "You are the elite, premium, hyper-organized backend assistant for A12 AI. Use headings and bullet points."}
        )
        return response.text
    except Exception as e:
        return f"❌ Gemini Error: {str(e)}"

def call_openai(user_prompt, api_key):
    """Call OpenAI ChatGPT API."""
    try:
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are the elite, premium, hyper-organized backend assistant for A12 AI. Use headings and bullet points."
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            temperature=0.7,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ OpenAI Error: {str(e)}"

# =====================================================================
# CHAT INTERFACE
# =====================================================================

# Main chat container
chat_container = st.container()

with chat_container:
    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# Chat input section
if st.session_state.user_authenticated:
    st.divider()
    
    if user_prompt := st.chat_input("💬 Dispatch command...", key="chat_input"):
        # Validation checks
        if st.session_state.user_tier == "Free Account" and st.session_state.db_messages >= 100:
            st.error("🛑 **Daily Limit Reached (100/100)!**")
            st.info("💡 Upgrade to Premium VIP to bypass this 24-hour cooldown!")
        else:
            # Display user message
            with st.chat_message("user"):
                st.markdown(user_prompt)
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            
            # Determine which API to use
            model_choice = st.session_state.ai_model
            response_text = None
            
            try:
                if model_choice.startswith("Gemini"):
                    if not gemini_key:
                        with st.chat_message("assistant"):
                            st.error("⚠️ **Gemini API Key Required** - Please enter your key in the sidebar.")
                    else:
                        # Update message count
                        update_message_count()
                        
                        use_pro = "Pro" in model_choice
                        with st.chat_message("assistant"):
                            with st.spinner(f"🔄 Processing with {model_choice}..."):
                                response_text = call_gemini(user_prompt, gemini_key, use_pro)
                                st.markdown(response_text)
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response_text
                        })
                        st.rerun()
                
                elif model_choice == "ChatGPT 4o":
                    if not openai_key:
                        with st.chat_message("assistant"):
                            st.error("⚠️ **OpenAI API Key Required** - Please enter your key in the sidebar.")
                    else:
                        # Update message count
                        update_message_count()
                        
                        with st.chat_message("assistant"):
                            with st.spinner("🔄 Processing with ChatGPT 4o..."):
                                response_text = call_openai(user_prompt, openai_key)
                                st.markdown(response_text)
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response_text
                        })
                        st.rerun()
                        
            except Exception as e:
                with st.chat_message("assistant"):
                    st.error(f"❌ Chat Error: {str(e)}")
else:
    # Show login prompt if not authenticated
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("👈 **Please log in or sign up using the sidebar to start chatting!**")
        st.markdown("---")
        st.markdown("""
        ### 🎯 Getting Started:
        1. **Sign Up** with your email in the sidebar
        2. **Add your API keys** (Gemini or OpenAI)
        3. **Choose an AI model** and start chatting!
        
        ### 📊 Free Tier:
        - 100 messages per 24-hour window
        - Access to Gemini 2.5 Flash
        
        ### 👑 Premium ($9.99/mo):
        - Unlimited messages
        - Access to all models (Flash, Pro, ChatGPT 4o)
        """)
