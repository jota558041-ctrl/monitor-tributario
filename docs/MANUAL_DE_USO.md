# Manual de utilização

## Acesso e perfis

| Perfil | Pode | Não pode |
|---|---|---|
| **ADMIN** | tudo: usuários, regras de monitoramento, consultas, importações | — |
| **ANALISTA** | importar, cadastrar, consultar fontes, tratar alertas, simular | criar usuários e regras |
| **AUDITOR** | ler tudo, inclusive a trilha de auditoria | qualquer escrita |

Usuários de demonstração estão no README. Troque a senha em produção.

---

## 1. Painel

Primeira tela após o login. Traz, com filtro por responsável:

* **Clientes**: total, com débitos, sem pendências identificadas, sem consulta
  atualizada, nunca consultados, consulta indisponível.
* **Compensações**: total monitorado, homologadas, em análise/processamento,
  não homologadas, parciais/com exigência, sem informação atualizada — com o
  valor de crédito somado por situação.
* **Procurações**: ativas, próximas do vencimento, expiradas/revogadas e em
  situação desconhecida.
* **Gráficos**: distribuição por situação, valor por situação e evolução dos
  débitos consultados ao longo do tempo.
* **Clientes que exigem atenção**: ranking pela gravidade acumulada dos alertas
  abertos, com motivos e ação sugerida. Clicar abre a ficha do cliente.

> A faixa amarela no topo indica que o sistema está em **modo demonstração**
> (conectores em `simulador`). Ela desaparece ao configurar fontes reais.

---

## 2. Importar planilha

**Caminho:** menu *Importar planilha*.

1. **Baixar modelo** (opcional) — planilha `.xlsx` com as colunas esperadas,
   exemplos e uma aba de instruções.
2. **Enviar arquivo** `.xlsx`, `.xlsm` ou `.csv` (até 20 MB).
3. **Conferir as colunas detectadas.** O sistema reconhece variações
   ("CNPJ do contribuinte", "Vencimento procuração", "PER/DCOMP"…). Colunas não
   reconhecidas aparecem como ignoradas.
4. **Revisar a validação.** Cada linha recebe uma ação:
   * `CRIAR` — cliente novo;
   * `ATUALIZAR` — CNPJ já cadastrado;
   * `DUPLICADO` — mesma PER/DCOMP repetida na planilha (não é importada);
   * `ERRO` — bloqueada (ex.: CNPJ com dígito verificador inválido).
   Avisos (amarelo) não bloqueiam: e-mail suspeito, procuração sem validade,
   PER/DCOMP sem valor, validade já vencida etc.
5. **Corrigir** o que for necessário: o botão *Corrigir* abre a linha, e ao
   salvar o sistema revalida na hora. *Ignorar* exclui a linha da importação.
6. **Confirmar importação.** Só então o cadastro é alterado. O resumo informa
   quantos clientes foram criados/atualizados e quantas procurações e PER/DCOMP
   foram registradas.

**Regras úteis**
* Só o CNPJ é obrigatório.
* Várias linhas podem ter o mesmo CNPJ — uma PER/DCOMP por linha.
* Datas aceitas: `dd/mm/aaaa`, `aaaa-mm-dd` e data nativa do Excel.
* Valores aceitos: `1.234,56`, `1234.56`, `R$ 1.234,56`.
* A coluna "Situação da compensação" é tratada como **declaração da empresa**:
  o sistema não considera homologação sem evidência de consulta à fonte.

---

## 3. Clientes

Lista com busca por CNPJ, razão social ou nome fantasia e filtro por
responsável. Dois botões no topo: **Novo cliente** (cadastro manual, com
validação do CNPJ) e **Exportar carteira (Excel)**.

Abrir um cliente mostra:

* dados cadastrais e data da última consulta de cada domínio;
* **Resumo interpretado** (motor de regras), com os limites da interpretação;
* procurações, com situação do sistema × situação declarada;
* PER/DCOMP com valores, despacho e intimação;
* histórico de consultas fiscais (clique em *Detalhar* para ver as pendências);
* comparativos entre consultas;
* alertas do cliente e histórico de alterações cadastrais.

Botões disponíveis na ficha:

| Botão | O que faz |
|---|---|
| **Consultar agora** | executa o monitoramento completo só daquele cliente |
| **Posição em PDF** | gera o relatório completo do cliente para enviar ao responsável |
| **Extrato de consultas** | planilha com todas as consultas feitas nos últimos 180 dias |
| **Editar cliente** | altera os dados cadastrais (o CNPJ não é editável) |
| **Nova procuração** / **Nova PER/DCOMP** | lançamento manual, sem planilha |

Em cada linha de procuração e de PER/DCOMP há **Editar** e, para administradores,
**Excluir**. Lançar ou editar à mão **não** valida a procuração nem muda a
situação da compensação: isso continua dependendo de consulta à fonte ou do
registro de resultado oficial.

### Documentos anexados

No bloco **Documentos anexados** é possível guardar despacho decisório,
intimação, relatório do e-CAC, comprovante de PER/DCOMP e contratos:

* tipos aceitos: PDF, PNG, JPG, XLSX, XLS, CSV, TXT e XML, até o limite exibido
  na tela (padrão 25 MB);
* o arquivo pode ser vinculado a uma PER/DCOMP específica;
* marcando **Restrito**, só administradores conseguem baixar;
* cada arquivo mostra o início do SHA-256 — é a prova de integridade, conferida
  a cada download;
* **todo download é registrado na auditoria**, com usuário e data.

---

## 4. Compensações (PER/DCOMP)

Filtros por texto, situação, tributo e período de transmissão.

As nove classificações:

