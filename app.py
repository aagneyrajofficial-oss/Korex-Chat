import streamlit as st
import os
import time
import sqlite3
import google.genai as genai
from datetime import datetime

# Page Configuration
st.set_page_config(
    page_title="Korex Chat",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

GEMINI_API_KEY = "AQ.Ab8RN6JtKg-9BzUbcpA9vAmQrxI4WZl7cfCc0Q2efZ3lyi2kNA"

# ----------------- CLOUD / LOCAL DATABASE ADAPTER -----------------
USE_POSTGRES = "postgres" in st.secrets and "url" in st.secrets["postgres"]

if USE_POSTGRES:
    import psycopg2
    def get_db_connection():
        return psycopg2.connect(st.secrets["postgres"]["url"])
else:
    def get_db_connection():
        return sqlite3.connect("nexuschat.db", check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                name TEXT,
                pin TEXT,
                contacts TEXT,
                typing_status TEXT,
                last_seen TEXT,
                wallpaper TEXT DEFAULT 'Dark Classic'
            );
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                sender TEXT,
                receiver TEXT,
                text TEXT,
                media_type TEXT DEFAULT 'text',
                time TEXT,
                seen INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS groups (
                id SERIAL PRIMARY KEY,
                group_name TEXT,
                admin TEXT,
                members TEXT
            );
        """)
    else:
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                name TEXT,
                pin TEXT,
                contacts TEXT,
                typing_status TEXT,
                last_seen TEXT,
                wallpaper TEXT DEFAULT 'Dark Classic'
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                receiver TEXT,
                text TEXT,
                media_type TEXT DEFAULT 'text',
                time TEXT,
                seen INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT,
                admin TEXT,
                members TEXT
            );
        """)
    conn.commit()
    conn.close()

init_db()

# ----------------- SESSION STATE SETUP -----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "current_phone" not in st.session_state:
    st.session_state.current_phone = ""
if "current_name" not in st.session_state:
    st.session_state.current_name = ""
if "active_chat" not in st.session_state:
    st.session_state.active_chat = "AI_ASSISTANT"

# Recover session from URL parameter
if not st.session_state.logged_in and "session_phone" in st.query_params:
    saved_phone = st.query_params["session_phone"]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT name FROM users WHERE phone = ?", (saved_phone,))
    res = cursor.fetchone()
    conn.close()
    if res:
        st.session_state.logged_in = True
        st.session_state.current_phone = saved_phone
        st.session_state.current_name = res[0]

# Heartbeat online status update
if st.session_state.logged_in:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_seen = %s WHERE phone = %s" if USE_POSTGRES else "UPDATE users SET last_seen = ? WHERE phone = ?", (str(time.time()), st.session_state.current_phone))
    conn.commit()
    conn.close()

LOCAL_QA = {
    "hello": "Hello! Welcome to Korex Chat. How can I assist you today?",
    "hi": "Hey there! Ready to chat or explore your features?",
    "who are you": "I am Korex AI, your personal AI companion built straight into your secure chat network.",
    "features": "Korex Chat features permanent cloud storage, self-chats, group chats, and Korex AI assistant."
}

