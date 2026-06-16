# Briefing — Dashboard de Eficácia Escolar (Dash/Python)

## Contexto do Projeto
Dashboard interativo construído em Python com Dash para análise de dados de um questionário aplicado a três perfis (Aluno, Responsável, Profissional) com o objetivo de estimar a eficácia de escolas públicas do Rio Grande do Sul.

---

## Arquivos de Dados

| Arquivo | Descrição | Linhas |
|---|---|---|
| `Fatos_Respostas__1_.csv` | Tabela fato — cada linha é uma resposta | 291.289 |
| `Dimensao_Respondentes.xlsx` | Quem respondeu — perfil, escola, dados demográficos | 3.014 |
| `Dimensao_Perguntas__2_.csv` | Perguntas — texto, categoria, perfil alvo | 395 |
| `Dimensao_Escolas.csv` | Dados do Censo Escolar de cada escola | 419 |

---

## Modelo de Dados (Estrela)

```
Fatos_Respostas
├── ID_Respondente  →  Dimensao_Respondentes.ID_Respondente
├── ID_Pergunta     →  Dimensao_Perguntas.ID_Pergunta
└── CO_ENTIDADE     →  Dimensao_Escolas.CO_ENTIDADE
```

### Colunas da Fato
- `ID_Respondente`, `ID_Pergunta`, `CO_ENTIDADE`
- `Resposta_Numerica` — escala de 0 a 6
- `Resposta_Texto` — comentários abertos (nem todas as perguntas têm)
- `Importancia_Normalizada` — peso normalizado da resposta (0 a 100)

### Colunas relevantes da Dimensao_Respondentes
- `Perfil` — Aluno | Responsável | Profissional
- `Cidade da Escola`, `Nome da Escola`, `CO_ENTIDADE`
- **Demográficos gerais:** Idade, Gênero, Cor ou Raça
- **Específicos Aluno:** Modalidade de Ensino, Turno Escolar, Ano Escolar, Anos na Escola, Faixa de Renda Familiar, Auxilio Todo Jovem na Escola
- **Específicos Responsável:** Faixa de Renda Familiar, Escolaridade do Responsável, Grau de Parentesco, Familiar Estudou na Escola
- **Específicos Profissional:** Função na Escola, Escolaridade do Profissional, Carga Horária Semanal, Vínculo de Trabalho, Faixa Salarial do Profissional, Número de Escolas

### Colunas relevantes da Dimensao_Perguntas
- `ID_Pergunta`, `Pergunta_Padronizada`, `Afirmativa_Unificada`
- `Categoria` — 9 categorias temáticas (ver abaixo)
- `Perfil_Alvo` — Aluno | Responsável | Profissional

### Categorias Temáticas
1. Clima Escolar, Vínculos e Pertencimento
2. Relação Ensino-aprendizagem, Currículo e Práticas Pedagógicas
3. Gestão Escolar e Práticas Administrativas
4. Infraestrutura, Recursos Materiais e Tecnologias
5. Inclusão, Acessibilidade e Atendimento à Diversidade
6. Participação da Família e da Comunidade na Escola
7. Condições de Trabalho dos Profissionais da Educação
8. Merenda Escolar
9. Relações institucionais, Políticas Educacionais, Reformas Curriculares e Políticas Intersetoriais

---

## Estrutura do Dashboard

### Tecnologias
- **Framework:** Dash (plotly/dash)
- **Visualizações:** Plotly Express / Plotly Graph Objects
- **Tabelas:** dash_table ou dash_ag_grid
- **Estilo:** Bootstrap via dash-bootstrap-components

### Carregamento dos Dados
Carregar e fazer merge dos dados UMA VEZ na inicialização do app, antes de definir o layout:

```python
import pandas as pd

fato = pd.read_csv("Fatos_Respostas__1_.csv")
perguntas = pd.read_csv("Dimensao_Perguntas__2_.csv")
respondentes = pd.read_excel("Dimensao_Respondentes.xlsx")
escolas = pd.read_csv("Dimensao_Escolas.csv")

# Atenção: separador decimal é vírgula nos CSVs
# Converter Resposta_Numerica para float
fato['Resposta_Numerica'] = fato['Resposta_Numerica'].str.replace(',', '.').astype(float)

# DataFrame analítico completo
df = (fato
      .merge(perguntas, on='ID_Pergunta')
      .merge(respondentes, on='ID_Respondente')
      .merge(escolas[['CO_ENTIDADE', 'NO_ENTIDADE', 'NO_MUNICIPIO']], 
             left_on='CO_ENTIDADE_x', right_on='CO_ENTIDADE', how='left'))
```

