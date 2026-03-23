# 湖流一体湖仓基建

## 组件

- 计算层：Flink:1.20(流批一体)、StarRocks:3.5.14(查询引擎)
- 存储层：AliyunOSS(对象存储)、Paimon:1.3.1(表格式层)
- 调度层：Airflow:2.11.2(离线调度)、Streampark:2.1.5(实时调度)
- 元数据层：TODO...
- 应用层：Superset(看板搭建)

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

#### 设置密钥（如果使用AliyunOSS）

```sh
grep -rl "<your-oss-access-key>" . | xargs sed -i 's/<your-oss-access-key>/真实access-key/g'
grep -rl "<your-oss-secret-key>" . | xargs sed -i 's/<your-oss-secret-key>/真实secret-key/g'
grep -rl "<your-oss-endpoint>" . | xargs sed -i 's/<your-oss-endpoint>/真实endpoint/g'
```

#### 启动集群

```sh
kubectl apply -k .
```

#### 启动Airflow DAGs同步脚本

```sh
./sync_dags_from_github.sh
```

#### StarRocks创建Paimon Catalog

```sh
CREATE CATALOG paimon PROPERTIES (

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
- [ ] 比较OLAP实现方案 1. StarRocks查询Paimon 2. StarRocks查询内部 3. Flink OLAP查询
- [ ] TB级压力测试，制造数据倾斜，优化k8s配置，设计解决方案

---

> [!NOTE]
> StreamPark默认账号密码：admin streampark

> [!TIP]
> 部署后可以用`./test.sql`测试Flink+Paimon，用`./test.py`测试Airflow
