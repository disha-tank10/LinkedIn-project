import pymysql


def get_db_connection():
    db = pymysql.Connect(
        host="127.0.0.1",
        user="root",
        password="tiger",
        database="linkedin"
    )

    return db