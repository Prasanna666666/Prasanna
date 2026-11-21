"""Atlas Core, Stage 2 foundation: reference implementation of the language-neutral contract in ../../contracts.

Layers, lowest first (a module may import only from layers below it; tests enforce this):
  1 errors, contracts, rules       2 events, identity      3 policy      4 gate, evidence      5 answer, tasks
  6 service                        7 api                   8 transport
"""

API_VERSION = "1.0"
SUPPORTED_VERSIONS = ("1.0",)
