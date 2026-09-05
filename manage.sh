#!/bin/bash
# Bot management script
# Usage: bash manage.sh [start|stop|restart|logs|status]

ACTION=${1:-status}

case $ACTION in
    start)
        echo "Starting bot..."
        docker-compose up -d
        echo "Bot started!"
        ;;
    stop)
        echo "Stopping bot..."
        docker-compose down
        echo "Bot stopped!"
        ;;
    restart)
        echo "Restarting bot..."
        docker-compose down
        docker-compose up -d
        echo "Bot restarted!"
        ;;
    logs)
        docker-compose logs -f --tail=50
        ;;
    status)
        echo "========================================="
        echo "  Bot Status"
        echo "========================================="
        docker-compose ps
        echo ""
        echo "Last 10 log lines:"
        docker-compose logs --tail=10
        ;;
    update)
        echo "Updating bot..."
        docker-compose down
        git pull
        docker-compose build --no-cache
        docker-compose up -d
        echo "Bot updated!"
        ;;
    *)
        echo "Usage: bash manage.sh [start|stop|restart|logs|status|update]"
        ;;
esac
