import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from pathlib import Path

import pymysql
import serial
from dotenv import load_dotenv
from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from serial.tools import list_ports

print("--- ENVIRONMENT DEBUG ---")
print("Current Working Directory Python is running from:", os.getcwd())

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"
STATIC_PATH = SCRIPT_DIR / "static"
print("Checking for .env file at:", ENV_PATH)
print("Does .env file exist here?:", ENV_PATH.exists())


load_dotenv(dotenv_path=ENV_PATH)

try:
    config = {
        "host": os.environ["DB_HOST"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
    }
except KeyError as e:
    raise RuntimeError(
        f"CRITICAL CONFIG ERROR: Missing required environment variable: {e}"
    )


connection = pymysql.connect(
    host=config["host"],
    user=config["user"],
    password=config["password"],
    database=config["database"],
    autocommit=True,
    cursorclass=pymysql.cursors.DictCursor,
)

print("✅ DB Environment Loaded Successfully!")
print("DB_USER found in .env:", os.getenv("DB_USER"))
print("DB_HOST found in .env:", os.getenv("DB_HOST"))
print("------------------------")


def get_db_connection():
    """Returns a fresh connection using the strictly validated config dictionary."""
    return pymysql.connect(
        host=config["host"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


# 2. SHIFT CONFIGURATIONS & STATE
SHIFT_HOURS = [
    {
        "display": "06:00 - 07:00",
        "start": time(6, 0),
        "end": time(7, 0),
        "is_break": False,
        "production_minutes": 50,
        "custom_target": 26,
    },
    {
        "display": "07:00 - 08:00",
        "start": time(7, 0),
        "end": time(8, 0),
        "is_break": False,
        "production_minutes": 60,
        "custom_target": 31,
    },
    {
        "display": "08:00 - 09:00",
        "start": time(8, 0),
        "end": time(9, 0),
        "is_break": False,
        "production_minutes": 60,
        "custom_target": 31,
    },
    {
        "display": "09:00 - 10:00",
        "start": time(9, 0),
        "end": time(10, 0),
        "is_break": False,
        "production_minutes": 45,
        "custom_target": 24,
    },
    {
        "display": "10:00 - 11:00",
        "start": time(10, 0),
        "end": time(11, 0),
        "is_break": False,
        "production_minutes": 60,
        "custom_target": 31,
    },
    {
        "display": "11:00 - 12:00",
        "start": time(11, 0),
        "end": time(12, 0),
        "is_break": False,
        "production_minutes": 60,
        "custom_target": 31,
    },
    {
        "display": "12:00 - 12:30",
        "start": time(12, 0),
        "end": time(12, 30),
        "is_break": True,
        "production_minutes": 0,
        "custom_target": 0,
    },
    {
        "display": "12:45 - 13:30",
        "start": time(12, 45),
        "end": time(13, 30),
        "is_break": False,
        "production_minutes": 45,
        "custom_target": 24,
    },
    {
        "display": "13:30 - 14:30",
        "start": time(13, 30),
        "end": time(14, 30),
        "is_break": False,
        "production_minutes": 50,
        "custom_target": 31,
    },
]

actual_counts = [0] * len(SHIFT_HOURS)
daily_target = 225
active_connections: list[WebSocket] = []
scan_type_counts = {"SH": 0, "TWIN": 0, "TRIPLE": 0}


# 3. DATABASE OPERATIONS
def load_todays_data_from_db():
    global actual_counts, scan_type_counts
    today = date.today().isoformat()
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT shift_block, SUM(unit_weight) as total_credits 
                FROM production_scans 
                WHERE scan_date = %s 
                GROUP BY shift_block
            """
            cursor.execute(query, (today,))
            rows = cursor.fetchall()

            actual_counts = [0] * len(SHIFT_HOURS)
            for row in rows:
                for i, block in enumerate(SHIFT_HOURS):
                    if block["display"] == row["shift_block"]:
                        actual_counts[i] = int(row["total_credits"] or 0)

            # Rebuild layout classification sidebar metrics
            type_query = """
                SELECT barcode FROM production_scans 
                WHERE scan_date = %s
            """
            cursor.execute(type_query, (today,))
            scans = cursor.fetchall()

            scan_type_counts = {"SH": 0, "TWIN": 0, "TRIPLE": 0}
            for scan in scans:
                b_upper = scan["barcode"].upper()
                if "-UNDO" in b_upper:
                    clean_b = b_upper.replace("-UNDO", "").strip()
                    modifier = -1
                else:
                    clean_b = b_upper
                    modifier = 1

                if "SH" in clean_b:
                    scan_type_counts["SH"] += modifier
                elif "TWIN" in clean_b:
                    scan_type_counts["TWIN"] += modifier
                elif "TRIPLE" in clean_b:
                    scan_type_counts["TRIPLE"] += modifier

        conn.close()
        print("Successfully synced state with MySQL historical data.")
    except Exception as e:
        print(f"Error initializing data from DB: {e}")


def save_scan_to_db(barcode: str, shift_block: str, unit_weight: int):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = """
                INSERT INTO production_scans (barcode, scan_date, scan_time, shift_block, unit_weight)
                VALUES (%s, %s, %s, %s, %s)
            """
            now = datetime.now()
            cursor.execute(
                query,
                (
                    barcode,
                    now.date().isoformat(),
                    now.time().isoformat(),
                    shift_block,
                    unit_weight,
                ),
            )
        conn.close()
    except Exception as e:
        print(f"Database write failed: {e}")


def increment_current_hour_sync(barcode: str):
    global actual_counts, scan_type_counts
    current_time = datetime.now().time()
    raw_barcode = barcode.strip()

    is_undo = False
    if raw_barcode.upper().endswith("-UNDO"):
        is_undo = True
        barcode_key = raw_barcode[:-5].strip()
    else:
        barcode_key = raw_barcode

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = "SELECT unit_weight FROM product_barcodes WHERE barcode = %s"
            cursor.execute(query, (barcode_key,))
            result = cursor.fetchone()
        conn.close()

        if result:
            weight = int(result["unit_weight"])
            if is_undo:
                weight = -weight
        else:
            print(f"⚠️ VLOOKUP FAILED: Barcode '{barcode_key}' not found. Ignored.")
            return False

    except Exception as e:
        print(f"Database VLOOKUP failed during scan process: {e}")
        return False

    for i, block in enumerate(SHIFT_HOURS):
        if block["start"] <= current_time < block["end"]:
            if block["is_break"]:
                print("Scan ignored: Currently scheduled break time.")
                return False

            actual_counts[i] += weight
            save_scan_to_db(raw_barcode, block["display"], weight)

            barcode_upper = barcode_key.upper()
            modifier = -1 if is_undo else 1

            if "SH" in barcode_upper:
                scan_type_counts["SH"] += modifier
            elif "TWIN" in barcode_upper:
                scan_type_counts["TWIN"] += modifier
            elif "TRIPLE" in barcode_upper:
                scan_type_counts["TRIPLE"] += modifier

            print(f"Logged progress ({weight:+} units) to {block['display']}.")
            return True

    print("⚠️ Scan Ignored: No active shift time block matched current system time.")
    return False


def get_andon_grid():
    grid = []
    BOSS_BASELINE_TARGET = 225
    scale_factor = daily_target / BOSS_BASELINE_TARGET if daily_target > 0 else 0
    running_target_sum = 0
    total_shifts = len(SHIFT_HOURS)

    for i, block in enumerate(SHIFT_HOURS):
        actual = actual_counts[i]

        if i == total_shifts - 1:
            hourly_target = (
                0 if block["is_break"] else (daily_target - running_target_sum)
            )
        else:
            hourly_target = (
                0 if block["is_break"] else round(block["custom_target"] * scale_factor)
            )

        if not block["is_break"]:
            running_target_sum += hourly_target

        if i == total_shifts - 1:
            running_target_sum = daily_target

        efficiency = round((actual / hourly_target) * 100) if hourly_target > 0 else 0

        grid.append(
            {
                "hour": block["display"],
                "actual": actual,
                "target": hourly_target,
                "running_target": running_target_sum,
                "efficiency": efficiency,
                "is_break": block["is_break"],
            }
        )
    return {"shift_grid": grid, "type_counts": scan_type_counts}


async def broadcast_update():
    message = json.dumps(get_andon_grid())
    for connection in list(active_connections):
        try:
            await connection.send_text(message)
        except Exception:
            if connection in active_connections:
                active_connections.remove(connection)


def find_scanner_port():
    ports = list(list_ports.comports())
    for p in ports:
        desc = p.description.lower()
        if "symbol" in desc or "usb" in desc or "serial" in desc or "zebra" in desc:
            return p.device
    return None


async def serial_scanner_worker():
    ser = None
    buffer = b""

    while True:
        if ser is None or not ser.is_open:
            target_port = find_scanner_port()
            if target_port:
                try:
                    ser = serial.Serial(port=target_port, baudrate=9600, timeout=0.05)
                    print(f"✅ Hardware Connected to Scanner on port: {target_port}")
                except Exception as e:
                    print(
                        f"⚠️ Scanner detected on {target_port} but connection failed: {e}"
                    )
                    ser = None
            else:
                print("⏳ Scanning for USB Serial devices on Dell Hub...")
                ser = None
                await asyncio.sleep(4.0)
                continue

        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    raw_bytes = ser.read(ser.in_waiting)
                    buffer += raw_bytes

                    if b"\r" in buffer or b"\n" in buffer:
                        normalized = buffer.replace(b"\r", b"\n")
                        lines = normalized.split(b"\n")
                        buffer = lines.pop()

                        for line in lines:
                            barcode_data = line.decode("utf-8", errors="ignore").strip()
                            if barcode_data:
                                print(f"Barcode Scanned via Serial: {barcode_data}")

                                success = await asyncio.to_thread(
                                    increment_current_hour_sync, barcode_data
                                )
                                if success:
                                    await broadcast_update()
            except Exception as e:
                print(f"❌ Connection lost or broken during runtime tracking read: {e}")
                ser = None
                buffer = b""

        await asyncio.sleep(0.05)


# 4. LIFESPAN MANAGEMENT
@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(load_todays_data_from_db)
    scanner_task = asyncio.create_task(serial_scanner_worker())
    yield
    scanner_task.cancel()
    try:
        await scanner_task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)


if STATIC_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_PATH)), name="static")
else:
    print(
        f"⚠️ Warning: Static subdirectory directory not found at {STATIC_PATH}. Create it to offload CSS file extraction."
    )


@app.post("/test-scan")
async def test_scan(barcode: str = Form(...)):
    raw_barcode = barcode.strip()
    if not raw_barcode:
        return {"status": "error", "message": "Barcode cannot be empty"}

    success = await asyncio.to_thread(increment_current_hour_sync, raw_barcode)

    if success:
        await broadcast_update()
        return {"status": "success", "message": f"Mock scanned: {raw_barcode}"}
    else:
        return {
            "status": "ignored",
            "message": "Scan dropped (Break time, invalid barcode, or off-shift)",
        }


@app.post("/update-target")
async def update_target(target: int = Form(...)):
    global daily_target
    daily_target = target
    await broadcast_update()
    return {"status": "success", "new_target": daily_target}


@app.websocket("/ws/andon")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    await websocket.send_text(json.dumps(get_andon_grid()))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)


@app.get("/")
async def get_dashboard():
    initial_data_json = json.dumps(get_andon_grid())
    html_file_path = SCRIPT_DIR / "index.html"

    try:
        with open(html_file_path, "r", encoding="utf-8") as file:
            html_template = file.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1 style='color:red;'>CRITICAL ERROR: index.html not found!</h1>",
            status_code=500,
        )

    html_content = html_template.replace("__DAILY_TARGET__", str(daily_target))
    html_content = html_content.replace("__INITIAL_DATA_JSON__", initial_data_json)

    return HTMLResponse(content=html_content)
