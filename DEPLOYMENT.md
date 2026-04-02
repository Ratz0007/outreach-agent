# Deployment Guide: Launching Your Career Agent for Free

Follow this guide to launch your platform publicly so job seekers around the world can use it with their own API keys.

## 1. Database: Neon.tech (PostgreSQL)

1. Sign up at [Neon.tech](https://neon.tech).
2. Create a new project named `outreach-agent`.
3. Copy the **Connection String** (it starts with `postgresql://`).
4. Save this as `DATABASE_URL` for the next steps.

## 2. Backend: Railway.app

1. Sign up at [Railway.app](https://railway.app).
2. Click **New Project** > **Deploy from GitHub repo**.
3. Select this repository.
4. Go to **Variables** and add:
   - `DATABASE_URL`: (Paste your Neon connection string here)
   - `PORT`: `8080`
   - `ANTHROPIC_API_KEY`: (Your personal master key for the Coach)
5. Go to **Settings** > **Public Networking** and click **Generate Domain**.
6. Copy this URL (e.g., `outreach-production.up.railway.app`). This is your `NEXT_PUBLIC_API_URL`.

## 3. Frontend: Vercel

1. Sign up at [Vercel.com](https://vercel.com).
2. Click **Add New** > **Project**.
3. Import this repository.
4. Set the **Root Directory** to `frontend`.
5. Add **Environment Variables**:
   - `NEXT_PUBLIC_API_URL`: (Paste your Railway URL here)
6. Click **Deploy**.

---

## Technical Architecture

> [!TIP]
> **BYOK (Bring Your Own Key)**: The platform is designed such that users enter their own keys in the Onboarding Wizard. These keys are stored in the `users.settings` JSON column in PostgreSQL, so the agent runs using their credits, not yours!

> [!IMPORTANT]
> **CORS**: The backend is already configured to allow all origins via `CORSMiddleware`, but for production, you should update `src/dashboard/app.py` to only allow your Vercel domain.