> Atenção: `CO_ENTIDADE` aparece tanto na fato quanto nas dimensões — verificar sufixos `_x` e `_y` após o merge.

---

## Páginas e Conteúdo

### Página 1 — Visão Geral
**Cards de resumo:**
- Total de respondentes (com breakdown por perfil)
- Total de escolas participantes
- Total de municípios

**Gráficos:**
- Pizza ou barras horizontais: distribuição de respondentes por perfil
- Barras agrupadas: média geral por categoria temática, comparando os 3 perfis lado a lado
- Barras horizontais: top escolas por média geral de respostas

**Filtros disponíveis nesta página:**
- Dropdown: filtrar por município
- Dropdown: filtrar por escola

---

### Página 2 — Alunos
**Subaba 1 — Perfil Demográfico:**
- Distribuição por Gênero (pizza)
- Distribuição por Cor ou Raça (barras horizontais)
- Distribuição por Faixa de Renda Familiar (barras)
- Distribuição por Modalidade de Ensino (barras)
- Distribuição por Turno Escolar (pizza)
- Distribuição por Ano Escolar (barras)

**Subaba 2 — Resultados por Categoria:**
- Barras horizontais: média por categoria temática
- Ao selecionar uma categoria, exibe as perguntas individuais com suas médias

**Filtros disponíveis:**
- Dropdown: município
- Dropdown: escola
- Dropdown: modalidade de ensino
- Dropdown: turno

---

### Página 3 — Responsáveis
**Subaba 1 — Perfil Demográfico:**
- Distribuição por Gênero (pizza)
- Distribuição por Cor ou Raça (barras horizontais)
- Distribuição por Faixa de Renda Familiar (barras)
- Distribuição por Escolaridade do Responsável (barras)
- Distribuição por Grau de Parentesco (pizza)

**Subaba 2 — Resultados por Categoria:**
- Mesma estrutura da página de Alunos

**Filtros disponíveis:**
- Dropdown: município
- Dropdown: escola

---

### Página 4 — Profissionais
**Subaba 1 — Perfil Demográfico:**
- Distribuição por Função na Escola (pizza)
- Distribuição por Vínculo de Trabalho (barras)
- Distribuição por Escolaridade (barras horizontais)
- Distribuição por Faixa Salarial (barras)
- Distribuição por Carga Horária Semanal (barras)

**Subaba 2 — Resultados por Categoria:**
- Mesma estrutura da página de Alunos

**Filtros disponíveis:**
- Dropdown: município
- Dropdown: escola
- Dropdown: função na escola

---

## Observações Técnicas Importantes

1. **Separador decimal:** os CSVs usam vírgula como separador decimal (ex: `1,0` em vez de `1.0`). Converter ao carregar.

2. **CO_ENTIDADE com casas decimais:** na fato aparece como `43167764,0` — limpar antes dos merges.

3. **Turno com variação de capitalização:** `Turno Integral` e `Turno integral` aparecem como valores distintos — normalizar com `.str.strip().str.title()`.

4. **Modalidade de Ensino com sujeira:** alguns valores são claramente erros de preenchimento livre. Filtrar apenas os valores válidos: `['Ensino Fundamental', 'Ensino Médio', 'Ensino Técnico', 'EJA – Educação de Jovens e Adultos', 'Anos iniciais']`.

5. **Subabas dentro das páginas:** usar `dcc.Tabs` dentro de cada página para separar Demográfico de Resultados.

6. **Navegação entre páginas:** usar `dcc.Location` + `dcc.Link` ou `dash-bootstrap-components` navbar.

7. **Performance:** com 291k linhas, fazer os merges uma vez só na inicialização. Nos callbacks, filtrar o `df` já pronto — nunca recarregar arquivos dentro de callbacks.

---

## Paleta de Cores Sugerida
- Alunos: `#009B4E` 
- Responsáveis: `#F5C518` 
- Profissionais: `#D01020` 
- Fundo geral: branco ou cinza muito claro (`#F8F9FA`)

---

## Dependências
```
dash
dash-bootstrap-components
plotly
pandas
openpyxl
```

Instalar com:
```bash
pip install dash dash-bootstrap-components plotly pandas openpyxl
```
