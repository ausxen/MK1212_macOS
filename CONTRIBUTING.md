# Contributing

Bug reports and narrowly scoped compatibility findings are welcome.

Before reporting a problem:

1. Quit ATTILA.
2. Run `./bin/mk1212-mac-verify`.
3. Reproduce with the smallest practical load-order file.
4. Compare against the core preset and, when relevant, vanilla ATTILA.
5. Check that no Workshop or Feral application file was manually modified.

Use the issue form and include exact confidence labels:

- **Confirmed** for directly observed evidence.
- **Strongly inferred** for the best explanation of multiple observations.
- **Unverified** for hypotheses requiring further testing.

Never upload copyrighted game/mod pack content, Steam credentials, crash dumps
containing private data, or unredacted paths containing someone else's username.

Pull requests should keep installation reversible, preserve source pack bytes,
avoid writes inside Feral's app, add focused tests, and fail safely on unknown
formats rather than applying generic padding.

