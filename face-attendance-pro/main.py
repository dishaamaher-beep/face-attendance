from fastapi import FastAPI, UploadFile, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
from datetime import datetime
import face_recognition
import sqlite3
import pandas as pd
from PIL import Image
import numpy as np
import io

app = FastAPI()

# ------------------- إعداد المسارات -------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

db_path = os.path.join(BASE_DIR, "attendance.db")
known_faces_folder = os.path.join(BASE_DIR, "known_faces")
photo_folder = os.path.join(BASE_DIR, "attendance_photos")

os.makedirs(known_faces_folder, exist_ok=True)
os.makedirs(photo_folder, exist_ok=True)

# عمل StaticFiles للصور
app.mount("/attendance_photos", StaticFiles(directory=photo_folder), name="photos")

# ------------------- تحميل الوجوه -------------------
known_face_encodings = []
known_face_names = []

for filename in os.listdir(known_faces_folder):
    if filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
        image_path = os.path.join(known_faces_folder, filename)
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        if encodings:
            known_face_encodings.append(encodings[0])
            known_face_names.append(os.path.splitext(filename)[0])

# ------------------- إعداد قاعدة البيانات -------------------
def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            date TEXT,
            time TEXT,
            status TEXT,
            photo TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------- الصفحة الرئيسية -------------------
@app.get("/", response_class=HTMLResponse)
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ------------------- رفع الصور وتسجيل الحضور -------------------
@app.post("/attendance")
async def attendance(file: UploadFile):
    try:
        contents = await file.read()

        # تحويل أي صورة لأي صيغة RGB
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        img_np = np.array(image)
        rgb_img = img_np

        face_encodings = face_recognition.face_encodings(rgb_img)
        if not face_encodings:
            return {"status": "error", "message": "لم يتم الكشف عن وجه"}

        face_encoding = face_encodings[0]
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "غير معروف"
        if True in matches:
            name = known_face_names[matches.index(True)]

        date = datetime.now().strftime("%Y-%m-%d")
        time = datetime.now().strftime("%H-%M-%S")
        status = "حاضر"

        # حفظ الصورة بصيغة JPEG
        photo_filename = f"{name}_{date}_{time}.jpg"
        photo_path = os.path.join(photo_folder, photo_filename)
        image.save(photo_path, format="JPEG")

        # حفظ البيانات في DB
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance WHERE name=? AND date=?", (name, date))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO attendance (name, date, time, status, photo) VALUES (?, ?, ?, ?, ?)",
                (name, date, time, status, photo_path)
            )
            conn.commit()
            conn.close()
            return {"status": "success", "name": name}
        else:
            conn.close()
            return {"status": "already", "name": name}

    except Exception as e:
        return {"status": "error", "message": str(e)}

# ------------------- Dashboard -------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, date, time, status, photo FROM attendance ORDER BY date DESC, time DESC")
    data = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse("dashboard.html", {"request": request, "data": data})

# ------------------- إحصائيات الرسم البياني -------------------
@app.get("/stats")
def stats():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT date, COUNT(*) FROM attendance GROUP BY date")
    data = cursor.fetchall()
    conn.close()
    return data

# ------------------- تصدير Excel -------------------
@app.get("/export")
def export_excel():
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM attendance", conn)
    conn.close()
    export_path = os.path.join(BASE_DIR, "attendance_export.xlsx")
    df.to_excel(export_path, index=False)
    return FileResponse(export_path, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename="attendance_export.xlsx")