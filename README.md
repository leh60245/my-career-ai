```
enterprise-storm
├─ assets
│  ├─ co-storm-workflow.jpg
│  ├─ logo.svg
│  ├─ overview.svg
│  ├─ storm_naacl2024_slides.pdf
│  └─ two_stages.jpg
├─ backend
│  ├─ assets
│  │  └─ sample_report.md
│  ├─ main.py
│  ├─ storm_service.py
│  └─ __init__.py
├─ docker-compose.yml
├─ docs
│  ├─ API_SPEC.md
│  ├─ FEAT-Core-002-HybridRM-Implementation.md
│  ├─ FEAT-v2.1-dashboard-revolution.md
│  ├─ FIX-Core-002-PostProcessingBridge.md
│  └─ TEST_SUITE_DELIVERY.md
├─ examples
│  ├─ costorm_examples
│  │  └─ run_costorm_gpt.py
│  └─ storm_examples
│     ├─ helper
│     │  └─ process_kaggle_arxiv_abstract_dataset.py
│     ├─ README.md
│     ├─ run_storm_wiki_claude.py
│     ├─ run_storm_wiki_deepseek.py
│     ├─ run_storm_wiki_gemini.py
│     ├─ run_storm_wiki_gpt.py
│     ├─ run_storm_wiki_gpt_with_VectorRM.py
│     ├─ run_storm_wiki_groq.py
│     ├─ run_storm_wiki_mistral.py
│     ├─ run_storm_wiki_ollama.py
│     ├─ run_storm_wiki_ollama_with_searxng.py
│     └─ run_storm_wiki_serper.py
├─ frontend
│  └─ react-app
│     ├─ .eslintrc.json
│     ├─ index.html
│     ├─ package-lock.json
│     ├─ package.json
│     ├─ README.md
│     ├─ src
│     │  ├─ App.jsx
│     │  ├─ components
│     │  │  ├─ Dashboard.jsx
│     │  │  └─ ReportViewer.jsx
│     │  ├─ index.css
│     │  ├─ main.jsx
│     │  ├─ services
│     │  │  └─ apiService.js
│     │  └─ styles
│     │     └─ ReportViewer.css
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
│  ├─ db
│  │  ├─ postgres_connector.py
│  │  └─ __init__.py
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
│  ├─ run_ingestion.py
│  └─ run_storm.py
├─ src
│  ├─ common
│  │  ├─ config.py
│  │  ├─ embedding.py
│  │  └─ __init__.py
│  ├─ database
│  │  ├─ connection.py
│  │  ├─ migrations
│  │  │  ├─ alembic.ini
│  │  │  ├─ env.py
│  │  │  ├─ script.py.mako
│  │  │  └─ versions
│  │  │     └─ 001_initial_schema.py
│  │  ├─ models
│  │  │  ├─ analysis_report.py
│  │  │  ├─ base.py
│  │  │  ├─ company.py
│  │  │  ├─ generated_report.py
│  │  │  ├─ source_material.py
│  │  │  └─ __init__.py
│  │  ├─ repositories
│  │  │  ├─ analysis_report_repository.py
│  │  │  ├─ base_repository.py
│  │  │  ├─ company_repository.py
│  │  │  ├─ generated_report_repository.py
│  │  │  ├─ source_material_repository.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  ├─ engine
│  │  ├─ adapter.py
│  │  ├─ builder.py
│  │  ├─ io.py
│  │  └─ __init__.py
│  ├─ ingestion
│  │  ├─ dart_agent.py
│  │  ├─ embedding_worker.py
│  │  ├─ pipeline.py
│  │  └─ __init__.py
│  ├─ schemas
│  │  ├─ analysis_report.py
│  │  ├─ base.py
│  │  ├─ company.py
│  │  ├─ generated_report.py
│  │  └─ source_material.py
│  ├─ services
│  │  ├─ analysis_service.py
│  │  ├─ company_service.py
│  │  ├─ generation_service.py
│  │  ├─ vector_search_service.py
│  │  └─ __init__.py
│  └─ __init__.py
├─ start_backend.sh
└─ tests
   ├─ conftest.py
   ├─ integration
   │  ├─ test_db_connection.py
   │  ├─ test_repositories.py
   │  └─ __init__.py
   ├─ README.md
   ├─ unit
   │  ├─ test_generation_service.py
   │  └─ __init__.py
   └─ __init__.py

```