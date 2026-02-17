
```
enterprise-storm
├─ backend
│  ├─ alembic.ini
│  ├─ main.py
│  ├─ src
│  │  ├─ common
│  │  │  ├─ config.py
│  │  │  ├─ database
│  │  │  │  ├─ connection.py
│  │  │  │  ├─ migrations
│  │  │  │  │  ├─ env.py
│  │  │  │  │  ├─ script.py.mako
│  │  │  │  │  └─ versions
│  │  │  │  │     └─ 08bbea7fc671_rebuild_schema.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ enums.py
│  │  │  ├─ llm
│  │  │  │  ├─ client.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ models
│  │  │  │  ├─ base.py
│  │  │  │  ├─ job.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ repositories
│  │  │  │  ├─ base_repository.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ schemas
│  │  │  │  ├─ base.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ search
│  │  │  │  ├─ client.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ services
│  │  │  │  ├─ embedding.py
│  │  │  │  ├─ entity_resolver.py
│  │  │  │  └─ __init__.py
│  │  │  └─ __init__.py
│  │  ├─ company
│  │  │  ├─ engine
│  │  │  │  ├─ adapter.py
│  │  │  │  ├─ builder.py
│  │  │  │  ├─ io.py
│  │  │  │  ├─ retriever.py
│  │  │  │  ├─ storm_pipeline.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ models
│  │  │  │  ├─ analysis_report.py
│  │  │  │  ├─ company.py
│  │  │  │  ├─ generated_report.py
│  │  │  │  ├─ report_job.py
│  │  │  │  ├─ source_material.py
│  │  │  │  ├─ talent.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ repositories
│  │  │  │  ├─ analysis_report_repository.py
│  │  │  │  ├─ company_repository.py
│  │  │  │  ├─ generated_report_repository.py
│  │  │  │  ├─ report_job_repository.py
│  │  │  │  ├─ source_material_repository.py
│  │  │  │  ├─ talent_repository.py
│  │  │  │  └─ __init__.py
│  │  │  ├─ router.py
│  │  │  ├─ schemas
│  │  │  │  ├─ analysis_report.py
│  │  │  │  ├─ company.py
│  │  │  │  ├─ generated_report.py
│  │  │  │  ├─ llm_query_analysis_result.py
│  │  │  │  ├─ report_job.py
│  │  │  │  ├─ search.py
│  │  │  │  ├─ source_material.py
│  │  │  │  └─ __init__.py
│  │  │  └─ services
│  │  │     ├─ analysis_service.py
│  │  │     ├─ company_service.py
│  │  │     ├─ dart_service.py
│  │  │     ├─ generated_report_service.py
│  │  │     ├─ ingestion_service.py
│  │  │     ├─ llm_query_analyzer.py
│  │  │     ├─ quality_inspector.py
│  │  │     ├─ report_job_service.py
│  │  │     ├─ reranker_service.py
│  │  │     ├─ source_material_service.py
│  │  │     ├─ storm_service.py
│  │  │     ├─ talent_service.py
│  │  │     └─ __init__.py
│  │  ├─ resume
│  │  │  ├─ models.py
│  │  │  ├─ repositories.py
│  │  │  ├─ router.py
│  │  │  ├─ schemas.py
│  │  │  ├─ services
│  │  │  │  ├─ correction_service.py
│  │  │  │  ├─ guide_service.py
│  │  │  │  └─ __init__.py
│  │  │  └─ __init__.py
│  │  ├─ user
│  │  │  ├─ models.py
│  │  │  ├─ repositories.py
│  │  │  ├─ router.py
│  │  │  ├─ schemas.py
│  │  │  ├─ services.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  └─ __init__.py
├─ CLAUDE.md
├─ docker-compose.yml
├─ docker-credential-fake.cmd
├─ docs
├─ frontend
│  └─ react-app
│     ├─ .eslintrc.json
│     ├─ dist
│     │  ├─ assets
│     │  │  ├─ index-Bbz7mRN2.js
│     │  │  ├─ index-Bbz7mRN2.js.map
│     │  │  └─ index-D_pvcILE.css
│     │  └─ index.html
│     ├─ index.html
│     ├─ package-lock.json
│     ├─ package.json
│     ├─ src
│     │  ├─ App.jsx
│     │  ├─ components
│     │  │  ├─ Dashboard.jsx
│     │  │  └─ ReportViewer.jsx
│     │  ├─ contexts
│     │  │  ├─ AuthContext.jsx
│     │  │  └─ ResumeContext.jsx
│     │  ├─ index.css
│     │  ├─ layouts
│     │  │  └─ MainLayout.jsx
│     │  ├─ main.jsx
│     │  ├─ pages
│     │  │  ├─ CompanyAnalysis.jsx
│     │  │  ├─ Home.jsx
│     │  │  └─ ResumeCoaching.jsx
│     │  ├─ services
│     │  │  ├─ apiClient.js
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
│  ├─ demo_light
│  │  ├─ .streamlit
│  │  │  └─ config.toml
│  │  ├─ assets
│  │  │  ├─ article_display.jpg
│  │  │  ├─ create_article.jpg
│  │  │  └─ void.jpg
│  │  ├─ demo_util.py
│  │  ├─ pages_util
│  │  │  ├─ CreateNewArticle.py
│  │  │  └─ MyArticles.py
│  │  ├─ README.md
│  │  ├─ requirements.txt
│  │  ├─ stoc.py
│  │  └─ storm.py
│  ├─ encoder.py
│  ├─ examples
│  │  ├─ costorm_examples
│  │  │  └─ run_costorm_gpt.py
│  │  └─ storm_examples
│  │     ├─ helper
│  │     │  └─ process_kaggle_arxiv_abstract_dataset.py
│  │     ├─ README.md
│  │     ├─ run_storm_wiki_claude.py
│  │     ├─ run_storm_wiki_deepseek.py
│  │     ├─ run_storm_wiki_gemini.py
│  │     ├─ run_storm_wiki_gpt.py
│  │     ├─ run_storm_wiki_gpt_with_VectorRM.py
│  │     ├─ run_storm_wiki_groq.py
│  │     ├─ run_storm_wiki_mistral.py
│  │     ├─ run_storm_wiki_ollama.py
│  │     ├─ run_storm_wiki_ollama_with_searxng.py
│  │     └─ run_storm_wiki_serper.py
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
└─ scripts
   ├─ init_db.py
   ├─ run_ingestion.py
   └─ run_storm.py

```
