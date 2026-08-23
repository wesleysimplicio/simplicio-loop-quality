# Fast V3 conformance lanes

The conformance matrix exercises Python, Rust and off engines in Full and
Loop-standalone modes across conformance, corruption, generation drift,
selection, fallback, crash recovery and benchmark integrity. Every lane runs
at 1, 20 and 100 slots.

The quality extension consumes Loop receipts and public hooks. It never calls
the Fast engine directly or creates a second adapter. Rust must not load
Python or silently fall back. Shadow execution must not duplicate effects and
rollback must be exercised before promotion.

The evaluator binds results to source and policy hashes and requires evidence.
Missing or unavailable component environments remain BLOCKED.
