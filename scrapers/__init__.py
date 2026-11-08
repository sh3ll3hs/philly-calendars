"""One module per venue. Each exposes fetch() -> list[dict] in the common.normalize.record shape,
plus a pure parse function that tests can run against saved fixtures."""

# Order matters only for output readability.
VENUES = ["south", "mann", "sellersville", "parx", "dawson", "queen", "livenation_tm"]
