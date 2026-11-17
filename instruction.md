# Play Message From Aliens

In 2058, Earth received a long sequence of mysterious signals from space.

Who are they, and where do they come from? Most importantly, what are they saying?

Message From Aliens is a science fiction puzzle game about deciphering a
pictographic alien language. Its entire interface is written in mysterious
symbols. The only human language text you can see in the game is your own notes.

## Goals

1. Complete all content.
2. Accurately translate all text.

## Rules

- Interact with the game only through its MCP tools; refer to their descriptions
  for usage. Do not run shell commands, read files, search the web, consult
  external answers, or use other tools or MCP servers.
- Use `note` to annotate character meanings in English.
- Do not brute-force answers.
- Do not wait for the user to provide translations or approve routine actions.
  Do not clear the save or reset overall progress. Stop only after completing
  all goals or when the user asks you to stop.

## Approach

- Use `note` as your working dictionary: record preliminary guesses as soon as
  they are supported by game observations. Use short, clear English words or
  phrases, mark uncertainty with `?`, and revise contradictions promptly. Filling
  every annotation does not make the translations correct; check for contradictions
  across different contexts.
- Observe the writing: use `glyph` to inspect character shapes or visual details.
  Observing, comparing, and identifying patterns across characters can help you
  understand their meanings.
- Try more and speculate less: use `click` to try different symbols. Once you
  form a hypothesis, test it through an interaction or another passage, observe
  the result, and revise. Avoid prolonged speculation without testing.
