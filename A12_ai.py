import streamlit as st
from google import genai
import openai
from postgrest import PostgrestClient  # Changed from AsyncPostgrestClient
import os
from dotenv import load_dotenv
import stripe
from datetime import datetime, timezone

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
        st.error("⚠️ Missing Supabase credentials in environment variables.")
        return None
    
    try:
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY
        }
        # Using synchronous client to avoid async/await issues
        client = PostgrestClient(f"{SUPABASE_URL}/rest/v1", headers=headers)
        return client
    except Exception as e:
        st.error(f"⚠️ Database connection failed: {e}")
        return None

supabase = init_supabase()

# =====================================================================
# PAGE SETUP & BRANDING
# =====================================================================
st.set_page_config(page_title="A12 AI Hub", page_icon="⚡", layout="centered")
st.markdown("<h1 style='text-align: center; color: #1e3c72;'>⚡ A12 AI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888888;'>The Hyper-Organized, Personal Premium AI Agent Engine</p>", unsafe_allow_html=True)
st.markdown("---")

# =====================================================================
# SESSION STATE INITIALIZATION
# =====================================================================
def init_session_state():
    """Initialize all required session state variables."""
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
        st.session_state.user_tier = "Free Account"
        st.session_state.db_messages = 0
        st.session_state.window_started = None
        st.session_state.ai_model = "Gemini 2.5 Flash"  # Default model
        st.session_state.messages = []

init_session_state()

# =====================================================================
# AUTHENTICATION FUNCTIONS
# =====================================================================
def handle_login(login_email):
    """Handle user login with proper error handling."""
    if not login_email or "@" not in login_email:
        st.error("❌ Please enter a valid email address.")
        return False
    
    try:
        # Query the database
        prof = supabase.table("user_profiles").select("*").eq("email", login_email).execute()
        
        # Check if data exists
        if prof.data and len(prof.data) > 0:
            user_data = prof.data[0]
            st.session_state.user_email = user_data.get("email")
            st.session_state.user_tier = user_data.get("tier", "Free Account")
            st.session_state.db_messages = user_data.get("messages_sent", 0)
            st.session_state.window_started = user_data.get("window_started_at")
            st.success("✅ Access Granted!")
            st.rerun()
            return True
        else:
            st.error("❌ Account not found. Please sign up.")
            return False
            
    except AttributeError as e:
        st.error(f"❌ Database error: Response format issue. {str(e)}")
        return False
    except Exception as e:
        st.error(f"❌ Login error: {str(e)}")
        return False

def handle_signup(reg_email):
    """Handle user signup with proper error handling."""
    if not reg_email or "@" not in reg_email:
        st.error("❌ Please enter a valid email address.")
        return False
    
    try:
        # Check if email already exists
        existing = supabase.table("user_profiles").select("*").eq("email", reg_email).execute()
        
        if existing.data and len(existing.data) > 0:
            st.error("❌ Email already registered.")
            return False
        
        # Create new account
        current_now = datetime.now(timezone.utc).isoformat()
        new_user = supabase.table("user_profiles").insert({
            "email": reg_email,
            "tier": "Free Account",
            "messages_sent": 0,
            "window_started_at": current_now
        }).execute()
        
        if new_user.data:
            st.session_state.user_email = reg_email
            st.session_state.user_tier = "Free Account"
            st.session_state.db_messages = 0
            st.session_state.window_started = current_now
            st.success("✅ Account created successfully!")
            st.rerun()
            return True
        else:
            st.error("❌ Failed to create account. Please try again.")
            return False
            
    except AttributeError as e:
        st.error(f"❌ Database error: Response format issue. {str(e)}")
        return False
    except Exception as e:
        st.error(f"❌ Signup error: {str(e)}")
        return False

def check_24hr_window():
    """Check and reset 24-hour message window if expired."""
    if not st.session_state.window_started:
        return
    
    try:
        start_time = datetime.fromisoformat(
            st.session_state.window_started.replace('Z', '+00:00')
        )
        hours_passed = (datetime.now(timezone.utc) - start_time).total_seconds() / 3600
        
        if hours_passed >= 24:
            st.session_state.db_messages = 0
            st.session_state.window_started = datetime.now(timezone.utc).isoformat()
            supabase.table("user_profiles").update({
                "messages_sent": 0,
                "window_started_at": st.session_state.window_started
            }).eq("email", st.session_state.user_email).execute()
            st.info("🔄 24-hour window reset. Message counter refreshed!")
            
    except ValueError:
        st.warning("⚠️ Timestamp format issue. Resetting window.")
        st.session_state.window_started = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        st.warning(f"⚠️ Window check error: {str(e)}")

