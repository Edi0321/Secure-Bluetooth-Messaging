#router_db.py
import sqlite3
from typing import List, Dict, Any
from .config_loader import ROUTING_CFG

DB_PATH = "routingDB.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id TEXT UNIQUE,
            envelope_json TEXT,
            delivered INTEGER DEFAULT 0,
            retries INTEGER DEFAULT 0,
            ttl INTEGER,
            status TEXT DEFAULT 'queued',
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def enqueue_message(
    msg_id: str,
    envelope_json: str,
    ttl: int,
    sender_fp: str | None = None,
    recipient_fp: str | None = None,
):
    conn = get_connection()
    cur = conn.cursor()

    max_size = ROUTING_CFG.get("max_queue_size", 5000)

    cur.execute("SELECT COUNT(*) FROM queue WHERE delivered = 0")
    count = cur.fetchone()[0]
    if count >= max_size:
        raise Exception("Routing queue is full")

    cur.execute(
        """
        INSERT INTO queue (msg_id, envelope_json, ttl)
        VALUES (?, ?, ?)
        ON CONFLICT(msg_id) DO NOTHING
        """,
        (msg_id, envelope_json, ttl),
    )
    conn.commit()
    conn.close()



def get_outgoing() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT id, msg_id, envelope_json, retries, ttl, status, last_update
        FROM queue
        WHERE delivered = 0 AND status = 'queued'
        """
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        row_id, msg_id, env_json, retries, ttl, status, last_update = row
        result.append(
            {
                "row_id": row_id,
                "msg_id": msg_id,
                "envelope_json": env_json,
                "retries": retries,
                "ttl": ttl,
                "status": status,
                "last_update": last_update,
            }
        )
    return result

def mark_delivered(row_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE queue
        SET delivered = 1, status = 'delivered', last_update = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (row_id,),
    )
    conn.commit()
    conn.close()


def mark_dropped(row_id: int, reason: str = "ttl_expired"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE queue
        SET delivered = 1, status = ?, last_update = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (reason, row_id),
    )
    conn.commit()
    conn.close()


def increment_retry(row_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE queue
        SET retries = retries + 1, last_update = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (row_id,),
    )
    conn.commit()
    conn.close()
