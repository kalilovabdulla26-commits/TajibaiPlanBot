import logging
import asyncio
import os
import io
import uuid
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image, ImageDraw, ImageFont

# --- ЖӨНДӨӨЛӨР ---
API_TOKEN = '8388259014:AAFlyJXykZUZRBWSmiBZsCFlgIhQsnCLCWo'
ADMIN_ID = 5148336517 
STAMP_PATH = 'stamp.png'

# Убактылуу маалымат сактоо үчүн (баскычтар иштеши үчүн)
pending_plans = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def add_stamp_and_date(image_bytes):
    try:
        main_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        base_w, base_h = main_img.size
        
        # 1. ШТАМПТЫ ПРOГРАММАЛЫК ТҮРДӨ ЖАСОО (Stamp Creation)
        # Штамптын өлчөмүн негизги сүрөттүн 25% кылып алабыз
        s_w = int(base_w * 0.3)
        s_h = int(s_w * 0.5)
        stamp_canvas = Image.new('RGBA', (s_w, s_h), (0, 0, 0, 0))
        draw_s = ImageDraw.Draw(stamp_canvas)
        
        # Түсү (Кочкул көк - Deep Blue)
        stamp_color = (26, 26, 140, 255)
        
        # Рамка чийүү
        line_w = int(s_w * 0.02)
        draw_s.rectangle([0, 0, s_w, s_h], outline=stamp_color, width=line_w)
        
        # Шрифтерди жүктөө
        try:
            # Mac үчүн шрифт жолу
            font_path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            f_main = ImageFont.truetype(font_path, int(s_h * 0.18))
            f_sub = ImageFont.truetype(font_path, int(s_h * 0.14))
            f_date = ImageFont.truetype(font_path, int(s_h * 0.12))
        except:
            f_main = f_sub = f_date = ImageFont.load_default()

        # Тексттер
        txt1 = "ЭЛЕКТРОНДУК ТҮРДӨ"
        txt2 = "ТЕКШЕРИЛДИ"
        txt3 = "ОББ: ТОКТОМАМАТОВА.А"
        date_txt = datetime.now().strftime("%d.%m.%Y | %H:%M")

        # Тексттерди штамптын ичине борборлоштуруп жазуу
        def draw_center(draw_obj, text, font, y_pos, width):
            w = draw_obj.textbbox((0, 0), text, font=font)[2]
            draw_obj.text(((width - w) / 2, y_pos), text, fill=stamp_color, font=font)

        draw_center(draw_s, txt1, f_sub, s_h * 0.15, s_w)
        draw_center(draw_s, txt2, f_main, s_h * 0.35, s_w)
        draw_center(draw_s, txt3, f_sub, s_h * 0.65, s_w)
        
        # 2. ПОЗИЦИЯНЫ ТАНДОО
        pos_x = base_w - s_w - 50
        pos_y = base_h - s_h - 100
        
        # Штампты негизги сүрөткө чаптоо
        main_img.paste(stamp_canvas, (pos_x, pos_y), stamp_canvas)
        
        # 3. ДАТАНЫ ШТАМПТЫН АСТЫНА ЖАЗУУ
        draw_main = ImageDraw.Draw(main_img)
        # Тексттин астына фон (окумдуу болуш үчүн)
        d_bbox = draw_main.textbbox((0,0), date_txt, font=f_date)
        d_w = d_bbox[2] - d_bbox[0]
        d_x = pos_x + (s_w - d_w) // 2
        d_y = pos_y + s_h + 10
        
        # Датаны жазуу
        draw_main.text((d_x, d_y), date_txt, fill=stamp_color, font=f_date)
        
        output = io.BytesIO()
        main_img.convert("RGB").save(output, format="JPEG", quality=95)
        output.seek(0)
        return output, None
    except Exception as e:
        return None, str(e)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Салам! Пландын сүрөтүн жөнөтүңүз.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    # Уникалдуу кыска ID түзөбүз (64 байттан ашпашы үчүн)
    plan_id = str(uuid.uuid4())[:8] 
    
    # Маалыматты сактайбыз
    pending_plans[plan_id] = {
        'file_id': message.photo[-1].file_id,
        'user_id': message.from_user.id,
        'user_name': message.from_user.full_name
    }
    
    await message.answer("✅ Планыңыз кабыл алынды. Текшерүүдөн кийин сизге жообун жөнөтөм.")
    
    builder = InlineKeyboardBuilder()
    # Эми callback_data кыска: "ok_id" же "no_id"
    builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{plan_id}"))
    builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{plan_id}"))
    
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=f"📩 Жаңы план!\nКимден: {message.from_user.full_name}\nТекшересизби?",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("ok_"))
async def approve_callback(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[1]
    
    if plan_id not in pending_plans:
        await callback.answer("Бул план эскирип калган же табылган жок.", show_alert=True)
        return

    plan_data = pending_plans[plan_id]
    await callback.message.edit_caption(caption="Иштетилүүдө... ⏳")
    
    file = await bot.get_file(plan_data['file_id'])
    content = await bot.download_file(file.file_path)
    processed_img, error = add_stamp_and_date(content.read())
    
    if not error:
        input_file = types.BufferedInputFile(processed_img.read(), filename="checked.jpg")
        await bot.send_photo(chat_id=plan_data['user_id'], photo=input_file, caption="✅ Сиздин планыңыз кабыл алынды!")
        await callback.message.edit_caption(caption=f"✅ План ({plan_data['user_name']}) кабыл алынды.")
        del pending_plans[plan_id] # Эс тутумду тазалоо
    else:
        await callback.answer(f"Ката: {error}")

@dp.callback_query(F.data.startswith("no_"))
async def reject_callback(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[1]
    if plan_id in pending_plans:
        user_id = pending_plans[plan_id]['user_id']
        await bot.send_message(chat_id=user_id, text="❌ Кечиресиз, сиздин планыңыз кабыл алынган жок.")
        await callback.message.edit_caption(caption="❌ Сиз бул планды четке кактыңыз.")
        del pending_plans[plan_id]

async def main():
    print("Бот иштеп жатат...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())