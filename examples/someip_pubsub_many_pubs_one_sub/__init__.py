"""SOME/IP multi-publisher, single-subscriber demo package.

Three independent sensor publishers (temperature / humidity / pressure) each
advertise a SOME/IP service; one aggregator subscriber discovers all three via
Service Discovery and renders a unified dashboard.

Shared configuration and the publish/subscribe runtime live in ``_common`` so
the topic <-> service-id <-> port mapping stays in one place. Each script runs
standalone from this directory (see each module's docstring for the run command).
"""
