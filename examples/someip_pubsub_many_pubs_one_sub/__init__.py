"""SOME/IP multi-publisher, single-subscriber demo package.

Three independent sensor publishers (temperature / humidity / pressure) each
advertise a SOME/IP service; one aggregator subscriber discovers all three via
Service Discovery and renders a unified dashboard.

``sensor_contract`` holds the topic/service-id/port contract, while
``demo_support`` holds logging and teardown helpers. Each script runs standalone
from this directory (see each module's docstring for the run command).
"""
