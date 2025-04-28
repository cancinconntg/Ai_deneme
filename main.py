# -*- coding: utf-8 -*-

import asyncio
import json
import os
import traceback
import logging
from datetime import datetime

# --- Gerekli Kütüphaneler ---
# requirements.txt dosyanıza ekleyin:
# pyrogram>=2.0.106,<3.0.0
# TgCrypto>=1.2.5,<2.0.0  # ÖNEMLİ: Hız ve stabilite için
# python-telegram-bot>=21.0.1,<22.0.0
# google-generativeai>=0.5.4
# httpx>=0.24.1,<0.28.0
# pytz>=2023.3

# Pyrogram (Kullanıcı Botu için)
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ChatType, ParseMode as PyroParseMode
from pyrogram.errors import UserNotParticipant, UserIsBlocked, PeerIdInvalid, ChannelInvalid, ChannelPrivate

# python-telegram-bot (Kontrol Botu için)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters as ptb_filters, PicklePersistence
)
from telegram.constants import ParseMode as TGParseMode
from telegram.error import TelegramError

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
# Pyrogram loglarını biraz kısmak isterseniz:
# logging.getLogger("pyrogram").setLevel(logging.WARNING)
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
    # SETTINGS_FILE = os.getenv('SETTINGS_FILE', 'settings.json') # Şimdilik kullanılmıyor

    # TgCrypto kontrolü
    try:
        import TgCrypto
        logger.info("✅ TgCrypto yüklü.")
    except ImportError:
        logger.warning("⚠️ TgCrypto bulunamadı! Pyrogram daha yavaş çalışacaktır. `pip install TgCrypto` ile kurun.")

    logger.info("✅ Gerekli ortam değişkenleri başarıyla yüklendi.")
except (KeyError, ValueError) as e:
    logger.critical(f"❌ Kritik Hata: Eksik veya geçersiz ortam değişkeni: {e}")
    exit(1)

# --- Global Değişkenler ve Durum Yönetimi ---
DEFAULT_SETTINGS = {
    "is_listening": False,
    "language": "tr",
    "prompt_config": {
        # Eski prompt yapısı biraz karışıktı, daha basit bir yapı kullanalım
        # "base_prompt": "Ben {age} yaşında, {gender}.{jokes}{swearing}{insult} Genellikle ekran başında olmam.",
        "age": 23,
        "gender": "erkeğim", # "kadınım" veya başka bir ifade olabilir
        "use_swearing": True,
        "make_jokes": True,
        "can_insult": False, # Hakaret etme ayarı
        "custom_suffix": "- Afk Mesajı" # Mesaj sonuna eklenecek imza
    },
    "interacted_users": {}, # {user_id: {"name": "...", "link": "...", "type": "dm/mention/reply", "timestamp": ...}}
    "ai_model": "gemini-1.5-flash" # veya gemini-1.5-pro-latest
}

# Dil Dosyası (Basit Dictionary)
localization = {
    "tr": {
        "start_message": "🤖 Merhaba! AFK Yanıt Botu Ayarları.\n\nMevcut Durum: `{status}`\nAktif Dil: 🇹🇷 Türkçe",
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
        "enter_suffix": "Lütfen mesaj sonuna eklenecek ifadeyi girin (boş bırakmak için '-' yazın):",
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
        "unknown_command": "❓ Bilinmeyen komut veya eylem.",
        "prompt_generation_error": "⚠️ Prompt oluşturulamadı, varsayılan kullanılıyor.",
        "pyrogram_handler_error": "⚠️ Pyrogram işleyicisinde hata (Peer ID: {peer_id}): {error}",
        "admin_error_notification": "❌ AFK Yanıt Hatası ({chat_id}): {error}\n\nTraceback:\n{trace}",
        # Yeni Prompt Parçaları
        "prompt_persona_base": "Senin görevin, şu anda bilgisayar başında olmayan bir Telegram kullanıcısının yerine geçen bir yapay zeka asistansın olmak. Aşağıdaki kişilik özelliklerine sahipmiş gibi davranmalısın:",
        "prompt_age_gender": "- {age} yaşında bir {gender}.",
        "prompt_jokes_on": "- Esprili ve eğlenceli bir üslup kullanırsın.",
        "prompt_jokes_off": "- Ciddi bir üslup kullanırsın.",
        "prompt_swearing_on": "- Duruma göre argo veya nadiren hafif küfürler kullanabilirsin.",
        "prompt_swearing_off": "- Kesinlikle küfür veya argo kullanmazsın.",
        "prompt_insult_on": "- Eğer sana kötü davranılırsa veya hakaret edilirse, kendini savunur ve gerekirse karşılık verirsin.",
        "prompt_insult_off": "- Ne olursa olsun kimseye hakaret etmezsin, nazik kalırsın.",
        "prompt_context_intro": "\nŞu anda sana şu bağlamda bir mesaj geldi:",
        "prompt_context_dm": "- '{sender_name}' adlı kullanıcıdan özel mesaj:",
        "prompt_context_mention": "- '{sender_name}' adlı kullanıcı bir grup sohbetinde senden bahsetti:",
        "prompt_context_reply": "- '{sender_name}' adlı kullanıcı bir grup sohbetinde senin bir mesajına yanıt verdi:",
        "prompt_instruction": "\nBu mesaja, tanımlanan kişiliğe uygun, kısa ve öz bir şekilde yanıt ver. Şu anda AFK (klavye başında değil) olduğunu belirtmeyi unutma.",
    },
    "en": {
        # ... (Diğer diller için de benzer güncellemeler yapılmalı) ...
        "start_message": "🤖 Hello! AFK Reply Bot Settings.\n\nCurrent Status: `{status}`\nActive Language: 🇬🇧 English",
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
        "enter_suffix": "Please enter the suffix to append to messages (use '-' for none):",
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
        "unknown_command": "❓ Unknown command or action.",
        "prompt_generation_error": "⚠️ Could not generate prompt, using default.",
        "pyrogram_handler_error": "⚠️ Error in Pyrogram handler (Peer ID: {peer_id}): {error}",
        "admin_error_notification": "❌ AFK Reply Error ({chat_id}): {error}\n\nTraceback:\n{trace}",
        # New Prompt Parts (EN)
        "prompt_persona_base": "Your task is to act as an AI assistant replacing a Telegram user who is currently away from their keyboard. You should behave as if you have the following personality traits:",
        "prompt_age_gender": "- A {age} year old {gender}.",
        "prompt_jokes_on": "- You use a witty and fun tone.",
        "prompt_jokes_off": "- You use a serious tone.",
        "prompt_swearing_on": "- You might use slang or occasionally mild swear words depending on the situation.",
        "prompt_swearing_off": "- You strictly avoid swearing or slang.",
        "prompt_insult_on": "- If treated badly or insulted, you defend yourself and might respond in kind.",
        "prompt_insult_off": "- You remain polite and never insult anyone, regardless of the situation.",
        "prompt_context_intro": "\nYou have just received a message in the following context:",
        "prompt_context_dm": "- A direct message from user '{sender_name}':",
        "prompt_context_mention": "- User '{sender_name}' mentioned you in a group chat:",
        "prompt_context_reply": "- User '{sender_name}' replied to one of your messages in a group chat:",
        "prompt_instruction": "\nRespond to this message briefly and concisely, according to the defined personality. Don't forget to mention that you are currently AFK (away from keyboard).",
    },
    "ru": {
        # ... (Rusça çeviriler güncellenmeli) ...
    }
}

