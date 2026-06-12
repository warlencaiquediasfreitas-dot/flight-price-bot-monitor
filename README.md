# Monitor de preço de voo

Robô para monitorar preço de passagens e enviar alerta por WhatsApp via CallMeBot.

## Rodar localmente

```bash
python -m app.main --once
```

## Rodar no GitHub Actions

Configure os secrets do repositório:

- `CALLMEBOT_PHONE`
- `CALLMEBOT_APIKEY`

Depois acesse **Actions > Monitorar passagens > Run workflow** para testar manualmente.
O agendamento automático roda aproximadamente uma vez por hora.
