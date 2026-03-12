import logging
import asyncio
import os
import io
import uuid
import json
import gspread
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google.oauth2.service_account import Credentials
from PIL import Image, ImageDraw, ImageFont

# --- ЖӨНДӨӨЛӨР ---
API_TOKEN = '8388259014:AAFlyJXykZUZRBWSmiBZsCFlgIhQsnCLCWo'
ADMIN_ID = 5689542074 
SPREADSHEET_ID = '1g74mCtl8zqbcDCJ306q4eoPWJXwOnEdpOTMA/8_cPcU'
USERS_FILE = "users.txt" # Колдонуучулардын базасы

pending_plans = {}
user_states = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- КОЛДОНУУЧУЛАРДЫ САКТОО ---
def save_user(user_id):
    user_id = str(user_id)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f: f.write("")
    
    with open(USERS_FILE, "r") as f:
        users = f.read().splitlines()
    
    if user_id not in users:
        with open(USERS_FILE, "a") as f:
            f.write(user_id + "\n")

# --- БАШКА ФУНКЦИЯЛАР (Дата, Таблица, Штамп) ---
def get_kg_time():
    return datetime.utcnow() + timedelta(hours=6)

# ... (башка функциялар мурункудай калат) ...

# --- ХЕНДЛЕРЛЕР ---

@dp.message(Command("start"))
async def start(m: types.Message):
    save_user(m.from_user.id) # Колдонуучуну базага кошуу
    await m.answer("Салам! Пландын сүрөтүн жөнөтүңүз.")

# ЖАҢЫ: БАРДЫККА ЖӨНӨТҮҮ КОМАНДАСЫ
@dp.message(Command("send"), F.from_user.id == ADMIN_ID)
async def broadcast(m: types.Message):
    msg_to_send = m.text.replace("/send", "").strip()
    if not msg_to_send:
        await m.answer("Командадан кийин текст жазыңыз. Мисалы: /send Салам кесиптештер!")
        return

    if not os.path.exists(USERS_FILE):
        await m.answer("Колдонуучулар жок.")
        return

    with open(USERS_FILE, "r") as f:
        users = f.read().splitlines()

    count = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, msg_to_send)
            count += 1
            await asyncio.sleep(0.05) # Бот блокко түшпөшү үчүн аз тыныгуу
        except Exception:
            pass
    
    await m.answer(f"Билдирүү {count} колдонуучуга жөнөтүлдү.")
    
@dp.message(F.photo)
async def handle_photo(m: types.Message):
    user_states[m.from_user.id] = {'photo': m.photo[-1].file_id}
    await m.answer("✅ Сүрөт алынды. Эми аты-жөнүңүздү жазыңыз:")

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_name(m: types.Message):
    uid = m.from_user.id
    if uid in user_states:
        name = m.text
        plan_id = str(uuid.uuid4())[:8]
        pending_plans[plan_id] = {'file_id': user_states[uid]['photo'], 'user_id': uid, 'name': name}
        await m.answer(f"Рахмат, {name}! План текшерүүгө жиберилди.")
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{plan_id}"))
        builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{plan_id}"))
        await bot.send_photo(ADMIN_ID, photo=user_states[uid]['photo'], 
                             caption=f"📩 Жаңы план: {name}", reply_markup=builder.as_markup())
        del user_states[uid]

@dp.callback_query(F.data.startswith("ok_"))
async def approve(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    if pid in pending_plans:
        p = pending_plans[pid]
        log_to_sheet(p['name'], "Кабыл алынды")
        file = await bot.get_file(p['file_id'])
        content = await bot.download_file(file.file_path)
        img, _ = add_stamp_and_date(content.read())
        await bot.send_photo(p['user_id'], photo=types.BufferedInputFile(img.read(), filename="res.jpg"), caption="✅ Кабыл алынды!")
        await c.message.edit_caption(caption=f"✅ {p['name']} - Кабыл алынды.")
        del pending_plans[pid]

@dp.callback_query(F.data.startswith("no_"))
async def reject(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    if pid in pending_plans:
        p = pending_plans[pid]
        log_to_sheet(p['name'], "Четке кагылды")
        await bot.send_message(p['user_id'], text="❌ Кабыл алынган жок.")
        await c.message.edit_caption(caption=f"❌ {p['name']} - Четке кагылды.")
        del pending_plans[pid]

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
