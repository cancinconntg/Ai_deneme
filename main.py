# -*- coding: utf-8 -*-

import asyncio
import json
import os
import traceback  # Hata ayıklama için eklendi
from datetime import datetime

import bleach
import markdown
import telegram
from google import generativeai as genai  # Google AI kütüphanesi
from pyrogram import Client, filters   # Pyrogram kütüphanesi ve filtreler
from pyrogram.enums import ChatType
from pyrogram.errors import PeerIdInvalid
# from pyrogram.raw.functions.messages import GetDialogs # Dialogs listeleme için gerekli olabilir, şimdilik kapalı
# from pyrogram.raw.types import InputPeerEmpty # Gerekli olabilir, şimdilik kapalı
from telegram import Update
from telegram.constants import ParseMode # ParseMode import edildi
from telegram.ext import (Application, CallbackContext, CommandHandler,
                          MessageHandler, filters as tg_filters) # Telegram Ext filtreleri yeniden adlandırıldı

# --- Yapılandırma (Ortam Değişkenlerinden Yükleme) ---
# Heroku veya benzeri ortamlar için doğrudan ortam değişkenlerinden okuma
print("➡️ Ortam değişkenleri okunuyor...")
try:
    admin_id_str = os.getenv("ADMIN_ID")
    if not admin_id_str:
        raise ValueError("ADMIN_ID ortam değişkeni bulunamadı veya boş.")
    admin_id = int(admin_id_str)

    TG_api_id = os.getenv("TG_API_ID")
    if not TG_api_id: raise ValueError("TG_API_ID ortam değişkeni eksik.")

    TG_api_hash = os.getenv("TG_API_HASH")
    if not TG_api_hash: raise ValueError("TG_API_HASH ortam değişkeni eksik.")

    TGbot_token = os.getenv("TG_BOT_TOKEN")
    if not TGbot_token: raise ValueError("TG_BOT_TOKEN ortam değişkeni eksik.")

    AI_api_key = os.getenv("AI_API_KEY")
    if not AI_api_key: raise ValueError("AI_API_KEY ortam değişkeni eksik.")

    # String Session ortam değişkeni (ZORUNLU)
    TG_string_session = os.getenv("TG_STRING_SESSION")
    if not TG_string_session:
        raise ValueError("TG_STRING_SESSION ortam değişkeni bulunamadı. Bot çalışamaz.")

    config_vars = [admin_id, TG_api_id, TG_api_hash, TGbot_token, AI_api_key, TG_string_session]
    print("✅ Tüm gerekli ortam değişkenleri başarıyla yüklendi.")

except ValueError as e:
    print(f"❌ Kritik Hata: Yapılandırma yüklenemedi. Eksik veya geçersiz ortam değişkeni: {e}")
    exit(1) # Eksik yapılandırma ile devam etme


# --- Sabitler ve Global Değişkenler ---
AI_DEFAULT_PROMPT = "Bu sohbetteki ana konuları, fikirleri, kişileri vb. çok kısa bir şekilde, maddeler halinde, formatlama yapmadan özetle."
MESSAGE_FETCH_DELAY = 0.3  # API limitlerini aşmamak için Pyrogram istekleri arasındaki saniye cinsinden gecikme
ALLOWED_HTML_TAGS = ['b', 'i', 'u', 's', 'strike', 'del', 'code', 'pre', 'a', 'blockquote', 'strong', 'em', 'tg-spoiler'] # İzin verilen HTML etiketleri
GEMINI_MODEL_NAME = "gemini-1.5-flash" # Kullanılacak Gemini modeli

# --- İstemci Başlatma ---
try:
    print("⏳ Gemini AI istemcisi başlatılıyor...")
    genai.configure(api_key=AI_api_key)
    AI_client = genai.GenerativeModel(model_name=GEMINI_MODEL_NAME)
    # Bağlantı testi (isteğe bağlı ama önerilir)
    AI_client.generate_content("test bağlantısı")
    print("✅ Gemini AI istemcisi başarıyla başlatıldı.")
except Exception as e:
     print(f"❌ Kritik Hata: Gemini AI istemcisi başlatılamadı: {e}")
     exit(1)

try:
    print("⏳ Pyrogram kullanıcı bot istemcisi (String Session ile) başlatılıyor...")
    # Pyrogram Client'ı api_id, api_hash VE session_string ile başlat
    # "my_userbot" adı, session dosyası kullanılmasa bile Pyrogram tarafından dahili olarak kullanılır.
    userbotTG_client = Client(
        "my_userbot",
        api_id=TG_api_id,
        api_hash=TG_api_hash,
        session_string=TG_string_session # Yüklenen string session kullanılıyor
    )
    print("✅ Pyrogram kullanıcı bot istemcisi tanımlandı (bağlantı bekleniyor).")
except Exception as e:
    print(f"❌ Kritik Hata: Pyrogram istemcisi başlatılamadı: {e}")
    exit(1)

try:
    print("⏳ Telegram bot istemcisi (python-telegram-bot) başlatılıyor...")
    botTG_client_builder = Application.builder().token(TGbot_token)
    botTG_client = botTG_client_builder.build()
    print("✅ Telegram bot istemcisi başarıyla başlatıldı.")
except Exception as e:
    print(f"❌ Kritik Hata: Telegram bot istemcisi başlatılamadı: {e}")
    exit(1)


# --- Global Depolama ---
dialog_history = {} # Kullanıcı bazında AI sohbet geçmişini saklar
last_fetched_chat_history = "Sohbet geçmişi henüz çekilmedi." # En son çekilen sohbet geçmişini saklar

# --- Yardımcı Fonksiyonlar ---

