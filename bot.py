import sqlite3
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

# CONFIG
TOKEN = os.getenv("TOKEN")
LIMITE_DIARIO = 5
DB = "agenda.db"

# BANCO
def conectar():
    return sqlite3.connect(DB)

def criar_tabela():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT,
        cliente TEXT
    )
    """)
    conn.commit()
    conn.close()

# MENU
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Agendar", callback_data="agendar_ini")],
        [InlineKeyboardButton("📊 Ver Agenda", callback_data="status_ini")],
        [InlineKeyboardButton("📆 Status do Mês", callback_data="status_mes_ini")]
    ])

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Agenda de Serviços", reply_markup=menu())

# AGENDAR INICIO
async def iniciar_agendamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["etapa"] = "data"
    context.user_data["user_id"] = query.from_user.id

    await query.message.reply_text("📅 Envie a data (DD/MM/AAAA):")

# STATUS INICIO
async def status_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["etapa"] = "ver_data"
    context.user_data["user_id"] = query.from_user.id

    await query.message.reply_text("📅 Informe a data:")

# STATUS MES INICIO
async def status_mes_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["etapa"] = "ver_mes"
    context.user_data["user_id"] = query.from_user.id

    await query.message.reply_text("📆 Informe o mês (MM/AAAA):")

# FLUXO
async def fluxo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    etapa = context.user_data.get("etapa")
    user_id = update.message.from_user.id

    if not etapa or context.user_data.get("user_id") != user_id:
        return

    texto = update.message.text

    # DATA
    if etapa == "data":
        try:
            data = datetime.strptime(texto, "%d/%m/%Y").strftime("%Y-%m-%d")
            context.user_data["data"] = data
            context.user_data["etapa"] = "cliente"
            await update.message.reply_text("👤 Nome do cliente:")
        except:
            await update.message.reply_text("❌ Data inválida")

    # CLIENTE
    elif etapa == "cliente":
        context.user_data["cliente"] = texto
        context.user_data["etapa"] = None

        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirmar", callback_data="confirmar")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_fluxo")]
        ])

        await update.message.reply_text(
            f"Confirmar?\n📅 {context.user_data['data']}\n👤 {texto}",
            reply_markup=teclado
        )

    # VER DIA
    elif etapa == "ver_data":
        try:
            data = datetime.strptime(texto, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            await update.message.reply_text("❌ Data inválida")
            return

        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("SELECT id, cliente FROM agendamentos WHERE data = ?", (data,))
        dados = cursor.fetchall()
        conn.close()

        if not dados:
            await update.message.reply_text("📭 Sem agendamentos")
            return

        for id_, nome in dados:
            teclado = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("❌ Cancelar", callback_data=f"del_{id_}"),
                    InlineKeyboardButton("🔁 Reagendar", callback_data=f"rea_{id_}")
                ]
            ])
            await update.message.reply_text(f"👤 {nome}", reply_markup=teclado)

        context.user_data["etapa"] = None

    # VER MES
    elif etapa == "ver_mes":
        try:
            mes, ano = texto.split("/")
        except:
            await update.message.reply_text("❌ Use MM/AAAA")
            return

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT data, COUNT(*) 
            FROM agendamentos
            WHERE strftime('%m', data) = ? AND strftime('%Y', data) = ?
            GROUP BY data
            ORDER BY data
        """, (mes.zfill(2), ano))

        resultados = cursor.fetchall()
        conn.close()

        if not resultados:
            await update.message.reply_text("📭 Nenhum agendamento no mês")
            return

        texto_resp = f"📆 {mes}/{ano}\n\n"

        for data, total in resultados:
            d = datetime.strptime(data, "%Y-%m-%d")
            vagas = LIMITE_DIARIO - total

            texto_resp += (
                f"{d.strftime('%d/%m')}: {total} | "
                f"{'🟢' if vagas > 0 else '🔴'} {vagas}\n"
            )

        context.user_data["etapa"] = None
        await update.message.reply_text(texto_resp)

    # REAGENDAR
    elif etapa == "nova_data":
        try:
            nova_data = datetime.strptime(texto, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            await update.message.reply_text("❌ Data inválida")
            return

        id_ = context.user_data.get("reagendar_id")

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM agendamentos WHERE data = ?", (nova_data,))
        total = cursor.fetchone()[0]

        if total >= LIMITE_DIARIO:
            await update.message.reply_text("🚫 Dia cheio")
            conn.close()
            return

        cursor.execute("UPDATE agendamentos SET data = ? WHERE id = ?", (nova_data, id_))
        conn.commit()
        conn.close()

        context.user_data.clear()
        await update.message.reply_text("🔁 Reagendado")

# CONFIRMAR
async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = context.user_data.get("data")
    cliente = context.user_data.get("cliente")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM agendamentos WHERE data = ?", (data,))
    total = cursor.fetchone()[0]

    if total >= LIMITE_DIARIO:
        await query.message.reply_text("🚫 Dia cheio")
        conn.close()
        return

    cursor.execute(
        "INSERT INTO agendamentos (data, cliente) VALUES (?, ?)",
        (data, cliente)
    )

    conn.commit()
    conn.close()

    context.user_data.clear()
    await query.message.reply_text("✅ Agendado")

# CANCELAR FLUXO
async def cancelar_fluxo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    await query.message.reply_text("❌ Cancelado")

# DELETAR
async def deletar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    id_ = int(query.data.split("_")[1])

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agendamentos WHERE id = ?", (id_,))
    conn.commit()
    conn.close()

    await query.message.reply_text("✅ Cancelado")

# REAGENDAR INICIO
async def iniciar_reagendamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    id_ = int(query.data.split("_")[1])

    context.user_data["reagendar_id"] = id_
    context.user_data["etapa"] = "nova_data"
    context.user_data["user_id"] = query.from_user.id

    await query.message.reply_text("📅 Nova data (DD/MM/AAAA):")

# RUN
app = ApplicationBuilder().token(TOKEN).build()

criar_tabela()

app.add_handler(CommandHandler("start", start))

app.add_handler(CallbackQueryHandler(iniciar_agendamento, pattern="agendar_ini"))
app.add_handler(CallbackQueryHandler(confirmar, pattern="confirmar"))
app.add_handler(CallbackQueryHandler(cancelar_fluxo, pattern="cancelar_fluxo"))

app.add_handler(CallbackQueryHandler(status_ini, pattern="status_ini"))
app.add_handler(CallbackQueryHandler(status_mes_ini, pattern="status_mes_ini"))

app.add_handler(CallbackQueryHandler(deletar, pattern="del_"))
app.add_handler(CallbackQueryHandler(iniciar_reagendamento, pattern="rea_"))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fluxo))

print("🤖 Bot rodando...")
app.run_polling()
