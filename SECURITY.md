# Security

## Threat model

Janus writes to your filesystem based on local-model output. The defenses,
in order:

1. **Decision gate** — ambiguous/malicious-shaped requests escalate before
   any generation is spent.
2. **Deterministic parsing** — model output is data; the parser is fuzzed
   (hypothesis) and cannot crash on arbitrary bytes.
3. **Path containment** — patch targets are resolved and refused if they
   escape the repo root.
4. **Verification** — tests must pass before a run is reported successful.
5. **Restore-parity rollback** — edits are restored byte-for-byte; created
   files are deleted.

Prompt-injected model output (e.g. a hostile docstring asking the model to
write elsewhere) is contained by (1) and (3). Report anything that breaks
these guarantees as a vulnerability.

## Reporting

Open a private security advisory on GitHub, or open an issue titled
`[security]` without details if you prefer public-first.

## Scope notes

- The verification step runs your project's own test command in a
  subprocess with your credentials — treat `JANUS_VERIFY_COMMAND` as code.
- `laya-serve` mode binds a localhost HTTP port with optional Bearer auth;
  prefer loopback.
