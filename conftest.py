import sys

# Hydra registers a broken pytest plugin that crashes on Python 3.14 due to a
# dataclass change. Block it from loading before pytest tries to import it.
sys.modules.setdefault("hydra", type(sys)("hydra"))
