# Integração com serviços oficiais da Receita Federal

> **Resumo executivo.** Existe caminho oficial e contratável para **situação
> fiscal** e **procurações eletrônicas** (API Integra Contador, do SERPRO, com
> certificado e-CNPJ e procuração no e-CAC). **Não foi localizada API oficial
> pública para consulta de PER/DCOMP**: esse acompanhamento depende do portal
> e-CAC e, no sistema, é atendido por importação manual do resultado oficial ou
> por automação expressamente autorizada. Nada disso está ligado por padrão.

Pesquisa realizada em **16/11/2026**. Confirme o estado atual antes de contratar:
catálogos e identificadores de serviço mudam entre versões.

---

## 1. O que foi investigado

| Pergunta | Resposta encontrada |
|---|---|
| Existe API oficial para situação fiscal? | Sim — módulo **Integra-SITFIS** da API Integra Contador (SERPRO), descrito como solução para "emissão de relatórios da situação fiscal do contribuinte" |
| Existe API oficial para procurações? | Sim — módulo **Integra-Procurações**, descrito como "informações referentes a uma procuração eletrônica concedida a terceiros" |
| Existe API oficial para PER/DCOMP? | **Não localizada.** Os serviços de PER/DCOMP (consulta de processamento, despacho decisório, intimação) constam como serviços do portal **e-CAC**, sem documentação de API pública |
| Como é a autenticação? | Consumer Key + Consumer Secret em Basic (base64 de `key:secret`) **e** certificado digital **e-CNPJ ICP-Brasil (A1 `.p12`/`.pfx`) do contratante**; a resposta traz um `jwt_token` usado nas chamadas seguintes |
| Certificado e-CPF serve? | Não para o contratante: o SERPRO não dá suporte a e-CPF no Integra Contador |
| E quando quem consulta é procurador? | Existe o módulo **Autentica Procurador**: Termo de Autorização em XML assinado digitalmente, com certificado e-CPF ou e-CNPJ ICP-Brasil (A1 ou A3) do autor do pedido |
| Há limite de requisições? | Sim, previsto em contrato — o sistema já implementa *rate limiting* configurável (`MT_INTEGRA_CONTADOR_RATE_LIMIT_RPM`) |

Outros módulos citados no catálogo do Integra Contador: Integra-SN, Integra-MEI,
Integra-DCTFWeb, Integra-Sicalc, Integra-CaixaPostal, Integra-Pagamento e
Integra-Contador-Gerenciador. O status de cada serviço (em produção / em
prospecção) **diverge entre versões da página do catálogo** — verifique a página
vigente antes de planejar qualquer funcionalidade sobre eles.

### Fontes consultadas

* Catálogo de Serviços — Integra Contador (SERPRO):
  <https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/catalogo_de_servicos/>
* Visão geral / soluções — Integra Contador:
  <https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/solucoes/>
* Como autenticar na API — Integra Contador:
  <https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/quick_start/>
* Autentica Procurador — Integra Contador:
  <https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/solucoes/integra-contador-gerenciador/autenticaprocurador/>
* Serviços disponíveis no Portal e-CAC — Receita Federal:
  <https://servicos.receita.fazenda.gov.br/Servicos/servicos-ecac/default.aspx>
* SERPRO — notícias de lançamento do Integra Contador:
  <https://www.serpro.gov.br/menu/noticias/noticias-2022/integra-contador-unifica-acesso-a-informacoes-contabeis>

> **Observação de ambiente.** O domínio `apicenter.estaleiro.serpro.gov.br` está
> fora da política de rede do ambiente em que este sistema foi construído, de modo
> que as páginas acima foram consultadas por busca e não puderam ser baixadas
> integralmente aqui. Por isso **nenhum endpoint, `idSistema` ou `idServico` foi
> fixado no código**: todos vêm de configuração, preenchidos a partir da
> documentação contratual à qual o cliente tem acesso.

---

## 2. O que o sistema faz com isso

### 2.1 Nada é inventado
`app/connectors/integra_contador.py` não contém URL de produção, nome de serviço
nem formato de resposta presumido. O adaptador:

1. monta a autenticação **no formato documentado** (Basic + certificado → `jwt_token`);
2. monta o envelope documentado (`contratante`, `autorPedidoDados`, `contribuinte`,
   `pedidoDados` com `idSistema`/`idServico`/`dados`);
3. lê **de variáveis de ambiente** a URL base, a URL de token e os identificadores
   de serviço;
4. se faltar qualquer item, responde `NAO_AUTORIZADO` com o motivo — e o sistema
   trata como "não consultado", nunca como "sem pendência".

### 2.2 PER/DCOMP sem API oficial
O conector `IntegraCompensacao` declara explicitamente
`disponivel_oficialmente = False` e lista as limitações. Os caminhos legítimos
previstos no produto são:

1. **Importação manual do resultado oficial** (implementada): a tela de
   Compensações tem "Registrar resultado oficial manualmente", que grava a
   situação, despacho, intimação e valores com origem `IMPORTACAO_RELATORIO`,
   data informada e autor da informação — tudo no histórico.
