# -*- coding: utf-8 -*-

import asyncio
import json
import os
import traceback
import logging
from datetime import datetime
import pytz

from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ChatType, ParseMode as PyroParseMode
from pyrogram.errors import UserNotParticipant, UserIsBlocked, PeerIdInvalid, ChannelInvalid, ChannelPrivate

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters as ptb_filters, PicklePersistence
)
from telegram.constants import ParseMode as TGParseMode
from telegram.error import TelegramError

from google import generativeai as genai
from google.api_core.exceptions import GoogleAPIError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

logger.info("➡️ Ortam değişkenleri okunuyor...")
try:
    ADMIN_ID = int(os.environ['ADMIN_ID'])
    TG_API_ID = int(os.environ['TG_API_ID'])
    TG_API_HASH = os.environ['TG_API_HASH']
    TG_BOT_TOKEN = os.environ['TG_BOT_TOKEN']
    AI_API_KEY = os.environ['AI_API_KEY']
    TG_STRING_SESSION = os.environ['TG_STRING_SESSION']
    PERSISTENCE_FILE = os.getenv('PERSISTENCE_FILE', 'bot_persistence.pickle')

    try:
        import TgCrypto
        logger.info("✅ TgCrypto yüklü.")
    except ImportError:
        logger.warning("⚠️ TgCrypto bulunamadı! Pyrogram daha yavaş çalışacaktır. `pip install TgCrypto` ile kurun.")

    logger.info(f"✅ Gerekli ortam değişkenleri başarıyla yüklendi. ADMIN_ID: {ADMIN_ID}")
except (KeyError, ValueError) as e:
    logger.critical(f"❌ Kritik Hata: Eksik veya geçersiz ortam değişkeni: {e}")
    exit(1)

DEFAULT_SETTINGS = {
    "is_listening": False,
    "language": "tr",
    "prompt_config": {
        "age": 23,
        "gender": "erkeğim",
        "use_swearing": True,
        "make_jokes": True,
        "can_insult": False,
        "custom_suffix": "- Afk Mesajı"
    },
    "interacted_users": {},
    "ai_model": "gemini-1.5-flash"
}

