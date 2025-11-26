# Netlify Deployment Guide

This guide will help you deploy your **frontend** to Netlify and set up your **backend** on a compatible hosting service.

## Important Note

**Netlify is for frontend only!** Your FastAPI backend needs to be deployed separately on a service that supports Python applications (like Railway, Render, Fly.io, or Heroku).

## Part 1: Deploy Frontend to Netlify

### Option A: Deploy via Netlify Dashboard (Recommended)

1. **Build your frontend locally first (to test):**
   ```bash
   cd frontend
   npm install
   npm run build
   ```

2. **Go to [Netlify](https://app.netlify.com) and sign in**

3. **Add a new site:**
   - Click "Add new site" → "Import an existing project"
   - Connect to GitHub and select your repository: `Sirf-Alfaaz/Lexi_AI`
   - Set build settings:
     - **Base directory:** `frontend`
     - **Build command:** `npm run build`
     - **Publish directory:** `frontend/dist`

4. **Set Environment Variables:**
   - Go to Site settings → Environment variables
   - Add: `VITE_API_URL` = `https://your-backend-url.com`
     - Replace with your actual backend URL (from Part 2)

5. **Deploy!**
   - Click "Deploy site"
   - Netlify will build and deploy your frontend

### Option B: Deploy via Netlify CLI

1. **Install Netlify CLI:**
   ```bash
   npm install -g netlify-cli
   ```

2. **Login to Netlify:**
   ```bash
   netlify login
   ```

3. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

4. **Initialize Netlify:**
   ```bash
   netlify init
   ```
   - Choose "Create & configure a new site"
   - Follow the prompts

5. **Set environment variable:**
   ```bash
   netlify env:set VITE_API_URL https://your-backend-url.com
   ```

6. **Deploy:**
   ```bash
   netlify deploy --prod
   ```

## Part 2: Deploy Backend with Docker (OCR Ready)

PyMuPDF’s OCR features require native libraries (Tesseract, Leptonica, etc.). The repo
includes an OCR-ready Dockerfile at `backend/Dockerfile`. You can run it locally or
deploy it on Render / Railway / Fly by choosing a **Docker** service.

### Local smoke test
```bash
cd backend
docker build -t legal-backend .
docker run --env-file .env -p 8000:8000 legal-backend
```

### Option 1: Render (Docker)

1. **Go to [Render](https://render.com)**
2. **New Web Service → Build & Deploy from a Git repository**
3. When prompted, choose **Docker** and set:
   - **Root directory:** `backend`
   - **Dockerfile path:** `backend/Dockerfile`
   - **Auto deploy:** optional
4. **Add environment variables** (see list below). At minimum:
   - `MONGODB_URL`, `MONGODB_DB_NAME`
   - `GEMINI_API_KEY`
   - `SECRET_KEY`
   - `EMAIL_*` settings if email is enabled
   - `CORS_ORIGINS` (comma-separated list including Netlify URL)
5. Render automatically sets `PORT`. The Dockerfile already runs `uvicorn` on `$PORT`.
6. Deploy and copy the resulting URL (e.g., `https://your-backend.onrender.com`).
7. Update Netlify `VITE_API_URL` to this URL and redeploy the frontend.

### Option 2: Railway (Docker)

Railway also supports Docker services (Starter plan or higher).

1. **Go to [Railway](https://railway.app)** → **New Project → Deploy from Repo**
2. In the service settings, switch the **builder** to **Dockerfile** and set:
   - **Root directory:** `backend`
   - **Dockerfile:** `backend/Dockerfile`
3. Configure the same environment variables as above.
4. Railway exposes `PORT`; no extra command needed.
5. Update Netlify `VITE_API_URL` after the service is live.

> **Note:** If you must use a buildpack-based deployment (no Docker), you will need to
> install Tesseract system packages manually, which is only available on paid tiers and
> increases build times. Docker is the recommended path.

### Option 3: Fly.io (Docker)

1. **Install Fly CLI:**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login:**
   ```bash
   fly auth login
   ```

3. **Create app from backend directory:**
   ```bash
   cd backend
   fly launch --dockerfile Dockerfile
   ```

4. **Set environment variables / secrets:**
   ```bash
   fly secrets set MONGODB_URL=... GEMINI_API_KEY=... CORS_ORIGINS=...
   ```

5. **Deploy:**
   ```bash
   fly deploy
   ```

### Option 3: Fly.io

1. **Install Fly CLI:**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login:**
   ```bash
   fly auth login
   ```

3. **Create app:**
   ```bash
   cd backend
   fly launch
   ```

4. **Set environment variables:**
   ```bash
   fly secrets set MONGODB_URL=your_url
   fly secrets set GEMINI_API_KEY=your_key
   # ... etc
   ```

5. **Deploy:**
   ```bash
   fly deploy
   ```

### Option 4: Heroku (Container Registry)

Heroku’s free tier is gone, but if you have access you can push the Docker image:

```bash
cd backend
heroku login
heroku container:login
heroku create your-backend
heroku container:push web --app your-backend
heroku container:release web --app your-backend
```

Set the same environment variables via `heroku config:set ...`.

## Part 3: Update CORS in Backend

After deploying your backend, update CORS settings in `backend/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Local dev
        "https://your-netlify-app.netlify.app",  # Netlify URL
        "https://your-custom-domain.com"  # Custom domain (if any)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Part 4: Final Steps

1. **Update Netlify environment variable** with your backend URL
2. **Redeploy Netlify** (or it will auto-deploy on next push)
3. **Test your deployed app!**

## Environment Variables Summary

### Frontend (Netlify)
- `VITE_API_URL` - Your backend URL (e.g., `https://your-backend.railway.app`)

### Backend (Railway/Render/etc.)
- `MONGODB_URL` - MongoDB connection string
- `MONGODB_DB_NAME` - Database name
- `GEMINI_API_KEY` - Google Gemini API key
- `SECRET_KEY` - Override JWT secret
- `JWT_EXPIRE_MINUTES` - Token expiration (default: 60)
- `CORS_ORIGINS` - Comma-separated list of allowed origins (Netlify URL, custom domains)
- `EMAIL_ENABLED` - Enable email (true/false)
- `EMAIL_SERVICE` - Email service (gmail, etc.)
- `EMAIL_FROM` - Sender email
- `EMAIL_PASSWORD` - Email password
- `EMAIL_SMTP_SERVER` - SMTP server
- `EMAIL_SMTP_PORT` - SMTP port
- `EMAIL_USE_TLS` - Use TLS (true/false)

## Troubleshooting

### Frontend can't connect to backend
- Check `VITE_API_URL` is set correctly in Netlify
- Verify backend is running and accessible
- Check CORS settings in backend

### Build fails on Netlify
- Check build logs in Netlify dashboard
- Ensure `package.json` has correct build script
- Verify Node version (should be 18+)

### Backend deployment issues
- Check logs in your hosting platform
- Verify all environment variables are set
- Ensure MongoDB connection string is correct
- Check if port is set correctly (`$PORT` for most platforms)

## Quick Reference

- **Frontend URL:** `https://your-app.netlify.app`
- **Backend URL:** `https://your-backend.railway.app` (or your hosting service)
- **GitHub Repo:** `https://github.com/Sirf-Alfaaz/Lexi_AI`

## Need Help?

- [Netlify Docs](https://docs.netlify.com/)
- [Railway Docs](https://docs.railway.app/)
- [Render Docs](https://render.com/docs)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)


