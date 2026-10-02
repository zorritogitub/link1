import os
import json
import asyncio
import logging
import threading
from pathlib import Path

from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")  # Render la inyecta sola
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    raise SystemExit("❌ Falta la variable BOT_TOKEN")

BASE_DIR = Path(__file__).parent
ADMINS_FILE = BASE_DIR / "admins.json"
USERS_FILE = BASE_DIR / "usuarios.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

# ==================== PERSISTENCIA ====================
def leer_json(path: Path, fallback: dict) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def guardar_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def cargar_admins() -> list:
    return leer_json(ADMINS_FILE, {"admins": []}).get("admins", [])


def cargar_usuarios() -> list:
    return leer_json(USERS_FILE, {"usuarios": []}).get("usuarios", [])


ADMINS = set(cargar_admins())
USUARIOS = cargar_usuarios()


def es_admin(chat_id) -> bool:
    return str(chat_id) in ADMINS


# ==================== COMANDOS DEL BOT ====================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if es_admin(chat_id):
        texto = (
            "👑 <b>Panel de administrador</b>\n\n"
            "Comandos disponibles:\n"
            "/agregar &lt;chat_id&gt; — Añadir destinatario\n"
            "/quitar &lt;chat_id&gt; — Eliminar destinatario\n"
            "/lista — Ver destinatarios\n"
            "/limpiar — Vaciar la lista\n"
            "/miid — Ver tu chat_id\n"
            "/ayuda — Ayuda"
        )
    else:
        texto = (
            "👋 Hola. Este bot notifica códigos de acceso.\n\n"
            f"Tu chat_id es: <code>{chat_id}</code>\n\n"
            "Pide a un admin que te agregue."
        )
    await update.message.reply_text(texto, parse_mode="HTML")


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Comandos</b>\n\n"
        "/agregar &lt;chat_id&gt; (admin)\n"
        "/quitar &lt;chat_id&gt; (admin)\n"
        "/lista (admin)\n"
        "/limpiar (admin)\n"
        "/miid\n"
        "/ayuda",
        parse_mode="HTML",
    )


async def cmd_miid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 Tu chat_id es: <code>{chat_id}</code>",
        parse_mode="HTML",
    )


async def cmd_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_chat.id):
        await update.message.reply_text("⛔ No autorizado.")
        return
    if not USUARIOS:
        await update.message.reply_text("📭 No hay destinatarios.")
        return
    lineas = "\n".join(f"{i+1}. <code>{u}</code>" for i, u in enumerate(USUARIOS))
    await update.message.reply_text(
        f"👥 <b>Destinatarios ({len(USUARIOS)})</b>\n\n{lineas}",
        parse_mode="HTML",
    )


async def cmd_agregar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_chat.id):
        await update.message.reply_text("⛔ No autorizado.")
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Uso: <code>/agregar 123456789</code>", parse_mode="HTML"
        )
        return
    nuevo = context.args[0].strip()
    if not nuevo.lstrip("-").isdigit():
        await update.message.reply_text("⚠️ El chat_id debe ser numérico.")
        return
    if nuevo in USUARIOS:
        await update.message.reply_text("ℹ️ Ese ID ya está en la lista.")
        return
    USUARIOS.append(nuevo)
    guardar_json(USERS_FILE, {"usuarios": USUARIOS})
    await update.message.reply_text(
        f"✅ Agregado: <code>{nuevo}</code>\nTotal: {len(USUARIOS)}",
        parse_mode="HTML",
    )


async def cmd_quitar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_chat.id):
        await update.message.reply_text("⛔ No autorizado.")
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Uso: <code>/quitar 123456789</code>", parse_mode="HTML"
        )
        return
    objetivo = context.args[0].strip()
    if objetivo not in USUARIOS:
        await update.message.reply_text("❌ Ese ID no estaba en la lista.")
        return
    USUARIOS.remove(objetivo)
    guardar_json(USERS_FILE, {"usuarios": USUARIOS})
    await update.message.reply_text(
        f"🗑️ Eliminado: <code>{objetivo}</code>\nTotal: {len(USUARIOS)}",
        parse_mode="HTML",
    )


