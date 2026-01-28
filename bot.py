import logging
import json
import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ContextTypes
)

# --- ENVIRONMENT VARIABLES (RENDER PAR SET KAREIN) ---
API_TOKEN = os.environ.get('API_TOKEN')
# Admin ID ko int mein convert karna zaroori hai
ADMIN_USER_ID = int(os.environ.get('ADMIN_USER_ID', 0))
CHANNEL_ID = os.environ.get('CHANNEL_ID', '@Scammerawarealert')

# --- FLASK SETUP (RENDER KO JAGANE KE LIYE) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running 24/7!", 200

def run_flask():
    # Render khud PORT provide karta hai
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG & STATES ---
USERS_FILE = 'users.json'
ASK_USERNAME, ASK_DESCRIPTION, ASK_AMOUNT, ASK_PROOF_LINK = range(4)

user_states = {}
reports = {}

# --- DATABASE FUNCTIONS ---
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(list(users), f)
    except Exception as e:
        logger.error(f"Save error: {e}")

all_users = load_users()

# --- BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return
    user_id = update.effective_user.id
    
    if user_id not in all_users:
        all_users.add(user_id)
        save_users(all_users)

    user_states[user_id] = ASK_USERNAME
    reports[user_id] = {} 
    
    await update.effective_message.reply_text(
        "Welcome to Scammer Report Bot! 👮\n\n"
        "Step 1: Send the Scammer's @Username (or name):"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_id = update.effective_user.id
    text = update.message.text
    state = user_states.get(user_id)

    if state is None: return

    if state == ASK_USERNAME:
        reports[user_id]['scammer'] = text
        user_states[user_id] = ASK_DESCRIPTION
        await update.message.reply_text("Step 2: Describe the scam incident in detail:")

    elif state == ASK_DESCRIPTION:
        reports[user_id]['description'] = text
        user_states[user_id] = ASK_AMOUNT
        await update.message.reply_text("Step 3: Enter the Scammed Amount:")

    elif state == ASK_AMOUNT:
        reports[user_id]['amount'] = text
        user_states[user_id] = ASK_PROOF_LINK
        await update.message.reply_text("Step 4: Send the Proof Link (Telegram channel/msg link):")

    elif state == ASK_PROOF_LINK:
        if not (text.startswith("http") or text.startswith("t.me")):
            await update.message.reply_text("❌ Invalid link! Send a valid URL (https://... or t.me/...)")
            return
        reports[user_id]['proof_link'] = text
        await submit_to_admin(update, context)

async def submit_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    report = reports.get(user_id)
    if not report: return

    admin_caption = (
        f"📩 *New Scam Report Submitted*\n\n"
        f"👤 *Reporter:* [User Link](tg://user?id={user_id})\n"
        f"🕵️ *Scammer:* {report['scammer']}\n"
        f"💰 *Amount:* {report['amount']}\n"
        f"📝 *Info:* {report['description']}"
    )

    keyboard = [
        [InlineKeyboardButton("🔍 View Proofs", url=report['proof_link'])],
        [InlineKeyboardButton("✅ Accept", callback_data=f"approve_{user_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]
    ]
    
    await context.bot.send_message(ADMIN_USER_ID, admin_caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ Report submitted! Waiting for Admin review.")
    user_states.pop(user_id, None)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, r_user_id = query.data.split('_')
    r_user_id = int(r_user_id)
    report = reports.get(r_user_id)

    if action == "approve":
        if not report:
            await query.answer("Error: Report data not found in memory.", show_alert=True)
            return

        channel_post = (
            f"➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
            f"🚨 *SCAMMER ALERT*\n"
            f"➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
            f"🕵️ *Scammer:* {report['scammer']}\n"
            f"💰 *Scammed Amount:* {report['amount']}\n"
            f"📝 *Details:* {report['description']}\n"
        )
        btns = [
            [InlineKeyboardButton("🖼️ View Proofs", url=report['proof_link'])],
            [InlineKeyboardButton("👤 Reported By", url=f"tg://user?id={r_user_id}")]
        ]
        await context.bot.send_message(CHANNEL_ID, channel_post, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(btns))
        
        try: await context.bot.send_message(r_user_id, "✅ Your report was approved and posted!")
        except: pass
        await query.edit_message_text(f"{query.message.text}\n\n✅ *Status: Approved*", parse_mode='Markdown')
        
    elif action == "reject":
        try: await context.bot.send_message(r_user_id, "❌ Your report was rejected by Admin.")
        except: pass
        await query.edit_message_text(f"{query.message.text}\n\n❌ *Status: Rejected*", parse_mode='Markdown')

    reports.pop(r_user_id, None)
    await query.answer()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    await update.message.reply_text(f"📊 Total Users: {len(all_users)}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID or not context.args: return
    msg = " ".join(context.args)
    count = 0
    for u_id in list(all_users):
        try:
            await context.bot.send_message(u_id, msg)
            count += 1
        except: pass
    await update.message.reply_text(f"📢 Broadcast sent to {count} users.")

# --- MAIN ---
def main():
    if not API_TOKEN:
        print("Error: API_TOKEN environment variable not set.")
        return

    # Start Flask Health Check in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    application = ApplicationBuilder().token(API_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    print("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
