# DPU & PPM a partir da base RFT

Segundo site em Streamlit para calcular **DPU** e **PPM** usando a mesma base/regra do RFT.

## Atualização importante

O app agora possui **histórico cumulativo de uploads** em SQLite local (`dpu_ppm_historico.db`).

Modo padrão:

```text
Somar ao histórico
```

Assim, é possível carregar um arquivo de 2025, depois um de 2026, e selecionar o ano no painel lateral sem substituir a base anterior.

## Modos de importação

- `Somar ao histórico`: adiciona o arquivo à base existente.
- `Substituir período sobreposto`: apaga somente o período/posto/ano coberto pelo arquivo novo antes de salvar.
- `Reprocessar ano inteiro`: apaga o ano/posto do arquivo novo antes de salvar novamente.

## Regra de postos

- `QG09` é o posto principal e fica selecionado por padrão.
- `QG07` é opcional e só aparece quando habilitado no painel lateral.
- Qualquer outro posto existente na base é ignorado pelo app.

## Como rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```
