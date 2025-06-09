import logging
import os
import asyncio
import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.error import TelegramError
import gspread
from google.oauth2.service_account import Credentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
import io
import random

# הגדרת לוגינג
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# הגדרות המערכת
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN') or "7619055199:AAEL28DJ-E1Xl7iEfdPqTXJ0in1Lps0VOtM"
CHANNEL_ID = os.getenv('CHANNEL_ID') or "-1002886874719"
GOOGLE_CREDENTIALS = os.getenv('GOOGLE_CREDENTIALS')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# מצבי השיחה
WAITING_FOR_EMAIL = 1

class PeakTradeBot:
    def __init__(self):
        self.application = None
        self.scheduler = None
        self.google_client = None
        self.sheet = None
        self.setup_google_sheets()
        
    def setup_google_sheets(self):
        """הגדרת חיבור ל-Google Sheets"""
        try:
            if GOOGLE_CREDENTIALS:
                creds_dict = json.loads(GOOGLE_CREDENTIALS)
                scope = [
                    'https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive'
                ]
                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                self.google_client = gspread.authorize(creds)
                self.sheet = self.google_client.open_by_key(SPREADSHEET_ID).sheet1
                
                # וידוא שיש כותרות בגיליון
                try:
                    headers = self.sheet.row_values(1)
                    if not headers:
                        header_row = [
                            'telegram_user_id', 'telegram_username', 'email', 
                            'disclaimer_sent_time', 'confirmation_status', 
                            'trial_start_date', 'trial_end_date', 'payment_status',
                            'gumroad_sale_id', 'gumroad_subscription_id', 'last_update_timestamp'
                        ]
                        self.sheet.append_row(header_row)
                        logger.info("✅ Headers added to Google Sheets")
                except Exception as e:
                    logger.error(f"❌ Error checking headers: {e}")
                
                logger.info("✅ Google Sheets connected successfully")
            else:
                logger.warning("⚠️ Google Sheets credentials not found")
        except Exception as e:
            logger.error(f"❌ Error setting up Google Sheets: {e}")

    def check_user_exists(self, user_id):
        """בדיקה אם משתמש כבר קיים ב-Google Sheets"""
        try:
            if not self.sheet:
                return False
            
            records = self.sheet.get_all_records()
            for record in records:
                if str(record.get('telegram_user_id')) == str(user_id):
                    # בדיקה אם המשתמש פעיל (trial_active או paid_subscriber)
                    status = record.get('payment_status', '')
                    if status in ['trial_active', 'paid_subscriber']:
                        return True
            return False
        except Exception as e:
            logger.error(f"❌ Error checking user existence: {e}")
            return False

    def get_mixed_stock_recommendations(self):
        """קבלת המלצות מניות מעורבות - אמריקאיות וישראליות"""
        try:
            # מניות אמריקאיות פופולריות
            us_symbols = [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 
                'AMD', 'INTC', 'IBM', 'CSCO', 'ORCL', 'CRM', 'ADBE', 'PYPL',
                'UBER', 'LYFT', 'SPOT', 'ZOOM', 'SHOP', 'SQ', 'ROKU',
                'SNAP', 'PINS', 'DOCU', 'ZM', 'PLTR', 'COIN', 'RBLX', 'HOOD'
            ]
            
            # מניות ישראליות הנסחרות בנאסד"ק
            israeli_nasdaq_symbols = [
                'CHKP',    # Check Point Software
                'CYBR',    # CyberArk Software
                'NICE',    # NICE Ltd
                'MNDY',    # Monday.com
                'WIX',     # Wix.com
                'FVRR',    # Fiverr International
                'TEVA',    # Teva Pharmaceutical
                'CELG',    # Cellcom Israel
                'PLTK',    # Playtika Holding
                'SSYS',    # Stratasys
                'NNDM',    # Nano Dimension
                'RDWR',    # Radware
                'MGIC',    # Magic Software
                'GILT',    # Gilat Satellite Networks
                'ELBM',    # Electra Battery Materials
                'OPRX',    # OptimizeRx Corporation
                'KRNT',    # Kornit Digital
                'INMD',    # InMode
                'SMWB',    # Similarweb
                'SPNS'     # Sapiens International
            ]
            
            # מניות ישראליות בת"א (עם סיומת .TA)
            israeli_ta_symbols = [
                'TEVA.TA',   # טבע
                'ICL.TA',    # כימיקלים לישראל
                'BANK.TA',   # בנק הפועלים
                'LUMI.TA',   # אור אנרגיה
                'ELCO.TA',   # אלקו
                'AZRM.TA',   # עזריאלי
                'DORL.TA',   # דורל
                'ISCN.TA',   # ישקרון
                'ALHE.TA',   # אלון הולדינגס
                'MZTF.TA'    # מזרחי טפחות
            ]
            
            # איחוד כל הרשימות
            all_symbols = us_symbols + israeli_nasdaq_symbols + israeli_ta_symbols
            
            recommendations = []
            
            for symbol in all_symbols:
                try:
                    stock = yf.Ticker(symbol)
                    hist = stock.history(period='2d')
                    
                    if hist.empty or len(hist) < 2:
                        continue
                    
                    close_today = hist['Close'][-1]
                    close_yesterday = hist['Close'][-2]
                    change_percent = ((close_today - close_yesterday) / close_yesterday) * 100
                    
                    # הוספת מניה עם שינוי משמעותי (מעל 1.5%)
                    if abs(change_percent) > 1.5:
                        # זיהוי סוג המניה
                        if symbol in israeli_nasdaq_symbols:
                            stock_type = "🇮🇱 ישראלית (נאסד\"ק)"
                        elif symbol.endswith('.TA'):
                            stock_type = "🇮🇱 ישראלית (ת\"א)"
                        else:
                            stock_type = "🇺🇸 אמריקאית"
                            
                        recommendations.append({
                            'symbol': symbol,
                            'change_percent': change_percent,
                            'current_price': close_today,
                            'stock_type': stock_type
                        })
                        
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
                    continue
            
            # מיון לפי שינוי אחוזי (הגדול ביותר קודם)
            recommendations.sort(key=lambda x: abs(x['change_percent']), reverse=True)
            
            # החזרת עד 12 המלצות מובילות (מעורב)
            return recommendations[:12]
            
        except Exception as e:
            logger.error(f"❌ Error getting mixed stock recommendations: {e}")
            # fallback למניות קבועות
            return [
                {'symbol': 'AAPL', 'change_percent': 0, 'current_price': 150, 'stock_type': '🇺🇸 אמריקאית'},
                {'symbol': 'CHKP', 'change_percent': 0, 'current_price': 120, 'stock_type': '🇮🇱 ישראלית (נאסד"ק)'},
                {'symbol': 'TEVA.TA', 'change_percent': 0, 'current_price': 50, 'stock_type': '🇮🇱 ישראלית (ת"א)'}
            ]

    def get_crypto_recommendations(self):
        """קבלת המלצות קריפטו מובילות"""
        try:
            crypto_symbols = [
                'BTC-USD',   # Bitcoin
                'ETH-USD',   # Ethereum
                'SOL-USD',   # Solana
                'XRP-USD',   # Ripple
                'BNB-USD',   # Binance Coin
                'ADA-USD',   # Cardano
                'DOGE-USD',  # Dogecoin
                'TRX-USD',   # Tron
                'AVAX-USD',  # Avalanche
                'DOT-USD',   # Polkadot
                'MATIC-USD', # Polygon
                'LINK-USD'   # Chainlink
            ]
            
            recommendations = []
            
            for symbol in crypto_symbols:
                try:
                    crypto = yf.Ticker(symbol)
                    hist = crypto.history(period='2d')
                    
                    if hist.empty or len(hist) < 2:
                        continue
                    
                    close_today = hist['Close'][-1]
                    close_yesterday = hist['Close'][-2]
                    change_percent = ((close_today - close_yesterday) / close_yesterday) * 100
                    
                    # הוספת קריפטו עם שינוי משמעותי (מעל 2%)
                    if abs(change_percent) > 2:
                        recommendations.append({
                            'symbol': symbol,
                            'change_percent': change_percent,
                            'current_price': close_today,
                            'crypto_type': '🪙 קריפטו'
                        })
                        
                except Exception as e:
                    logger.error(f"Error processing crypto {symbol}: {e}")
                    continue
            
            # מיון לפי שינוי אחוזי (הגדול ביותר קודם)
            recommendations.sort(key=lambda x: abs(x['change_percent']), reverse=True)
            
            # החזרת עד 6 המלצות מובילות
            return recommendations[:6]
            
        except Exception as e:
            logger.error(f"❌ Error getting crypto recommendations: {e}")
            # fallback לקריפטו קבועים
            return [
                {'symbol': 'BTC-USD', 'change_percent': 0, 'current_price': 50000, 'crypto_type': '🪙 קריפטו'},
                {'symbol': 'ETH-USD', 'change_percent': 0, 'current_price': 3000, 'crypto_type': '🪙 קריפטו'},
                {'symbol': 'SOL-USD', 'change_percent': 0, 'current_price': 100, 'crypto_type': '🪙 קריפטו'}
            ]

    def create_advanced_chart_with_stoploss(self, symbol):
        """יצירת גרף נרות מתקדם עם סטופלוס מומלץ"""
        try:
            stock = yf.Ticker(symbol)
            data = stock.history(period="30d")
            
            if data.empty:
                return None, None
            
            # חישוב סטופלוס - 2% מתחת למחיר סגירה אחרון
            last_close = data['Close'][-1]
            stoploss = last_close * 0.98
            
            # יצירת גרף נרות
            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # יצירת גרף נרות עם mplfinance
            mpf.plot(data, type='candle', style='charles', 
                    title=f'{symbol} - 30 Days Candlestick Chart',
                    ylabel='Price',
                    ax=ax)
            
            # הוספת קו סטופלוס
            ax.axhline(stoploss, color='red', linestyle='--', linewidth=2, 
                      label=f'Stop Loss: {stoploss:.2f} (-2%)', alpha=0.8)
            
            # הוספת קו מחיר נוכחי
            ax.axhline(last_close, color='yellow', linestyle='-', linewidth=1.5, 
                      label=f'Current: {last_close:.2f}', alpha=0.8)
            
            # הוספת אזור רווח פוטנציאלי
            profit_target = last_close * 1.05  # 5% רווח
            ax.axhline(profit_target, color='green', linestyle=':', linewidth=1.5, 
                      label=f'Target: {profit_target:.2f} (+5%)', alpha=0.8)
            
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)
            
            # שמירת הגרף כתמונה
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight', 
                       facecolor='black', edgecolor='none')
            buffer.seek(0)
            plt.close()
            
            return buffer, stoploss
            
        except Exception as e:
            logger.error(f"❌ Error creating chart for {symbol}: {e}")
            return None, None

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת התחלה עם disclaimer"""
        user = update.effective_user
        logger.info(f"User {user.id} ({user.username}) started PeakTrade bot")
        
        # בדיקה אם המשתמש כבר קיים
        if self.check_user_exists(user.id):
            existing_user_message = f"""🔄 שלום {user.first_name}!

