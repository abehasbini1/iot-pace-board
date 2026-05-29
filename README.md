# IoT Pace Board

A real-time, hardware-integrated production pace board designed for modern manufacturing environments. This application replaces traditional manual whiteboards with an automated, live digital dashboard that tracks shift throughput pacing (Actual vs. Target) and item classifications.
Target being Takt Time.

### 🚀 Key Features
* **Physical Hardware Integration:** Implements a low-level background listener and serial worker to instantly intercept inputs from physical USB/HID/Serial barcode scanners (Zebra, Symbol, etc.).
* **Real-Time Data Streaming:** Powered by an asynchronous FastAPI backend and WebSockets for instantaneous UI updates across all shop floor displays without page reloads.
* **Intelligent Hour-Block Pacing:** Automatically categorizes scans into custom, pre-configured shift timing blocks while handling break times, ramp-up and ramp-down activities and dynamic, scalable efficiency metrics.
* **Robust Relational Data Syncing:** Connected to a MySQL database backend using secure environment configurations for historical logging and automatic state recovery on application launch.
* **Fail-Safe Processing:** Includes smart `-UNDO` barcode capabilities to retroactively adjust counts on the fly and graceful hardware reconnection handlers for uninterrupted line operation.

### 🛠️ Tech Stack
* **Backend:** Python, FastAPI, Uvicorn, Asyncio
* **Database:** MySQL, PyMySQL
* **Hardware Interfacing:** PySerial, Web Keyboard Listeners
* **Frontend:** Vanilla JavaScript (ES6+ WebSockets, Template Literals), HTML5, CSS3
