import pymysql
import config


def _conn():
    return pymysql.connect(**config.DB, cursorclass=pymysql.cursors.DictCursor, autocommit=True)


def query(sql, args=None, one=False):
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone() if one else cur.fetchall()
    finally:
        c.close()


def execute(sql, args=None):
    c = _conn()
    try:
        with c.cursor() as cur:
            cur.execute(sql, args)
            return cur.lastrowid
    finally:
        c.close()
