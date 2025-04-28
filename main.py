# -*- coding: utf-8 -*-

import asyncio
import json
import os
import traceback
import logging
from datetime import datetime

# --- Gerekli Kütüphaneler ---
# pip install pyrogram TgCrypto python-telegram-bot>=21.0.1 google-generativeai>=0.5.4 httpx>=0.24.1,<0.28.0 pytz # pytz eklendi

# Pyrogram (Kullanıcı Botu için)
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ChatType, ParseMode as PyroParseMode
from pyrogram.errors import UserNotParticipant, UserIsBlocked, PeerIdInvalid

# python-telegram-bot (Kontrol Botu için)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters as ptb_filters, PicklePersistence
)
from telegram.constants import ParseMode as TGParseMode

# Google Gemini AI
from google import generativeai as genai
from google.api_core.exceptions import GoogleAPIError # Hata yakalama için

# Diğerleri
import pytz # Zaman dilimi için

# --- Logging Ayarları ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Çok konuşkan httpx loglarını azalt
logger = logging.getLogger(__name__)

# --- Yapılandırma (Ortam Değişkenleri) ---
logger.info("➡️ Ortam değişkenleri okunuyor...")
try:
    ADMIN_ID = int(os.environ['ADMIN_ID'])
    TG_API_ID = int(os.environ['TG_API_ID'])
    TG_API_HASH = os.environ['TG_API_HASH']
    TG_BOT_TOKEN = os.environ['TG_BOT_TOKEN'] # Kontrol botu token'ı
    AI_API_KEY = os.environ['AI_API_KEY']
    TG_STRING_SESSION = os.environ['TG_STRING_SESSION'] # Userbot string session
    # İsteğe bağlı: Persistence dosyası adı
    PERSISTENCE_FILE = os.getenv('PERSISTENCE_FILE', 'bot_persistence.pickle')
    SETTINGS_FILE = os.getenv('SETTINGS_FILE', 'settings.json')

    logger.info("✅ Gerekli ortam değişkenleri başarıyla yüklendi.")
except (KeyError, ValueError) as e:
    logger.critical(f"❌ Kritik Hata: Eksik veya geçersiz ortam değişkeni: {e}")
    exit(1)

# --- Global Değişkenler ve Durum Yönetimi ---
# Bu değişkenler `bot_data` içinde saklanacak (PicklePersistence ile)
# Default ayarları burada tanımlayalım, persistence yoksa bunlar kullanılır.
DEFAULT_SETTINGS = {
    "is_listening": False,
    "language": "tr",
    "prompt_config": {
        "base_prompt": "Ben {age} yaşında, esprili, {swearing} argo kullanan, eğlenceli bir {gender}. Ekran başında değilim.",
        "age": 23,
        "gender": "erkeğim", # "kadınım" veya başka bir ifade olabilir
        "use_swearing": True,
        "make_jokes": True,
        "can_insult": False, # Hakaret etme ayarı
        "custom_suffix": "- Afk Mesajı" # Mesaj sonuna eklenecek imza
    },
    "interacted_users": {}, # {user_id: {"name": "...", "link": "...", "type": "dm/mention/reply", "timestamp": ...}}
    "ai_model": "gemini-1.5-flash"
}

# Ayarları Yükle/Kaydet (PicklePersistence bunu büyük ölçüde otomatik yapar)
# Ancak program başlangıcında/durdurulduğunda JSON'a yedeklemek iyi olabilir.
# Şimdilik persistence'a güvenelim.