def get_chat_icon_and_link(chat):
    """Sohbet türüne göre ikon ve doğrudan bağlantı oluşturur."""
    chat_id_str = str(chat.id)
    # -100 ön ekini kaldır (süpergruplar/kanallar için)
    link_chat_id = chat_id_str.replace('-100', '') if chat_id_str.startswith('-100') else chat_id_str

    if chat.type == ChatType.PRIVATE:
        icon = "👤"
        direct_link = f"tg://user?id={chat.id}"
        if chat.username:
            direct_link = f"https://t.me/{chat.username}" # Kullanıcı adı varsa öncelikli
    elif chat.type == ChatType.GROUP:
        icon = "🫂"
        direct_link = f"https://t.me/c/{link_chat_id}/-1" # Genel grup link formatı
        if chat.invite_link: direct_link = chat.invite_link # Davet linki varsa kullan
    elif chat.type == ChatType.SUPERGROUP:
        icon = "👥"
        if chat.username:
            direct_link = f"https://t.me/{chat.username}"
        else:
            # Özel süpergruplar için link formatı
            direct_link = f"https://t.me/c/{link_chat_id}/-1" # Mesaj ID'si ile daha iyi çalışabilir
    elif chat.type == ChatType.CHANNEL:
        icon = "📢"
        if chat.username:
            direct_link = f"https://t.me/{chat.username}"
        else:
            # Özel kanallar için link formatı
            direct_link = f"https://t.me/c/{link_chat_id}/-1"
    elif chat.type == ChatType.BOT:
        icon = "🤖"
        direct_link = f"https://t.me/{chat.username}" if chat.username else f"tg://user?id={chat.id}"
    else:
        icon = "❓"
        direct_link = ""
    return icon, direct_link

def format_time_since(dt_object):
    """Bir datetime nesnesinden bu yana geçen süreyi kullanıcı dostu şekilde formatlar."""
    if not dt_object: return "bilinmeyen zaman önce"
    now = datetime.now(dt_object.tzinfo) # Zaman dilimi farkındalığı
    time_since = now - dt_object
    days = time_since.days
    seconds = time_since.seconds

    if days > 0:
        return f"{days} gün önce"
    elif seconds >= 3600:
        hours = seconds // 3600
        return f"{hours} saat önce"
    elif seconds >= 60:
        minutes = seconds // 60
        return f"{minutes} dakika önce"
    else:
        return "az önce"

def sanitize_html(text):
    """Markdown metnini HTML'e çevirir ve Telegram'da güvenli gösterim için temizler."""
    try:
        # 1. Markdown'dan HTML'e dönüştür
        html_content = markdown.markdown(text)
        # 2. Bleach ile HTML'i temizle
        cleaned_html = bleach.clean(
            html_content,
            tags=ALLOWED_HTML_TAGS,
            strip=True  # İzin verilmeyen etiketleri kaldır
        )
        return cleaned_html
    except Exception as e:
        print(f"⚠️ HTML temizleme hatası: {e}")
        # Hata durumunda güvenli bir metin döndür
        return bleach.clean(text, tags=[], strip=True)


def log_any_user(update: Update) -> None:
    """Gelen mesajları konsola loglar ve admin dışı kullanıcılardan gelirse admin'e bildirir."""
    if not update or not update.message: # Mesaj içermeyen güncellemeleri (örn: kanal post düzenlemeleri) yoksay
        return

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    user = update.message.from_user
    if not user: # Kullanıcı bilgisi olmayan durumları ele al (nadiren)
        print(f"⚠️ [{current_time}] Kullanıcı bilgisi olmayan mesaj alındı.")
        return

    username = f"@{user.username}" if user.username else "(kullanıcı adı yok)"
    user_id = user.id
    user_name = (user.first_name or '') + ' ' + (user.last_name or '')
    message_text = update.message.text if update.message.text else f"({update.message.effective_attachment.__class__.__name__ if update.message.effective_attachment else 'metin olmayan mesaj'})" # Eklentiyi tanımla

    # Konsola logla
    print(f"\n💬 [{current_time}] ID:{user_id} {username} ({user_name.strip()}):\n   {message_text}")

    # Mesaj admin'den değilse admin'e bildir
    if user_id != admin_id:
        print(f"⚠️ Admin olmayan kullanıcıdan mesaj alındı: {user_id}")
        notification_text = (
            f"⚠️ Bilinmeyen kullanıcıdan mesaj!\n"
            f"👤 {user_name.strip()}\n"
            f"{username}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"Mesaj aşağıdadır:"
        )
        # Asenkron görevler ana işleyiciyi engellemez
        asyncio.create_task(send_message_to_admin(notification_text))
        asyncio.create_task(forward_message_to_admin(update))

async def send_message_to_admin(text: str):
    """Admin'e metin mesajı gönderir."""
    bot = telegram.Bot(token=TGbot_token)
    try:
        await bot.send_message(chat_id=admin_id, text=text, parse_mode=ParseMode.HTML)
        print(f"✅ Bildirim admin'e gönderildi.")
    except Exception as e:
        print(f"❌ Admin'e mesaj gönderilirken hata oluştu: {e}")

