# 湖流一体湖仓基建

## 组件

- 计算层：Flink:1.20(流批一体)、Doris:3.1.4(查询引擎)
- 存储层：AliyunOSS/MinIO:latest(对象存储)、Paimon:1.3.1(表格式层)、Fluss:0.9(湖流一体)
- 调度层：Airflow:2.11.2(离线调度)、Streampark:2.1.5(实时调度)
- 元数据层：~Hive-MetaStore:4.2.0(元数据管理)(暂时没必要)~、~DataHub(数据目录)(依赖组件过多，暂时搁置)~

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

#### 安装 Doris Operator, MinIO Operator

1. 在有外网环境的主机下载Helm Charts

```sh
helm repo add doris https://charts.selectdb.com
helm repo add minio-operator https://operator.min.io
helm repo update
helm pull doris/doris-operator
helm pull minio-operator/operator
```

2. 在服务器安装Helm Charts（配置docker镜像，确保image正常获取）

```sh
helm upgrade --install doris-operator ./doris-operator-*.tgz -n doris --create-namespace
helm upgrade --install minio-operator ./operator-*.tgz -n minio-operator --create-namespace
```

#### 设置密钥（如果使用AliyunOSS）

```sh
grep -rl "<your-oss-access-key>" . | xargs sed -i 's/<your-oss-access-key>/真实access-key/g'
grep -rl "<your-oss-secret-key>" . | xargs sed -i 's/<your-oss-secret-key>/真实secret-key/g'
grep -rl "<your-oss-endpoint>" . | xargs sed -i 's/<your-oss-endpoint>/真实endpoint/g'
```

#### 启动集群

```sh
# 部署容器
kubectl apply -k .

# 启动 tiering job 记得先创建fluss桶
kubectl -n lakehouse exec deploy/flink-jobmanager -- \
  /opt/flink/bin/flink run \
  /opt/flink/opt/fluss-flink-tiering-0.9.0-incubating.jar \
  --fluss.bootstrap.servers fluss-coordinator:9123 \
  --datalake.format paimon \
  --datalake.paimon.metastore filesystem \
  --datalake.paimon.warehouse s3://fluss/paimon \
  --datalake.paimon.s3.endpoint <your-oss-url> \
  --datalake.paimon.s3.access.key <your-oss-access-key> \
  --datalake.paimon.s3.secret.key <your-oss-secret-key> \
  --datalake.paimon.s3.path.style.access true
```

> [!TIP]
> 如果是AliyunOSS，所有path.style都要设置false

#### 启动Airflow DAGs同步脚本

```sh
./sync_dags_from_github.sh
```

#### Doris创建Paimon Catalog

```sh
CREATE CATALOG paimon PROPERTIES (
	"type" = "paimon",
	"warehouse" = "s3://fluss/paimon",
	"paimon.catalog-type" = "filesystem",
	"s3.endpoint" = "<your-oss-url>",
	"s3.access_key" = "<your-oss-access-key>",
	"s3.secret_key" = "<your-oss-secret-key>",
	"s3.region" = "us-east-1",
	"use_path_style" = "true"
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

#### TODO

- [x] Airflow DAGs同步git仓库
- [ ] 比较OLAP实现方案 1. Doris查询Paimon 2. Doris查询内部 3. Flink OLAP查询
- [ ] TB级压力测试，制造数据倾斜，优化k8s配置，设计解决方案

---

> [!NOTE]
> StreamPark默认账号密码：admin streampark

> [!TIP]
> 部署后可以用`./test.sql`测试Flink+Fluss，用`./test.py`测试Airflow
