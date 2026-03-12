# 湖流一体湖仓基建

## 组件

- 计算层：Flink:1.20(流批一体)、Doris:3.1.4(查询引擎)
- 存储层：RustFS(对象存储)、Paimon:1.3.1(表格式层)、Fluss:0.9(湖流一体)

## 部署方案

### docker-compose(单节点)

```sh
cd single-node

# 复制环境变量模板并按当前机器修改
cp .env.example .env

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

单节点环境中的 Flink 默认会：

- 自动启用 `flink-s3-fs-hadoop` 插件
- 自动挂载 `HOST_DATA_DIR` 到容器内的 `/host-data`

这允许直接用 `file:///host-data/...` 方式导入本机上的 CSV。

### Doris(测试环境)

`single-node/docker-compose.yml` 已包含单机 Doris PoC 配置，适合在现有 lakehouse 环境上增量验证。

启动前需要：

- 在 `single-node/.env` 中设置 Doris 固定子网参数：
  - `DORIS_NET_SUBNET`
  - `DORIS_FE_IP`
  - `DORIS_BE_IP`
  - `DORIS_PRIORITY_NETWORKS`
- 建议使用独立 Docker 子网，并让 `DORIS_PRIORITY_NETWORKS` 与该子网一致
- 宿主机执行 `sudo sysctl -w vm.max_map_count=2000000`

启动命令：

```sh
docker compose up -d doris-fe doris-be
```

验证步骤：

```sh
docker compose logs --tail=100 doris-fe
docker compose logs --tail=100 doris-be
```

进入 FE 后可执行：

```sql
SHOW FRONTENDS;
SHOW BACKENDS;
```

### Kubernetes(多节点)

```sh
TODO
```

---

> [!TIP]
> 部署后可以用`./test.sql`测试