async def cmd_limpiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_chat.id):
        await update.message.reply_text("⛔ No autorizado.")
        return
    USUARIOS.clear()
    guardar_json(USERS_FILE, {"usuarios": USUARIOS})
    await update.message.reply_text("🧹 Lista vaciada.")


# ==================== TELEGRAM APP ====================
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", cmd_start))
telegram_app.add_handler(CommandHandler("ayuda", cmd_ayuda))
telegram_app.add_handler(CommandHandler("help", cmd_ayuda))
telegram_app.add_handler(CommandHandler("miid", cmd_miid))
telegram_app.add_handler(CommandHandler("lista", cmd_lista))
telegram_app.add_handler(CommandHandler("agregar", cmd_agregar))
telegram_app.add_handler(CommandHandler("quitar", cmd_quitar))
telegram_app.add_handler(CommandHandler("limpiar", cmd_limpiar))

# ==================== FLASK ====================
flask_app = Flask(__name__)

tg_loop: asyncio.AbstractEventLoop = None


@flask_app.route("/health")
def health():
    return "OK", 200


@flask_app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    fut = asyncio.run_coroutine_threadsafe(
        telegram_app.process_update(update), tg_loop
    )
    try:
        fut.result(timeout=10)
    except Exception as e:
        logger.error(f"Error procesando update: {e}")
    return "OK", 200


@flask_app.route("/api/codigo", methods=["POST"])
def api_codigo():
    """La web manda el código aquí y el bot lo reenvía a todos los usuarios."""
    data = request.get_json(silent=True) or {}
    codigo = str(data.get("codigo", "")).strip()

    if not codigo.isdigit() or len(codigo) != 6:
        return jsonify({"ok": False, "error": "Código inválido"}), 400

    if not USUARIOS:
        return jsonify({"ok": False, "error": "Sin destinatarios"}), 503

    mensaje = f"🔐 Código de WhatsApp: <b>{codigo}</b>"

    async def _enviar_todos():
        enviados = 0
        for chat_id in USUARIOS:
            try:
                await telegram_app.bot.send_message(
                    chat_id=chat_id, text=mensaje, parse_mode="HTML"
                )
                enviados += 1
            except Exception as e:
                logger.warning(f"❌ Error enviando a {chat_id}: {e}")
        return enviados

    fut = asyncio.run_coroutine_threadsafe(_enviar_todos(), tg_loop)
    enviados = fut.result(timeout=30)

    return jsonify({
        "ok": enviados > 0,
        "enviados": enviados,
        "total": len(USUARIOS),
    })


@flask_app.route("/api/estado")
def api_estado():
    return jsonify({"ok": True, "destinatarios": len(USUARIOS)})


# ==================== ARRANQUE ====================
def _run_telegram_forever():
    """Corre el bot de Telegram en su propio event loop (hilo aparte)."""
    global tg_loop
    asyncio.set_event_loop(asyncio.new_event_loop())
    tg_loop = asyncio.get_event_loop()

    async def _setup():
        await telegram_app.initialize()
        await telegram_app.start()
        if RENDER_URL:
            webhook_url = f"{RENDER_URL}/telegram/webhook"
            await telegram_app.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook registrado: {webhook_url}")
        else:
            logger.warning("⚠️ RENDER_EXTERNAL_URL no definida")

    tg_loop.run_until_complete(_setup())
    tg_loop.run_forever()


if __name__ == "__main__":
    hilo_tg = threading.Thread(target=_run_telegram_forever, daemon=True)
    hilo_tg.start()

    logger.info(f"🚀 Flask en puerto {PORT}")
    logger.info(f"👑 Admins: {ADMINS or '(ninguno)'}")
    logger.info(f"👥 Usuarios: {USUARIOS}")
    flask_app.run(host="0.0.0.0", port=PORT)
