
from __future__ import annotations

class DataviewQuery:
    VALID_TYPES = {"TABLE", "LIST", "TASK", "CALENDAR"}
    def __init__(self, query_type: str = "TABLE") -> None:
        qt = query_type.upper()
        if qt not in self.VALID_TYPES: raise ValueError(f"Invalid query type '{query_type}'")
        self._type = qt; self._fields: list[str] = []; self._from = None
        self._where_clauses: list[str] = []; self._sort_clauses: list[tuple] = []
        self._limit = None; self._flatten = None; self._group_by = None; self._without_id = False

    def fields(self, *f: str): self._fields.extend(f); return self
    def from_folder(self, folder: str): self._from = f'"{folder}"'; return self
    def from_tag(self, tag: str): self._from = tag if tag.startswith("#") else f"#{tag}"; return self
    def from_raw(self, expr: str): self._from = expr; return self
    def where(self, clause: str): self._where_clauses.append(clause); return self
    def sort(self, field: str, direction: str = "ASC"):
        d = direction.upper()
        if d not in ("ASC","DESC"): raise ValueError(f"Sort direction must be ASC or DESC")
        self._sort_clauses.append((field, d)); return self
    def limit(self, n: int):
        if n <= 0: raise ValueError("LIMIT must be positive")
        self._limit = n; return self
    def flatten(self, field: str): self._flatten = field; return self
    def group_by(self, field: str): self._group_by = field; return self
    def without_id(self): self._without_id = True; return self

    def build(self) -> str:
        lines = []
        if self._type == "TABLE" and self._fields:
            lines.append(f"{'TABLE WITHOUT ID' if self._without_id else 'TABLE'} {', '.join(self._fields)}")
        else:
            lines.append(self._type)
        if self._from: lines.append(f"FROM {self._from}")
        if self._flatten: lines.append(f"FLATTEN {self._flatten}")
        for c in self._where_clauses: lines.append(f"WHERE {c}")
        if self._group_by: lines.append(f"GROUP BY {self._group_by}")
        for field, d in self._sort_clauses: lines.append(f"SORT {field} {d}")
        if self._limit: lines.append(f"LIMIT {self._limit}")
        return "\n".join(lines)

    def as_codeblock(self) -> str: return f"```dataview\n{self.build()}\n```"
    def __str__(self) -> str: return self.build()

class VaultQueries:
    @staticmethod
    def all_tracks():
        return (DataviewQuery("TABLE").fields("artist","album","bpm","camelot","key","genre","duration_fmt")
            .from_folder("Music").where('type = "track"').sort("artist","ASC").sort("bpm","ASC"))
    @staticmethod
    def tracks_by_camelot(camelot_code: str):
        return (DataviewQuery("TABLE").fields("title","artist","bpm","key")
            .from_folder("Music").where(f'camelot = "{camelot_code}"').sort("bpm","ASC"))
    @staticmethod
    def high_bpm_tracks(min_bpm: float = 128.0):
        return (DataviewQuery("TABLE").fields("title","artist","bpm","camelot","genre")
            .from_folder("Music").where(f"bpm >= {min_bpm}").sort("bpm","DESC"))
    @staticmethod
    def recently_added(days: int = 30, entity_type: str = "track", folder: str = "Music"):
        return (DataviewQuery("TABLE").fields("title","artist","date_added")
            .from_folder(folder).where(f'type = "{entity_type}"')
            .where(f"date_added >= date(today) - dur({days} days)").sort("date_added","DESC"))
    @staticmethod
    def all_photos():
        return (DataviewQuery("TABLE").fields("date_taken","city","country","camera_model","people")
            .from_folder("photo-notes").where('type = "photo"').sort("date_taken","DESC"))
    @staticmethod
    def photos_by_city(city: str):
        return (DataviewQuery("TABLE").fields("date_taken","camera_model","ai_tags","people")
            .from_folder("photo-notes").where(f'city = "{city}"').sort("date_taken","DESC"))
    @staticmethod
    def tracks_for_dj_set():
        return (DataviewQuery("TABLE").fields("title","artist","bpm","camelot","key","duration_fmt","genre")
            .from_folder("Music").where('type = "track"').where("bpm != null").sort("bpm","ASC"))