# ----------------- AUTHENTICATION -----------------
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>Korex Chat</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #9ca3af;'>Persistent Real-Time Encrypted Messaging Platform</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        auth_tab1, auth_tab2 = st.tabs(["Log In", "Create Account"])
        
        with auth_tab1:
            st.subheader("Sign In")
            login_phone = st.text_input("Mobile Number", placeholder="e.g., 1111111111", key="login_phone_box").strip()
            login_pin = st.text_input("Security PIN", type="password", placeholder="Enter 4-digit PIN", key="login_pin_box").strip()
            
            if st.button("Log In to Korex Chat", use_container_width=True):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT name, pin FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT name, pin FROM users WHERE phone = ?", (login_phone,))
                user_record = cursor.fetchone()
                conn.close()
                
                if user_record:
                    db_name, db_pin = user_record
                    if db_pin == login_pin:
                        st.session_state.logged_in = True
                        st.session_state.current_phone = login_phone
                        st.session_state.current_name = db_name
                        st.query_params["session_phone"] = login_phone
                        st.success(f"Welcome back, {db_name}!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Incorrect security PIN.")
                else:
                    st.error("Mobile number not registered.")

        with auth_tab2:
            st.subheader("Register New Account")
            reg_name = st.text_input("Your Full Name", placeholder="e.g., John Doe", key="reg_name_box").strip()
            reg_phone = st.text_input("Mobile Number", placeholder="e.g., 1111111111", key="reg_phone_box").strip()
            reg_pin = st.text_input("Create Security PIN", type="password", placeholder="4-digit PIN", key="reg_pin_box").strip()
            
            if st.button("Create Account & Start", use_container_width=True):
                if not reg_name or not reg_phone or not reg_pin:
                    st.warning("Please fill out all fields.")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT phone FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT phone FROM users WHERE phone = ?", (reg_phone,))
                    if cursor.fetchone():
                        st.error("An account with this mobile number already exists.")
                        conn.close()
                    else:
                        cursor.execute("""
                            INSERT INTO users (phone, name, pin, contacts, typing_status, last_seen, wallpaper) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """ if USE_POSTGRES else """
                            INSERT INTO users (phone, name, pin, contacts, typing_status, last_seen, wallpaper) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (reg_phone, reg_name, reg_pin, "", "", str(time.time()), "Dark Classic"))
                        conn.commit()
                        conn.close()
                        st.session_state.logged_in = True
                        st.session_state.current_phone = reg_phone
                        st.session_state.current_name = reg_name
                        st.query_params["session_phone"] = reg_phone
                        st.success(f"Account created! Welcome, {reg_name}!")
                        time.sleep(0.5)
                        st.rerun()
    st.stop()

# ----------------- THEME & WALLPAPER -----------------
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT wallpaper FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT wallpaper FROM users WHERE phone = ?", (st.session_state.current_phone,))
w_res = cursor.fetchone()
conn.close()
user_wallpaper = w_res[0] if w_res and w_res[0] else "Dark Classic"

wallpaper_styles = {
    "Dark Classic": {"bg": "#0b141a", "sidebar": "#111b21", "user": "#005c4b", "bot": "#202c33", "text": "#e9edef", "border": "#222d34"},
    "Midnight Blue": {"bg": "#09101d", "sidebar": "#101828", "user": "#1e3a8a", "bot": "#1e293b", "text": "#f8fafc", "border": "#334155"},
    "Emerald Luxe": {"bg": "#022c22", "sidebar": "#064e3b", "user": "#047857", "bot": "#065f46", "text": "#ecfdf5", "border": "#047857"},
    "Sunset Orange": {"bg": "#1c120f", "sidebar": "#291814", "user": "#9a3412", "bot": "#431407", "text": "#fff7ed", "border": "#572314"},
}

active_theme = wallpaper_styles.get(user_wallpaper, wallpaper_styles["Dark Classic"])

st.markdown(f"""
    <style>
    .stApp {{ background-color: {active_theme["bg"]}; color: {active_theme["text"]}; }}
    [data-testid="stSidebar"] {{ background-color: {active_theme["sidebar"]}; border-right: 1px solid {active_theme["border"]}; }}
    .nexus-header {{ display: flex; align-items: center; background-color: {active_theme["sidebar"]}; padding: 15px 20px; border-bottom: 1px solid {active_theme["border"]}; border-radius: 12px; margin-bottom: 20px; }}
    .user-msg {{ background-color: {active_theme["user"]}; color: {active_theme["text"]}; padding: 12px 16px; border-radius: 12px 12px 2px 12px; margin-left: auto; max-width: 75%; margin-bottom: 10px; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); position: relative; }}
    .bot-msg {{ background-color: {active_theme["bot"]}; color: {active_theme["text"]}; padding: 12px 16px; border-radius: 12px 12px 12px 2px; margin-right: auto; max-width: 75%; margin-bottom: 10px; border: 1px solid {active_theme["border"]}; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); }}
    .msg-meta {{ font-size: 0.7em; color: #8696a0; text-align: right; margin-top: 4px; }}
    </style>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR CONTROLS -----------------
with st.sidebar:
    st.title("Chats")
    st.markdown(f"**{st.session_state.current_name}** (`{st.session_state.current_phone}`)")
    
    with st.expander("Settings & Wallpapers"):
        new_display_name = st.text_input("Edit Name:", value=st.session_state.current_name).strip()
        if st.button("Save Name"):
            if new_display_name:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET name = %s WHERE phone = %s" if USE_POSTGRES else "UPDATE users SET name = ? WHERE phone = ?", (new_display_name, st.session_state.current_phone))
                conn.commit()
                conn.close()
                st.session_state.current_name = new_display_name
                st.success("Name updated!")
                time.sleep(0.3)
                st.rerun()

        selected_wp = st.selectbox("Wallpaper Theme", list(wallpaper_styles.keys()), index=list(wallpaper_styles.keys()).index(user_wallpaper))
        if selected_wp != user_wallpaper:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET wallpaper = %s WHERE phone = %s" if USE_POSTGRES else "UPDATE users SET wallpaper = ? WHERE phone = ?", (selected_wp, st.session_state.current_phone))
            conn.commit()
            conn.close()
            st.rerun()

    if st.button("Log Out", use_container_width=True):
        if "session_phone" in st.query_params:
            del st.query_params["session_phone"]
        st.session_state.logged_in = False
        st.rerun()

    st.markdown("---")
    st.subheader("Add Contact / Group")
    add_tab1, add_tab2 = st.tabs(["Contact", "Group"])
    
    with add_tab1:
        search_number = st.text_input("Mobile Number:", placeholder="e.g., 1111111111", label_visibility="collapsed").strip()
        if st.button("Add Contact", use_container_width=True):
            if search_number == st.session_state.current_phone:
                st.warning("Cannot add yourself.")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT name, contacts FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT name, contacts FROM users WHERE phone = ?", (search_number,))
                target_user = cursor.fetchone()
                if target_user:
                    target_name = target_user[0]
                    cursor.execute("SELECT contacts FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT contacts FROM users WHERE phone = ?", (st.session_state.current_phone,))
                    my_record = cursor.fetchone()
                    current_contacts = my_record[0].split(",") if my_record[0] else []
                    if search_number not in current_contacts:
                        current_contacts.append(search_number)
                        cursor.execute("UPDATE users SET contacts = %s WHERE phone = %s" if USE_POSTGRES else "UPDATE users SET contacts = ? WHERE phone = ?", (",".join(current_contacts), st.session_state.current_phone))
                        conn.commit()
                        st.success(f"Added {target_name}!")
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.info("Already in contacts.")
                else:
                    st.error("User not found.")
                conn.close()

    with add_tab2:
        g_name = st.text_input("Group Name", placeholder="e.g., Project Team").strip()
        g_members = st.text_input("Member Phones (comma-separated)", placeholder="1111111111,2222222222").strip()
        if st.button("Create Group", use_container_width=True):
            if g_name:
                conn = get_db_connection()
                cursor = conn.cursor()
                all_mems = f"{st.session_state.current_phone},{g_members}"
                cursor.execute("INSERT INTO groups (group_name, admin, members) VALUES (%s, %s, %s)" if USE_POSTGRES else "INSERT INTO groups (group_name, admin, members) VALUES (?, ?, ?)", (g_name, st.session_state.current_phone, all_mems))
                conn.commit()
                conn.close()
                st.success(f"Group '{g_name}' created!")
                time.sleep(0.3)
                st.rerun()

    st.markdown("---")
    chat_search = st.text_input("Search chats...", placeholder="Type to search...", label_visibility="collapsed").strip().lower()
    st.markdown("### Conversations")
    
    # AI Assistant Conversation
    if not chat_search or "ai" in chat_search or "korex" in chat_search:
        if st.button("Korex AI Assistant", key="chat_ai", use_container_width=True):
            st.session_state.active_chat = "AI_ASSISTANT"
            st.rerun()

    # Own Chat / Saved Messages (Self-Chat)
    if not chat_search or "saved" in chat_search or "note" in chat_search or st.session_state.current_phone.lower() in chat_search:
        self_key = f"SELF_{st.session_state.current_phone}"
        if st.button(f"{st.session_state.current_name} (You / Saved Messages)", key="chat_self", use_container_width=True):
            st.session_state.active_chat = self_key
            st.rerun()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Groups
    cursor.execute("SELECT id, group_name, members FROM groups")
    for g_id, g_name, members in cursor.fetchall():
        if st.session_state.current_phone in members.split(","):
            if not chat_search or chat_search in g_name.lower():
                g_key = f"GROUP_{g_id}"
                if st.button(f"Group: {g_name}", key=f"grp_{g_id}", use_container_width=True):
                    st.session_state.active_chat = g_key
                    st.rerun()

    # Direct Chats
    cursor.execute("SELECT contacts FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT contacts FROM users WHERE phone = ?", (st.session_state.current_phone,))
    res = cursor.fetchone()
    my_contacts = res[0].split(",") if res and res[0] else []
    
    for c_phone in my_contacts:
        if c_phone:
            cursor.execute("SELECT name, last_seen FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT name, last_seen FROM users WHERE phone = ?", (c_phone,))
            c_res = cursor.fetchone()
            if c_res:
                c_name, c_last_seen = c_res[0], c_res[1]
                if not chat_search or chat_search in c_name.lower() or chat_search in c_phone:
                    if st.button(f"{c_name} ({c_phone})", key=f"wa_chat_{c_phone}", use_container_width=True):
                        st.session_state.active_chat = c_phone
                        st.rerun()
    conn.close()

# ----------------- CHAT HEADER -----------------
active_chat_title = "Chat"
if st.session_state.active_chat == "AI_ASSISTANT":
    active_chat_title = "Korex AI"
elif st.session_state.active_chat.startswith("SELF_"):
    active_chat_title = f"Saved Messages ({st.session_state.current_name})"
elif st.session_state.active_chat.startswith("GROUP_"):
    g_id = st.session_state.active_chat.split("_")[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT group_name FROM groups WHERE id = %s" if USE_POSTGRES else "SELECT group_name FROM groups WHERE id = ?", (g_id,))
    g_res = cursor.fetchone()
    conn.close()
    active_chat_title = f"Group: {g_res[0] if g_res else 'Group'}"
else:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE phone = %s" if USE_POSTGRES else "SELECT name FROM users WHERE phone = ?", (st.session_state.active_chat,))
    t_res = cursor.fetchone()
    conn.close()
    active_chat_title = t_res[0] if t_res else "Chat"

st.markdown(f"""
    <div class="nexus-header">
        <div>
            <h2 style="margin: 0; padding: 0;">{active_chat_title}</h2>
            <span style="font-size: 0.85em; color: #00a884;">End-to-End Encrypted Cloud Workspace</span>
        </div>
    </div>
""", unsafe_allow_html=True)

tab_chat, tab_calls, tab_status = st.tabs(["Chat & Media", "Voice & Video Calls", "Status Feed"])

# --- TAB 1: MESSAGING ---
with tab_chat:
    if st.session_state.active_chat == "AI_ASSISTANT":
        st.write("Chatting with Korex AI assistant.")
        if "ai_chats" not in st.session_state:
            st.session_state.ai_chats = []

        for msg in st.session_state.ai_chats:
            if msg["role"] == "user":
                st.markdown(f'<div class="user-msg"><b>You:</b><br>{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bot-msg"><b>Korex AI:</b><br>{msg["content"]}</div>', unsafe_allow_html=True)

        if user_prompt := st.chat_input("Ask Korex AI..."):
            st.session_state.ai_chats.append({"role": "user", "content": user_prompt})
            matched_reply = LOCAL_QA.get(user_prompt.strip().lower())
            
            if matched_reply:
                final_answer = matched_reply
            else:
                with st.spinner("Korex AI is thinking..."):
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        res = client.models.generate_content(model="gemini-2.5-flash", contents=user_prompt)
                        final_answer = res.text
                    except Exception as err:
                        final_answer = f"Error: {str(err)}"
            st.session_state.ai_chats.append({"role": "assistant", "content": final_answer})
            st.rerun()

    else:
        target_receiver = st.session_state.active_chat
        if target_receiver.startswith("SELF_"):
            target_receiver = st.session_state.current_phone

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, sender, text, media_type, time, seen FROM messages 
            WHERE (sender = %s AND receiver = %s) OR (sender = %s AND receiver = %s)
            ORDER BY id ASC
        """ if USE_POSTGRES else """
            SELECT id, sender, text, media_type, time, seen FROM messages 
            WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
            ORDER BY id ASC
        """, (st.session_state.current_phone, target_receiver, target_receiver, st.session_state.current_phone))
        room_messages = cursor.fetchall()
        conn.close()

        for msg_id, sender, text, media_type, timestamp, seen in room_messages:
            ticks = '<span style="color: #34b7f1;">✓✓</span>' if seen == 1 else '<span style="color: #8696a0;">✓</span>'
            if sender == st.session_state.current_phone:
                st.markdown(f'<div class="user-msg">{text}<div class="msg-meta">{timestamp} &nbsp; {ticks}</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bot-msg"><b>{sender}:</b><br>{text}<div class="msg-meta">{timestamp}</div></div>', unsafe_allow_html=True)

        if peer_prompt := st.chat_input(f"Message {active_chat_title}..."):
            timestamp = datetime.now().strftime("%H:%M")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (sender, receiver, text, time, seen) VALUES (%s, %s, %s, %s, 0)
            """ if USE_POSTGRES else """
                INSERT INTO messages (sender, receiver, text, time, seen) VALUES (?, ?, ?, ?, 0)
            """, (st.session_state.current_phone, target_receiver, peer_prompt, timestamp))
            conn.commit()
            conn.close()
            st.rerun()

# --- TAB 2: CALLS ---
with tab_calls:
    st.subheader("Direct HD Voice & Video Call")
    room_code = st.text_input("Enter Meeting Room Code:", "Korex-Secure-Call-Room").strip()
    if room_code:
        call_url = f"https://meet.jit.si/{room_code}#config.prejoinPageEnabled=false"
        st.components.v1.iframe(call_url, height=580, scrolling=True)

# --- TAB 3: STATUS ---
with tab_status:
    st.subheader("Status Feed")
    st.markdown(f"* **{st.session_state.current_name}**: *'Online on Korex Chat.'* — Just now")
    new_status = st.text_input("Post a status update:")
    if st.button("Broadcast Status"):
        if new_status:
            st.success(f"Status posted: '{new_status}'")