localization = {
    "tr": {
        "start_message": (
            "🤖 Merhaba! AFK Yanıt Kontrol Botu.\n\n"
            "Userbot Dinleme Durumu: `{status}`\n"
            "Aktif Dil: 🇹🇷 Türkçe\n\n"
            "Kullanılabilir Komutlar:\n"
            "`/on` - Userbot dinlemesini başlatır.\n"
            "`/off` - Userbot dinlemesini durdurur ve etkileşim listesini sıfırlar.\n"
            "`/list` - Son `/on` komutundan beri etkileşim kuranları listeler.\n"
            "`/settings` - Dil ve AI prompt ayarları menüsünü açar.\n"
            "`/ping` - Botun ve userbot'un yanıt verip vermediğini kontrol eder."
        ),
        "settings_menu_title": "⚙️ Ayarlar Menüsü",
        "language_select": "🌍 Dil Seçimi",
        "prompt_settings": "📝 Prompt Ayarları",
        "back_button": " geri",
        "status_on": "AKTİF ✅",
        "status_off": "PASİF ❌",
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
        "afk_signature": "- Afk Mesajı",
        "list_title": "💬 Son Etkileşimler ( `/on` komutundan beri):",
        "list_empty": "ℹ️ `/on` komutundan beri kayıtlı etkileşim yok veya dinleme kapalı.",
        "list_format_dm": "<a href=\"tg://user?id={user_id}\">{name}</a> (Özel Mesaj)",
        "list_format_group": "<a href=\"{link}\">{name}</a> ({type})",
        "error_ai": "❌ AI yanıtı alınırken hata oluştu: {error}",
        "error_sending": "❌ Mesaj gönderilirken hata oluştu: {error}",
        "listening_started": "✅ Userbot dinleme modu AKTİF.",
        "listening_stopped": "❌ Userbot dinleme modu DEVRE DIŞI. Etkileşim listesi sıfırlandı.",
        "already_listening": "ℹ️ Userbot dinleme modu zaten AKTİF.",
        "already_stopped": "ℹ️ Userbot dinleme modu zaten DEVRE DIŞI.",
        "unknown_command": "❓ Bilinmeyen komut.",
        "prompt_generation_error": "⚠️ Prompt oluşturulamadı, varsayılan kullanılıyor.",
        "pyrogram_handler_error": "⚠️ Pyrogram işleyicisinde hata (Peer ID: {peer_id}): {error}",
        "admin_error_notification": "❌ AFK Yanıt Hatası ({chat_id}): {error}\n\nTraceback:\n{trace}",
        "ping_reply": "🏓 Pong!\nKontrol Botu: Aktif ✅\nUserbot Bağlantı: {userbot_status}",
        "userbot_connected": "Bağlı ✅",
        "userbot_disconnected": "Bağlı Değil ❌",
        "userbot_error": "Hata ⚠️",
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
        "start_message": (
            "🤖 Hello! AFK Reply Control Bot.\n\n"
            "Userbot Listening Status: `{status}`\n"
            "Active Language: 🇬🇧 English\n\n"
            "Available Commands:\n"
            "`/on` - Starts the userbot listening.\n"
            "`/off` - Stops the userbot listening and clears the interaction list.\n"
            "`/list` - Lists users who interacted since the last `/on` command.\n"
            "`/settings` - Opens the language and AI prompt settings menu.\n"
            "`/ping` - Checks if the bot and userbot are responsive."
        ),
        "status_on": "ACTIVE ✅",
        "status_off": "INACTIVE ❌",
        "list_title": "💬 Recent Interactions (since `/on` command):",
        "list_empty": "ℹ️ No interactions recorded since `/on` command or listening is off.",
        "listening_started": "✅ Userbot listening mode ACTIVE.",
        "listening_stopped": "❌ Userbot listening mode INACTIVE. Interaction list cleared.",
        "already_listening": "ℹ️ Userbot listening mode is already ACTIVE.",
        "already_stopped": "ℹ️ Userbot listening mode is already INACTIVE.",
        "ping_reply": "🏓 Pong!\nControl Bot: Active ✅\nUserbot Connection: {userbot_status}",
        "userbot_connected": "Connected ✅",
        "userbot_disconnected": "Disconnected ❌",
        "userbot_error": "Error ⚠️",
        # Diğer İngilizce metinler buraya eklenebilir...
    },
    "ru": {
        # Rusça metinler buraya eklenebilir...
    }
}

def get_text(context: ContextTypes.DEFAULT_TYPE | None, key: str, lang: str = None, **kwargs) -> str:
    if lang is None:
        if context is None:
            effective_lang = DEFAULT_SETTINGS['language']
        else:
            settings = get_current_settings(context)
            effective_lang = settings.get('language', DEFAULT_SETTINGS['language'])
    else:
        effective_lang = lang

    fallback_lang = 'en' if effective_lang != 'en' else 'tr'
    template = localization.get(effective_lang, {}).get(key)
    if template is None:
        template = localization.get(fallback_lang, {}).get(key)
        if template is None:
             logger.warning(f"Metin anahtarı '{key}' hem '{effective_lang}' hem de '{fallback_lang}' dilinde bulunamadı.")
             template = f"<{key}>"

    try:
        return template.format(**kwargs) if kwargs else template
    except KeyError as e:
        logger.warning(f"Metin formatlamada eksik anahtar: {e} (anahtar: {key}, dil: {effective_lang})")
        return template
    except Exception as e:
        logger.error(f"Metin formatlamada beklenmedik hata: {e} (anahtar: {key}, dil: {effective_lang})", exc_info=True)
        return template