# --- Yardımcı Fonksiyonlar ---

def get_text(context: ContextTypes.DEFAULT_TYPE | None, key: str, lang: str = None, **kwargs) -> str:
    """Yerelleştirilmiş metni alır. Context None ise lang belirtilmeli."""
    if lang is None:
        if context is None:
            # Hem context hem lang None ise varsayılan dil kullanılır.
            # Bu durum prompt oluşturma gibi context'in olmadığı yerlerde olur.
            # get_current_settings içinde varsayılan 'tr' ayarlanıyor.
            # Ancak emin olmak için burada da kontrol edelim.
            effective_lang = DEFAULT_SETTINGS['language']
            logger.warning("get_text context olmadan ve lang belirtilmeden çağrıldı, varsayılan dil '%s' kullanılıyor.", effective_lang)
        else:
            # Context varsa, oradan dili al
            settings = get_current_settings(context)
            effective_lang = settings.get('language', DEFAULT_SETTINGS['language'])
    else:
        # Lang doğrudan belirtilmişse onu kullan
        effective_lang = lang

    # Anahtar bulunamazsa İngilizce'ye veya anahtarın kendisine geri dön
    fallback_lang = 'en' if effective_lang != 'en' else 'tr' # İngilizce değilse İngilizce'ye, İngilizce ise Türkçe'ye fallback
    template = localization.get(effective_lang, {}).get(key)
    if template is None:
        template = localization.get(fallback_lang, {}).get(key)
        if template is None:
             logger.warning(f"Metin anahtarı '{key}' hem '{effective_lang}' hem de '{fallback_lang}' dilinde bulunamadı.")
             template = f"<{key}>" # En kötü ihtimalle anahtarı göster

    try:
        return template.format(**kwargs) if kwargs else template
    except KeyError as e:
        logger.warning(f"Metin formatlamada eksik anahtar: {e} (anahtar: {key}, dil: {effective_lang})")
        return template # Formatlama yapamasa bile şablonu döndür
    except Exception as e:
        logger.error(f"Metin formatlamada beklenmedik hata: {e} (anahtar: {key}, dil: {effective_lang})", exc_info=True)
        return template


