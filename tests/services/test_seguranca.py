"""Testes das garantias de segurança que não são óbvias no código.

Não repetem o que `test_upload_validacao.py` já cobre (assinatura, tamanho,
corrupção). Aqui ficam as três garantias que dependem de comportamento e não
de uma checagem simples.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from app.repositories.transcription_repository import TranscriptionRepository
from app.services.document_service import DocumentService
from app.services.transcription_service import TranscriptionService


def _servico(tmp_path, pipeline, max_simultaneos=2, retention_hours=24):
    repositorio = TranscriptionRepository(tmp_path / "t.db")
    repositorio.init_db()
    return (
        TranscriptionService(
            repository=repositorio,
            documents=DocumentService(
                storage_dir=tmp_path / "pdfs",
                max_upload_bytes=10 * 1024 * 1024,
                max_pdf_pages=50,
            ),
            pipeline=pipeline,
            retention_hours=retention_hours,
            max_simultaneos=max_simultaneos,
        ),
        repositorio,
    )


def test_processamento_simultaneo_respeita_o_limite(tmp_path):
    """O README exige comportamento DEFINIDO para uploads simultâneos.

    Sem limite a vazão degrada abaixo do sequencial: medido, 6 uploads de um
    documento de 19s levaram 189s. O excedente agora espera na fila, com
    `status` `processando`, em vez de disputar CPU.
    """
    simultaneos = 0
    pico = 0
    trava = threading.Lock()

    def pipeline_lento(pdf_path, tipo):
        nonlocal simultaneos, pico
        with trava:
            simultaneos += 1
            pico = max(pico, simultaneos)
        time.sleep(0.15)
        with trava:
            simultaneos -= 1
        return {"pages": []}

    servico, repositorio = _servico(tmp_path, pipeline_lento, max_simultaneos=2)

    for numero in range(6):
        repositorio.create(
            transcricao_id=f"id{numero}",
            tipo="cartao-ponto",
            status="processando",
            pdf_path=None,
        )

    threads = [
        threading.Thread(target=servico.processar, args=(f"id{n}",)) for n in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert pico <= 2, f"até 2 em paralelo, observado {pico}"

    # e todas terminam — a fila não perde trabalho
    assert all(repositorio.get(f"id{n}").status == "concluido" for n in range(6))


def test_pdf_armazenado_nao_e_legivel_por_outros(tmp_path):
    """O arquivo guarda nome, CPF, matrícula e salário de pessoas reais."""
    servico, _ = _servico(tmp_path, lambda p, t: {"pages": []})

    origem = Path(__file__).resolve().parents[2] / "exemplos" / "payroll-03.pdf"
    with origem.open("rb") as arquivo:
        transcricao_id = servico.criar("holerite", arquivo)

    guardado = tmp_path / "pdfs" / f"{transcricao_id}.pdf"

    assert guardado.exists()
    assert oct(guardado.stat().st_mode)[-3:] == "600"
    assert oct((tmp_path / "pdfs").stat().st_mode)[-3:] == "700"


def test_permissoes_sobrevivem_a_diretorio_ja_existente(tmp_path, monkeypatch):
    """REGRESSÃO de um bug real desta mesma correção.

    A primeira versão restringia a permissão com `mkdir(mode=0o700,
    exist_ok=True)`. Mas `ensure_directories()` já cria o diretório na subida
    da aplicação, e `mkdir` NÃO altera o modo de diretório existente — então em
    produção o diretório ficava 0755, apesar do teste passar.

    O teste anterior não pegou porque nunca chamava `ensure_directories()`.
    Este chama, reproduzindo a ordem real.
    """
    from app.core.config import Settings

    configuracao = Settings(
        database_path=tmp_path / "d" / "t.db",
        storage_dir=tmp_path / "d" / "pdfs",
        max_upload_bytes=1024,
        max_pdf_pages=5,
        retention_hours=24,
        max_processamento_simultaneo=2,
        min_words_text_layer=40,
        ocr_lang="por",
        ocr_dpi=300,
        ocr_psm=6,
        log_level="WARNING",
    )

    configuracao.ensure_directories()
    configuracao.ensure_directories()  # segunda subida: diretório já existe

    assert oct(configuracao.storage_dir.stat().st_mode)[-3:] == "700"

    repositorio = TranscriptionRepository(configuracao.database_path)
    repositorio.init_db()
    assert oct(configuracao.database_path.stat().st_mode)[-3:] == "600"


def test_retencao_remove_transcricao_e_arquivo(tmp_path):
    """A política precisa ser aplicada, não só declarada."""
    servico, repositorio = _servico(
        tmp_path, lambda p, t: {"pages": []}, retention_hours=0
    )

    origem = Path(__file__).resolve().parents[2] / "exemplos" / "payroll-03.pdf"
    with origem.open("rb") as arquivo:
        transcricao_id = servico.criar("holerite", arquivo)

    guardado = tmp_path / "pdfs" / f"{transcricao_id}.pdf"
    assert guardado.exists()

    assert servico.limpar_expiradas() == 1

    assert repositorio.get(transcricao_id) is None
    assert not guardado.exists()  # o PDF sai do disco, não só do banco


def test_nome_original_do_upload_nunca_vai_para_o_disco(tmp_path):
    """Nome de arquivo costuma conter o nome da pessoa."""
    servico, _ = _servico(tmp_path, lambda p, t: {"pages": []})

    origem = Path(__file__).resolve().parents[2] / "exemplos" / "payroll-03.pdf"
    with origem.open("rb") as arquivo:
        transcricao_id = servico.criar("holerite", arquivo)

    nomes = [caminho.name for caminho in (tmp_path / "pdfs").iterdir()]
    assert nomes == [f"{transcricao_id}.pdf"]
    assert "payroll" not in nomes[0]
