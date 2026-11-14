"""The small files the Documents service and the reader leave for each other in the shared folder (nothing readable is ever kept in them)."""

AUTO_LIMIT = ".auto_limit"  # the service writes it for a round that starts by itself: how many files that round may read at most
AUTO_CAPPED = ".auto_capped"  # the reader writes it when a round stopped at that limit with files still waiting
