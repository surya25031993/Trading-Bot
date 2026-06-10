# Deploying to AWS EC2 (cheapest reliable AWS path for an ML app)

## ⚠ Honest cost up-front

| Item | Cost |
|---|---|
| **t3.small instance** (2 GB RAM, 2 vCPU) — needed for xgboost | ~$15/month (~₹1,250/month) |
| 30 GB gp3 storage | ~$2.40/month |
| Data transfer (10 GB out) | ~$0.90/month |
| **Total** | **~$18/month (~₹1,500/month)** |

Free tier (t2.micro) **will not work** — only 1 GB RAM, ML cold start needs ~600 MB.

You will need to **add a credit card** to AWS to sign up, even though you'll get the free tier on other services.

---

## Step 1 — Create AWS account (10 min)
1. Go to https://aws.amazon.com/free/ → click **Create a Free Account**
2. Email, password, account name
3. **Add credit card** (mandatory — AWS will ₹2 verify and refund)
4. Choose **Basic Support — Free**
5. Verify phone via SMS

## Step 2 — Launch an EC2 instance (15 min)
1. Open https://console.aws.amazon.com/ec2 → Choose region **Mumbai (ap-south-1)**
2. Click **Launch Instance**
3. Fill in:
   - **Name**: `algobot-india`
   - **AMI**: **Ubuntu Server 22.04 LTS** (free tier eligible)
   - **Instance type**: **`t3.small`** (NOT t2.micro — too small for ML)
   - **Key pair**: click **Create new key pair**, name it `algobot`, type RSA, format `.pem`, download it (you only get to do this once — save the file!)
   - **Network settings** → **Edit**:
     - Allow SSH (port 22) from `My IP`
     - Allow HTTP (port 80) from `Anywhere`
     - Allow HTTPS (port 443) from `Anywhere`
     - **Add custom rule**: TCP port `7860` from `Anywhere` (the app port)
   - **Storage**: 30 GB gp3 (free tier allows up to 30 GB)
4. Click **Launch Instance**
5. After ~30 sec, copy the **Public IPv4 address** (e.g. `13.232.45.67`)

## Step 3 — SSH into the instance (5 min)
On your laptop:
```bash
chmod 400 algobot.pem
ssh -i algobot.pem ubuntu@<your-public-ip>
```
Type `yes` when asked about authenticity.

## Step 4 — Install Docker (3 min)
On the instance:
```bash
sudo apt-get update
sudo apt-get install -y docker.io git
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
exit
```
SSH back in (so the docker group takes effect):
```bash
ssh -i algobot.pem ubuntu@<your-public-ip>
```

## Step 5 — Pull the code (5 min)

### Option A — from your repo (if you've pushed to GitHub)
```bash
git clone https://github.com/<your-username>/<your-repo>.git algobot
cd algobot
```

### Option B — upload from your laptop (no GitHub needed)
On your **laptop**, in the folder containing `/app`:
```bash
scp -i algobot.pem -r ./app ubuntu@<your-public-ip>:/home/ubuntu/algobot
```
Then on the instance:
```bash
cd /home/ubuntu/algobot
```

## Step 6 — Set env vars
```bash
cat > .env <<EOF
MONGO_URL=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
DB_NAME=algo_ml_app
EMERGENT_LLM_KEY=sk-emergent-28dEb4a6c9052658a9
CORS_ORIGINS=*
FYERS_APP_ID=OJB8SDCIDS-100
FYERS_SECRET_KEY=8CNG5GHCZK
FYERS_REDIRECT_URL=http://<your-public-ip>:7860/api/fyers/callback
EOF
```

You still need a MongoDB — sign up for **MongoDB Atlas free tier** (see Step 1 in `DEPLOY_FREE.md`) and paste the connection string above.

## Step 7 — Build and run the Docker image (~15 min)
```bash
docker build -t algobot .
docker run -d --name algobot --restart=always \
  -p 7860:7860 \
  --env-file .env \
  -e PORT=7860 \
  algobot
```

## Step 8 — Test it
```bash
curl http://localhost:7860/api/
# should return {"message":"Algo Trading Bot API","status":"ok"}
```

Then in your browser:
```
http://<your-public-ip>:7860
```

## Step 9 — Update Fyers redirect URL
Go to https://fyers.in/web/api-dashboard/user-apps → your app → set redirect URL to:
```
http://<your-public-ip>:7860/api/fyers/callback
```

## Step 10 — (Optional) Add a domain + HTTPS
- Buy a domain (Namecheap ~$10/year)
- Point an A record to `<your-public-ip>`
- Install Caddy on the instance for auto-HTTPS:
  ```bash
  sudo apt install -y caddy
  echo "yourdomain.com {
      reverse_proxy localhost:7860
  }" | sudo tee /etc/caddy/Caddyfile
  sudo systemctl restart caddy
  ```

---

## Troubleshooting
| Symptom | Fix |
|---|---|
| `docker build` runs out of memory | t3.small is barely enough — close other Docker builds, or move to t3.medium ($30/mo) |
| Site won't load on `:7860` | Check Security Group inbound rules include port 7860 from 0.0.0.0/0 |
| ML Predict 502s after a few minutes | Container OOM-killed. Restart: `docker restart algobot`. Consider t3.medium |
| Fyers redirect fails | Compare URLs character-for-character |
| Instance shuts down on me | t3.small uses **unlimited** burst credits which can bill higher. Use `t3a.small` (AMD, slightly cheaper) for steady workloads |

## Cost saving
- **Stop the instance when not using it** (e.g. nights / weekends) → only pay for storage. Right-click the instance → Stop.
- **Use AWS Cost Explorer** to set a billing alarm at $25/month so you don't get surprised.
