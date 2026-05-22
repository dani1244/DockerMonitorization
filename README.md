# Infraestrutura Base (MQTT + Docker)

## Brief description
Este projeto consiste num sistema de **monitorização ativa** de serviços de Docker usando **MQTT** como protocolo de comunicação, tendo como principal objetivo Telemetria de estado da rede e disponibilidade dos serviços (não dados de sensores).

O Sistema disponibilizará :
-  **Broker MQTT** que centraliza as mensagens;
- **Rede Docker interna dedicada** para isolamento;
- **Containers de teste** para validar publish/subscribe;
-  **Agente** em cada container que publica heartbeat periódico; 
-  **Serviço central** que subscreve todos os tópicos e mostra o estado dos serviços em tempo real.


## Estrutura do Projeto
.
|- docker-compose.yml
|- mosquitto/
|  \- mosquitto.conf
|- .gitignore
|- README.md
\- Projetos_Guidelines_v2.pdf


## Servicos no docker-compose

| Serviço | Descrição |
|---------|-----------|
| `mosquitto` | Broker MQTT (centro das comunicações) |
| `mqtt-test-pub` | Publica mensagens de teste no tópico `infra/test` |
| `mqtt-test-sub` | Subscreve `infra/test` e mostra mensagens recebidas |
| `heartbeat-agent` | Publica heartbeat periódico no tópico `heartbeat/<service_id>` |


## Configuração

| Variável | Descrição | Default |
|----------|-----------|---------|
| `HEARTBEAT_INTERVAL` | Intervalo entre heartbeats (segundos) | 5 |
| `BROKER_HOST` | Host do broker MQTT | mosquitto |
| `BROKER_PORT` | Porta do broker MQTT | 1883 |


### Exemplo
Para alterar o intervalo de heartbeat para 10 segundos, edita o `docker-compose.yml`:
```yaml
heartbeat-agent:
  environment:
    - HEARTBEAT_INTERVAL=10
```

Depois reinicia o servico:

```bash
docker compose up -d heartbeat-agent
```


## Como executar

1. Subir infraestrutura
    ```bash
   docker compose up -d

2. Confirmar estado
   ```bash
   docker compose ps

3. Ver teste de subscrição
    ```bash
   docker compose logs --tail=50 mqtt-test-sub


## Validação esperada

Nos logs de `mqtt-test-sub` devem aparecer mensagens do tipo:

- `infra/test ping 2026-05-07T00:00:00Z`
Isto confirma que o broker esta funcional e que o fluxo pub/sub esta valido.

E o heartbeat-agent(Issue #4) publica mensagens no tópico heartbeat/<service_id> com o seguinte payload JSON:
```json
{
  "service_id": "exemplo-container",
  "timestamp": "2026-05-18T14:30:00Z",
  "status": "alive"
}

## Nota
O codigo CORE (agente heartbeat e monitor central) foi removido de proposito para manter apenas o setup base nesta etapa.



