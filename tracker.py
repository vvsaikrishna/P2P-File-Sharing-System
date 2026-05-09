"""
P2P File Sharing - Tracker Server
----------------------------------
Acts as a phonebook. Knows who is online and what files they have.
Does NOT store any files itself.
"""

import socket
import threading
import json
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[TRACKER] %(asctime)s - %(message)s",
    datefmt="%H:%M:%S"
)

# ---------- Global State ----------
peers = {}          # { peer_id: { ip, port, files, last_seen } }
peers_lock = threading.Lock()

TRACKER_HOST = "0.0.0.0"
TRACKER_PORT = 9000
TIMEOUT      = 60   # seconds before a peer is considered dead


# ---------- Helpers ----------
def cleanup_dead_peers():
    """Remove peers that haven't pinged in TIMEOUT seconds."""
    while True:
        time.sleep(15)
        now = time.time()
        with peers_lock:
            dead = [pid for pid, info in peers.items()
                    if now - info["last_seen"] > TIMEOUT]
            for pid in dead:
                logging.info(f"Removing dead peer: {pid}")
                del peers[pid]


def send_json(conn, data):
    msg = json.dumps(data).encode()
    conn.sendall(len(msg).to_bytes(4, "big") + msg)


def recv_json(conn):
    raw_len = conn.recv(4)
    if not raw_len:
        return None
    length = int.from_bytes(raw_len, "big")
    data = b""
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    return json.loads(data.decode())


# ---------- Request Handlers ----------
def handle_register(peer_id, data):
    with peers_lock:
        peers[peer_id] = {
            "ip":        data["ip"],
            "port":      data["port"],
            "files":     data.get("files", []),
            "last_seen": time.time()
        }
    logging.info(f"REGISTER  {peer_id} @ {data['ip']}:{data['port']} | files: {data.get('files', [])}")
    return {"status": "ok", "message": "Registered successfully"}


def handle_update(peer_id, data):
    with peers_lock:
        if peer_id not in peers:
            return {"status": "error", "message": "Peer not registered"}
        peers[peer_id]["files"]     = data.get("files", [])
        peers[peer_id]["last_seen"] = time.time()
    logging.info(f"UPDATE    {peer_id} | files: {data.get('files', [])}")
    return {"status": "ok"}


def handle_ping(peer_id):
    with peers_lock:
        if peer_id in peers:
            peers[peer_id]["last_seen"] = time.time()
    return {"status": "ok"}


def handle_list(peer_id):
    with peers_lock:
        result = {
            pid: {
                "ip":    info["ip"],
                "port":  info["port"],
                "files": info["files"]
            }
            for pid, info in peers.items()
            if pid != peer_id          # don't include the requester itself
        }
    logging.info(f"LIST      {peer_id} → {len(result)} peers")
    return {"status": "ok", "peers": result}


def handle_search(peer_id, data):
    filename = data.get("filename", "").lower()
    results  = {}
    with peers_lock:
        for pid, info in peers.items():
            if pid == peer_id:
                continue
            for f in info["files"]:
                if filename in f.lower():
                    results[pid] = {
                        "ip":       info["ip"],
                        "port":     info["port"],
                        "filename": f
                    }
    logging.info(f"SEARCH    {peer_id} → '{filename}' → {len(results)} results")
    return {"status": "ok", "results": results}


def handle_leave(peer_id):
    with peers_lock:
        peers.pop(peer_id, None)
    logging.info(f"LEAVE     {peer_id}")
    return {"status": "ok", "message": "Goodbye"}


# ---------- Connection Handler ----------
def handle_connection(conn, addr):
    try:
        data = recv_json(conn)
        if not data:
            return

        action    = data.get("action")
        peer_id   = data.get("peer_id", str(addr))

        handlers = {
            "register": lambda: handle_register(peer_id, data),
            "update":   lambda: handle_update(peer_id, data),
            "ping":     lambda: handle_ping(peer_id),
            "list":     lambda: handle_list(peer_id),
            "search":   lambda: handle_search(peer_id, data),
            "leave":    lambda: handle_leave(peer_id),
        }

        if action in handlers:
            response = handlers[action]()
        else:
            response = {"status": "error", "message": f"Unknown action: {action}"}

        send_json(conn, response)

    except Exception as e:
        logging.error(f"Error handling {addr}: {e}")
    finally:
        conn.close()


# ---------- Main ----------
def main():
    # Start cleanup thread
    threading.Thread(target=cleanup_dead_peers, daemon=True).start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((TRACKER_HOST, TRACKER_PORT))
    server.listen(50)

    logging.info(f"Tracker running on port {TRACKER_PORT}")
    logging.info("Waiting for peers to connect...")

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_connection, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
