import os
import logging
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TaskBot:
    def __init__(self, telegram_token, google_credentials_path, spreadsheet_id):
        self.telegram_token = telegram_token
        self.spreadsheet_id = spreadsheet_id
        
        # Google Sheets bağlantısı
        self.setup_google_sheets(google_credentials_path)
        
    def setup_google_sheets(self, credentials_path):
        """Google Sheets API bağlantısını kurar"""
        try:
            # Google Sheets API için gerekli scope'lar
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Kimlik doğrulama
            creds = Credentials.from_service_account_file(credentials_path, scopes=scope)
            self.gc = gspread.authorize(creds)
            
            # Spreadsheet'i aç
            self.sheet = self.gc.open_by_key(self.spreadsheet_id).sheet1
            
            # Başlıkları kontrol et ve gerekirse ekle
            self.setup_headers()
            
        except Exception as e:
            logger.error(f"Google Sheets bağlantısı kurulurken hata: {e}")
            raise
    
    def setup_headers(self):
        """Google Sheets'te başlık satırını ayarlar"""
        try:
            # İlk satırı kontrol et
            headers = self.sheet.row_values(1)
            expected_headers = ['Görev Adı', 'Görev Notu', 'Son Tarih', 'İlgili Kişi', 'Durum']
            
            if not headers or headers != expected_headers:
                self.sheet.clear()
                self.sheet.append_row(expected_headers)
                logger.info("Başlık satırı eklendi")
                
        except Exception as e:
            logger.error(f"Başlık ayarlanırken hata: {e}")
    
    def add_task(self, task_name, task_note, due_date, related_person):
        """Yeni görev ekler"""
        try:
            # Tarihi doğrula
            try:
                datetime.strptime(due_date, '%Y-%m-%d')
            except ValueError:
                try:
                    # Türkçe format denemesi (dd.mm.yyyy)
                    date_obj = datetime.strptime(due_date, '%d.%m.%Y')
                    due_date = date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    raise ValueError("Geçersiz tarih formatı. YYYY-MM-DD veya DD.MM.YYYY formatını kullanın.")
            
            # Yeni görev ekle
            new_row = [task_name, task_note, due_date, related_person, 'Bekliyor']
            self.sheet.append_row(new_row)
            
            return True, "Görev başarıyla eklendi!"
            
        except Exception as e:
            logger.error(f"Görev eklenirken hata: {e}")
            return False, f"Görev eklenirken hata oluştu: {str(e)}"
    
    def get_pending_tasks(self):
        """Bekleyen görevleri getirir"""
        try:
            all_records = self.sheet.get_all_records()
            pending_tasks = [task for task in all_records if task['Durum'] == 'Bekliyor']
            return pending_tasks
        except Exception as e:
            logger.error(f"Görevler getirilirken hata: {e}")
            return []
    
    def get_today_tasks(self):
        """Bugünkü görevleri getirir"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            all_records = self.sheet.get_all_records()
            
            today_tasks = []
            for task in all_records:
                if task['Durum'] == 'Bekliyor':
                    task_date = task['Son Tarih']
                    # Farklı tarih formatlarını kontrol et
                    if task_date == today or self.format_date_for_comparison(task_date) == today:
                        today_tasks.append(task)
            
            return today_tasks
        except Exception as e:
            logger.error(f"Bugünkü görevler getirilirken hata: {e}")
            return []
    
    def format_date_for_comparison(self, date_str):
        """Tarih formatını karşılaştırma için standardize eder"""
        try:
            # DD.MM.YYYY formatından YYYY-MM-DD'ye çevir
            if '.' in date_str:
                date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                return date_obj.strftime('%Y-%m-%d')
            return date_str
        except:
            return date_str
    
    def complete_task(self, task_name):
        """Görevi tamamlandı olarak işaretler"""
        try:
            all_records = self.sheet.get_all_records()
            
            for i, task in enumerate(all_records, start=2):  # 2'den başlar çünkü 1. satır başlık
                if task['Görev Adı'].lower() == task_name.lower() and task['Durum'] == 'Bekliyor':
                    self.sheet.update_cell(i, 5, 'Tamamlandı')  # 5. sütun Durum sütunu
                    return True, f"'{task_name}' görevi tamamlandı olarak işaretlendi!"
            
            return False, f"'{task_name}' adında bekleyen bir görev bulunamadı."
            
        except Exception as e:
            logger.error(f"Görev tamamlanırken hata: {e}")
            return False, f"Görev tamamlanırken hata oluştu: {str(e)}"

# Bot instance'ı
task_bot = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot başlangıç komutu"""
    welcome_text = """
🤖 **Görev Takip Botuna Hoş Geldiniz!**

Kullanabileceğiniz komutlar:

📝 `/ekle GörevAdı; GörevNotu; SonTarih; İlgiliKişi`
   Yeni görev ekler (Tarih: YYYY-MM-DD veya DD.MM.YYYY formatında)

📋 `/liste` - Tüm bekleyen görevleri listeler

📅 `/bugun` - Bugünkü görevleri gösterir  

✅ `/tamamla GörevAdı` - Görevi tamamlandı olarak işaretler

❓ `/help` - Bu yardım mesajını gösterir

**Örnek kullanım:**
`/ekle Proje sunumu; Müdüre sunum hazırla; 2024-12-25; Ahmet Bey`
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yardım komutu"""
    await start(update, context)

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Görev ekleme komutu"""
    try:
        # Komut metnini al
        text = update.message.text
        command_part = text[5:].strip()  # "/ekle " kısmını çıkar
        
        if not command_part:
            await update.message.reply_text(
                "❌ Hatalı format!\n\n"
                "Doğru format: `/ekle GörevAdı; GörevNotu; SonTarih; İlgiliKişi`\n\n"
                "Örnek: `/ekle Proje sunumu; Müdüre sunum hazırla; 2024-12-25; Ahmet Bey`"
            )
            return
        
        # Noktalı virgülle böl
        parts = [part.strip() for part in command_part.split(';')]
        
        if len(parts) != 4:
            await update.message.reply_text(
                "❌ Eksik bilgi!\n\n"
                "4 bilgi girilmeli: GörevAdı; GörevNotu; SonTarih; İlgiliKişi\n\n"
                "Örnek: `/ekle Proje sunumu; Müdüre sunum hazırla; 2024-12-25; Ahmet Bey`"
            )
            return
        
        task_name, task_note, due_date, related_person = parts
        
        # Görev ekle
        success, message = task_bot.add_task(task_name, task_note, due_date, related_person)
        
        if success:
            await update.message.reply_text(f"✅ {message}")
        else:
            await update.message.reply_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"add_task_command hatası: {e}")
        await update.message.reply_text("❌ Görev eklenirken bir hata oluştu.")

async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bekleyen görevleri listeleme komutu"""
    try:
        tasks = task_bot.get_pending_tasks()
        
        if not tasks:
            await update.message.reply_text("📋 Bekleyen görev bulunmuyor.")
            return
        
        message = "📋 **Bekleyen Görevler:**\n\n"
        
        for i, task in enumerate(tasks, 1):
            message += f"**{i}. {task['Görev Adı']}**\n"
            message += f"📝 Not: {task['Görev Notu']}\n"
            message += f"📅 Son Tarih: {task['Son Tarih']}\n"
            message += f"👤 İlgili Kişi: {task['İlgili Kişi']}\n"
            message += "─────────────\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"list_tasks_command hatası: {e}")
        await update.message.reply_text("❌ Görevler listelenirken bir hata oluştu.")

