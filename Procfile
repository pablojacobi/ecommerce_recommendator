# Railway/Heroku Procfile
# release: runs once after deploy, before web starts
# web: the main application server

release: python scripts/setup_db.py
web: gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2
