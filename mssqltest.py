import pymysql

conn = pymysql.connect(
    host="mleasd.mysql.pythonanywhere-services.com",
    user="mleasd",
    password="@T@_$Ciy2kTSg_t"
)
print("Connected!")
conn.close()
