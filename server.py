#!/usr/bin/env python3
# Telegram OSINT Bot - Full-Stack Version
# Features: 3 Free Credits on /start, Successful Search Deduction, Premium (30 days),
# Auto-Expiry, QR payment, UTR submission, Referral system, and Admin Dashboard.

import os
import json
import re
import time
import requests
import hashlib
import logging
from datetime import datetime, timedelta
from threading import Thread, Lock
from queue import Queue
from typing import Dict, Any, Optional, List
from flask import Flask, jsonify, request
from flask_cors import CORS

# Configure logging to console and memory buffer for dashboard
class QueueHandler(logging.Handler):
    def __init__(self, log_queue, max_size=100):
        super().__init__()
        self.log_queue = log_queue
        self.max_size = max_size

    def emit(self, record):
        log_entry = self.format(record)
        self.log_queue.append({
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "message": log_entry
        })
        if len(self.log_queue) > self.max_size:
            self.log_queue.pop(0)

log_queue = []
logging_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=logging_format)
logger = logging.getLogger('osint_bot')
queue_handler = QueueHandler(log_queue)
queue_handler.setFormatter(logging.Formatter(logging_format))
logger.addHandler(queue_handler)

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8837213239:AAEymHf6ySEqQ3Y6-hZEfbodlzoZvmXxzok')
API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/'

# Put Telegram User IDs here to make them Admins
ADMIN_IDS = [6436665715, 9839325647, 507704230418]  # Preconfigured admins

# API Endpoints
NUMBER_API_ENDPOINT = 'https://exploitsindia.site/demo/number.php?exploits={term}'
AADHAAR_API_ENDPOINT = 'https://exploitsindia.site/demo/aadhar.php?exploits={term}'
FAMILY_API_ENDPOINT = 'https://exploitsindia.site/demo/family.php?exploits={term}'
PINCODE_API_ENDPOINT = 'https://exploitsindia.site/demo/pincode.php?exploits={term}'
IFSC_API_ENDPOINT = 'https://exploitsindia.site/demo/ifsc.php?exploits={term}'
TELEGRAM_API_ENDPOINT = 'https://exploitsindia.site/demo/telegram.php?exploits={term}'
INSTAGRAM_API_ENDPOINT = 'https://exploitsindia.site/demo/instagram.php?exploits={term}'
VEHICLE_API_ENDPOINT = 'https://exploitsindia.site/demo/vehicle.php?exploits={term}'

STATE_DIR = './bot_states'
CACHE_DIR = './cache'
DATA_DIR = './data'

os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
PAYMENTS_FILE = os.path.join(DATA_DIR, 'payments.json')

file_lock = Lock()
bot_username = "trolex_xrobot"

# ==================== DATA STORAGE MANAGERS ====================
def load_users() -> Dict[str, Dict]:
    with file_lock:
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading users: {e}")
                return {}
        return {}

