# Deploy ke Railway

Project ini bisa dideploy sebagai satu service Railway. FastAPI akan menjalankan backend sekaligus menyajikan `frontend/index.html` dari route `/`.

## Start Command

Railway akan membaca `railway.json` dan menjalankan:

```bash
python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port $PORT
```

## Environment Variable Opsional

Untuk satu node demo:

```env
P2P_DISCOVERY=0
P2P_NODE_ID=node-railway-1
```

Untuk banyak node/service Railway:

```env
P2P_DISCOVERY=0
P2P_NODE_ID=node-railway-1
P2P_PEERS=https://node-railway-2.up.railway.app,https://node-railway-3.up.railway.app
```

`P2P_NODE_URL` tidak wajib jika service sudah punya public domain Railway, karena aplikasi otomatis membaca `RAILWAY_PUBLIC_DOMAIN`.

## Storage

Railway filesystem bawaan bisa berubah saat redeploy. Untuk demo masih cukup. Jika file ZIP, chunk, dan ledger harus tahan lama, tambahkan Railway Volume lalu set:

```env
P2P_STORAGE_DIR=/data
```