def get_current_settings(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Mevcut ayarları alır veya varsayılanları döndürür."""
    if 'settings' not in context.bot_data:
        logger.info("Persistence'ta ayar bulunamadı, varsayılan ayarlar yükleniyor.")
        # Varsayılanları deep copy ile alalım ki iç içe dict'ler etkilenmesin
        context.bot_data['settings'] = json.loads(json.dumps(DEFAULT_SETTINGS))
    # Mevcut ayarlarda eksik anahtar varsa varsayılanlardan tamamla (versiyon güncellemesi vb. için)
    # Bu kısım daha karmaşık hale gelebilir, şimdilik basit tutalım
    # current = context.bot_data['settings']
    # for key, value in DEFAULT_SETTINGS.items():
    #     if key not in current:
    #         current[key] = value
    #     elif isinstance(value, dict):
    #         for sub_key, sub_value in value.items():
    #             if key == "prompt_config" and sub_key not in current.get(key, {}):
    #                  if key not in current: current[key] = {}
    #                  current[key][sub_key] = sub_value
    # context.bot_data['settings'] = current # Güncellenmiş ayarları kaydet
    return context.bot_data['settings']

async def save_settings(context: ContextTypes.DEFAULT_TYPE, settings: dict):
    """Ayarları persistence'a kaydeder."""
    context.bot_data['settings'] = settings
    # PicklePersistence flush() otomatik yapar ama emin olmak için çağrılabilir.
    try:
        await context.application.persistence.flush()
        logger.info("Ayarlar persistence'a kaydedildi.")
    except Exception as e:
        logger.error(f"Persistence flush sırasında hata: {e}")


def get_status_text(context: ContextTypes.DEFAULT_TYPE, status: bool) -> str:
    """Boolean durumu dile göre Açık/Kapalı metnine çevirir."""
    return get_text(context, "status_on") if status else get_text(context, "status_off")

def get_yes_no(context: ContextTypes.DEFAULT_TYPE, status: bool) -> str:
    """Boolean durumu Evet/Hayır veya Açık/Kapalı'ya çevirir (dil desteği eklenebilir)."""
    # Şimdilik basitçe evet/hayır kullanalım (get_status_text daha uygun olabilir)
    return get_text(context, "status_on") if status else get_text(context, "status_off") # Dildeki ON/OFF'u kullanalım


def generate_full_prompt(prompt_config: dict, lang: str, sender_name: str, interaction_type: str, message_text: str) -> str:
    """Ayarlara ve mesaja göre tam AI prompt'unu oluşturur."""
    try:
        p_conf = prompt_config
        # 1. Kişilik Tanımı
        prompt_lines = [get_text(None, "prompt_persona_base", lang=lang)]
        prompt_lines.append(get_text(None, "prompt_age_gender", lang=lang, age=p_conf.get('age', 23), gender=p_conf.get('gender', 'birey')))
        prompt_lines.append(get_text(None, "prompt_jokes_on", lang=lang) if p_conf.get('make_jokes', True) else get_text(None, "prompt_jokes_off", lang=lang))
        prompt_lines.append(get_text(None, "prompt_swearing_on", lang=lang) if p_conf.get('use_swearing', True) else get_text(None, "prompt_swearing_off", lang=lang))
        prompt_lines.append(get_text(None, "prompt_insult_on", lang=lang) if p_conf.get('can_insult', False) else get_text(None, "prompt_insult_off", lang=lang))

        # 2. Mesaj Bağlamı
        prompt_lines.append(get_text(None, "prompt_context_intro", lang=lang))
        context_key = f"prompt_context_{interaction_type}" # dm, mention, reply
        prompt_lines.append(get_text(None, context_key, lang=lang, sender_name=sender_name))
        prompt_lines.append(f"```\n{message_text or '[Mesaj metni yok]'}\n```") # Gelen mesaj

        # 3. Talimat
        prompt_lines.append(get_text(None, "prompt_instruction", lang=lang))

        return "\n".join(prompt_lines)

    except Exception as e:
        logger.error(f"Prompt oluşturulurken hata oluştu: {e}", exc_info=True)
        # Hata durumunda çok basit bir fallback prompt döndür
        return get_text(None, "prompt_generation_error", lang=lang) + f"\n\nLütfen '{sender_name}' tarafından gönderilen şu mesaja AFK olduğunuzu belirterek yanıt verin: {message_text}"

# --- Klavye Oluşturma Yardımcı Fonksiyonları ---

def _generate_main_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> list[list[InlineKeyboardButton]]:
    settings = get_current_settings(context)
    # status = get_status_text(context, settings.get('is_listening', False)) # Buton metni için durum gerekmez
    return [
        [InlineKeyboardButton(get_text(context, "toggle_listening"), callback_data='toggle_listening')],
        [InlineKeyboardButton(get_text(context, "language_select"), callback_data='select_language')],
        [InlineKeyboardButton(get_text(context, "prompt_settings"), callback_data='prompt_settings')],
    ]

def _generate_prompt_settings_keyboard(context: ContextTypes.DEFAULT_TYPE) -> list[list[InlineKeyboardButton]]:
    settings = get_current_settings(context)
    prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])

    status_swearing = get_status_text(context, prompt_config.get('use_swearing', True))
    status_jokes = get_status_text(context, prompt_config.get('make_jokes', True))
    status_insult = get_status_text(context, prompt_config.get('can_insult', False))
    current_age = prompt_config.get('age', DEFAULT_SETTINGS['prompt_config']['age'])
    current_gender = prompt_config.get('gender', DEFAULT_SETTINGS['prompt_config']['gender'])
    current_suffix = prompt_config.get('custom_suffix', DEFAULT_SETTINGS['prompt_config']['custom_suffix'])

    return [
        [InlineKeyboardButton(get_text(context, "set_age", age=current_age), callback_data='prompt_set_age')],
        [InlineKeyboardButton(get_text(context, "set_gender", gender=current_gender), callback_data='prompt_set_gender')],
        [InlineKeyboardButton(get_text(context, "toggle_swearing", status=status_swearing), callback_data='prompt_toggle_swearing')],
        [InlineKeyboardButton(get_text(context, "toggle_jokes", status=status_jokes), callback_data='prompt_toggle_jokes')],
        [InlineKeyboardButton(get_text(context, "toggle_insult", status=status_insult), callback_data='prompt_toggle_insult')],
        [InlineKeyboardButton(get_text(context, "edit_suffix", suffix=current_suffix if current_suffix else "[Boş]"), callback_data='prompt_edit_suffix')],
        [InlineKeyboardButton(f"🔙{get_text(context, 'back_button')}", callback_data='main_menu')],
    ]