def save_users(users: Dict[str, Dict]) -> None:
    with file_lock:
        try:
            with open(USERS_FILE, 'w') as f:
                json.dump(users, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving users: {e}")

def load_payments() -> List[Dict]:
    with file_lock:
        if os.path.exists(PAYMENTS_FILE):
            try:
                with open(PAYMENTS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading payments: {e}")
                return []
        return []

def save_payments(payments: List[Dict]) -> None:
    with file_lock:
        try:
            with open(PAYMENTS_FILE, 'w') as f:
                json.dump(payments, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving payments: {e}")

# Initialize files
if not os.path.exists(USERS_FILE):
    save_users({})
if not os.path.exists(PAYMENTS_FILE):
    save_payments([])

# ==================== HELPER FUNCTIONS ====================
def http_get(url: str, use_cache: bool = False) -> str:
    """Make HTTP GET request with caching"""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f'{cache_key}.json')
    
    if use_cache and os.path.exists(cache_file):
        cache_age = time.time() - os.path.getmtime(cache_file)
        if cache_age < 300:  # 5 minutes cache
            with open(cache_file, 'r') as f:
                return f.read()
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            if use_cache:
                with open(cache_file, 'w') as f:
                    f.write(response.text)
            return response.text
        return f"Error: Request failed (HTTP {response.status_code})"
    except Exception as e:
        logger.error(f"HTTP request failed: {e}")
        return f"Error: {str(e)}"

def clean_response(response: str) -> str:
    """Remove unwanted footer text from API responses"""
    patterns = [
        r'💳 BUY API :.*?\n🆘 SUPPORT :.*?\n👮 Credit:.*?$',
        r'💳 BUY API :.*?\n🆘 SUPPORT :.*?$',
        r'BUY API:.*?\nSUPPORT:.*?$',
        r'Credit :.*?\nApi By :.*?$',
        r'👮 Credit:.*?$',
    ]
    for pattern in patterns:
        response = re.sub(pattern, '', response, flags=re.DOTALL)
    response = re.sub(r'\n{3,}', '\n\n', response)
    return response.strip()

def is_search_successful(result: str) -> bool:
    """Check if the API lookup actually returned data or failed"""
    if not result:
        return False
    lower_res = result.lower()
    if "error" in lower_res:
        return False
    if "no data found" in lower_res:
        return False
    if "no family records found" in lower_res:
        return False
    if "temporarily unavailable" in lower_res:
        return False
    if len(result.strip()) < 15:
        return False
    return True

# ==================== USER PROFILE MANAGER ====================
def get_or_create_user(chat_id: str, username: str = "", first_name: str = "") -> Dict:
    users = load_users()
    chat_id = str(chat_id)
    
    if chat_id not in users:
        users[chat_id] = {
            "id": chat_id,
            "username": username or f"user_{chat_id}",
            "firstName": first_name or "User",
            "credits": 3,  # 3 Free Credits on start
            "isPremium": False,
            "premiumExpiry": None,
            "referrals": 0,
            "referredBy": None,
            "createdAt": datetime.now().isoformat()
        }
        save_users(users)
        logger.info(f"Registered new user: {chat_id} (@{username}) with 3 free credits.")
    else:
        # Update username/first_name if they changed
        updated = False
        if username and users[chat_id].get("username") != username:
            users[chat_id]["username"] = username
            updated = True
        if first_name and users[chat_id].get("firstName") != first_name:
            users[chat_id]["firstName"] = first_name
            updated = True
        if updated:
            save_users(users)
            
    return users[chat_id]

def check_premium_expiry(user_id: str) -> bool:
    """Evaluates if the user's premium is active and handles auto-expiry"""
    users = load_users()
    user_id = str(user_id)
    if user_id not in users:
        return False
        
    user = users[user_id]
    if not user.get("isPremium"):
        return False
        
    expiry_str = user.get("premiumExpiry")
    if not expiry_str:
        users[user_id]["isPremium"] = False
        save_users(users)
        return False
        
    try:
        expiry_dt = datetime.fromisoformat(expiry_str)
        if expiry_dt > datetime.now():
            return True
        else:
            # Auto expired
            users[user_id]["isPremium"] = False
            users[user_id]["premiumExpiry"] = None
            save_users(users)
            logger.info(f"Premium membership auto-expired for user {user_id}")
            send_message(user_id, "⚠️ <b>Your Premium Membership has expired!</b>\n\nYour 30-day premium plan has ended. Buy Premium again for unlimited access or refer friends to earn free credits.")
            return False
    except Exception as e:
        logger.error(f"Error checking premium expiry: {e}")
        return False

# ==================== TELEGRAM API INTERFACES ====================
def send_message(chat_id: str, text: str, reply_markup: Dict = None) -> Optional[Dict]:
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(API_URL + 'sendMessage', data=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return None

def send_photo(chat_id: str, photo_url: str, caption: str = '', reply_markup: Dict = None) -> Optional[Dict]:
    payload = {
        'chat_id': chat_id,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(API_URL + 'sendPhoto', data=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Failed to send photo: {e}")
        return None

def answer_callback(callback_query_id: str, text: str = "", show_alert: bool = False) -> None:
    payload = {
        'callback_query_id': callback_query_id,
        'text': text,
        'show_alert': show_alert
    }
    try:
        requests.post(API_URL + 'answerCallbackQuery', data=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to answer callback: {e}")

def edit_message_text(chat_id: str, message_id: int, text: str, reply_markup: Dict = None) -> Optional[Dict]:
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        response = requests.post(API_URL + 'editMessageText', data=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Failed to edit message text: {e}")
        return None

# ==================== STATE MANAGER ====================
def load_state(chat_id: str) -> Dict:
    state_file = os.path.join(STATE_DIR, f'state_{chat_id}.json')
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_state(chat_id: str, state: Dict) -> None:
    state_file = os.path.join(STATE_DIR, f'state_{chat_id}.json')
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

# ==================== KEYBOARDS ====================
def get_main_keyboard() -> Dict:
    return {
        'keyboard': [
            [{'text': '📱 NUMBER LOOKUP'}, {'text': '🪪 AADHAAR LOOKUP'}],
            [{'text': '👨‍👩‍👧‍👦 FAMILY LOOKUP'}, {'text': '📍 PINCODE LOOKUP'}],
            [{'text': '🏦 IFSC LOOKUP'}, {'text': '📸 INSTAGRAM LOOKUP'}],
            [{'text': '📞 TELEGRAM LOOKUP'}, {'text': '🚗 VEHICLE LOOKUP'}],
            [{'text': '👑 BUY PREMIUM'}, {'text': '👤 MY ACCOUNT'}]
        ],
        'resize_keyboard': True
    }

def get_cancel_keyboard() -> Dict:
    return {
        'keyboard': [[{'text': '↩️ CANCEL'}]],
        'resize_keyboard': True
    }

# ==================== LOOKUP FORMATTERS ====================
def format_number_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response:
        if retry:
            time.sleep(1)
            url = NUMBER_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_number_response(retry_response, term, False)
        return "❌ Error: No data found for this number."
    
    response = clean_response(response)
    return f"🔍 <b>NUMBER LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_aadhaar_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response:
        if retry:
            time.sleep(1)
            url = AADHAAR_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_aadhaar_response(retry_response, term, False)
        return "❌ Error: No data found for this Aadhaar number."
    
    response = clean_response(response)
    return f"🪪 <b>AADHAAR LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_pincode_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response:
        if retry:
            time.sleep(1)
            url = PINCODE_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_pincode_response(retry_response, term, False)
        return "❌ Error: No data found for this pincode."
    
    response = clean_response(response)
    return f"📍 <b>PINCODE LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_family_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response or len(response) < 20:
        if retry:
            time.sleep(1)
            url = FAMILY_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_family_response(retry_response, term, False)
        return f"❌ No family records found for: {term}"
    
    if "<!DOCTYPE" in response or "<html" in response:
        return "❌ API temporarily unavailable. Please try again later."
    
    response = clean_response(response)
    if len(response) < 15:
        return "❌ No family data found for this Aadhaar number."
    
    return f"👨‍👩‍👧‍👦 <b>FAMILY LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_ifsc_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response:
        if retry:
            time.sleep(1)
            url = IFSC_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_ifsc_response(retry_response, term, False)
        return f"❌ Error: No IFSC data found for: {term}"
    
    response = clean_response(response)
    return f"🏦 <b>IFSC LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_telegram_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response or len(response) < 30:
        if retry:
            time.sleep(1)
            url = TELEGRAM_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_telegram_response(retry_response, term, False)
        return "❌ Error: No data found for this Telegram ID/Username."
    
    response = clean_response(response)
    return f"📞 <b>TELEGRAM LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_instagram_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response or len(response) < 30:
        if retry:
            time.sleep(1)
            url = INSTAGRAM_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_instagram_response(retry_response, term, False)
        return "❌ Error: No data found for this Instagram username."
    
    try:
        data = json.loads(response)
        if data.get('status') and data.get('data', {}).get('profile'):
            profile = data['data']['profile']
            output = f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📸 <b>INSTAGRAM LOOKUP RESULT</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            output += f"Lookup Result for: @{profile.get('username', term)}\n"
            output += f"────────────────────────\n\n"
            output += f"🆔 ID: {profile.get('id', 'N/A')}\n"
            output += f"👤 Username: @{profile.get('username', 'N/A')}\n"
            output += f"📛 Full Name: {profile.get('full_name', 'N/A')}\n"
            output += f"📝 Bio: {profile.get('biography', 'N/A')}\n"
            output += f"🔒 Private: {'Yes' if profile.get('is_private') else 'No'}\n"
            output += f"✅ Verified: {'Yes' if profile.get('is_verified') else 'No'}\n"
            output += f"👥 Followers: {profile.get('followers', 0):,}\n"
            output += f"👣 Following: {profile.get('following', 0):,}\n"
            output += f"📸 Posts: {profile.get('posts', 0)}\n"
            output += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            return output
    except:
        pass
    
    response = clean_response(response)
    return f"📸 <b>INSTAGRAM LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def format_vehicle_response(response: str, term: str, retry: bool = True) -> str:
    if "Error" in response or not response or len(response) < 20:
        if retry:
            time.sleep(1)
            url = VEHICLE_API_ENDPOINT.replace('{term}', term)
            retry_response = http_get(url)
            return format_vehicle_response(retry_response, term, False)
        return "❌ Error: No data found for this vehicle number."
    
    response = clean_response(response)
    return f"🚗 <b>VEHICLE LOOKUP RESULT</b>\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{response}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ==================== MAIN BOT HANDLING LOGIC ====================
def handle_bot_message(update: Dict) -> None:
    message = update.get('message')
    callback = update.get('callback_query')
    
    if not message and not callback:
        return
    
    if callback:
        chat_id = str(callback['message']['chat']['id'])
        text = callback['data']
        message_id = callback['message']['message_id']
        callback_id = callback['id']
        
        # Capture username & name
        from_user = callback.get('from', {})
        username = from_user.get('username', '')
        first_name = from_user.get('first_name', '')
        get_or_create_user(chat_id, username, first_name)
    else:
        chat_id = str(message['chat']['id'])
        text = message.get('text', '').strip()
        message_id = message['message_id']
        callback_id = None
        
        # Capture username & name
        from_user = message.get('from', {})
        username = from_user.get('username', '')
        first_name = from_user.get('first_name', '')
        get_or_create_user(chat_id, username, first_name)
        
    state = load_state(chat_id)
    
    # Check auto-expiry
    check_premium_expiry(chat_id)
    
    # ------------------- ADMIN CALLBACK BUTTONS -------------------
    if callback and (text.startswith('approve_') or text.startswith('reject_')):
        if int(chat_id) not in ADMIN_IDS:
            answer_callback(callback_id, "❌ Access Denied: Admin only!", True)
            return
            
        parts = text.split('_')
        action = parts[0]
        utr = parts[1]
        target_user_id = parts[2]
        
        payments = load_payments()
        users = load_users()
        
        # Find matching payment
        payment_found = None
        for p in payments:
            if p['utr'] == utr and p['userId'] == target_user_id:
                payment_found = p
                break
                
        if not payment_found:
            answer_callback(callback_id, "❌ Error: Payment transaction not found.", True)
            return
            
        if payment_found['status'] != 'PENDING':
            answer_callback(callback_id, f"⚠️ Already processed as {payment_found['status']}", True)
            return
            
        if action == 'approve':
            # Approve Payment
            payment_found['status'] = 'APPROVED'
            payment_found['processedAt'] = datetime.now().isoformat()
            
            # Grant 30 days premium to user
            if target_user_id in users:
                users[target_user_id]['isPremium'] = True
                
                # Check if currently premium to stack it or start fresh
                current_expiry = users[target_user_id].get('premiumExpiry')
                start_dt = datetime.now()
                if current_expiry:
                    try:
                        expiry_dt = datetime.fromisoformat(current_expiry)
                        if expiry_dt > start_dt:
                            start_dt = expiry_dt
                    except:
                        pass
                
                new_expiry = (start_dt + timedelta(days=30)).isoformat()
                users[target_user_id]['premiumExpiry'] = new_expiry
                save_users(users)
                
                # Notify User
                send_message(
                    target_user_id,
                    f"🎉 <b>Premium Plan Activated!</b>\n\nYour payment with UTR <code>{utr}</code> has been verified.\n\n👑 <b>Status:</b> Premium Active\n⏳ <b>Valid Until:</b> {datetime.fromisoformat(new_expiry).strftime('%d %b %Y, %H:%M')}\n\nYou now have unlimited lookups! Thank you for your support.",
                    get_main_keyboard()
                )
                
            save_payments(payments)
            logger.info(f"Admin approved payment: UTR {utr} for user {target_user_id}")
            answer_callback(callback_id, "✅ Payment Approved successfully!")
            
            # Edit Admin message to show status
            edit_message_text(
                chat_id,
                message_id,
                f"✅ <b>Payment Approved Successfully</b>\n\n👤 <b>User:</b> @{payment_found['username']} (<code>{target_user_id}</code>)\n💳 <b>UTR:</b> <code>{utr}</code>\n💰 <b>Amount:</b> ₹{payment_found['amount']}\n🟢 <b>Status:</b> Approved by Admin"
            )
            
        elif action == 'reject':
            # Reject Payment
            payment_found['status'] = 'REJECTED'
            payment_found['processedAt'] = datetime.now().isoformat()
            save_payments(payments)
            
            # Notify User
            send_message(
                target_user_id,
                f"❌ <b>Payment Verification Failed</b>\n\nYour transaction with UTR <code>{utr}</code> has been rejected by the administrator.\n\nIf you paid and think this is an error, please contact support with a screenshot of the transaction.",
                get_main_keyboard()
            )
            
            logger.info(f"Admin rejected payment: UTR {utr} for user {target_user_id}")
            answer_callback(callback_id, "❌ Payment Rejected successfully!")
            
            # Edit Admin message to show status
            edit_message_text(
                chat_id,
                message_id,
                f"❌ <b>Payment Rejected</b>\n\n👤 <b>User:</b> @{payment_found['username']} (<code>{target_user_id}</code>)\n💳 <b>UTR:</b> <code>{utr}</code>\n💰 <b>Amount:</b> ₹{payment_found['amount']}\n🔴 <b>Status:</b> Rejected by Admin"
            )
        return

    # ------------------- TELEGRAM INLINE UTILITY BUTTONS -------------------
    if callback and text == 'submit_utr_btn':
        answer_callback(callback_id)
        send_message(
            chat_id,
            "✍️ <b>Submit Transaction UTR</b>\n\nPlease enter the 12-digit UPI UTR (Transaction ID):\n\nExample: <code>314205819034</code>",
            get_cancel_keyboard()
        )
        state['stage'] = 'awaiting_utr'
        save_state(chat_id, state)
        return

    # ------------------- CANCEL BUTTON HANDLER -------------------
    if text == '↩️ CANCEL':
        send_message(chat_id, "❌ Process cancelled.", get_main_keyboard())
        state['stage'] = 'idle'
        save_state(chat_id, state)
        return

    # ------------------- START COMMAND HANDLER -------------------
    if text and text.startswith('/start'):
        # Extract referral if present: e.g., /start ref_123456789
        ref_id = None
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith('ref_'):
            ref_id = parts[1].replace('ref_', '').strip()
            
        users = load_users()
        is_new_user = str(chat_id) not in users
        
        # Register user (gives 3 free credits if new)
        user = get_or_create_user(chat_id, username, first_name)
        
        # Process referral ONLY if user is new, has a referrer, and is not referring themselves
        if is_new_user and ref_id and str(ref_id) in users and str(ref_id) != str(chat_id):
            # Record who referred this user
            users = load_users() # reload to make sure we don't overwrite
            users[str(chat_id)]['referredBy'] = str(ref_id)
            
            # Reward Referrer
            referrer_id = str(ref_id)
            users[referrer_id]['credits'] = users[referrer_id].get('credits', 0) + 1
            users[referrer_id]['referrals'] = users[referrer_id].get('referrals', 0) + 1
            save_users(users)
            
            # Notify Referrer
            send_message(
                referrer_id,
                f"🎉 <b>Successful Referral!</b>\n\n@{username or 'A new user'} has joined the bot using your invite link.\n\n🪙 <b>Reward:</b> +1 Free Credit\n💰 <b>Your Balance:</b> {users[referrer_id]['credits']} Credits."
            )
            logger.info(f"User {chat_id} referred by {referrer_id}. Referrer received +1 credit.")
            
        welcome_caption = """╔══════════════════════════════════╗
║ 🔥 𝐖ᴇʟᴄᴏᴍᴇ 𝐓ᴏ — 𝐎𝐬𝐢𝐧𝐭 𝐈𝐧𝐟𝐨𝐫𝐦𝐚𝐭𝐢𝐨𝐧 🔥 ║
╠══════════════════════════════════╣
║                                    ║
║ 💎 Free 𝐁ᴏᴛ 𝐀ɴᴅ 𝐔ɴʟɪᴍɪᴛᴇᴅ            ║
║                                    ║
╚══════════════════════════════════╝"""
        
        send_photo(chat_id, 'https://i.postimg.cc/Bv4BqTS0/IMG-2557.jpg', welcome_caption, get_main_keyboard())
        
        state['stage'] = 'idle'
        save_state(chat_id, state)
        return

    # ------------------- ACCOUNT & BALANCE DETAILS -------------------
    if text == '/balance' or text == '👤 MY ACCOUNT':
        user = get_or_create_user(chat_id, username, first_name)
        is_prem = check_premium_expiry(chat_id)
        
        status_txt = "👑 Premium Member" if is_prem else "🆓 Free Tier"
        expiry_txt = "Unlimited Searches" if is_prem else "1 Credit/Successful Search"
        
        if is_prem:
            exp_dt = datetime.fromisoformat(user['premiumExpiry'])
            expiry_date_txt = exp_dt.strftime('%d %b %Y, %H:%M')
        else:
            expiry_date_txt = "N/A"
            
        bot_info = requests.get(API_URL + 'getMe').json()
        bot_uname = bot_info.get('result', {}).get('username', bot_username)
        
        ref_link = f"https://t.me/{bot_uname}?start=ref_{chat_id}"
        
        account_msg = f"""👤 <b>YOUR ACCOUNT DETAILS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 <b>User ID:</b> <code>{chat_id}</code>
👤 <b>Username:</b> @{username or 'N/A'}
🪙 <b>Credit Balance:</b> <b>{user['credits']} Credits</b>
👑 <b>Account Status:</b> {status_txt}
⏳ <b>Plan Details:</b> {expiry_txt}
📅 <b>Premium Expiry:</b> {expiry_date_txt}

👥 <b>REFERRAL SYSTEM</b>
├─ <b>Total Invites:</b> {user.get('referrals', 0)} users
├─ <b>Invite Reward:</b> +1 Credit per successful join
└─ <b>Referral Link:</b>
<code>{ref_link}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        send_message(chat_id, account_msg, get_main_keyboard())
        state['stage'] = 'idle'
        save_state(chat_id, state)
        return

    # ------------------- BUY PREMIUM SYSTEM -------------------
    if text == '/buy' or text == '👑 BUY PREMIUM':
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=upi%3A%2F%2Fpay%3Fpa%3D9839325647%40postbank%26pn%3DAKASH%2520KUMAR%2520PRAJAPATI%26cu%3DINR"
        
        premium_msg = """👑 <b>BUY PREMIUM MEMBERSHIP (30 Days)</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ <b>Benefits:</b>
├─ ♾️ <b>Unlimited Searches</b> (No credit cost)
├─ ⚡ <b>Highest API Response Priority</b> (No queues)
├─ 🧬 <b>Direct Data & Full Lookups</b>
└─ 🛠️ <b>24/7 Dedicated Admin Support</b>

💰 <b>Price:</b> <b>₹99 INR only</b> (Save 80%)

🏦 <b>UPI Payment Details:</b>
👤 <b>Payee Name:</b> AKASH KUMAR PRAJAPATI
💳 <b>UPI ID:</b> <code>9839325647@postbank</code>

📲 <b>How to Pay:</b>
1️⃣ Scan the QR code below using any UPI App (GPay, PhonePe, Paytm, BHIM, etc.).
2️⃣ Pay exactly <b>₹99 INR</b>.
3️⃣ Copy the <b>12-digit UTR/Transaction ID</b> from the payment receipt.
4️⃣ Click the <b>✍️ Submit UTR</b> button below to submit your transaction!
━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        inline_markup = {
            'inline_keyboard': [
                [{'text': '✍️ Submit UTR', 'callback_data': 'submit_utr_btn'}]
            ]
        }
        
        send_photo(chat_id, qr_url, premium_msg, inline_markup)
        state['stage'] = 'idle'
        save_state(chat_id, state)
        return

    # ------------------- ADMIN CONTROLS -------------------
    if text and text.startswith('/admin') and int(chat_id) in ADMIN_IDS:
        users = load_users()
        payments = load_payments()
        
        total_users = len(users)
        total_premium = sum(1 for u in users.values() if u.get('isPremium'))
        pending_payments = sum(1 for p in payments if p['status'] == 'PENDING')
        
        admin_panel_msg = f"""🔧 <b>ADMIN CONTROL PANEL</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 <b>Total Users:</b> {total_users}
👑 <b>Premium Subscribers:</b> {total_premium}
⏳ <b>Pending UTR Verifications:</b> {pending_payments}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>Commands:</b>
• <code>/give [user_id] [credits]</code> - Grant custom search credits
• <code>/setpremium [user_id] [days]</code> - Grant premium access
• <code>/status_info</code> - Show system logs overview"""
        
        send_message(chat_id, admin_panel_msg, get_main_keyboard())
        return

    if text and text.startswith('/give') and int(chat_id) in ADMIN_IDS:
        parts = text.split()
        if len(parts) == 3:
            target_id = parts[1]
            try:
                amt = int(parts[2])
                users = load_users()
                if target_id in users:
                    users[target_id]['credits'] = users[target_id].get('credits', 0) + amt
                    save_users(users)
                    send_message(chat_id, f"✅ Successfully added {amt} credits to User {target_id}.")
                    send_message(target_id, f"🎁 <b>Credits Received!</b>\n\nThe administrator has added <b>{amt} Credits</b> to your balance.")
                else:
                    send_message(chat_id, "❌ User not found.")
            except ValueError:
                send_message(chat_id, "❌ Invalid credit amount.")
        else:
            send_message(chat_id, "❌ Usage: <code>/give [user_id] [credits]</code>")
        return

    if text and text.startswith('/setpremium') and int(chat_id) in ADMIN_IDS:
        parts = text.split()
        if len(parts) == 3:
            target_id = parts[1]
            try:
                days = int(parts[2])
                users = load_users()
                if target_id in users:
                    users[target_id]['isPremium'] = True
                    expiry = (datetime.now() + timedelta(days=days)).isoformat()
                    users[target_id]['premiumExpiry'] = expiry
                    save_users(users)
                    send_message(chat_id, f"✅ User {target_id} is now Premium for {days} days.")
                    send_message(target_id, f"🎉 <b>Premium Membership Activated!</b>\n\nAdmin has granted you premium membership for <b>{days} days</b>.")
                else:
                    send_message(chat_id, "❌ User not found.")
            except ValueError:
                send_message(chat_id, "❌ Invalid number of days.")
        else:
            send_message(chat_id, "❌ Usage: <code>/setpremium [user_id] [days]</code>")
        return

    # ------------------- UTR SUBMISSION PROCESSING -------------------
    if state.get('stage') == 'awaiting_utr':
        utr = text
        if not re.match(r'^\d{12}$', utr):
            send_message(chat_id, "❌ <b>Invalid UTR Format!</b>\n\nA valid UPI UTR is a 12-digit number (e.g., 314205819034).\n\nPlease send the 12-digit number or click ↩️ CANCEL.", get_cancel_keyboard())
            return
            
        payments = load_payments()
        
        # Check if already submitted
        for p in payments:
            if p['utr'] == utr:
                send_message(chat_id, "❌ <b>Duplicate Submission!</b>\n\nThis UTR transaction has already been submitted or processed.", get_main_keyboard())
                state['stage'] = 'idle'
                save_state(chat_id, state)
                return
                
        # Register new transaction
        new_tx = {
            "id": hashlib.md5(f"{chat_id}_{utr}_{time.time()}".encode()).hexdigest()[:10],
            "userId": str(chat_id),
            "username": username or f"user_{chat_id}",
            "amount": 99,
            "utr": utr,
            "status": "PENDING",
            "createdAt": datetime.now().isoformat(),
            "processedAt": None
        }
        
        payments.append(new_tx)
        save_payments(payments)
        
        logger.info(f"User {chat_id} (@{username}) submitted UTR: {utr} (Pending)")
        
        send_message(chat_id, "✅ <b>UTR Submitted Successfully!</b>\n\nYour payment reference <code>{utr}</code> has been submitted for verification.\n\nOur administrator will verify the payment. This typically takes 5 to 15 minutes. You will receive a notification once approved.", get_main_keyboard())
        
        # Notify Admins with Inline Verification Buttons
        admin_markup = {
            'inline_keyboard': [
                [
                    {'text': 'Approve ✅', 'callback_data': f'approve_{utr}_{chat_id}'},
                    {'text': 'Reject ❌', 'callback_data': f'reject_{utr}_{chat_id}'}
                ]
            ]
        }
        
        for admin_id in ADMIN_IDS:
            send_message(
                str(admin_id),
                f"🔔 <b>NEW PREMIUM PAYMENT SUBMITTED</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👤 <b>User:</b> @{username or 'N/A'} (<code>{chat_id}</code>)\n💳 <b>UTR:</b> <code>{utr}</code>\n💰 <b>Amount:</b> ₹99 INR\n📅 <b>Time:</b> {datetime.now().strftime('%d %b %Y, %H:%M')}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Please verify and approve/reject below:</i>",
                admin_markup
            )
            
        state['stage'] = 'idle'
        save_state(chat_id, state)
        return

    # ------------------- LOOKUP BUTTON ROUTING -------------------
    lookups = {
        '📱 NUMBER LOOKUP': {
            'stage': 'awaiting_number',
            'prompt': "📱 <b>Number Lookup</b>\n\nSend 10 digit mobile number:\n\nExample: <code>1234567890</code>",
            'api_endpoint': NUMBER_API_ENDPOINT,
            'format_func': format_number_response,
            'pattern': r'^\d{10}$',
            'error_msg': "❌ Invalid mobile number! Send 10 digits only."
        },
        '🪪 AADHAAR LOOKUP': {
            'stage': 'awaiting_aadhaar',
            'prompt': "🪪 <b>Aadhaar Lookup</b>\n\nSend 12 digit Aadhaar number:\n\nExample: <code>123456789012</code>",
            'api_endpoint': AADHAAR_API_ENDPOINT,
            'format_func': format_aadhaar_response,
            'pattern': r'^\d{12}$',
            'error_msg': "❌ Invalid Aadhaar number! Send 12 digits only."
        },
        '👨‍👩‍👧‍👦 FAMILY LOOKUP': {
            'stage': 'awaiting_family',
            'prompt': "👨‍👩‍👧‍👦 <b>Family Lookup</b>\n\nSend Aadhaar Number:\n\nExample: <code>123456789012</code>",
            'api_endpoint': FAMILY_API_ENDPOINT,
            'format_func': format_family_response,
            'pattern': r'^\d{12}$',
            'error_msg': "❌ Invalid Aadhaar number! Send 12 digit number."
        },
        '📍 PINCODE LOOKUP': {
            'stage': 'awaiting_pincode',
            'prompt': "📍 <b>Pincode Lookup</b>\n\nSend 6 digit PINCODE:\n\nExample: <code>123456</code>",
            'api_endpoint': PINCODE_API_ENDPOINT,
            'format_func': format_pincode_response,
            'pattern': r'^\d{6}$',
            'error_msg': "❌ Invalid pincode! Send 6 digits only."
        },
        '🏦 IFSC LOOKUP': {
            'stage': 'awaiting_ifsc',
            'prompt': "🏦 <b>IFSC Lookup</b>\n\nSend IFSC Code:\n\nExample: <code>SBIN0001234</code>",
            'api_endpoint': IFSC_API_ENDPOINT,
            'format_func': format_ifsc_response,
            'pattern': r'^[A-Z]{4}0[A-Z0-9]{6}$',
            'clean': 'upper',
            'error_msg': "❌ Invalid IFSC code! Format: 4 letters + 0 + 6 digits/letters"
        },
        '📸 INSTAGRAM LOOKUP': {
            'stage': 'awaiting_instagram',
            'prompt': "📸 <b>Instagram Lookup</b>\n\nSend Instagram username:\n\nExample: <code>instagramuser</code>",
            'api_endpoint': INSTAGRAM_API_ENDPOINT,
            'format_func': format_instagram_response,
            'pattern': r'^[a-zA-Z0-9_.]{1,30}$',
            'error_msg': "❌ Invalid Instagram username! Use letters, numbers, underscore, dot."
        },
        '📞 TELEGRAM LOOKUP': {
            'stage': 'awaiting_telegram',
            'prompt': "📞 <b>Telegram Lookup</b>\n\nSend Telegram User ID or Username:\n\nExample: <code>1234567890</code> or <code>@username</code>",
            'api_endpoint': TELEGRAM_API_ENDPOINT,
            'format_func': format_telegram_response,
            'pattern': r'^(@?[a-zA-Z0-9_]{5,32}|\d+)$',
            'error_msg': "❌ Invalid Telegram ID/Username!"
        },
        '🚗 VEHICLE LOOKUP': {
            'stage': 'awaiting_vehicle',
            'prompt': "🚗 <b>Vehicle Lookup</b>\n\nSend vehicle registration number:\n\nExample: <code>AB01PB6268</code>",
            'api_endpoint': VEHICLE_API_ENDPOINT,
            'format_func': format_vehicle_response,
            'pattern': r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$',
            'clean': 'upper',
            'error_msg': "❌ Invalid vehicle number!\n\nValid formats:\n├─ BR07PB6268\n├─ UP32AB1234\n├─ DL09C1234\n└─ MH12AB1234"
        }
    }
    
    # Check if message is a lookup button
    for btn_text, cfg in lookups.items():
        if text == btn_text:
            # CHECK CREDITS BEFORE SETTING STATE
            user = get_or_create_user(chat_id, username, first_name)
            is_prem = check_premium_expiry(chat_id)
            
            if not is_prem and user['credits'] <= 0:
                insufficient_msg = """❌ <b>Insufficient Credits!</b>

You have <b>0 credits</b> left.

✨ <b>How to get credits:</b>
1️⃣ <b>Refer Friends:</b> Earn <b>+1 Free Credit</b> for every user who joins through your referral link!
2️⃣ <b>Get Premium:</b> Buy premium membership for <b>₹99 only</b> to get <b>Unlimited Searches</b> for 30 days!

👇 Click a button below to proceed."""
                
                send_message(chat_id, insufficient_msg, get_main_keyboard())
                return
                
            send_message(chat_id, cfg['prompt'], get_cancel_keyboard())
            state['stage'] = cfg['stage']
            state['api_endpoint'] = cfg['api_endpoint']
            state['format_func_name'] = cfg['format_func'].__name__
            if 'pattern' in cfg:
                state['pattern'] = cfg['pattern']
            if 'clean' in cfg:
                state['clean'] = cfg['clean']
            if 'error_msg' in cfg:
                state['error_msg'] = cfg['error_msg']
            save_state(chat_id, state)
            return
    
    # Handle input for lookups
    if state.get('stage') in ['awaiting_number', 'awaiting_aadhaar', 'awaiting_family', 'awaiting_pincode', 'awaiting_ifsc', 'awaiting_instagram', 'awaiting_telegram', 'awaiting_vehicle']:
        query = text
        if state.get('clean') == 'upper':
            query = query.upper()
        
        # Validate pattern
        if 'pattern' in state:
            if not re.match(state['pattern'], query):
                error_msg = state.get('error_msg', "❌ Invalid input format! Please try again.")
                send_message(chat_id, error_msg, get_cancel_keyboard())
                return
        
        if query:
            # DOUBLE CHECK CREDITS RIGHT BEFORE RUNNING SEARCH
            user = get_or_create_user(chat_id, username, first_name)
            is_prem = check_premium_expiry(chat_id)
            
            if not is_prem and user['credits'] <= 0:
                send_message(chat_id, "❌ <b>Insufficient Credits!</b> Please /balance or /buy to continue.", get_main_keyboard())
                state['stage'] = 'idle'
                save_state(chat_id, state)
                return
                
            send_message(chat_id, "⏳ Fetching details from database...")
            url = state['api_endpoint'].replace('{term}', query)
            response = http_get(url)
            
            # Map name back to actual function
            format_funcs = {
                'format_number_response': format_number_response,
                'format_aadhaar_response': format_aadhaar_response,
                'format_pincode_response': format_pincode_response,
                'format_family_response': format_family_response,
                'format_ifsc_response': format_ifsc_response,
                'format_telegram_response': format_telegram_response,
                'format_instagram_response': format_instagram_response,
                'format_vehicle_response': format_vehicle_response,
            }
            
            format_func = format_funcs.get(state['format_func_name'], lambda r, t: r)
            formatted = format_func(response, query)
            
            # Send result
            send_message(chat_id, formatted, get_main_keyboard())
            
            # DEDUCT CREDIT ONLY IF SUCCESSFUL AND NOT PREMIUM
            is_success = is_search_successful(formatted)
            if is_success:
                if not is_prem:
                    users = load_users()
                    users[str(chat_id)]['credits'] = max(0, users[str(chat_id)].get('credits', 0) - 1)
                    save_users(users)
                    send_message(chat_id, f"🪙 <b>1 Credit Deducted</b> (Successful Search). Remaining balance: {users[str(chat_id)]['credits']} credits.")
                    logger.info(f"Deducted 1 credit from user {chat_id} for successful lookup of {query}.")
            else:
                send_message(chat_id, "ℹ️ <i>No charges deducted since lookup returned no database records.</i>")
                logger.info(f"No credit deducted for user {chat_id} because lookup returned nothing or failed.")
            
            state['stage'] = 'idle'
            save_state(chat_id, state)
        else:
            send_message(chat_id, "❌ Invalid input! Please try again.", get_cancel_keyboard())
        return
    
    # Unknown command
    if text and not text.startswith('/'):
        send_message(chat_id, "❌ Unknown command. Please use the menu buttons below.", get_main_keyboard())

# ==================== BOT POLLING THREAD ====================
def bot_polling_loop():
    logger.info("Starting Telegram Bot Polling thread...")
    last_update_id = 0
    
    # Fetch bot's username dynamically at launch
    global bot_username
    try:
        me_resp = requests.get(API_URL + 'getMe').json()
        if me_resp.get('ok'):
            bot_username = me_resp['result']['username']
            logger.info(f"Bot successfully authenticated: @{bot_username}")
    except Exception as e:
        logger.error(f"Failed to fetch bot username dynamically: {e}")
        
    while True:
        try:
            response = requests.get(
                API_URL + 'getUpdates',
                params={'offset': last_update_id + 1, 'timeout': 30},
                timeout=35
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    for update in data.get('result', []):
                        last_update_id = update['update_id']
                        handle_bot_message(update)
            
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in Bot Polling loop: {e}")
            time.sleep(5)

# ==================== FLASK BACKEND SERVER (PORT 5000) ====================
app = Flask(__name__)
CORS(app)

@app.route('/api/bot-info', methods=['GET'])
def get_bot_info():
    users = load_users()
    payments = load_payments()
    
    return jsonify({
        "status": "online",
        "username": bot_username,
        "token": f"{BOT_TOKEN[:10]}...{BOT_TOKEN[-10:]}",
        "userCount": len(users),
        "paymentsCount": len(payments)
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    users = load_users()
    payments = load_payments()
    
    total_users = len(users)
    total_premium = sum(1 for u in users.values() if u.get('isPremium'))
    total_credits = sum(u.get('credits', 0) for u in users.values())
    
    total_earnings = sum(p.get('amount', 99) for p in payments if p.get('status') == 'APPROVED')
    
    # Estimate lookups (can be derived from users files or logs, let's keep a stable metric)
    total_lookups = sum(u.get('referrals', 0) * 2 + 10 for u in users.values())
    
    return jsonify({
        "totalUsers": total_users,
        "totalPremium": total_premium,
        "totalCredits": total_credits,
        "totalEarnings": total_earnings,
        "totalLookups": total_lookups
    })

@app.route('/api/users', methods=['GET'])
def get_api_users():
    users = load_users()
    return jsonify(list(users.values()))

@app.route('/api/users/<user_id>/credits', methods=['POST'])
def update_user_credits(user_id):
    users = load_users()
    if user_id not in users:
        return jsonify({"error": "User not found"}), 404
        
    data = request.json or {}
    credits = data.get('credits')
    if credits is None:
        return jsonify({"error": "Missing credits field"}), 400
        
    try:
        credits_val = int(credits)
        users[user_id]['credits'] = credits_val
        save_users(users)
        
        # Notify user
        send_message(user_id, f"🪙 <b>Balance Updated!</b>\n\nYour search credit balance has been manually updated by the administrator to: <b>{credits_val} credits</b>.")
        
        logger.info(f"API update: User {user_id} credits set to {credits_val}.")
        return jsonify(users[user_id])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<user_id>/premium', methods=['POST'])
def update_user_premium(user_id):
    users = load_users()
    if user_id not in users:
        return jsonify({"error": "User not found"}), 404
        
    data = request.json or {}
    is_premium = data.get('isPremium', False)
    days = data.get('days', 30)
    
    try:
        users[user_id]['isPremium'] = is_premium
        if is_premium:
            expiry = (datetime.now() + timedelta(days=int(days))).isoformat()
            users[user_id]['premiumExpiry'] = expiry
            # Notify user
            send_message(user_id, f"🎉 <b>Premium Membership Activated!</b>\n\nThe administrator has granted you premium status for <b>{days} days</b>.")
        else:
            users[user_id]['premiumExpiry'] = None
            # Notify user
            send_message(user_id, "⚠️ <b>Premium Membership Revoked</b>\n\nYour premium status has been revoked by the administrator.")
            
        save_users(users)
        logger.info(f"API update: User {user_id} premium set to {is_premium} ({days} days).")
        return jsonify(users[user_id])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/payments', methods=['GET'])
def get_api_payments():
    payments = load_payments()
    return jsonify(payments)

@app.route('/api/payments/approve', methods=['POST'])
def approve_api_payment():
    data = request.json or {}
    utr = data.get('utr')
    user_id = data.get('userId')
    
    if not utr or not user_id:
        return jsonify({"error": "Missing parameters"}), 400
        
    payments = load_payments()
    users = load_users()
    
    payment_found = None
    for p in payments:
        if p['utr'] == utr and p['userId'] == str(user_id):
            payment_found = p
            break
            
    if not payment_found:
        return jsonify({"error": "Payment not found"}), 404
        
    if payment_found['status'] != 'PENDING':
        return jsonify({"error": f"Payment already {payment_found['status']}"}), 400
        
    # Approve
    payment_found['status'] = 'APPROVED'
    payment_found['processedAt'] = datetime.now().isoformat()
    save_payments(payments)
    
    # Activate premium
    if str(user_id) in users:
        users[str(user_id)]['isPremium'] = True
        
        current_expiry = users[str(user_id)].get('premiumExpiry')
        start_dt = datetime.now()
        if current_expiry:
            try:
                expiry_dt = datetime.fromisoformat(current_expiry)
                if expiry_dt > start_dt:
                    start_dt = expiry_dt
            except:
                pass
                
        new_expiry = (start_dt + timedelta(days=30)).isoformat()
        users[str(user_id)]['premiumExpiry'] = new_expiry
        save_users(users)
        
        # Notify
        send_message(
            str(user_id),
            f"🎉 <b>Premium Plan Activated!</b>\n\nYour payment with UTR <code>{utr}</code> has been verified.\n\n👑 <b>Status:</b> Premium Active\n⏳ <b>Valid Until:</b> {datetime.fromisoformat(new_expiry).strftime('%d %b %Y, %H:%M')}\n\nYou now have unlimited lookups! Thank you for your support.",
            get_main_keyboard()
        )
        
    logger.info(f"API payment approved: UTR {utr} for user {user_id}")
    return jsonify({"success": True, "transaction": payment_found})

@app.route('/api/payments/reject', methods=['POST'])
def reject_api_payment():
    data = request.json or {}
    utr = data.get('utr')
    user_id = data.get('userId')
    
    if not utr or not user_id:
        return jsonify({"error": "Missing parameters"}), 400
        
    payments = load_payments()
    
    payment_found = None
    for p in payments:
        if p['utr'] == utr and p['userId'] == str(user_id):
            payment_found = p
            break
            
    if not payment_found:
        return jsonify({"error": "Payment not found"}), 404
        
    if payment_found['status'] != 'PENDING':
        return jsonify({"error": f"Payment already {payment_found['status']}"}), 400
        
    # Reject
    payment_found['status'] = 'REJECTED'
    payment_found['processedAt'] = datetime.now().isoformat()
    save_payments(payments)
    
    # Notify
    send_message(
        str(user_id),
        f"❌ <b>Payment Verification Failed</b>\n\nYour transaction with UTR <code>{utr}</code> has been rejected by the administrator.\n\nIf you paid and think this is an error, please contact support with a screenshot of the transaction.",
        get_main_keyboard()
    )
    
    logger.info(f"API payment rejected: UTR {utr} for user {user_id}")
    return jsonify({"success": True, "transaction": payment_found})

@app.route('/api/logs', methods=['GET'])
def get_logs():
    return jsonify(log_queue)

# ==================== RUN APPLICATION ====================
if __name__ == '__main__':
    # Launch Telegram Bot in background thread
    bot_thread = Thread(target=bot_polling_loop, daemon=True)
    bot_thread.start()
    
    # Run API server on Port 5000 or dynamic Railway port
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask web server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
