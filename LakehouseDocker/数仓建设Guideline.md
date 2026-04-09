# TIP

同步k8s目录到云服务器前记得将占位符替换为真实密钥

```plain&#x20;text
grep -rl "<your-access-key>" . | xargs sed -i 's/<your-access-key>/真实access-key/g'
grep -rl "<your-secret-key>" . | xargs sed -i 's/<your-secret-key>/真实secret-key/g'
grep -rl "<your-endpoint>" . | xargs sed -i 's/<your-endpoint>/真实endpoint/g'
```

# 面向部署

详见`LakehouseDocker/README.md`

# 面向运维

## Flink环境lib依赖冲突

将jar-downloader-job里对应冲突的依赖去除，然后同步到服务器部署，并重启所有Flink节点。（实时作业推荐在Streampark里配置依赖，Streampark会自动下载并提交。Airflow最好只调度Paimon内部ETL）

## Flink扩缩容

修改`taskmanager-hpa.yaml`里面

&#x20; minReplicas: 2

&#x20; maxReplicas: 4

这两个字段，控制k8s弹性扩缩容的上限和下限。建议下限略多于实时作业的个数，给即席查询和离线调度留出空间

## JobManager/TaskManager配置

1. 在Streampark中配置TaskManager参数，Streampark提交作业时会启动新的TaskManager

2. 修改`jobmanager-deployment.yaml`、`taskmanager-deployment.yaml`、`secret.yaml`，同步到服务器并部署，重启jobmanager、taskmanager让配置生效

## StarRocks扩缩容

StarRocks采用operator部署，扩缩容只需要执行`kubectl edit starrockscluster -n starrocks`并修改`replicas`字段

## Kafka扩缩容

kafka暂不支持直接扩缩容

# 面向CI/CD

在宿主机运行`sync_dags_from_github.sh`脚本，可以同步github仓库的DAG目录到airflow的DAG目录，从而实现“push即部署”

# 面向测试

test目录下包含了集群测试脚本

test.sql用于测试paimon数据湖功能正常

test.py用于测试airflow调度功能正常

StarRocks\_vs\_FlinkSQL.md测试报告StarRocks和FlinkSQL(批模式)的性能

dataskew.md测试报告数据倾斜不同处理方案的效果

# 文件夹规范

Airflow的调度脚本放在`DAGs/`目录下，一个业务对应一个文件夹，比如`health_sensor/`是硬件传感器链路

Streampark实时作业SQL代码放在`Pipelines/`目录下归档，同样是一个业务对应一个文件夹