# --- Kontrol Botu (python-telegram-bot) İşleyicileri ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start komutu - Ana menüyü gösterir."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bu botu sadece sahibi kullanabilir.")
        return

    settings = get_current_settings(context)
    status = get_status_text(context, settings.get('is_listening', False))
    keyboard = _generate_main_menu_keyboard(context)
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        get_text(context, "start_message", status=status),
        reply_markup=reply_markup,
        parse_mode=TGParseMode.MARKDOWN_V2 # `status` içindeki özel karakterler için
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ana menüyü mesajı düzenleyerek gösterir."""
    query = update.callback_query
    if not query: return # Sadece callback query ile çağrılmalı
    await query.answer()
    if query.from_user.id != ADMIN_ID: return # Sadece admin

    settings = get_current_settings(context)
    status = get_status_text(context, settings.get('is_listening', False))
    keyboard = _generate_main_menu_keyboard(context)
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(
            get_text(context, "start_message", status=status),
            reply_markup=reply_markup,
            parse_mode=TGParseMode.MARKDOWN_V2
        )
    except TelegramError as e:
        logger.error(f"Ana menü düzenlenirken hata: {e}")
        # Mesaj değiştirilmemişse veya başka bir hata varsa kullanıcıya bildirim gönderilebilir
        if "Message is not modified" not in str(e):
             await query.message.reply_text(f"Menü güncellenirken bir hata oluştu: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline butonlara basıldığında çalışır."""
    query = update.callback_query
    await query.answer() # Butona basıldığını kullanıcıya bildirir
    if query.from_user.id != ADMIN_ID: return

    callback_data = query.data
    settings = get_current_settings(context)
    # Prompt config'i sadece gerektiğinde alalım
    # prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])

    logger.info(f"Buton geri çağrısı alındı: {callback_data}")

    # --- Ana Menü Butonları ---
    if callback_data == 'toggle_listening':
        new_status = not settings.get('is_listening', False)
        settings['is_listening'] = new_status
        await save_settings(context, settings)
        status_text = get_text(context, "listening_started") if new_status else get_text(context, "listening_stopped")
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
        try:
            await query.edit_message_text(get_text(context, "select_language_prompt"), reply_markup=reply_markup)
        except TelegramError as e:
            logger.error(f"Dil seçim menüsü düzenlenirken hata: {e}")

    elif callback_data == 'prompt_settings':
        await prompt_settings_menu(update, context) # Prompt ayar menüsünü göster

    # --- Dil Seçim Butonları ---
    elif callback_data.startswith('lang_'):
        lang_code = callback_data.split('_')[1]
        if lang_code in localization:
            settings['language'] = lang_code
            await save_settings(context, settings)
            logger.info(f"Dil değiştirildi: {lang_code}")
            await main_menu(update, context) # Yeni dilde ana menüyü göster
        else:
            logger.warning(f"Geçersiz dil kodu: {lang_code}")
            await query.answer("Geçersiz dil!", show_alert=True) # Kullanıcıyı uyar

    # --- Prompt Ayar Butonları ---
    elif callback_data == 'prompt_set_age':
        context.user_data['next_action'] = 'set_age' # Bir sonraki mesajın yaş için olduğunu işaretle
        try:
            await query.edit_message_text(get_text(context, "enter_age"))
        except TelegramError as e: logger.error(f"Yaş isteme mesajı düzenlenirken hata: {e}")

    elif callback_data == 'prompt_set_gender':
        context.user_data['next_action'] = 'set_gender'
        try:
            await query.edit_message_text(get_text(context, "enter_gender"))
        except TelegramError as e: logger.error(f"Cinsiyet isteme mesajı düzenlenirken hata: {e}")

    elif callback_data == 'prompt_toggle_swearing':
        prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
        prompt_config['use_swearing'] = not prompt_config.get('use_swearing', True)
        settings['prompt_config'] = prompt_config
        await save_settings(context, settings)
        await query.answer(get_text(context, "setting_updated")) # Kısa bildirim
        await prompt_settings_menu(update, context) # Menüyü güncelle

    elif callback_data == 'prompt_toggle_jokes':
        prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
        prompt_config['make_jokes'] = not prompt_config.get('make_jokes', True)
        settings['prompt_config'] = prompt_config
        await save_settings(context, settings)
        await query.answer(get_text(context, "setting_updated"))
        await prompt_settings_menu(update, context)

    elif callback_data == 'prompt_toggle_insult':
        prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
        prompt_config['can_insult'] = not prompt_config.get('can_insult', False)
        settings['prompt_config'] = prompt_config
        await save_settings(context, settings)
        await query.answer(get_text(context, "setting_updated"))
        await prompt_settings_menu(update, context)

    elif callback_data == 'prompt_edit_suffix':
        context.user_data['next_action'] = 'set_suffix'
        try:
            await query.edit_message_text(get_text(context, "enter_suffix"))
        except TelegramError as e: logger.error(f"Suffix isteme mesajı düzenlenirken hata: {e}")

    # --- Geri Butonları ---
    elif callback_data == 'main_menu':
        # next_action kalmışsa temizle
        context.user_data.pop('next_action', None)
        await main_menu(update, context)


