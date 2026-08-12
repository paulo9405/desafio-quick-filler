/* Interface de revisão.
 *
 * REGRA DE OURO DESTE ARQUIVO: nenhuma regra de negócio aqui.
 *
 * Este script não sabe o que é uma batida ímpar, não sabe que dezembro vem
 * antes de janeiro e não procura `?` em lugar nenhum. Ele pede ao backend a
 * projeção em tabela (`/revisao`), que já vem com as colunas da planilha, a
 * severidade de cada linha e o motivo legível de cada aviso.
 *
 * O único trabalho estrutural que ele faz é aplicar `caminho -> valor` num
 * objeto JSON, e isso é genérico: não depende de o documento ser cartão de
 * ponto ou holerite.
 */

(() => {
  "use strict";

  const INTERVALO_INICIAL_MS = 1000;
  const INTERVALO_MAXIMO_MS = 5000;
  // ~5 min de espera antes de desistir. OCR de 5 páginas leva ~30 s; o teto
  // existe para a tela nunca ficar num loop infinito.
  const TENTATIVAS_MAXIMAS = 90;

  const estado = {
    id: null,
    tipo: null,
    value: null,
    salvando: false,
    pendente: false,
  };

  const el = (id) => document.getElementById(id);

  const secaoEnvio = el("secao-envio");
  const secaoStatus = el("secao-status");
  const secaoRevisao = el("secao-revisao");
  const alertaErro = el("alerta-erro");
  const spinner = el("spinner");
  const statusTitulo = el("status-titulo");
  const statusDetalhe = el("status-detalhe");
  const estadoSalvamento = el("estado-salvamento");

  // ----------------------------------------------------------------- envio

  el("form-envio").addEventListener("submit", async (evento) => {
    evento.preventDefault();

    const arquivo = el("arquivo").files[0];
    if (!arquivo) return;

    const dados = new FormData();
    dados.append("arquivo", arquivo);
    dados.append("tipo", el("tipo").value);

    el("botao-enviar").disabled = true;
    mostrarProcessando();

    try {
      const resposta = await fetch("/api/transcricoes", { method: "POST", body: dados });
      const corpo = await resposta.json();

      if (resposta.status !== 202) {
        // O backend devolve mensagem legível em `detail` para 4xx.
        mostrarErro(corpo.detail || "Não foi possível enviar o arquivo.");
        return;
      }

      estado.id = corpo.id;
      acompanhar();
    } catch (erro) {
      mostrarErro("Falha de rede ao enviar o arquivo.");
    } finally {
      el("botao-enviar").disabled = false;
    }
  });

  el("botao-novo").addEventListener("click", () => window.location.reload());

  // ------------------------------------------------------------ polling

  async function acompanhar() {
    let intervalo = INTERVALO_INICIAL_MS;

    for (let tentativa = 0; tentativa < TENTATIVAS_MAXIMAS; tentativa++) {
      await esperar(intervalo);
      // Recuo progressivo: consultas frequentes no começo, espaçadas depois.
      intervalo = Math.min(intervalo * 1.3, INTERVALO_MAXIMO_MS);

      let transcricao;
      try {
        const resposta = await fetch(`/api/transcricoes/${estado.id}`);
        transcricao = await resposta.json();
      } catch (erro) {
        continue; // falha de rede pontual não encerra o acompanhamento
      }

      if (transcricao.status === "concluido") {
        estado.tipo = transcricao.tipo;
        estado.value = transcricao.value;
        await abrirRevisao();
        return;
      }

      if (transcricao.status === "erro") {
        mostrarErro(transcricao.erro || "O processamento falhou.");
        return;
      }

      statusDetalhe.textContent =
        `Processando há ${Math.round(((tentativa + 1) * intervalo) / 1000)}s. ` +
        "Documentos escaneados passam por OCR e demoram mais.";
    }

    mostrarErro(
      "O processamento está demorando mais que o esperado. " +
        "Atualize a página para consultar novamente."
    );
  }

  const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

  // ----------------------------------------------------------- revisão

  async function abrirRevisao() {
    const resposta = await fetch(`/api/transcricoes/${estado.id}/revisao`);
    if (!resposta.ok) {
      mostrarErro("Não foi possível montar a tabela de revisão.");
      return;
    }

    const revisao = await resposta.json();
    renderizarTabela(revisao);

    el("visualizador-pdf").src = `/api/transcricoes/${estado.id}/arquivo`;

    secaoEnvio.classList.add("d-none");
    secaoStatus.classList.add("d-none");
    secaoRevisao.classList.remove("d-none");
  }

  function renderizarTabela(revisao) {
    const tabela = document.createElement("table");
    tabela.className = "table table-sm table-bordered mb-0";

    const cabecalho = document.createElement("thead");
    const linhaCabecalho = document.createElement("tr");
    revisao.colunas.forEach((coluna) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = coluna;
      linhaCabecalho.appendChild(th);
    });
    cabecalho.appendChild(linhaCabecalho);
    tabela.appendChild(cabecalho);

    const corpo = document.createElement("tbody");
    revisao.linhas.forEach((linha) => {
      const tr = document.createElement("tr");

      if (linha.severidade) {
        tr.classList.add(`linha-${linha.severidade}`);
      }
      if (linha.motivos.length) {
        // O motivo legível vem pronto do backend.
        tr.title = linha.motivos.join(" ");
        tr.classList.add("celula-motivo");
      }

      linha.celulas.forEach((celula) => {
        const td = document.createElement("td");
        const campo = document.createElement("input");
        campo.type = "text";
        campo.value = celula.valor;

        if (celula.caminho) {
          campo.dataset.caminho = celula.caminho;
          campo.addEventListener("change", aoCorrigirCelula);
        } else {
          // Sem campo correspondente no JSON: não há o que corrigir.
          campo.readOnly = true;
          campo.tabIndex = -1;
        }

        td.appendChild(campo);
        tr.appendChild(td);
      });

      corpo.appendChild(tr);
    });

    tabela.appendChild(corpo);

    const area = el("area-tabela");
    area.innerHTML = "";
    area.appendChild(tabela);

    atualizarResumo(revisao);
  }

  function atualizarResumo(revisao) {
    const total = revisao.linhas.length;
    const marcadas = revisao.linhas.filter((l) => l.severidade).length;

    el("resumo-avisos").textContent = marcadas
      ? `${total} linhas · ${marcadas} precisam de atenção`
      : `${total} linhas · nenhum problema detectado`;
  }

  // ------------------------------------------------------------- edição

  async function aoCorrigirCelula(evento) {
    const campo = evento.target;
    aplicarNoCaminho(estado.value, campo.dataset.caminho, campo.value);
    await salvar();
  }

  /* Aplica `valor` no caminho `pages.0.days.3.time_hhmm` dentro de `objeto`.
   * Genérico de propósito: não conhece a estrutura de nenhum tipo de
   * documento. */
  function aplicarNoCaminho(objeto, caminho, valor) {
    const partes = caminho.split(".");
    let atual = objeto;

    for (let i = 0; i < partes.length - 1; i++) {
      atual = atual[chave(partes[i])];
      if (atual === undefined) return;
    }

    atual[chave(partes[partes.length - 1])] = valor;
  }

  const chave = (parte) => (/^\d+$/.test(parte) ? Number(parte) : parte);

  async function salvar() {
    if (estado.salvando) {
      estado.pendente = true;
      return;
    }

    estado.salvando = true;
    marcarSalvamento("Salvando…", "text-bg-warning");

    try {
      const resposta = await fetch(`/api/transcricoes/${estado.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: estado.value }),
      });

      if (!resposta.ok) {
        marcarSalvamento("Erro ao salvar", "text-bg-danger");
        return;
      }

      marcarSalvamento("Salvo", "text-bg-success");

      // Recarrega a avaliação: a correção pode ter resolvido — ou criado — um
      // aviso. Quem decide isso continua sendo o backend.
      const revisao = await (await fetch(`/api/transcricoes/${estado.id}/revisao`)).json();
      renderizarTabela(revisao);
    } catch (erro) {
      marcarSalvamento("Erro ao salvar", "text-bg-danger");
    } finally {
      estado.salvando = false;
      if (estado.pendente) {
        estado.pendente = false;
        salvar();
      }
    }
  }

  function marcarSalvamento(texto, classe) {
    estadoSalvamento.textContent = texto;
    estadoSalvamento.className = `badge border ${classe}`;
  }

  // ------------------------------------------------------------ download

  document.querySelectorAll("[data-formato]").forEach((botao) => {
    botao.addEventListener("click", () => {
      // O backend gera a planilha a partir do `value` persistido, que já
      // recebeu as correções via PUT.
      window.location.href =
        `/api/transcricoes/${estado.id}/planilha?formato=${botao.dataset.formato}`;
    });
  });

  // --------------------------------------------------------------- estados

  function mostrarProcessando() {
    alertaErro.classList.add("d-none");
    spinner.classList.remove("d-none");
    statusTitulo.textContent = "Processando…";
    statusDetalhe.textContent =
      "Documentos escaneados passam por OCR e podem levar alguns minutos.";
    secaoStatus.classList.remove("d-none");
  }

  function mostrarErro(mensagem) {
    spinner.classList.add("d-none");
    statusTitulo.textContent = "Não foi possível transcrever este documento";
    statusDetalhe.textContent = "";
    alertaErro.textContent = mensagem;
    alertaErro.classList.remove("d-none");
    secaoStatus.classList.remove("d-none");
  }
})();
