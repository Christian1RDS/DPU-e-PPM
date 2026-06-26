# DPU & PPM a partir da base RFT

Segundo site em Streamlit para calcular **DPU** e **PPM** usando a mesma base/regra do RFT.

## Objetivo

Este app calcula:

- RFT %
- DPU
- PPM por defeito
- PPM por peça não RFT
- total inspecionado
- peças RFT
- peças não RFT
- total de defeitos

## Critério usado

O cálculo usa as colunas padrão da base RFT:

- `NR_WO`
- `DT_HR_INSPECAO`
- `C_DPU_QG_AMARELO`
- `CD_POSTO_CN`

Regras:

```text
Total inspecionado = quantidade de NR_WO únicos
Total de defeitos = soma de C_DPU_QG_AMARELO por NR_WO
Peça RFT = NR_WO com soma de defeitos igual a 0
Peça não RFT = NR_WO com soma de defeitos maior que 0
RFT % = peças RFT / total inspecionado × 100
DPU = total de defeitos / total inspecionado
PPM por defeito = DPU × 1.000.000
PPM por peça não RFT = peças não RFT / total inspecionado × 1.000.000
```

## Como rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Como usar com o site RFT atual

Opção 1: colocar o arquivo `rft_v61_local.db` na mesma pasta deste app e selecionar **Banco SQLite do site RFT**.

Opção 2: exportar/carregar uma base `.xlsx`, `.xls` ou `.csv` contendo as colunas exigidas.

## Deploy no Streamlit Community Cloud

No GitHub, deixe os arquivos assim:

```text
app.py
requirements.txt
README.md
.gitignore
```

Depois, no Streamlit Community Cloud, selecione:

```text
Main file path: app.py
```
