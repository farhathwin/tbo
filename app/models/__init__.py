from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()  # For tenant-specific DBs

from .models import *  # So other models can still be imported cleanly