| Situação | Significado |
|---|---|
| Transmitida | declaração enviada; **não** significa homologação |
| Em processamento | em processamento nos sistemas da RFB |
| Em análise | crédito sob verificação |
| Homologada | compensação homologada integralmente |
| Não homologada | compensação não homologada |
| Homologada parcialmente | há saldo não homologado |
| Cancelada | declaração cancelada/retificada |
| Com exigência/intimação | há exigência pendente de resposta |
| Sem informação atualizada | a fonte não informou — **não** é deferimento |

Ao abrir uma PER/DCOMP você vê todos os campos, o **histórico de evolução**
(cada consulta e cada mudança `de → para`, com origem e data) e dois recursos:

* **Consultar fonte agora** — dispara a consulta no conector configurado;
* **Registrar resultado oficial manualmente** — para quando não existe consulta
  automática autorizada: informe situação, despacho, valores e observação. O
  registro fica com origem `IMPORTACAO_RELATORIO` e entra no histórico.

---

## 5. Procurações eletrônicas

Semáforo:

| Cor | Significado |
|---|---|
| 🟢 **Verde** | ativa e **validada por fonte autorizada** |
| 🟡 **Amarelo** | validada e vencendo em até 30 dias |
| 🔴 **Vermelho** | expirada ou revogada conforme a fonte |
| ⚪ **Cinza** | situação desconhecida: sem validação, sem dados, indisponível ou sem autorização |

Uma procuração recém-importada é **sempre cinza**: a planilha informa o que a
empresa acredita, não o que o e-CAC confirma. Depois de uma consulta
bem-sucedida, o sistema passa a usar a situação retornada.

A tabela "Próximos vencimentos" cobre de −30 a +60 dias. Alertas são gerados a
30, 15, 7 e 0 dias (configurável), além de expiração e revogação.

---

## 6. Situação fiscal

Visão por cliente com total atual, total da consulta anterior e variação.
*Histórico* abre todas as consultas e os comparativos, que separam:

* **novos** — pendências que não existiam na consulta anterior;
* **baixados** — pendências que deixaram de constar;
* **remanescentes** — pendências que permanecem;
* **alterados** — mesma pendência com valor diferente.

Exemplo real do sistema: R$ 15.000,00 na primeira consulta e R$ 5.000,00 na
segunda → diferença de −R$ 10.000,00, acompanhada da ressalva de que a redução
**não** é automaticamente atribuída à compensação (pagamento, parcelamento,
retificação e decisões administrativas também alteram o valor).

Débitos **suspensos** e **parcelamentos** aparecem nos totais próprios, mas não
entram no total exigível.

---

## 7. Alertas

Cada alerta traz:

* criticidade (INFO → CRÍTICA) e tipo;
* mensagem objetiva;
* **"Por que este alerta foi gerado"** — a regra aplicada;
* **evidências** — fonte, data/hora da consulta, campo, valor anterior e novo.

Ações: *Marcar como resolvido*, *Em análise* ou *Ignorar*, sempre com nota de
tratamento (fica registrada com autor e data). Um alerta resolvido que volta a
ocorrer é reaberto automaticamente.

---

## 8. Monitoramento, regras e simulador

**Executar agora**: escolha o tipo (completo, procurações, compensações ou
situação fiscal) e, opcionalmente, um cliente. Ao final, o sistema informa
consultas OK, indisponíveis, não autorizadas, mudanças detectadas e alertas
gerados.

**Agendador**: lista os jobs ativos e a próxima execução de cada um.

**Regras** (ADMIN): nome, tipo, expressão cron, criticidade mínima e canais
(sistema/e-mail). Criar, pausar e reativar reprograma o agendador na hora.

**Simulador** (ambiente de teste): altera o "mundo fiscal" fictício para
verificar se os alertas disparam. Cenários disponíveis incluem homologar,
homologar parcialmente, não homologar, emitir intimação, reverter homologação,
parar de informar, revogar/vencer/renovar procuração, novo débito, reduzir
débito, quitar débitos e forçar indisponibilidade ou falta de autorização.

Fluxo recomendado: *Aplicar cenário* → *Executar monitoramento* → conferir em
**Alertas**.

---

## 9. Fontes de dados

Mostra, para cada domínio, o conector ativo, se a consulta é automatizada, se
exige certificado e procuração, os poderes necessários e **todas as limitações
declaradas**, além do status do Integra Contador. É a tela que responde
"de onde vem cada informação deste sistema".

---

## 9.1 Prontidão para produção (ADMIN)

Ainda em **Fontes de dados**, o painel **Prontidão para produção** roda um
checklist automático da configuração: chaves, banco, fontes ativas, CORS,
usuários de demonstração, bloqueio de login, agendador, e-mail e retenção.
Cada item mostra como está e o que fazer. Itens críticos devem ser zerados
antes de liberar o acesso a usuários reais.

Abaixo dele, **Amostras de homologação** lista as capturas de requisição e
resposta das fontes — úteis para mapear os campos de um contrato novo e que
devem ser apagadas ao fim do mapeamento.

## 9.2 Usuários (ADMIN)

Menu **Usuários**: criar, trocar perfil, ativar/desativar e redefinir senha.
Senha exige 10 caracteres com letra, número e caractere especial. Após 5
tentativas malsucedidas a conta fica bloqueada por 15 minutos — nesse período
nem a senha correta entra, e o bloqueio aparece na auditoria.

## 10. Auditoria

Disponível para ADMIN e AUDITOR. Registra login (inclusive falhas), leitura de
ficha de cliente, criações, alterações, exclusões, importações, consultas às
fontes, resultados manuais, simulações, resumos de IA, tratamento de alertas,
geração de relatórios e todo o ciclo dos documentos (anexo, download, acesso
negado e exclusão) — com usuário, IP, entidade afetada e detalhe.
