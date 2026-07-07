import os
import shutil
import hashlib
import tempfile
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from crypto import sign, verify as verify_signature
from ledger import append_block, add_file, find_file, get_chain, get_summary, replace_chain, validate_chain
from merkle import merkle_root
from nodes import CONFIGURED_PEERS, NODE_ID, NODE_URL, PORT, STORAGE_DIR, get_nodes, get_peer_urls, heartbeat, register_node
from torrent import CHUNK_SIZE, hash_file, rebuild_file, split_file

app = FastAPI(
    title="ZIP Integrity P2P Lightweight Blockchain",
    description="Analisis integritas file ZIP menggunakan SHA-256, Merkle Tree, dan blockchain lightweight berbasis P2P.",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
STORAGE = STORAGE_DIR
REBUILD_DIR = os.path.join(STORAGE, "rebuild")
os.makedirs(STORAGE, exist_ok=True)
os.makedirs(REBUILD_DIR, exist_ok=True)

DISCOVERY_PORT = int(os.environ.get("P2P_DISCOVERY_PORT", "9779"))
DISCOVERY_INTERVAL = int(os.environ.get("P2P_DISCOVERY_INTERVAL", "5"))
DEFAULT_DISCOVERY = "0" if os.environ.get("RAILWAY_PUBLIC_DOMAIN") else "1"
DISCOVERY_ENABLED = os.environ.get("P2P_DISCOVERY", DEFAULT_DISCOVERY) != "0"
SCAN_PORTS = [
    int(value)
    for part in os.environ.get("P2P_SCAN_PORTS", "8000-8010").replace(" ", "").split(",")
    if part
    for value in (
        range(int(part.split("-", 1)[0]), int(part.split("-", 1)[1]) + 1)
        if "-" in part
        else [int(part)]
    )
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-P2P-Fetched-Chunks"],
)


def _chunk_hashes(chunks):
    return [hash_file(chunk) for chunk in chunks]


def _json_request(url, method="GET", payload=None, timeout=2):
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _discover_localhost_peers():
    if not DISCOVERY_ENABLED:
        return []

    discovered = []
    for port in SCAN_PORTS:
        if port == PORT:
            continue

        peer = f"http://127.0.0.1:{port}"
        try:
            identity = _json_request(f"{peer}/identity", timeout=0.5)
            peer_url = identity.get("node_url")
            if peer_url and peer_url != NODE_URL:
                register_node(peer_url, identity.get("node_id"), source="localhost-scan")
                discovered.append(peer_url)
        except Exception:
            continue
    return discovered


def _discovery_payload():
    return json.dumps({
        "type": "p2p_zip_chain_hello",
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "port": PORT,
    }).encode()


def _discovery_listener():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", DISCOVERY_PORT))
        sock.settimeout(1)
    except Exception:
        return

    while True:
        try:
            data, _ = sock.recvfrom(4096)
            payload = json.loads(data.decode())
            if payload.get("type") != "p2p_zip_chain_hello":
                continue
            peer_url = payload.get("node_url", "").rstrip("/")
            if peer_url and peer_url != NODE_URL:
                heartbeat(peer_url, "online", payload.get("node_id"), source="lan-broadcast")
        except Exception:
            continue


def _discovery_announcer():
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(_discovery_payload(), ("255.255.255.255", DISCOVERY_PORT))
        except Exception:
            pass

        _discover_localhost_peers()
        time.sleep(DISCOVERY_INTERVAL)


def _start_discovery():
    if not DISCOVERY_ENABLED:
        return

    threading.Thread(target=_discovery_listener, daemon=True).start()
    threading.Thread(target=_discovery_announcer, daemon=True).start()
    _discover_localhost_peers()


@app.get("/")
def frontend_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend index.html tidak ditemukan.")
    return FileResponse(index_path)


@app.get("/app.js")
def frontend_app():
    app_path = os.path.join(FRONTEND_DIR, "app.js")
    if not os.path.exists(app_path):
        raise HTTPException(status_code=404, detail="Frontend app.js tidak ditemukan.")
    return FileResponse(app_path, media_type="application/javascript")


def _broadcast_block(block, exclude=None):
    exclude = set(exclude or [])
    results = []
    for peer in get_peer_urls():
        if peer in exclude:
            continue
        try:
            response = _json_request(
                f"{peer}/receive_block",
                method="POST",
                payload={"block": block, "from_node": NODE_URL},
            )
            heartbeat(peer, "online")
            results.append({"peer": peer, "ok": True, "response": response})
        except Exception as exc:
            heartbeat(peer, "offline")
            results.append({"peer": peer, "ok": False, "error": str(exc)})
    return results


def _sync_with_peers():
    results = []
    for peer in get_peer_urls():
        try:
            remote = _json_request(f"{peer}/chain")
            heartbeat(peer, "online")
            replacement = replace_chain(remote.get("chain", []))
            results.append({"peer": peer, "ok": True, **replacement})
        except Exception as exc:
            heartbeat(peer, "offline")
            results.append({"peer": peer, "ok": False, "error": str(exc)})
    return results


def _fetch_chunk_from_peer(peer, file_hash, index):
    try:
        url = f"{peer}/chunks/{file_hash}/{index}"
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read()
    except Exception:
        return None


def _ensure_local_chunks(block):
    data = block["data"]
    chunk_dir = os.path.join(STORAGE, data["file_hash"])
    os.makedirs(chunk_dir, exist_ok=True)

    fetched = []
    for index, expected_hash in enumerate(data["chunk_hashes"]):
        path = os.path.join(chunk_dir, f"chunk_{index}")
        if os.path.exists(path) and hash_file(path) == expected_hash:
            continue

        for peer in data.get("chunk_owners", {}).get(str(index), []):
            if peer == NODE_URL:
                continue
            content = _fetch_chunk_from_peer(peer, data["file_hash"], index)
            if content and hashlib.sha256(content).hexdigest() == expected_hash:
                with open(path, "wb") as f:
                    f.write(content)
                fetched.append({"chunk": index, "from": peer})
                break

    return fetched


def _file_integrity(path):
    file_hasher = hashlib.sha256()
    chunk_hashes = []

    with open(path, "rb") as f:
        while True:
            data = f.read(CHUNK_SIZE)
            if not data:
                break
            file_hasher.update(data)
            chunk_hashes.append(hashlib.sha256(data).hexdigest())

    return file_hasher.hexdigest(), chunk_hashes, merkle_root(chunk_hashes)


def _signature_payload(file_hash, root):
    return f"{file_hash}:{root}".encode()


def _is_zip(path, filename):
    return filename.lower().endswith(".zip") and zipfile.is_zipfile(path)


def _chunk_paths(file_hash, expected_count=None):
    chunk_dir = os.path.join(STORAGE, file_hash)
    if not os.path.isdir(chunk_dir):
        return []

    chunks = [name for name in os.listdir(chunk_dir) if name.startswith("chunk_")]
    chunks.sort(key=lambda name: int(name.split("_", 1)[1]))
    paths = [os.path.join(chunk_dir, name) for name in chunks]
    if expected_count is not None and len(paths) != expected_count:
        return []
    return paths


@app.on_event("startup")
def startup_sync():
    _start_discovery()
    _sync_with_peers()


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join(STORAGE, file.filename)

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        if not _is_zip(file_path, file.filename):
            os.remove(file_path)
            raise HTTPException(status_code=400, detail="Only valid .zip files can be registered.")

        file_hash = hash_file(file_path)
        chunk_dir = os.path.join(STORAGE, file_hash)
        chunks = split_file(file_path, chunk_dir)
        chunk_hashes = _chunk_hashes(chunks)
        root = merkle_root(chunk_hashes)
        signature = sign(_signature_payload(file_hash, root))
        chunk_owners = {str(index): [NODE_URL] for index in range(len(chunk_hashes))}

        block = add_file(
            file_name=file.filename,
            file_hash=file_hash,
            file_size=os.path.getsize(file_path),
            chunk_hashes=chunk_hashes,
            merkle_root=root,
            signature=signature,
            owner=NODE_URL,
            chunk_owners=chunk_owners,
        )
        broadcast_results = _broadcast_block(block)

        return {
            "status": "registered",
            "message": "ZIP file registered in lightweight blockchain ledger.",
            "file_hash": file_hash,
            "merkle_root": root,
            "chunks": len(chunks),
            "block_index": block["index"],
            "block_hash": block["block_hash"],
            "owner": NODE_URL,
            "broadcast": broadcast_results,
        }
    except HTTPException:
        raise
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/upload_with_file")
async def upload_with_file(file: UploadFile = File(...)):
    return await upload_file(file)


@app.get("/verify/{file_hash}")
def verify(file_hash: str):
    block = find_file(file_hash)
    if not block:
        return {
            "authentic": False,
            "reason": "Hash is not registered in the lightweight blockchain ledger.",
        }

    data = block["data"]
    chunks = _chunk_paths(file_hash, data["chunk_count"])
    current_chunk_hashes = _chunk_hashes(chunks) if chunks else []
    current_root = merkle_root(current_chunk_hashes)
    signature_ok = verify_signature(
        _signature_payload(data["file_hash"], data["merkle_root"]),
        bytes.fromhex(data["signature"]),
    )
    chain_ok = validate_chain()
    chunks_ok = current_chunk_hashes == data["chunk_hashes"]
    root_ok = current_root == data["merkle_root"]

    return {
        "authentic": chain_ok and signature_ok and chunks_ok and root_ok,
        "blockchain_valid": chain_ok,
        "signature_valid": signature_ok,
        "chunks_valid": chunks_ok,
        "merkle_root_valid": root_ok,
        "file_hash": file_hash,
        "merkle_root": data["merkle_root"],
        "block_hash": block["block_hash"],
    }


@app.post("/verify_file")
async def verify_file(file: UploadFile = File(...)):
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=STORAGE) as tmp:
            temp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

        if not _is_zip(temp_path, file.filename):
            raise HTTPException(status_code=400, detail="Only valid .zip files can be verified.")

        uploaded_hash, uploaded_chunk_hashes, uploaded_root = _file_integrity(temp_path)
        block = find_file(uploaded_hash)

        if not block:
            return {
                "authentic": False,
                "reason": "ZIP file is not registered or its content has changed.",
                "uploaded_file_name": file.filename,
                "uploaded_file_hash": uploaded_hash,
                "uploaded_merkle_root": uploaded_root,
            }

        data = block["data"]
        stored_chunks = _chunk_paths(uploaded_hash, data["chunk_count"])
        stored_chunk_hashes = _chunk_hashes(stored_chunks) if stored_chunks else []
        stored_root = merkle_root(stored_chunk_hashes)
        signature_ok = verify_signature(
            _signature_payload(data["file_hash"], data["merkle_root"]),
            bytes.fromhex(data["signature"]),
        )

        chain_ok = validate_chain()
        uploaded_matches_block = (
            uploaded_hash == data["file_hash"]
            and uploaded_chunk_hashes == data["chunk_hashes"]
            and uploaded_root == data["merkle_root"]
        )
        stored_chunks_ok = stored_chunk_hashes == data["chunk_hashes"]
        stored_root_ok = stored_root == data["merkle_root"]

        return {
            "authentic": (
                chain_ok
                and signature_ok
                and uploaded_matches_block
                and stored_chunks_ok
                and stored_root_ok
            ),
            "message": "ZIP file matches the registered blockchain record." if uploaded_matches_block else "ZIP file does not match the registered blockchain record.",
            "uploaded_file_name": file.filename,
            "registered_file_name": data["file_name"],
            "filename_matches": file.filename == data["file_name"],
            "file_hash": uploaded_hash,
            "merkle_root": uploaded_root,
            "blockchain_valid": chain_ok,
            "signature_valid": signature_ok,
            "uploaded_file_matches_block": uploaded_matches_block,
            "stored_chunks_valid": stored_chunks_ok,
            "stored_merkle_root_valid": stored_root_ok,
            "block_hash": block["block_hash"],
        }
    except HTTPException:
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/download/{file_hash}")
def download(file_hash: str):
    block = find_file(file_hash)
    if not block:
        raise HTTPException(status_code=404, detail="Hash is not registered.")

    fetched = _ensure_local_chunks(block)
    chunks = _chunk_paths(file_hash, block["data"]["chunk_count"])
    if not chunks:
        raise HTTPException(status_code=404, detail="Chunk data not found.")

    output_path = os.path.join(REBUILD_DIR, block["data"]["file_name"])
    rebuild_file(chunks, output_path)

    if hash_file(output_path) != file_hash:
        raise HTTPException(status_code=409, detail="Rebuilt ZIP hash does not match ledger hash.")

    return FileResponse(
        output_path,
        filename=block["data"]["file_name"],
        media_type="application/zip",
        headers={"X-P2P-Fetched-Chunks": json.dumps(fetched)},
    )


