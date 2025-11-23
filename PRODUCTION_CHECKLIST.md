# Production Deployment Checklist

## ✅ Pre-Deployment Checklist

### Configuration
- [ ] Created `.env` file from `.env.dist`
- [ ] Added `BOT_TOKEN` to `.env`
- [ ] Verified `MONGODB_URL` (optional, auto-configured for Docker)

### Dependencies
- [ ] All dependencies listed in `requirements/base.txt`
- [ ] Production requirements verified (`requirements/production.txt`)

### Code Quality
- [ ] No unused imports or files
- [ ] All tests pass: `pytest src/tests/ -v`
- [ ] No linter errors
- [ ] Code compiles: `python -m py_compile bot.py`

### Docker
- [ ] Dockerfile builds successfully
- [ ] Docker Compose configuration verified
- [ ] `.dockerignore` excludes unnecessary files

### Documentation
- [ ] README.md updated with current features
- [ ] DOCKER_SETUP.md contains deployment instructions
- [ ] DEPLOYMENT.md contains production guide

## 🚀 Deployment Steps

1. **Prepare environment:**
   ```bash
   cp .env.dist .env
   # Edit .env and add BOT_TOKEN
   ```

2. **Build and start:**
   ```bash
   docker-compose up -d --build
   ```

3. **Verify:**
   ```bash
   docker-compose ps
   docker-compose logs -f bot-app
   ```

4. **Test bot:**
   - Send `/start` to bot
   - Subscribe to a queue
   - Check notifications settings
   - Verify schedule checking works

## 📊 Monitoring

- Check logs regularly: `docker-compose logs -f bot-app`
- Monitor MongoDB: `docker-compose logs mongodb`
- Check resource usage: `docker stats`

## 🔄 Updates

When updating:
1. Pull latest code
2. Rebuild: `docker-compose up -d --build bot-app`
3. Check logs: `docker-compose logs -f bot-app`
4. Verify bot responds correctly

## ⚠️ Important Notes

- **Never commit `.env` file** - it contains sensitive tokens
- **Backup MongoDB** regularly
- **Monitor logs** for errors
- **Keep dependencies updated** for security

