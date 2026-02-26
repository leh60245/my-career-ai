# STORM (Synthesis of Topic Outlines through Retrieval and Multi-perspective question asking) 기술 보고서

> **문서 버전**: 1.0  
> **작성일**: 2026-02-25  
> **원 논문**: [Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models (NAACL 2024)](https://arxiv.org/pdf/2402.14207.pdf)  
> **코드베이스**: `knowledge_storm/storm_wiki/`

---

## 1. 개요

STORM은 Stanford NLP 그룹이 개발한 **자동 위키피디아 스타일 문서 생성 프레임워크**입니다. 핵심 아이디어는 인간 작가가 긴 문서를 작성할 때 수행하는 **사전 조사(pre-writing) 과정**을 LLM 에이전트의 다중 관점(Multi-Perspective) 대화 시뮬레이션으로 자동화한 것입니다.

### 1.1 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **Multi-Perspective** | 단일 관점이 아닌 다양한 페르소나(편집자)가 각각 다른 각도에서 주제를 탐구 |
| **Information-Seeking Conversation** | 위키 작가(Writer)와 주제 전문가(Expert) 간의 대화를 시뮬레이션하여 정보 수집 |
| **Grounded Generation** | 모든 서술이 검색 결과 기반 인용(`[1]`, `[2]`)으로 뒷받침됨 |
| **Outline-First** | 대화에서 수집된 정보를 기반으로 아웃라인을 먼저 생성한 후 본문 작성 |

### 1.2 4단계 파이프라인 구조

```
[Topic] → Stage 1: Persona Generation
        → Stage 2: Knowledge Curation (Multi-Perspective Conversation)
        → Stage 3: Outline Generation
        → Stage 4: Article Generation & Polishing
        → [Final Article]
```

---

## 2. 아키텍처 상세

### 2.1 클래스 계층 구조

```
Engine (Abstract)
  └── STORMWikiRunner
        ├── STORMWikiLMConfigs (LLM 구성)
        │     ├── conv_simulator_lm   → TopicExpert 역할
        │     ├── question_asker_lm   → WikiWriter + PersonaGenerator 역할
        │     ├── outline_gen_lm      → OutlineGeneration 역할
        │     ├── article_gen_lm      → ArticleGeneration 역할
        │     └── article_polish_lm   → ArticlePolishing 역할
        │
        ├── StormKnowledgeCurationModule
        │     ├── StormPersonaGenerator
        │     │     └── CreateWriterWithPersona
        │     └── ConvSimulator
        │           ├── WikiWriter (질문자)
        │           └── TopicExpert (답변자)
        │
        ├── StormOutlineGenerationModule
        │     └── WriteOutline
        │
        ├── StormArticleGenerationModule
        │     └── ConvToSection
        │
        └── StormArticlePolishingModule
              └── PolishPageModule
```

### 2.2 LLM 역할 분배

STORM은 파이프라인의 각 단계에 서로 다른 LLM을 할당하여 비용-품질 균형을 최적화합니다.

| LLM Config 속성 | 기본 모델 | 담당 역할 | max_tokens |
|-----------------|----------|----------|------------|
| `conv_simulator_lm` | gpt-4o-mini | TopicExpert 답변 생성 | 500 |
| `question_asker_lm` | gpt-4o-mini | WikiWriter 질문, Persona 생성 | 500 |
| `outline_gen_lm` | gpt-4o | 아웃라인 생성/개선 | 400 |
| `article_gen_lm` | gpt-4o-mini | 섹션별 본문 생성 | 700 |
| `article_polish_lm` | gpt-4o | 최종 폴리싱, 중복 제거 | 4,000 |

### 2.3 주요 설정 파라미터 (`STORMWikiRunnerArguments`)

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `max_conv_turn` | 3 | 각 페르소나별 대화 최대 턴 수 |
| `max_perspective` | 3 | 생성할 페르소나 최대 수 |
| `max_search_queries_per_turn` | 3 | 턴당 최대 검색 쿼리 수 |
| `search_top_k` | 3 | 쿼리당 상위 검색 결과 수 |
| `retrieve_top_k` | 3 | 섹션 생성 시 참조할 최대 레퍼런스 수 |
| `max_thread_num` | 10 | 병렬 처리 최대 스레드 수 |

---

## 3. Stage 1: 페르소나 생성 (Persona Generation)

### 3.1 목적

주제에 대해 다양한 관점을 포착할 수 있는 "가상 위키피디아 편집자" 목록을 동적으로 생성합니다. 이를 통해 단일 관점으로는 놓칠 수 있는 측면을 포괄적으로 커버합니다.

### 3.2 실행 흐름

```
Topic → FindRelatedTopic(LLM) → Wikipedia URL 목록
      → 각 URL에서 ToC(목차) 크롤링
      → GenPersona(LLM + ToC examples) → Persona 목록
      → "Basic fact writer" 기본 페르소나 추가
```

### 3.3 역할 프롬프트 상세

#### 3.3.1 `FindRelatedTopic` (dspy.Signature)

> **역할**: 주제와 관련된 위키피디아 페이지 URL을 찾아 구조적 영감을 제공

```
System Prompt (Signature docstring):
─────────────────────────────────────
"I'm writing a Wikipedia page for a topic mentioned below.
 Please identify and recommend some Wikipedia pages on closely
 related subjects. I'm looking for examples that provide
 insights into interesting aspects commonly associated with
 this topic, or examples that help me understand the typical
 content and structure included in Wikipedia pages for similar
 topics.
 Please list the urls in separate lines."

Input:
  - Topic of interest: {topic}

Output:
  - related_topics (위키피디아 URL 목록)
```

**동작**: LLM이 주제와 관련된 위키피디아 URL을 제안하면, 시스템이 각 URL에 HTTP 요청을 보내 `<h2>`~`<h6>` 태그에서 목차(Table of Contents)를 추출합니다. 이 목차는 다음 단계인 페르소나 생성의 참고 자료로 활용됩니다.

#### 3.3.2 `GenPersona` (dspy.Signature)

> **역할**: 주제에 대해 다양한 관점을 대표하는 편집자 그룹 선정

```
System Prompt (Signature docstring):
─────────────────────────────────────
"You need to select a group of Wikipedia editors who will
 work together to create a comprehensive article on the topic.
 Each of them represents a different perspective, role, or
 affiliation related to this topic. You can use other Wikipedia
 pages of related topics for inspiration. For each editor,
 add a description of what they will focus on.
 Give your answer in the following format:
 1. short summary of editor 1: description
 2. short summary of editor 2: description
 ..."

Input:
  - Topic of interest: {topic}
  - Wiki page outlines of related topics for inspiration:
    {관련 위키 페이지 목차들}

Output:
  - personas (편집자 목록)
```

**동작**: LLM이 생성한 편집자 목록에 **기본 페르소나**("Basic fact writer: Basic fact writer focusing on broadly covering the basic facts about the topic.")가 리스트 맨 앞에 추가됩니다. 최종 페르소나 수는 `max_perspective + 1`개입니다.

---

## 4. Stage 2: 지식 큐레이션 (Knowledge Curation)

### 4.1 목적

각 페르소나의 관점에서 주제에 대한 **정보 탐색 대화(Information-Seeking Conversation)**를 시뮬레이션하여, 검색 기반의 근거 있는(grounded) 정보를 체계적으로 수집합니다.

### 4.2 Multi-Perspective Conversation Simulation 구조

각 페르소나별로 독립적인 대화가 **병렬 스레드**로 실행됩니다:

```
┌─ Persona 1 ("Basic fact writer") ──────────────────────┐
│  Turn 1: WikiWriter(질문) → TopicExpert(검색+답변)      │
│  Turn 2: WikiWriter(후속질문) → TopicExpert(검색+답변)   │
│  Turn 3: WikiWriter(후속질문) → TopicExpert(검색+답변)   │
│  → "Thank you so much for your help!" (대화 종료)       │
└─────────────────────────────────────────────────────────┘

┌─ Persona 2 ("Technology analyst") ─────────────────────┐
│  Turn 1-3: 동일 구조, 다른 관점의 질문/답변              │
└─────────────────────────────────────────────────────────┘

┌─ Persona 3 ("Industry historian") ─────────────────────┐
│  Turn 1-3: 동일 구조, 다른 관점의 질문/답변              │
└─────────────────────────────────────────────────────────┘
```

### 4.3 대화 참여자별 역할 프롬프트

#### 4.3.1 `WikiWriter` — 질문자 역할

두 가지 프롬프트 변형이 존재합니다:

**(A) `AskQuestionWithPersona`** (페르소나가 존재할 때)

```
System Prompt:
─────────────────────────────────────
"You are an experienced Wikipedia writer and want to edit
 a specific page. Besides your identity as a Wikipedia writer,
 you have specific focus when researching the topic.
 Now, you are chatting with an expert to get information.
 Ask good questions to get more useful information.
 When you have no more question to ask, say
 'Thank you so much for your help!' to end the conversation.
 Please only ask a question at a time and don't ask what
 you have asked before. Your questions should be related
 to the topic you want to write."

Input:
  - Topic you want to write: {topic}
  - Your persona besides being a Wikipedia writer: {persona}
  - Conversation history: {이전 대화 내역}

Output:
  - question (다음 질문)
```

**(B) `AskQuestion`** (페르소나 없이 기본 모드)

```
System Prompt:
─────────────────────────────────────
"You are an experienced Wikipedia writer. You are chatting
 with an expert to get information for the topic you want
 to contribute. Ask good questions to get more useful
 information relevant to the topic.
 When you have no more question to ask, say
 'Thank you so much for your help!' to end the conversation.
 Please only ask a question at a time and don't ask what
 you have asked before."

Input:
  - Topic you want to write: {topic}
  - Conversation history: {이전 대화 내역}

Output:
  - question
```

**대화 히스토리 관리 전략**:

- 최근 4개 턴: 전체 답변 포함
- 그 이전 턴: `"Expert: Omit the answer here due to space limit."` 로 요약 (토큰 절약)
- 전체 대화 히스토리를 최대 2,500 단어로 제한

#### 4.3.2 `TopicExpert` — 답변자 역할 (3단계 파이프)

TopicExpert는 단순한 답변자가 아니라, 내부적으로 **3단계 파이프**를 실행합니다:

```
Question → (1) QuestionToQuery → (2) Retriever.retrieve() → (3) AnswerQuestion
```

**(1) `QuestionToQuery`** — 질문을 검색 쿼리로 변환

```
System Prompt:
─────────────────────────────────────
"You want to answer the question using Google search.
 What do you type in the search box?
 Write the queries you will use in the following format:
 - query 1
 - query 2
 ...
 - query n

 Important: When the topic involves recent events, financials,
 or news, include the current year or recent date range in
 your queries to find the most up-to-date information.
 For Korean companies, also include Korean keywords."

Input:
  - Topic you are discussing about: {topic}
  - Question you want to answer: {question}

Output:
  - queries (검색 쿼리 목록, 최대 max_search_queries_per_turn개)
```

**(2) Retriever** — 검색 실행

생성된 쿼리를 `dspy.Retrieve` 기반 검색 모듈(SerperRM, YouRM, 또는 HybridRM)로 전달하여 웹 검색 결과를 수집합니다. 각 결과는 `Information` 객체(url, title, snippets, description)로 구조화됩니다.

**(3) `AnswerQuestion`** — 검색 결과 기반 답변 생성

```
System Prompt:
─────────────────────────────────────
"You are an expert who can use information effectively.
 You are chatting with a Wikipedia writer who wants to write
 a Wikipedia page on topic you know. You have gathered the
 related information and will now use the information to
 form a response.
 Make your response as informative as possible, ensuring
 that every sentence is supported by the gathered information.
 If the [gathered information] is not directly related to
 the [topic] or [question], provide the most relevant answer
 based on the available information. If no appropriate answer
 can be formulated, respond with 'I cannot answer this
 question based on the available information,' and explain
 any limitations or gaps.

 Important guidelines for interpreting numerical data:
   - When information contains tables or numerical values,
     ALWAYS check for meta information at the end
     (units, legends, base dates, currency).
   - Apply these meta details correctly when interpreting numbers.

 Important guidelines for recency:
   - Always prefer the most recent data.
   - State dates explicitly (e.g., '2025년 3분기')."

Input:
  - Topic you are discussing about: {topic}
  - Question: {question}
  - Gathered information: {검색 결과 snippets}

Output:
  - answer (인용 포함 답변)

Output Prefix:
  "Now give your response. (Try to use as many different
   sources as possible and do not hallucinate.)"
```

### 4.4 최종 산출물: StormInformationTable

모든 페르소나별 대화가 완료되면, 전체 대화 히스토리에서 수집된 검색 결과를 URL 기반으로 중복 제거하여 `StormInformationTable`로 통합합니다.

```python
# 데이터 구조
StormInformationTable:
  conversations: List[(persona, List[DialogueTurn])]
  url_to_info: Dict[url → Information(url, title, snippets, description)]
```

---

## 5. Stage 3: 아웃라인 생성 (Outline Generation)

### 5.1 목적

수집된 대화 정보를 기반으로 기사의 계층적 구조(아웃라인)를 생성합니다. **2단계 아웃라인 생성 전략**을 사용합니다.

### 5.2 실행 흐름

```
(1) LLM 사전 지식 기반 → Draft Outline (WritePageOutline)
(2) Draft Outline + 대화 히스토리 → Refined Outline (WritePageOutlineFromConv)
```

### 5.3 역할 프롬프트 상세

#### 5.3.1 `WritePageOutline` — 초안 아웃라인

```
System Prompt:
─────────────────────────────────────
"Write an outline for a Wikipedia page.
 Here is the format of your writing:
 1. Use '#' Title to indicate section title,
    '##' Title for subsection, '###' for subsubsection, etc.
 2. Do not include other information.
 3. Do not include topic name itself in the outline."

Input:
  - The topic you want to write: {topic}

Output:
  - outline (마크다운 형식 아웃라인)
```

#### 5.3.2 `WritePageOutlineFromConv` — 대화 기반 개선 아웃라인

```
System Prompt:
─────────────────────────────────────
"Improve an outline for a Wikipedia page. You already have
 a draft outline that covers the general information. Now
 you want to improve it based on the information learned
 from an information-seeking conversation to make it more
 informative.
 Here is the format of your writing:
 1. Use '#' Title to indicate section title,
    '##' Title for subsection, '###' for subsubsection, etc.
 2. Do not include other information.
 3. Do not include topic name itself in the outline."

Input:
  - The topic you want to write: {topic}
  - Conversation history: {전체 대화 히스토리, 최대 5,000 단어}
  - Current outline: {Draft Outline}

Output:
  - outline (개선된 아웃라인)
```

**설계 의도**: LLM의 사전 지식(parametric knowledge)으로 기본 구조를 잡고, 검색 대화에서 발견된 새로운 주제/세부사항을 반영하여 아웃라인을 보강합니다.

---

## 6. Stage 4: 기사 생성 & 폴리싱 (Article Generation & Polishing)

### 6.1 기사 생성 (Article Generation)

#### 6.1.1 병렬 섹션 생성

아웃라인의 1-level 섹션별로 **병렬 스레드**를 통해 독립적으로 본문을 생성합니다. "Introduction"과 "Conclusion/Summary" 섹션은 자동 건너뜁니다.

```
Outline:
  # History
    ## Early Years
    ## Modern Era
  # Technology
    ## Products
    ## R&D

→ Thread 1: generate_section("History", ...)
→ Thread 2: generate_section("Technology", ...)
```

각 섹션 생성 시, `StormInformationTable`에서 해당 섹션 키워드와 가장 관련 높은 정보를 `retrieve_top_k`개 가져옵니다.

#### 6.1.2 `WriteSection` 프롬프트

```
System Prompt:
─────────────────────────────────────
"Write a Wikipedia section based on the collected information.

 Here is the format of your writing:
   1. Use '#' Title for section, '##' for subsection, etc.
   2. Use [1], [2], ..., [n] in line (for example,
      'The capital of the United States is Washington, D.C.[1][3].')
      You DO NOT need to include a References section at the end.

 Important guidelines for interpreting numerical data:
   - ALWAYS check for meta information at the end of the paragraph
     (units, legends, base dates, currency).
   - Apply these meta details correctly when presenting numbers.

 Important guidelines for recency and dates:
   - Always state explicit dates or periods instead of vague terms.
   - Prefer the most recent data when information spans
     different time periods."

Input:
  - The collected information: {검색 결과 snippets, 최대 1,500 단어}
  - The topic of the page: {topic}
  - The section you need to write: {section_name}

Output:
  - section text (인라인 인용 포함)

Output Prefix:
  "Write the section with proper inline citations
   (Start your writing with # section title.
    Don't include the page title or try to write other sections):"
```

### 6.2 기사 폴리싱 (Article Polishing)

#### 6.2.1 리드 섹션 생성 — `WriteLeadSection`

```
System Prompt:
─────────────────────────────────────
"Write a lead section for the given Wikipedia page with
 the following guidelines:
 1. The lead should stand on its own as a concise overview.
    It should identify the topic, establish context, explain
    why the topic is notable, and summarize the most important
    points, including any prominent controversies.
 2. The lead section should be concise and contain no more
    than four well-composed paragraphs.
 3. The lead section should be carefully sourced as appropriate.
    Add inline citations where necessary."

Input:
  - The topic of the page: {topic}
  - The draft page: {전체 초안 기사}

Output:
  - lead_section (요약 리드 섹션)
```

#### 6.2.2 중복 제거 — `PolishPage`

```
System Prompt:
─────────────────────────────────────
"You are a faithful text editor that is good at finding
 repeated information in the article and deleting them
 to make sure there is no repetition in the article.
 You won't delete any non-repeated part in the article.
 You will keep the inline citations and article structure
 (indicated by '#', '##', etc.) appropriately.
 Do your job for the following article."

Input:
  - The draft article: {초안 기사}

Output:
  - page (정제된 기사)
```

---

## 7. 데이터 흐름 요약

```
┌────────────────────────────────────────────────────────────────────┐
│                     STORM 전체 데이터 흐름                          │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  [Topic String]                                                    │
│       │                                                            │
│       ▼                                                            │
│  ┌─ Stage 1: Persona Generation ─┐                                │
│  │ FindRelatedTopic → GenPersona  │                                │
│  │ Output: List[str] personas     │                                │
│  └────────────┬───────────────────┘                                │
│               │                                                    │
│               ▼                                                    │
│  ┌─ Stage 2: Knowledge Curation ──────────────────────────┐       │
│  │  Per-Persona Parallel Conversations                     │       │
│  │  WikiWriter ⇄ TopicExpert (with Retriever)             │       │
│  │  Output: StormInformationTable                          │       │
│  │    ├── conversations: [(persona, [DialogueTurn])]       │       │
│  │    └── url_to_info: {url → Information}                 │       │
│  └────────────┬────────────────────────────────────────────┘       │
│               │                                                    │
│               ▼                                                    │
│  ┌─ Stage 3: Outline Generation ─┐                                │
│  │ WritePageOutline (draft)       │                                │
│  │ WritePageOutlineFromConv       │                                │
│  │ Output: StormArticle (outline) │                                │
│  └────────────┬───────────────────┘                                │
│               │                                                    │
│               ▼                                                    │
│  ┌─ Stage 4: Article Gen & Polish ─────────────────────┐          │
│  │ Per-Section WriteSection (parallel)                   │          │
│  │ WriteLeadSection + PolishPage                         │          │
│  │ Output: StormArticle (full text with citations)       │          │
│  └──────────────────────┬───────────────────────────────┘          │
│                         │                                          │
│                         ▼                                          │
│  [Final Article Files]                                             │
│    ├── storm_gen_article_polished.txt                               │
│    ├── storm_gen_outline.txt                                        │
│    ├── conversation_log.json                                        │
│    ├── raw_search_results.json                                      │
│    ├── url_to_info.json                                             │
│    ├── run_config.json                                              │
│    └── llm_call_history.jsonl                                       │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. 역할 프롬프트 흐름 총괄표

| # | dspy.Signature 클래스 | 역할 요약 | 사용 LLM | Stage |
|---|----------------------|----------|---------|-------|
| 1 | `FindRelatedTopic` | 관련 위키피디아 페이지 URL 추천 | question_asker_lm | 1 |
| 2 | `GenPersona` | 다양한 관점의 편집자 그룹 생성 | question_asker_lm | 1 |
| 3 | `AskQuestionWithPersona` | 특정 페르소나로서 전문가에게 질문 | question_asker_lm | 2 |
| 4 | `AskQuestion` | 기본 모드로 전문가에게 질문 | question_asker_lm | 2 |
| 5 | `QuestionToQuery` | 질문을 검색 엔진 쿼리로 변환 | conv_simulator_lm | 2 |
| 6 | `AnswerQuestion` | 검색 결과 기반 인용 포함 답변 생성 | conv_simulator_lm | 2 |
| 7 | `WritePageOutline` | LLM 사전 지식 기반 초안 아웃라인 | outline_gen_lm | 3 |
| 8 | `WritePageOutlineFromConv` | 대화 정보 기반 아웃라인 개선 | outline_gen_lm | 3 |
| 9 | `WriteSection` | 수집 정보 기반 섹션 본문 작성 | article_gen_lm | 4 |
| 10 | `WriteLeadSection` | 기사 요약 리드 섹션 작성 | article_gen_lm | 4 |
| 11 | `PolishPage` | 중복 제거 및 최종 정제 | article_polish_lm | 4 |

---

## 9. 검색 모듈 (Retrieval Module)

STORM은 `dspy.Retrieve` 인터페이스를 통해 다양한 검색 백엔드를 플러그인 방식으로 교체할 수 있습니다.

### 9.1 지원 검색 모듈

| 모듈 | 소스 | 설명 |
|------|------|------|
| `SerperRM` | 외부 웹 검색 (Serper API) | Google 검색 결과 기반, gl/hl/tbs 파라미터 지원 |
| `YouRM` | You.com API | 대체 웹 검색 |
| `BingSearch` | Bing API | MS Bing 기반 검색 |
| `VectorRM` | 로컬 벡터 DB | Qdrant 기반 내부 문서 검색 |
| `HybridRM` (커스텀) | 내부 + 외부 결합 | PostgresRM(pgvector) + SerperRM 하이브리드 |

### 9.2 검색 흐름

```
Query String
    → dspy.Retrieve.forward(query, exclude_urls)
    → List[dict] (snippets, title, url, description)
    → Information 객체 변환
    → citation 제거 (원문 인용 오염 방지)
    → StormInformationTable에 저장
```

---

## 10. 병렬 처리 전략

STORM은 두 지점에서 `ThreadPoolExecutor` 기반 병렬 처리를 수행합니다:

| 병렬 지점 | 대상 | max_workers |
|----------|------|-------------|
| **Knowledge Curation** | 페르소나별 대화 시뮬레이션 | `min(max_thread_num, len(personas))` |
| **Article Generation** | 섹션별 본문 생성 | `max_thread_num` |

---

## 11. 출력 파일 구조

```
{output_dir}/{topic_name}/
    ├── conversation_log.json       ← 전체 대화 히스토리 (Stage 2)
    ├── raw_search_results.json     ← 검색 원본 결과 (Stage 2)
    ├── direct_gen_outline.txt      ← 초안 아웃라인 (Stage 3)
    ├── storm_gen_outline.txt       ← 개선된 아웃라인 (Stage 3)
    ├── storm_gen_article.txt       ← 초안 기사 (Stage 4)
    ├── url_to_info.json            ← URL→정보 매핑 (Stage 4)
    ├── storm_gen_article_polished.txt ← 최종 기사 (Stage 4)
    ├── run_config.json             ← 실행 설정 로그
    └── llm_call_history.jsonl      ← LLM 호출 이력
```

---

## 12. 한계점 및 Enterprise 확장

### 12.1 원본 STORM의 한계

| 한계 | 설명 |
|------|------|
| **비구조화 출력** | 위키 마크다운 자유형식 → 구조화 JSON 스키마 부재 |
| **검증 부재** | NLI(Natural Language Inference) 기반 환각 검증 없음 |
| **단일 패스** | 한 번의 LLM 호출로 전체 기사 생성 → 깊이 부족 |
| **고정 스키마 없음** | 기업 분석 등 도메인 특화 output 포맷 강제 불가 |

### 12.2 Enterprise Career Pipeline (v2.0)에서의 확장

본 프로젝트의 `career_pipeline.py`는 원본 STORM의 설계 철학을 계승하면서 다음과 같이 확장합니다:

| 확장 요소 | STORM 원본 | Career Pipeline v2.0 |
|----------|-----------|---------------------|
| 출력 형식 | 자유형식 마크다운 | `CareerAnalysisReport` (Pydantic V2 JSON) |
| 페르소나 | LLM 동적 생성 (3+1개) | 고정 3인 (산업 애널리스트, 수석 취업 지원관, 실무 면접관) |
| 파이프라인 | 단일 패스 | 3-Phase Sequential RAG (Phase-by-Phase NLI) |
| 검증 | 없음 | NLI Evaluator → Refiner → force_delete_hallucinations |
| 검색 | SerperRM 단일 | HybridRM (PostgresRM + SerperRM + EntityResolver) |
| 대화 시뮬레이션 | WikiWriter ↔ TopicExpert | 제거 (직접 검색 → LLM 구조화 생성) |

---

## 부록 A: dspy.Signature 패턴 설명

STORM은 Stanford의 **DSPy** 프레임워크를 사용합니다. `dspy.Signature`는 LLM 호출의 입출력 스키마를 선언적으로 정의하는 패턴입니다:

```python
class MyPrompt(dspy.Signature):
    """이 docstring이 System Prompt로 사용됩니다."""

    input_field = dspy.InputField(prefix="Input Label: ", format=str)
    output_field = dspy.OutputField(prefix="Output Label: ", format=str)
```

- **docstring** → LLM에게 전달되는 시스템 프롬프트 (역할 지시)
- **InputField** → 사용자 메시지의 구조화된 입력
- **OutputField** → LLM이 생성해야 할 출력 형식
- **dspy.Predict(Signature)** → 단순 호출
- **dspy.ChainOfThought(Signature)** → 추론 과정(rationale)을 포함한 호출

---

*End of Document*
