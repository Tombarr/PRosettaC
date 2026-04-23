"""Local (no-scheduler) runner for single-machine / container use.

runBatchCommands executes each batch as a blocking shell script; wait() is a
no-op because everything has already finished by the time it is called.
"""

import os
import subprocess
import sys
import uuid
from typing import List

from ..Cluster import Cluster


class Local(Cluster):

    def __init__(self):
        super().__init__()

    def getRunningJobIDs(self) -> List[str]:
        return []

    def submit(self, job_file: str) -> str:
        job_id = str(uuid.uuid4())
        log_path = job_file + '.out'
        with open(log_path, 'w') as log:
            try:
                subprocess.run(['bash', job_file], check=True, stdout=log, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                print(f'Local job {job_file} failed with exit {e.returncode}; see {log_path}', file=sys.stderr)
        return job_id

    def writeJobFile(self, job_file: str, commands: List[str], mem: int) -> None:
        # No `set -e`: Rosetta returns non-zero if *any* nstruct model fails
        # out of many. With set -e the first partial failure would kill the
        # whole 12-command batch. Individual command output still goes to the
        # job's .out file for debugging.
        header = ['#!/usr/bin/env bash']
        if Cluster.SCHEDULER_PARAMS is not None:
            try:
                with open(Cluster.SCHEDULER_PARAMS) as f:
                    header.append(f.read())
            except IOError as e:
                print(f'Could not read SCHEDULER_PARAMS: {e}', file=sys.stderr)
        with open(job_file, 'w') as f:
            f.write('\n'.join(header) + '\n')
            for c in commands:
                f.write(c + '\n')
        os.chmod(job_file, 0o755)

    def runSingle(self, command):
        subprocess.run(command, shell=True, check=True)
        return str(uuid.uuid4())

    def wait(self, job_ids, timeout=-1):
        return
