"""Recebimento e validação do PDF enviado.

O desafio é explícito: é um endpoint público que recebe documento com nome,
CPF, matrícula, salário e jornada de pessoas reais. O INSTRUCOES oficial diz
que "um `.txt` renomeado para `.pdf` não pode virar transcrição", e que recusar
com 4xx é o comportamento ideal.

Três camadas de validação, da mais barata para a mais cara:

1. tamanho — cortado durante a leitura, em streaming, para que um arquivo
   gigante não seja carregado inteiro na memória antes de ser recusado;
2. assinatura — os bytes iniciais precisam ser `%PDF-`. Extensão e
   `content-type` vêm do cliente e não valem como prova;
3. abertura real — o PDF precisa abrir e ter um número de páginas dentro do
   limite. É o que pega PDF corrompido e "bomba" de páginas.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import BinaryIO, Optional

import pdfplumber

PDF_MAGIC = b"%PDF-"

_CHUNK_SIZE = 64 * 1024


class UploadInvalido(Exception):
    """Arquivo recusado. A mensagem é legível e vai para o cliente."""


class UploadMuitoGrande(Exception):
    """Arquivo excede o limite configurado."""


class DocumentService:
    def __init__(self, storage_dir: Path, max_upload_bytes: int, max_pdf_pages: int) -> None:
        self._storage_dir = storage_dir
        self._max_upload_bytes = max_upload_bytes
        self._max_pdf_pages = max_pdf_pages

    def store_upload(self, source: BinaryIO, transcricao_id: str) -> Path:
        """Valida e grava o PDF. Devolve o caminho gravado.

        O arquivo é gravado com um nome derivado do id da transcrição, e NUNCA
        com o nome original enviado: nomes de arquivo costumam conter o nome da
        pessoa (ex.: "holerite-joao-silva.pdf"), o que seria PII em disco e nos
        logs.
        """
        # O diretório e os arquivos guardam PII: nome, CPF, matrícula, salário
        # e jornada de pessoas reais. Só o usuário da aplicação precisa lê-los.
        self._storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        destino = self._storage_dir / f"{transcricao_id}.pdf"
        destino.touch(mode=0o600, exist_ok=True)

        try:
            self._write_with_limit(source, destino)
            self._assert_pdf_signature(destino)
            self._assert_openable(destino)
        except Exception:
            destino.unlink(missing_ok=True)
            raise

        return destino

    # ------------------------------------------------------------------ camadas

    def _write_with_limit(self, source: BinaryIO, destino: Path) -> None:
        total = 0
        with destino.open("wb") as saida:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > self._max_upload_bytes:
                    raise UploadMuitoGrande(
                        "O arquivo excede o tamanho máximo permitido de "
                        f"{self._max_upload_bytes // (1024 * 1024)} MB."
                    )
                saida.write(chunk)

        if total == 0:
            raise UploadInvalido("O arquivo enviado está vazio.")

    @staticmethod
    def _assert_pdf_signature(caminho: Path) -> None:
        with caminho.open("rb") as arquivo:
            inicio = arquivo.read(len(PDF_MAGIC))
        if inicio != PDF_MAGIC:
            raise UploadInvalido("O arquivo enviado não é um PDF válido.")

    def _assert_openable(self, caminho: Path) -> None:
        try:
            with pdfplumber.open(caminho) as pdf:
                paginas = len(pdf.pages)
        except Exception as exc:  # pdfminer levanta vários tipos diferentes
            raise UploadInvalido(
                "O PDF está corrompido ou não pôde ser aberto."
            ) from exc

        if paginas == 0:
            raise UploadInvalido("O PDF não contém páginas.")

        if paginas > self._max_pdf_pages:
            raise UploadInvalido(
                f"O PDF tem {paginas} páginas e o limite é "
                f"{self._max_pdf_pages}."
            )

    # ------------------------------------------------------------------ apoio

    @staticmethod
    def new_id() -> str:
        """Identificador opaco, sem qualquer relação com o conteúdo enviado."""
        return uuid.uuid4().hex[:12]

    @staticmethod
    def remove(caminho: Optional[str]) -> None:
        """Remove o PDF do disco (usado pela política de retenção)."""
        if not caminho:
            return
        Path(caminho).unlink(missing_ok=True)
