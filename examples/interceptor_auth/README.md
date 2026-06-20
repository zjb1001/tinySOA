# interceptor_auth — custom interceptor + Auth demo (Lab 6)

Demonstrates the SPI **interceptor chain**, tinySOA's extension point for
cross-cutting concerns (auth, tracing, timing, metrics, …). It is the
hands-on counterpart to `/tinysoa-lab` Lab 6 and `/tinysoa-teach` module 6.

## What it shows

A `greet` service is fronted by a three-stage chain:

| # | interceptor              | priority | kind     | role                                  |
|---|--------------------------|----------|----------|---------------------------------------|
| 1 | `CorrelationIdInterceptor` | 1      | **custom**   | stamps a correlation id (runs first)  |
| 2 | `AuthInterceptor`          | 5      | **built-in** | checks the `Authorization` header     |
| 3 | `TimingInterceptor`        | 15     | **custom**   | measures duration via `try/finally`   |

Priority is **ascending**: lower runs first on the way in.

Three scenarios are played out, and the per-invocation execution order is
printed so the behavior is self-evident:

1. **authorized** — valid token: the request flows through every stage → response.
2. **unauthorized** — wrong token: `AuthInterceptor` **short-circuits**
   (`context.error` is set, `next_invoker` is never called) — `TimingInterceptor`
   and the invoker never run.
3. **business error** — the invoker raises: the exception **propagates through
   the chain untouched** (never swallowed). `TimingInterceptor` (try/finally)
   still records its exit; `CorrelationIdInterceptor` (plain `await`) does not —
   the raise unwinds straight past it.

## Run

Self-contained & deterministic (in-memory, no network). From the repo root:

```bash
PYTHONPATH=src:tinySOA/src python tinySOA/examples/interceptor_auth/app.py
PYTHONPATH=src:tinySOA/src python tinySOA/examples/interceptor_auth/app.py --scenario unauthorized
PYTHONPATH=src:tinySOA/src python tinySOA/examples/interceptor_auth/app.py --log-level DEBUG
```

Or via the examples Makefile:

```bash
make -C tinySOA/examples interceptors
```

Expected (authorized scenario) trace:

```
trace  : correlation:enter -> timing:enter -> timing:exit -> correlation:exit
outcome: OK -> {'greeting': 'hello, World!', 'correlation_id': 'corr-xxxxxxxx'}
```

## Key takeaways

- Implement the `Interceptor` ABC: override `priority` and
  `async intercept(context, next_invoker)`.
- **Continue the chain** with `await next_invoker(context)`.
- **Short-circuit** by setting `context.response` / `context.error` and returning
  *without* calling `next_invoker`.
- **Lower priority runs first.** Order cross-cutting concerns deliberately
  (correlation before everything; auth before business timing).
- Exceptions are **never swallowed** — to run cleanup on the error path too,
  wrap `next_invoker` in `try/finally` (compare `TimingInterceptor` vs
  `CorrelationIdInterceptor`).

## Test

Regression test pinning all three scenarios:

```bash
cd tinySOA && PYTHONPATH=src uvx pytest -q tests/test_example_interceptor_auth.py
```
