import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.error import TelegramError
import asyncio
import signal
import sys

# הגדרת לוגינג
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# משתני סביבה
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or "7592108692:AAHRNtKPAmveFp4nfv_tWvoMt8Cg0gIFJKE"
CHANNEL_ID = os.getenv('CHANNEL_ID') or "-100591679360"
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME') or "my_channel_name"

# מצבי השיחה
WAITING_FOR_EMAIL = 1

class TelegramBot:
    def __init__(self):
        self.application = None
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת התחלה"""
        user = update.effective_user
        logger.info(f"User {user.id} ({user.username}) started the bot")
        
        welcome_message = f"""
🎉 *ברוכים הבאים לבוט הניסיון שלנו!*

שלום {user.first_name}! 👋

📧 *כדי להתחיל את תקופת הניסיון של 7 ימים:*
אנא שלח את כתובת האימייל שלך בפורמט הבא:
`your-email@example.com מאשר`

💡 *דוגמה:*
`john@gmail.com מאשר`

לאחר שתשלח את האימייל, אקבל אותך לערוץ הפרמיום שלנו! 🚀
        """
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown'
        )
        
        return WAITING_FOR_EMAIL
    
    async def handle_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בהודעת האימייל"""
        user = update.effective_user
        message_text = update.message.text.strip()
        
        logger.info(f"User {user.id} sent: {message_text}")
        
        # בדיקה אם ההודעה מכילה "מאשר"
        if "מאשר" not in message_text:
            await update.message.reply_text(
                "❌ אנא שלח את האימייל בפורמט הנכון:\n"
                "`your-email@example.com מאשר`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_EMAIL
        
        # חילוץ האימייל
        email = message_text.replace("מאשר", "").strip()
        
        # בדיקה בסיסית של פורמט האימייל
        if "@" not in email or "." not in email:
            await update.message.reply_text(
                "❌ כתובת האימייל לא נראית תקינה. אנא נסה שוב:\n"
                "`your-email@example.com מאשר`",
                parse_mode='Markdown'
            )
            return WAITING_FOR_EMAIL
        
        try:
            # יצירת קישור הזמנה לערוץ (7 ימים)
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                expire_date=None,  # ללא תפוגה
                member_limit=1,    # משתמש אחד בלבד
                name=f"Trial_{user.id}_{email.split('@')[0]}"
            )
            
            success_message = f"""
✅ *נרשמת בהצלחה לתקופת ניסיון!*

📧 *האימייל שלך:* `{email}`
👤 *שם משתמש:* @{user.username or 'לא זמין'}
🆔 *מזהה:* `{user.id}`

🔗 *קישור הצטרפות לערוץ הפרמיום:*
{invite_link.invite_link}

⏰ *תקופת הניסיון:* 7 ימים מהיום

🎯 *מה תקבל בערוץ:*
• אנליזות מתקדמות
• אותות מסחר
• גרפים וחיזויים
• תמיכה אישית

*תהנה מתקופת הניסיון! 🚀*
            """
            
            await update.message.reply_text(
                success_message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            logger.info(f"Created trial access for user {user.id} with email {email}")
            
            return ConversationHandler.END
            
        except TelegramError as e:
            logger.error(f"Error creating invite link: {e}")
            await update.message.reply_text(
                "❌ אירעה שגיאה ביצירת הקישור. ודא שהבוט הוא אדמין בערוץ עם הרשאות ליצור קישורי הזמנה.",
                parse_mode='Markdown'
            )
            return ConversationHandler.END
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול השיחה"""
        await update.message.reply_text(
            "❌ הפעולה בוטלה. שלח /start כדי להתחיל מחדש.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת עזרה"""
        help_text = """
🆘 *עזרה - פקודות זמינות:*

/start - התחלת תהליך הרשמה לניסיון
/help - הצגת הודעת עזרה זו
/cancel - ביטול תהליך נוכחי

📧 *לרשמה לניסיון:*
שלח את האימייל שלך בפורמט:
`your-email@example.com מאשר`

💬 *זקוק לעזרה נוספת?*
פנה אלינו דרך הערוץ הראשי.
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    def setup_handlers(self):
        """הגדרת handlers"""
        # ConversationHandler לתהליך הרשמה
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                WAITING_FOR_EMAIL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_email)
                ],
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_command),
                CommandHandler('start', self.start_command)
            ],
        )
        
        # הוספת handlers
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler('help', self.help_command))
        
        logger.info("All handlers added successfully")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בשגיאות"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "❌ אירעה שגיאה. אנא נסה שוב או פנה לתמיכה."
            )
    
    async def run(self):
        """הפעלת הבוט"""
        logger.info(f"Bot token starts with: {BOT_TOKEN[:10]}...")
        logger.info(f"Channel ID: {CHANNEL_ID}")
        logger.info("Starting Telegram Bot...")
        
        # יצירת Application
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # הגדרת handlers
        self.setup_handlers()
        
        # הגדרת error handler
        self.application.add_error_handler(self.error_handler)
        
        logger.info("Starting polling...")
        
        # הפעלת הבוט עם טיפול נכון ב-event loop
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
            # המתנה אינסופית
            stop_signals = (signal.SIGTERM, signal.SIGINT)
            for sig in stop_signals:
                signal.signal(sig, lambda s, f: asyncio.create_task(self.shutdown()))
            
            logger.info("Bot is running. Press Ctrl+C to stop.")
            
            # המתנה אינסופית
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in bot execution: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """כיבוי נקי של הבוט"""
        logger.info("Shutting down bot...")
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

def main():
    """פונקציה ראשית"""
    try:
        bot = TelegramBot()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Bot shutdown complete")

if __name__ == '__main__':
    main()
