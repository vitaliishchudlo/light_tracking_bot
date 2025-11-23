# Deployment Guide

## Production Deployment

### Prerequisites

- Docker and Docker Compose installed
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Server with at least 512MB RAM

### Quick Start

1. **Clone and configure:**
   ```bash
   git clone <repository-url>
   cd light_tracking_bot
   cp .env.dist .env
   # Edit .env and add your BOT_TOKEN
   ```

2. **Start services:**
   ```bash
   docker-compose up -d
   ```

3. **Check logs:**
   ```bash
   docker-compose logs -f bot-app
   ```

### Environment Variables

Create `.env` file with:

```env
BOT_TOKEN=your_bot_token_here
MONGODB_URL=mongodb://mongodb:27017/  # Optional, auto-configured for Docker
```

### Monitoring

**Check bot status:**
```bash
docker-compose ps
docker-compose logs bot-app --tail=50
```

**Check MongoDB:**
```bash
docker-compose logs mongodb --tail=50
docker exec -it svitlo-mongodb mongosh --eval "db.adminCommand('ping')"
```

### Updates

**Update bot code:**
```bash
git pull
docker-compose up -d --build bot-app
```

**View logs after update:**
```bash
docker-compose logs -f bot-app
```

### Backup

**Backup MongoDB:**
```bash
docker exec svitlo-mongodb mongodump --out /data/backup
docker cp svitlo-mongodb:/data/backup ./backup
```

**Restore MongoDB:**
```bash
docker cp ./backup svitlo-mongodb:/data/backup
docker exec svitlo-mongodb mongorestore /data/backup
```

### Troubleshooting

**Bot not starting:**
- Check `.env` file exists and has `BOT_TOKEN`
- Check MongoDB is running: `docker-compose ps`
- Check logs: `docker-compose logs bot-app`

**MongoDB connection issues:**
- Verify MongoDB health: `docker-compose ps mongodb`
- Check MongoDB logs: `docker-compose logs mongodb`
- Verify network: `docker network ls`

**Restart services:**
```bash
docker-compose restart bot-app
docker-compose restart mongodb
```

### Production Recommendations

1. **Use reverse proxy** (nginx/traefik) for additional security
2. **Set up log rotation** for Docker logs
3. **Monitor resource usage** (CPU, RAM, disk)
4. **Regular backups** of MongoDB data
5. **Update dependencies** regularly
6. **Monitor bot uptime** with health checks

### Health Checks

The bot includes automatic health checks:
- MongoDB connection verification on startup
- Schedule checker runs every minute
- Error logging for debugging

### Scaling

For high load, consider:
- Running MongoDB on separate server
- Using MongoDB replica set
- Adding monitoring (Prometheus, Grafana)
- Setting up alerts for errors

