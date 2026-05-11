# Unleashed Proxy Server

A lightweight Flask proxy that sits between Claude.ai and the Unleashed API,
handling authentication and CORS so your inventory dashboard works seamlessly.

## Deploy to Render (free, ~5 minutes)

### Step 1 — Put this code on GitHub

1. Go to https://github.com/new and create a new **private** repository called `unleashed-proxy`
2. Upload all files from this folder (app.py, requirements.txt, Procfile, README.md)
   - Click "uploading an existing file" on the repo page
   - Drag and drop all four files
   - Click "Commit changes"

### Step 2 — Deploy on Render

1. Go to https://render.com and sign up (free, no credit card)
2. Click **New → Web Service**
3. Connect your GitHub account and select the `unleashed-proxy` repo
4. Fill in the settings:
   - **Name**: unleashed-proxy (or anything you like)
   - **Region**: Singapore (closest to NZ)
   - **Branch**: main
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free
5. Click **Advanced** and add these environment variables:
   - `UNLEASHED_API_ID` = `4ad4fb7c-a30a-443e-9299-d338c84c6b2c`
   - `UNLEASHED_API_KEY` = `cpgb7TllT7EWD36AlUrTOQXUBdnzs6GYdpKQW7qwOfT3j0nDPwhDcq94GaDWj4odtzpoTEr8tgm0ixqvmw==`
   - `UNLEASHED_CLIENT_TYPE` = `marathonproductslimited/api`
6. Click **Create Web Service**

Render will build and deploy in about 2 minutes. You'll get a URL like:
`https://unleashed-proxy.onrender.com`

### Step 3 — Test it

Open this in your browser (replace with your actual Render URL):
```
https://unleashed-proxy.onrender.com/health
```
You should see: `{"status": "ok"}`

Then test the stock endpoint:
```
https://unleashed-proxy.onrender.com/stock-on-hand
```

### Step 4 — Tell Claude your proxy URL

Once deployed, come back to Claude and say:
"My proxy is live at https://unleashed-proxy.onrender.com"

Claude will then build the live inventory dashboard connected through your proxy.

## Available endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Check the proxy is running |
| `GET /stock-on-hand` | All products with stock quantities |
| `GET /stock-on-hand/{guid}` | Single product stock |
| `GET /products` | All products |

## Security notes

- Your API credentials are stored as environment variables in Render, never in code
- The proxy only allows GET requests (read-only)
- CORS is enabled so Claude.ai widgets can call it directly
- Consider adding a `PROXY_SECRET` env var and checking it as a bearer token if you want extra security