async def today_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bugünkü görevleri listeleme komutu"""
    try:
        tasks = task_bot.get_today_tasks()
        
        if not tasks:
            await update.message.reply_text("📅 Bugün için görev bulunmuyor.")
            return
        
        today_str = datetime.now().strftime('%d.%m.%Y')
        message = f"📅 **Bugünkü Görevler ({today_str}):**\n\n"
        
        for i, task in enumerate(tasks, 1):
            message += f"**{i}. {task['Görev Adı']}**\n"
            message += f"📝 Not: {task['Görev Notu']}\n"
            message += f"👤 İlgili Kişi: {task['İlgili Kişi']}\n"
            message += "─────────────\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"today_tasks_command hatası: {e}")
        await update.message.reply_text("❌ Bugünkü görevler listelenirken bir hata oluştu.")

async def complete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Görev tamamlama komutu"""
    try:
        # Komut metnini al
        text = update.message.text
        command_part = text[9:].strip()  # "/tamamla " kısmını çıkar
        
        if not command_part:
            await update.message.reply_text(
                "❌ Görev adı belirtilmedi!\n\n"
                "Doğru format: `/tamamla GörevAdı`\n\n"
                "Örnek: `/tamamla Proje sunumu`"
            )
            return
        
        task_name = command_part
        
        # Görevi tamamla
        success, message = task_bot.complete_task(task_name)
        
        if success:
            await update.message.reply_text(f"✅ {message}")
        else:
            await update.message.reply_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"complete_task_command hatası: {e}")
        await update.message.reply_text("❌ Görev tamamlanırken bir hata oluştu.")

