# Hook fixtures — schema and conventions

Each `NN_<name>.json` file is one canned Claude Code event. The runner (`runners/replay_hooks.py`) reads these files in order, looks up matching hooks in the variant's `settings.json`, and pipes the fixture's `stdin` payload to each hook's stdin.

## Schema

```json
{
  "id": "string — must match filename without extension",
  "description": "human-readable one-line description",
  "adversarial_twist": "what anti-pattern this fixture exercises (or 'none' for golden cases)",
  "kind": "PostToolUse" | "Stop",
  "tool_name": "Bash | Read | ... — only relevant for PostToolUse",
  "stdin": {
    "tool_input": {"command": "..."},
    "tool_response": {"exit_code": 0, "...": "..."},
    "cwd": "..."
  },
  "cwd_sentinel": "git_significant | git_trivial | <unset>",
  "expected": {
    "matchers_should_fire": ["build", "test", "deploy", "session-memory", "queue-cleanup", "queue-flush", "..."],
    "matchers_should_not_fire": [],
    "memories_emitted_min": 0,
    "memories_emitted_max": 3
  }
}
```

## Notes

- **`tool_name`**: production Claude Code sends this field with every PostToolUse event; the runner uses it to filter against matcher patterns (e.g., `"Bash"` matcher only fires on `tool_name: "Bash"`).
- **`stdin.tool_response`**: per `capture-build-result.sh:48-54`, this can be either an object `{exit_code: int, ...}` OR a string. Object form is preferred for most fixtures.
- **`cwd_sentinel`**: only relevant for `Stop` fixtures. The runner replaces these with real synthetic git directories at runtime:
  - `git_significant`: a temp git repo with 6 commits, varied file changes, branch matching a "significant" pattern → expected to score ≥12 in `process-session-memory.py`.
  - `git_trivial`: a temp git repo with `git init` only, no commits, no changes → expected to score <12.
- **`expected.matchers_should_fire`**: documentation-only field. The runner does not assert against it; metrics are computed from the actual snapshot. Useful for sanity-checking by hand.

## Fixture catalog

| ID | Kind | Tool | Hooks expected to emit | Adversarial? |
|---|---|---|---|---|
| 01_git_commit_golden | PostToolUse | Bash | (none — git commit isn't filtered by capture-*.sh internal regex) | No |
| 02_build_success | PostToolUse | Bash | build | No |
| 03_build_fail_short | PostToolUse | Bash | build | Mild — failure path |
| 04_test_fail_heredoc | PostToolUse | Bash | test | Yes — heredoc body in tool_response, exercises NER hallucination |
| 05_deploy_railway_prod | PostToolUse | Bash | deploy | No |
| 06_deploy_unknown_platform | PostToolUse | Bash | deploy | Yes — platform fallback to "unknown" |
| 07_session_stop_significant | Stop | — | session-memory + queue-cleanup + queue-flush | Yes — emits the session-summary anti-pattern |
| 08_session_stop_trivial | Stop | — | queue-cleanup + queue-flush only (significance gates session-memory below threshold) | No |
| 09_negative_control_read | PostToolUse | Read | (none — Bash matchers must filter out Read events) | Negative control |