# Dil Dosyası (Basit Dictionary)
localization = {
    "tr": {
        "start_message": "🤖 Merhaba! AFK Yanıt Botu Ayarları.\n\n Mevcut Durum: `{status}`\n Aktif Dil: 🇹🇷 Türkçe",
        "settings_menu_title": "⚙️ Ayarlar Menüsü",
        "listening_status": "Dinleme Durumu",
        "language_select": "🌍 Dil Seçimi",
        "prompt_settings": "📝 Prompt Ayarları",
        "back_button": " geri",
        "status_on": "AÇIK ✅",
        "status_off": "KAPALI ❌",
        "toggle_listening": "Dinlemeyi Aç/Kapat",
        "select_language_prompt": "Lütfen bir dil seçin:",
        "prompt_menu_title": "📝 Prompt Ayar Menüsü",
        "set_age": " Yaş Ayarla ({age})",
        "set_gender": " Cinsiyet ({gender})",
        "toggle_swearing": " Küfür/Argo ({status})",
        "toggle_jokes": " Espri Yap ({status})",
        "toggle_insult": " Hakaret Et ({status})",
        "edit_suffix": " Mesaj Sonu ({suffix})",
        "enter_age": "Lütfen yaşınızı girin (sayı olarak):",
        "enter_gender": "Lütfen cinsiyet ifadenizi girin (örn: erkeğim, kadınım):",
        "enter_suffix": "Lütfen mesaj sonuna eklenecek ifadeyi girin:",
        "age_updated": "✅ Yaş güncellendi: {age}",
        "gender_updated": "✅ Cinsiyet güncellendi: {gender}",
        "suffix_updated": "✅ Mesaj sonu güncellendi: {suffix}",
        "setting_updated": "✅ Ayar güncellendi.",
        "error_invalid_input": "❌ Geçersiz giriş.",
        "afk_signature": "- Afk Mesajı", # Bu da prompt_config'den gelmeli
        "list_title": "💬 Son Etkileşimler:",
        "list_empty": "ℹ️ Henüz kayıtlı etkileşim yok.",
        "list_format_dm": "<a href=\"tg://user?id={user_id}\">{name}</a> (Özel Mesaj)",
        "list_format_group": "<a href=\"{link}\">{name}</a> ({type})", # type: mention/reply
        "error_ai": "❌ AI yanıtı alınırken hata oluştu: {error}",
        "error_sending": "❌ Mesaj gönderilirken hata oluştu: {error}",
        "listening_started": "✅ Dinleme modu AKTİF.",
        "listening_stopped": "❌ Dinleme modu DEVRE DIŞI.",
        "unknown_command": "❓ Bilinmeyen komut.",
        "prompt_base": "Ben {age} yaşında, {gender}.{jokes}{swearing}{insult} Genellikle ekran başında olmam.",
        "prompt_jokes_on": " Espriler yaparım, eğlenceliyim.",
        "prompt_jokes_off": "",
        "prompt_swearing_on": " Argo ve gerektiğinde küfür kullanırım.",
        "prompt_swearing_off": " Küfürlü konuşmam.",
        "prompt_insult_on": " Bana bulaşana karşılık veririm, hakaret edebilirim.",
        "prompt_insult_off": " Hakaret etmem.",
    },
    "en": {
        "start_message": "🤖 Hello! AFK Reply Bot Settings.\n\n Current Status: `{status}`\n Active Language: 🇬🇧 English",
        "settings_menu_title": "⚙️ Settings Menu",
        "listening_status": "Listening Status",
        "language_select": "🌍 Select Language",
        "prompt_settings": "📝 Prompt Settings",
        "back_button": " Back",
        "status_on": "ON ✅",
        "status_off": "OFF ❌",
        "toggle_listening": "Toggle Listening",
        "select_language_prompt": "Please select a language:",
        "prompt_menu_title": "📝 Prompt Settings Menu",
        "set_age": " Set Age ({age})",
        "set_gender": " Set Gender ({gender})",
        "toggle_swearing": " Use Swearing ({status})",
        "toggle_jokes": " Make Jokes ({status})",
        "toggle_insult": " Allow Insults ({status})",
        "edit_suffix": " Edit Suffix ({suffix})",
        "enter_age": "Please enter your age (as a number):",
        "enter_gender": "Please enter your gender expression (e.g., male, female):",
        "enter_suffix": "Please enter the suffix to append to messages:",
        "age_updated": "✅ Age updated: {age}",
        "gender_updated": "✅ Gender updated: {gender}",
        "suffix_updated": "✅ Suffix updated: {suffix}",
        "setting_updated": "✅ Setting updated.",
        "error_invalid_input": "❌ Invalid input.",
        "afk_signature": "- AFK Message",
        "list_title": "💬 Recent Interactions:",
        "list_empty": "ℹ️ No interactions recorded yet.",
        "list_format_dm": "<a href=\"tg://user?id={user_id}\">{name}</a> (Direct Message)",
        "list_format_group": "<a href=\"{link}\">{name}</a> ({type})", # type: mention/reply
        "error_ai": "❌ Error getting AI response: {error}",
        "error_sending": "❌ Error sending message: {error}",
        "listening_started": "✅ Listening mode ACTIVE.",
        "listening_stopped": "❌ Listening mode INACTIVE.",
        "unknown_command": "❓ Unknown command.",
        "prompt_base": "I am a {age} year old {gender}.{jokes}{swearing}{insult} I'm usually away from the keyboard.",
        "prompt_jokes_on": " I make jokes, I'm fun.",
        "prompt_jokes_off": "",
        "prompt_swearing_on": " I use slang and swear when necessary.",
        "prompt_swearing_off": " I don't use swear words.",
        "prompt_insult_on": " I talk back to those who mess with me, I can insult.",
        "prompt_insult_off": " I don't insult.",
    },
    "ru": {
        "start_message": "🤖 Привет! Настройки AFK Ответчика.\n\n Текущий Статус: `{status}`\n Активный Язык: 🇷🇺 Русский",
        "settings_menu_title": "⚙️ Меню Настроек",
        "listening_status": "Статус Прослушивания",
        "language_select": "🌍 Выбор Языка",
        "prompt_settings": "📝 Настройки Промпта",
        "back_button": " Назад",
        "status_on": "ВКЛ ✅",
        "status_off": "ВЫКЛ ❌",
        "toggle_listening": "Вкл/Выкл Прослушивание",
        "select_language_prompt": "Пожалуйста, выберите язык:",
        "prompt_menu_title": "📝 Меню Настроек Промпта",
        "set_age": " Установить Возраст ({age})",
        "set_gender": " Установить Пол ({gender})",
        "toggle_swearing": " Использовать Ругательства ({status})",
        "toggle_jokes": " Шутить ({status})",
        "toggle_insult": " Оскорблять ({status})",
        "edit_suffix": " Ред. Суффикс ({suffix})",
        "enter_age": "Пожалуйста, введите ваш возраст (числом):",
        "enter_gender": "Пожалуйста, введите ваше гендерное выражение (напр: мужчина, женщина):",
        "enter_suffix": "Пожалуйста, введите суффикс для добавления к сообщениям:",
        "age_updated": "✅ Возраст обновлен: {age}",
        "gender_updated": "✅ Пол обновлен: {gender}",
        "suffix_updated": "✅ Суффикс обновлен: {suffix}",
        "setting_updated": "✅ Настройка обновлена.",
        "error_invalid_input": "❌ Неверный ввод.",
        "afk_signature": "- AFK Сообщение",
        "list_title": "💬 Недавние Взаимодействия:",
        "list_empty": "ℹ️ Записей о взаимодействиях пока нет.",
        "list_format_dm": "<a href=\"tg://user?id={user_id}\">{name}</a> (Личное сообщение)",
        "list_format_group": "<a href=\"{link}\">{name}</a> ({type})", # type: mention/reply
        "error_ai": "❌ Ошибка при получении ответа ИИ: {error}",
        "error_sending": "❌ Ошибка при отправке сообщения: {error}",
        "listening_started": "✅ Режим прослушивания АКТИВЕН.",
        "listening_stopped": "❌ Режим прослушивания НЕАКТИВЕН.",
        "unknown_command": "❓ Неизвестная команда.",
        "prompt_base": "Мне {age} лет, я {gender}.{jokes}{swearing}{insult} Обычно меня нет за клавиатурой.",
        "prompt_jokes_on": " Я шучу, я веселый(ая).",
        "prompt_jokes_off": "",
        "prompt_swearing_on": " Я использую сленг и ругаюсь, когда это необходимо.",
        "prompt_swearing_off": " Я не ругаюсь.",
        "prompt_insult_on": " Я отвечаю тем, кто пристает ко мне, могу оскорбить.",
        "prompt_insult_off": " Я не оскорбляю.",
    }
}

