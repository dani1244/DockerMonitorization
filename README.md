# Tema 3 - Infraestrutura Base (MQTT + Docker)

Este repositorio esta na fase de infraestrutura base do projeto.

## O que esta incluido nesta fase

- broker MQTT Mosquitto
- rede docker interna dedicada
- dois containers de teste para validar publish/subscribe
- agente de heartbeat MQTT (Issue #4)

## Servicos no docker-compose

- `mosquitto`: broker MQTT
- `mqtt-test-pub`: publica mensagem periodica no topico `infra/test`
- `mqtt-test-sub`: subscreve `infra/test` e imprime mensagens recebidas
- `heartbeat-agent`: publica heartbeat periodico no topico `heartbeat/<service_id>`

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

## Validacao esperada

Nos logs de `mqtt-test-sub` devem aparecer mensagens tipo:

`infra/test ping 2026-05-07T00:00:00Z`

Isto confirma que o broker esta funcional e que o fluxo pub/sub esta valido.

Para heartbeat (Issue #4), e esperado payload JSON com:

- `service_id`
- `timestamp`
- `status: alive`

## Nota

O codigo CORE (agente heartbeat e monitor central) foi removido de proposito para manter apenas o setup base nesta etapa.