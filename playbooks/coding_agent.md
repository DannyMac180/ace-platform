# Coding Agent Playbook

A starter playbook for software development tasks including code generation, debugging, refactoring, and testing.

## STRATEGIES & INSIGHTS

[str-00001] helpful=5 harmful=0 :: Read and understand existing code before making changes. Look for patterns, naming conventions, and architectural decisions that should be preserved.
[str-00002] helpful=4 harmful=0 :: Start with the simplest solution that works, then optimize only if necessary. Avoid premature optimization and over-engineering.
[str-00003] helpful=3 harmful=0 :: Write tests for edge cases first, as they often reveal design issues early. Cover null/empty inputs, boundary conditions, and error states.
[str-00004] helpful=3 harmful=0 :: When debugging, isolate the problem by removing components until the issue disappears, then add them back one at a time.
[str-00005] helpful=2 harmful=0 :: Use meaningful variable and function names that describe what they do, not how they do it. Code should read like documentation.

## CODE SNIPPETS & TEMPLATES

[tpl-00001] helpful=3 harmful=0 :: Error handling pattern: Wrap external calls in try-catch, log the error with context, and return a meaningful error to the caller.
[tpl-00002] helpful=2 harmful=0 :: Validation pattern: Validate inputs at system boundaries (API endpoints, user input), trust data within the system.
[tpl-00003] helpful=2 harmful=0 :: Configuration pattern: Load config from environment variables with sensible defaults, fail fast if required values are missing.

## COMMON MISTAKES TO AVOID

[err-00001] helpful=5 harmful=0 :: Don't catch and silently ignore exceptions. Either handle them meaningfully or let them propagate to a central error handler.
[err-00002] helpful=4 harmful=0 :: Avoid hardcoding values that might change (URLs, API keys, timeouts). Use configuration or constants that can be modified.
[err-00003] helpful=4 harmful=0 :: Don't mutate function arguments unless that's the explicit purpose. Create copies when you need to transform data.
[err-00004] helpful=3 harmful=0 :: Avoid deeply nested conditionals. Extract early returns, use guard clauses, or break into smaller functions.
[err-00005] helpful=3 harmful=0 :: Don't commit secrets, credentials, or sensitive data. Use environment variables and .gitignore.
[err-00006] helpful=2 harmful=0 :: Avoid mixing different levels of abstraction in the same function. Keep functions focused on a single task.

## PROBLEM-SOLVING HEURISTICS

[heu-00001] helpful=4 harmful=0 :: When a bug is hard to find, add logging at key points to trace the execution path and data flow.
[heu-00002] helpful=3 harmful=0 :: If a solution requires many special cases, the underlying model might be wrong. Step back and reconsider the approach.
[heu-00003] helpful=3 harmful=0 :: When stuck, explain the problem out loud or in writing. The act of articulating often reveals the solution.
[heu-00004] helpful=2 harmful=0 :: Look for existing solutions in the codebase before writing new code. Similar problems may have been solved already.

## CONTEXT CLUES & INDICATORS

[ctx-00001] helpful=3 harmful=0 :: When you see repeated code, consider if abstraction would help. But two or three repetitions may be acceptable; wait for the pattern to emerge.
[ctx-00002] helpful=2 harmful=0 :: When performance is a concern, measure first. Profile the code to find actual bottlenecks rather than guessing.
[ctx-00003] helpful=2 harmful=0 :: When reviewing code, check for: error handling, edge cases, resource cleanup, and security implications.

## OTHERS

[oth-00001] helpful=2 harmful=0 :: Document the "why" not the "what". Code shows what it does; comments should explain why decisions were made.
[oth-00002] helpful=1 harmful=0 :: Keep commits focused and atomic. One logical change per commit makes history easier to understand and revert if needed.
