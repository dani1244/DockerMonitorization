# Tema 3 - Infraestrutura Base (MQTT + Docker)

Este repositorio esta na fase de infraestrutura base do projeto.

## O que esta incluido nesta fase

- broker MQTT Mosquitto
- rede docker interna dedicada
- dois containers de teste para validar publish/subscribe
- agente de heartbeat MQTT (Issue #4)
- monitor de estado MQTT com deteccao de DOWN por timeout (Issue #6)

## Servicos no docker-compose

- `mosquitto`: broker MQTT
- `mqtt-test-pub`: publica mensagem periodica no topico `infra/test`
- `mqtt-test-sub`: subscreve `infra/test` e imprime mensagens recebidas
- `heartbeat-agent`: publica heartbeat periodico no topico `heartbeat/<service_id>`
- `mqtt-monitor-service`: consome `heartbeat/#` e marca servicos DOWN por timeout

## Estrutura atual

.
|- docker-compose.yml
|- mosquitto/
|  \- mosquitto.conf
|- .gitignore
|- README.md
\- Projetos_Guidelines_v2.pdf

## Como executar

1. Subir infraestrutura

   docker compose up -d

2. Confirmar estado

   docker compose ps

3. Ver teste de subscricao

   docker compose logs --tail=50 mqtt-test-sub

## Configuracao

O agente de heartbeat pode ser configurado com variaveis de ambiente:

- `HEARTBEAT_INTERVAL`: Intervalo em segundos (default: 5)
- `BROKER_HOST`: Host do broker MQTT (default: mosquitto)
- `BROKER_PORT`: Porta do broker MQTT (default: 1883)

O monitor pode ser configurado com variaveis de ambiente:

- `DOWN_TIMEOUT`: Tempo maximo sem heartbeat antes de marcar DOWN (default: 10)

### Exemplo

Para alterar o intervalo de heartbeat para 10 segundos, edita o `docker-compose.yml`:

```yaml
heartbeat-agent:
  environment:
    - HEARTBEAT_INTERVAL=10
```

Depois rebota o servico:

```bash
docker compose up -d heartbeat-agent
```

## Validacao esperada

Nos logs de `mqtt-test-sub` devem aparecer mensagens tipo:

`infra/test ping 2026-05-07T00:00:00Z`

Isto confirma que o broker esta funcional e que o fluxo pub/sub esta valido.

Para heartbeat (Issue #4), e esperado payload JSON com:

- `service_id`
- `timestamp`
- `status: alive`

Para monitor (Issue #6), o estado muda para `DOWN` quando um servico
fica sem heartbeat por mais de 10 segundos (ou valor configurado em `DOWN_TIMEOUT`).

## Nota

Esta base ja inclui os componentes centrais de heartbeat e monitoramento inicial.
As proximas iteracoes focam em refinamento de estado, metricas e testes finais.