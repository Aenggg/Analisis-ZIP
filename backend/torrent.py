import os
import hashlib

CHUNK_SIZE = 256 * 1024  # 256 KB

def hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            h.update(block)
    return h.hexdigest()

def split_file(path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    chunks = []

    with open(path, "rb") as f:
        i = 0
        while True:
            data = f.read(CHUNK_SIZE)
            if not data:
                break
            chunk_path = os.path.join(out_dir, f"chunk_{i}")
            with open(chunk_path, "wb") as c:
                c.write(data)
            chunks.append(chunk_path)
            i += 1

    return chunks

def rebuild_file(chunks, output):
    with open(output, "wb") as out:
        for c in chunks:
            with open(c, "rb") as f:
                out.write(f.read())
