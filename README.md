
```
enterprise-storm
├─ backend
│  ├─ assets
│  │  └─ sample_report.md
│  ├─ main.py
│  ├─ storm_service.py
│  └─ __init__.py
├─ docker-compose.yml
├─ examples
│  ├─ costorm_examples
│  │  └─ run_costorm_gpt.py
│  └─ storm_examples
│     ├─ helper
│     │  └─ process_kaggle_arxiv_abstract_dataset.py
│     ├─ README.md
│     ├─ run_storm_wiki_claude.py
├─ frontend
│  └─ react-app
│     └─ vite.config.js
├─ knowledge_storm
│  ├─ collaborative_storm
│  │  ├─ engine.py
│  │  ├─ modules
│  │  │  ├─ article_generation.py
│  │  │  ├─ callback.py
│  │  │  ├─ collaborative_storm_utils.py
│  │  │  ├─ costorm_expert_utterance_generator.py
│  │  │  ├─ co_storm_agents.py
│  │  │  ├─ expert_generation.py
│  │  │  ├─ grounded_question_answering.py
│  │  │  ├─ grounded_question_generation.py
│  │  │  ├─ information_insertion_module.py
│  │  │  ├─ knowledge_base_summary.py
│  │  │  ├─ simulate_user.py
│  │  │  ├─ warmstart_hierarchical_chat.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  ├─ dataclass.py
│  ├─ encoder.py
│  ├─ interface.py
│  ├─ lm.py
│  ├─ logging_wrapper.py
│  ├─ rm.py
│  ├─ storm_wiki
│  │  ├─ engine.py
│  │  ├─ modules
│  │  │  ├─ article_generation.py
│  │  │  ├─ article_polish.py
│  │  │  ├─ callback.py
│  │  │  ├─ knowledge_curation.py
│  │  │  ├─ outline_generation.py
│  │  │  ├─ persona_generator.py
│  │  │  ├─ retriever.py
│  │  │  ├─ storm_dataclass.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  ├─ utils.py
│  └─ __init__.py
├─ pyproject.toml
├─ pytest.ini
├─ README.md
├─ requirements.txt
├─ scripts
│  ├─ init_db.py
│  ├─ run_ingestion.py
│  └─ run_storm.py
├─ src
│  ├─ common
│  │  ├─ config.py
│  │  ├─ embedding.py
│  │  ├─ entity_resolver.py
│  │  ├─ enums.py
│  │  └─ __init__.py
│  ├─ database
│  │  ├─ connection.py
│  │  ├─ migrations
│  │  │  ├─ alembic.ini
│  │  │  ├─ env.py
│  │  │  ├─ script.py.mako
│  │  │  └─ versions
│  │  │     └─ 001_initial_schema.py
│  │  └─ __init__.py
│  ├─ engine
│  │  ├─ adapter.py
│  │  ├─ builder.py
│  │  ├─ io.py
│  │  ├─ README.md
│  │  ├─ retriever.py
│  │  └─ __init__.py
│  ├─ models
│  │  ├─ analysis_report.py
│  │  ├─ base.py
│  │  ├─ company.py
│  │  ├─ generated_report.py
│  │  ├─ report_job.py
│  │  ├─ source_material.py
│  │  └─ __init__.py
│  ├─ repositories
│  │  ├─ analysis_report_repository.py
│  │  ├─ base_repository.py
│  │  ├─ company_repository.py
│  │  ├─ generated_report_repository.py
│  │  ├─ report_job_repository.py
│  │  ├─ source_material_repository.py
│  │  └─ __init__.py
│  ├─ schemas
│  │  ├─ analysis_report.py
│  │  ├─ base.py
│  │  ├─ company.py
│  │  ├─ generated_report.py
│  │  ├─ llm_query_analysis_result.py
│  │  ├─ report_job.py
│  │  ├─ request.py
│  │  ├─ search.py
│  │  ├─ source_material.py
│  │  └─ __init__.py
│  ├─ services
│  │  ├─ analysis_service.py
│  │  ├─ company_service.py
│  │  ├─ dart_service.py
│  │  ├─ generation_service.py
│  │  ├─ ingestion_service.py
│  │  ├─ llm_query_analyzer.py
│  │  ├─ reranker_service.py
│  │  ├─ source_material_service.py
│  │  └─ __init__.py
│  └─ __init__.py
├─ start_backend.sh
├─ tests
│  ├─ conftest.py
│  ├─ integration
│  │  ├─ test_db_connection.py
│  │  ├─ test_repositories.py
│  │  └─ __init__.py
│  ├─ README.md
│  ├─ unit
│  │  ├─ test_generation_service.py
│  │  └─ __init__.py
│  └─ __init__.py

## Database schema notes

- `src/database/migrations` is kept for developer use only (local schema checks, experiments).
- Production or shared environments should use a controlled migration process, but this repo does not enforce Alembic at runtime.
- For local runs without Alembic, set `AUTO_CREATE_SCHEMA=1` to create tables from models at startup.


```