# StudyFlow Backend

Backend em Python (FastAPI) para a plataforma de estudos para concursos.

## Requisitos

- Python 3.11+
- pip

## Instalação

```bash
cd studyflow-backend

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env e coloque sua ANTHROPIC_API_KEY
```

## Rodando localmente

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse a documentação automática em: http://localhost:8000/docs

## Endpoints disponíveis

### PDF
- `POST /pdf/processar` — Envia um PDF, recebe o markdown com highlights + nível de domínio
- `POST /pdf/nivel-dominio` — Versão leve, só as métricas (sem o markdown)

### Trilha
- `POST /trilha/gerar` — Envia o perfil do aluno, recebe a trilha de 2 semanas gerada pela IA
- `GET /trilha/status` — Verifica se a chave da IA está configurada

### Perfil
- `GET /perfil/materias-base` — Lista as matérias base da Área Fiscal

## Como o Lovable vai se conectar

No frontend (Lovable), as chamadas serão feitas via fetch para `http://localhost:8000` enquanto estiver local.
Quando subir para produção, basta trocar a URL base para o servidor hospedado (Railway, Render, etc).

## Próximos passos

- [ ] Integrar banco de questões
- [ ] Adicionar parser de editais (PDF do edital → matérias mapeadas)
- [ ] Persistir perfil e progresso do aluno no SQLite local
- [ ] Conectar Google Drive para monitorar pasta de PDFs
