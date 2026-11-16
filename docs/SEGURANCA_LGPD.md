# Segurança da informação e LGPD

O sistema trata dados cadastrais e fiscais de pessoas jurídicas e, nas
procurações, CPF de pessoas físicas (procuradores). Este documento descreve o
que está implementado, o que é responsabilidade do operador e o que
deliberadamente **não** é feito.

## 1. Controle de acesso

* **Autenticação**: JWT HS256, expiração configurável (padrão 8 h), emitido
  somente após conferência de credenciais. Token carrega usuário, organização e
  perfil; a organização do token é confrontada com a do usuário a cada chamada.
* **Senhas**: hash **bcrypt** com 12 rounds. Política mínima aplicada na criação
  e troca: 10 caracteres, com letra, número e caractere especial.
* **Força bruta**: após `MT_LOGIN_MAX_TENTATIVAS` falhas (padrão 5) a conta é
  bloqueada por `MT_LOGIN_BLOQUEIO_MINUTOS` (padrão 15). Durante o bloqueio,
  **nem a senha correta libera o acesso**; a resposta é 429 com `Retry-After`,
  e tanto as falhas quanto os bloqueios ficam na auditoria.
* **Perfis**: `ADMIN` (tudo), `ANALISTA` (escrita operacional) e `AUDITOR`
  (somente leitura, inclusive auditoria). A separação é verificada por teste
  automatizado.
* **Segregação por empresa**: toda consulta filtra por `organizacao_id`; há
  teste que tenta acessar dado de outra organização e exige `404`.

## 2. Criptografia

| Onde | Como |
|---|---|
| Em trânsito | HTTPS no proxy reverso; `Strict-Transport-Security` em produção |
| Em repouso (campos sensíveis) | `TextoCriptografado` (Fernet: AES-128-CBC + HMAC-SHA256) nas credenciais de integração e na senha do certificado |
| Em repouso (banco inteiro) | responsabilidade da infraestrutura: volume/disco cifrado ou TDE do provedor |
| Integridade de consulta | `hash_conteudo` (SHA-256) em snapshots e consultas, para detectar mudança real de conteúdo |

A chave Fernet vem de `MT_FERNET_KEY`. Em desenvolvimento, é derivada da
`MT_SECRET_KEY` — comportamento aceitável apenas fora de produção.

## 2.1 Documentos anexados

Despachos, intimações e relatórios do e-CAC costumam conter a situação fiscal
completa do contribuinte. Por isso:

* o binário **não** vai para o banco: fica em volume dedicado, fora do webroot,
  com permissão `0640`;
* o nome enviado pelo usuário nunca compõe o caminho em disco — o arquivo é
  gravado sob um identificador aleatório, o que neutraliza *path traversal*;
* o tipo é validado por extensão **e** por assinatura do conteúdo (um `.exe`
  renomeado para `.pdf` é recusado), com limite de tamanho configurável;
* cada arquivo tem **SHA-256** registrado, conferido a cada download: alteração
  no disco resulta em erro, não em entrega silenciosa de conteúdo adulterado;
* um documento pode ser marcado como **restrito** — aparece na listagem, mas o
  download exige perfil ADMIN e a tentativa negada é auditada;
* todo download registra quem baixou, quando e de qual documento;
* a exclusão é restrita a ADMIN, apaga o arquivo do disco e fica registrada.

## 3. Proteção de credenciais de terceiros

Regras aplicadas no código, não apenas na documentação:

* **Nenhuma senha gov.br é solicitada ou armazenada**, em nenhuma hipótese.
* A **chave privada do certificado digital não é persistida no banco**: guarda-se
  o caminho do arquivo em volume somente leitura e a senha, cifrada.
* `Consumer Key`/`Consumer Secret` são cifrados com Fernet quando cadastrados
  pela API, e nunca retornam em respostas.
* O diretório `certificados/` está no `.gitignore` e é montado como
  `read-only` no contêiner.
* Nenhum segredo é escrito em log: a aplicação registra apenas tipo de erro e
  mensagem do conector.

## 4. Trilha de auditoria

A tabela `audit_log` registra, com usuário, e-mail, IP, user-agent, entidade,
identificador, detalhe em JSON e data/hora:

`LOGIN`, `LOGIN_FALHA`, `TROCA_SENHA`, `LEITURA` (ficha de cliente),
`LOGIN_BLOQUEADO`, `CRIACAO`, `ALTERACAO`, `EXCLUSAO`, `IMPORTACAO_CARREGADA`,
`IMPORTACAO_CORRECAO`, `IMPORTACAO_CONFIRMADA`, `CONSULTA_FONTE`,
`RESULTADO_MANUAL`, `MONITORAMENTO`, `SIMULACAO`, `ALERTA_ACAO`, `IA_RESUMO`,
`RELATORIO_GERADO`, `DOCUMENTO_ANEXADO`, `DOCUMENTO_VISUALIZADO`,
`DOCUMENTO_ACESSO_NEGADO`, `DOCUMENTO_EXCLUIDO`.

