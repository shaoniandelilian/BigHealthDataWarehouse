#!/bin/bash
set -euo pipefail

# ============================================================
# 构建并运行 laife 非 GPU 服务 Docker 测试
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  Laife 非 GPU 部署 Docker 测试"
echo "=========================================="
echo ""

# 检查必要目录
if [ ! -d "laife-ai" ]; then
  echo "[ERROR] laife-ai 源码目录不存在"
  exit 1
fi
if [ ! -d "realtime_rag_pipeline" ]; then
  echo "[ERROR] realtime_rag_pipeline 源码目录不存在"
  exit 1
fi
if [ ! -d "deploy-bundle" ]; then
  echo "[ERROR] deploy-bundle 目录不存在"
  exit 1
fi

echo "[1/3] 构建 Docker 镜像..."
echo "  这可能需要 5-15 分钟（安装 Python 依赖）..."
docker compose -f docker-test/docker-compose.yml build --no-cache laife-app 2>&1 | tail -20

echo ""
echo "[2/3] 启动中间件（MongoDB + PostgreSQL）..."
docker compose -f docker-test/docker-compose.yml up -d mongodb postgres
echo "  等待中间件就绪..."
sleep 10

echo ""
echo "[3/3] 启动应用容器并运行测试..."
docker compose -f docker-test/docker-compose.yml up laife-app 2>&1

EXIT_CODE=$?

echo ""
echo "=========================================="
echo "  测试完成 (exit=$EXIT_CODE)"
echo "=========================================="

if [ $EXIT_CODE -eq 0 ]; then
  echo ""
  echo "✅ 所有非 GPU 服务部署验证通过！"
  echo ""
  echo "可以手动检查的端口:"
  echo "  Questionnaire:  http://localhost:8015/docs"
  echo "  Weekly:         http://localhost:8014/docs"
  echo "  Chat:           http://localhost:8010/docs"
  echo "  Report:         http://localhost:8013/health"
  echo "  PDF Extract:    http://localhost:8002/health"
  echo "  RAG API:        http://localhost:8011/metrics"
else
  echo ""
  echo "❌ 存在失败项，请查看上方日志"
fi

echo ""
echo "清理命令:"
echo "  docker compose -f docker-test/docker-compose.yml down -v"
