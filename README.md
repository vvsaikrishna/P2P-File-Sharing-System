# 🌐 P2P File Sharing System

A simple decentralized peer-to-peer file sharing system built with Python sockets.

## Architecture

```
         TRACKER SERVER
         (phonebook only)
         /      |      \
        /       |       \
    Peer A   Peer B   Peer C
    (alice)  (bob)    (carol)

Step 1: All peers register with tracker (share their IP, port, file list)
Step 2: Peer A searches tracker for a file
Step 3: Tracker says "Peer B has it at 192.168.x.x:PORT"
Step 4: Peer A connects DIRECTLY to Peer B and downloads
```

Files are **never stored on the tracker**. Tracker is just a directory.

---

## Features

- ✅ Peer discovery via central tracker
- ✅ Direct peer-to-peer file transfer (no server in between)
- ✅ Added encryption (AES) using `cryptography` library
- ✅ Added authentication (password to join network)
- ✅ Resume interrupted downloads
- ✅ File integrity verification (SHA256 checksum)
- ✅ Transfer progress bar
- ✅ Search for files across all peers
- ✅ Auto-cleanup of dead peers
- ✅ Multi-threaded (handles multiple peers simultaneously)
- ✅ Works across different machines on same network


---

## Project Structure

```
p2p_fileshare/
├── tracker.py    ← Run this first (once, on any machine)
├── peer.py       ← Run this on each machine that wants to share
├── shared/       ← Put files here to share them
├── downloads/    ← Downloaded files go here
└── README.md
```

---

## How to Run

### Step 1: Start the Tracker (run once)
```bash
python tracker.py
```
You'll see:
```
[TRACKER] 12:00:00 - Tracker running on port 9000
[TRACKER] 12:00:00 - Waiting for peers to connect...
```

### Step 2: Start Peer(s)

**On Machine 1 (or Terminal 1):**
```bash
python peer.py
```
Enter your name when prompted: `alice`

**On Machine 2 (or Terminal 2):**
```bash
python peer.py
```
Enter your name when prompted: `bob`

> ⚠️ If running on different machines, edit `TRACKER_HOST` in `peer.py` to the tracker's IP address.

---

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| `list` | Show all online peers and their files | `list` |
| `search <name>` | Find who has a file | `search photo.jpg` |
| `get <file> <ip> <port>` | Download from a peer | `get photo.jpg 192.168.1.5 54321` |
| `share <filepath>` | Share a file with network | `share /home/user/photo.jpg` |
| `myfiles` | Show files you're sharing | `myfiles` |
| `help` | Show commands | `help` |
| `exit` | Leave the network | `exit` |

---

## Example Session

```
Enter your peer name: alice
🔗 Connecting to tracker at 127.0.0.1:9000...
✅ Registered as 'alice' | IP: 192.168.1.4 | Port: 52341

p2p> share /home/alice/notes.pdf
✅ 'notes.pdf' is now shared with the network

p2p> list
───────────────────────────────────────────────────────
  PEER ID              IP:PORT                FILES
───────────────────────────────────────────────────────
  bob                  192.168.1.5:53211      photo.jpg, music.mp3

p2p> search photo
🔍 Found 'photo' on 1 peer(s):
   • bob @ 192.168.1.5:53211 → photo.jpg

p2p> get photo.jpg 192.168.1.5 53211
📥 Connecting to 192.168.1.5:53211...
📦 Receiving 'photo.jpg' (2,048,000 bytes)...
   [████████████████████] 100.0%
✅ Downloaded 'photo.jpg' → ./downloads/photo.jpg
   SHA256 verified ✓
```

---

## Running on Different Machines (Same WiFi)

1. Find tracker machine's IP:
   ```bash
   # On Linux/Mac
   ip addr show   # or ifconfig
   # On Windows
   ipconfig
   ```

2. Edit `peer.py`:
   ```python
   TRACKER_HOST = "192.168.1.X"  # ← tracker machine's IP
   ```

3. Run tracker on one machine, peer.py on all others.

---

## Technical Details

| Component | Choice | Reason |
|-----------|--------|--------|
| Protocol | TCP | Reliable, ordered delivery for file transfer |
| Concurrency | Threading | Handle multiple peers simultaneously |
| File integrity | SHA256 | Detect corruption after transfer |
| Transfer | Chunked (4KB) | Works for large files without memory issues |
| Peer keepalive | Ping every 20s | Tracker cleans up dead peers after 60s |
| Cryptography | AES-256 | Encryption and decryption of the file data for confidentiality |
| Authentication | password required | Ensures only the authenticated users can decrypt the file |
| Resume interrupted downloads | - | byte-offset tracking and partial file writes to continue interrupted transfers efficiently |
---

## Requirements

- Python 3.8+
- Install `cryptography` library as follows:
   ```bash
   pip install cryptography
   ```
- No other external libraries needed (uses only stdlib)

---

## Possible Extensions (for extra credit)

- [ ] GUI using `tkinter`
- [ ] Parallel chunk download from multiple peers
