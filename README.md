# Proovexa — Academic Plagiarism & AI Writing Detection Platform

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2+-092E20?style=flat&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=flat&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success)](#deployment)

A professional, web-based academic plagiarism detection, text similarity analysis, and AI writing detection platform inspired by the workflow of modern academic integrity software like Turnitin.

---

## 🌟 Key Features

### 1. Multi-Format Document Ingestion
- Upload and analyze **PDF**, **DOCX**, **PPTX**, and **TXT** files.
- Automated text extraction preserving page boundaries, paragraph structures, word counts, and metadata.
- Pre-upload validation for file extensions, MIME signatures, file sizes (up to 25MB), and word count caps.

### 2. Multi-Tier Similarity Detection Engine
- **Exact Phrase Matching**: Identifies verbatim sentence and paragraph duplication.
- **N-Gram Sliding Window**: Detects subtle phrase rearrangements and minor word swaps.
- **Fuzzy / Levenshtein Distance**: Flags paraphrased variations, typos, and slight wording alterations.
- **TF-IDF & Cosine Vector Analysis**: Measures contextual and thematic semantic overlap.
- **Configurable Exclusions**: Toggle exclusion of direct quotations, bibliography/references, small matches (< 5 words or < 1%), and cited excerpts.

### 3. AI Writing Detection
- Sentence-level perplexity, burstiness, and lexical entropy analysis.
- Turnitin-style percentage badges and categorized probability metrics.
- Standalone downloadable AI Writing PDF reports with authentic page-by-page breakdown.

### 4. Interactive Report Viewer (Turnitin Replica)
- **Authentic Page 2 "Integrity Overview"**: Includes sheet view, running headers/footers, and interactive view toggling.
- Side-by-side split comparison highlighting matching source text with color-coded indices.
- Source breakdown panel grouping matches by Internet, Publications, and Crossref student repositories.
- Export options: Downloadable PDF reports, editable DOCX summaries, and structured JSON data.

### 5. Role-Based Access Control & Auditing
- **Three user roles**: Administrator, Instructor/Teacher, and Student.
- Strict data privacy isolation: students can only view their own submissions.
- Comprehensive security audit log tracking every document upload, scan, report view, and deletion.

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/vermaaniket577/Proovexa.git
cd Proovexa
```

### 2. Set Up Virtual Environment
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment & Run Migrations
```bash
cp .env.example .env
python manage.py migrate
python manage.py collectstatic --noinput
```

### 5. Start Development Server
```bash
python manage.py runserver
```
Visit `http://127.0.0.1:8000/` in your browser.

---

## 🐳 Docker Deployment

Run the full stack with **MySQL 8.0** and **Gunicorn** in one command:

```bash
docker compose up -d --build
```
Create an administrator account:
```bash
docker compose exec web python manage.py createsuperuser
```
Check system health:
```bash
curl http://localhost:8000/health/
```

---

## 📁 Project Architecture

```
Proovexa/
├── accounts/            # Custom User model, auth views, audit logging, rate-limiting
├── analysis/            # Plagiarism comparison algorithms, AI writing detector, scoring
├── dashboard/           # Role-based dashboard interfaces (Admin, Teacher, Student)
├── documents/           # Upload handling, secure storage, document parsers & extractors
├── jobs/                # Asynchronous queue jobs & background task management
├── reports/             # PDF report generator, DOCX generator, criteria formatting
├── sources/             # Comparison repository models & external source providers
├── static/              # Vanilla CSS design system, fonts, and JavaScript assets
├── templates/           # Bootstrap 5 responsive templates & error pages (404, 500, etc.)
├── Dockerfile           # Production container build
├── docker-compose.yml   # Docker Compose stack with MySQL 8.0
├── DEPLOYMENT.md        # Comprehensive production deployment guide
├── gunicorn.conf.py     # Linux WSGI server settings
├── run_production.py    # Windows Waitress WSGI runner
└── requirements.txt     # Pinned Python package dependencies
```

---

## 🔒 Security & Data Privacy

- **Private Uploads**: Student submissions are stored outside the public document root and require session-level permission checks.
- **CSRF & Rate-Limiting**: Protection against brute-force attacks and cross-site scripting.
- **Audit Logs**: Every administrative and student action is cryptographically tied to IP addresses and timestamps.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.