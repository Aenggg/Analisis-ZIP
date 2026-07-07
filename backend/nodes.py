import os
import socket
import sys
import time

TIMEOUT = 30


def _split_peers(raw):
    return [peer.strip().rstrip("/") for peer in raw.split(",") if peer.strip()]


def _arg_value(name, default=None):
    if name not in sys.argv:
        return default

    index = sys.argv.index(name)
    if index + 1 >= len(sys.argv):
        return default
    return sys.argv[index + 1]


def _local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


PORT = int(os.environ.get("PORT") or os.environ.get("P2P_PORT") or _arg_value("--port", "8000"))
HOST = os.environ.get("P2P_HOST") or _arg_value("--host", "127.0.0.1")
_public_host = _local_ip() if HOST in {"0.0.0.0", "::"} else HOST

railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
default_node_url = f"https://{railway_domain}" if railway_domain else f"http://{_public_host}:{PORT}"
NODE_URL = os.environ.get("P2P_NODE_URL", default_node_url).rstrip("/")
NODE_ID = os.environ.get("P2P_NODE_ID", f"node-{PORT}")
CONFIGURED_PEERS = _split_peers(os.environ.get("P2P_PEERS", ""))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.environ.get("P2P_STORAGE_DIR", os.path.join(BASE_DIR, "storage", NODE_ID))

nodes = {}


def bootstrap_nodes():
    nodes[NODE_URL] = {
        "node_id": NODE_ID,
        "status": "self",
        "last_seen": time.time(),
        "source": "self",
    }

    for peer in CONFIGURED_PEERS:
        if peer != NODE_URL:
            nodes[peer] = {
                "node_id": peer,
                "status": "configured",
                "last_seen": time.time(),
                "source": "env",
            }


def register_node(address: str, node_id=None, source="manual"):
    address = address.rstrip("/")
    if address == NODE_URL:
        bootstrap_nodes()
        return nodes[NODE_URL]

    nodes[address] = {
        "node_id": node_id or address,
        "status": "online",
        "last_seen": time.time(),
        "source": source,
    }
    return nodes[address]


def heartbeat(address: str, status="online", node_id=None, source="discovered"):
    address = address.rstrip("/")
    if address not in nodes:
        register_node(address, node_id=node_id, source=source)
    nodes[address]["last_seen"] = time.time()
    nodes[address]["status"] = status
    if node_id:
        nodes[address]["node_id"] = node_id


def get_peer_urls(include_self=False):
    bootstrap_nodes()
    urls = list(nodes.keys())
    if not include_self:
        urls = [url for url in urls if url != NODE_URL]
    return urls


def get_nodes():
    bootstrap_nodes()
    now = time.time()
    for address, info in nodes.items():
        if address == NODE_URL:
            info["status"] = "self"
        elif now - info["last_seen"] > TIMEOUT and info["status"] == "online":
            info["status"] = "offline"
    return nodes


bootstrap_nodes()
