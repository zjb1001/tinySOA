"""SOME/IP Echo — 共享配置。

两个独立进程通过同一个 MAPPING 找到彼此：
  - publisher 通过 SD Offer 通告 (service_id=0x3333, instance=0x0001, eventgroup=0x0001)
  - subscriber 通过 SD Find 发现同一个服务
"""
from tinysoa.eventbus.someip import SomeIPTopicMapping

TOPIC = "echo.hello"

MAPPING = SomeIPTopicMapping(
    service_id=0x3333,
    instance_id=0x0001,
    eventgroup_id=0x0001,
    major_version=1,
)

LOCAL_IP = "127.0.0.1"

# 两个进程用不同端口，避免冲突
PUBLISHER_PORT = 30900
SUBSCRIBER_PORT = 30910
