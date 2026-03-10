# 湖流一体湖仓基建

## 组件

- 计算层：Flink:1.20(流批一体)、Doris:2.1.8(查询引擎)
- 存储层：RustFS(对象存储)、Paimon:1.3.1(表格式层)、Fluss:0.9(湖流一体)

## 部署方案

### docker-compose(单节点)

```sh
cd single-node

# 下载依赖
./download_deps.sh

# 启动
docker compose up -d

# 启动tiering job(fluss)
docker compose exec flink-jobmanager \
  /opt/flink/bin/flink run \
  /opt/flink/opt/fluss-flink-tiering-0.9.0-incubating.jar \
  --fluss.bootstrap.servers fluss-coordinator:9123 \
  --datalake.format paimon \
  --datalake.paimon.metastore filesystem \
  --datalake.paimon.warehouse s3://fluss/paimon \
  --datalake.paimon.s3.endpoint http://rustfs:9000 \
  --datalake.paimon.s3.access.key rustfsadmin \
  --datalake.paimon.s3.secret.key rustfsadmin \
  --datalake.paimon.s3.path.style.access true
```

### Kubernetes(多节点)

```sh
TODO
```

---

> [!TIP]
> 部署后可以用`./test.sql`测试
