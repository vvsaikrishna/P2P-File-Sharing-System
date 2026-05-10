"""
P2P File Sharing - Peer Node
------------------------------
Each peer can:
  1. Register with tracker (share what files it has)
  2. List all online peers and their files
  3. Search for a specific file
  4. Download a file directly from another peer
  5. Share new files

Security:
  - Password authentication (wrong password = can't decrypt anything)
  - AES-256 encryption on all file transfers (via Fernet)
"""

import socket
import threading
import json
import os
import hashlib
import time
import logging
import sys
import getpass
import base64
from cryptography.fernet import Fernet

logging.basicConfig(
    level=logging.INFO,
    format="[PEER] %(asctime)s - %(message)s",
    datefmt="%H:%M:%S"
)

# ---------- Config ----------
TRACKER_HOST  = "127.0.0.1"   # Change to tracker's IP for different machines
TRACKER_PORT  = 9000
PEER_PORT     = 0              # 0 = OS picks a free port automatically
SHARED_FOLDER = "./shared/"
DOWNLOAD_FOLDER = "./downloads/"
CHUNK_SIZE    = 4096           # 4KB chunks
PING_INTERVAL = 20             # seconds between pings to tracker
FERNET_KEY       = None   # shared encryption key derived from password

# ---------- Helpers ----------
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


def sha256_file(filepath):
    """Compute SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def get_local_ip():
    """Get this machine's local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def list_shared_files():
    """Return list of filenames in shared folder."""
    if not os.path.exists(SHARED_FOLDER):
        os.makedirs(SHARED_FOLDER)
    return os.listdir(SHARED_FOLDER)

# ---------- NEW: Encryption Helpers ----------
def make_fernet_key(password):
    """
    Convert password into a valid AES-256 Fernet key.
    SHA256 of password = 32 bytes = perfect for AES-256.
    Same password = same key on every peer.
    Wrong password = different key = decryption fails.
    """
    key_bytes = hashlib.sha256(password.encode()).digest()  # 32 raw bytes
    key_b64   = base64.urlsafe_b64encode(key_bytes)         # Fernet needs base64
    return Fernet(key_b64)
 
 
def encrypt_bytes(data):
    """Encrypt raw bytes using the network AES key."""
    return FERNET_KEY.encrypt(data)
 
 
def decrypt_bytes(data):
    """Decrypt bytes using the network AES key."""
    return FERNET_KEY.decrypt(data)


# ---------- Tracker Communication ----------
def tracker_request(data):
    """Send a request to tracker and get response."""
    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(10)
        conn.connect((TRACKER_HOST, TRACKER_PORT))
        send_json(conn, data)
        response = recv_json(conn)
        conn.close()
        return response
    except ConnectionRefusedError:
        print("\n❌ Cannot connect to tracker. Is tracker.py running?")
        return None
    except Exception as e:
        print(f"\n❌ Tracker error: {e}")
        return None


# ---------- File Server (this peer acts as server for others) ----------
def handle_incoming_request(conn, addr):
    """
    Handle a file request from another peer.
    SENDER SIDE — encrypts file before sending.
    """
    try:
        data = recv_json(conn)
        if not data:
            return

        action = data.get("action")

        if action == "download":
            filename = data.get("filename")
            filepath = os.path.join(SHARED_FOLDER, filename)

            if not os.path.exists(filepath):
                send_json(conn, {"status": "error", "message": "File not found"})
                return

            filesize = os.path.getsize(filepath)
            checksum = sha256_file(filepath)

            # Get how many bytes receiver already has
            offset = data.get("offset", 0)  # receiver sends this in request

            # Send file metadata
            send_json(conn, {
                "status":   "ok",
                "filename": filename,
                "filesize": filesize,
                "checksum": checksum,
                "offset":   offset    # confirm offset to receiver
            })

            # NEW: Read chunks of file, encrypt it, then send
            with open(filepath, "rb") as f:
                f.seek(offset)         # jump to where receiver stopped
                while chunk := f.read(CHUNK_SIZE):
                    encrypted = encrypt_bytes(chunk)              # AES encrypt
                    conn.sendall(len(encrypted).to_bytes(8, "big"))  # send encrypted size (8 bytes)
                    conn.sendall(encrypted)                          # send encrypted data
 
            logging.info(f"Sent '{filename}' ({filesize} bytes) to {addr[0]}")

        elif action == "list_files":
            files = list_shared_files()
            send_json(conn, {"status": "ok", "files": files})

    except Exception as e:
        logging.error(f"Error serving {addr}: {e}")
    finally:
        conn.close()


