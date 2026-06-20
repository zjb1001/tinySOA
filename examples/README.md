# Examples

- Echo service: examples/echo_service/app.py
- Custom interceptor + Auth (Lab 6): examples/interceptor_auth/app.py
  - Custom CorrelationIdInterceptor + built-in AuthInterceptor + custom TimingInterceptor
  - Demonstrates priority ordering, Auth short-circuit, and exception propagation
- Pub/Sub (one publisher → many subscribers): examples/pubsub_multi/
  - server.py: TCP EventBus server
  - subscriber.py: subscriber process
  - publisher.py: publisher process
- Pub/Sub (many publishers → one subscriber): examples/multi_publishers_single_sub/
  - publisher_with_id.py: publishers with id field in payload
  - Reuse server and subscriber from pubsub_multi

Quick start (set PYTHONPATH):
```bash
cd tinySOA
export PYTHONPATH=$PWD/src
```
