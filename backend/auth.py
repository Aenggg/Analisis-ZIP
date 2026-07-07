import json
import uuid
import os

NODE_FILE = "storage/nodes.json"

def load_nodes():
    if not os.path.exists(NODE_FILE):
        return {}
    with open(NODE_FILE) as f:
        return json.load(f)

def save_nodes(nodes):
    with open(NODE_FILE, "w") as f:
        json.dump(nodes, f, indent=2)

def register_node(name):
    nodes = load_nodes()
    api_key = str(uuid.uuid4())
    nodes[api_key] = {
        "name": name,
        "status": "online"
    }
    save_nodes(nodes)
    return api_key
