import logging
import asyncio
import os
import io
import uuid
import asyncpg
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

# --- ЖӨНДӨӨЛӨР ---
API_TOKEN = '8388259014:AAFlyJXykZUZRBWSmiBZsCFlgIhQsnCLCWo'
ADMIN_IDS = [5689542074, 5148336517]
# Railway'ден алган DATABASE_URL бул жерге автоматтык түрдө келет
DB_URL = os.getenv("DATABASE_URL") 
FONT_PATH = "Arial.ttf"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА МЕНЕН ИШТӨӨ ---
async def init_db():
    conn = await asyncpg.connect(DB_URL)
    # Мугалимдердин таблицасы
    await conn.execute('''CREATE TABLE IF NOT EXISTS teachers (
        uid TEXT PRIMARY KEY, name TEXT)''')
    # Пландардын таблицасы
    await conn.execute('''CREATE TABLE IF NOT EXISTS plans (
        pid TEXT PRIMARY KEY, file_id TEXT, user_id BIGINT, 
        name TEXT, class TEXT, subject TEXT)''')
    await conn.close()

def get_kg_time():
    return datetime.utcnow() + timedelta(hours=6)

# --- ШТАМП БАСУУ ---
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
            f_main = ImageFont.truetype(FONT_PATH, int(s_h * 0.16))
            f_sub = ImageFont.truetype(FONT_PATH, int(s_h * 0.10))
            f_date = ImageFont.truetype(FONT_PATH, int(s_h * 0.09))
        else: f_main = f_sub = f_date = ImageFont.load_default()

        txt1, txt2, txt3 = "ЭЛЕКТРОНДУК ТҮРДӨ", "ТЕКШЕРИЛДИ", "ОББ: ТОКТОМАМАТОВА.А"
        date_txt = get_kg_time().strftime("%d.%m.%Y | %H:%M")

        def draw_c(text, font, y_pct):
            w = draw_s.textbbox((0, 0), text, font=font)[2]
            draw_s.text(((s_w - w) / 2, int(s_h * y_pct)), text, fill=stamp_color, font=font)

        draw_c(txt1, f_sub, 0.15); draw_c(txt2, f_main, 0.40); draw_c(txt3, f_sub, 0.70)
        main_img.paste(stamp_canvas, (base_w - s_w - 50, base_h - s_h - 100), stamp_canvas)
        draw_m = ImageDraw.Draw(main_img)
        draw_m.text((base_w - s_w - 30, base_h - 95), date_txt, fill=stamp_color, font=f_date)
        
        out = io.BytesIO()
        main_img.convert("RGB").save(out, format="JPEG", quality=95)
        out.seek(0)
        return out, None
    except Exception as e: return None, str(e)

# --- БОТ ХЕНДЛЕРЛЕРИ ---
user_states = {}

@dp.message(Command("start"))
async def start(m: types.Message):
    conn = await asyncpg.connect(DB_URL)
    teacher = await conn.fetchrow("SELECT name FROM teachers WHERE uid = $1", str(m.from_user.id))
    await conn.close()
    
    if teacher:
        await m.answer(f"Салам, {teacher['name']}! Пландын сүрөтүн жөнөтүңүз.")
    else:
        await m.answer("Салам! Каттоо үчүн аты-жөнүңүздү жазыңыз:")
        user_states[m.from_user.id] = {'step': 'register'}

@dp.message(F.text, lambda m: user_states.get(m.from_user.id, {}).get('step') == 'register')
async def register(m: types.Message):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("INSERT INTO teachers (uid, name) VALUES ($1, $2) ON CONFLICT (uid) DO UPDATE SET name = $2", str(m.from_user.id), m.text)
    await conn.close()
    await m.answer(f"Рахмат, {m.text}! Эми сүрөт жиберсеңиз болот.")
    user_states[m.from_user.id] = {}

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    user_states[m.from_user.id] = {'photo': m.photo[-1].file_id, 'step': 'class'}
    builder = InlineKeyboardBuilder()
    for i in range(1, 12): builder.add(InlineKeyboardButton(text=f"{i}-кл", callback_data=f"class_{i}"))
    builder.adjust(4)
    await m.answer("Классты тандаңыз:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("class_"))
async def set_class(c: types.CallbackQuery):
    class_num = c.data.split("_")[1]
    user_states[c.from_user.id].update({'class': class_num, 'step': 'subject'})
    await c.message.edit_text(f"Тандалды: {class_num}-класс. Сабактын атын жазыңыз:")

@dp.message(F.text, lambda m: user_states.get(m.from_user.id, {}).get('step') == 'subject')
async def set_subject(m: types.Message):
    uid = m.from_user.id
    state = user_states[uid]
    pid = str(uuid.uuid4())[:8]
    
    conn = await asyncpg.connect(DB_URL)
    teacher = await conn.fetchrow("SELECT name FROM teachers WHERE uid = $1", str(uid))
    await conn.execute("INSERT INTO plans (pid, file_id, user_id, name, class, subject) VALUES ($1, $2, $3, $4, $5, $6)",
                       pid, state['photo'], uid, teacher['name'], state['class'], m.text)
    await conn.close()
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{pid}"))
    builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{pid}"))
    
    for admin in ADMIN_IDS:
        cap = f"📩 План: {teacher['name']}\n📚 Сабак: {m.text}\n👥 Класс: {state['class']}"
        try: await bot.send_photo(admin, photo=state['photo'], caption=cap, reply_markup=builder.as_markup())
        except: pass
    await m.answer("План текшерүүгө жиберилди.")
    user_states[uid] = {}

@dp.callback_query(F.data.startswith("ok_"))
async def approve(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    conn = await asyncpg.connect(DB_URL)
    p = await conn.fetchrow("SELECT * FROM plans WHERE pid = $1", pid)
    
    if not p:
        await conn.close()
        return await c.answer("Ката: План табылган жок!", show_alert=True)
    
    await c.answer("Штамп басылууда...")
    file = await bot.get_file(p['file_id'])
    content = await bot.download_file(file.file_path)
    img_out, err = add_stamp_and_date(content.read())
    
    if img_out:
        await bot.send_photo(p['user_id'], photo=BufferedInputFile(img_out.read(), filename="res.jpg"), caption="✅ Планыңыз кабыл алынды!")
        await c.message.edit_caption(caption=f"✅ Текшерилди: {p['name']}\n📖 {p['subject']}, {p['class']}-класс")
        await conn.execute("DELETE FROM plans WHERE pid = $1", pid)
    else: await c.answer(f"Ката: {err}", show_alert=True)
    await conn.close()

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
