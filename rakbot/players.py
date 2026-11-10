"""Player names from structurally decoded replication, never raw byte searches."""

import unicodedata

from .replication import Inspector


def _name(value):
    if not isinstance(value, bytes) or not 1 <= len(value) <= 256:
        return None
    try:
        text = value.decode("utf-8")
    except UnicodeError:
        return None
    if not text.strip() or any(unicodedata.category(char).startswith("C") for char in text):
        return None
    return text


class PlayerRoster(Inspector):
    def __init__(self, schema, user_id, *, on_player=None):
        super().__init__(schema, user_id, retain_world=False)
        self.on_player = on_player
        self._announced = {}
        self._source = None

    def players(self):
        result = {}
        for _, node in (self._source or self).nodes.class_items('Player'):
            if node["class"] != "Player":
                continue
            props = node["props"]
            user_id = props.get("UserId")
            username = _name(props.get("Name"))
            if type(user_id) is not int or not 0 < user_id < 2**63 or username is None:
                continue
            result[user_id] = {"user_id": user_id, "username": username,
                               "display_name": _name(props.get("DisplayName")),
                               "is_self": user_id == self.user_id}
        return sorted(result.values(), key=lambda row: (row["username"].casefold(), row["user_id"]))

    def push(self, packet):
        super().push(packet)
        self.refresh()

    def refresh(self, source=None):
        if source is not None:
            self._source = source
        current = {row["user_id"]: row for row in self.players()}
        if self.on_player is not None:
            for user_id, row in current.items():
                if self._announced.get(user_id) != row:
                    self.on_player(dict(row))
        self._announced = current

    def summary(self):
        return {"players": self.players(), "players_complete": False,
                "players_scope": "Decoded Player records; unsupported replication may omit players.",
                "player_list_decode_stops": dict((self._source or self).stops)}