2. **Automação de navegador** (Playwright) **somente** se houver autorização
   expressa do titular/procuração e se os termos de uso do serviço permitirem.
   O projeto **não implementa** contorno de CAPTCHA, de MFA ou de qualquer
   controle de segurança, e não deve ser adaptado para isso.
3. **Eventual API futura**: basta implementar um novo conector que satisfaça o
   contrato `ConectorCompensacao`; nenhuma outra parte do sistema muda.

### 2.3 Transparência para o usuário
A tela **Fontes de dados** (`GET /api/integracoes/status`) mostra, para cada
domínio: conector ativo, se é automatizado, se exige certificado e procuração,
quais poderes são necessários e **todas as limitações declaradas**.

---

## 3. Pré-requisitos para ligar a integração oficial

1. **Contrato com o SERPRO** para a API Integra Contador (produto comercial).
2. **Certificado e-CNPJ A1 ICP-Brasil** do contratante, em arquivo `.p12`/`.pfx`.
3. **Procuração eletrônica no e-CAC**, concedida por cada cliente ao CNPJ que fará
   as consultas, contemplando os serviços pretendidos (situação fiscal,
   procurações, caixa postal etc.).
4. Quando o autor do pedido for procurador: **Termo de Autorização** em XML
   assinado digitalmente (módulo Autentica Procurador).
5. Identificadores `idSistema`/`idServico` de cada serviço, extraídos do catálogo
   oficial do contrato.

### Configuração (arquivo `.env`)

```bash
MT_CONNECTOR_SITUACAO_FISCAL=integra_contador
MT_CONNECTOR_PROCURACAO=integra_contador
MT_CONNECTOR_COMPENSACAO=manual          # não há API oficial para PER/DCOMP

MT_INTEGRA_CONTADOR_ENABLED=true
MT_INTEGRA_CONTADOR_BASE_URL=<url do contrato>
MT_INTEGRA_CONTADOR_TOKEN_URL=<url de autenticação do contrato>
MT_INTEGRA_CONTADOR_CONSUMER_KEY=<área do cliente SERPRO>
MT_INTEGRA_CONTADOR_CONSUMER_SECRET=<área do cliente SERPRO>
MT_INTEGRA_CONTADOR_CERT_PATH=/certificados/ecnpj.p12
MT_INTEGRA_CONTADOR_CERT_PASSWORD=<senha do certificado>
MT_INTEGRA_CONTADOR_CONTRATANTE_CNPJ=<CNPJ do contratante>
MT_INTEGRA_CONTADOR_AUTOR_PEDIDO_CNPJ=<CNPJ/CPF do autor do pedido>
MT_IC_SITFIS_ID_SISTEMA=<catálogo oficial>
MT_IC_SITFIS_ID_SERVICO=<catálogo oficial>
MT_IC_PROCURACOES_ID_SISTEMA=<catálogo oficial>
MT_IC_PROCURACOES_ID_SERVICO=<catálogo oficial>
```

### Modo homologação (mapeamento assistido)

Antes de confiar no mapeamento, ligue:

```bash
MT_INTEGRA_CONTADOR_MODO_HOMOLOGACAO=true
```

Cada chamada passa a gravar, na tabela `amostra_integracao`, a requisição
enviada, a resposta recebida (ou o erro), o status HTTP e a duração. Consulte
em **Fontes de dados → Amostras de homologação** (perfil ADMIN) ou em
`GET /api/sistema/amostras-integracao`.

É com essas amostras que se ajusta o mapeamento real dos campos — em vez de
adivinhar o formato. **Desligue o modo e apague as amostras ao terminar**: elas
contêm dados fiscais completos do contribuinte. O checklist de prontidão para
produção acusa o modo ligado.

### Roteiro de homologação sugerido

1. Ligar a integração **para um único cliente de teste** (escopo da regra de
   monitoramento), mantendo os demais no conector `manual`.
2. Conferir em **Fontes de dados** se o status saiu de "configuração incompleta".
3. Rodar `POST /api/situacao-fiscal/{cliente}/consultar` e inspecionar o snapshot:
   a resposta bruta fica em `relatorio_bruto`/payload para mapeamento.
4. Ajustar o mapeamento de campos (`app/services/fiscal.py::normalizar_pendencias`
   e `app/services/compensacoes.py::_mapear_payload`) ao formato real do
   contrato, usando as amostras capturadas no modo homologação.
5. Só então ampliar o escopo e ativar o agendamento.

> O relatório do SITFIS é **assíncrono** (solicitação de protocolo + download).
> Ao mapear, trate o protocolo como uma consulta de duas etapas; enquanto o
> relatório não chega, o resultado correto é `INDISPONIVEL` — nunca "regular".

---

## 4. Limites éticos e legais assumidos pelo projeto

* Não contornar CAPTCHA, autenticação multifator ou qualquer controle de segurança.
* Não armazenar senha gov.br.
* Não usar credenciais de terceiros sem procuração válida e vigente.
* Respeitar limites de requisição e termos de uso dos serviços.
* Registrar em auditoria toda consulta realizada, com autor, data e resultado.
* Quando não há caminho autorizado, o correto é **declarar ausência de informação**,
  não estimar, não presumir e não "raspar" o que não se pode acessar.