def start_file_server(peer_port):
    """Start listening for incoming file requests."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", peer_port))
    server.listen(10)
    logging.info(f"File server listening on port {peer_port}")
    while True:
        conn, addr = server.accept()
        threading.Thread(
            target=handle_incoming_request,
            args=(conn, addr),
            daemon=True
        ).start()


# ---------- Ping Thread ----------
def ping_tracker(peer_id):
    """Keep registration alive by pinging tracker periodically."""
    while True:
        time.sleep(PING_INTERVAL)
        tracker_request({"action": "ping", "peer_id": peer_id})


# ---------- CLI Commands ----------
def cmd_list(peer_id):
    """List all online peers and their files."""
    response = tracker_request({"action": "list", "peer_id": peer_id})
    if not response or response["status"] != "ok":
        print("❌ Failed to get peer list")
        return

    peers = response.get("peers", {})
    if not peers:
        print("📭 No other peers online right now")
        return

    print(f"\n{'─'*55}")
    print(f"  {'PEER ID':<20} {'IP:PORT':<22} FILES")
    print(f"{'─'*55}")
    for pid, info in peers.items():
        files = ", ".join(info["files"]) if info["files"] else "(no files)"
        addr  = f"{info['ip']}:{info['port']}"
        print(f"  {pid:<20} {addr:<22} {files}")
    print(f"{'─'*55}\n")


def cmd_search(peer_id, filename):
    """Search for a file across all peers."""
    response = tracker_request({
        "action":   "search",
        "peer_id":  peer_id,
        "filename": filename
    })
    if not response or response["status"] != "ok":
        print("❌ Search failed")
        return

    results = response.get("results", {})
    if not results:
        print(f"🔍 No peers have '{filename}'")
        return

    print(f"\n🔍 Found '{filename}' on {len(results)} peer(s):")
    for pid, info in results.items():
        print(f"   • {pid} @ {info['ip']}:{info['port']} → {info['filename']}")
    print()


def cmd_download(peer_id, filename, peer_ip, peer_port):
    """
    Download a file directly from another peer.
    RECEIVER SIDE — receives encrypted data, decrypts after.
    """
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    save_path = os.path.join(DOWNLOAD_FOLDER, filename)

    print(f"📥 Connecting to {peer_ip}:{peer_port}...")

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(30)
        conn.connect((peer_ip, int(peer_port)))

        # find the offset (number of chunks downloaded * CHUNK_SIZE)
        downloaded_size = os.path.getsize(save_path) if os.path.exists(save_path) else 0
        offset = (downloaded_size // CHUNK_SIZE) * CHUNK_SIZE # align to chunk boundary
        
        # truncate incomplete last chunk before resuming
        if offset > 0:
            with open(save_path, "r+b") as f:
                f.truncate(offset)

        # Request the file
        send_json(conn, {"action": "download", "filename": filename, "offset": offset})

        # Get metadata
        meta = recv_json(conn)
        if not meta or meta["status"] != "ok":
            print(f"❌ Error: {meta.get('message', 'Unknown error')}")
            conn.close()
            return

        filesize = meta["filesize"]
        checksum = meta["checksum"]

        print(f"📦 Receiving '{filename}' ({filesize} bytes)...")
        if offset > 0:
            print(f"⏩ Resuming from byte {offset}...")
 
        # Receive, decrypt and write chunk by chunk
        received = offset
        mode = "ab" if offset > 0 else "wb"

        with open(save_path, mode) as f:
            while True:
                # Read encrypted chunk size (8 bytes)
                size_data = conn.recv(8)
                if not size_data:
                    break
                encrypted_chunk_size  = int.from_bytes(size_data, "big") # Read chunk size first (8 bytes)
                if encrypted_chunk_size == 0:   # 0 = sender done
                    break

                # Read exactly encrypted_chunk_size bytes
                encrypted_chunk = b""
                while len(encrypted_chunk) < encrypted_chunk_size:
                    enc_data = conn.recv(min(CHUNK_SIZE, encrypted_chunk_size - len(encrypted_chunk)))
                    if not enc_data:
                        break
                    encrypted_chunk += enc_data

                # Decrypt the received chunk
                try:
                    raw_data = decrypt_bytes(encrypted_chunk)
                except Exception:
                    print("❌ Decryption failed! Wrong password or corrupted data.")
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    return
                
                # Write chunk
                f.write(raw_data)
                f.flush()
                os.fsync(f.fileno())   # safe write
        
                # Progress bar
                received += len(raw_data)
                pct = received / filesize * 100
                bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
                print(f"\r   [{bar}] {pct:.1f}%", end="", flush=True)
    
        print()
        print("🔓 Decryption successful...")
        conn.close()
 
        # Verify checksum
        local_checksum = sha256_file(save_path)
        if local_checksum == checksum:
            print(f"✅ Downloaded '{filename}' → {save_path}")
            print(f"   SHA256 verified ✓")
        else:
            print(f"⚠️  Checksum mismatch! File may be corrupted.")
            os.remove(save_path)

    except ConnectionRefusedError:
        print(f"❌ Cannot connect to peer {peer_ip}:{peer_port}")
    except ConnectionResetError:
        print(f"\n❌ Download failed! Sender disconnected.")
    except Exception as e:
        print(f"\n❌ Download failed: {e}")
        if os.path.exists(save_path):
            os.remove(save_path)


def cmd_share(peer_id, filepath):
    """Add a file to your shared folder."""
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return

    os.makedirs(SHARED_FOLDER, exist_ok=True)
    filename = os.path.basename(filepath)
    dest     = os.path.join(SHARED_FOLDER, filename)

    # Copy file to shared folder
    with open(filepath, "rb") as src, open(dest, "wb") as dst:
        while chunk := src.read(CHUNK_SIZE):
            dst.write(chunk)

    # Update tracker
    files    = list_shared_files()
    response = tracker_request({
        "action":  "update",
        "peer_id": peer_id,
        "files":   files
    })

    if response and response["status"] == "ok":
        print(f"✅ '{filename}' is now shared with the network")
    else:
        print(f"⚠️  File copied but tracker update failed")


def cmd_myfiles():
    """Show files you are currently sharing."""
    files = list_shared_files()
    if not files:
        print("📂 You are not sharing any files yet")
        print(f"   Put files in '{SHARED_FOLDER}' or use: share <filepath>")
        return
    print(f"\n📂 Your shared files ({len(files)}):")
    for f in files:
        path = os.path.join(SHARED_FOLDER, f)
        size = os.path.getsize(path)
        print(f"   • {f} ({size:,} bytes)")
    print()


def print_help():
    print("""