@app.post("/register_node")
def register(address: str = Form(...)):
    return register_node(address)


@app.get("/nodes")
def nodes():
    return get_nodes()


@app.get("/summary")
def summary():
    return get_summary(node_id=NODE_ID, node_url=NODE_URL, peers=get_peer_urls())


@app.get("/identity")
def identity():
    return {
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "port": PORT,
        "storage_dir": STORAGE,
        "peers": get_peer_urls(),
        "discovery_enabled": DISCOVERY_ENABLED,
    }


@app.post("/discover")
def discover():
    return {
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "localhost_peers": _discover_localhost_peers(),
        "known_peers": get_peer_urls(),
    }


@app.get("/chain")
def chain():
    local_chain = get_chain()
    return {
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "length": len(local_chain),
        "valid": validate_chain(local_chain),
        "chain": local_chain,
    }


@app.post("/receive_block")
def receive_block(payload: dict):
    from_node = payload.get("from_node")
    if from_node:
        register_node(from_node, from_node)
    result = append_block(payload.get("block", {}))
    if result["accepted"] and result["reason"] == "Block accepted.":
        result["forwarded"] = _broadcast_block(payload.get("block", {}), exclude={from_node})
    if not result["accepted"]:
        result["sync"] = _sync_with_peers()
    return result


