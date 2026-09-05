#!/bin/bash
# Deploy script for VPS (run once)
# Usage: bash deploy.sh

echo "========================================="
echo "  Crypto Bot - Deploy to VPS"
echo "========================================="

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install docker-compose
sudo apt install docker-compose -y

# Clone project (or upload files via scp)
echo ""
echo "========================================="
echo "  Next steps:"
echo "========================================="
echo "1. Upload project files to VPS:"
echo "   scp -r 'forecasts bot/' user@YOUR_VPS_IP:/home/user/crypto-bot"
echo ""
echo "2. SSH into VPS:"
echo "   ssh user@YOUR_VPS_IP"
echo ""
echo "3. Go to project folder:"
echo "   cd ~/crypto-bot"
echo ""
echo "4. Create .env file with your BOT_TOKEN:"
echo "   nano .env"
echo ""
echo "5. Start bot:"
echo "   docker-compose up -d"
echo ""
echo "6. View logs:"
echo "   docker-compose logs -f"
echo ""
echo "7. Stop bot:"
echo "   docker-compose down"
echo "========================================="