# =====================================================================
# CONTROL PANEL & SIDEBAR
# =====================================================================
with st.sidebar:
    st.header("⚙️ Control Panel")
    
    # API Keys Section
    st.subheader("🔑 API Keys")
    gemini_key = st.text_input("Gemini API Key:", type="password", key="gemini_input")
    openai_key = st.text_input("OpenAI API Key:", type="password", key="openai_input")
    
    st.divider()
    
    # User Account Portal
    st.header("👤 Account Portal")
    
    if supabase is None:
        st.error("⚠️ Database not configured.")
        user_authenticated = False
    else:
        if st.session_state.user_email is None:
            # Authentication Tabs
            auth_tab1, auth_tab2 = st.tabs(["🔑 Log In", "📝 Sign Up"])
            
            # --- LOG IN TAB ---
            with auth_tab1:
                st.markdown("**Access your account**")
                login_email = st.text_input("Email:", key="login_email", placeholder="you@example.com")
                login_col1, login_col2 = st.columns(2)
                with login_col1:
                    if st.button("Access Engine", key="login_btn", use_container_width=True):
                        handle_login(login_email)
            
            # --- SIGN UP TAB ---
            with auth_tab2:
                st.markdown("**Create a new account**")
                signup_email = st.text_input("Email:", key="signup_email", placeholder="you@example.com")
                signup_col1, signup_col2 = st.columns(2)
                with signup_col1:
                    if st.button("Create Account", key="signup_btn", use_container_width=True):
                        handle_signup(signup_email)
            
            user_authenticated = False
        
        else:
            # Authenticated User Panel
            st.success(f"✅ Connected: {st.session_state.user_email}")
            st.divider()
            
            # Check 24-hour window
            check_24hr_window()
            
            # AI Model Selection
            st.subheader("🤖 AI Model")
            selected_model = st.radio(
                "Choose your AI model:",
                ["Gemini 2.5 Flash", "Gemini 2.5 Pro", "ChatGPT 4o"],
                key="model_selector"
            )
            st.session_state.ai_model = selected_model
            
            st.divider()
            
            # Tier Display & Upgrade
            st.subheader("💎 Subscription Tier")
            if st.session_state.user_tier == "Premium VIP Account":
                st.success("🔥 **Premium VIP Unlocked!**")
                st.info(f"Unlimited messages across all AI models")
            else:
                st.warning("📊 **Free Account**")
                st.info("100 messages per 24-hour window")
                
                if st.button("👑 Upgrade to Premium VIP ($9.99/mo)", use_container_width=True):
                    with st.spinner("Generating secure Stripe checkout..."):
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
                        except Exception as e:
                            st.error(f"❌ Stripe error: {str(e)}")
            
            st.divider()
            
            # Usage Metrics
            st.subheader("📊 Usage")
            st.metric(
                label="Messages (24h window)",
                value=f"{st.session_state.db_messages} / 100",
                delta="Free tier limit"
            )
            
            st.divider()
            
            # Logout
            if st.button("🚪 Log Out", use_container_width=True):
                st.session_state.user_email = None
                st.session_state.user_tier = "Free Account"
                st.session_state.db_messages = 0
                st.session_state.window_started = None
                st.session_state.messages = []
                st.rerun()
            
            user_authenticated = True

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
SYSTEM_INSTRUCTION = "You are the elite, premium, hyper-organized backend assistant for A12 AI. Use headings and bullet points."

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if user_prompt := st.chat_input("Dispatch command..."):
    
    # Validation checks
    if not user_authenticated:
        st.error("🛑 **Access Prohibited**: Log in first.")
    elif st.session_state.user_tier == "Free Account" and st.session_state.db_messages >= 100:
        st.error("🛑 **Daily Limit Reached (100/100)!**")
        st.info("Upgrade to Premium VIP to bypass this 24-hour cooldown!")
    else:
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_prompt)
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        
        # Determine which API to use
        model_choice = st.session_state.ai_model
        
        if model_choice.startswith("Gemini"):
            if not gemini_key:
                with st.chat_message("assistant"):
                    st.error("⚠️ Gemini API Key Required in Sidebar.")
            else:
                try:
                    st.session_state.db_messages += 1
                    supabase.table("user_profiles").update({
                        "messages_sent": st.session_state.db_messages
                    }).eq("email", st.session_state.user_email).execute()
                    
                    use_pro = "Pro" in model_choice
                    with st.chat_message("assistant"):
                        with st.spinner("Processing with Gemini..."):
                            response_text = call_gemini(user_prompt, gemini_key, use_pro)
                            st.markdown(response_text)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": response_text
                            })
                    st.rerun()
                except Exception as e:
                    with st.chat_message("assistant"):
                        st.error(f"❌ Chat Error: {str(e)}")
        
        elif model_choice == "ChatGPT 4o":
            if not openai_key:
                with st.chat_message("assistant"):
                    st.error("⚠️ OpenAI API Key Required in Sidebar.")
            else:
                try:
                    st.session_state.db_messages += 1
                    supabase.table("user_profiles").update({
                        "messages_sent": st.session_state.db_messages
                    }).eq("email", st.session_state.user_email).execute()
                    
                    with st.chat_message("assistant"):
                        with st.spinner("Processing with ChatGPT..."):
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
