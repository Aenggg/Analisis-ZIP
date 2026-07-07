import os

CHUNK_SIZE = 1024 * 512  # 512KB

def chunk_file(file_bytes, file_hash):
    folder = f"storage/chunks/{file_hash}"
    os.makedirs(folder, exist_ok=True)

    chunks = []
    for i in range(0, len(file_bytes), CHUNK_SIZE):
        chunk = file_bytes[i:i+CHUNK_SIZE]
        path = f"{folder}/{i}.chunk"
        with open(path, "wb") as f:
            f.write(chunk)
        chunks.append(chunk)

    return chunks
