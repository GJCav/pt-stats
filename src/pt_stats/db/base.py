from .database import conn
import peewee

MODELS = []

def register(cls):
    MODELS.append(cls)
    return cls

class DatabaseModel(peewee.Model):
    class Meta:
        database = conn