async def forward_message_to_admin(update: Update):
    """Kullanıcının mesajını admin'e iletir."""
    if not update.message: return
    bot = telegram.Bot(token=TGbot_token)
    try:
        await bot.copy_message(
            chat_id=admin_id,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        print(f"✅ Mesaj admin'e iletildi.")
    except Exception as e:
        print(f"❌ Mesaj admin'e iletilirken hata oluştu: {e}")


# --- Komut İşleyiciler ---

async def start_command(update: Update, context: CallbackContext) -> None:
    """/start komutunu işler."""
    log_any_user(update)
    await update.message.reply_text('Merhaba! Ben hazırım.')

async def ping_command(update: Update, context: CallbackContext) -> None:
    """/ping komutunu işler, bağlantı durumunu kontrol eder."""
    log_any_user(update)
    if update.message.from_user.id != admin_id:
        await update.message.reply_text("⛔ Erişim reddedildi.")
        return

    results = []
    status_message = await update.message.reply_text("⏳ Tanılama çalıştırılıyor...")

    # 1. Telegram Bot Bağlantısı (python-telegram-bot)
    try:
        bot_info = await context.bot.get_me()
        results.append(f"✅ Telegram Bot (@{bot_info.username}): Bağlı")
    except Exception as e:
        results.append(f"❌ Telegram Bot Hatası: {e}")

    # 2. Pyrogram Kullanıcı Bot Bağlantısı
    try:
        if not userbotTG_client.is_connected:
             await status_message.edit_text(status_message.text + "\n⏳ Pyrogram istemcisi bağlanıyor...")
             await userbotTG_client.connect() # Bağlı değilse bağlanmayı dene
        user_info = await userbotTG_client.get_me()
        results.append(f"✅ Pyrogram Userbot ({user_info.first_name} / @{user_info.username}): Bağlı")
    except Exception as e:
        results.append(f"❌ Pyrogram Userbot Hatası: {e}")
        # Hata durumunda bağlantıyı kesip tekrar denemek isteyebilirsiniz
        # try: await userbotTG_client.disconnect() except Exception: pass

    # 3. Gemini AI İstemci Bağlantısı
    try:
        # Basit bir test sorgusu
        ai_test_response = AI_client.generate_content("ping testi")
        # Yanıtın içeriğini kontrol et
        if ai_test_response.text and "test" in ai_test_response.text.lower():
             results.append("✅ Gemini AI İstemcisi: Yanıt verdi")
        elif ai_test_response.candidates and ai_test_response.candidates[0].content:
             results.append("✅ Gemini AI İstemcisi: Yanıt verdi (candidates yolu)")
        else:
             print(f"⚠️ Gemini AI Test Yanıtı:\n{ai_test_response}") # Detaylı loglama
             results.append("⚠️ Gemini AI İstemcisi: Bağlandı ancak beklenmedik yanıt alındı.")
    except Exception as e:
        results.append(f"❌ Gemini AI İstemci Hatası: {e}")

    # Tanılama sonuçlarını gönder
    diagnostic_results = "\n".join(results)
    await status_message.edit_text(
        f"<b>Bot Durumu:</b> 👌<blockquote expandable>{diagnostic_results}</blockquote>",
        parse_mode=ParseMode.HTML
    )

async def list_chats_command(update: Update, context: CallbackContext) -> None:
    """/list komutunu işler, son sohbetleri listeler."""
    log_any_user(update)
    if update.message.from_user.id != admin_id:
        await update.message.reply_text("⛔ Erişim reddedildi.")
        return

    limit = 10 # Varsayılan limit
    filter_type_enum = None # None tüm türleri ifade eder
    filter_type_str = "tüm" # Kullanıcı geri bildirimi için

    # Argümanları işle: /list [limit] [tür]
    if len(context.args) > 0:
        try:
            limit = int(context.args[0])
            if limit <= 0: limit = 10 # Geçersizse varsayılana dön
        except ValueError:
            await update.message.reply_text("⚠️ Geçersiz limit. Varsayılan (10) kullanılıyor. Kullanım: /list [limit] [tür]")
            limit = 10

    if len(context.args) > 1:
        filter_input = context.args[1].lower()
        filter_mapping = {
            # Özel
            "p": ChatType.PRIVATE, "private": ChatType.PRIVATE, "özel": ChatType.PRIVATE,
            "ozel": ChatType.PRIVATE, "kisi": ChatType.PRIVATE, "kişi": ChatType.PRIVATE,
            "dm": ChatType.PRIVATE, "ls": ChatType.PRIVATE,
            # Grup/Süpergrup
            "g": "group", "group": "group", "grup": "group", "gruplar": "group",
            "supergroup": "group", "süpergrup": "group", "sohbet": "group", "chat": "group",
            # Kanal
            "c": ChatType.CHANNEL, "channel": ChatType.CHANNEL, "kanal": ChatType.CHANNEL,
            "kanallar": ChatType.CHANNEL,
            # Bot
            "b": ChatType.BOT, "bot": ChatType.BOT, "botlar": ChatType.BOT,
        }
        if filter_input in filter_mapping:
            mapped_value = filter_mapping[filter_input]
            if mapped_value == "group":
                filter_type_enum = [ChatType.GROUP, ChatType.SUPERGROUP] # Gruplar için özel durum
                filter_type_str = "grup/süpergrup"
            else:
                filter_type_enum = mapped_value
                filter_type_str = filter_type_enum.name.lower() # örn. PRIVATE -> private
        else:
             await update.message.reply_text(f"⚠️ Bilinmeyen filtre türü '{filter_input}'. Tüm türler gösteriliyor.")

    status_message = await update.message.reply_text(f"⏳ Son {limit} {filter_type_str} sohbet getiriliyor...")

    try:
        if not userbotTG_client.is_connected: await userbotTG_client.connect() # Bağlı değilse bağlan

        dialog_items = []
        fetched_count = 0
        async for dialog in userbotTG_client.get_dialogs():
            if dialog.chat is None: continue # Bazen chat bilgisi None gelebilir

            # Filtreyi uygula
            if filter_type_enum:
                 if isinstance(filter_type_enum, list): # Grup filtresi
                     if dialog.chat.type not in filter_type_enum: continue
                 elif dialog.chat.type != filter_type_enum: # Tek tür filtresi
                     continue

            # Sohbet detaylarını al
            chat = dialog.chat
            display_name = chat.title or (chat.first_name or '') + ' ' + (chat.last_name or '')
            display_name = display_name.strip() or "Bilinmeyen Sohbet"
            icon, direct_link = get_chat_icon_and_link(chat)

            dialog_items.append(
                f"• <a href='{direct_link}'>{icon} {display_name}</a>\n"
                f"  <code>{chat.id}</code>"
                f"{' (@' + chat.username + ')' if chat.username else ''}"
            )

            fetched_count += 1
            if fetched_count >= limit: break
            # await asyncio.sleep(0.05) # Çok fazla sohbet varsa limitleri aşmamak için küçük bekleme

        if dialog_items:
            result_text = f"<b>Son {fetched_count} {filter_type_str} sohbet:</b>\n\n" + "\n".join(dialog_items)
        else:
            result_text = f"⚠️ Hiç {filter_type_str} sohbet bulunamadı."

        await status_message.edit_text(result_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    except Exception as e:
        await status_message.edit_text(f"❌ Sohbetler getirilirken bir hata oluştu: {e}\n\n{traceback.format_exc()}") # Hata detayını ekle
        print(f"❌ /list Hatası: {e}")
        traceback.print_exc()


async def ai_query_command(update: Update, context: CallbackContext) -> None:
    """/ai komutunu işler, doğrudan Gemini'ye soru sorar."""
    log_any_user(update)
    user_id = update.message.from_user.id

    if user_id != admin_id:
        await update.message.reply_text("⛔ Erişim reddedildi.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Lütfen /ai komutundan sonra sorgunuzu yazın. Örnek: `/ai Güncel haberleri özetle`")
        return

    query = " ".join(context.args)
    processing_message = await update.message.reply_text("🧠 Düşünüyorum...")

    # Kullanıcı için diyalog geçmişini başlat veya al
    if user_id not in dialog_history:
        dialog_history[user_id] = [] # Temiz geçmiş başlat

    # Kullanıcı sorgusunu geçmişe ekle (basit format)
    dialog_history[user_id].append({"role": "user", "parts": [query]})

    # Geçmiş uzunluğunu yönetilebilir tut (örn: son 10 tur = 20 mesaj)
    # Gemini API'si genellikle daha uzun geçmişleri yönetebilir, ancak sınırlama faydalıdır.
    max_history_items = 20 # Rol + içerik çifti olarak
    if len(dialog_history[user_id]) > max_history_items:
        dialog_history[user_id] = dialog_history[user_id][-max_history_items:]

    try:
        print(f"🧠 AI'ye gönderiliyor (kullanıcı {user_id}):\n{dialog_history[user_id]}") # AI girdisini logla
        # Gemini'ye isteği gönder (geçmişi kullanarak)
        ai_conversation = AI_client.start_chat(history=dialog_history[user_id][:-1]) # Son kullanıcı mesajı hariç geçmiş
        ai_response = await ai_conversation.send_message_async(dialog_history[user_id][-1]['parts']) # Son mesajı gönder

        response_text = ai_response.text

        # AI yanıtını geçmişe ekle
        dialog_history[user_id].append({"role": "model", "parts": [response_text]})

        # Yanıtı Telegram için temizle ve formatla
        formatted_response = sanitize_html(response_text)

        # Yanıtı geri gönder
        await processing_message.edit_text(
            f"🤖 <b>AI Yanıtı:</b>\n<blockquote>{formatted_response}</blockquote>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        print(f"🤖 AI Yanıtı (kullanıcı {user_id}):\n{response_text}") # AI çıktısını logla

    except Exception as e:
        error_message = f"❌ AI sorgunuz işlenirken bir hata oluştu: {e}"
        await processing_message.edit_text(error_message)
        print(f"❌ AI Hatası (kullanıcı {user_id}): {e}")
        traceback.print_exc()
        # Hata durumunda son kullanıcı/AI çiftini geçmişten kaldır?
        if user_id in dialog_history and len(dialog_history[user_id]) > 0:
            # En son eklenen kullanıcı ve potansiyel model yanıtını kaldır
            last_entry = dialog_history[user_id].pop()
            if last_entry["role"] != "user" and len(dialog_history[user_id]) > 0:
                 dialog_history[user_id].pop() # Önceki kullanıcıyı da kaldır

async def ai_clean_command(update: Update, context: CallbackContext) -> None:
    """/ai_clean komutunu işler, AI diyalog geçmişini temizler."""
    log_any_user(update)
    user_id = update.message.from_user.id

    if user_id != admin_id:
         await update.message.reply_text("⛔ Erişim reddedildi.")
         return

    if user_id in dialog_history:
        del dialog_history[user_id]
        await update.message.reply_text("🗑️ Bu sohbet için AI diyalog geçmişi temizlendi.")
        print(f"🗑️ Kullanıcı {user_id} için AI diyalog geçmişi temizlendi.")
    else:
        await update.message.reply_text("ℹ️ Temizlenecek AI diyalog geçmişi bulunamadı.")


async def json_command(update: Update, context: CallbackContext) -> None:
    """/json komutunu işler, test JSON dosyası gönderir."""
    log_any_user(update)
    if update.message.from_user.id != admin_id:
         await update.message.reply_text("⛔ Erişim reddedildi.")
         return

    test_json_data = {
        "zamanDamgasi": datetime.now().isoformat(),
        "kullanici": {
            "id": update.message.from_user.id,
            "kullaniciAdi": update.message.from_user.username,
            "adminMi": update.message.from_user.id == admin_id
        },
        "mesaj": "Bot tarafından oluşturulan örnek JSON verisi.",
        "durum": "OK"
    }
    file_path = "test_verisi.json"
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(test_json_data, file, indent=4, ensure_ascii=False)

        await context.bot.send_document(
            chat_id=update.message.chat_id,
            document=open(file_path, "rb"),
            filename=file_path,
            caption="📄 İşte test JSON dosyanız."
        )
        print(f"📄 Test JSON {update.message.chat_id} adresine gönderildi")
    except Exception as e:
        await update.message.reply_text(f"❌ JSON dosyası oluşturulurken veya gönderilirken hata: {e}")
        print(f"❌ /json Hatası: {e}")
    finally:
        # Dosyayı temizle
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Geçici dosya {file_path} silinemedi: {e}")

async def id_command(update: Update, context: CallbackContext) -> None:
    """/id komutunu işler, yanıtlanan mesajın bilgilerini verir."""
    log_any_user(update)
    if update.message.from_user.id != admin_id:
         await update.message.reply_text("⛔ Erişim reddedildi.")
         return

    if update.message.reply_to_message:
        replied_message = update.message.reply_to_message
        sender = replied_message.from_user
        sender_info = "Bilinmeyen Gönderici"
        if sender:
             sender_info = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
             sender_info += f" (@{sender.username})" if sender.username else ""
             sender_info += f" [ID: <code>{sender.id}</code>]"
        elif replied_message.sender_chat: # Kanal olarak gönderilen mesajlar
             sender_chat = replied_message.sender_chat
             sender_info = f"{sender_chat.title} (Kanal) [ID: <code>{sender_chat.id}</code>]"


        await update.message.reply_html( # Kolay formatlama için reply_html kullan
            f"ℹ️ Yanıtlanan Mesaj Bilgisi:\n"
            f"  <b>Mesaj ID:</b> <code>{replied_message.message_id}</code>\n"
            f"  <b>Gönderen:</b> {sender_info}\n"
            f"  <b>Sohbet ID:</b> <code>{replied_message.chat_id}</code>"
        )
    else:
        await update.message.reply_text("⚠️ /id komutunu kullanmak için bir mesaja yanıt verin.")

# --- Ana Mesaj İşleyici (Sohbet Geçmişi & AI Özeti) ---

async def handle_chat_request(update: Update, context: CallbackContext) -> None:
    """Sohbet ID'si ve isteğe bağlı olarak mesaj sayısı/AI istemi içeren mesajları işler."""
    log_any_user(update)
    # Bu fonksiyon sadece admin içindir
    if update.message.from_user.id != admin_id:
        # Admin olmayanları sessizce yoksay veya genel bir yanıt ver
        # await update.message.reply_text("Üzgünüm, sadece admin'in isteklerini işleyebilirim.")
        return

    global last_fetched_chat_history # Çekilen geçmişi saklamak için global değişkene referans

    # --- Girdi Ayrıştırma ---
    try:
        lines = update.message.text.strip().split("\n")
        if not lines: raise ValueError("Boş mesaj.")

        # Satır 1: Sohbet ID veya @kullanıcıadı (zorunlu)
        chat_id_input = lines[0].strip()
        try:
            # Tam sayıya dönüştürmeyi dene, ancak kullanıcı adı olabileceği için orijinali sakla
            chat_id = int(chat_id_input)
        except ValueError:
            chat_id = chat_id_input # String olarak tut (örn: @kullaniciadi, me)

        # Satır 2: Mesaj Sayısı (isteğe bağlı, varsayılan 20)
        msg_count = 20 # Varsayılan mesaj sayısı
        if len(lines) > 1 and lines[1].strip():
            try:
                msg_count_in = int(lines[1].strip())
                if msg_count_in > 0:
                    msg_count = min(msg_count_in, 3000) # Pyrogram limiti genellikle 3000 civarı
                else:
                    await update.message.reply_text("⚠️ Mesaj sayısı pozitif olmalı. Varsayılan (20) kullanılıyor.")
            except ValueError:
                 await update.message.reply_text("⚠️ Geçersiz mesaj sayısı. Varsayılan (20) kullanılıyor.")

        # Satır 3+: AI İstemi (isteğe bağlı, varsayılan istem)
        ai_question = AI_DEFAULT_PROMPT
        if len(lines) > 2:
            ai_question = "\n".join(lines[2:]).strip() # Kalan satırları birleştir
            if not ai_question: # Birleştirdikten sonra boş istemi kontrol et
                ai_question = AI_DEFAULT_PROMPT

    except Exception as e:
        await update.message.reply_text(
            f"❌ Geçersiz girdi formatı.\n"
            f"Lütfen şunu sağlayın:\n"
            f"Satır 1: Sohbet ID veya @kullanıcıadı\n"
            f"Satır 2: Mesaj sayısı (isteğe bağlı, varsayılan 20)\n"
            f"Satır 3+: AI için sorunuz/isteminiz (isteğe bağlı)"
        )
        print(f"❌ Girdi ayrıştırma hatası: {e}")
        return

    # --- İşleme ---
    status_message = await update.message.reply_text(f"⏳ '{chat_id_input}' sohbetine erişiliyor...", parse_mode=ParseMode.HTML)
    chat_info_text = ""
    file_path = None # file_path'ı başlangıçta None yap

    try:
        if not userbotTG_client.is_connected:
            print("Pyrogram bağlanıyor...")
            await status_message.edit_text(status_message.text + "\n⏳ Kullanıcı botu bağlanıyor...")
            await userbotTG_client.connect()
            print("Pyrogram bağlandı.")

        # --- Sohbet Bilgisini Al ---
        print(f"Sohbet bilgisi alınıyor: {chat_id}")
        chat = await userbotTG_client.get_chat(chat_id)
        print(f"Sohbet bilgisi alındı: {chat.title or chat.first_name}")
        icon, direct_link = get_chat_icon_and_link(chat)
        chat_title = chat.title or (chat.first_name or '') + ' ' + (chat.last_name or '')
        chat_title = chat_title.strip() or "Bilinmeyen Sohbet Adı"
        chat_info_text = (
            f"<a href='{direct_link}'>{icon} <b>{chat_title}</b></a>\n"
            f"🆔 <code>{chat.id}</code> | Tür: {chat.type.name}\n"
            f"📝 Son {msg_count} mesaj getiriliyor...\n"
        )
        await status_message.edit_text(chat_info_text + "█▒▒▒▒▒▒▒▒▒ 0%", parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        # --- Mesajları Getir ---
        messages_raw = []
        progress_update_threshold = max(1, msg_count // 10) # İlerlemeyi kabaca 10 kez güncelle
        print(f"{msg_count} mesaj getiriliyor...")
        async for i, msg in enumerate(userbotTG_client.get_chat_history(chat.id, limit=msg_count)):
            messages_raw.append(msg)

            # İlerleme çubuğunu daha seyrek güncelle (performans için)
            if (i + 1) % progress_update_threshold == 0 or (i + 1) == msg_count:
                percentage = (i + 1) / msg_count
                bar_length = 10
                filled_length = int(bar_length * percentage)
                bar = '█' * filled_length + '▒' * (bar_length - filled_length)
                try: # Telegram API'lerini floodlamaktan kaçın
                    await status_message.edit_text(
                        chat_info_text + f"{bar} {int(percentage * 100)}%",
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                except Exception as e: # Güncellemeler sırasında olası flood wait hatalarını yoksay
                    # print(f" Minor error updating progress: {e}") # İsteğe bağlı loglama
                    pass # Hata durumunda devam et

            await asyncio.sleep(MESSAGE_FETCH_DELAY) # Temel gecikme

        print(f"{len(messages_raw)} mesaj getirildi.")

        if not messages_raw:
            await status_message.edit_text(chat_info_text + "\n⚠️ Sohbet boş veya erişilemez görünüyor.", parse_mode=ParseMode.HTML)
            last_fetched_chat_history = "Sohbet boş veya erişilemez." # Global durumu güncelle
            return # Mesaj yoksa işlemeyi durdur

        # --- Mesajları İşle ve Formatla ---
        formatted_history_preview = [] # Önizleme için kısa format
        full_history_for_ai = [] # AI bağlamı için daha detaylı

        for msg in reversed(messages_raw): # En eskiden başlayarak işle
            sender_name = "Bilinmeyen"
            sender_id = "N/A"
            if msg.from_user:
                sender_name = (msg.from_user.first_name or '') + ' ' + (msg.from_user.last_name or '')
                sender_name = sender_name.strip() or f"Kullanıcı {msg.from_user.id}" # Yedek isim
                sender_id = msg.from_user.id
            elif msg.sender_chat: # Kanal olarak gönderilen mesajlar
                 sender_name = msg.sender_chat.title or f"Sohbet {msg.sender_chat.id}"
                 sender_id = msg.sender_chat.id

            message_time = msg.date.strftime('%Y-%m-%d %H:%M') if msg.date else "Bilinmeyen zaman"
            content_desc = "(Desteklenmeyen mesaj türü)" # Varsayılan

            # İçerik türünü belirle
            if msg.text:
                content_desc = msg.text
            elif msg.photo:
                content_desc = f"[Fotoğraf] {msg.caption or ''}"
            elif msg.sticker:
                content_desc = f"[Çıkartma {msg.sticker.emoji or ''}]"
            elif msg.video:
                content_desc = f"[Video] {msg.caption or ''}"
            elif msg.voice:
                content_desc = f"[Sesli M. ~{msg.voice.duration}s] {msg.caption or ''}"
            elif msg.video_note:
                content_desc = f"[Görüntülü M. ~{msg.video_note.duration}s]"
            elif msg.document:
                content_desc = f"[Belge: {msg.document.file_name or 'N/A'}] {msg.caption or ''}"
            elif msg.animation:
                content_desc = "[GIF Animasyon]"
            elif msg.location:
                content_desc = f"[Konum: {msg.location.latitude:.4f}, {msg.location.longitude:.4f}]"
            elif msg.poll:
                options = ", ".join([f'"{opt.text}"' for opt in msg.poll.options])
                content_desc = f"[Anket: '{msg.poll.question}' ({options})]"
            elif msg.new_chat_members:
                names = ', '.join([(m.first_name or f'ID:{m.id}') for m in msg.new_chat_members])
                content_desc = f"[Olay: {names} katıldı]"
            elif msg.left_chat_member:
                name = msg.left_chat_member.first_name or f'ID:{msg.left_chat_member.id}'
                content_desc = f"[Olay: {name} ayrıldı]"
            # Daha fazla tür eklenebilir (contact, game, invoice vb.)

            # Önizleme için kısa format
            formatted_history_preview.append(f"[{sender_name} @ {message_time}]:\n{content_desc}\n")
            # AI için detaylı format
            full_history_for_ai.append({
                "sender_id": sender_id,
                "sender_name": sender_name,
                "time": message_time,
                "content": content_desc.strip(),
                "msg_id": msg.id # İstenirse mesaj ID'sini dahil et
            })

        # Global geçmişi güncelle (ayrı olarak çağrılırsa AI_answer tarafından kullanılır)
        # İdeal olarak, geçmişi global yerine doğrudan fonksiyona geçmek daha iyidir.
        last_fetched_chat_history = json.dumps(full_history_for_ai, indent=2, ensure_ascii=False) # AI için JSON string olarak sakla

        # --- Çıktıyı Hazırla ---
        first_msg = messages_raw[-1] # Getirilen en eski mesaj
        first_msg_link = ""
        # Mesaj bağlantısını oluştur (genel/özel süpergrup/kanallar için güvenilir çalışır)
        if chat.type in [ChatType.SUPERGROUP, ChatType.CHANNEL] and chat.id < 0:
             # Süpergrup/kanal ID'leri için -100 ön ekini işle
             link_chat_id = str(chat.id).replace("-100", "")
             first_msg_link = f"https://t.me/c/{link_chat_id}/{first_msg.id}"

        time_since_str = format_time_since(first_msg.date)
        header = f"📜 <a href='{direct_link}'>{icon} <b>{chat_title}</b></a> için Geçmiş (<code>{chat.id}</code>)\n"
        header += f" Son {len(messages_raw)} mesaj gösteriliyor.\n"
        if first_msg_link:
             header += f" En eski mesaj <a href='{first_msg_link}'>🔗</a> {time_since_str}.\n"
        else:
             header += f" En eski mesaj {time_since_str}.\n"


        # --- Önizleme Oluştur ---
        # Mesajları birleştir, Telegram limitlerini aşmamak için toplam uzunluğu sınırla
        preview_limit = 3800 # Başlık ve altbilgi için yer bırak
        chat_history_preview_text = ""
        temp_preview = "\n".join(formatted_history_preview)
        if len(header) + len(temp_preview) < preview_limit:
            chat_history_preview_text = temp_preview
        else:
             # Çok uzunsa basit kırpma (daha gelişmiş mantık eklenebilir)
             available_chars = preview_limit - len(header) - 50 # '...kırpıldı...' için ayır
             chat_history_preview_text = temp_preview[:available_chars] + "\n... (önizleme kırpıldı)"

        result_text = header + f"<blockquote expandable>{chat_history_preview_text}</blockquote>"

        await status_message.edit_text(result_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        print(f"✅ {chat.id} sohbeti için sohbet geçmişi önizlemesi gönderildi")

        # --- Tam Geçmişi JSON'a Kaydet ---
        # Dosya adını temizle
        safe_chat_name = "".join(c if c.isalnum() or c in (' ', '_') else '_' for c in chat_title).rstrip().replace(' ', '_')
        safe_chat_name = safe_chat_name[:50] # Uzunluğu sınırla
        file_path = f"tg_gecmis_{safe_chat_name}_{chat.id}_{len(messages_raw)}msj.json"

        chat_json_data = {
            "sohbet_bilgisi": {
                "id": chat.id,
                "baslik": chat_title,
                "tur": chat.type.name,
                "kullanici_adi": chat.username,
                "link": direct_link,
            },
            "getirme_detaylari":{
                "sayi": len(messages_raw),
                "zamanDamgasi": datetime.now().isoformat(),
            },
            "mesajlar": full_history_for_ai # Detaylı listeyi kullan
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(chat_json_data, f, indent=2, ensure_ascii=False)
            print(f"JSON dosyası '{file_path}' diske yazıldı.")

            # --- JSON Dosyasını Gönder ---
            await context.bot.send_document(
                chat_id=admin_id, # Admin'e gönder
                document=open(file_path, "rb"),
                filename=file_path,
                caption=f"📄 '{chat_title}' sohbetinin tam geçmişi ({len(messages_raw)} mesaj)"
            )
            print(f"✅ Tam geçmiş JSON '{file_path}' admin'e gönderildi.")

        except Exception as e:
            print(f"❌ Geçmiş JSON kaydedilirken/gönderilirken hata: {e}")
            await update.message.reply_text(f"⚠️ Tam geçmiş JSON dosyası kaydedilemedi veya gönderilemedi: {e}")

        # --- AI'yi Çağır ---
        # Getirilen geçmişi (JSON string olarak) ve kullanıcının sorusunu ilet
        print("AI yanıtı isteniyor...")
        await AI_answer(update, context, AI_question=ai_question, chat_history_json=last_fetched_chat_history)


    except PeerIdInvalid:
        await status_message.edit_text(f"❌ Hata: '{chat_id_input}' ID'li sohbet bulunamadı veya erişim reddedildi.", parse_mode=ParseMode.HTML)
        print(f"❌ PeerIdInvalid: {chat_id_input}")
        last_fetched_chat_history = "Hata: Sohbet bulunamadı veya erişilemez."
    except ConnectionError as e:
         await status_message.edit_text(f"❌ Bağlantı Hatası: Pyrogram istemcisi bağlanamadı. Lütfen String Session'ı kontrol edin ve botu yeniden başlatın.\nHata: {e}", parse_mode=ParseMode.HTML)
         print(f"❌ Pyrogram Bağlantı Hatası: {e}")
         # Botu durdurmak veya yeniden başlatmayı denemek isteyebilirsiniz
         # Örneğin Heroku'da bu otomatik olabilir.
    except Exception as e:
        error_details = traceback.format_exc() # Hatanın tam izini al
        await status_message.edit_text(f"❌ Beklenmedik bir hata oluştu: {e}\n\nDetaylar loglarda.", parse_mode=ParseMode.HTML)
        print(f"❌ handle_chat_request içinde beklenmedik hata ({chat_id_input}): {e}\n{error_details}")
        last_fetched_chat_history = f"Hata: {e}" # Hata durumunu global değişkende sakla
    finally:
        # --- Temizlik ---
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"🗑️ Geçici dosya '{file_path}' silindi.")
            except Exception as e:
                print(f"⚠️ Geçici dosya '{file_path}' silinemedi: {e}")


async def AI_answer(update: Update, context: CallbackContext, AI_question: str, chat_history_json: str = None) -> None:
    """AI'ye bir sorgu gönderir, potansiyel olarak sohbet geçmişi bağlamını içerir."""
    print("🤖 AI yanıtı oluşturuluyor...")
    ai_status_message = await update.message.reply_text("🧠 AI'ye soruluyor...") # Orijinal kullanıcı mesajına yanıt ver

    # Sağlanmışsa geçmişi kullan, yoksa globale geri dön (daha az ideal)
    history_context = chat_history_json if chat_history_json else last_fetched_chat_history
    if not history_context or history_context == "Sohbet geçmişi henüz çekilmedi.":
         history_context = "(Bağlam için belirli bir sohbet geçmişi sağlanmadı)"
    elif isinstance(history_context, str) and history_context.startswith("Hata:"):
         history_context = f"(Önceki adımda hata oluştuğu için sohbet geçmişi kullanılamıyor: {history_context})"


    # AI için son istemi oluştur
    # Modelin büyük JSON'ları kaldırabileceğini varsayıyoruz, ancak gerekirse kırpma yapılabilir.
    final_prompt = f"Aşağıdaki sohbet geçmişine dayanarak (JSON formatında):\n\n```json\n{history_context[:10000]}\n```\n\nLütfen şu soruyu yanıtla: {AI_question}" # Geçmişi kırpabiliriz

    try:
        print(f"🧠 AI'ye gönderiliyor:\n{final_prompt[:500]}...") # Kırpılmış istemi logla
        ai_response = await AI_client.generate_content_async(
             contents=final_prompt
             # safety_settings=... # İstenirse güvenlik ayarları eklenebilir
        )

        response_text = ai_response.text
        formatted_response = sanitize_html(response_text) # Yanıtı temizle

        await ai_status_message.edit_text(
            f"🤖 <b>AI Yanıtı:</b>\n<blockquote>{formatted_response}</blockquote>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        print(f"🤖 AI yanıtı alındı.")

    except Exception as e:
        error_message = f"❌ AI yanıtı alınırken bir hata oluştu: {e}"
        await ai_status_message.edit_text(error_message)
        print(f"❌ AI işleme hatası: {e}")
        traceback.print_exc()


# --- Genel Mesaj Loglayıcı (Yedek) ---
async def log_generic_message(update: Update, context: CallbackContext) -> None:
    """Diğer işleyiciler tarafından yakalanmayan herhangi bir mesajı loglar."""
    log_any_user(update)
    # İsteğe bağlı olarak burada diğer mesaj türleri için mantık eklenebilir


# --- Ana Çalıştırma ---

async def post_init(application: Application) -> None:
    """Bot başlatıldıktan sonra çalışacak asenkron görevler."""
    print("Pyrogram istemcisi bağlanıyor (post_init)...")
    try:
        await userbotTG_client.start()
        my_info = await userbotTG_client.get_me()
        print(f"✅ Pyrogram istemcisi başarıyla bağlandı: {my_info.first_name} (@{my_info.username})")
        await send_message_to_admin(f"🚀 Bot başarıyla başlatıldı ve Pyrogram kullanıcısı (@{my_info.username}) olarak bağlandı!")
    except ConnectionError as e:
        print(f"❌ KRİTİK: Pyrogram istemcisi bağlanamadı! String session geçersiz olabilir. Hata: {e}")
        await send_message_to_admin(f"❌ KRİTİK: Bot başlatıldı ancak Pyrogram istemcisi bağlanamadı! String session'ı kontrol edin. Hata: {e}")
        # Bağlantı kurulamazsa botun çalışmasını durdurmak mantıklı olabilir.
        # application.stop() # Bu, başlatma sırasında sorun yaratabilir.
    except Exception as e:
        print(f"❌ Pyrogram başlatılırken beklenmedik hata: {e}")
        await send_message_to_admin(f"❌ Bot başlatıldı ancak Pyrogram başlatılırken hata oluştu: {e}")
        traceback.print_exc()


def main() -> None:
    """İşleyicileri ayarlar ve botu çalıştırır."""
    print("🔧 Telegram bot işleyicileri ayarlanıyor...")

    # --- İşleyicileri Kaydet ---
    # Komutlar (Erişim kontrolü işleyici içinde yapılır)
    botTG_client.add_handler(CommandHandler("start", start_command))
    botTG_client.add_handler(CommandHandler("ping", ping_command))
    botTG_client.add_handler(CommandHandler("list", list_chats_command))
    botTG_client.add_handler(CommandHandler("ai", ai_query_command))
    botTG_client.add_handler(CommandHandler("ai_clean", ai_clean_command))
    botTG_client.add_handler(CommandHandler("json", json_command))
    botTG_client.add_handler(CommandHandler("id", id_command))

    # Mesaj İşleyicileri
    # 1. Sohbet istekleri için özel işleyici (sadece admin, metin, komut değil)
    #    Potansiyel ID/kullanıcı adı ile başlayan mesajları eşleştirmek için regex kullanır
    chat_request_filter = tg_filters.TEXT & ~tg_filters.COMMAND & tg_filters.User(user_id=admin_id) # & filters.Regex(r'^(-?\d+|@\w+).*') # Regex şimdilik kapalı, her admin mesajı denensin
    botTG_client.add_handler(MessageHandler(chat_request_filter, handle_chat_request))

    # 2. Diğer tüm mesaj türleri veya admin dışı metin mesajları için yedek loglayıcı
    botTG_client.add_handler(MessageHandler(tg_filters.ALL & ~tg_filters.User(user_id=admin_id), log_generic_message)) # Admin dışı her şeyi logla

    # Başlatma sonrası görevleri ekle
    botTG_client.post_init = post_init

    print("🚀 Telegram bot polling başlatılıyor...")
    try:
        # Botu çalıştır
        botTG_client.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"❌ Bot polling hatası nedeniyle durdu: {e}")
        traceback.print_exc()
    finally:
        # --- Temizlik ---
        # Pyrogram istemcisini düzgünce durdur (eğer çalışıyorsa)
        print("👋 Kapanış işlemleri...")
        if userbotTG_client.is_connected:
            print("⏳ Pyrogram istemcisi durduruluyor...")
            try:
                 # Asenkron durdurmayı çalıştırmak için event loop gerekebilir
                 loop = asyncio.get_event_loop()
                 if loop.is_running():
                      loop.create_task(userbotTG_client.stop())
                      # Görevin tamamlanmasını beklemek için karmaşıklaşabilir,
                      # şimdilik sadece görevi oluşturup çıkıyoruz.
                 else:
                      loop.run_until_complete(userbotTG_client.stop())
                 print("✅ Pyrogram istemcisi durduruldu.")
            except Exception as e:
                 print(f"⚠️ Pyrogram istemcisini durdururken hata: {e}")


if __name__ == '__main__':
    print("==========================================")
    print("     Telegram Geçmiş Analiz Botu      ")
    print("==========================================")
    # Ana bot mantığını çalıştır
    main()
    print("👋 Betik sonlandırıldı.")

