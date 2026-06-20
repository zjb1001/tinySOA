#!/bin/bash
export PYTHONPATH=/home/page/GitPlayground/pysomeip/src:/home/page/GitPlayground/pysomeip/tinySOA/src:$PYTHONPATH
cd "$(dirname "$0")"
python publisher3_pressure.py
