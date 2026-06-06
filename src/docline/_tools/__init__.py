"""Internal subprocess CLIs invoked by the docline batch processor.

These tools are not part of the public docline CLI surface; they exist
so the batch processor can run docling (which loads heavy PyTorch
models and can OOM with hard-to-catch C-level errors) in an isolated
child process. If a child crashes, the OS reaps it cleanly and the
parent records a non-zero exit code, downgrading that chunk to the
heuristic engine.
"""
