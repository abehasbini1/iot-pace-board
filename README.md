# IoT Production Pace Board

A real-time, hardware-integrated production pace board designed for lean manufacturing and shop-floor environments. This application replaces traditional manual whiteboards with an automated, live digital dashboard that tracks shift throughput pacing (**Actual vs. Target / Takt Time**) and item classifications.

##  System Architecture & Data Flow

The system operates on an asynchronous event loop. When a physical barcode scanner registers a scan, a low-level background listener intercepts the hardware signal, processes the payload via FastAPI, updates the relational state in MySQL, and broadcasts the live metrics to all connected shop floor displays over WebSockets in **< 50ms**.

##  Features

* ** Physical Hardware Integration:** Implements a low-level background listener and serial worker to instantly intercept inputs from physical USB/HID/Serial barcode scanners (e.g., Zebra, Symbol hardware).
* ** Real-Time Data Streaming:** Powered by an asynchronous FastAPI backend and WebSockets for instantaneous UI updates across all shop floor displays without page reloads.
* ** Lean Metrics & Takt Time Pacing:** Automatically categorizes scans into custom, pre-configured shift timing blocks. Dynamically calculates efficiency metrics while factoring in:
    * Scheduled break times / lunch hours.
    * Shift ramp-up and ramp-down activity allowances.
    * Real-time Takt Time deltas.
* ** Fail-Safe Shop Floor Operations:** * **`--UNDO` Barcode Capability:** Operators can scan a specific physical undo code to retroactively adjust counts on the fly without database access.
    * **Hot-Plug Reconnection:** Graceful hardware reconnection handlers ensure uninterrupted line operation if a scanner is unplugged.
* ** Automatic State Recovery:** Connected to a MySQL database backend for robust historical logging and automatic dashboard state recovery in the event of power loss or application launch.

##  Tech Stack

* **Core Backend:** Python, FastAPI, Uvicorn, Asyncio (Asynchronous event handling)
* **Hardware Interfacing:** PySerial, Web Keyboard Listeners (HID/Serial communication)
* **Database & Persistence:** MySQL (Relational data synchronization & historical logging)
* **Frontend Dashboard:** JavaScript (Vanilla ES6), WebSockets API, HTML5, CSS3

---

##  Configuration & Hardware Setup

### 1. Environment Configuration
Create a `.env` file in the root directory to configure your database and hardware port settings:
```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_secure_password
SCANNER_PORT=COM3 # Or /dev/ttyUSB0 on Linux
TAKT_TIME_TARGET=45 # Target seconds per unit