┌─────────────────────────────────────────────┐
│           P2P File Share - Commands         │
├─────────────────────────────────────────────┤
│  list                  → Show online peers  │
│  search <filename>     → Find a file        │
│  get <file> <ip> <port>→ Download file      │
│  share <filepath>      → Share a file       │
│  myfiles               → Your shared files  │
│  help                  → Show this menu     │
│  exit                  → Leave network      │
└─────────────────────────────────────────────┘
""")


# ---------- Main ----------
def main():
    global PASSWORD, FERNET_KEY

    os.makedirs(SHARED_FOLDER, exist_ok=True)
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    # Start file server on a random port
    file_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    file_server.bind(("0.0.0.0", 0))
    actual_port = file_server.getsockname()[1]
    file_server.close()

    threading.Thread(
        target=start_file_server,
        args=(actual_port,),
        daemon=True
    ).start()

    my_ip   = get_local_ip()
    peer_id = None
    password = None
    while True:
        peer_id = input("Enter your peer name (e.g. alice, bob): ").strip()
        if not peer_id:
            peer_id = f"peer_{os.getpid()}"

        # Register with tracker
        print(f"🔗 Connecting to tracker at {TRACKER_HOST}:{TRACKER_PORT}...")
        response = tracker_request({
            "action":  "register",
            "peer_id": peer_id,
            "ip":      my_ip,
            "port":    actual_port,
            "files":   list_shared_files()
        })

        if not response or response["status"] != "ok":
            print("❌ Failed to register with tracker. Exiting.")
            sys.exit(1)
        elif response["message"] == "peer_id already used":
            print("❌ Failed to register with tracker. ")
            print(f"Reason: peer name `{peer_id}` is not available.")
            print("Try using another peer name...")
        else:
            # NEW: Ask for network password — hidden input like ***
            # All peers must use the same password
            # Wrong password = decryption fails = cannot access any files
            password   = getpass.getpass("🔑 Network password: ")
            FERNET_KEY = make_fernet_key(password)
            print("✅ Encryption key ready")
            break

    print(f"✅ Registered as '{peer_id}' | IP: {my_ip} | Port: {actual_port}")

    # Start ping thread
    threading.Thread(target=ping_tracker, args=(peer_id,), daemon=True).start()

    print_help()

    # CLI loop
    while True:
        try:
            cmd = input("p2p> ").strip().split()
            if not cmd:
                continue

            if cmd[0] == "exit":
                tracker_request({"action": "leave", "peer_id": peer_id})
                print("👋 Left the network. Goodbye!")
                break

            elif cmd[0] == "list":
                cmd_list(peer_id)

            elif cmd[0] == "search":
                if len(cmd) < 2:
                    print("Usage: search <filename>")
                else:
                    cmd_search(peer_id, cmd[1])

            elif cmd[0] == "get":
                if len(cmd) < 4:
                    print("Usage: get <filename> <peer_ip> <peer_port>")
                else:
                    cmd_download(peer_id, cmd[1], cmd[2], cmd[3])

            elif cmd[0] == "share":
                if len(cmd) < 2:
                    print("Usage: share <filepath>")
                else:
                    cmd_share(peer_id, cmd[1])

            elif cmd[0] == "myfiles":
                cmd_myfiles()

            elif cmd[0] == "help":
                print_help()

            else:
                print(f"❓ Unknown command: '{cmd[0]}'. Type 'help' for commands.")

        except KeyboardInterrupt:
            tracker_request({"action": "leave", "peer_id": peer_id})
            print("\n👋 Left the network. Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
