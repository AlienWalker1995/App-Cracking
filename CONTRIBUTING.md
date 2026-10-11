# Contributing

Thanks for helping improve App-Cracker. This is a public repository, so please keep
contributions clean and free of anything target-specific.

## Proposing a change

1. Fork the repository, or create a branch from `main`.
2. Make your change and open a pull request against `main`.
3. `main` is protected: a pull request is required, history stays linear, and merges are
   squash-only. Do not push directly to `main`.
4. CI must pass before a pull request can be merged. The required check is the `ci` job in
   `.github/workflows/ci.yml`.

## What belongs here

- Engine-agnostic, package-parameterized tooling.
- Documentation and examples that do not name a real target.

## What does not belong here

- No secrets: no keys, tokens, signing material, or per-target offsets.
- No target data: no decrypted assets, bytecode dumps, databases, or captured traffic from
  any third-party application.
- No real app or game names in examples. Use placeholders such as `com.example.game`.

See [DISCLAIMER.md](DISCLAIMER.md) for the responsible-use scope and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for how we work together.

## Code style

Keep it readable. Match the surrounding code, prefer simple and explicit over clever, and
let the linters do the nitpicking. The Python lint config in `ruff.toml` is intentionally
lenient (real syntax and undefined-name errors only), so do not add style-only rules there
without a reason.

## Licensing

All contributions are made under the [Apache License 2.0](LICENSE). By contributing, you
agree that your contribution will be licensed under Apache-2.0.
