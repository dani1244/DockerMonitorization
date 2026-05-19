# Infraestrutura Base (MQTT + Docker)

## Descricao
Este projeto implementa monitorizacao ativa de servicos Docker usando MQTT para telemetria de estado e disponibilidade.

## Componentes
- Broker MQTT (Mosquitto)
- Rede Docker interna dedicada
- Containers de teste publish/subscribe
- Agente de heartbeat por servico
- Servico central de monitorizacao com deteccao de DOWN por timeout

## Estrutura do Projeto
.
|- docker-compose.yml
|- mosquitto/
|  \- mosquitto.conf
|- agent/
|  |- agent.py
|  |- Dockerfile
|  \- requirements.txt
|- monitor/
|  |- monitor.py
|  |- Dockerfile
|  \- requirements.txt
|- .gitignore
|- README.md
\- Projetos_Guidelines_v2.pdf

## Servicos no docker-compose
| Servico | Descricao |
|---------|-----------|
| mosquitto | Broker MQTT |
| heartbeat-agent | Publica metadata e heartbeat periodico |
| monitor | Consome topicos monitor/+/metadata e monitor/+/heartbeat |
| mqtt-test-pub | Publica mensagens de teste em infra/test |
| mqtt-test-sub | Subscreve infra/test e mostra mensagens |

## Configuracao
### Agente
| Variavel | Descricao | Default |
|----------|-----------|---------|
| HEARTBEAT_INTERVAL | Intervalo entre heartbeats (s) | 5 |
| BROKER_HOST | Host do broker MQTT | mosquitto |
| BROKER_PORT | Porta do broker MQTT | 1883 |
| SERVICE_PORT | Porta logica do servico monitorado | NA |

### Monitor
| Variavel | Descricao | Default |
|----------|-----------|---------|
| BROKER_HOST | Host do broker MQTT | mosquitto |
| BROKER_PORT | Porta do broker MQTT | 1883 |
| TIMEOUT_SECONDS | Tempo sem heartbeat para marcar DOWN (s) | 15 |
| LOG_FILE | Caminho do log do monitor | monitor.log |

## Como executar
1. Subir infraestrutura:
```bash
docker compose up -d
```

2. Confirmar estado:
```bash
docker compose ps
```

3. Ver monitor em tempo real:
```bash
docker compose logs -f monitor
```

4. Ver teste de subscricao:
```bash
docker compose logs --tail=50 mqtt-test-sub
```

## Validacao esperada
- mqtt-test-sub recebe mensagens em infra/test
- monitor mostra servicos UP quando heartbeat chega
- monitor marca servicos DOWN quando ultrapassa o timeout configurado

## Nota
Base funcional para heartbeat e monitoramento inicial. Proximas iteracoes focam em tabela de estado refinada, metricas (RTT) e testes finais.
