"""Persistência das transcrições em SQLite.

Por que SQLite e não PostgreSQL: ver docs/roadmap.md seção 4. Resumo — a
Quick Filler não exige banco, a persistência necessária é um documento JSON por
transcrição, e um serviço a menos deixa o `docker compose up` mais rápido e mais
confiável, que é o requisito duro do desafio.

Por que uma conexão por operação, em vez de uma conexão global:

Uploads simultâneos são um requisito explícito de segurança do desafio, e o
processamento roda em background, em outra thread. Uma conexão SQLite não pode
ser compartilhada entre threads sem cuidado. Abrir e fechar por operação é o
padrão mais simples que é correto sob concorrência — o custo é irrelevante para
o volume deste projeto.

WAL (Write-Ahead Logging) permite leituras concorrentes com uma escrita, que é
exatamente o padrão aqui: o frontend faz polling (leitura) enquanto o
processamento grava o resultado.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcricoes (
    id          TEXT PRIMARY KEY,
    tipo        TEXT NOT NULL,
    status      TEXT NOT NULL,
    erro        TEXT,
    value_json  TEXT,
    pdf_path    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcricoes_created_at
    ON transcricoes (created_at);
"""


@dataclass
class Transcricao:
    """Uma transcrição persistida.

    `value` é o documento JSON no formato oficial (ou None enquanto processa).
    Não é normalizado em tabelas: o formato é ditado pela Quick Filler e
    quebrá-lo em linhas só criaria trabalho de remontagem.
    """

    id: str
    tipo: str
    status: str
    erro: Optional[str]
    value: Optional[Dict[str, Any]]
    pdf_path: Optional[str]
    created_at: datetime
    updated_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


class TranscriptionRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

        # O banco guarda as transcrições, que são o conteúdo dos documentos —
        # nome, CPF, salário. O SQLite cria o arquivo com a permissão padrão do
        # processo; aqui ela é restringida explicitamente.
        self._database_path.chmod(0o600)

    # ------------------------------------------------------------------ escrita

    def create(
        self,
        transcricao_id: str,
        tipo: str,
        status: str,
        pdf_path: Optional[str],
    ) -> Transcricao:
        moment = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transcricoes
                    (id, tipo, status, erro, value_json, pdf_path,
                     created_at, updated_at)
                VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)
                """,
                (transcricao_id, tipo, status, pdf_path, _iso(moment), _iso(moment)),
            )
        return Transcricao(
            id=transcricao_id,
            tipo=tipo,
            status=status,
            erro=None,
            value=None,
            pdf_path=pdf_path,
            created_at=moment,
            updated_at=moment,
        )

    def set_concluido(self, transcricao_id: str, value: Dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE transcricoes
                   SET status = 'concluido',
                       erro = NULL,
                       value_json = ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (json.dumps(value, ensure_ascii=False), _iso(_now()), transcricao_id),
            )

    def set_erro(self, transcricao_id: str, mensagem: str) -> None:
        """Marca erro. `mensagem` precisa ser legível e não conter PII."""
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE transcricoes
                   SET status = 'erro',
                       erro = ?,
                       value_json = NULL,
                       updated_at = ?
                 WHERE id = ?
                """,
                (mensagem, _iso(_now()), transcricao_id),
            )

    def replace_value(self, transcricao_id: str, value: Dict[str, Any]) -> bool:
        """Substitui a transcrição com as correções feitas na interface (PUT).

        Devolve False quando o id não existe.
        """
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE transcricoes
                   SET value_json = ?,
                       updated_at = ?
                 WHERE id = ?
                """,
                (json.dumps(value, ensure_ascii=False), _iso(_now()), transcricao_id),
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ leitura

    def get(self, transcricao_id: str) -> Optional[Transcricao]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM transcricoes WHERE id = ?", (transcricao_id,)
            ).fetchone()
        return self._row_to_transcricao(row) if row else None

    # ---------------------------------------------------------------- retenção

    def find_expired(self, retention_hours: int) -> List[Transcricao]:
        """Transcrições mais antigas que a janela de retenção.

        A política de retenção é exigida explicitamente pelo desafio: os PDFs
        contêm nome, CPF, matrícula, salário e jornada de pessoas reais, e não
        podem ficar guardados indefinidamente.
        """
        limite = _now() - timedelta(hours=retention_hours)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM transcricoes WHERE created_at < ?", (_iso(limite),)
            ).fetchall()
        return [self._row_to_transcricao(row) for row in rows]

    def delete(self, transcricao_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM transcricoes WHERE id = ?", (transcricao_id,)
            )

    # ------------------------------------------------------------------ interno

    @staticmethod
    def _row_to_transcricao(row: sqlite3.Row) -> Transcricao:
        return Transcricao(
            id=row["id"],
            tipo=row["tipo"],
            status=row["status"],
            erro=row["erro"],
            value=json.loads(row["value_json"]) if row["value_json"] else None,
            pdf_path=row["pdf_path"],
            created_at=_parse_iso(row["created_at"]),
            updated_at=_parse_iso(row["updated_at"]),
        )
