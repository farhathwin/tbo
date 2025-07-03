import os
import pymysql

conn = pymysql.connect(
    host="127.0.0.1",
    user="root",
    password=os.environ.get("DB_PASSWORD")
)
print("Connected!")
conn.close()
