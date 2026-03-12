import logging
import asyncio
import os
import io
import uuid
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

# --- ЖӨНДӨӨЛӨР ---
API_TOKEN = '8388259014:AAFlyJXykZUZRBWSmiBZsCFlgIhQsnCLCWo'
ADMIN_IDS = [5689542074, 5148336517]
PLANS_FILE = "pending_plans.json"
# GitHub'дагы файлдын аты так ушундай болушу керек (баш тамга менен)
FONT_PATH = "Arial.ttf" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- ПЛАНДАРДЫ ФАЙЛГА САКТОО ---
# Бул функция бот өчүп күйсө да пландарды жоготпойт
def load_plans():
    if os.path.exists(PLANS_FILE):
        try:
            with open(PLANS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

def save_plans(plans):
    with open(PLANS_FILE, "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=4)

def get_kg_time():
    return datetime.utcnow() + timedelta(hours=6)

# --- ШТАМП БАСУУ ФУНКЦИЯСЫ ---
def add_stamp_and_date(image_bytes):
    try:
        main_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        base_w, base_h = main_img.size
        # Штамптын өлчөмү сүрөткө жараша
        s_w, s_h = int(base_w * 0.45), int(base_w * 0.45 * 0.5)
        stamp_canvas = Image.new('RGBA', (s_w, s_h), (0, 0, 0, 0))
        draw_s = ImageDraw.Draw(stamp_canvas)
        stamp_color = (26, 26, 140, 255) # Көк түс
        
        # Штамптын чеги (рамка)
        draw_s.rectangle([0, 0, s_w, s_h], outline=stamp_color, width=max(4, int(s_w*0.02)))
        
        # Шрифтти жүктөө (сенин Arial.ttf файлыңды колдонот)
        if os.path.exists(FONT_PATH):
            f_main = ImageFont.truetype(FONT_PATH, int(s_h * 0.16))
            f_sub = ImageFont.truetype(FONT_PATH, int(s_h * 0.10))
            f_date = ImageFont.truetype(FONT_PATH, int(s_h * 0.09))
        else:
            logging.error(f"КАТА: {FONT_PATH} файлы табылган жок!")
            f_main = f_sub = f_date = ImageFont.load_default()

        txt1 = "ЭЛЕКТРОНДУК ТҮРДӨ"
        txt2 = "ТЕКШЕРИЛДИ"
        txt3 = "ОББ: ТОКТОМАМАТОВА.А"
        date_txt = get_kg_time().strftime("%d.%m.%Y | %H:%M")

        def draw_c(text, font, y_pct):
            w = draw_s.textbbox((0, 0), text, font=font)[2]
            draw_s.text(((s_w - w) / 2, int(s_h * y_pct)), text, fill=stamp_color, font=font)

        draw_c(txt1, f_sub, 0.15)
        draw_c(txt2, f_main, 0.40)
        draw_c(txt3, f_sub, 0.70)
        
        # Штампты негизги сүрөткө чаптоо
        main_img.paste(stamp_canvas, (base_w - s_w - 50, base_h - s_h - 100), stamp_canvas)
        draw_m = ImageDraw.Draw(main_img)
        draw_m.text((base_w - s_w - 30, base_h - 95), date_txt, fill=stamp_color, font=f_date)
        
        out = io.BytesIO()
        main_img.convert("RGB").save(out, format="JPEG", quality=95)
        out.seek(0)
        return out, None
    except Exception as e:
        return None, str(e)

# --- БОТТУН ХЕНДЛЕРЛЕРИ ---
user_states = {}

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Салам! Пландын сүрөтүн жөнөтүңүз.")

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    user_states[m.from_user.id] = {'photo': m.photo[-1].file_id}
    await m.answer("✅ Сүрөт алынды. Эми аты-жөнүңүздү жазыңыз:")

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_name(m: types.Message):
    uid = m.from_user.id
    if uid in user_states:
        name, pid = m.text, str(uuid.uuid4())[:8]
        plans = load_plans()
        plans[pid] = {'file_id': user_states[uid]['photo'], 'user_id': uid, 'name': name}
        save_plans(plans)
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{pid}"))
        builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{pid}"))
        
        for admin in ADMIN_IDS:
            try:
                await bot.send_photo(admin, photo=user_states[uid]['photo'], 
                                     caption=f"📩 Жаңы план: {name}", reply_markup=builder.as_markup())
            except: pass
        await m.answer("Рахмат! План текшерүүгө жиберилди.")
        del user_states[uid]

@dp.callback_query(F.data.startswith("ok_"))
async def approve(c: types.CallbackQuery):
    pid = c.data.split("_")[1]
    plans = load_plans()
    
    if pid not in plans:
        return await c.answer("Бул план базадан өчүрүлгөн же эскирген.", show_alert=True)
    
    await c.answer("Штамп басылууда...")
    p = plans[pid]
    file = await bot.get_file(p['file_id'])
    content = await bot.download_file(file.file_path)
    img_out, err = add_stamp_and_date(content.read())
    
    if img_out:
        await bot.send_photo(p['user_id'], photo=BufferedInputFile(img_out.read(), filename="res.jpg"), 
                             caption="✅ Планыңыз кабыл алынды!")
        await c.message.edit_caption(caption=f"✅ {p['name']} - Кабыл алынды.")
    else:
        await c.answer(f"Ката: {err}", show_alert=True)
    
    # Текшерилгенден кийин тизмеден өчүрөбүз
    del plans[pid]
    save_plans(plans)

async def main():
    # Бот иштегенде эски конфликттерди тазалайт
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