async def prompt_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt ayarları menüsünü gösterir/düzenler."""
    query = update.callback_query # Callback query olmalı
    if not query:
        logger.warning("prompt_settings_menu query olmadan çağrıldı.")
        return
    if query.from_user.id != ADMIN_ID: return

    keyboard = _generate_prompt_settings_keyboard(context)
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(get_text(context, "prompt_menu_title"), reply_markup=reply_markup)
    except TelegramError as e:
        logger.error(f"Prompt menüsü düzenlenirken hata: {e}")
        if "Message is not modified" not in str(e):
             await query.message.reply_text(f"Menü güncellenirken bir hata oluştu: {e}")

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt ayarları için metin girişlerini işler."""
    if update.effective_user.id != ADMIN_ID: return # Sadece admin

    action = context.user_data.pop('next_action', None)
    if not action:
        # Beklenen bir eylem yoksa, bilinmeyen komut mesajı gönderilebilir veya yok sayılabilir.
        # await update.message.reply_text(get_text(context, "unknown_command"))
        logger.debug(f"Admin'den beklenmeyen metin mesajı: {update.message.text}")
        return

    text = update.message.text.strip()
    settings = get_current_settings(context)
    prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
    should_show_menu_again = False

    if action == 'set_age':
        try:
            age = int(text)
            if 0 < age < 150:
                prompt_config['age'] = age
                settings['prompt_config'] = prompt_config
                await save_settings(context, settings)
                await update.message.reply_text(get_text(context, "age_updated", age=age))
                should_show_menu_again = True
            else:
                await update.message.reply_text(get_text(context, "error_invalid_input") + " (Yaş 1-149 arası olmalı)")
                context.user_data['next_action'] = 'set_age' # Tekrar sormak için action'ı geri koy
        except ValueError:
            await update.message.reply_text(get_text(context, "error_invalid_input") + " (Lütfen sadece sayı girin)")
            context.user_data['next_action'] = 'set_age' # Tekrar sormak için action'ı geri koy

    elif action == 'set_gender':
        if text:
            gender = text[:30] # Çok uzun olmasın
            prompt_config['gender'] = gender
            settings['prompt_config'] = prompt_config
            await save_settings(context, settings)
            await update.message.reply_text(get_text(context, "gender_updated", gender=gender))
            should_show_menu_again = True
        else:
            await update.message.reply_text(get_text(context, "error_invalid_input"))
            context.user_data['next_action'] = 'set_gender' # Tekrar sormak için

    elif action == 'set_suffix':
        suffix = text[:50] # Suffix uzunluğunu sınırla
        if suffix == '-': # Boş bırakmak için özel karakter
            suffix = ""
        prompt_config['custom_suffix'] = suffix
        settings['prompt_config'] = prompt_config
        await save_settings(context, settings)
        await update.message.reply_text(get_text(context, "suffix_updated", suffix=suffix if suffix else "[Boş]"))
        should_show_menu_again = True
        # Boş metin gelirse hata vermeye gerek yok, boş suffix olarak ayarlanır.

    # Ayar yapıldıysa menüyü tekrar göster
    if should_show_menu_again:
         # Yeni bir mesaj olarak gönderelim, edit yerine
         keyboard = _generate_prompt_settings_keyboard(context)
         reply_markup = InlineKeyboardMarkup(keyboard)
         await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=reply_markup)


# --- Kullanıcı Botu (Pyrogram) İşleyicileri ---

user_bot_client: Client = None # Global Pyrogram client
ptb_app: Application = None # Global PTB application

# Gemini AI istemcisini yapılandıralım
try:
    genai.configure(api_key=AI_API_KEY)
    # TODO: Model adını ayarlardan alacak şekilde dinamik yapabiliriz
    ai_model_instance = genai.GenerativeModel(DEFAULT_SETTINGS['ai_model'])
    logger.info(f"Gemini AI Modeli ({DEFAULT_SETTINGS['ai_model']}) yapılandırıldı.")
    # Güvenlik ayarlarını yapılandır (isteğe bağlı, küfür vb. için)
    # Daha serbest yanıtlar için:
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    logger.info(f"Gemini AI güvenlik ayarları: {safety_settings}")
except Exception as e:
    logger.critical(f"❌ Gemini AI yapılandırılamadı: {e}", exc_info=True)
    ai_model_instance = None # Hata durumunda modeli None yap
    safety_settings = None


async def get_pyrogram_settings() -> dict:
    """PTB persistence'dan Pyrogram için ayarları alır."""
    if not ptb_app:
        logger.error("PTB Application Pyrogram ayarları için kullanılamıyor.")
        return DEFAULT_SETTINGS.copy()
    # Geçici context oluşturarak bot_data'ya erişim
    # chat_id ve user_id aslında burada çok önemli değil, sadece context oluşturmak için
    context = ContextTypes.DEFAULT_TYPE(application=ptb_app, chat_id=ADMIN_ID, user_id=ADMIN_ID)
    return get_current_settings(context) # Bu fonksiyon zaten varsayılanları hallediyor

async def save_pyrogram_settings(settings: dict):
    """Pyrogram'dan gelen ayarları PTB persistence'a kaydeder."""
    if not ptb_app:
        logger.error("PTB Application Pyrogram ayarları kaydetmek için kullanılamıyor.")
        return
    context = ContextTypes.DEFAULT_TYPE(application=ptb_app, chat_id=ADMIN_ID, user_id=ADMIN_ID)
    await save_settings(context, settings)

async def notify_admin(client: Client, message: str):
    """Admin'e önemli hataları veya bilgileri gönderir."""
    if ADMIN_ID:
        try:
            await client.send_message(ADMIN_ID, message[:4096]) # Limit mesaj uzunluğu
        except Exception as e:
            logger.error(f"Admin'e bildirim gönderilemedi ({ADMIN_ID}): {e}")

# Pyrogram için decorator'ları Client örneği oluşturulduktan sonra tanımlamak yerine
# doğrudan fonksiyonları tanımlayıp sonra add_handler ile ekleyebiliriz.
# Ancak mevcut yapı da çalışır. Client global olduğu için sorun olmaz.