נראה שאתה כבר רשום במערכת שלנו! 

✅ הסטטוס שלך: פעיל בערוץ PeakTrade VIP

🎯 מה תוכל לעשות:
• להמשיך ליהנות מהתוכן הפרמיום
• לקבל ניתוחים טכניים יומיים
• לראות גרפי נרות בזמן אמת

💬 יש שאלות? פנה למנהל הערוץ

תודה שאתה חלק מקהילת PeakTrade VIP! 🚀"""
            
            await update.message.reply_text(existing_user_message)
            return ConversationHandler.END
        
        disclaimer_message = f"""🏔️ PeakTrade VIP | הצהרת אחריות

שלום {user.first_name}! 👋

⚠️ הצהרת ויתור אחריות:
• המידע המוצג בערוץ הוא לצרכי חינוך בלבד
• אין זו המלצה להשקעה או ייעוץ פיננסי
• כל השקעה כרוכה בסיכון והפסדים אפשריים
• אתה נושא באחריות המלאה להחלטותיך

📈 מה תקבל בערוץ PeakTrade VIP:
• ניתוחים טכניים מתקדמים
• גרפי נרות בזמן אמת עם סטופלוס מומלץ
• המלצות מניות דינמיות - אמריקאיות וישראליות
• המלצות קריפטו מובילות
• תוכן ייחודי ומקצועי

