# ADR 1: SQLite + FTS5 instead of an in-memory dataframe
Context: 500 GB library on an 8 GB machine. Decision: SQLite (WAL) with trigram FTS5 and chunked embedding search. Consequence: bounded memory, resumable, queryable.
