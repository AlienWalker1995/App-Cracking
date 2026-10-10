# AGENTS.md

App-Cracker is a generic Android app reverse-engineering toolkit. It takes an APK (or a
package name) and produces a structured evidence bundle across three tiers: Tier 0 static
analysis (engine, assets, IL2CPP dump, endpoints, manifest), Tier 1 dynamic on-device
analysis (runtime Lua and config carved from memory, live DB, read/write and network
monitoring), and Tier 2 synthesis (a sourced "how it works" report). The pipeline is
engine-agnostic and package-parameterized; per-target keys and decoders live beside it,
not in this repository.

## Using the app-cracker skill

The full operating contract, the trigger gate, and the step-by-step workflow live in
`skills/app-cracker/SKILL.md`. An agent MUST read that file and follow its "Trigger contract
(hard rules)" before taking any action. Do not restate or improvise the workflow here; the
canonical skill is the single source of truth.

## Safety

Only analyze apps you have the right to analyze; see `DISCLAIMER.md`.