# Ana Mesaj İşleyici
@Client.on_message(filters.private | filters.mentioned | filters.reply & ~filters.me & ~filters.service, group=1)
async def handle_user_message(client: Client, message: Message):
    """Özel mesajları, mentionları ve yanıtlara gelen mesajları işler (kendimiz hariç)."""
    # Pyrogram client'ının başlatıldığından emin ol (gerçi decorator bunu sağlıyor)
    if not client or not client.is_connected:
        logger.warning("Pyrogram client hazır değil, mesaj işlenemiyor.")
        return

    # Hata Yakalama Bloğu: Tüm işleyiciyi sarar
    try:
        settings = await get_pyrogram_settings()

        # 1. Dinleme modu kapalıysa işlem yapma
        if not settings.get('is_listening', False):
            # logger.debug("Dinleme modu kapalı, mesaj yoksayılıyor.")
            return

        # 2. Gerekli bilgileri al
        my_id = client.me.id
        sender = message.from_user or message.sender_chat # Gönderen kullanıcı veya kanal

        if not sender:
            logger.warning(f"Mesajda gönderici bilgisi yok: {message.id} in {message.chat.id}")
            return # Gönderici yoksa işlem yapma

        # Kendi mesajımızı zaten filtre ile engelledik (~filters.me)
        # if sender.id == my_id: return

        sender_id = sender.id
        # Kanal mesajlarında 'title', kullanıcı mesajlarında 'first_name' olur. İkisi de yoksa ID yaz.
        sender_name = getattr(sender, 'title', getattr(sender, 'first_name', f"ID:{sender_id}"))
        if hasattr(sender, 'last_name') and sender.last_name:
             sender_name += f" {sender.last_name}"

        chat_id = message.chat.id
        message_id = message.id
        message_text = message.text or message.caption or "" # Metin veya medya başlığı
        message_link = message.link # Pyrogram link sağlar

        # 3. Etkileşim türünü belirle (Filtreler zaten bunu garanti ediyor ama yine de netleştirelim)
        interaction_type = "unknown"
        if message.chat.type == ChatType.PRIVATE:
            interaction_type = "dm"
        elif message.mentioned:
            interaction_type = "mention"
        elif message.reply_to_message and message.reply_to_message.from_user_id == my_id:
             interaction_type = "reply"
        else:
             # Bu durum filtreler nedeniyle olmamalı, ama olursa loglayalım
             logger.warning(f"Beklenmeyen mesaj türü algılandı: chat_id={chat_id}, msg_id={message_id}")
             return # İşleme devam etme

        logger.info(f"İşlenecek mesaj ({interaction_type}): {sender_name} ({sender_id}) -> {message_text[:50] if message_text else '[Metin/Başlık Yok]'} (Link: {message_link})")

        # 4. Kullanıcıyı etkileşim listesine ekle/güncelle
        now_utc = datetime.now(pytz.utc) # Zaman damgası için UTC kullan
        interacted_users = settings.get('interacted_users', {})
        interacted_users[str(sender_id)] = {
            "name": sender_name,
            "link": message_link, # Gruplar için mesaj linki daha anlamlı
            "type": interaction_type,
            "timestamp": now_utc.isoformat()
        }
        # Liste boyutunu sınırla (isteğe bağlı, eski kayıtları silmek için)
        # MAX_INTERACTIONS = 100
        # if len(interacted_users) > MAX_INTERACTIONS:
        #     sorted_users = sorted(interacted_users.items(), key=lambda item: item[1].get('timestamp', ''))
        #     interacted_users = dict(sorted_users[len(interacted_users)-MAX_INTERACTIONS:])

        settings['interacted_users'] = interacted_users
        await save_pyrogram_settings(settings) # Ayarları kaydet

        # 5. AI Yanıtı Oluşturma
        if not ai_model_instance:
             logger.error("AI modeli başlatılmamış, yanıt verilemiyor.")
             await notify_admin(client, "❌ Hata: AI modeli başlatılamadığı için AFK yanıtı verilemedi.")
             return # AI yoksa devam etme

        prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
        lang = settings.get('language', 'tr')
        full_prompt = generate_full_prompt(prompt_config, lang, sender_name, interaction_type, message_text)

        logger.debug(f"Oluşturulan AI Prompt'u:\n---\n{full_prompt}\n---")

        # AI'ye gönderilecek tam içerik (generate_full_prompt zaten hepsini içeriyor)
        ai_content = full_prompt

        logger.info(f"AI ({settings['ai_model']}) modeline istek gönderiliyor...")
        response = await ai_model_instance.generate_content_async(
            ai_content,
            safety_settings=safety_settings # Güvenlik ayarlarını uygula
            # generation_config=genai.types.GenerationConfig(...) # İsteğe bağlı: max_tokens, temperature vb.
        )
        ai_reply_text = response.text
        logger.info(f"AI yanıtı alındı: {ai_reply_text[:100]}...")

        # 6. Yanıtı Gönderme
        suffix = prompt_config.get('custom_suffix', "") # Ayarlardan al, yoksa boş
        final_reply = ai_reply_text
        if suffix: # Sadece suffix varsa ekle
            final_reply += f"\n\n{suffix}"

        await client.send_message(
            chat_id=chat_id,
            text=final_reply,
            reply_to_message_id=message_id,
            parse_mode=PyroParseMode.MARKDOWN # Gemini genellikle Markdown döndürür
        )
        logger.info(f"Yanıt gönderildi: chat_id={chat_id}, reply_to={message_id}")

    # Hata Yakalama
    except (PeerIdInvalid, ChannelInvalid, ChannelPrivate) as e:
        # Bu hatalar genellikle botun o sohbete erişimi olmadığında olur.
        # Hata mesajını logla ve admin'e bildir (eğer varsa). Botun çökmesini engelle.
        peer_id_info = f"Chat ID: {message.chat.id}" if message else "Bilinmiyor"
        logger.error(f"Pyrogram Peer/Channel Hatası ({peer_id_info}): {e}. Bu sohbetten gelen güncellemeler işlenemiyor.", exc_info=False) # Traceback'e gerek yok
        # await notify_admin(client, get_text(None, "pyrogram_handler_error", lang='tr', peer_id=peer_id_info, error=str(e)))
    except (UserIsBlocked, UserNotParticipant) as e:
        logger.warning(f"Mesaj gönderilemedi (kullanıcı engelledi veya grupta değil): {e} (Chat ID: {message.chat.id if message else 'N/A'})")
        # Bu kullanıcıyı belki interacted_users'dan çıkarabiliriz
    except GoogleAPIError as e:
        logger.error(f"Google AI API Hatası: {e}", exc_info=True)
        error_text = get_text(None, "error_ai", lang=settings.get('language', 'tr'), error=str(e))
        await notify_admin(client, error_text)
    except Exception as e:
        # Diğer beklenmedik hatalar
        logger.error(f"Mesaj işlenirken veya gönderilirken beklenmedik hata: {e}", exc_info=True)
        error_trace = traceback.format_exc()
        # Admin'e detaylı bildirim gönder
        await notify_admin(client, get_text(None, "admin_error_notification", lang='tr', # Admin bildirimi hep TR olsun?
                                             chat_id=message.chat.id if message else 'N/A',
                                             error=str(e), trace=error_trace[-1000:])) # Traceback'i kısalt

