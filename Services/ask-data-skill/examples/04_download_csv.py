"""
CSV 下载脚本模板
Agent 根据查询结果生成此脚本，将数据保存为 CSV。支持 Mac/Windows/Linux。
"""
import csv, os, platform, subprocess, sys
from datetime import datetime


def get_downloads_dir(custom_path=None):
    if custom_path:
        os.makedirs(custom_path, exist_ok=True)
        return custom_path
    return os.path.join(os.path.expanduser("~"), "Downloads")


def query_remote(sql, db="default"):
    full_sql = f"SET CATALOG paimon_catalog; USE {db}; {sql}"
    cmd = ["ssh", "root@47.110.248.69",
           f'mysql -uroot -h 127.0.0.1 -P 30930 -e "{full_sql}"']
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[ERROR] {r.stderr}", file=sys.stderr)
        sys.exit(1)
    return r.stdout


def parse_mysql_output(output):
    lines = [l for l in output.strip().split("\n") if l]
    if not lines:
        return [], []
    return lines[0].split("\t"), [l.split("\t") for l in lines[1:]]


def save_csv(header, rows, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def download_large(sql, db, filepath):
    remote_tmp = "/tmp/query_result.tsv"
    full_sql = f"SET CATALOG paimon_catalog; USE {db}; {sql}"
    subprocess.run(["ssh", "root@47.110.248.69",
                     f'mysql -uroot -h 127.0.0.1 -P 30930 -e "{full_sql}" > {remote_tmp}'], check=True)
    subprocess.run(["scp", f"root@47.110.248.69:{remote_tmp}", filepath], check=True)
    subprocess.run(["ssh", "root@47.110.248.69", f"rm -f {remote_tmp}"], check=True)


if __name__ == "__main__":
    DATABASE = "zz"
    SQL = "SELECT spu_id AS spu, unique_id AS P码 FROM dwm_scm_detail_di WHERE pt='20260313' AND promise_type_code=1"
    CUSTOM_PATH = None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(get_downloads_dir(CUSTOM_PATH), f"query_result_{ts}.csv")

    count_out = query_remote(f"SELECT COUNT(*) AS cnt FROM ({SQL}) t", DATABASE)
    _, count_rows = parse_mysql_output(count_out)
    row_count = int(count_rows[0][0]) if count_rows else 0
    print(f"[INFO] 查询结果共 {row_count} 行")

    if row_count <= 1000:
        header, rows = parse_mysql_output(query_remote(SQL, DATABASE))
        save_csv(header, rows, filepath)
    else:
        download_large(SQL, DATABASE, filepath)

    print(f"[INFO] 文件已保存至: {filepath}")
