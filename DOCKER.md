# Docker Deployment Guide

This guide explains how to build, run, and manage the Image Frames API using Docker and Docker Compose.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Building the Image](#building-the-image)
- [Running with Docker Compose](#running-with-docker-compose)
- [Running Standalone Container](#running-standalone-container)
- [Data Ingestion](#data-ingestion)
- [Monitoring and Logs](#monitoring-and-logs)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## Quick Start

**One command to rule them all:**

```bash
docker compose up
```

Access the API at: http://localhost:8000/docs

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose v2.0+
- At least 1GB free disk space
- (Optional) CSV data file for ingestion

Verify installation:

```bash
docker --version
docker compose version
```

## Building the Image

### Multi-stage Build

The Dockerfile uses a multi-stage build for optimal image size:

1. **Builder stage**: Installs dependencies
2. **Runtime stage**: Creates lean production image (~200MB)

```bash
# Build the image
docker build -t aiq-depth-frames-api:latest .

# Build with custom tag
docker build -t aiq-depth-frames-api:v1.0.0 .

# Build without cache (force rebuild)
docker build --no-cache -t aiq-depth-frames-api:latest .
```

### Image Size Optimization

The multi-stage build reduces image size from ~1GB to ~200MB:

- Uses `python:3.11-slim` base image
- Removes build dependencies in final stage
- Only includes runtime dependencies

## Running with Docker Compose

### Start Services

```bash
# Start in foreground (see logs)
docker compose up

# Start in detached mode (background)
docker compose up -d

# Start with rebuild
docker compose up --build

# Start specific service
docker compose up api
```

### Stop Services

```bash
# Stop services (keep containers)
docker compose stop

# Stop and remove containers
docker compose down

# Stop and remove containers + volumes
docker compose down -v

# Stop and remove everything including images
docker compose down --rmi all -v
```

### View Status

```bash
# List running services
docker compose ps

# View logs
docker compose logs

# Follow logs in real-time
docker compose logs -f

# View logs for specific service
docker compose logs -f api

# View last 100 lines
docker compose logs --tail=100 api
```

## Running Standalone Container

### Basic Run

```bash
# Run with port mapping
docker run -p 8000:8000 aiq-depth-frames-api:latest

# Run with volume mount for data persistence
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  aiq-depth-frames-api:latest

# Run in detached mode
docker run -d -p 8000:8000 \
  --name aiq-depth-frames-api \
  -v $(pwd)/data:/app/data \
  aiq-depth-frames-api:latest
```

### With Environment Variables

```bash
# Pass environment variables
docker run -p 8000:8000 \
  -e LOG_LEVEL=debug \
  -e ADMIN_TOKEN=my-secure-token \
  -v $(pwd)/data:/app/data \
  aiq-depth-frames-api:latest

# Use .env file
docker run -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  aiq-depth-frames-api:latest
```

### Interactive Shell

```bash
# Enter container shell
docker run -it --rm \
  -v $(pwd)/data:/app/data \
  aiq-depth-frames-api:latest \
  /bin/bash

# With docker compose
docker compose exec api /bin/bash
```

## Data Ingestion

### Using Docker Compose

```bash
# Create sample CSV data
mkdir -p data
echo "depth,0,1,2,3" > data/sample.csv
echo "100.0,50,100,150,200" >> data/sample.csv

# Run ingestion inside container
docker compose exec api python -m app.cli.ingest /app/data/sample.csv

# With custom chunk size
docker compose exec api python -m app.cli.ingest /app/data/sample.csv --chunk-size 1000

# Check progress
docker compose logs -f api
```

### Using Standalone Container

```bash
# Run ingestion as one-off command
docker run --rm \
  -v $(pwd)/data:/app/data \
  aiq-depth-frames-api:latest \
  python -m app.cli.ingest /app/data/sample.csv

# Interactive ingestion
docker run -it --rm \
  -v $(pwd)/data:/app/data \
  aiq-depth-frames-api:latest \
  /bin/bash -c "python -m app.cli.ingest /app/data/sample.csv"
```

### Verify Ingestion

```bash
# Check database file was created
ls -lh data/frames.db

# Query via API
curl http://localhost:8000/frames?limit=5

# Check frame count
curl http://localhost:8000/frames | jq '.metadata.total'
```

## Monitoring and Logs

### Health Checks

```bash
# Check container health
docker compose ps

# Manual health check
curl http://localhost:8000/health

# Detailed health check
curl http://localhost:8000/health | jq
```

Expected response:

```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-11-06T10:30:00Z"
}
```

### Application Logs

```bash
# View all logs
docker compose logs

# Follow logs (Ctrl+C to exit)
docker compose logs -f

# Filter by log level
docker compose logs | grep ERROR
docker compose logs | grep WARNING

# Export logs to file
docker compose logs > logs/container.log

# View structured logs
docker compose logs api | jq -R 'fromjson? | select(.level == "ERROR")'
```

### Cache Statistics

```bash
# View cache performance
curl http://localhost:8000/cache/stats

# Clear caches (requires admin token)
curl -X DELETE http://localhost:8000/cache \
  -H "X-Admin-Token: your-admin-token"
```

### Resource Usage

```bash
# View resource consumption
docker stats aiq-depth-frames-api

# View all containers
docker stats

# One-time stats
docker stats --no-stream
```

## Configuration

### Environment Variables

Key environment variables (see `.env.example` for full list):

| Variable       | Description                | Default                                   |
| -------------- | -------------------------- | ----------------------------------------- |
| `HOST`         | Server bind address        | `0.0.0.0`                                 |
| `PORT`         | Server port                | `8000`                                    |
| `LOG_LEVEL`    | Logging level              | `info`                                    |
| `DATABASE_URL` | Database connection string | `sqlite+aiosqlite:////app/data/frames.db` |
| `ADMIN_TOKEN`  | Admin API token            | `changeme-secure-token-here`              |
| `WORKERS`      | Number of worker processes | `1`                                       |

### Volume Mounts

The container uses the following directories:

```yaml
volumes:
  - ./data:/app/data # Database and data files
  - ./sample_data:/app/sample_data:ro # Read-only CSV files
  - ./logs:/app/logs # Application logs (optional)
```

### Persistent Data

Data persists across container restarts using Docker volumes:

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect aiq-depth-frames-data

# Backup database
docker compose exec api cat /app/data/frames.db > backup/frames.db

# Restore database
docker compose cp backup/frames.db api:/app/data/frames.db
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
docker compose logs api

# Check container status
docker compose ps

# Verify image built successfully
docker images | grep aiq-depth-frames

# Rebuild from scratch
docker compose build --no-cache
docker compose up
```

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000  # Unix/Mac
netstat -ano | findstr :8000  # Windows

# Use different port
docker compose down
# Edit docker-compose.yml: ports: - "8001:8000"
docker compose up
```

### Database Issues

```bash
# Check database file exists
docker compose exec api ls -lh /app/data/

# Reset database (WARNING: deletes all data)
docker compose down -v
rm data/frames.db
docker compose up

# Verify database connection
docker compose exec api python -c "
from app.db import get_engine
import asyncio
async def test():
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute('SELECT 1')
        print('Database connected:', result.scalar())
asyncio.run(test())
"
```

### Permission Issues

```bash
# Fix data directory permissions
sudo chown -R 1000:1000 data/

# Run container as root (not recommended)
docker compose run --user root api /bin/bash
```

### Memory Issues

```bash
# Increase Docker memory limit
# Docker Desktop: Settings > Resources > Memory

# Check container memory usage
docker stats aiq-depth-frames-api

# Reduce worker count
# Edit .env: WORKERS=1
docker compose restart
```

### API Not Responding

```bash
# Check if container is running
docker compose ps

# Check health status
docker inspect --format='{{json .State.Health}}' aiq-depth-frames-api | jq

# Test connectivity
curl -v http://localhost:8000/health

# Enter container and test
docker compose exec api curl http://localhost:8000/health
```

### Rebuild Issues

```bash
# Clean build cache
docker builder prune

# Remove old images
docker image prune -a

# Complete cleanup
docker system prune -a --volumes
# WARNING: This removes all unused containers, images, and volumes!
```

## Production Deployment

### Security Checklist

- [ ] Change `ADMIN_TOKEN` to strong random value
- [ ] Use HTTPS with reverse proxy (nginx/traefik)
- [ ] Enable CORS restrictions
- [ ] Set `ENVIRONMENT=production`
- [ ] Configure log rotation
- [ ] Set resource limits
- [ ] Use secrets management (Docker Secrets/Kubernetes Secrets)
- [ ] Regular backups of database

### Performance Tuning

```yaml
# docker-compose.yml adjustments for production
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: 2G
    reservations:
      cpus: "1.0"
      memory: 1G
```

### Scaling

```bash
# Run multiple replicas
docker compose up --scale api=3

# With load balancer
docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

## Additional Commands

### Database Management

```bash
# Backup database
docker compose exec api sqlite3 /app/data/frames.db .dump > backup.sql

# Restore database
cat backup.sql | docker compose exec -T api sqlite3 /app/data/frames.db

# Compact database
docker compose exec api sqlite3 /app/data/frames.db VACUUM
```

### Testing

```bash
# Run tests in container
docker compose exec api pytest tests/

# Run specific test
docker compose exec api pytest tests/test_api.py -v

# Run with coverage
docker compose exec api pytest tests/ --cov=app --cov-report=html
```

### Updates and Maintenance

```bash
# Pull latest image
docker compose pull

# Rebuild and restart
docker compose up --build -d

# View image history
docker history aiq-depth-frames-api:latest

# Clean old images
docker image prune
```

## Support

For issues, check:

1. Container logs: `docker compose logs -f`
2. Health endpoint: `http://localhost:8000/health`
3. OpenAPI docs: `http://localhost:8000/docs`

## Summary

✅ **One command deployment**: `docker compose up`  
✅ **Multi-stage build**: Optimized image size (~200MB)  
✅ **Data persistence**: SQLite with volume mounts  
✅ **Health checks**: Built-in container health monitoring  
✅ **Ingestion support**: CLI available inside container  
✅ **Production ready**: Resource limits, logging, security

Access the API at: **http://localhost:8000/docs** 🚀