⏰ תקופת ניסיון: 7 ימים חינם

✅ להמשך, אנא שלח את כתובת האימייל שלך בפורמט:
your-email@example.com מאשר

💡 דוגמה:
john.doe@gmail.com מאשר

חשוב: השתמש באותו אימייל לתשלום עתידי!"""
        
        await update.message.reply_text(disclaimer_message)
        
        await self.log_disclaimer_sent(user)
        return WAITING_FOR_EMAIL
    
    async def log_disclaimer_sent(self, user):
        """רישום שליחת disclaimer ב-Google Sheets"""
        try:
            if not self.sheet:
                return
                
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            new_row = [
                user.id,
                user.username or "N/A",
                "",
                current_time,
                "pending",
                "",
                "",
                "trial_pending",
                "",
                "",
                current_time
            ]
            self.sheet.append_row(new_row)
            logger.info(f"✅ Disclaimer logged for user {user.id}")
            
        except Exception as e:
            logger.error(f"❌ Error logging disclaimer: {e}")
    
    async def handle_email_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול באישור האימייל"""
        user = update.effective_user
        message_text = update.message.text.strip()
        
        logger.info(f"User {user.id} sent: {message_text}")
        
        if "מאשר" not in message_text:
            await update.message.reply_text(
                "❌ אנא שלח את האימייל בפורמט הנכון:\n"
                "your-email@example.com מאשר"
            )
            return WAITING_FOR_EMAIL
        
        email = message_text.replace("מאשר", "").strip()
        
        if "@" not in email or "." not in email:
            await update.message.reply_text(
                "❌ כתובת האימייל לא תקינה. אנא נסה שוב:\n"
                "your-email@example.com מאשר"
            )
            return WAITING_FOR_EMAIL
        
        processing_msg = await update.message.reply_text(
            "⏳ מעבד את הרישום לתקופת ניסיון..."
        )
        
        try:
            await self.register_trial_user(user, email)
            
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                expire_date=int((datetime.now() + timedelta(days=8)).timestamp()),
                name=f"Trial_{user.id}_{email.split('@')[0]}"
            )
            
            success_message = f"""✅ ברוך הבא ל-PeakTrade VIP!

📧 האימייל שלך: {email}
👤 משתמש: @{user.username or 'לא זמין'}
🆔 מזהה: {user.id}

🔗 קישור הצטרפות לערוץ הפרמיום:
{invite_link.invite_link}

⏰ תקופת ניסיון: 7 ימים
📅 מתחיל: {datetime.now().strftime("%d/%m/%Y")}
📅 מסתיים: {(datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")}

🎯 מה תקבל בערוץ:
• 10 ניתוחים טכניים יומיים (מניות)
• 3 המלצות קריפטו יומיות
• גרפי נרות בזמן אמת עם סטופלוס
• המלצות אמריקאיות וישראליות
• תובנות שוק ייחודיות

💳 לפני סיום תקופת הניסיון תקבל הודעה עם אפשרות להמשיך כמנוי בתשלום.

לחץ על הקישור והצטרף עכשיו! 🚀"""
            
            await processing_msg.edit_text(
                success_message,
                disable_web_page_preview=True
            )
            
            logger.info(f"✅ Trial registration successful for user {user.id}")
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"❌ Error in trial registration: {e}")
            await processing_msg.edit_text(
                f"❌ שגיאה ברישום לתקופת ניסיון\n\n"
                f"פרטי השגיאה: {str(e)}\n\n"
                f"אנא פנה לתמיכה."
            )
            return ConversationHandler.END
    
    async def register_trial_user(self, user, email):
        """רישום משתמש לתקופת ניסיון ב-Google Sheets"""
        try:
            if not self.sheet:
                raise Exception("Google Sheets not connected")
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            trial_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            
            all_values = self.sheet.get_all_values()
            user_row = None
            
            for i, row in enumerate(all_values):
              if len(row) > 0 and str(row[0]) == str(user.id):
                    user_row = i + 1
                    break
            
            if user_row and user_row > 1:
                try:
                    logger.info(f"Updating existing user at row {user_row}")
                    
                    updates = [
                        (user_row, 3, email),
                        (user_row, 5, "confirmed"),
                        (user_row, 6, current_time),
                        (user_row, 7, trial_end),
                        (user_row, 8, "trial_active"),
                        (user_row, 11, current_time)
                    ]
                    
                    for row, col, value in updates:
                        try:
                            self.sheet.update_cell(row, col, value)
                        except Exception as update_error:
                            logger.error(f"Error updating cell ({row}, {col}): {update_error}")
                            raise Exception("Update failed, will create new row")
                    
                except Exception as update_error:
                    logger.warning(f"Failed to update existing row: {update_error}")
                    user_row = None
            
            if not user_row:
                logger.info("Adding new user row")
                new_row = [
                    user.id,
                    user.username or "N/A",
                    email,
                    current_time,
                    "confirmed",
                    current_time,
                    trial_end,
                    "trial_active",
                    "",
                    "",
                    current_time
                ]
                self.sheet.append_row(new_row)
            
            logger.info(f"✅ User {user.id} registered for trial successfully")
            
        except Exception as e:
            logger.error(f"❌ Error registering trial user: {e}")
            raise Exception(f"Google Sheets error: {str(e)}")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת עזרה"""
        help_text = """🆘 PeakTrade VIP Bot - עזרה

