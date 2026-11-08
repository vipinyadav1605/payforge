# Learning log

One entry per problem you solve. These become your interview answers.
Template:

```
## <date> - <short title>
**Problem:** what broke or what was unclear
**Options considered:** A (pros/cons), B (pros/cons)
**Decision + why:**
**Evidence:** test name, metric, or log line that proves it works
**What I'd do differently / open questions:**
```

## Starter entries to write after reading the code

- Why `amount` is an integer, and what goes wrong with floats.
- Walk through what happens when two identical `POST /v1/payments` arrive at the same instant.
- Why the outbox row is written in the same transaction as the payment.
- What the deferred constraint trigger protects against that application code can't.
- What happens to a webhook when the merchant's server is down for 2 hours?
