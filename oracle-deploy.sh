#!/bin/bash
# Oracle Cloud Free Tier - Deploy Crypto Bot
# Run this AFTER creating VM instance on Oracle Cloud

echo "========================================="
echo "  Oracle Cloud - Crypto Bot Deploy"
echo "========================================="

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install docker-compose
sudo apt install docker-compose -y

# Enable Docker to start on boot
sudo systemctl enable docker

echo "========================================="
echo "  Docker installed!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Upload project files:"
echo "   scp -r 'forecasts bot/' ubuntu@YOUR_IP:/home/ubuntu/crypto-bot"
echo ""
echo "2. SSH into server:"
echo "   ssh ubuntu@YOUR_IP"
echo ""
echo "3. cd ~/crypto-bot"
echo "4. nano .env  (add BOT_TOKEN)"
echo "5. docker-compose up -d"
echo "6. bash manage.sh logs"
echo "========================================="