📋 פקודות זמינות:
/start - התחלת תהליך רישום
/help - הצגת עזרה זו

✅ איך להצטרף:
1. שלח /start
2. קרא את הצהרת האחריות
3. שלח את האימייל שלך + "מאשר"
4. קבל קישור לערוץ הפרמיום

⏰ תקופת ניסיון: 7 ימים חינם
💳 תשלום: דרך Gumroad (PayPal/כרטיס אשראי)

🎯 מה תקבל (13 הודעות יומיות):
• 10 המלצות מניות - אמריקאיות וישראליות
• 3 המלצות קריפטו מובילות
• גרפי נרות עם סטופלוס מומלץ
• ניתוחים טכניים מתקדמים

🇮🇱 מניות ישראליות כלולות:
• נאסד"ק: Check Point, CyberArk, NICE, Monday.com
• ת"א: טבע, כימיקלים לישראל, בנק הפועלים

🪙 קריפטו כלול:
• Bitcoin, Ethereum, Solana, Ripple, BNB, ועוד

💬 תמיכה: פנה למנהל הערוץ"""
        
        await update.message.reply_text(help_text)
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ביטול תהליך"""
        await update.message.reply_text(
            "❌ התהליך בוטל. שלח /start כדי להתחיל מחדש."
        )
        return ConversationHandler.END
    
    def setup_handlers(self):
        """הגדרת handlers"""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start_command)],
            states={
                WAITING_FOR_EMAIL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_email_confirmation)
                ],
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_command),
                CommandHandler('start', self.start_command)
            ],
        )
        
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler('help', self.help_command))
        
        logger.info("✅ All handlers configured")
    
    def setup_scheduler(self):
        """הגדרת תזמון משימות - 10 מניות + 3 קריפטו"""
        self.scheduler = AsyncIOScheduler()
        
        # בדיקת תפוגת ניסיונות
        self.scheduler.add_job(
            self.check_trial_expiry,
            CronTrigger(hour=9, minute=0),
            id='check_trial_expiry'
        )
        
        # 10 משימות מניות (ישראל+חו"ל)
        for i in range(10):
            random_hour = random.randint(10, 22)
            random_minute = random.randint(0, 59)
            
            self.scheduler.add_job(
                self.send_mixed_content,
                CronTrigger(hour=random_hour, minute=random_minute),
                id=f'stock_content_{i}'
            )
        
        # 3 משימות קריפטו
        for i in range(3):
            random_hour = random.randint(10, 22)
            random_minute = random.randint(0, 59)
            
            self.scheduler.add_job(
                self.send_crypto_content,
                CronTrigger(hour=random_hour, minute=random_minute),
                id=f'crypto_content_{i}'
            )
        
        self.scheduler.start()
        logger.info("✅ Scheduler configured: 10 stocks + 3 crypto daily")
    
    async def check_trial_expiry(self):
        """בדיקת תפוגת תקופות ניסיון"""
        try:
            if not self.sheet:
                return
            
            records = self.sheet.get_all_records()
            current_time = datetime.now()
            
            for i, record in enumerate(records):
                if record.get('payment_status') == 'trial_active':
                    trial_end_str = record.get('trial_end_date')
                    if trial_end_str:
                        try:
                            trial_end = datetime.strptime(trial_end_str, "%Y-%m-%d %H:%M:%S")
                            
                            if current_time > trial_end:
                                user_id = record.get('telegram_user_id')
                                await self.handle_trial_expired(user_id, i + 2)
                            
                            elif (trial_end - current_time).days == 1:
                                user_id = record.get('telegram_user_id')
                                await self.send_payment_reminder(user_id)
                        except ValueError:
                            logger.error(f"Invalid date format: {trial_end_str}")
            
            logger.info("✅ Trial expiry check completed")
            
        except Exception as e:
            logger.error(f"❌ Error checking trial expiry: {e}")
    
    async def send_payment_reminder(self, user_id):
        """שליחת תזכורת תשלום"""
        try:
            reminder_message = """⏰ תזכורת: תקופת הניסיון מסתיימת מחר!

היי! תקופת הניסיון של 7 ימים ב-PeakTrade VIP מסתיימת מחר.

💎 כדי להמשיך ליהנות מהתוכן הפרמיום:
🔗 לחץ כאן לרכישת מנוי: [קישור Gumroad]

💳 תשלום מאובטח דרך:
• כרטיס אשראי
• Apple Pay
• Google Pay

⚠️ חשוב: השתמש באותו אימייל שרשמת איתו!

תודה שאתה חלק מקהילת PeakTrade VIP! 🚀"""
            
            await self.application.bot.send_message(
                chat_id=user_id,
                text=reminder_message
            )
            
            logger.info(f"✅ Payment reminder sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error sending payment reminder to {user_id}: {e}")
    
    async def handle_trial_expired(self, user_id, row_index):
        """טיפול במשתמש שתקופת הניסיון שלו הסתיימה"""
        try:
            await self.application.bot.ban_chat_member(
                chat_id=CHANNEL_ID,
                user_id=user_id
            )
            
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                self.sheet.update_cell(row_index, 8, "expired_no_payment")
                self.sheet.update_cell(row_index, 11, current_time)
            except Exception as update_error:
                logger.error(f"Error updating expiry status: {update_error}")
            
            expiry_message = """⏰ תקופת הניסיון הסתיימה

היי! תקופת הניסיון שלך ב-PeakTrade VIP הסתיימה.

💎 רוצה להמשיך ליהנות מהתוכן הפרמיום?
🔗 לחץ כאן לרכישת מנוי: [קישור Gumroad]

תודה שניסית את PeakTrade VIP! 🙏"""
            
            await self.application.bot.send_message(
                chat_id=user_id,
                text=expiry_message
            )
            
            logger.info(f"✅ Trial expired handled for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error handling trial expiry for {user_id}: {e}")
    
    async def send_mixed_content(self):
        """שליחת תוכן מעורב עם מניות אמריקאיות וישראליות"""
        try:
            # קבלת המלצות מניות מעורבות
            recommendations = self.get_mixed_stock_recommendations()
            
            if not recommendations:
                logger.warning("No mixed stock recommendations available")
                return
            
            # בחירת מניה אקראית מההמלצות
            selected_stock = random.choice(recommendations)
            symbol = selected_stock['symbol']
            stock_type = selected_stock['stock_type']
            
            # יצירת גרף מתקדם עם סטופלוס
            chart_buffer, stoploss = self.create_advanced_chart_with_stoploss(symbol)
            
            if not chart_buffer:
                logger.error(f"Failed to create chart for {symbol}")
                return
            
            # קבלת נתונים נוספים
            stock = yf.Ticker(symbol)
            data = stock.history(period="2d")
            
            current_price = data['Close'][-1]
            change = data['Close'][-1] - data['Close'][-2] if len(data) > 1 else 0
            change_percent = (change / data['Close'][-2] * 100) if len(data) > 1 and data['Close'][-2] != 0 else 0
            volume = data['Volume'][-1] if len(data) > 0 else 0
            
            # חישוב יעד רווח
            profit_target = current_price * 1.05
            risk_reward = (profit_target - current_price) / (current_price - stoploss) if stoploss else 0
            
            # קביעת מטבע לפי סוג המניה
            currency = "₪" if symbol.endswith('.TA') else "$"
            
            # יצירת טקסט מפורט עם זיהוי סוג המניה
            caption = f"""{stock_type} 📈 {symbol} - ניתוח טכני מתקדם

💰 מחיר נוכחי: {currency}{current_price:.2f}
📊 שינוי יומי: {change:+.2f} ({change_percent:+.2f}%)
📈 נפח מסחר: {volume:,.0f}

🎯 המלצות מסחר:
🔴 Stop Loss: {currency}{stoploss:.2f} (-2.0%)
🟢 יעד רווח: {currency}{profit_target:.2f} (+5.0%)
⚖️ יחס סיכון/תשואה: 1:{risk_reward:.1f}

🔍 נקודות מפתח:
• מגמה: {'עלייה חזקה' if change_percent > 3 else 'עלייה' if change_percent > 0 else 'ירידה'}
• נפח: {'גבוה מהממוצע' if volume > 1000000 else 'נמוך מהממוצע'}
• תנודתיות: {'גבוהה' if abs(change_percent) > 3 else 'בינונית'}

💡 אסטרטגיה מומלצת:
• כניסה: מעל {currency}{current_price:.2f}
• סטופלוס: מתחת ל-{currency}{stoploss:.2f}
• יעד: {currency}{profit_target:.2f}

⚠️ זה לא ייעוץ השקעה - לצרכי חינוך בלבד

#PeakTradeVIP #{symbol.replace('.TA', '')} #TechnicalAnalysis #Stocks"""
            
            # שליחה לערוץ
            await self.application.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=chart_buffer,
                caption=caption
            )
            
            logger.info(f"✅ Stock content sent for {symbol} ({stock_type}) - Change: {change_percent:.2f}%")
            
        except Exception as e:
            logger.error(f"❌ Error sending stock content: {e}")
    
    async def send_crypto_content(self):
        """שליחת תוכן קריפטו עם גרף וסטופלוס"""
        try:
            # קבלת המלצות קריפטו
            recommendations = self.get_crypto_recommendations()
            
            if not recommendations:
                logger.warning("No crypto recommendations available")
                return
            
            # בחירת קריפטו אקראי מההמלצות
            selected_crypto = random.choice(recommendations)
            symbol = selected_crypto['symbol']
            crypto_type = selected_crypto['crypto_type']
            
            # יצירת גרף מתקדם עם סטופלוס
            chart_buffer, stoploss = self.create_advanced_chart_with_stoploss(symbol)
            
            if not chart_buffer:
                logger.error(f"Failed to create chart for {symbol}")
                return
            
            # קבלת נתונים נוספים
            crypto = yf.Ticker(symbol)
            data = crypto.history(period="2d")
            
            current_price = data['Close'][-1]
            change = data['Close'][-1] - data['Close'][-2] if len(data) > 1 else 0
            change_percent = (change / data['Close'][-2] * 100) if len(data) > 1 and data['Close'][-2] != 0 else 0
            volume = data['Volume'][-1] if len(data) > 0 else 0
            
            # חישוב יעד רווח
            profit_target = current_price * 1.05
            risk_reward = (profit_target - current_price) / (current_price - stoploss) if stoploss else 0
            
            # יצירת שם נקי לקריפטו
            crypto_name = symbol.replace('-USD', '')
            
            # יצירת טקסט מפורט לקריפטו
            caption = f"""{crypto_type} {crypto_name} - ניתוח טכני מתקדם

💰 מחיר נוכחי: ${current_price:.2f}
📊 שינוי יומי: {change:+.2f} ({change_percent:+.2f}%)
📈 נפח מסחר: {volume:,.0f}

🎯 המלצות מסחר:
🔴 Stop Loss: ${stoploss:.2f} (-2.0%)
🟢 יעד רווח: ${profit_target:.2f} (+5.0%)
⚖️ יחס סיכון/תשואה: 1:{risk_reward:.1f}

🔍 נקודות מפתח:
• מגמה: {'עלייה חזקה' if change_percent > 5 else 'עלייה' if change_percent > 0 else 'ירידה'}
• נפח: {'גבוה מהממוצע' if volume > 100000 else 'נמוך מהממוצע'}
• תנודתיות: {'גבוהה מאוד' if abs(change_percent) > 10 else 'גבוהה' if abs(change_percent) > 5 else 'בינונית'}

💡 אסטרטגיה מומלצת:
• כניסה: מעל ${current_price:.2f}
• סטופלוס: מתחת ל-${stoploss:.2f}
• יעד: ${profit_target:.2f}

⚠️ זה לא ייעוץ השקעה - לצרכי חינוך בלבד
⚠️ קריפטו כרוך בסיכון גבוה במיוחד

#PeakTradeVIP #{crypto_name} #Crypto #TechnicalAnalysis"""
            
            # שליחה לערוץ
            await self.application.bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=chart_buffer,
                caption=caption
            )
            
            logger.info(f"✅ Crypto content sent for {symbol} - Change: {change_percent:.2f}%")
            
        except Exception as e:
            logger.error(f"❌ Error sending crypto content: {e}")
    
    async def run(self):
        """הפעלת הבוט"""
        logger.info("🚀 Starting PeakTrade VIP Bot (Background Worker)...")
        
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        self.setup_scheduler()
        
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("✅ PeakTrade VIP Bot is running successfully!")
            logger.info("📊 Daily content: 10 stocks + 3 crypto = 13 messages")
            
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
        finally:
            if self.scheduler:
                self.scheduler.shutdown()
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

if __name__ == "__main__":
    bot = PeakTradeBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
