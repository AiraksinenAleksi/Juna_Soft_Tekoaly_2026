rail-app/
├── app.py
├── config.py
├── requirements.txt
├── pytest.ini
├── tests/
│   └── test_app.py
└── templates/
    ├── index.html
    ├── departures.html
    └── _rows.html        ← partial used by auto-refresh

---

pip install -r requirements.txt

---

Running it

Development:
export DIGITRAFFIC_USER="my-railway-app.example.com" # your app identifier
export FLASK_DEBUG=1 # only for development!
python app.py

Production (recommended instead of python app.py):
pip install gunicorn
DIGITRAFFIC_USER="my-railway-app.example.com" \
gunicorn -w 2 -b 127.0.0.1:8000 app:app