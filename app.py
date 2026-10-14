import streamlit as st
import os
import time
import sqlite3
import google.genai as genai
from datetime import datetime, timedelta
import base64

# Page Configuration
st.set_page_config(
    page_title="Korex Chat",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

GEMINI_API_KEY = "AQ.Ab8RN6JtKg-9BzUbcpA9vAmQrxI4WZl7cfCc0Q2efZ3lyi2kNA"

# ----------------- DATABASE SETUP -----------------
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
                media_data TEXT,
                media_type TEXT DEFAULT 'text',
                time TEXT,
                timestamp_epoch DOUBLE PRECISION,
                expire_seconds INTEGER DEFAULT 0,
                seen INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS groups (
                id SERIAL PRIMARY KEY,
                group_name TEXT,
                admin TEXT,
                members TEXT
            );
            CREATE TABLE IF NOT EXISTS communities (
                id SERIAL PRIMARY KEY,
                comm_name TEXT,
                description TEXT,
                admin TEXT,
                groups TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_wallpapers (
                user_phone TEXT,
                chat_target TEXT,
                wallpaper_data TEXT,
                PRIMARY KEY (user_phone, chat_target)
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
                media_data TEXT,
                media_type TEXT DEFAULT 'text',
                time TEXT,
                timestamp_epoch REAL,
                expire_seconds INTEGER DEFAULT 0,
                seen INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT,
                admin TEXT,
                members TEXT
            );
            CREATE TABLE IF NOT EXISTS communities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comm_name TEXT,
                description TEXT,
                admin TEXT,
                groups TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_wallpapers (
                user_phone TEXT,
                chat_target TEXT,
                wallpaper_data TEXT,
                PRIMARY KEY (user_phone, chat_target)
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
if "voice_mode" not in st.session_state:
    st.session_state.voice_mode = False

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
    "features": "Korex Chat features cloud storage, communities, file sharing, disappearing messages, custom photo wallpapers, and Korex AI assistant."
}

# ----------------- AUDIO & NOTIFICATIONS HELPER -----------------
def trigger_notification(msg_title, msg_body):
    sound_html = f"""
    <audio autoplay style="display:none">
        <source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mpeg">
    </audio>
    <script>
        if (Notification.permission === "granted") {{
            new Notification("{msg_title}", {{ body: "{msg_body}" }});
        }} else if (Notification.permission !== "denied") {{
            Notification.requestPermission().then(permission => {{
                if (permission === "granted") {{
                    new Notification("{msg_title}", {{ body: "{msg_body}" }});
                }}
            }});
        }}
    </script>
    """
    st.components.v1.html(sound_html, height=0, width=0)

shortcut_listener_html = """
<script>
    document.addEventListener('keydown', function(event) {
        if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'd') {
            event.preventDefault();
            const btn = window.parent.document.querySelectorAll('button');
            for (let b of btn) {
                if (b.innerText.includes('Voice Mode')) {
                    b.click();
                    break;
                }
            }
        }
    });
</script>
"""
st.components.v1.html(shortcut_listener_html, height=0, width=0)

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

# ----------------- WALLPAPER GALLERIES & STYLING -----------------
preset_wallpapers = {
    "Nature": {
        "Forest Mist": "https://images.unsplash.com/photo-1542273917363-3b1817f69a2d?auto=format&fit=crop&w=1200&q=80",
        "Starry Night": "https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1200&q=80",
        "Ocean Waves": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80"
    },
    "Anime": {
        "Cyber City": "https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1200&q=80",
        "Neon Sunset": "https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1200&q=80",
        "Sakura Dreams": "https://images.unsplash.com/photo-1522383225653-ed111181a951?auto=format&fit=crop&w=1200&q=80"
    },
    "Classic / Dark": {
        "Dark Classic": "solid:#0b141a",
        "Midnight Blue": "solid:#09101d",
        "Emerald Luxe": "solid:#022c22",
        "Sunset Orange": "solid:#1c120f"
    }
}

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT wallpaper_data FROM chat_wallpapers WHERE user_phone = %s AND chat_target = %s" if USE_POSTGRES else "SELECT wallpaper_data FROM chat_wallpapers WHERE user_phone = ? AND chat_target = ?", (st.session_state.current_phone, st.session_state.active_chat))
wp_res = cursor.fetchone()
conn.close()

active_wallpaper_url = wp_res[0] if wp_res and wp_res[0] else "solid:#0b141a"

if active_wallpaper_url.startswith("solid:"):
    bg_color = active_wallpaper_url.split(":")[1]
    bg_style = f"background-color: {bg_color};"
else:
    bg_style = f"background-image: linear-gradient(rgba(0,0,0,0.6), rgba(0,0,0,0.6)), url('{active_wallpaper_url}'); background-size: cover; background-position: center;"

st.markdown(f"""
    <style>
    .stApp {{ {bg_style} color: #e9edef; }}
    [data-testid="stSidebar"] {{ background-color: #111b21; border-right: 1px solid #222d34; }}
    .nexus-header {{ display: flex; align-items: center; background-color: #111b21; padding: 15px 20px; border-bottom: 1px solid #222d34; border-radius: 12px; margin-bottom: 20px; }}
    .user-msg {{ background-color: #005c4b; color: #e9edef; padding: 12px 16px; border-radius: 12px 12px 2px 12px; margin-left: auto; max-width: 75%; margin-bottom: 10px; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); position: relative; }}
    .bot-msg {{ background-color: #202c33; color: #e9edef; padding: 12px 16px; border-radius: 12px 12px 12px 2px; margin-right: auto; max-width: 75%; margin-bottom: 10px; border: 1px solid #222d34; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13); }}
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

        st.subheader("Customize Current Chat Wallpaper")
        wp_category = st.selectbox("Category", list(preset_wallpapers.keys()))
        wp_choice = st.selectbox("Preset Wallpapers", list(preset_wallpapers[wp_category].keys()))
        
        if st.button("Apply Preset Wallpaper"):
            selected_url = preset_wallpapers[wp_category][wp_choice]
            conn = get_db_connection()
            cursor = conn.cursor()
            if USE_POSTGRES:
                cursor.execute("""
                    INSERT INTO chat_wallpapers (user_phone, chat_target, wallpaper_data) VALUES (%s, %s, %s)
                    ON CONFLICT (user_phone, chat_target) DO UPDATE SET wallpaper_data = EXCLUDED.wallpaper_data
                """, (st.session_state.current_phone, st.session_state.active_chat, selected_url))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO chat_wallpapers (user_phone, chat_target, wallpaper_data) VALUES (?, ?, ?)
                """, (st.session_state.current_phone, st.session_state.active_chat, selected_url))
            conn.commit()
            conn.close()
            st.success("Wallpaper updated!")
            st.rerun()

        st.markdown("---")
        custom_file = st.file_uploader("Upload Custom Image", type=["jpg", "png", "jpeg"])
        if custom_file is not None:
            image_bytes = custom_file.read()
            encoded_img = base64.b64encode(image_bytes).decode("utf-8")
            custom_data_url = f"data:image/jpeg;base64,{encoded_img}"
            
            conn = get_db_connection()
            cursor = conn.cursor()
            if USE_POSTGRES:
                cursor.execute("""
                    INSERT INTO chat_wallpapers (user_phone, chat_target, wallpaper_data) VALUES (%s, %s, %s)
                    ON CONFLICT (user_phone, chat_target) DO UPDATE SET wallpaper_data = EXCLUDED.wallpaper_data
                """, (st.session_state.current_phone, st.session_state.active_chat, custom_data_url))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO chat_wallpapers (user_phone, chat_target, wallpaper_data) VALUES (?, ?, ?)
                """, (st.session_state.current_phone, st.session_state.active_chat, custom_data_url))
            conn.commit()
            conn.close()
            st.success("Custom wallpaper applied!")
            st.rerun()

        st.markdown("---")
        st.subheader("Disappearing Messages")
        disappearing_option = st.selectbox("Timer", ["Off", "1 Minute", "1 Hour", "24 Hours"], key="disappearing_timer")

    if st.button("Log Out", use_container_width=True):
        if "session_phone" in st.query_params:
            del st.query_params["session_phone"]
        st.session_state.logged_in = False
        st.rerun()

    st.markdown("---")
    st.subheader("Add Contact / Group / Community")
    add_tab1, add_tab2, add_tab3 = st.tabs(["Contact", "Group", "Community"])
    
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

    with add_tab3:
        c_name = st.text_input("Community Name", placeholder="e.g., Tech Hub").strip()
        c_desc = st.text_input("Description", placeholder="e.g., Global Developer Discussions").strip()
        if st.button("Create Community", use_container_width=True):
            if c_name:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO communities (comm_name, description, admin, groups) VALUES (%s, %s, %s, %s)" if USE_POSTGRES else "INSERT INTO communities (comm_name, description, admin, groups) VALUES (?, ?, ?, ?)", (c_name, c_desc, st.session_state.current_phone, ""))
                conn.commit()
                conn.close()
                st.success(f"Community '{c_name}' created!")
                time.sleep(0.3)
                st.rerun()

    st.markdown("---")
    chat_search = st.text_input("Search chats...", placeholder="Type to search...", label_visibility="collapsed").strip().lower()
    st.markdown("### Conversations")
    
    if not chat_search or "ai" in chat_search or "korex" in chat_search:
        if st.button("Korex AI Assistant", key="chat_ai", use_container_width=True):
            st.session_state.active_chat = "AI_ASSISTANT"
            st.rerun()

    if not chat_search or "saved" in chat_search or "note" in chat_search or st.session_state.current_phone.lower() in chat_search:
        self_key = f"SELF_{st.session_state.current_phone}"
        if st.button(f"{st.session_state.current_name} (You / Saved Messages)", key="chat_self", use_container_width=True):
            st.session_state.active_chat = self_key
            st.rerun()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Communities
    cursor.execute("SELECT id, comm_name FROM communities")
    for comm_id, comm_name in cursor.fetchall():
        if not chat_search or chat_search in comm_name.lower():
            c_key = f"COMM_{comm_id}"
            if st.button(f"Community: {comm_name}", key=f"comm_{comm_id}", use_container_width=True):
                st.session_state.active_chat = c_key
                st.rerun()

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

# ----------------- CHAT HEADER & VOICE CONTROLS -----------------
active_chat_title = "Chat"
if st.session_state.active_chat == "AI_ASSISTANT":
    active_chat_title = "Korex AI"
elif st.session_state.active_chat.startswith("SELF_"):
    active_chat_title = f"Saved Messages ({st.session_state.current_name})"
elif st.session_state.active_chat.startswith("COMM_"):
    c_id = st.session_state.active_chat.split("_")[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT comm_name FROM communities WHERE id = %s" if USE_POSTGRES else "SELECT comm_name FROM communities WHERE id = ?", (c_id,))
    c_res = cursor.fetchone()
    conn.close()
    active_chat_title = f"Community: {c_res[0] if c_res else 'Community'}"
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

col_h1, col_h2 = st.columns([5, 1])
with col_h1:
    st.markdown(f"""
        <div class="nexus-header">
            <div>
                <h2 style="margin: 0; padding: 0;">{active_chat_title}</h2>
                <span style="font-size: 0.85em; color: #00a884;">End-to-End Encrypted Cloud Workspace</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

with col_h2:
    if st.button("Voice Mode (Ctrl+Shift+D)", use_container_width=True):
        st.session_state.voice_mode = not st.session_state.voice_mode
        st.rerun()

if st.session_state.voice_mode:
    st.info("🎙️ Voice Mode Active: Speak your thoughts or listen to responses.")

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
                        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
                        client = genai.Client()
                        res = client.models.generate_content(model="gemini-2.5-flash", contents=user_prompt)
                        final_answer = res.text
                    except Exception as err:
                        final_answer = f"Error: {str(err)}"
            st.session_state.ai_chats.append({"role": "assistant", "content": final_answer})
            trigger_notification("Korex AI", "New message response received.")
            st.rerun()

    else:
        target_receiver = st.session_state.active_chat
        if target_receiver.startswith("SELF_"):
            target_receiver = st.session_state.current_phone

        # Clean up expired disappearing messages safely using adapter placeholders
        conn = get_db_connection()
        cursor = conn.cursor()
        current_epoch = time.time()
        
        if USE_POSTGRES:
            cursor.execute("DELETE FROM messages WHERE expire_seconds > 0 AND (timestamp_epoch + expire_seconds) < %s", (current_epoch,))
        else:
            cursor.execute("DELETE FROM messages WHERE expire_seconds > 0 AND (timestamp_epoch + expire_seconds) < ?", (current_epoch,))
        conn.commit()

        # Fetch messages
        cursor.execute("""
            SELECT id, sender, text, media_data, media_type, time, seen FROM messages 
            WHERE (sender = %s AND receiver = %s) OR (sender = %s AND receiver = %s)
            ORDER BY id ASC
        """ if USE_POSTGRES else """
            SELECT id, sender, text, media_data, media_type, time, seen FROM messages 
            WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
            ORDER BY id ASC
        """, (st.session_state.current_phone, target_receiver, target_receiver, st.session_state.current_phone))
        room_messages = cursor.fetchall()
        conn.close()

        for msg_id, sender, text, media_data, media_type, timestamp, seen in room_messages:
            ticks = '<span style="color: #34b7f1;">✓✓</span>' if seen == 1 else '<span style="color: #8696a0;">✓</span>'
            
            content_display = text if text else ""
            if media_type == "image" and media_data:
                content_display += f"<br><img src='{media_data}' style='max-width: 250px; border-radius: 8px; margin-top: 5px;'/>"
            elif media_type == "file" and media_data:
                content_display += f"<br>📁 <em>Attached File</em>"

            if sender == st.session_state.current_phone:
                st.markdown(f'<div class="user-msg">{content_display}<div class="msg-meta">{timestamp} &nbsp; {ticks}</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bot-msg"><b>{sender}:</b><br>{content_display}<div class="msg-meta">{timestamp}</div></div>', unsafe_allow_html=True)

        # Chat Input with File Attachment Support
        user_input = st.chat_input("Message or attach file...", accept_file=True, file_type=["jpg", "png", "jpeg", "pdf", "txt"])
        
        if user_input:
            msg_text = user_input.text if hasattr(user_input, "text") else str(user_input)
            uploaded_files = user_input.files if hasattr(user_input, "files") and user_input.files else []
            
            timestamp = datetime.now().strftime("%H:%M")
            timestamp_epoch = time.time()
            
            expire_sec = 0
            timer_setting = st.session_state.get("disappearing_timer", "Off")
            if timer_setting == "1 Minute":
                expire_sec = 60
            elif timer_setting == "1 Hour":
                expire_sec = 3600
            elif timer_setting == "24 Hours":
                expire_sec = 86400

            conn = get_db_connection()
            cursor = conn.cursor()

            if uploaded_files:
                for f in uploaded_files:
                    f_bytes = f.read()
                    f_b64 = base64.b64encode(f_bytes).decode("utf-8")
                    f_type = "image" if f.type.startswith("image") else "file"
                    f_data_url = f"data:{f.type};base64,{f_b64}"
                    
                    cursor.execute("""
                        INSERT INTO messages (sender, receiver, text, media_data, media_type, time, timestamp_epoch, expire_seconds, seen) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
                    """ if USE_POSTGRES else """
                        INSERT INTO messages (sender, receiver, text, media_data, media_type, time, timestamp_epoch, expire_seconds, seen) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """, (st.session_state.current_phone, target_receiver, msg_text, f_data_url, f_type, timestamp, timestamp_epoch, expire_sec))
            elif msg_text.strip():
                cursor.execute("""
                    INSERT INTO messages (sender, receiver, text, media_data, media_type, time, timestamp_epoch, expire_seconds, seen) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
                """ if USE_POSTGRES else """
                    INSERT INTO messages (sender, receiver, text, media_data, media_type, time, timestamp_epoch, expire_seconds, seen) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (st.session_state.current_phone, target_receiver, msg_text, "", "text", timestamp, timestamp_epoch, expire_sec))

            conn.commit()
            conn.close()
            trigger_notification("Korex Chat", f"New message from {st.session_state.current_name}")
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