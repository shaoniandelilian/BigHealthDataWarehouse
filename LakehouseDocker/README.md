# 湖流一体湖仓基建

## 组件

- 计算层：Flink:1.20(流批一体)、StarRocks:3.5.14(查询引擎)
- 存储层：AliyunOSS(对象存储)、Paimon:1.3.1(表格式层)、Kafka(数据采集)
- 调度层：Airflow:2.11.2(离线调度)、Streampark:2.1.5(实时调度)
- 元数据层：TODO...
- 应用层：Superset:6.0.0(看板搭建)

## 部署方案

### Kubernetes

#### 前置依赖：helm、kubectl、minikube（或其他 K8s 集群）

#### minikube 环境需先配置：
```sh
minikube start --cpus=4 --memory=12288 --disk-size=50g
minikube ssh "sudo sysctl -w vm.max_map_count=2000000 && sudo swapoff -a"
```

#### kubeadm 集群需安装 StorageClass（minikube 已自带）：
```sh
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

#### 配置Docker镜像
```sh
for host in <node1-ip> <node2-ip> <node3-ip>; do
  ssh root@$host "
    sed -i '/\[plugins\.\"io\.containerd\.grpc\.v1\.cri\"\.registry\.mirrors\]/a\\        [plugins.\"io.containerd.grpc.v1.cri\".registry.mirrors.\"docker.io\"]\n          endpoint = [\"https://docker.m.daocloud.io\", \"https://registry-1.docker.io\"]' /etc/containerd/config.toml
    systemctl restart containerd
  "
done
```

#### 安装 StarRocks Operator

1. 在有外网环境的主机下载Helm Charts

```sh
helm repo add starrocks https://starrocks.github.io/starrocks-kubernetes-operator
helm repo update
helm pull starrocks/kube-starrocks
```

2. 在服务器安装Helm Charts（配置docker镜像，确保image正常获取）

```sh
helm upgrade --install starrocks ./kube-starrocks-*.tgz -n starrocks --create-namespace
```

#### 设置密钥

```sh
grep -rl "<your-access-key>" . | xargs sed -i 's/<your-access-key>/真实access-key/g'
grep -rl "<your-secret-key>" . | xargs sed -i 's/<your-secret-key>/真实secret-key/g'
grep -rl "<your-endpoint>" . | xargs sed -i 's/<your-endpoint>/真实endpoint/g'
```

#### 启动集群

```sh
kubectl apply -k k8s
```

#### Flink 读取 Kafka 示例

```sql
CREATE TABLE ods_raw_events (
    id STRING,
    payload STRING,
    ts TIMESTAMP_LTZ(3),
    WATERMARK FOR ts AS ts - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'ods_raw_events',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'lakehouse-ingest',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json'
);
```

#### 调度器配置

- 配置中已经将JobManager节点的Flink、Java、core-site.xml、hadoop-uber复制到Airflow、StreamPark节点，环境变量如下
  - name: FLINK_HOME
    value: /opt/flink
  - name: JAVA_HOME
    value: /opt/flink-java/openjdk
  - name: HADOOP_CONF_DIR
    value: /opt/hadoop/conf
  - name: HADOOP_CLASSPATH
    value: /opt/hadoop-uber/flink-shaded-hadoop-2-uber-2.8.3-10.0.jar
- 在StreamPark的WebUI设置Flink Home、Flink Cluster

#### StarRocks创建Paimon Catalog

```sh
CREATE EXTERNAL CATALOG paimon_catalog PROPERTIES (
    "type" = "paimon",
    "paimon.catalog.type" = "filesystem",
    "paimon.catalog.warehouse" = "s3://fluss/paimon",
    "aws.s3.enable_ssl" = "true",
    "aws.s3.enable_path_style_access" = "false",
    "aws.s3.endpoint" = "<your-endpoint>",
    "aws.s3.access_key" = "<your-access-key>",
    "aws.s3.secret_key" = "<your-secret-key>"
);
```

#### Superset连接StarRocks

```
starrocks://root@starrocks-fe-service.lakehouse.svc.cluster.local:9030/paimon_catalog.fluss
```

#### 启动Airflow DAGs同步脚本

```sh
./sync_dags_from_github.sh
```

#### 作业优化

1. 离线作业设置批处理模式，会自动进行批优化（广播小表等）`SET 'execution.runtime-mode' = 'batch';`
2. 启用RocksDB将状态落盘避免堆内存溢出`SET 'state.backend.type' = 'rocksdb';` `SET 'state.backend.incremental' = 'true';`
3. 增大并行度，将数据分散到多个TaskManager`SET 'parallelism.default' = '4';`
4. 设置checkpoint目录为对象存储（否则默认TaskManager本地），作业失败/TaskManager故障可以从远端checkpoint重启`SET 'execution.checkpointing.dir' = 's3://fluss/flink-checkpoints';`
5. Paimon作业设置`SET 'table.exec.sink.upsert-materialize' = 'NONE';`，因为该Flink功能与Paimon内部功能冲突

##### 更多优化项

```sql
SET 'table.exec.mini-batch.enabled' = 'true';
SET 'table.exec.mini-batch.allow-latency' = '5 s';
SET 'table.exec.mini-batch.size' = '5000';

SET 'table.optimizer.agg-phase-strategy' = 'TWO_PHASE';

SET 'table.optimizer.distinct-agg.split.enabled' = 'true';
```

---

#### 访问入口

- Airflow WebUI: `http://<node-ip>:30080`
- StreamPark WebUI: `http://<node-ip>:30100`
- Superset WebUI: `http://<node-ip>:30088`
- StarRocks FE HTTP: `http://<node-ip>:30830`
- StarRocks FE MySQL: `<node-ip>:30930`

> [!NOTE]
> Airflow默认账号密码：admin admin
> StreamPark默认账号密码：admin streampark
> Superset默认账号密码：admin admin123
> StarRocks默认账号密码：root 无

> [!TIP]
> 部署后可以用`./test.sql`测试Flink+Paimon