def get_current_settings(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if 'settings' not in context.bot_data:
        logger.info("Persistence'ta ayar bulunamadı, varsayılan ayarlar yükleniyor.")
        context.bot_data['settings'] = json.loads(json.dumps(DEFAULT_SETTINGS))
    return context.bot_data['settings']

async def save_settings(context: ContextTypes.DEFAULT_TYPE, settings: dict):
    context.bot_data['settings'] = settings
    try:
        await context.application.persistence.flush()
    except Exception as e:
        logger.error(f"Persistence flush sırasında hata: {e}")

def get_status_text(context: ContextTypes.DEFAULT_TYPE, status: bool) -> str:
    return get_text(context, "status_on") if status else get_text(context, "status_off")

def generate_full_prompt(prompt_config: dict, lang: str, sender_name: str, interaction_type: str, message_text: str) -> str:
    try:
        p_conf = prompt_config
        prompt_lines = [get_text(None, "prompt_persona_base", lang=lang)]
        prompt_lines.append(get_text(None, "prompt_age_gender", lang=lang, age=p_conf.get('age', 23), gender=p_conf.get('gender', 'birey')))
        prompt_lines.append(get_text(None, "prompt_jokes_on", lang=lang) if p_conf.get('make_jokes', True) else get_text(None, "prompt_jokes_off", lang=lang))
        prompt_lines.append(get_text(None, "prompt_swearing_on", lang=lang) if p_conf.get('use_swearing', True) else get_text(None, "prompt_swearing_off", lang=lang))
        prompt_lines.append(get_text(None, "prompt_insult_on", lang=lang) if p_conf.get('can_insult', False) else get_text(None, "prompt_insult_off", lang=lang))

        prompt_lines.append(get_text(None, "prompt_context_intro", lang=lang))
        context_key = f"prompt_context_{interaction_type}"
        prompt_lines.append(get_text(None, context_key, lang=lang, sender_name=sender_name))
        prompt_lines.append(f"```\n{message_text or '[Mesaj metni yok]'}\n```")

        prompt_lines.append(get_text(None, "prompt_instruction", lang=lang))

        return "\n".join(prompt_lines)

    except Exception as e:
        logger.error(f"Prompt oluşturulurken hata oluştu: {e}", exc_info=True)
        return get_text(None, "prompt_generation_error", lang=lang) + f"\n\nLütfen '{sender_name}' tarafından gönderilen şu mesaja AFK olduğunuzu belirterek yanıt verin: {message_text}"

def _generate_main_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> list[list[InlineKeyboardButton]]:
    return [
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Received command '/start' from user ID {user_id}. Comparing with ADMIN_ID {ADMIN_ID}.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt for /start by user ID {user_id}.")
        await update.message.reply_text("⛔ Bu botu sadece sahibi kullanabilir.")
        return

    settings = get_current_settings(context)
    status = get_status_text(context, settings.get('is_listening', False))
    await update.message.reply_text(
        get_text(context, "start_message", status=status),
        parse_mode=TGParseMode.MARKDOWN_V2
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Received command '/settings' from user ID {user_id}. Comparing with ADMIN_ID {ADMIN_ID}.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt for /settings by user ID {user_id}.")
        return

    keyboard = _generate_main_menu_keyboard(context)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        get_text(context, "settings_menu_title"),
        reply_markup=reply_markup
    )

async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Received command '/on' from user ID {user_id}. Comparing with ADMIN_ID {ADMIN_ID}.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt for /on by user ID {user_id}.")
        return

    settings = get_current_settings(context)
    if not settings.get('is_listening', False):
        settings['is_listening'] = True
        await save_settings(context, settings)
        await update.message.reply_text(get_text(context, "listening_started"))
        logger.info(f"Userbot dinleme modu /on komutuyla AKTİF edildi (Admin: {ADMIN_ID}).")
    else:
        await update.message.reply_text(get_text(context, "already_listening"))

async def off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Received command '/off' from user ID {user_id}. Comparing with ADMIN_ID {ADMIN_ID}.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt for /off by user ID {user_id}.")
        return

    settings = get_current_settings(context)
    if settings.get('is_listening', False):
        settings['is_listening'] = False
        settings['interacted_users'] = {}
        await save_settings(context, settings)
        await update.message.reply_text(get_text(context, "listening_stopped"))
        logger.info(f"Userbot dinleme modu /off komutuyla DEVRE DIŞI bırakıldı ve liste sıfırlandı (Admin: {ADMIN_ID}).")
    else:
        if 'interacted_users' in settings and settings['interacted_users']:
             settings['interacted_users'] = {}
             await save_settings(context, settings)
             logger.info("Dinleme zaten kapalıydı, ancak etkileşim listesi temizlendi.")
        await update.message.reply_text(get_text(context, "already_stopped"))

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Received command '/list' from user ID {user_id}. Comparing with ADMIN_ID {ADMIN_ID}.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt for /list by user ID {user_id}.")
        return

    settings = get_current_settings(context)
    interacted = settings.get('interacted_users', {})
    lang = settings.get('language', 'tr')

    if not interacted or not settings.get('is_listening', False):
        await update.message.reply_text(get_text(context, "list_empty"))
        return

    try:
        sorted_users = sorted(
            interacted.items(),
            key=lambda item: datetime.fromisoformat(item[1].get('timestamp', '1970-01-01T00:00:00+00:00')),
            reverse=True
        )
    except Exception as sort_e:
         logger.error(f"/list: Etkileşim listesi sıralama hatası: {sort_e}")
         sorted_users = list(interacted.items())

    list_text = get_text(context, "list_title") + "\n\n"
    count = 0
    max_list_items = 30

    for user_id_str, data in sorted_users:
        if count >= max_list_items:
             list_text += f"\n... ve {len(sorted_users) - max_list_items} diğerleri."
             break

        name = data.get('name', f'ID:{user_id_str}')
        link = data.get('link', None)
        interaction_type = data.get('type', 'unknown')

        try:
            user_id_int = int(user_id_str)
            if interaction_type == 'dm':
                 user_link = f"tg://user?id={user_id_int}"
                 list_text += f"• <a href=\"{user_link}\">{name}</a> (Özel Mesaj)\n"
            elif link:
                 list_text += f"• <a href=\"{link}\">{name}</a> ({interaction_type})\n"
            else:
                 list_text += f"• {name} ({interaction_type} - ID: {user_id_int})\n"
            count += 1
        except ValueError:
             logger.warning(f"/list: Geçersiz kullanıcı ID'si string'i: {user_id_str}")
             list_text += f"• {name} (ID: {user_id_str}, Tip: {interaction_type})\n"
             count += 1
        except Exception as format_e:
             logger.error(f"/list: Liste formatlama hatası for {user_id_str}: {format_e}")
             list_text += f"• {name} (formatlama hatası)\n"
             count += 1

    try:
        await update.message.reply_text(
            list_text,
            parse_mode=TGParseMode.HTML,
            disable_web_page_preview=True
        )
    except TelegramError as e:
         logger.error(f"/list gönderilemedi: {e}")
         await update.message.reply_text(f"❌ Liste gönderilirken hata oluştu: {e}")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Received command '/ping' from user ID {user_id}. Comparing with ADMIN_ID {ADMIN_ID}.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized access attempt for /ping by user ID {user_id}.")
        return

    userbot_status_key = "userbot_disconnected"
    userbot_status_text = ""
    if user_bot_client and user_bot_client.is_connected:
        try:
            await user_bot_client.get_me()
            userbot_status_key = "userbot_connected"
        except Exception as e:
            logger.warning(f"Ping sırasında userbot erişim hatası: {e}")
            userbot_status_key = "userbot_error"
    else:
        userbot_status_key = "userbot_disconnected"

    userbot_status_text = get_text(context, userbot_status_key)

    await update.message.reply_text(
        get_text(context, "ping_reply", userbot_status=userbot_status_text)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    logger.info(f"Received button callback '{query.data}' from user ID {user_id}. Comparing with ADMIN_ID {ADMIN_ID}.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized button callback '{query.data}' attempt by user ID {user_id}.")
        return

    callback_data = query.data
    settings = get_current_settings(context)

    logger.info(f"Button callback işleniyor: {callback_data}")

    if callback_data == 'select_language':
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
        except TelegramError as e: logger.error(f"Dil seçim menüsü düzenlenirken hata: {e}")

    elif callback_data == 'prompt_settings':
        await prompt_settings_menu(update, context)

    elif callback_data.startswith('lang_'):
        lang_code = callback_data.split('_')[1]
        if lang_code in localization:
            settings['language'] = lang_code
            await save_settings(context, settings)
            logger.info(f"Dil değiştirildi: {lang_code}")
            keyboard = _generate_main_menu_keyboard(context)
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await query.edit_message_text(
                    get_text(context, "settings_menu_title"),
                    reply_markup=reply_markup
                )
            except TelegramError as e: logger.error(f"Dil değiştirildikten sonra menü düzenlenirken hata: {e}")
        else:
            logger.warning(f"Geçersiz dil kodu: {lang_code}")
            await query.answer("Geçersiz dil!", show_alert=True)

    elif callback_data == 'prompt_set_age':
        context.user_data['next_action'] = 'set_age'
        try: await query.edit_message_text(get_text(context, "enter_age"))
        except TelegramError as e: logger.error(f"Yaş isteme mesajı düzenlenirken hata: {e}")

    elif callback_data == 'prompt_set_gender':
        context.user_data['next_action'] = 'set_gender'
        try: await query.edit_message_text(get_text(context, "enter_gender"))
        except TelegramError as e: logger.error(f"Cinsiyet isteme mesajı düzenlenirken hata: {e}")

    elif callback_data == 'prompt_toggle_swearing':
        prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
        prompt_config['use_swearing'] = not prompt_config.get('use_swearing', True)
        settings['prompt_config'] = prompt_config
        await save_settings(context, settings)
        await query.answer(get_text(context, "setting_updated"))
        await prompt_settings_menu(update, context)

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
        try: await query.edit_message_text(get_text(context, "enter_suffix"))
        except TelegramError as e: logger.error(f"Suffix isteme mesajı düzenlenirken hata: {e}")

    elif callback_data == 'main_menu':
        context.user_data.pop('next_action', None)
        keyboard = _generate_main_menu_keyboard(context)
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                get_text(context, "settings_menu_title"),
                reply_markup=reply_markup
            )
        except TelegramError as e:
            if "Message is not modified" not in str(e):
                 logger.error(f"Ana menüye geri dönerken hata: {e}")

async def prompt_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return # Should not happen if called from button_callback
    # Admin check already done in button_callback

    keyboard = _generate_prompt_settings_keyboard(context)
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(get_text(context, "prompt_menu_title"), reply_markup=reply_markup)
    except TelegramError as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Prompt menüsü düzenlenirken hata: {e}")

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    logger.info(f"Received text input from user ID {user_id}. Checking if admin and if action pending.")
    if user_id != ADMIN_ID:
        logger.warning(f"Unauthorized text input from user ID {user_id}. Text: {update.message.text}")
        return

    action = context.user_data.pop('next_action', None)
    if not action:
        logger.debug(f"Admin'den ({user_id}) beklenen bir eylem olmadan metin mesajı alındı: {update.message.text}")
        return

    logger.info(f"Processing pending action '{action}' for admin {user_id} with text: {update.message.text}")
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
                context.user_data['next_action'] = 'set_age'
        except ValueError:
            await update.message.reply_text(get_text(context, "error_invalid_input") + " (Lütfen sadece sayı girin)")
            context.user_data['next_action'] = 'set_age'

    elif action == 'set_gender':
        if text:
            gender = text[:30]
            prompt_config['gender'] = gender
            settings['prompt_config'] = prompt_config
            await save_settings(context, settings)
            await update.message.reply_text(get_text(context, "gender_updated", gender=gender))
            should_show_menu_again = True
        else:
            await update.message.reply_text(get_text(context, "error_invalid_input"))
            context.user_data['next_action'] = 'set_gender'

    elif action == 'set_suffix':
        suffix = text[:50]
        if suffix == '-': suffix = ""
        prompt_config['custom_suffix'] = suffix
        settings['prompt_config'] = prompt_config
        await save_settings(context, settings)
        await update.message.reply_text(get_text(context, "suffix_updated", suffix=suffix if suffix else "[Boş]"))
        should_show_menu_again = True

    if should_show_menu_again:
         keyboard = _generate_prompt_settings_keyboard(context)
         reply_markup = InlineKeyboardMarkup(keyboard)
         await update.message.reply_text(get_text(context, "prompt_menu_title"), reply_markup=reply_markup)

user_bot_client: Client = None
ptb_app: Application = None

try:
    genai.configure(api_key=AI_API_KEY)
    ai_model_instance = genai.GenerativeModel(DEFAULT_SETTINGS['ai_model'])
    logger.info(f"Gemini AI Modeli ({DEFAULT_SETTINGS['ai_model']}) yapılandırıldı.")
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    logger.info(f"Gemini AI güvenlik ayarları: {safety_settings}")
except Exception as e:
    logger.critical(f"❌ Gemini AI yapılandırılamadı: {e}", exc_info=True)
    ai_model_instance = None
    safety_settings = None

async def get_pyrogram_settings() -> dict:
    if not ptb_app:
        logger.error("PTB Application Pyrogram ayarları için kullanılamıyor.")
        return DEFAULT_SETTINGS.copy()
    context = ContextTypes.DEFAULT_TYPE(application=ptb_app, chat_id=ADMIN_ID, user_id=ADMIN_ID)
    return get_current_settings(context)

async def save_pyrogram_settings(settings: dict):
    if not ptb_app:
        logger.error("PTB Application Pyrogram ayarları kaydetmek için kullanılamıyor.")
        return
    context = ContextTypes.DEFAULT_TYPE(application=ptb_app, chat_id=ADMIN_ID, user_id=ADMIN_ID)
    await save_settings(context, settings)

async def notify_admin(client: Client, message: str):
    if ADMIN_ID:
        try:
            if ptb_app:
                 await ptb_app.bot.send_message(ADMIN_ID, message[:4096])
        except Exception as e:
            logger.error(f"Admin'e bildirim gönderilemedi ({ADMIN_ID}): {e}")

@Client.on_message(filters.private | filters.mentioned | filters.reply & ~filters.me & ~filters.service, group=1)
async def handle_user_message(client: Client, message: Message):
    if not client or not client.is_connected:
        logger.warning("Pyrogram client hazır değil, mesaj işlenemiyor.")
        return

    settings = {} # Hata durumunda tanımlı olması için
    try:
        settings = await get_pyrogram_settings()
        if not settings.get('is_listening', False):
            return

        my_id = client.me.id
        sender = message.from_user or message.sender_chat
        if not sender:
            logger.warning(f"Mesajda gönderici bilgisi yok: {message.id} in {message.chat.id}")
            return
        sender_id = sender.id
        sender_name = getattr(sender, 'title', getattr(sender, 'first_name', f"ID:{sender_id}"))
        if hasattr(sender, 'last_name') and sender.last_name: sender_name += f" {sender.last_name}"
        chat_id = message.chat.id
        message_id = message.id
        message_text = message.text or message.caption or ""
        message_link = message.link

        interaction_type = "unknown"
        if message.chat.type == ChatType.PRIVATE: interaction_type = "dm"
        elif message.mentioned: interaction_type = "mention"
        elif message.reply_to_message and message.reply_to_message.from_user_id == my_id: interaction_type = "reply"
        else:
             logger.warning(f"Beklenmeyen mesaj türü algılandı (dinleme açıkken): chat_id={chat_id}, msg_id={message_id}, sender_id={sender_id}")
             return

        logger.info(f"İşlenecek mesaj ({interaction_type}): {sender_name} ({sender_id}) -> {message_text[:50] if message_text else '[Metin/Başlık Yok]'} (Link: {message_link})")

        now_utc = datetime.now(pytz.utc)
        interacted_users = settings.get('interacted_users', {})
        interacted_users[str(sender_id)] = {
            "name": sender_name,
            "link": message_link,
            "type": interaction_type,
            "timestamp": now_utc.isoformat()
        }
        settings['interacted_users'] = interacted_users
        await save_pyrogram_settings(settings)

        if not ai_model_instance:
             logger.error("AI modeli başlatılmamış, yanıt verilemiyor.")
             await notify_admin(client, "❌ Hata: AI modeli başlatılamadığı için AFK yanıtı verilemedi.")
             return
        prompt_config = settings.get('prompt_config', DEFAULT_SETTINGS['prompt_config'])
        lang = settings.get('language', 'tr')
        full_prompt = generate_full_prompt(prompt_config, lang, sender_name, interaction_type, message_text)
        # logger.debug(f"Oluşturulan AI Prompt'u:\n---\n{full_prompt}\n---")
        ai_content = full_prompt

        logger.info(f"AI ({settings.get('ai_model', 'bilinmiyor')}) modeline istek gönderiliyor...")
        response = await ai_model_instance.generate_content_async(
            ai_content,
            safety_settings=safety_settings
        )
        ai_reply_text = response.text
        logger.info(f"AI yanıtı alındı: {ai_reply_text[:100]}...")

        suffix = prompt_config.get('custom_suffix', "")
        final_reply = ai_reply_text
        if suffix: final_reply += f"\n\n{suffix}"
        await client.send_message(
            chat_id=chat_id,
            text=final_reply,
            reply_to_message_id=message_id,
            parse_mode=PyroParseMode.MARKDOWN
        )
        logger.info(f"Yanıt gönderildi: chat_id={chat_id}, reply_to={message_id}")

    except (PeerIdInvalid, ChannelInvalid, ChannelPrivate) as e:
        peer_id_info = f"Chat ID: {message.chat.id}" if message else "Bilinmiyor"
        logger.error(f"Pyrogram Peer/Channel Hatası ({peer_id_info}): {e}. Bu sohbetten gelen güncellemeler işlenemiyor.", exc_info=False)
    except (UserIsBlocked, UserNotParticipant) as e:
        logger.warning(f"Mesaj gönderilemedi (kullanıcı engelledi veya grupta değil): {e} (Chat ID: {message.chat.id if message else 'N/A'})")
    except GoogleAPIError as e:
        logger.error(f"Google AI API Hatası: {e}", exc_info=True)
        error_text = get_text(None, "error_ai", lang=settings.get('language', 'tr'), error=str(e))
        await notify_admin(client, error_text)
    except Exception as e:
        logger.error(f"Mesaj işlenirken veya gönderilirken beklenmedik hata: {e}", exc_info=True)
        error_trace = traceback.format_exc()
        chat_id_info = message.chat.id if message else 'N/A'
        await notify_admin(client, get_text(None, "admin_error_notification", lang='tr',
                                             chat_id=chat_id_info,
                                             error=str(e), trace=error_trace[-1000:]))

async def main():
    global user_bot_client, ptb_app

    logger.info(f"Persistence dosyası kullanılıyor: {PERSISTENCE_FILE}")
    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)

    logger.info("Kontrol botu (PTB) Application oluşturuluyor...")
    ptb_application = Application.builder() \
        .token(TG_BOT_TOKEN) \
        .persistence(persistence) \
        .build()
    ptb_app = ptb_application

    admin_filter = ptb_filters.User(ADMIN_ID)
    ptb_application.add_handler(CommandHandler("start", start_command, filters=admin_filter))
    ptb_application.add_handler(CommandHandler("settings", settings_command, filters=admin_filter))
    ptb_application.add_handler(CommandHandler("on", on_command, filters=admin_filter))
    ptb_application.add_handler(CommandHandler("off", off_command, filters=admin_filter))
    ptb_application.add_handler(CommandHandler("list", list_command, filters=admin_filter))
    ptb_application.add_handler(CommandHandler("ping", ping_command, filters=admin_filter))
    ptb_application.add_handler(CallbackQueryHandler(button_callback)) # İçinde admin kontrolü var
    ptb_application.add_handler(MessageHandler(ptb_filters.TEXT & ~ptb_filters.COMMAND & admin_filter, handle_text_input))
    logger.info("PTB handler'ları eklendi.")

    logger.info("Pyrogram kullanıcı botu istemcisi oluşturuluyor...")
    user_bot_client = Client(
        "my_afk_userbot",
        api_id=TG_API_ID,
        api_hash=TG_API_HASH,
        session_string=TG_STRING_SESSION
    )
    logger.info("Pyrogram handler'ları tanımlandı.")

    try:
        logger.info("Kontrol botu (PTB) başlatılıyor (initialize)...")
        await ptb_application.initialize()
        logger.info("Pyrogram kullanıcı botu (Userbot) başlatılıyor...")
        await user_bot_client.start()
        my_info = await user_bot_client.get_me()
        logger.info(f"✅ Userbot başarıyla bağlandı: {my_info.first_name} (@{my_info.username}) ID: {my_info.id}")
        logger.info("Kontrol botu polling başlatılıyor (start)...")
        await ptb_application.start()
        logger.info("✅ Kontrol botu başarıyla başlatıldı.")
        logger.info("Botlar çalışıyor... Userbot dinlemesi için /on komutunu kullanın. Kapatmak için CTRL+C.")

        await idle()

    except ConnectionError as e:
         logger.critical(f"❌ Pyrogram bağlanamadı! String Session geçersiz veya ağ sorunu: {e}", exc_info=True)
         if ptb_application.running: await ptb_application.stop()
    except TelegramError as e:
        logger.critical(f"❌ Kontrol botu (PTB) hatası: {e}", exc_info=True)
        if user_bot_client.is_connected: await user_bot_client.stop()
    except Exception as e:
        logger.critical(f"❌ Ana çalıştırma döngüsünde kritik hata: {e}", exc_info=True)
    finally:
        logger.info("Botlar durduruluyor...")
        tasks = []
        if user_bot_client and user_bot_client.is_connected:
            logger.info("Pyrogram userbot durduruluyor...")
            tasks.append(asyncio.create_task(user_bot_client.stop()))
        if ptb_application and ptb_application.running:
            logger.info("Kontrol botu (PTB) durduruluyor...")
            tasks.append(asyncio.create_task(ptb_application.stop()))
            tasks.append(asyncio.create_task(ptb_application.shutdown()))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Pyrogram userbot durduruldu.")
        logger.info("Kontrol botu (PTB) durduruldu.")
        logger.info("Tüm işlemler durduruldu.")


if __name__ == "__main__":
    print("==========================================")
    print("  Telegram AFK Yanıt Botu v3 (PTB Kontrol)")
    print("==========================================")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("CTRL+C algılandı, botlar durduruluyor...")
    except Exception as e:
        logger.critical(f"Ana çalıştırma bloğunda beklenmedik hata: {e}", exc_info=True)

