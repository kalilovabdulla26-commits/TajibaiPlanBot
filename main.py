import logging
import asyncio
import os
import io
import uuid
import json
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google.oauth2.service_account import Credentials
from PIL import Image, ImageDraw, ImageFont

# --- ЖӨНДӨӨЛӨР ---
# Render'дин Environment Variables бөлүмүнө кошкон токениңди алат
API_TOKEN = '8388259014:AAFlyJXykZUZRBWSmiBZsCFlgIhQsnCLCWo'
ADMIN_ID = 5148336517
# Сенин Google Таблицаңдын ID'си
SPREADSHEET_ID = '1g74mCtl8zqbcDCJ306q4eoPWJXwOnEdpOTMAj8_cPcU'

# Убактылуу маалымат сактоо үчүн
pending_plans = {}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- GOOGLE SHEETS ФУНКЦИЯСЫ ---
def log_to_sheet(teacher_name, status):
    try:
        # Render'ден GOOGLE_JSON өзгөрмөсүн текст түрүндө окуйбуз
        json_creds = os.environ.get('GOOGLE_JSON')
        if not json_creds:
            logging.error("GOOGLE_JSON өзгөрмөсү табылган жок!")
            return
            
        info = json.loads(json_creds)
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(info, scopes=scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        # Сап кошуу: Дата, Мугалим, Статус
        sheet.append_row([now, teacher_name, status])
        logging.info(f"Таблицага жазылды: {teacher_name} - {status}")
    except Exception as e:
        logging.error(f"Таблицага жазууда ката: {e}")

# --- ШТАМП БАСУУ ФУНКЦИЯСЫ ---
def add_stamp_and_date(image_bytes):
    try:
        main_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        base_w, base_h = main_img.size
        
        s_w = int(base_w * 0.3)
        s_h = int(s_w * 0.5)
        stamp_canvas = Image.new('RGBA', (s_w, s_h), (0, 0, 0, 0))
        draw_s = ImageDraw.Draw(stamp_canvas)
        
        stamp_color = (26, 26, 140, 255) # Deep Blue
        line_w = int(s_w * 0.02)
        draw_s.rectangle([0, 0, s_w, s_h], outline=stamp_color, width=line_w)
        
        try:
            # Render (Linux) үчүн стандарттык шрифт жолу
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path):
                font_path = "arial.ttf" # Эгер локалдык иштетсең
            f_main = ImageFont.truetype(font_path, int(s_h * 0.18))
            f_sub = ImageFont.truetype(font_path, int(s_h * 0.14))
            f_date = ImageFont.truetype(font_path, int(s_h * 0.12))
        except:
            f_main = f_sub = f_date = ImageFont.load_default()

        txt1, txt2, txt3 = "ЭЛЕКТРОНДУК ТҮРДӨ", "ТЕКШЕРИЛДИ", "ОББ: ТОКТОМАМАТОВА.А"
        date_txt = datetime.now().strftime("%d.%m.%Y | %H:%M")

        def draw_center(draw_obj, text, font, y_pos, width):
            w = draw_obj.textbbox((0, 0), text, font=font)[2]
            draw_obj.text(((width - w) / 2, y_pos), text, fill=stamp_color, font=font)

        draw_center(draw_s, txt1, f_sub, s_h * 0.15, s_w)
        draw_center(draw_s, txt2, f_main, s_h * 0.35, s_w)
        draw_center(draw_s, txt3, f_sub, s_h * 0.65, s_w)
        
        pos_x, pos_y = base_w - s_w - 50, base_h - s_h - 100
        main_img.paste(stamp_canvas, (pos_x, pos_y), stamp_canvas)
        
        draw_main = ImageDraw.Draw(main_img)
        d_bbox = draw_main.textbbox((0,0), date_txt, font=f_date)
        d_w = d_bbox[2] - d_bbox[0]
        draw_main.text((pos_x + (s_w - d_w) // 2, pos_y + s_h + 10), date_txt, fill=stamp_color, font=f_date)
        
        output = io.BytesIO()
        main_img.convert("RGB").save(output, format="JPEG", quality=95)
        output.seek(0)
        return output, None
    except Exception as e:
        return None, str(e)

# --- ХЕНДЛЕРЛЕР ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Салам! Пландын сүрөтүн жөнөтүңүз.")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    plan_id = str(uuid.uuid4())[:8] 
    pending_plans[plan_id] = {
        'file_id': message.photo[-1].file_id,
        'user_id': message.from_user.id,
        'user_name': message.from_user.full_name
    }
    
    await message.answer("✅ Планыңыз кабыл алынды. Текшерүүдөн кийин сизге жообун жөнөтөм.")
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Макул", callback_data=f"ok_{plan_id}"))
    builder.add(InlineKeyboardButton(text="❌ Жок", callback_data=f"no_{plan_id}"))
    
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=f"📩 Жаңы план!\nКимден: {message.from_user.full_name}",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("ok_"))
async def approve_callback(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[1]
    if plan_id not in pending_plans:
        await callback.answer("Ката: Маалымат табылган жок.")
        return

    plan_data = pending_plans[plan_id]
    await callback.message.edit_caption(caption="Иштетилүүдө... ⏳")
    
    # Таблицага жазуу
    log_to_sheet(plan_data['user_name'], "Кабыл алынды")
    
    file = await bot.get_file(plan_data['file_id'])
    content = await bot.download_file(file.file_path)
    processed_img, error = add_stamp_and_date(content.read())
    
    if not error:
        input_file = types.BufferedInputFile(processed_img.read(), filename="checked.jpg")
        await bot.send_photo(chat_id=plan_data['user_id'], photo=input_file, caption="✅ Сиздин планыңыз кабыл алынды!")
        await callback.message.edit_caption(caption=f"✅ План ({plan_data['user_name']}) кабыл алынды жана журналга жазылды.")
        del pending_plans[plan_id]
    else:
        await callback.answer(f"Ката: {error}")

@dp.callback_query(F.data.startswith("no_"))
async def reject_callback(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[1]
    if plan_id in pending_plans:
        plan_data = pending_plans[plan_id]
        # Таблицага жазуу (Четке кагылды)
        log_to_sheet(plan_data['user_name'], "Четке кагылды")
        
        await bot.send_message(chat_id=plan_data['user_id'], text="❌ Кечиресиз, сиздин планыңыз кабыл алынган жок.")
        await callback.message.edit_caption(caption=f"❌ Сиз ({plan_data['user_name']}) планын четке кактыңыз.")
        del pending_plans[plan_id]

async def main():
    logging.info("Бот ишке кирди...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
