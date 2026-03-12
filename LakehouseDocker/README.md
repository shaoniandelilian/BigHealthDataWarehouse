# 湖流一体湖仓基建

## 组件

- 计算层：Flink:1.20(流批一体)、Doris:3.1.4(查询引擎)
- 存储层：RustFS/MinIO(对象存储)、Paimon:1.3.1(表格式层)、Fluss:0.9(湖流一体)

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

### Kubernetes（多节点）

前置依赖：Helm 3、kubectl、minikube（或其他 K8s 集群）

minikube 环境需先配置：
```sh
minikube start --cpus=4 --memory=12288 --disk-size=50g
minikube ssh "sudo sysctl -w vm.max_map_count=2000000 && sudo swapoff -a"
```

裸机 kubeadm 集群需安装 StorageClass（minikube 已自带）：
```sh
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

配置Docker镜像
```sh
for host in <node1-ip> <node2-ip> <node3-ip>; do
  ssh root@$host "
    sed -i '/\[plugins\.\"io\.containerd\.grpc\.v1\.cri\"\.registry\.mirrors\]/a\\        [plugins.\"io.containerd.grpc.v1.cri\".registry.mirrors.\"docker.io\"]\n          endpoint = [\"https://docker.m.daocloud.io\", \"https://registry-1.docker.io\"]' /etc/containerd/config.toml
    systemctl restart containerd
  "
done
```

安装 Doris Operator, MinIO Operator
```sh
helm repo add doris https://charts.selectdb.com || true
helm repo update doris
helm upgrade --install doris-operator doris/doris-operator \
  --namespace doris --create-namespace \
  --set operator.resources.requests.cpu=200m \
  --set operator.resources.limits.cpu=1 \
  --wait --timeout 300s

helm repo add minio-operator https://operator.min.io || true
helm repo update minio-operator
helm upgrade --install minio-operator minio-operator/operator \
  --namespace minio-operator --create-namespace \
  --wait --timeout 300s
```

启动集群
```sh
cd multi-node

# 部署容器
kubectl apply -k .

# 启动 tiering job
kubectl -n lakehouse exec deploy/flink-jobmanager -- \
  /opt/flink/bin/flink run \
  /opt/flink/opt/fluss-flink-tiering-0.9.0-incubating.jar \
  --fluss.bootstrap.servers fluss-coordinator:9123 \
  --datalake.format paimon \
  --datalake.paimon.metastore filesystem \
  --datalake.paimon.warehouse s3://fluss/paimon \
  --datalake.paimon.s3.endpoint http://minio.lakehouse.svc.cluster.local \
  --datalake.paimon.s3.access.key minioadmin \
  --datalake.paimon.s3.secret.key minioadmin \
  --datalake.paimon.s3.path.style.access true
```

检查容器、扩缩容
```sh
# 检查 CR 状态
kubectl -n lakehouse get doriscluster
kubectl -n lakehouse get tenant

# 检查所有 Pod
kubectl -n lakehouse get pods

# 端口转发
# Flink WebUI
kubectl -n lakehouse port-forward svc/flink-jobmanager 8081:8081 --address 0.0.0.0
# Doris MySQL Port
kubectl -n lakehouse port-forward svc/doriscluster-lakehouse-fe-service 9030:9030 --address 0.0.0.0
# Doris WebUI
kubectl -n lakehouse port-forward svc/doriscluster-lakehouse-fe-service 8030:8030 --address 0.0.0.0
# MinIO Console
kubectl -n lakehouse port-forward svc/minio-console 9090:9090 --address 0.0.0.0
# MinIO S3
kubectl -n lakehouse port-forward svc/minio 9000:80 --address 0.0.0.0

# 水平扩缩容
kubectl -n lakehouse scale statefulset fluss-tablet --replicas=3
kubectl -n lakehouse scale deployment flink-taskmanager --replicas=3
# Doris/MinIO 通过修改 CR replicas 后 kubectl apply 扩缩容
```

Doris创建Paimon Catalog
```sh
CREATE CATALOG paimon PROPERTIES (
	"type" = "paimon",
	"warehouse" = "s3://fluss/paimon",
	"paimon.catalog-type" = "filesystem",
	"s3.endpoint" = "http://minio:80",
	"s3.access_key" = "minioadmin",
	"s3.secret_key" = "minioadmin",
	"s3.region" = "us-east-1",
	"use_path_style" = "true"
);
```

> [!TODO]
> 部署调度工具

---

> [!TIP]
> 部署后可以用`./test.sql`测试
