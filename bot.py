"""
BOT SCRIPT v2
-------------
New in this version:
1. Auto-indexes new PDFs posted to the channel (no need to re-run Colab)
2. Smarter search: ignores extra spaces/punctuation, matches multi-word queries better
3. Requires users to join @booksharepdfs before they can search

Requires:
- BOT_TOKEN set as an environment variable (from BotFather)
- books.db present in the same folder (built by indexer.py)
- The bot must be an ADMIN of the channel
"""

import os
import re
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_USERNAME = "@booksharepdfs"
CHANNEL_HANDLE = "booksharepdfs"  # without @, used for membership checks
DB_FILE = "books.db"


# ---------- Database helpers ----------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            message_id INTEGER PRIMARY KEY,
            title TEXT,
            tags TEXT,
            caption TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def normalize(text):
    """Lowercase, collapse extra whitespace, strip punctuation noise."""
    text = text or ""
    text = text.lower()
    text = re.sub(r"[^\w\s#]", " ", text)  # drop punctuation except # and word chars
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_tags(text):
    return " ".join(re.findall(r"#(\w+)", text or "")).lower()


def extract_title(text):
    if not text:
        return ""
    cleaned = re.sub(r"#\w+", "", text).strip()
    return cleaned.split("\n")[0][:200]


def add_or_update_book(message_id, caption):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    tags = extract_tags(caption)
    title = extract_title(caption)
    c.execute(
        "INSERT OR REPLACE INTO books (message_id, title, tags, caption) VALUES (?, ?, ?, ?)",
        (message_id, title, tags, caption),
    )
    conn.commit()
    conn.close()


def search_books(query):
    """Match if every word in the query appears somewhere in title+tags.
    Ignores extra spaces/punctuation and is not thrown off by word order."""
    words = normalize(query).split()
    if not words:
        return []

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    conditions = []
    params = []
    for w in words:
        conditions.append("(lower(title) || ' ' || lower(tags)) LIKE ?")
        params.append(f"%{w}%")

    sql = (
        "SELECT message_id, title FROM books WHERE "
        + " AND ".join(conditions)
        + " LIMIT 15"
    )
    c.execute(sql, params)
    results = c.fetchall()
    conn.close()
    return results


# ---------- Membership gate ----------

async def is_channel_member(user_id, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(
            chat_id=f"@{CHANNEL_HANDLE}", user_id=user_id
        )
        return member.status not in ("left", "kicked")
    except Exception:
        # If the check fails for any reason, default to blocking rather than
        # silently letting someone through.
        return False


async def prompt_join(update: Update):
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📚 Join BookShare Channel", url=f"https://t.me/{CHANNEL_HANDLE}")]]
    )
    await update.effective_message.reply_text(
        "🔒 You need to join our channel first to use this bot.\n\n"
        "Tap below to join, then come back and send your search again.",
        reply_markup=keyboard,
    )


# ---------- Handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_channel_member(update.effective_user.id, context):
        await prompt_join(update)
        return
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Send me a book name or a language (hindi / english / gujarati) "
        "and I'll send you the matching PDF(s) from the channel."
    )


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_channel_member(update.effective_user.id, context):
        await prompt_join(update)
        return

    query = update.message.text.strip()
    results = search_books(query)

    if not results:
        await update.message.reply_text(
            "No matching PDFs found. Try a different name or language."
        )
        return

    if len(results) == 1:
        message_id, title = results[0]
        await context.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=CHANNEL_USERNAME,
            message_id=message_id,
        )
        return

    buttons = [
        [InlineKeyboardButton(title or f"Book {mid}", callback_data=str(mid))]
        for mid, title in results
    ]
    await update.message.reply_text(
        f"Found {len(results)} matches, tap one to get the PDF:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await is_channel_member(query.from_user.id, context):
        await query.answer()
        await prompt_join(update)
        return

    await query.answer()
    message_id = int(query.data)
    await context.bot.copy_message(
        chat_id=query.message.chat_id,
        from_chat_id=CHANNEL_USERNAME,
        message_id=message_id,
    )


async def handle_new_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-index new PDFs as soon as they're posted to the channel."""
    message = update.channel_post
    if not message or not message.document:
        return
    if not message.chat.username or message.chat.username.lower() != CHANNEL_HANDLE.lower():
        return

    caption = message.text or message.caption or ""
    add_or_update_book(message.message_id, caption)
    print(f"Auto-indexed new post: message_id={message.message_id}")


def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(
        MessageHandler(filters.UpdateType.CHANNEL_POST & filters.Document.ALL, handle_new_channel_post)
    )
    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
