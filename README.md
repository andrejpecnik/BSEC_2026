# MedicApp — BSEC Brno 2026 Project

This project won 3rd place award at BSEC Brno 2026 in the **"Analyse" category**.

The application was developed as part of the BSEC (Brno Student Engineering Competition) organised by BEST (Board of European Students of Technology) Brno.

---

## Project Overview

**MedicApp** is a web-based healthcare dashboard designed to help users efficiently search and analyze healthcare facilities in the South Moravian Region (Czech Republic).

The application aggregates healthcare data stored in a SQLite database and provides:

* Advanced search and filtering of healthcare facilities
* Location-based search (nearest facilities)
* Detailed facility information
* Opening hours formatting and normalization
* Nearby pharmacies and public transport stops
* AI-assisted search using Google Gemini

---

## Technologies Used

### Backend

* Python
* Flask
* SQLite

### Frontend

* HTML
* CSS
* JavaScript
* Leaflet.js (map)

### AI Integration

* Google Gemini (via `google-genai`)

---

## Architecture

The application follows a simple client–server architecture:

```
Browser (Frontend)
        ↓
Flask API (app.py)
        ↓
SQLite Database (MedicApp.db)
        ↓
Optional AI Layer (Google Gemini)
```

Main components:

* `app.py` — Flask backend and REST API
* `templates/` — HTML templates
* `static/` — CSS and JavaScript assets
* `MedicApp.db` — SQLite healthcare database (required)

---

## Features

* Full-text healthcare facility search
* Distance-based search using geographic coordinates
* Facility detail view
* Opening hours
* Nearest public transport stops
* Nearest pharmacies
* AI chatbot that converts natural language into search filters
* API statistics endpoint

---

## Requirements

Python dependencies:

```
flask
pandas
google-genai
```

SQLite Database:

```
MedicApp.db
```

AI functionality requires Google Vertex AI credentials.

* The application still works without it.

---

## Running the Application

1. Clone the repository:

```bash
git clone https://github.com/andrejpecnik/BSEC_2026.git
cd BSEC_2026
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Ensure `MedicApp.db` exists in the root folder.

4. Start the server:

```bash
python app.py
```

5. Open in browser:

```
http://localhost:5000
```

---

## API Endpoints (Overview)

| Endpoint             | Description         |
| -------------------- | ------------------- |
| `/api/search`        | Search facilities   |
| `/api/search_nearby` | Search by distance  |
| `/api/detail`        | Facility detail     |
| `/api/suggestions`   | Search suggestions  |
| `/api/stats`         | Database statistics |
| `/api/ai_chat`       | AI-powered search   |

---

## Authors

Andrej Pecník, David Gregora, Šimon Binder, Jozef Lovíšek