@app.post("/sync")
def sync():
    return {
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "results": _sync_with_peers(),
        "local_length": len(get_chain()),
        "local_valid": validate_chain(),
    }


@app.get("/peers/validate")
def validate_peers():
    results = []
    local_chain = get_chain()
    local_tip = local_chain[-1]["block_hash"]

    for peer in get_peer_urls():
        try:
            remote = _json_request(f"{peer}/chain")
            remote_chain = remote.get("chain", [])
            remote_tip = remote_chain[-1]["block_hash"] if remote_chain else None
            heartbeat(peer, "online")
            results.append({
                "peer": peer,
                "reachable": True,
                "valid": validate_chain(remote_chain),
                "length": len(remote_chain),
                "same_tip": remote_tip == local_tip,
            })
        except Exception as exc:
            heartbeat(peer, "offline")
            results.append({
                "peer": peer,
                "reachable": False,
                "valid": False,
                "error": str(exc),
            })

    return {
        "node_id": NODE_ID,
        "node_url": NODE_URL,
        "local_valid": validate_chain(local_chain),
        "local_length": len(local_chain),
        "peers": results,
    }


@app.get("/chunks/{file_hash}/{index}")
def get_chunk(file_hash: str, index: int):
    block = find_file(file_hash)
    if not block:
        raise HTTPException(status_code=404, detail="File hash is not registered.")

    chunk_path = os.path.join(STORAGE, file_hash, f"chunk_{index}")
    if not os.path.exists(chunk_path):
        raise HTTPException(status_code=404, detail="Chunk is not stored on this peer.")

    expected_hashes = block["data"].get("chunk_hashes", [])
    if index >= len(expected_hashes) or hash_file(chunk_path) != expected_hashes[index]:
        raise HTTPException(status_code=409, detail="Chunk hash does not match ledger.")

    return FileResponse(chunk_path, media_type="application/octet-stream")
