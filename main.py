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
ADMIN_ID = 5148336517
SPREADSHEET_ID = '1g74mCtl8zqbcDCJ306q4eoPWJXwOnEdpOTMAj8_cPcU'

# Убактылуу маалымат сактоо
pending_plans = {}  # Админдин макулдугун күткөндөр
user_states = {}    # Аты-жөнүн жазып жаткандар

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Кыргызстан убактысын алуу (+6 саат)
def get_kg_time():
    return datetime.utcnow() + timedelta(hours=6)

# --- GOOGLE SHEETS ФУНКЦИЯСЫ ---
def log_to_sheet(teacher_name, status):
    try:
        json_creds = os.environ.get('GOOGLE_JSON')
        if not json_creds: return
        info = json.loads(json_creds)
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(info, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        now = get_kg_time().strftime("%d.%m.%Y %H:%M")
        sheet.append_row([now, teacher_name, status])
    except Exception as e:
        logging.error(f"Таблица катасы: {e}")

# --- ШТАМП БАСУУ ФУНКЦИЯСЫ ---
def add_stamp_and_date(image_bytes):
    try:
        main_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        base_w, base_h = main_img.size
        s_w = int(base_w * 0.35) # Штампты бир аз чоңойттук
        s_h = int(s_w * 0.5)
        stamp_canvas = Image.new('RGBA', (s_w, s_h), (0, 0, 0, 0))
        draw_s = ImageDraw.Draw(stamp_canvas)
        stamp_color = (26, 26, 140, 255)
        draw_s.rectangle([0, 0, s_w, s_h], outline=stamp_color, width=int(s_w*0.02))
        
        # Шрифтти кичирейтүү (0.12, 0.10) - батышы үчүн
        f_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if os.path.exists(f_path):
            f_main = ImageFont.truetype(f_path, int(s_h * 0.15))
            f_sub = ImageFont.truetype(f_path, int(s_h * 0.11))
            f_date = ImageFont.truetype(f_path, int(s_h * 0.10))
        else:
            f_main = f_sub = f_date = ImageFont.load_default()

        txt1, txt2, txt3 = "ЭЛЕКТРОНДУК ТҮРДӨ", "ТЕКШЕРИЛДИ", "ОББ: ТОКТОМАМАТОВА.А"
        date_txt = get_kg_time().strftime("%d.%m.%Y | %H:%M")

        def draw_c(text, font, y):
            w = draw_s.textbbox((0, 0), text, font=font)[2]
            draw_s.text(((s_w - w) / 2, y), text, fill=stamp_color, font=font)

        draw_c(txt1, f_sub, s_h * 0.15)
        draw_c(txt2, f_main, s_h * 0.40)
        draw_c(txt3, f_sub, s_h * 0.70)
        
        p_x, p_y = base_w - s_w - 50, base_h - s_h - 100
        main_img.paste(stamp_canvas, (p_x, p_y), stamp_canvas)
        draw_m = ImageDraw.Draw(main_img)
        d_w = draw_m.textbbox((0,0), date_txt, font=f_date)[2]
        draw_m.text((p_x + (s_w - d_w) // 2, p_y + s_h + 5), date_txt, fill=stamp_color, font=f_date)
        
        out = io.BytesIO()
        main_img.convert("RGB").save(out, format="JPEG", quality=95)
        out.seek(0)
        return out, None
    except Exception as e: return None, str(e)

# --- ХЕНДЛЕРЛЕР ---
@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Салам! Пландын сүрөтүн жөнөтүңүз.")

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    user_states[m.from_user.id] = {'photo': m.photo[-1].file_id}
    await m.answer("Сураныч, аты-жөнүңүздү жазыңыз (мисалы: Алиев Акыл):")

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_name(m: types.Message):
    uid = m.from_user.id
    if uid in user_states and 'photo' in user_states[uid]:
        name = m.text
        plan_id = str(uuid.uuid4())[:8]
        pending_plans[plan_id] = {'file_id': user_states[uid]['photo'], 'user_id': uid, 'name': name}
        
        await m.answer(f"Рахмат, {name}! Планыңыз текшерүүгө жиберилди.")
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{plan_id}"))
        builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{plan_id}"))
        
        await bot.send_photo(ADMIN_ID, photo=user_states[uid]['photo'], 
                             caption=f"📩 Жаңы план!\nМугалим: {name}", reply_markup=builder.as_markup())
        del user_states[uid]

@dp.callback_query(F.data.startswith("ok_"))
async def approve(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    if pid in pending_plans:
        p = pending_plans[pid]
        log_to_sheet(p['name'], "Кабыл алынды")
        file = await bot.get_file(p['file_id'])
        content = await bot.download_file(file.file_path)
        img, err = add_stamp_and_date(content.read())
        if not err:
            await bot.send_photo(p['user_id'], photo=types.BufferedInputFile(img.read(), filename="res.jpg"), caption="✅ Планыңыз кабыл алынды!")
            await c.message.edit_caption(caption=f"✅ {p['name']} - План кабыл алынды.")
        del pending_plans[pid]

@dp.callback_query(F.data.startswith("no_"))
async def reject(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    if pid in pending_plans:
        p = pending_plans[pid]
        log_to_sheet(p['name'], "Четке кагылды")
        await bot.send_message(p['user_id'], text="❌ Сиздин планыңыз кабыл алынган жок.")
        await c.message.edit_caption(caption=f"❌ {p['name']} - План четке кагылды.")
        del pending_plans[pid]

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
