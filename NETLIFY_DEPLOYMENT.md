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

## Part 2: Deploy Backend (Choose One)

### Option 1: Railway (Recommended - Easiest)

1. **Go to [Railway](https://railway.app)**
2. **Create new project** → "Deploy from GitHub repo"
3. **Select your repository**
4. **Add environment variables:**
   - `MONGODB_URL` - Your MongoDB connection string
   - `MONGODB_DB_NAME` - Your database name
   - `GEMINI_API_KEY` - Your Gemini API key
   - `JWT_EXPIRE_MINUTES` - 60
   - `EMAIL_ENABLED` - false (or true if you set up email)
5. **Railway will auto-detect Python and install dependencies**
6. **Set start command:** `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
7. **Get your backend URL** (e.g., `https://your-app.railway.app`)
8. **Update Netlify environment variable** `VITE_API_URL` with this URL

### Option 2: Render

1. **Go to [Render](https://render.com)**
2. **Create new Web Service**
3. **Connect GitHub repository**
4. **Configure:**
   - **Name:** `ai-legal-backend`
   - **Environment:** Python 3
   - **Build Command:** `cd backend && pip install -r requirements.txt`
   - **Start Command:** `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Add environment variables** (same as Railway)
6. **Deploy and get URL**

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

### Option 4: Heroku

1. **Install Heroku CLI**
2. **Login:** `heroku login`
3. **Create app:** `heroku create your-app-name`
4. **Set buildpacks:**
   ```bash
   heroku buildpacks:set heroku/python
   ```
5. **Create `Procfile` in backend:**
   ```
   web: uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
6. **Set environment variables:**
   ```bash
   heroku config:set MONGODB_URL=your_url
   # ... etc
   ```
7. **Deploy:** `git push heroku main`

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
- `JWT_EXPIRE_MINUTES` - Token expiration (default: 60)
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

