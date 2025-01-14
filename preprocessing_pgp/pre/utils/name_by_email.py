
import pandas as pd

import os
import subprocess
from pyarrow import fs
import pyarrow.parquet as pq
os.environ['HADOOP_CONF_DIR'] = "/etc/hadoop/conf/"
os.environ['JAVA_HOME'] = "/usr/jdk64/jdk1.8.0_112"
os.environ['HADOOP_HOME'] = "/usr/hdp/3.1.0.0-78/hadoop"
os.environ['ARROW_LIBHDFS_DIR'] = "/usr/hdp/3.1.0.0-78/usr/lib/"
os.environ['CLASSPATH'] = subprocess.check_output("$HADOOP_HOME/bin/hadoop classpath --glob", shell=True).decode('utf-8')
hdfs = fs.HadoopFileSystem(host="hdfs://hdfs-cluster.datalake.bigdata.local", port=8020)

import sys
sys.path.append('/bigdata/fdp/cdp/cdp_pages/scripts_hdfs/pre/utils/')
import preprocess_lib

# MAIN
if __name__ == '__main__':
    # params
    ROOT_PATH = '/data/fpt/ftel/cads/dep_solution/sa/cdp/core'
    utils_path = ROOT_PATH + '/utils'
    now_str = sys.argv[1]
    
    # run
    data = preprocess_lib.PipelineBestName(now_str, key='email')
    
    # save
    data.to_parquet(f'{utils_path}/name_by_email_latest.parquet', 
                    filesystem=hdfs,
                    index=False)
