#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот «Пауза»
--------------------
Мини-продукт для первичной проверки подозрительных сообщений.

Запуск:
1) python -m venv .venv
2) source .venv/bin/activate
3) pip install python-telegram-bot==21.6
4) export BOT_TOKEN="ВАШ_ТОКЕН_ОТ_BOTFATHER"
5) python telegram_bot_pause.py

Можно также положить токен в .env:
BOT_TOKEN=...
BOT_LANG=ru
"""

from __future__ import annotations

import logging
import os
import re
import json
from dataclasses import dataclass
from typing import Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEFAULT_LANG = os.getenv("BOT_LANG", "ru")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
ANALYTICS_WEBHOOK = os.getenv("ANALYTICS_WEBHOOK", "")

def send_analytics(event: str, lang: str = "", score: int = "", user_id: int = "", username: str = "") -> None:
    if not ANALYTICS_WEBHOOK:
        return
    try:
        import requests
        requests.post(ANALYTICS_WEBHOOK, json={
            "event": event, "lang": lang, "score": score,
            "user_id": user_id, "username": username
        }, timeout=3)
    except Exception as e:
        logger.warning(f"Analytics failed: {e}")

@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    weight: int
    patterns: List[re.Pattern]
    explanation: str


I18N = {
    "ru": {
        "start": (
            "👋 Привет! Я «Пауза» — бот для первичной проверки подозрительных сообщений.\n\n"
            "Пришли мне текст SMS, письма или пересказ звонка — я покажу балл риска, "
            "какие признаки нашёл и что сделать дальше.\n\n"
            "⚠️ Не отправляй полные номера карт, SMS-коды, пароли и лишние персональные данные."
        ),
        "help": (
            "Команды:\n"
            "/start — приветствие\n"
            "/help — помощь\n"
            "/sample — показать пример\n"
            "/lang — сменить язык\n\n"
            "Просто отправь текст подозрительного сообщения."
        ),
        "sample": "Пример: «Служба безопасности банка. Срочно подтвердите данные карты и код из SMS по ссылке, иначе счёт будет заблокирован сегодня. Никому не сообщайте о звонке».",
        "empty": "Пришли текст сообщения или пересказ звонка, а я помогу оценить риск.",
        "low": "Мало явных признаков",
        "medium": "Повышенная осторожность",
        "high": "Высокий риск",
        "score": "Балл риска",
        "signals": "Найденные признаки",
        "steps": "Что сделать сейчас",
        "low_summary": "Явных маркеров немного, но это не гарантия безопасности. Если обращение неожиданное — проверь через официальный канал.",
        "medium_summary": "Есть заметные тревожные признаки. Не переходи по ссылке и не сообщай данные до проверки.",
        "high_summary": "Найдено несколько сильных признаков мошенничества. Лучше прекратить контакт и проверить ситуацию через официальный номер банка или организации.",
        "no_findings": "По заданным правилам ничего не найдено. Это не гарантия безопасности.",
        "points": "баллов",
        "steps_base": "Сделай паузу и ничего не подтверждай в ответном сообщении или по телефону.",
        "steps_link": "Не открывай ссылку из обращения. Открой официальный сайт или приложение организации самостоятельно.",
        "steps_verify": "Проверь информацию через официальный номер, чат в приложении банка или сайт организации, который ты нашёл самостоятельно.",
        "steps_sensitive": "Не отправляй код из SMS, CVV, PIN, пароли, паспортные данные и номер карты. Если уже отправил — немедленно свяжись с банком.",
        "steps_remote": "Не устанавливай приложения по чужой инструкции и не давай удалённый доступ к устройству.",
        "steps_impersonation": "Помни: упоминание банка, полиции или госоргана не подтверждает подлинность обращения.",
        "steps_report": "Сохрани переписку и сообщи о подозрительном контакте в банк и/или в полицию, особенно если уже были операции или переданы данные.",
        "steps_talk": "Если обращение неожиданное и связано с деньгами, дополнительно обсуди его с близким человеком — пауза снижает риск ошибки.",
        "language": "Выбери язык / Choose language:",
        "language_set": "Язык переключён на русский.",
    },
    "en": {
        "start": (
            "👋 Hi! I’m Pause — a bot for a quick first-pass check of suspicious messages.\n\n"
            "Send me the text of an SMS, email, or a summary of a call. I’ll show a risk score, "
            "the signals I found, and the next safe step.\n\n"
            "⚠️ Do not send full card numbers, SMS codes, passwords, or unnecessary personal data."
        ),
        "help": (
            "Commands:\n"
            "/start — welcome\n"
            "/help — help\n"
            "/sample — show a sample\n"
            "/lang — change language\n\n"
            "Just send me the suspicious message text."
        ),
        "sample": "Sample: “Bank security department. Urgently confirm your card details and SMS code via the link, or your account will be blocked today. Do not tell anyone about this call.”",
        "empty": "Send me the message text or a call summary, and I’ll help assess the risk.",
        "low": "Few obvious signs",
        "medium": "Elevated caution",
        "high": "High risk",
        "score": "Risk score",
        "signals": "Detected signals",
        "steps": "What to do now",
        "low_summary": "Few obvious markers were found, but that does not prove the message is safe. If the contact is unexpected, verify it through an official channel.",
        "medium_summary": "There are noticeable warning signs. Do not open the link or share data until you verify the request independently.",
        "high_summary": "Several strong scam indicators were found. It’s better to stop the contact and verify the situation through the official bank or organization.",
        "no_findings": "No warning signs matched the current rules. That is not proof of safety.",
        "points": "points",
        "steps_base": "Pause and do not confirm anything in a reply or over the phone.",
        "steps_link": "Do not open the link in the message. Open the official website or app yourself.",
        "steps_verify": "Verify the information through an official phone number, the bank app chat, or a website you found yourself.",
        "steps_sensitive": "Do not send SMS codes, CVV, PINs, passwords, passport details, or card numbers. If you already did, contact your bank immediately.",
        "steps_remote": "Do not install apps on someone else’s instructions and do not give remote access to your device.",
        "steps_impersonation": "Remember: mentioning a bank, police, or a government agency does not prove the contact is genuine.",
        "steps_report": "Save the conversation and report the suspicious contact to your bank and/or the police, especially if money or data was already exposed.",
        "steps_talk": "If the message is unexpected and involves money, discuss it with a trusted person or colleague — a short pause lowers the chance of a mistake.",
        "language": "Choose language / Выбери язык:",
        "language_set": "Language switched to English.",
    },
}

RULES: Dict[str, List[Rule]] = {
    "ru": [
        Rule("urgency", "Срочность и давление", 18, [re.compile(p, re.I) for p in [r"срочно", r"немедленно", r"в течение\s+\d+", r"сегодня", r"прямо сейчас", r"последний шанс", r"иначе.{0,40}(заблокиру|замороз|закро)"]], "Мошенники часто торопят, чтобы человек не успел проверить информацию через официальный канал."),
        Rule("sensitive", "Запрос конфиденциальных данных", 24, [re.compile(p, re.I) for p in [r"код\s+из\s+смс", r"cvv|cvc|cvc2|cvv2", r"пин[-\s]?код", r"номер\s+карты", r"данные\s+карты", r"паспорт(ные)?\s+данные", r"парол[ья]", r"кодовое\s+слово", r"снилс", r"инн"]], "Банки и госорганы не должны запрашивать полные платёжные данные, SMS-коды или пароли в переписке."),
        Rule("threat", "Угрозы и запугивание", 16, [re.compile(p, re.I) for p in [r"заблокиру", r"замороз", r"арест", r"уголовн", r"штраф", r"долг", r"судебн", r"подозрительн.{0,30}(операц|перевод|кредит)"]], "Запугивание используется, чтобы подавить критическое мышление и заставить действовать быстро."),
        Rule("money", "Просьба перевести деньги или «обезопасить» счёт", 22, [re.compile(p, re.I) for p in [r"перевед(ите|ьте)", r"безопасн.{0,20}сч[её]т", r"спец(иальный)?\s+сч[её]т", r"оплат(ите|ьте)", r"верификац.{0,40}(карт|сч[её]т)", r"защитн.{0,20}(сч[её]т|перевод)"]], "Классический сценарий — убедить человека самостоятельно перевести деньги якобы для защиты."),
        Rule("link", "Ссылка или просьба перейти на сторонний ресурс", 15, [re.compile(p, re.I) for p in [r"https?://", r"www\.", r"перейд(ите|ьте)\s+по\s+ссылке", r"срочная\s+ссылка", r"подтверд(ите|ьте).{0,30}по\s+ссылке", r"короткая\s+ссылка"]], "Фишинг часто начинается со ссылки, ведущей на поддельный сайт банка, маркетплейса или госоргана."),
        Rule("impersonation", "Упоминание банка, службы безопасности или госоргана", 12, [re.compile(p, re.I) for p in [r"центробанк|центральн.{0,20}банк", r"служба\s+безопасности", r"банк", r"полиц", r"фнс|налогов", r"госуслуг", r"мвд", r"страхов", r"служба\s+доставки"]], "Злоумышленники часто маскируются под доверенные организации. Само упоминание не доказывает подлинность обращения."),
        Rule("too_good", "Обещание выплаты, выигрыша или выгоды", 14, [re.compile(p, re.I) for p in [r"выигр", r"компенсац", r"выплат", r"премия", r"кэшбэк", r"доход\s+до", r"гарантированн.{0,30}(доход|прибыл)", r"инвестиц.{0,30}(выгод|доход)"]], "Неожиданная выгода — типичный крючок, после которого просят данные, оплату или переход по ссылке."),
        Rule("secrecy", "Просьба никому не рассказывать", 12, [re.compile(p, re.I) for p in [r"никому\s+не\s+говорите", r"держите\s+в\s+тайне", r"конфиденциально", r"не\s+сообщайте\s+близким", r"не\s+отключайтесь"]], "Изоляция жертвы помогает мошеннику удержать контроль над ситуацией."),
        Rule("remote", "Просьба установить приложение или дать доступ к устройству", 20, [re.compile(p, re.I) for p in [r"установ(ите|ьте)\s+приложение", r"anydesk|teamviewer|rustdesk", r"удал[её]нн.{0,30}доступ", r"продикт", r"экран\s+телефона"]], "Удалённый доступ и сторонние приложения часто нужны для кражи данных и подтверждения операций."),
    ],
    "en": [
        Rule("urgency", "Urgency and pressure", 18, [re.compile(p, re.I) for p in [r"urgent", r"immediately", r"within\s+\d+\s+(hours?|minutes?|days?)", r"today", r"right now", r"last chance", r"otherwise.{0,40}(block|suspend|freeze|close)"]], "Scammers rush people so they do not have time to verify the request through an official channel."),
        Rule("sensitive", "Request for confidential data", 24, [re.compile(p, re.I) for p in [r"sms\s+code", r"verification\s+code", r"cvv|cvc|pin", r"card\s+number", r"card\s+details", r"passport\s+details", r"password", r"security\s+word", r"ssn", r"tax\s+id"]], "Banks and public authorities should not ask for full payment details, SMS codes, or passwords in chat."),
        Rule("threat", "Threats and intimidation", 16, [re.compile(p, re.I) for p in [r"blocked", r"frozen", r"arrest", r"criminal", r"fine", r"debt", r"court", r"suspicious.{0,30}(transaction|transfer|loan)"]], "Fear is used to suppress judgment and push the victim into fast action."),
        Rule("money", "Request to move money or “protect” the account", 22, [re.compile(p, re.I) for p in [r"transfer", r"safe\s+account", r"special\s+account", r"pay", r"verify.{0,40}(card|account)", r"protect.{0,20}(account|funds|money)"]], "A classic scam script is to make the victim move money themselves “for protection”."),
        Rule("link", "Link or request to visit an external page", 15, [re.compile(p, re.I) for p in [r"https?://", r"www\.", r"click\s+the\s+link", r"open\s+the\s+link", r"confirm.{0,30}(via|through)\s+link", r"short\s+link"]], "Phishing often starts with a link to a fake bank, marketplace, or government site."),
        Rule("impersonation", "Reference to a bank, security service, or government agency", 12, [re.compile(p, re.I) for p in [r"central\s+bank", r"security\s+department", r"bank", r"police", r"tax\s+office|irs|hmrc", r"government", r"customs", r"delivery\s+service"]], "Attackers often pretend to be trusted institutions. Mentioning an organization does not prove authenticity."),
        Rule("too_good", "Promise of a payout, prize, or benefit", 14, [re.compile(p, re.I) for p in [r"you\s+won|winner", r"compensation", r"payout", r"bonus", r"cashback", r"guaranteed.{0,30}(income|profit)", r"investment.{0,30}(return|profit)"]], "Unexpected benefits are a common hook before asking for data, payment, or a link click."),
        Rule("secrecy", "Request to keep it secret", 12, [re.compile(p, re.I) for p in [r"do\s+not\s+tell\s+anyone", r"keep\s+it\s+secret", r"confidential", r"do\s+not\s+share", r"stay\s+on\s+the\s+line"]], "Isolating the victim helps the scammer stay in control."),
        Rule("remote", "Request to install an app or grant device access", 20, [re.compile(p, re.I) for p in [r"install\s+(an\s+)?app", r"anydesk|teamviewer|rustdesk", r"remote\s+access", r"screen\s+sharing", r"share\s+your\s+screen"]], "Remote access tools are often used to steal data and approve transactions."),
    ],
}


def t(lang: str, key: str) -> str:
    return I18N.get(lang, I18N["ru"])[key]


def detect_lang(text: str, fallback: str = "ru") -> str:
    cyr = len(re.findall(r"[а-яА-ЯёЁ]", text))
    lat = len(re.findall(r"[a-zA-Z]", text))
    if cyr > lat:
        return "ru"
    if lat > cyr:
        return "en"
    return fallback


def analyze(text: str, lang: str) -> dict:
    matched = []
    score = 0
    for rule in RULES[lang]:
        found = []
        for pattern in rule.patterns:
            found.extend(pattern.findall(text))
        if found:
            score += rule.weight
            matched.append({
                "id": rule.rule_id,
                "title": rule.title,
                "weight": rule.weight,
                "explanation": rule.explanation,
                "matches": found[:3],
            })
    if re.search(r"[A-ZА-Я]{4,}", text):
        score += 4
    if len(text) > 260 and len(matched) >= 2:
        score += 4
    score = min(score, 100)
    if score >= 70:
        band = ("high", t(lang, "high"), t(lang, "high_summary"))
    elif score >= 40:
        band = ("medium", t(lang, "medium"), t(lang, "medium_summary"))
    else:
        band = ("low", t(lang, "low"), t(lang, "low_summary"))
    return {"score": score, "band": band, "matched": matched}


def build_steps(score: int, matched: list, lang: str) -> List[str]:
    ids = {item["id"] for item in matched}
    steps = [t(lang, "steps_base")]
    if "link" in ids:
        steps.append(t(lang, "steps_link"))
    steps.append(t(lang, "steps_verify"))
    if "sensitive" in ids:
        steps.append(t(lang, "steps_sensitive"))
    if "remote" in ids:
        steps.append(t(lang, "steps_remote"))
    if "impersonation" in ids:
        steps.append(t(lang, "steps_impersonation"))
    if score >= 70:
        steps.append(t(lang, "steps_report"))
    if len(steps) < 5:
        steps.append(t(lang, "steps_talk"))
    return list(dict.fromkeys(steps))


def format_result(text: str, lang: str) -> str:
    result = analyze(text, lang)
    score = result["score"]
    _, label, summary = result["band"]
    lines = [
        f"*{t(lang, 'score')}:* `{score}/100` — *{label}*",
        summary,
        "",
        f"*{t(lang, 'signals')}:*",
    ]
    if result["matched"]:
        for item in result["matched"]:
            lines.append(f"• *{item['title']}* (+{item['weight']} {t(lang, 'points')})")
            lines.append(f"  {item['explanation']}")
            if item["matches"]:
                matches = ", ".join(f"`{m}`" for m in item["matches"][:3])
                lines.append(f"  {matches}")
    else:
        lines.append(t(lang, "no_findings"))
    lines.extend(["", f"*{t(lang, 'steps')}:*"])
    for step in build_steps(score, result["matched"], lang):
        lines.append(f"— {step}")
    return "\n".join(lines)


def get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", DEFAULT_LANG)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    send_analytics(
        event="start",
        lang=get_lang(context),
        user_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )
    await update.message.reply_text(t(get_lang(context), "start"))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(t(get_lang(context), "help"))


async def sample(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(t(get_lang(context), "sample"))


async def lang_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Русский", callback_data="lang:ru"), InlineKeyboardButton("English", callback_data="lang:en")]
    ])

    await update.message.reply_text(t(get_lang(context), "language"), reply_markup=keyboard)


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    context.user_data["lang"] = lang
    await query.edit_message_text(t(lang, "language_set"))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:    
        await update.message.reply_text(t(get_lang(context), "empty"))
        return
    lang = context.user_data.get("lang") or detect_lang(text, DEFAULT_LANG)
    context.user_data["lang"] = lang
        reply = format_result(text, lang)
    send_analytics(
        event="check",
        lang=lang,
        score=analyze(text, lang)["score"],
        user_id=update.effective_user.id,
        username=update.effective_user.username or ""
    )
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Put it in env or .env")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("sample", sample))
    app.add_handler(CommandHandler("lang", lang_menu))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern=r"^lang:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
