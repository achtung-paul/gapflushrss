# The one place that defines what a client's statistical-model settings
# look like before anyone has touched them. Used both when a new client
# is created (api/admin_clients.py) and by this feature's own migration,
# which backfills the same defaults for every client that existed before
# the table did -- kept in one function so the two call sites can't
# quietly drift apart on what "default" means.
#
# Matches the app's pre-existing, hardcoded behaviour (core/simulation.py
# used to always compute exactly 3/4/5 sigma) so introducing this table
# doesn't silently change what any existing client sees.

DEFAULT_VISIBLE_SIGMA_LEVELS = (3, 4, 5)


def default_statistical_model_rows(client_id: int) -> list[dict]:
    """Plain dicts (not ORM objects) -- usable for both an ORM bulk-add and an Alembic bulk_insert."""
    return [
        {
            "client_id": client_id,
            "sigma_level": level,
            "visible": level in DEFAULT_VISIBLE_SIGMA_LEVELS,
            "info_only": False,
        }
        for level in range(1, 6)
    ]
