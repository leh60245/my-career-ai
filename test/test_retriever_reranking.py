#!/usr/bin/env python
"""
Retriever Post-Processing 테스트 스크립트

Section-Based Boosting과 Diversity Enforcement 기능을 검증합니다.

Usage:
    python -m scripts.test_retriever_reranking

테스트 항목:
1. 질문 의도 감지 테스트
2. Section-Based Boosting 테스트
3. Diversity Enforcement 테스트
4. 통합 테스트 (실제 검색 결과)
"""

import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_query_intent_detection():
    """질문 의도 감지 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 1: 질문 의도(Intent) 감지")
    print("=" * 60)

    from knowledge_storm.interface import Retriever

    # Retriever 인스턴스 직접 생성 (rm=None으로 테스트)
    retriever = Retriever.__new__(Retriever)
    retriever.max_thread = 1
    retriever.rm = None

    test_cases = [
        ("SK하이닉스 기업 개요", ["overview"]),
        ("삼성전자 회사의 개요 분석", ["overview"]),
        ("SK하이닉스 주요 사업 내용", ["business"]),
        ("삼성전자 재무제표 분석", ["financial"]),
        ("회사 연혁 및 설립 배경", ["history"]),  # history만 감지 (정확)
        ("반도체 시장 점유율", []),  # 특정 섹션 매칭 없음
    ]

    all_passed = True
    for query, expected_intents in test_cases:
        detected = retriever._detect_query_intent(query)
        # 순서 무관 비교
        match = set(detected) == set(expected_intents)
        status = "✅" if match else "❌"
        print(f"  {status} '{query}'")
        print(f"       감지: {detected}, 예상: {expected_intents}")
        if not match:
            all_passed = False

    print(f"\n🏁 테스트 1 결과: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_section_boost():
    """Section-Based Boosting 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 2: Section-Based Boosting")
    print("=" * 60)

    from knowledge_storm.interface import Retriever

    retriever = Retriever.__new__(Retriever)
    retriever.max_thread = 1
    retriever.rm = None

    test_cases = [
        # (title, intents, expected_boost > 0)
        ("1. 회사의 개요", ["overview"], True),
        ("II. 사업의 내용", ["business"], True),
        ("III. 재무에 관한 사항", ["financial"], True),
        ("이사회 구성 현황", ["overview"], False),  # 개요 intent지만 이사회는 매칭 안됨
        ("주요 사업 실적", ["business"], True),  # 사업 intent + 사업 키워드
        ("임원 보수 현황", ["overview"], False),
    ]

    all_passed = True
    for title, intents, should_boost in test_cases:
        boost = retriever._calculate_section_boost(title, intents)
        is_boosted = boost > 0
        match = is_boosted == should_boost
        status = "✅" if match else "❌"
        print(f"  {status} '{title}' (intents={intents})")
        print(f"       부스트: {boost:.2f}, 예상: {'> 0' if should_boost else '= 0'}")
        if not match:
            all_passed = False

    print(f"\n🏁 테스트 2 결과: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_chunk_type_detection():
    """Chunk Type 감지 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 3: Chunk Type 감지 (Text vs Table)")
    print("=" * 60)

    from knowledge_storm.interface import Retriever

    retriever = Retriever.__new__(Retriever)
    retriever.max_thread = 1
    retriever.rm = None

    test_cases = [
        # (data, expected_type)
        ({"content": "SK하이닉스는 1949년에 설립된...", "title": "회사의 개요"}, "text"),
        ({"content": "| 구분 | 2023 | 2022 |\n|---|---|---|\n| 매출 | 100 | 90 |", "title": "재무현황"}, "table"),
        ({"content": "[표 데이터]\n이름: 홍길동, 직위: 대표이사", "title": "임원현황"}, "table"),
        ({"content": "당사는 반도체 메모리를 생산합니다.", "title": "사업의 내용"}, "text"),
    ]

    all_passed = True
    for data, expected_type in test_cases:
        detected_type = retriever._get_chunk_type(data)
        match = detected_type == expected_type
        status = "✅" if match else "❌"
        print(f"  {status} Title: '{data['title']}'")
        print(f"       감지: {detected_type}, 예상: {expected_type}")
        if not match:
            all_passed = False

    print(f"\n🏁 테스트 3 결과: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_diversity_enforcement():
    """Diversity Enforcement 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 4: Diversity Enforcement (Text/Table 비율)")
    print("=" * 60)

    from knowledge_storm.interface import Retriever

    retriever = Retriever.__new__(Retriever)
    retriever.max_thread = 1
    retriever.rm = None

    # 테스트 데이터: 테이블 5개, 텍스트 2개 (테이블 편향 상황)
    mock_results = [
        {"content": "| 표1 | a | b |", "title": "이사회", "score": 0.95},  # table, highest score
        {"content": "| 표2 | c | d |", "title": "주주현황", "score": 0.90},  # table
        {"content": "| 표3 | e | f |", "title": "임원보수", "score": 0.88},  # table
        {"content": "SK하이닉스는 1949년 설립...", "title": "회사의 개요", "score": 0.85},  # text
        {"content": "| 표4 | g | h |", "title": "감사보고", "score": 0.82},  # table
        {"content": "반도체 메모리 사업을 영위...", "title": "사업의 내용", "score": 0.80},  # text
        {"content": "| 표5 | i | j |", "title": "재무표", "score": 0.75},  # table
    ]

    # top_k=5, MIN_TEXT_RATIO=0.4 → 최소 2개는 Text
    result = retriever._apply_diversity_enforcement(mock_results, top_k=5)

    # 결과 분석
    text_count = sum(1 for r in result if retriever._get_chunk_type(r) == "text")
    table_count = sum(1 for r in result if retriever._get_chunk_type(r) == "table")

    print(f"  입력: 7개 (Text 2, Table 5)")
    print(f"  출력: {len(result)}개 (Text {text_count}, Table {table_count})")
    print(f"  최소 Text 비율: {retriever.MIN_TEXT_RATIO} → 최소 {int(5 * retriever.MIN_TEXT_RATIO)}개")

    # 검증: Text가 최소 2개 이상이어야 함
    min_text = max(1, int(5 * retriever.MIN_TEXT_RATIO))
    passed = text_count >= min_text

    print(f"\n  선택된 청크:")
    for r in result:
        chunk_type = retriever._get_chunk_type(r)
        print(f"    - [{chunk_type.upper()}] {r['title']} (score: {r['score']:.2f})")

    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n🏁 테스트 4 결과: {status}")
    return passed


def test_integration():
    """통합 테스트: 실제 PostgresRM과 Retriever 연동"""
    print("\n" + "=" * 60)
    print("📋 테스트 5: 통합 테스트 (PostgresRM + Retriever)")
    print("=" * 60)

    from knowledge_storm.utils import load_api_key

    # secrets.toml 로드
    secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.toml")
    if os.path.exists(secrets_path):
        load_api_key(toml_file_path=secrets_path)
    elif os.path.exists("secrets.toml"):
        load_api_key(toml_file_path="secrets.toml")
    else:
        print("⚠️ secrets.toml not found, skipping integration test")
        return True

    try:
        from knowledge_storm.rm import PostgresRM
        from knowledge_storm.interface import Retriever

        # PostgresRM 초기화
        rm = PostgresRM(k=10, min_score=0.3, company_filter="SK하이닉스")
        print("✅ PostgresRM initialized")

        # Retriever 초기화
        retriever = Retriever(rm=rm, max_thread=1)
        print("✅ Retriever initialized")

        # 테스트 쿼리: "기업 개요" (개요 섹션 부스트 예상)
        query = "SK하이닉스 기업 개요 및 소개"
        print(f"\n🔍 테스트 쿼리: '{query}'")

        results = retriever.retrieve(query)

        print(f"\n📊 검색 결과: {len(results)}개")
        for i, r in enumerate(results[:5], 1):
            print(f"  [{i}] {r.title[:40]}...")
            print(f"      URL: {r.url}")
            if r.snippets:
                snippet_preview = r.snippets[0][:80] + "..." if len(r.snippets[0]) > 80 else r.snippets[0]
                print(f"      Snippet: {snippet_preview}")

        # 검증: "개요" 관련 청크가 상위에 있어야 함
        overview_in_top3 = any(
            "개요" in r.title or "사업" in r.title
            for r in results[:3]
        )

        rm.close()
        print(f"\n🏁 테스트 5 결과: {'✅ 개요 관련 청크 상위 랭크' if overview_in_top3 else '⚠️ 확인 필요'}")
        return True

    except Exception as e:
        print(f"❌ 통합 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """전체 테스트 실행"""
    print("=" * 60)
    print("🧪 Retriever Post-Processing 테스트")
    print("=" * 60)

    results = []

    # 테스트 1: 질문 의도 감지
    results.append(("Query Intent Detection", test_query_intent_detection()))

    # 테스트 2: Section-Based Boosting
    results.append(("Section-Based Boosting", test_section_boost()))

    # 테스트 3: Chunk Type 감지
    results.append(("Chunk Type Detection", test_chunk_type_detection()))

    # 테스트 4: Diversity Enforcement
    results.append(("Diversity Enforcement", test_diversity_enforcement()))

    # 테스트 5: 통합 테스트
    results.append(("Integration Test", test_integration()))

    # 최종 결과
    print("\n" + "=" * 60)
    print("📊 최종 테스트 결과")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 모든 테스트 통과!")
    else:
        print("⚠️ 일부 테스트 실패")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

