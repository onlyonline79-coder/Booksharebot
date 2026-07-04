import os
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
DB_FILE = "books.db"


def search_books(query):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    q = f"%{query.lower()}%"
    c.execute(
        "SELECT message_id, title FROM books WHERE lower(title) LIKE ? OR lower(tags) LIKE ? LIMIT 15",
        (q, q),
    )
    results = c.fetchall()
    conn.close()
    return results


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Send me a book name or a language (hindi / english / gujarati) "
        "and I'll send you the matching PDF(s) from the channel."
    )


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await query.answer()
    message_id = int(query.data)
    await context.bot.copy_message(
        chat_id=query.message.chat_id,
        from_chat_id=CHANNEL_USERNAME,
        message_id=message_id,
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    app.add_handler(CallbackQueryHandler(handle_button))
    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
