import hashlib
import json
import os
import time
from nodes import STORAGE_DIR

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_FILE = os.path.join(STORAGE_DIR, "blockchain_ledger.json")


def _block_hash(block):
    block_copy = {k: v for k, v in block.items() if k != "block_hash"}
    encoded = json.dumps(block_copy, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _genesis_block():
    block = {
        "index": 0,
        "timestamp": 0,
        "previous_hash": "0" * 64,
        "data": {
            "type": "genesis",
            "description": "Shared genesis block for lightweight P2P ZIP integrity blockchain",
        },
    }
    block["block_hash"] = _block_hash(block)
    return block


def _save_ledger(ledger):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)


def _ensure_ledger():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    if not os.path.exists(LEDGER_FILE):
        _save_ledger({"chain": [_genesis_block()]})


def _load_ledger():
    _ensure_ledger()
    with open(LEDGER_FILE) as f:
        ledger = json.load(f)

    if "chain" not in ledger:
        ledger = {"chain": [_genesis_block()]}
        _save_ledger(ledger)

    return ledger


def get_chain():
    return _load_ledger()["chain"]


def get_last_block():
    return get_chain()[-1]


def add_file(file_name, file_hash, file_size, chunk_hashes, merkle_root, signature, owner, chunk_owners):
    ledger = _load_ledger()
    block = {
        "index": len(ledger["chain"]),
        "timestamp": time.time(),
        "previous_hash": ledger["chain"][-1]["block_hash"],
        "data": {
            "file_name": file_name,
            "file_hash": file_hash,
            "file_size": file_size,
            "chunk_count": len(chunk_hashes),
            "chunk_hashes": chunk_hashes,
            "chunk_owners": chunk_owners,
            "owner": owner,
            "merkle_root": merkle_root,
            "signature": signature.hex(),
            "algorithm": "SHA-256",
            "file_type": "ZIP",
        },
    }
    block["block_hash"] = _block_hash(block)
    ledger["chain"].append(block)
    _save_ledger(ledger)
    return block


def validate_chain(chain=None):
    chain = chain or get_chain()
    if not chain:
        return False

    expected_genesis = _genesis_block()
    if chain[0].get("block_hash") != expected_genesis["block_hash"]:
        return False

    for index, block in enumerate(chain):
        if block.get("index") != index:
            return False
        if block.get("block_hash") != _block_hash(block):
            return False
        if index > 0 and block.get("previous_hash") != chain[index - 1].get("block_hash"):
            return False
    return True


def append_block(block):
    ledger = _load_ledger()
    chain = ledger["chain"]

    if any(existing.get("block_hash") == block.get("block_hash") for existing in chain):
        return {"accepted": True, "reason": "Block already exists."}

    if block.get("index") != len(chain):
        return {"accepted": False, "reason": "Block index does not follow local chain."}

    if block.get("previous_hash") != chain[-1].get("block_hash"):
        return {"accepted": False, "reason": "Previous hash does not match local chain tip."}

    candidate = chain + [block]
    if not validate_chain(candidate):
        return {"accepted": False, "reason": "Received block is invalid."}

    chain.append(block)
    _save_ledger(ledger)
    return {"accepted": True, "reason": "Block accepted."}


def replace_chain(chain):
    if not validate_chain(chain):
        return {"replaced": False, "reason": "Remote chain is invalid."}

    local_chain = get_chain()
    if len(chain) <= len(local_chain):
        return {"replaced": False, "reason": "Local chain is equal or longer."}

    _save_ledger({"chain": chain})
    return {"replaced": True, "reason": "Local chain replaced with longer valid peer chain."}


def find_file(file_hash):
    for block in reversed(get_chain()):
        if block.get("data", {}).get("file_hash") == file_hash:
            return block
    return None


def get_summary(node_id=None, node_url=None, peers=None):
    chain = get_chain()
    file_blocks = [b for b in chain if b.get("data", {}).get("file_hash")]

    return {
        "research_title": "Analisis Integritas File ZIP Menggunakan Blockchain Lightweight Berbasis Peer-to-Peer dengan Algoritma SHA-256 dan Merkle Tree untuk Menjamin Keaslian Data",
        "node_id": node_id,
        "node_url": node_url,
        "peers_configured": len(peers or []),
        "blockchain_valid": validate_chain(chain),
        "total_blocks": len(chain),
        "files_registered": len(file_blocks),
        "algorithm": "SHA-256",
        "structure": "Merkle Tree",
        "network_model": "Peer-to-Peer",
        "files_keys_sample": [
            {
                "file_name": b["data"].get("file_name"),
                "file_hash": b["data"]["file_hash"],
                "merkle_root": b["data"]["merkle_root"],
                "block_hash": b["block_hash"],
                "owner": b["data"].get("owner"),
                "timestamp": b.get("timestamp"),
            }
            for b in file_blocks[-5:]
        ],
    }