# --- Yardımcı Fonksiyonlar ---

def get_text(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs) -> str:
    """Yerelleştirilmiş metni alır."""
    lang = context.bot_data.get('settings', {}).get('language', 'tr')
    template = localization.get(lang, localization['tr']).get(key, f"<{key}>")
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Metin formatlamada eksik anahtar: {e} (anahtar: {key})")
        return template # Formatlama yapamasa bile şablonu döndür

def get_current_settings(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Mevcut ayarları alır veya varsayılanları döndürür."""
    # bot_data'dan ayarları al, yoksa DEFAULT_SETTINGS'i kullan ve kaydet
    if 'settings' not in context.bot_data:
        context.bot_data['settings'] = DEFAULT_SETTINGS.copy() # Kopyasını al
        logger.info("Varsayılan ayarlar yüklendi ve persistence'a kaydedildi.")
    return context.bot_data['settings']

def save_settings(context: ContextTypes.DEFAULT_TYPE, settings: dict):
    """Ayarları persistence'a kaydeder."""
    context.bot_data['settings'] = settings
    # PicklePersistence bunu otomatik yapar, ancak manuel kaydetme gerekirse:
    # await context.application.persistence.flush()
    logger.info("Ayarlar persistence'a kaydedildi.")

def get_yes_no(status: bool) -> str:
    """Boolean durumu Evet/Hayır veya Açık/Kapalı'ya çevirir (dil desteği eklenebilir)."""
    # Şimdilik basitçe evet/hayır kullanalım
    return "Evet ✅" if status else "Hayır ❌"


def generate_full_prompt(prompt_config: dict, lang: str) -> str:
    """Ayarlara göre tam AI prompt'unu oluşturur."""
    p_conf = prompt_config
    jokes_text = get_text(None, "prompt_jokes_on", lang=lang) if p_conf.get('make_jokes', True) else get_text(None, "prompt_jokes_off", lang=lang)
    swearing_text = get_text(None, "prompt_swearing_on", lang=lang) if p_conf.get('use_swearing', True) else get_text(None, "prompt_swearing_off", lang=lang)
    insult_text = get_text(None, "prompt_insult_on", lang=lang) if p_conf.get('can_insult', False) else get_text(None, "prompt_insult_off", lang=lang)

    # Temel prompt'u dil dosyasına göre oluştur
    base = localization.get(lang, localization['tr']).get('prompt_base', DEFAULT_SETTINGS['prompt_config']['base_prompt'])

    # Formatlama yaparak prompt'u oluştur
    try:
        full_prompt = base.format(
            age=p_conf.get('age', 23),
            gender=p_conf.get('gender', 'erkeğim'),
            jokes=jokes_text,
            swearing=swearing_text,
            insult=insult_text
        )
        return full_prompt
    except KeyError as e:
        logger.error(f"Prompt formatlamada eksik anahtar: {e}. Prompt config: {p_conf}")
        # Hata durumunda varsayılan veya basit bir prompt döndür
        return f"Ben {p_conf.get('age', 23)} yaşında biriyim. Genellikle meşgulüm."


# --- Kontrol Botu (python-telegram-bot) İşleyicileri ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start komutu - Ana menüyü gösterir."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Bu botu sadece sahibi kullanabilir.")
        return

    settings = get_current_settings(context)
    lang = settings.get('language', 'tr')
    status = get_text(context, "status_on") if settings.get('is_listening', False) else get_text(context, "status_off")

    keyboard = [
        [InlineKeyboardButton(get_text(context, "toggle_listening"), callback_data='toggle_listening')],
        [InlineKeyboardButton(get_text(context, "language_select"), callback_data='select_language')],
        [InlineKeyboardButton(get_text(context, "prompt_settings"), callback_data='prompt_settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        get_text(context, "start_message", status=status),
        reply_markup=reply_markup,
        parse_mode=TGParseMode.MARKDOWN_V2 # `status` için formatlama
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ana menüyü mesajı düzenleyerek gösterir."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return # Sadece admin

    settings = get_current_settings(context)
    lang = settings.get('language', 'tr')
    status = get_text(context, "status_on") if settings.get('is_listening', False) else get_text(context, "status_off")

    keyboard = [
        [InlineKeyboardButton(get_text(context, "toggle_listening"), callback_data='toggle_listening')],
        [InlineKeyboardButton(get_text(context, "language_select"), callback_data='select_language')],
        [InlineKeyboardButton(get_text(context, "prompt_settings"), callback_data='prompt_settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(
            get_text(context, "start_message", status=status),
            reply_markup=reply_markup,
            parse_mode=TGParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Ana menü düzenlenirken hata: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline butonlara basıldığında çalışır."""
    query = update.callback_query
    await query.answer() # Butona basıldığını kullanıcıya bildirir
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return

    callback_data = query.data
    settings = get_current_settings(context)
    prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])

    logger.info(f"Buton geri çağrısı alındı: {callback_data}")

    # --- Ana Menü Butonları ---
    if callback_data == 'toggle_listening':
        settings['is_listening'] = not settings.get('is_listening', False)
        save_settings(context, settings)
        status_text = get_text(context, "listening_started") if settings['is_listening'] else get_text(context, "listening_stopped")
        await query.message.reply_text(status_text) # Ayrı mesaj olarak durumu bildir
        await main_menu(update, context) # Menüyü güncelle

    elif callback_data == 'select_language':
        keyboard = [
            [
                InlineKeyboardButton("🇹🇷 Türkçe", callback_data='lang_tr'),
                InlineKeyboardButton("🇬🇧 English", callback_data='lang_en'),
                InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru'),
            ],
            [InlineKeyboardButton(f"🔙{get_text(context, 'back_button')}", callback_data='main_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(get_text(context, "select_language_prompt"), reply_markup=reply_markup)

    elif callback_data == 'prompt_settings':
        await prompt_settings_menu(update, context) # Prompt ayar menüsünü göster

    # --- Dil Seçim Butonları ---
    elif callback_data.startswith('lang_'):
        lang_code = callback_data.split('_')[1]
        if lang_code in localization:
            settings['language'] = lang_code
            save_settings(context, settings)
            logger.info(f"Dil değiştirildi: {lang_code}")
            await main_menu(update, context) # Yeni dilde ana menüyü göster
        else:
            logger.warning(f"Geçersiz dil kodu: {lang_code}")

    # --- Prompt Ayar Butonları ---
    elif callback_data == 'prompt_set_age':
        context.user_data['next_action'] = 'set_age' # Bir sonraki mesajın yaş için olduğunu işaretle
        await query.edit_message_text(get_text(context, "enter_age"))

    elif callback_data == 'prompt_set_gender':
        context.user_data['next_action'] = 'set_gender'
        await query.edit_message_text(get_text(context, "enter_gender"))

    elif callback_data == 'prompt_toggle_swearing':
        prompt_config['use_swearing'] = not prompt_config.get('use_swearing', True)
        settings['prompt_config'] = prompt_config
        save_settings(context, settings)
        await query.answer(get_text(context, "setting_updated")) # Kısa bildirim
        await prompt_settings_menu(update, context) # Menüyü güncelle

    elif callback_data == 'prompt_toggle_jokes':
        prompt_config['make_jokes'] = not prompt_config.get('make_jokes', True)
        settings['prompt_config'] = prompt_config
        save_settings(context, settings)
        await query.answer(get_text(context, "setting_updated"))
        await prompt_settings_menu(update, context)

    elif callback_data == 'prompt_toggle_insult':
        prompt_config['can_insult'] = not prompt_config.get('can_insult', False)
        settings['prompt_config'] = prompt_config
        save_settings(context, settings)
        await query.answer(get_text(context, "setting_updated"))
        await prompt_settings_menu(update, context)

    elif callback_data == 'prompt_edit_suffix':
        context.user_data['next_action'] = 'set_suffix'
        await query.edit_message_text(get_text(context, "enter_suffix"))

    # --- Geri Butonları ---
    elif callback_data == 'main_menu':
        await main_menu(update, context)


async def prompt_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt ayarları menüsünü gösterir/düzenler."""
    settings = get_current_settings(context)
    prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])

    yes_no_swearing = get_yes_no(prompt_config.get('use_swearing', True))
    yes_no_jokes = get_yes_no(prompt_config.get('make_jokes', True))
    yes_no_insult = get_yes_no(prompt_config.get('can_insult', False))
    current_age = prompt_config.get('age', 23)
    current_gender = prompt_config.get('gender', 'erkeğim')
    current_suffix = prompt_config.get('custom_suffix', '- Afk Mesajı')

    keyboard = [
        [InlineKeyboardButton(get_text(context, "set_age", age=current_age), callback_data='prompt_set_age')],
        [InlineKeyboardButton(get_text(context, "set_gender", gender=current_gender), callback_data='prompt_set_gender')],
        [InlineKeyboardButton(get_text(context, "toggle_swearing", status=yes_no_swearing), callback_data='prompt_toggle_swearing')],
        [InlineKeyboardButton(get_text(context, "toggle_jokes", status=yes_no_jokes), callback_data='prompt_toggle_jokes')],
        [InlineKeyboardButton(get_text(context, "toggle_insult", status=yes_no_insult), callback_data='prompt_toggle_insult')],
        [InlineKeyboardButton(get_text(context, "edit_suffix", suffix=current_suffix), callback_data='prompt_edit_suffix')],
        [InlineKeyboardButton(f"🔙{get_text(context, 'back_button')}", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Eğer query varsa mesajı düzenle, yoksa yeni mesaj at (nadiren gerekir)
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(get_text(context, "prompt_menu_title"), reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Prompt menüsü düzenlenirken hata: {e}")
    elif update.message:
         await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=reply_markup)


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt ayarları için metin girişlerini işler."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return # Sadece admin

    action = context.user_data.pop('next_action', None)
    if not action:
        # Belki normal bir mesajdır, şimdilik görmezden gel
        # Veya bilinmeyen komut mesajı gönderilebilir
        # await update.message.reply_text(get_text(context, "unknown_command"))
        return

    text = update.message.text.strip()
    settings = get_current_settings(context)
    prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])

    if action == 'set_age':
        try:
            age = int(text)
            if 0 < age < 150:
                prompt_config['age'] = age
                settings['prompt_config'] = prompt_config
                save_settings(context, settings)
                await update.message.reply_text(get_text(context, "age_updated", age=age))
                # Ayarlar menüsünü tekrar göster
                await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=InlineKeyboardMarkup(prompt_settings_menu_keyboard(context))) # Keyboard'ı tekrar oluşturmamız lazım
            else:
                await update.message.reply_text(get_text(context, "error_invalid_input") + " (Yaş 1-149 arası olmalı)")
        except ValueError:
            await update.message.reply_text(get_text(context, "error_invalid_input") + " (Lütfen sadece sayı girin)")

    elif action == 'set_gender':
        if text:
            prompt_config['gender'] = text[:30] # Çok uzun olmasın
            settings['prompt_config'] = prompt_config
            save_settings(context, settings)
            await update.message.reply_text(get_text(context, "gender_updated", gender=text[:30]))
            await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=InlineKeyboardMarkup(prompt_settings_menu_keyboard(context)))
        else:
            await update.message.reply_text(get_text(context, "error_invalid_input"))

    elif action == 'set_suffix':
        if text:
            prompt_config['custom_suffix'] = text[:50] # Suffix uzunluğunu sınırla
            settings['prompt_config'] = prompt_config
            save_settings(context, settings)
            await update.message.reply_text(get_text(context, "suffix_updated", suffix=text[:50]))
            await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=InlineKeyboardMarkup(prompt_settings_menu_keyboard(context)))
        else:
            # Boş suffix'e izin verilebilir veya hata verilebilir
            prompt_config['custom_suffix'] = ""
            settings['prompt_config'] = prompt_config
            save_settings(context, settings)
            await update.message.reply_text(get_text(context, "suffix_updated", suffix="[Boş]"))
            await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=InlineKeyboardMarkup(prompt_settings_menu_keyboard(context)))

    # Ayarlar menüsünü tekrar göstermek için yardımcı fonksiyon
    async def show_prompt_menu_again(update, context):
        settings = get_current_settings(context)
        prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
        yes_no_swearing = get_yes_no(prompt_config.get('use_swearing', True))
        yes_no_jokes = get_yes_no(prompt_config.get('make_jokes', True))
        yes_no_insult = get_yes_no(prompt_config.get('can_insult', False))
        current_age = prompt_config.get('age', 23)
        current_gender = prompt_config.get('gender', 'erkeğim')
        current_suffix = prompt_config.get('custom_suffix', '- Afk Mesajı')

        keyboard = [
            [InlineKeyboardButton(get_text(context, "set_age", age=current_age), callback_data='prompt_set_age')],
            [InlineKeyboardButton(get_text(context, "set_gender", gender=current_gender), callback_data='prompt_set_gender')],
            [InlineKeyboardButton(get_text(context, "toggle_swearing", status=yes_no_swearing), callback_data='prompt_toggle_swearing')],
            [InlineKeyboardButton(get_text(context, "toggle_jokes", status=yes_no_jokes), callback_data='prompt_toggle_jokes')],
            [InlineKeyboardButton(get_text(context, "toggle_insult", status=yes_no_insult), callback_data='prompt_toggle_insult')],
            [InlineKeyboardButton(get_text(context, "edit_suffix", suffix=current_suffix), callback_data='prompt_edit_suffix')],
            [InlineKeyboardButton(f"🔙{get_text(context, 'back_button')}", callback_data='main_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=reply_markup)

    # Eğer action işlendiyse menüyü göster
    if action in ['set_age', 'set_gender', 'set_suffix']:
         await show_prompt_menu_again(update, context)


# --- Kullanıcı Botu (Pyrogram) İşleyicileri ---

# Pyrogram istemcisini global yapalım ki işleyiciler erişebilsin
user_bot_client: Client = None

# Gemini AI istemcisini yapılandıralım
try:
    genai.configure(api_key=AI_API_KEY)
    ai_model_instance = genai.GenerativeModel(DEFAULT_SETTINGS['ai_model'])
    logger.info(f"Gemini AI Modeli ({DEFAULT_SETTINGS['ai_model']}) yapılandırıldı.")
except Exception as e:
    logger.critical(f"Gemini AI yapılandırılamadı: {e}")
    ai_model_instance = None # Hata durumunda modeli None yap

async def get_pyrogram_settings(app: Application) -> dict:
    """PTB persistence'dan Pyrogram için ayarları alır."""
    context = ContextTypes.DEFAULT_TYPE(application=app, chat_id=ADMIN_ID, user_id=ADMIN_ID) # Geçici context
    return get_current_settings(context)

async def save_pyrogram_settings(app: Application, settings: dict):
    """Pyrogram'dan gelen ayarları PTB persistence'a kaydeder."""
    context = ContextTypes.DEFAULT_TYPE(application=app, chat_id=ADMIN_ID, user_id=ADMIN_ID) # Geçici context
    save_settings(context, settings)


@Client.on_message(filters.private | filters.mentioned | filters.reply, group=1)
async def handle_user_message(client: Client, message: Message):
    """Özel mesajları, mentionları ve yanıtlara gelen mesajları işler."""
    global user_bot_client # Kontrol botuna erişim için
    ptb_app = user_bot_client.ptb_app # PTB application nesnesini al

    settings = await get_pyrogram_settings(ptb_app)
    my_id = client.me.id

    # 1. Kendi mesajlarımı veya admin komutlarını yoksay (komutlar ayrı handle edilecek)
    if message.from_user and message.from_user.id == my_id:
        # Ancak admin komutları için ayrı filtre daha iyi olur
        # logger.debug("Kendi mesajım, yoksayılıyor.")
        return

    # 2. Dinleme modu kapalıysa işlem yapma
    if not settings.get('is_listening', False):
        # logger.debug("Dinleme modu kapalı, mesaj yoksayılıyor.")
        return

    # 3. Mesajın relevant olup olmadığını kontrol et
    is_relevant = False
    interaction_type = "unknown"
    sender = message.from_user or message.sender_chat # Gönderen kullanıcı veya kanal

    if not sender:
        logger.warning(f"Mesajda gönderici bilgisi yok: {message.id} in {message.chat.id}")
        return # Gönderici yoksa işlem yapma

    sender_id = sender.id
    sender_name = getattr(sender, 'title', getattr(sender, 'first_name', f"ID:{sender_id}"))
    chat_id = message.chat.id
    message_id = message.id

    # Link oluşturma (basitleştirilmiş)
    message_link = message.link # Pyrogram link sağlar

    # a) Özel mesaj mı? (ve gönderen ben değilim)
    if message.chat.type == ChatType.PRIVATE and sender_id != my_id:
        is_relevant = True
        interaction_type = "dm"
        logger.info(f"Özel mesaj algılandı from {sender_name} ({sender_id})")

    # b) Mention içeriyor mu?
    elif message.mentioned:
        is_relevant = True
        interaction_type = "mention"
        logger.info(f"Mention algılandı from {sender_name} ({sender_id}) in {chat_id}")

    # c) Benim mesajıma yanıt mı?
    elif message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == my_id:
        is_relevant = True
        interaction_type = "reply"
        logger.info(f"Yanıt algılandı from {sender_name} ({sender_id}) in {chat_id}")

    # 4. Relevant değilse çık
    if not is_relevant:
        return

    # --- Relevant Mesaj İşleme ---
    logger.info(f"İşlenecek mesaj: {message.text[:50] if message.text else '[Metin Yok]'} (Link: {message_link})")

    # Kullanıcıyı etkileşim listesine ekle/güncelle
    now_utc = datetime.now(pytz.utc) # Zaman damgası için UTC kullan
    interacted_users = settings.get('interacted_users', {})
    interacted_users[str(sender_id)] = {
        "name": sender_name,
        "link": message_link,
        "type": interaction_type,
        "timestamp": now_utc.isoformat()
    }
    settings['interacted_users'] = interacted_users
    await save_pyrogram_settings(ptb_app, settings) # Ayarları kaydet

    # AI'ye göndermek için bağlam oluştur
    # TODO: Daha gelişmiş bağlam (önceki mesajlar vb.) eklenebilir
    context_text = f"Kullanıcı '{sender_name}' ({interaction_type}) şunu yazdı: {message.text or '[Mesaj metni yok]'}"

    # Prompt'u oluştur
    prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
    lang = settings.get('language', 'tr')
    full_prompt = generate_full_prompt(prompt_config, lang)

    # AI'ye gönderilecek tam içerik
    ai_content = f"Senin kişilik promptun:\n---\n{full_prompt}\n---\n\nSana gelen mesaj ve bağlam:\n---\n{context_text}\n---\n\nBu mesaja uygun, promptuna sadık kalarak bir yanıt ver:"

    # Yanıt oluşturma ve gönderme
    try:
        if not ai_model_instance:
             raise Exception("AI modeli başlatılmamış.")

        logger.info("AI'ye istek gönderiliyor...")
        # TODO: Gemini API'nin güvenlik ayarları (safety_settings) eklenebilir
        # Güvenlik ayarları küfür vs. engellememesi için ayarlanmalı.
        # response = await ai_model_instance.generate_content_async(ai_content, safety_settings=...)
        response = await ai_model_instance.generate_content_async(ai_content)
        ai_reply_text = response.text
        logger.info(f"AI yanıtı alındı: {ai_reply_text[:100]}...")

        # AFK imzasını ekle
        suffix = prompt_config.get('custom_suffix', get_text(None, "afk_signature", lang=lang))
        final_reply = f"{ai_reply_text}\n\n{suffix}"

        # Yanıtı gönder (kullanıcı botu olarak)
        await client.send_message(
            chat_id=chat_id,
            text=final_reply,
            reply_to_message_id=message_id,
            parse_mode=PyroParseMode.MARKDOWN # Veya HTML, AI çıktısına göre
        )
        logger.info(f"Yanıt gönderildi: {chat_id} / {message_id}")

    except GoogleAPIError as e:
        logger.error(f"Google AI API Hatası: {e}")
        error_text = get_text(None, "error_ai", lang=lang, error=str(e))
        # Belki admin'e de bildirim gönderilebilir
    except Exception as e:
        logger.error(f"AI yanıtı işlenirken veya mesaj gönderilirken hata: {e}")
        logger.error(traceback.format_exc())
        error_text = get_text(None, "error_sending", lang=lang, error=str(e))
        # Belki admin'e bildirim gönderilebilir veya yanıta hata mesajı eklenebilir
        try:
            await client.send_message(ADMIN_ID, f"❌ AFK Yanıt Hatası ({chat_id}): {e}")
        except Exception as admin_err:
            logger.error(f"Admin'e hata mesajı gönderilemedi: {admin_err}")


# Pyrogram için admin komutları
@Client.on_message(filters.me & filters.command(["on", "off", "list"], prefixes="."), group=0)
async def handle_pyrogram_commands(client: Client, message: Message):
    """Kullanıcı botu tarafından gönderilen .on, .off, .list komutlarını işler."""
    global user_bot_client
    ptb_app = user_bot_client.ptb_app

    command = message.command[0].lower()
    settings = await get_pyrogram_settings(ptb_app)
    lang = settings.get('language', 'tr')

    if command == "on":
        if not settings.get('is_listening', False):
            settings['is_listening'] = True
            await save_pyrogram_settings(ptb_app, settings)
            await message.edit_text(get_text(None, "listening_started", lang=lang))
            logger.info("Dinleme modu .on komutuyla AKTİF edildi.")
        else:
            await message.edit_text("ℹ️ Dinleme modu zaten AKTİF.")
            await asyncio.sleep(3)
            await message.delete()


    elif command == "off":
        if settings.get('is_listening', False):
            settings['is_listening'] = False
            await save_pyrogram_settings(ptb_app, settings)
            await message.edit_text(get_text(None, "listening_stopped", lang=lang))
            logger.info("Dinleme modu .off komutuyla DEVRE DIŞI bırakıldı.")
        else:
             await message.edit_text("ℹ️ Dinleme modu zaten DEVRE DIŞI.")
             await asyncio.sleep(3)
             await message.delete()

    elif command == "list":
        interacted = settings.get('interacted_users', {})
        if not interacted:
            await message.edit_text(get_text(None, "list_empty", lang=lang))
            return

        # Kullanıcıları zamana göre sırala (en yeniden en eskiye)
        try:
            sorted_users = sorted(
                interacted.items(),
                key=lambda item: datetime.fromisoformat(item[1].get('timestamp', '1970-01-01T00:00:00+00:00')),
                reverse=True
            )
        except Exception as sort_e:
             logger.error(f"Sıralama hatası: {sort_e}")
             sorted_users = list(interacted.items()) # Sıralama başarısız olursa olduğu gibi al

        list_text = get_text(None, "list_title", lang=lang) + "\n\n"
        count = 0
        max_list_items = 20 # Listeyi çok uzatmamak için sınır

        for user_id_str, data in sorted_users:
            if count >= max_list_items:
                 list_text += f"\n... ve {len(sorted_users) - max_list_items} diğerleri."
                 break

            name = data.get('name', f'ID:{user_id_str}')
            link = data.get('link', None)
            interaction_type = data.get('type', 'unknown')

            try:
                user_id = int(user_id_str)
                if interaction_type == 'dm':
                     list_text += f"• {get_text(None, 'list_format_dm', lang=lang, user_id=user_id, name=name)}\n"
                elif link:
                     # Grup etkileşimleri için genel format
                     list_text += f"• {get_text(None, 'list_format_group', lang=lang, link=link, name=name, type=interaction_type)}\n"
                else:
                     # Link yoksa basit format
                     list_text += f"• {name} ({interaction_type})\n"
                count += 1
            except ValueError:
                 logger.warning(f"Geçersiz kullanıcı ID'si: {user_id_str}")
            except Exception as format_e:
                 logger.error(f"Liste formatlama hatası for {user_id_str}: {format_e}")
                 list_text += f"• {name} (formatlama hatası)\n" # Hatalı girişi belirt
                 count += 1


        # Mesajı düzenleyerek listeyi gönder
        try:
            await message.edit_text(list_text, parse_mode=TGParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
             logger.error(f"Liste gönderilemedi: {e}")
             await message.edit_text(f"❌ Liste oluşturulurken hata: {e}")


    # Komut mesajını kısa süre sonra sil (isteğe bağlı)
    await asyncio.sleep(10)
    try:
        await message.delete()
    except Exception:
        pass # Silinemezse önemli değil


# --- Ana Çalıştırma Fonksiyonu ---

async def main():
    global user_bot_client # Userbot istemcisini global değişkene ata

    # 1. Persistence Ayarları
    # Diskte belirtilen dosyada bot durumunu (sohbet verisi, kullanıcı verisi vb.) saklar.
    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)

    # 2. Kontrol Botu (PTB) Application Oluşturma
    ptb_application = Application.builder() \
        .token(TG_BOT_TOKEN) \
        .persistence(persistence) \
        .build()

    # PTB İşleyicilerini Ekleme
    ptb_application.add_handler(CommandHandler("start", start))
    ptb_application.add_handler(CommandHandler("settings", start)) # Ayarlar için de /start kullan
    ptb_application.add_handler(CallbackQueryHandler(button_callback))
    ptb_application.add_handler(MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND & ptb_filters.User(ADMIN_ID), handle_text_input))

    # 3. Pyrogram İstemcisini Oluşturma ve Başlatma
    user_bot_client = Client(
        "my_afk_userbot", # Session adı (string session kullanılsa da gerekli)
        api_id=TG_API_ID,
        api_hash=TG_API_HASH,
        session_string=TG_STRING_SESSION
        # worker_count=4 # İsteğe bağlı: iş parçacığı sayısı
    )
    # Pyrogram işleyicilerini ekle (decorator ile yapıldı)

    # PTB application nesnesini Pyrogram client'ına ekleyelim ki işleyiciler erişebilsin
    user_bot_client.ptb_app = ptb_application

    # 4. İki Botu Aynı Anda Çalıştırma
    try:
        logger.info("Kontrol botu (PTB) başlatılıyor...")
        await ptb_application.initialize() # Botu başlatmadan önce gerekli hazırlıkları yapar
        logger.info("Pyrogram kullanıcı botu (Userbot) başlatılıyor...")
        await user_bot_client.start()
        my_info = await user_bot_client.get_me()
        logger.info(f"✅ Userbot başarıyla bağlandı: {my_info.first_name} (@{my_info.username})")
        logger.info("Kontrol botu polling başlatılıyor...")
        await ptb_application.start() # Bot komutları dinlemeye başlar
        logger.info("✅ Kontrol botu başarıyla başlatıldı.")
        logger.info("Botlar çalışıyor... Kapatmak için CTRL+C basın.")

        # İki botun da çalışmasını bekle
        await idle() # Pyrogram'ın çalışmasını sağlar

    except ConnectionError as e:
         logger.critical(f"❌ Pyrogram bağlanamadı! String Session geçersiz veya ağ sorunu: {e}")
         # Gerekirse PTB'yi durdur
         if ptb_application.running:
              await ptb_application.stop()
    except Exception as e:
        logger.critical(f"❌ Ana çalıştırma döngüsünde kritik hata: {e}")
        logger.critical(traceback.format_exc())
    finally:
        logger.info("Botlar durduruluyor...")
        # Graceful shutdown
        if user_bot_client and user_bot_client.is_connected:
            logger.info("Pyrogram userbot durduruluyor...")
            await user_bot_client.stop()
            logger.info("Pyrogram userbot durduruldu.")
        if ptb_application and ptb_application.running:
            logger.info("Kontrol botu (PTB) durduruluyor...")
            await ptb_application.stop()
            await ptb_application.shutdown()
            logger.info("Kontrol botu (PTB) durduruldu.")
        logger.info("Tüm işlemler durduruldu.")


if __name__ == "__main__":
    logger.info("==========================================")
    logger.info("     Telegram AFK Yanıt Botu v2         ")
    logger.info("==========================================")
    # Ana asenkron fonksiyonu çalıştır
    asyncio.run(main())