Além dela, o histórico de negócio é imutável por construção:
`cliente_historico` (campo a campo), `compensacao_evento` (linha do tempo),
`procuracao_consulta` (toda tentativa de consulta) e
`situacao_fiscal_snapshot` (nunca sofre `UPDATE`).

## 5. Princípios da LGPD aplicados

| Princípio (art. 6º) | Implementação |
|---|---|
| Finalidade | Dados usados apenas para monitorar a situação tributária dos clientes do escritório |
| Adequação / Necessidade | Coleta restrita ao necessário: CNPJ, razão social, contato, responsável, procuração, PER/DCOMP e pendências. Não há coleta de dados pessoais sensíveis |
| Transparência | Tela "Fontes de dados" informa origem, limitações e requisitos de cada consulta; cada registro mostra fonte e data |
| Qualidade dos dados | Validação na importação, correção assistida, marcação explícita de informação desatualizada |
| Segurança | Controle de acesso, criptografia, cabeçalhos de proteção, segregação por empresa, bloqueio contra força bruta, documentos com acesso restrito |
| Prevenção | Alertas de vencimento de procuração evitam consulta sem autorização vigente |
| Responsabilização | Trilha de auditoria completa e histórico imutável |
| Não discriminação | A camada de IA não classifica pessoas; ordena clientes por gravidade de alertas, com critério publicado |

**Base legal típica**: execução de contrato com o cliente do escritório
(art. 7º, V) e cumprimento de obrigação legal/regulatória (art. 7º, II). Cabe ao
operador formalizar isso no contrato de prestação de serviços.

**Papéis**: o escritório é **controlador** dos dados de seus clientes; quem
hospeda o sistema atua como **operador**. Firmar contrato de operador quando a
hospedagem for terceirizada.

## 6. Retenção e descarte

* `MT_RETENCAO_CONSULTAS_DIAS` (padrão 1825 = 5 anos) para snapshots e consultas.
* `MT_RETENCAO_AUDITORIA_DIAS` (padrão 1825) para a trilha de auditoria.
* O expurgo deve respeitar prazos de guarda fiscal (em regra 5 anos) e eventual
  prazo processual em curso. Recomenda-se exportar antes de excluir.
* Pedido de eliminação de dados (art. 18, VI) deve ser avaliado contra a
  obrigação legal de guarda — o sistema permite desativar o cliente (`ativo=false`)
  sem destruir histórico, que costuma ser a medida adequada.

## 7. Direitos do titular

* **Acesso/portabilidade**: a API expõe todos os dados de um cliente
  (`/api/clientes/{id}`, `/api/clientes/{id}/historico`,
  `/api/situacao-fiscal/{id}/snapshots`, `/api/compensacoes?cliente_id=`),
  permitindo exportação em JSON.
* **Correção**: edição pela tela de cliente, com histórico de quem alterou.
* **Informação sobre uso compartilhado**: a tela de Fontes de dados lista todas
  as integrações ativas.

## 8. Backup e continuidade

* Backup lógico diário de **banco e anexos** com `backend/scripts/backup.sh`,
  que grava SHA-256 de cada arquivo e expurga os antigos conforme a retenção.
* **Restauração testada**: `backend/scripts/restaurar.sh` confere a integridade,
  recria o banco e recusa sobrescrever a base em uso sem confirmação explícita.
  O ciclo completo (backup → perda simulada → restauração) está documentado e
  verificado em [OPERACAO.md](OPERACAO.md); repita-o mensalmente.
* Os arquivos de certificado digital precisam de backup próprio, cifrado e
  separado das credenciais.

## 8.1 Modo homologação da integração

Para mapear os campos de um contrato novo, `MT_INTEGRA_CONTADOR_MODO_HOMOLOGACAO`
grava requisição e resposta brutas da fonte na tabela `amostra_integracao`.
Essas amostras podem conter a situação fiscal completa do contribuinte, por
isso: vêm **desligadas por padrão**, só o perfil ADMIN as acessa, o checklist de
prontidão acusa quando o modo fica ligado, e existe uma ação para apagá-las.
Desligue o modo assim que o mapeamento terminar.

## 9. O que o sistema deliberadamente NÃO faz

* Não contorna CAPTCHA, MFA ou qualquer controle de segurança de terceiros.
* Não armazena senha gov.br.
* Não acessa serviço algum sem credencial e procuração válidas configuradas.
* Não presume homologação, regularidade ou vigência de procuração sem evidência.
* Não emite parecer jurídico: toda conclusão é sinalizada para validação humana.

## 10. Recomendações adicionais para produção

1. Ativar MFA no provedor de identidade corporativo e integrar via SSO (OIDC) —
   o modelo de usuários já isola a autenticação em `app/core/security.py`.
2. Restringir o acesso à rede do banco de dados (sem porta pública).
3. Rotacionar `MT_SECRET_KEY` periodicamente (invalida sessões em aberto) e
   manter versionamento da chave Fernet antes de rotacioná-la.
4. Monitorar `audit_log` para acessos fora do horário comercial e volume anormal
   de leitura.
5. Revisar trimestralmente os perfis de acesso e as procurações vigentes.