# Pyrogram için admin komutları
@Client.on_message(filters.me & filters.command(["on", "off", "list", "ping"], prefixes="."), group=0)
async def handle_pyrogram_commands(client: Client, message: Message):
    """Kullanıcı botu tarafından gönderilen .on, .off, .list, .ping komutlarını işler."""
    command = message.command[0].lower()
    delete_after = 10 # Komut mesajını silme süresi (saniye)
    edit_text = "" # Düzenlenecek metin

    try:
        settings = await get_pyrogram_settings()
        lang = settings.get('language', 'tr')

        if command == "on":
            if not settings.get('is_listening', False):
                settings['is_listening'] = True
                await save_pyrogram_settings(settings)
                edit_text = get_text(None, "listening_started", lang=lang)
                logger.info("Dinleme modu .on komutuyla AKTİF edildi.")
            else:
                edit_text = "ℹ️ Dinleme modu zaten AKTİF."
                delete_after = 3 # Zaten açıksa hızlı sil

        elif command == "off":
            if settings.get('is_listening', False):
                settings['is_listening'] = False
                await save_pyrogram_settings(settings)
                edit_text = get_text(None, "listening_stopped", lang=lang)
                logger.info("Dinleme modu .off komutuyla DEVRE DIŞI bırakıldı.")
            else:
                 edit_text = "ℹ️ Dinleme modu zaten DEVRE DIŞI."
                 delete_after = 3 # Zaten kapalıysa hızlı sil

        elif command == "list":
            interacted = settings.get('interacted_users', {})
            if not interacted:
                edit_text = get_text(None, "list_empty", lang=lang)
            else:
                # Kullanıcıları zamana göre sırala (en yeniden en eskiye)
                try:
                    sorted_users = sorted(
                        interacted.items(),
                        # Timestamp yoksa veya hatalıysa en başa atsın
                        key=lambda item: datetime.fromisoformat(item[1].get('timestamp', '1970-01-01T00:00:00+00:00')),
                        reverse=True
                    )
                except Exception as sort_e:
                     logger.error(f"Etkileşim listesi sıralama hatası: {sort_e}")
                     # Sıralama başarısız olursa ID'ye göre sırala veya olduğu gibi bırak
                     sorted_users = sorted(interacted.items(), key=lambda item: item[0])

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
                    timestamp_str = data.get('timestamp', 'Bilinmiyor')
                    # Zamanı daha okunabilir formatta gösterelim (isteğe bağlı)
                    # try:
                    #     dt_obj = datetime.fromisoformat(timestamp_str).astimezone(pytz.timezone('Europe/Istanbul')) # Yerel saate çevir
                    #     time_display = dt_obj.strftime('%Y-%m-%d %H:%M')
                    # except:
                    #     time_display = timestamp_str

                    try:
                        user_id_int = int(user_id_str) # Link için int lazım
                        if interaction_type == 'dm':
                             list_text += f"• {get_text(None, 'list_format_dm', lang=lang, user_id=user_id_int, name=name)}\n" # ({time_display})\n"
                        elif link:
                             list_text += f"• {get_text(None, 'list_format_group', lang=lang, link=link, name=name, type=interaction_type)}\n" # ({time_display})\n"
                        else:
                             list_text += f"• {name} ({interaction_type})\n" # ({time_display})\n"
                        count += 1
                    except ValueError:
                         logger.warning(f".list: Geçersiz kullanıcı ID'si string'i: {user_id_str}")
                         list_text += f"• {name} (ID: {user_id_str}, Tip: {interaction_type})\n" # ID'yi göster
                         count += 1
                    except Exception as format_e:
                         logger.error(f".list: Liste formatlama hatası for {user_id_str}: {format_e}")
                         list_text += f"• {name} (formatlama hatası)\n"
                         count += 1
                edit_text = list_text
        elif command == "ping":
             start_time = datetime.now()
             # Küçük bir Pyrogram API çağrısı yap
             await client.get_me()
             end_time = datetime.now()
             ping_time = (end_time - start_time).total_seconds() * 1000 # Milisaniye
             edit_text = f"Pong! 🏓 ({ping_time:.2f} ms)"
             delete_after = 5

        # Mesajı düzenleyerek yanıt ver
        if edit_text:
            await message.edit_text(
                edit_text,
                parse_mode=TGParseMode.HTML if command == "list" else None, # Sadece liste HTML parse kullansın
                disable_web_page_preview=True
            )

    except (PeerIdInvalid, ChannelInvalid, ChannelPrivate) as e:
        # Komut işlerken de bu hatalar olabilir (nadiren)
        logger.error(f"Pyrogram komut işleyicisinde Peer/Channel Hatası: {e}", exc_info=False)
        try: await message.edit_text(f"❌ Komut işlenirken hata oluştu: {e}")
        except: pass # Düzenleme de başarısız olabilir
    except Exception as e:
        logger.error(f"Pyrogram komut ({command}) işlenirken hata: {e}", exc_info=True)
        try: await message.edit_text(f"❌ Komut işlenirken beklenmedik hata: {e}")
        except: pass
        delete_after = 15 # Hata mesajı biraz daha kalsın

    # Komut mesajını silme
    await asyncio.sleep(delete_after)
    try:
        await message.delete()
    except Exception as del_err:
        # Silinemezse çok önemli değil, loglayalım
        logger.warning(f"Komut mesajı silinemedi: {del_err}")