def main():
    """Ana fonksiyon"""
    global task_bot
    
def main():
    """Ana fonksiyon"""
    global task_bot
    
    # Çevre değişkenlerinden bilgileri al
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH') 
    SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
    
    # Debug için değerleri yazdır
    print(f"TELEGRAM_TOKEN: {'✅ Var' if TELEGRAM_TOKEN else '❌ Yok'}")
    print(f"GOOGLE_CREDENTIALS_PATH: {'✅ Var' if GOOGLE_CREDENTIALS_PATH else '❌ Yok'}")
    print(f"SPREADSHEET_ID: {'✅ Var' if SPREADSHEET_ID else '❌ Yok'}")
    
    # Eğer hala None geliyorsa, doğrudan değerleri ata
    if not TELEGRAM_TOKEN:
        print("⚠️ Environment variables'dan alınamadı, doğrudan değer atanıyor...")
        TELEGRAM_TOKEN = "8321992478:AAFBdiIyGflYWp3RB4G0jllxKyNZSOTHcKA"
        GOOGLE_CREDENTIALS_PATH = "credentials.json"
        SPREADSHEET_ID = "1RBOzb89dlyEE0J9mFI38qFRtXOLVQeSZi6knRAWUvKw"
    
    # Bu kontrol kısmını kaldır
    # if not all([TELEGRAM_TOKEN, GOOGLE_CREDENTIALS_PATH, SPREADSHEET_ID]):
    #     print("❌ Gerekli çevre değişkenleri ayarlanmamış!")
    #     print("Gerekli değişkenler:")
    #     print("- TELEGRAM_BOT_TOKEN")
    #     print("- GOOGLE_CREDENTIALS_PATH") 
    #     print("- SPREADSHEET_ID")
    #     return
    
    try:
        # TaskBot instance'ını oluştur
        task_bot = TaskBot(TELEGRAM_TOKEN, GOOGLE_CREDENTIALS_PATH, SPREADSHEET_ID)
        
        # Telegram bot uygulamasını oluştur
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Komut handler'larını ekle
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("ekle", add_task_command))
        application.add_handler(CommandHandler("liste", list_tasks_command))
        application.add_handler(CommandHandler("bugun", today_tasks_command))
        application.add_handler(CommandHandler("tamamla", complete_task_command))
        
        print("🤖 Bot başlatılıyor...")
        
        # Bot'u çalıştır
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Bot çalıştırılırken hata: {e}")
        print(f"❌ Bot başlatılırken hata oluştu: {e}")

if __name__ == '__main__':
    main()
