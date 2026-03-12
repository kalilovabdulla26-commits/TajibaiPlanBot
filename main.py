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
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google.oauth2.service_account import Credentials
from PIL import Image, ImageDraw, ImageFont

# --- ЖӨНДӨӨЛӨР ---
API_TOKEN = '8388259014:AAFlyJXykZUZRBWSmiBZsCFlgIhQsnCLCWo'
ADMIN_IDS = [5689542074, 5148336517] 
SPREADSHEET_ID = '1g74mCtl8zqbcDCJ306q4eoPWJXwOnEdpOTMAj8_cPcU'
USERS_FILE = "users.json"

pending_plans = {}
user_states = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- ФУНКЦИЯЛАР ---
def get_users():
    if not os.path.exists(USERS_FILE): return []
    try:
        with open(USERS_FILE, "r") as f: return json.load(f)
    except: return []

def save_user(user_id):
    users = get_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_FILE, "w") as f: json.dump(users, f)

def get_kg_time():
    return datetime.utcnow() + timedelta(hours=6)

def log_to_sheet(teacher_name, status):
    try:
        json_creds = os.environ.get('GOOGLE_JSON')
        if not json_creds: return
        info = json.loads(json_creds)
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        sheet.append_row([get_kg_time().strftime("%d.%m.%Y %H:%M"), teacher_name, status])
    except Exception as e: logging.error(f"Sheet error: {e}")

# ОҢДОЛГОН ШТАМП ФУНКЦИЯСЫ (ШРИФТ МЕНЕН)
def add_stamp_and_date(image_bytes):
    try:
        main_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        base_w, base_h = main_img.size
        s_w, s_h = int(base_w * 0.4), int(base_w * 0.4 * 0.5)
        stamp_canvas = Image.new('RGBA', (s_w, s_h), (0, 0, 0, 0))
        draw_s = ImageDraw.Draw(stamp_canvas)
        stamp_color = (26, 26, 140, 255)
        
        draw_s.rectangle([0, 0, s_w, s_h], outline=stamp_color, width=max(3, int(s_w*0.02)))
        
        # СЕНИН ПАПКАҢДАГЫ ШРИФТТИ КОЛДОНУУ
        # Шрифттин атын өзүң жүктөгөн файлга жараша өзгөрт (мисалы: "arial.ttf")
        font_name = "arial.ttf" 
        
        if os.path.exists(font_name):
            f_main = ImageFont.truetype(font_name, int(s_h * 0.14))
            f_sub = ImageFont.truetype(font_name, int(s_h * 0.10))
            f_date = ImageFont.truetype(font_name, int(s_h * 0.09))
        else:
            logging.warning("Шрифт табылган жок! Стандарттык колдонулат.")
            f_main = f_sub = f_date = ImageFont.load_default()

        txt1 = "ЭЛЕКТРОНДУК ТҮРДӨ"
        txt2 = "ТЕКШЕРИЛДИ"
        txt3 = "ОББ: ТОКТОМАМАТОВА.А"
        date_txt = get_kg_time().strftime("%d.%m.%Y | %H:%M")

        def draw_c(text, font, y_pct):
            try:
                w = draw_s.textbbox((0, 0), text, font=font)[2]
            except:
                w = len(text) * 8
            draw_s.text(((s_w - w) / 2, int(s_h * y_pct)), text, fill=stamp_color, font=font)

        draw_c(txt1, f_sub, 0.15)
        draw_c(txt2, f_main, 0.40)
        draw_c(txt3, f_sub, 0.70)
        
        main_img.paste(stamp_canvas, (base_w - s_w - 50, base_h - s_h - 100), stamp_canvas)
        draw_m = ImageDraw.Draw(main_img)
        draw_m.text((base_w - s_w - 30, base_h - 95), date_txt, fill=stamp_color, font=f_date)
        
        out = io.BytesIO()
        main_img.convert("RGB").save(out, format="JPEG", quality=95)
        out.seek(0)
        return out, None
    except Exception as e: return None, str(e)

# --- ХЕНДЛЕРЛЕР ---
@dp.message(Command("start"))
async def start(m: types.Message):
    save_user(m.from_user.id)
    await m.answer("Салам! Пландын сүрөтүн жөнөтүңүз.")

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    save_user(m.from_user.id)
    user_states[m.from_user.id] = {'photo': m.photo[-1].file_id}
    await m.answer("✅ Сүрөт алынды. Аты-жөнүңүздү жазыңыз:")

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_name(m: types.Message):
    uid = m.from_user.id
    if uid in user_states:
        name, pid = m.text, str(uuid.uuid4())[:8]
        pending_plans[pid] = {'file_id': user_states[uid]['photo'], 'user_id': uid, 'name': name}
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{pid}"))
        builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{pid}"))
        
        for admin_id in ADMIN_IDS:
            try: await bot.send_photo(admin_id, photo=user_states[uid]['photo'], caption=f"📩 Жаңы план: {name}", reply_markup=builder.as_markup())
            except: pass
        await m.answer("План текшерүүгө жиберилди.")
        del user_states[uid]

@dp.callback_query(F.data.startswith("ok_"))
async def approve(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    if pid not in pending_plans: return await c.answer("Ката: План табылган жок.", show_alert=True)
    
    await c.answer("Штамп басылууда...")
    p = pending_plans[pid]
    file = await bot.get_file(p['file_id'])
    content = await bot.download_file(file.file_path)
    img_out, err = add_stamp_and_date(content.read())
    
    if img_out:
        await bot.send_photo(p['user_id'], photo=BufferedInputFile(img_out.read(), filename="res.jpg"), caption="✅ Планыңыз кабыл алынды!")
        await c.message.edit_caption(caption=f"✅ {p['name']} - Кабыл алынды.")
        log_to_sheet(p['name'], "Кабыл алынды")
    else: await c.answer(f"Ката: {err}", show_alert=True)
    if pid in pending_plans: del pending_plans[pid]

@dp.message(Command("send"), F.from_user.id.in_(ADMIN_IDS))
async def broadcast(m: types.Message):
    msg = m.text.replace("/send", "").strip()
    if not msg: return await m.answer("Текст жазыңыз!")
    users, count = get_users(), 0
    for u in users:
        try:
            await bot.send_message(u, msg)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await m.answer(f"Жөнөтүлдү: {count}")

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
