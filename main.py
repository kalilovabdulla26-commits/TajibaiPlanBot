import logging
import asyncio
import os
import io
import uuid
import json
import gspread
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google.oauth2.service_account import Credentials
from PIL import Image, ImageDraw, ImageFont

# --- ЖӨНДӨӨЛӨР ---
API_TOKEN = '8388259014:AAFlyJXykZUZRBWSmiBZsCFlgIhQsnCLCWo'
ADMIN_IDS = [5689542074, 5148336517] 
SPREADSHEET_ID = '1g74mCtl8zqbcDCJ306q4eoPWJXwOnEdpOTMAj8_cPcU'
USERS_FILE = "users.json"
PLANS_FILE = "pending_plans.json" # Пландар сактала турган файл
FONT_PATH = "arial.ttf" # БУЛ ЖЕРГЕ ЖҮКТӨГӨН ШРИФТТИН АТЫН ЖАЗ

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- ФАЙЛДАР МЕНЕН ИШТӨӨ ---
def load_data(filename):
    if not os.path.exists(filename): return {}
    try:
        with open(filename, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def save_user(user_id):
    users = list(load_data(USERS_FILE)) # users.json тизме катары
    if user_id not in users:
        users.append(user_id)
        save_data(USERS_FILE, users)

def get_kg_time():
    return datetime.utcnow() + timedelta(hours=6)

# --- ШТАМП ---
def add_stamp_and_date(image_bytes):
    try:
        main_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        base_w, base_h = main_img.size
        s_w, s_h = int(base_w * 0.45), int(base_w * 0.45 * 0.5)
        stamp_canvas = Image.new('RGBA', (s_w, s_h), (0, 0, 0, 0))
        draw_s = ImageDraw.Draw(stamp_canvas)
        stamp_color = (26, 26, 140, 255)
        
        draw_s.rectangle([0, 0, s_w, s_h], outline=stamp_color, width=max(4, int(s_w*0.02)))
        
        if os.path.exists(FONT_PATH):
            f_main = ImageFont.truetype(FONT_PATH, int(s_h * 0.15))
            f_sub = ImageFont.truetype(FONT_PATH, int(s_h * 0.11))
            f_date = ImageFont.truetype(FONT_PATH, int(s_h * 0.09))
        else:
            f_main = f_sub = f_date = ImageFont.load_default()

        txt1, txt2, txt3 = "ЭЛЕКТРОНДУК ТҮРДӨ", "ТЕКШЕРИЛДИ", "ОББ: ТОКТОМАМАТОВА.А"
        date_txt = get_kg_time().strftime("%d.%m.%Y | %H:%M")

        def draw_c(text, font, y_pct):
            w = draw_s.textbbox((0, 0), text, font=font)[2]
            draw_s.text(((s_w - w) / 2, int(s_h * y_pct)), text, fill=stamp_color, font=font)

        draw_c(txt1, f_sub, 0.15); draw_c(txt2, f_main, 0.40); draw_c(txt3, f_sub, 0.70)
        main_img.paste(stamp_canvas, (base_w - s_w - 50, base_h - s_h - 100), stamp_canvas)
        draw_m = ImageDraw.Draw(main_img)
        draw_m.text((base_w - s_w - 30, base_h - 90), date_txt, fill=stamp_color, font=f_date)
        
        out = io.BytesIO()
        main_img.convert("RGB").save(out, format="JPEG", quality=95)
        out.seek(0)
        return out, None
    except Exception as e: return None, str(e)

# --- ХЕНДЛЕРЛЕР ---
user_states = {}

@dp.message(Command("start"))
async def start_cmd(m: types.Message):
    save_user(m.from_user.id)
    await m.answer("Салам! Пландын сүрөтүн жөнөтүңүз.")

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    user_states[m.from_user.id] = {'photo': m.photo[-1].file_id}
    await m.answer("✅ Сүрөт алынды. Аты-жөнүңүздү жазыңыз:")

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_name(m: types.Message):
    uid = m.from_user.id
    if uid in user_states:
        name, pid = m.text, str(uuid.uuid4())[:8]
        
        # Планды файлга сактоо
        plans = load_data(PLANS_FILE)
        plans[pid] = {'file_id': user_states[uid]['photo'], 'user_id': uid, 'name': name}
        save_data(PLANS_FILE, plans)

        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{pid}"))
        builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{pid}"))
        
        for admin_id in ADMIN_IDS:
            try: await bot.send_photo(admin_id, photo=user_states[uid]['photo'], caption=f"📩 Жаңы план: {name}", reply_markup=builder.as_markup())
            except: pass
        await m.answer("Рахмат! План текшерүүгө жиберилди.")
        del user_states[uid]

@dp.callback_query(F.data.startswith("ok_"))
async def approve(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    plans = load_data(PLANS_FILE)
    
    if pid not in plans:
        return await c.answer("Бул билдирүү эскирип калган, жаңыдан жиберип көрүңүз.", show_alert=True)
    
    await c.answer("Штамп басылууда...")
    p = plans[pid]
    file = await bot.get_file(p['file_id'])
    content = await bot.download_file(file.file_path)
    img_out, err = add_stamp_and_date(content.read())
    
    if img_out:
        await bot.send_photo(p['user_id'], photo=BufferedInputFile(img_out.read(), filename="res.jpg"), caption="✅ Планыңыз кабыл алынды!")
        await c.message.edit_caption(caption=f"✅ {p['name']} - Кабыл алынды.")
        # Google Sheet логикасын бул жерге кошсоң болот
    else: 
        await c.answer(f"Ката: {err}", show_alert=True)
    
    # Планды базадан тазалоо
    del plans[pid]
    save_data(PLANS_FILE, plans)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