# --- Ana Çalıştırma Fonksiyonu ---

async def main():
    global user_bot_client, ptb_app # Global değişkenlere atama yapacağımızı belirtelim

    # 1. Persistence Ayarları
    logger.info(f"Persistence dosyası kullanılıyor: {PERSISTENCE_FILE}")
    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)

    # 2. Kontrol Botu (PTB) Application Oluşturma
    logger.info("Kontrol botu (PTB) Application oluşturuluyor...")
    ptb_application = Application.builder() \
        .token(TG_BOT_TOKEN) \
        .persistence(persistence) \
        .build()
    ptb_app = ptb_application # Global değişkene ata

    # PTB İşleyicilerini Ekleme
    # Önce komutlar
    ptb_application.add_handler(CommandHandler(("start", "settings"), start, filters=ptb_filters.User(ADMIN_ID)))
    # Sonra callback query'ler
    ptb_application.add_handler(CallbackQueryHandler(button_callback)) # Pattern belirtmeye gerek yok, hepsini yakalasın
    # Sonra metin girişleri (sadece admin'den ve komut olmayanlar)
    ptb_application.add_handler(MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND & ptb_filters.User(ADMIN_ID), handle_text_input))
    # Bilinmeyen komutlar için bir handler eklenebilir (isteğe bağlı)
    # ptb_application.add_handler(MessageHandler(ptb_filters.COMMAND & ptb_filters.User(ADMIN_ID), unknown_command_handler))

    logger.info("PTB handler'ları eklendi.")

    # 3. Pyrogram İstemcisini Oluşturma
    logger.info("Pyrogram kullanıcı botu istemcisi oluşturuluyor...")
    user_bot_client = Client(
        "my_afk_userbot", # Session adı (string session kullanılsa da gerekli)
        api_id=TG_API_ID,
        api_hash=TG_API_HASH,
        session_string=TG_STRING_SESSION
        # worker_count=4 # İsteğe bağlı: iş parçacığı sayısı (genelde varsayılan iyidir)
    )

    # Pyrogram handler'larını ekle (decorator ile yapıldı)
    # Eğer decorator kullanmasaydık burada eklerdik:
    # user_bot_client.add_handler(MessageHandler(handle_user_message, filters=...))
    # user_bot_client.add_handler(MessageHandler(handle_pyrogram_commands, filters=...))
    logger.info("Pyrogram handler'ları (decorator ile) tanımlandı.")

    # PTB application nesnesini Pyrogram client'ına ekleyelim (artık global olduğu için gerek yok ama zarar vermez)
    # user_bot_client.ptb_app = ptb_application

    # 4. İki Botu Aynı Anda Çalıştırma
    try:
        logger.info("Kontrol botu (PTB) başlatılıyor (initialize)...")
        await ptb_application.initialize() # Botu başlatmadan önce gerekli hazırlıkları yapar
        logger.info("Pyrogram kullanıcı botu (Userbot) başlatılıyor...")
        await user_bot_client.start()
        my_info = await user_bot_client.get_me()
        logger.info(f"✅ Userbot başarıyla bağlandı: {my_info.first_name} (@{my_info.username}) ID: {my_info.id}")
        logger.info("Kontrol botu polling başlatılıyor (start)...")
        await ptb_application.start() # Bot komutları dinlemeye başlar
        logger.info("✅ Kontrol botu başarıyla başlatıldı.")
        logger.info("Botlar çalışıyor... Kapatmak için CTRL+C basın.")

        # İki botun da çalışmasını bekle
        await idle() # Pyrogram'ın çalışmasını sağlar (ve PTB arka planda çalışır)

    except ConnectionError as e:
         # String session geçersizse veya ağ hatası varsa bu olabilir
         logger.critical(f"❌ Pyrogram bağlanamadı! String Session geçersiz veya ağ sorunu: {e}", exc_info=True)
         if ptb_application.running:
              await ptb_application.stop()
    except TelegramError as e:
        # PTB başlatma veya çalışma sırasında hata
        logger.critical(f"❌ Kontrol botu (PTB) hatası: {e}", exc_info=True)
        if user_bot_client.is_connected:
            await user_bot_client.stop()
    except Exception as e:
        logger.critical(f"❌ Ana çalıştırma döngüsünde kritik hata: {e}", exc_info=True)
    finally:
        logger.info("Botlar durduruluyor...")
        tasks = []
        # Graceful shutdown
        if user_bot_client and user_bot_client.is_connected:
            logger.info("Pyrogram userbot durduruluyor...")
            tasks.append(asyncio.create_task(user_bot_client.stop()))
        if ptb_application and ptb_application.running:
            logger.info("Kontrol botu (PTB) durduruluyor...")
            tasks.append(asyncio.create_task(ptb_application.stop()))
            tasks.append(asyncio.create_task(ptb_application.shutdown())) # Shutdown önemli

        # Tüm durdurma görevlerinin bitmesini bekle
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True) # Hataları yakala ama devam et

        logger.info("Pyrogram userbot durduruldu.")
        logger.info("Kontrol botu (PTB) durduruldu.")
        logger.info("Tüm işlemler durduruldu.")


if __name__ == "__main__":
    print("==========================================")
    print("     Telegram AFK Yanıt Botu v2.1         ")
    print("==========================================")
    # Ana asenkron fonksiyonu çalıştır
    # Python 3.10 ve sonrası için:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("CTRL+C algılandı, botlar durduruluyor...")
    except Exception as e:
        logger.critical(f"Ana çalıştırma bloğunda beklenmedik hata: {e}", exc_info=True)

