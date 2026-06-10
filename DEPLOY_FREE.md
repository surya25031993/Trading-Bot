# Deploying to Hugging Face Spaces (free, keeps ML, no credit card)

## What you'll get
A live URL like `https://<your-username>-algobot-india.hf.space` that:
- ✅ Costs ₹0/month forever
- ✅ Runs your full ML stack (xgboost + scikit-learn + scipy)
- ✅ Has 16 GB RAM, 2 vCPU — comfortable for cold ML starts
- ✅ Never sleeps (unlike Render free tier)
- ✅ Single container — both backend and frontend served together

## Step 1 — Create a free MongoDB Atlas database (5 min)
1. Go to https://www.mongodb.com/cloud/atlas/register and sign up (Google login is fine).
2. Click **"Build a Database"** → choose the **FREE** tier (M0 cluster).
3. Provider/region: pick AWS / Mumbai (`ap-south-1`) for lowest latency from India.
4. Click **Create**.
5. Set up access:
   - **Database User**: create a username/password (write it down).
   - **IP Access List**: click **"Allow access from anywhere"** (0.0.0.0/0). This is fine for now.
6. After cluster is ready (~2 min), click **Connect** → **Drivers** → copy the connection string. It looks like:
   ```
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
7. Replace `<password>` with your actual password and append `&appName=algobot` at the end. **Save this — you'll paste it in Step 3.**

## Step 2 — Create a free Hugging Face account (2 min)
1. Go to https://huggingface.co/join and sign up (Google login works).
2. Verify your email.
3. Note your username — your Space URL depends on it.

## Step 3 — Create a new Space (5 min)
1. Go to https://huggingface.co/new-space
2. Fill in:
   - **Owner**: your username
   - **Space name**: `algobot-india`
   - **License**: MIT
   - **Select SDK**: choose **Docker** → **Blank**
   - **Hardware**: CPU basic — FREE (16 GB RAM, 2 vCPU)
   - **Visibility**: Public (or Private — you can switch later)
3. Click **Create Space**.

## Step 4 — Push the code to your new Space (10 min)
You have two ways:

### Way A — Through the HF web UI (no terminal needed)
1. In your new Space, click **Files** → **+ Add file** → **Upload files**
2. **Drag all the files** from this `/app` folder (Dockerfile, README.md, .dockerignore, backend/, frontend/)
3. Commit. HF starts building automatically.

### Way B — Through git (faster if you know git)
```bash
# From your local machine after cloning the Emergent repo:
cd /path/to/repo
git remote add hf https://huggingface.co/spaces/<your-username>/algobot-india
git push hf main
```
You'll be prompted for an HF access token — generate one at https://huggingface.co/settings/tokens (scope: write).

## Step 5 — Set the environment variables in the Space (3 min)
1. In your Space, click **Settings** → **Variables and secrets**.
2. Add these **as Secrets** (so they don't show publicly):

| Name | Value |
|---|---|
| `MONGO_URL` | the connection string from Step 1.7 |
| `DB_NAME` | `algo_ml_app` |
| `EMERGENT_LLM_KEY` | `sk-emergent-28dEb4a6c9052658a9` |
| `CORS_ORIGINS` | `*` |
| `FYERS_APP_ID` | `OJB8SDCIDS-100` (or your new `-200` once approved) |
| `FYERS_SECRET_KEY` | `8CNG5GHCZK` (or your new one) |
| `FYERS_REDIRECT_URL` | `https://<your-username>-algobot-india.hf.space/api/fyers/callback` |

3. Click **Restart Space**. Build takes ~10-15 min the first time (downloading ML libs).

## Step 6 — Update Fyers redirect URL (2 min)
The redirect URL changed (`hf.space` instead of `preview.emergentagent.com`). Update Fyers:
1. https://fyers.in/web/api-dashboard/user-apps → edit your app
2. Change **Redirect URL** to:
   ```
   https://<your-username>-algobot-india.hf.space/api/fyers/callback
   ```
3. Save.

## Step 7 — Done! Visit your live URL
```
https://<your-username>-algobot-india.hf.space
```
Bookmark it / share it / install as PWA.

## Troubleshooting
- **Build fails on yfinance**: the curl_cffi build sometimes needs more RAM. Click Settings → "Restart" — second build usually works.
- **App returns 500 on `/api/`**: check Settings → Variables. Likely `MONGO_URL` is wrong.
- **Fyers login redirects to error**: redirect URL in HF doesn't match what's saved on Fyers dashboard. Compare character-for-character.
- **`/mlpredict` is slow (~60 s first time)**: that's xgboost training models on cold start. After the first call it's cached for 5 min.

## Cost summary
| Service | Tier | Cost |
|---|---|---|
| Hugging Face Spaces | CPU Basic 16 GB | **₹0/month** |
| MongoDB Atlas | M0 (512 MB) | **₹0/month** |
| **TOTAL** | | **₹0/month** |
