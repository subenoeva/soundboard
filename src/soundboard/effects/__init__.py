"""The microphone effects chain.

Imports neither Qt nor ``ui/``: this package sits at the same layer as ``audio/``
and runs on the callback thread, so the rules in AGENTS.md for that path apply
here too -- no I/O, no logging, no non-trivial allocation.

It also puts a constraint on the rest of the process, which is easier to break from
somewhere else entirely: the neural block releases the GIL and has to take it back
inside the block deadline, so no background thread here may occupy the GIL for long.
A pure-Python loop occupies it, and so does a long C call that never releases it;
what is safe is C that releases it and then blocks (``sf.read``, ``soxr``, socket
I/O). Anything else belongs in a subprocess. AGENTS.md carries the measurements.
"""
