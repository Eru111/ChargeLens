import os

from flask_sqlalchemy import SQLAlchemy


DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")
DB_NAME = os.environ.get("DB_NAME")
INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")

db = SQLAlchemy()