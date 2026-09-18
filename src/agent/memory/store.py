"""Memoria do agente em SQLite.

No M1 guarda so a serie de sinais -- que e o que permite calcular velocidade
para fontes que reportam nivel e nao taxa (Wikipedia, Google Trends). Sem
historico, "500 mil pageviews" e um numero sem significado: nao da para saber se
o assunto esta subindo ou ja passou.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent.models import Decision, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY,
    key         TEXT    NOT NULL,
    term        TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    volume      REAL    NOT NULL,
    unit        TEXT    NOT NULL,
    velocity    REAL,
    url         TEXT,
    seen_at     TEXT    NOT NULL
);
-- A consulta quente e "ultima observacao desta chave antes de agora".
CREATE INDEX IF NOT EXISTS idx_signals_key_seen ON signals(key, seen_at DESC);

CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY,
    term        TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    verdict     TEXT    NOT NULL,
    reason      TEXT    NOT NULL,
    score       REAL    NOT NULL,
    niche_fit   REAL    NOT NULL,
    url         TEXT,
    duplicate_of TEXT,
    decided_at  TEXT    NOT NULL
);
-- O ledger e sempre lido por "temas aprovados recentemente", nunca inteiro.
CREATE INDEX IF NOT EXISTS idx_topics_verdict_decided
    ON topics(verdict, decided_at DESC);
"""


class SignalStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, signals: Iterable[Signal]) -> int:
        rows = [
            (s.key, s.term, s.source, s.volume, s.unit, s.velocity,
             str(s.url) if s.url else None, s.seen_at.isoformat())
            for s in signals
        ]
        if not rows:
            return 0
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO signals (key, term, source, volume, unit, velocity, url, seen_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def previous(self, key: str, before: datetime) -> tuple[float, datetime] | None:
        """Ultima observacao desta chave antes de `before`, se houver."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT volume, seen_at FROM signals"
                " WHERE key = ? AND seen_at < ? ORDER BY seen_at DESC LIMIT 1",
                (key, before.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return float(row["volume"]), _parse_iso(row["seen_at"])

    def count(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"])

    # ------------------------------------------------------------ ledger de temas

    def record_decisions(self, decisions: Iterable[Decision]) -> int:
        """Grava toda decisao, aprovada ou nao.

        Rejeicao gravada e o que permite calibrar o score depois em vez de
        chutar: sem ela, so se sabe o que foi escolhido, nunca o que foi perdido.
        """
        rows = [
            (d.term, d.source, d.verdict.value, d.reason, d.score, d.niche_fit,
             str(d.url) if d.url else None, d.duplicate_of, d.decided_at.isoformat())
            for d in decisions
        ]
        if not rows:
            return 0
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO topics (term, source, verdict, reason, score, niche_fit,"
                " url, duplicate_of, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def recent_topics(self, days: int = 30, limit: int = 500) -> list[str]:
        """Temas ja aprovados, para o deduplicador comparar.

        So os aprovados entram: um tema rejeitado por politica ou por nicho nao
        "ja foi coberto" -- ele nunca virou video, e bloquear o parecido seria
        estender o veto a assuntos que nunca foram julgados.
        """
        corte = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT term FROM topics WHERE verdict = 'selected' AND decided_at >= ?"
                " ORDER BY decided_at DESC LIMIT ?",
                (corte, limit),
            ).fetchall()
        return [r["term"] for r in rows]

    def topic_count(self) -> int:
        with self._conn() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM topics").fetchone()["n"])


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    # Datas gravadas antes de uma normalizacao, ou por outra ferramenta, podem
    # vir sem tzinfo. Comparar naive com aware levanta TypeError no meio da
    # coleta, entao assume-se UTC, que e o que o agente sempre grava.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

