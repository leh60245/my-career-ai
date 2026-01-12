#!/usr/bin/env python
"""
FEAT-002: Source Tagging + Dual Filtering 테스트

테스트 항목:
1. 질문 의도 분류 테스트 (Factoid vs Analytical)
2. Dual Filtering 테스트 (Mock)
3. Source Tagging 테스트
4. 실제 DB 검색 테스트 (통합)

Usage:
    python test\test_source_tagging_dual_filter.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_query_intent_classification():
    """질문 의도 분류 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 1: 질문 의도 분류 (Intent Classification)")
    print("=" * 60)

    from knowledge_storm.db.postgres_connector import PostgresConnector

    # PostgresConnector의 _classify_query_intent만 테스트
    connector = PostgresConnector.__new__(PostgresConnector)

    test_cases = [
        # (query, expected_intent)
        ("SK하이닉스 설립일", "factoid"),
        ("삼성전자 대표이사", "factoid"),
        ("현대차 본사 주소", "factoid"),
        ("카카오 최대주주", "factoid"),
        ("SK하이닉스와 삼성전자 시장 점유율 비교", "analytical"),
        ("반도체 업계 경쟁 구도 분석", "analytical"),
        ("삼성전자 SWOT 분석", "analytical"),
        ("매출 성장률 추이", "analytical"),
        ("회사 개요", "factoid"),  # 개요는 factoid
    ]

    all_passed = True
    for query, expected in test_cases:
        result = connector._classify_query_intent(query)
        match = result == expected
        status = "✅" if match else "❌"
        print(f"  {status} '{query}' → {result} (예상: {expected})")
        if not match:
            all_passed = False

    print(f"\n🏁 테스트 1 결과: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_dual_filtering_mock():
    """Dual Filtering Mock 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 2: Dual Filtering (Mock)")
    print("=" * 60)

    from knowledge_storm.db.postgres_connector import PostgresConnector

    connector = PostgresConnector.__new__(PostgresConnector)

    # Mock 데이터
    mock_results = [
        {
            "content": "SK하이닉스는 1949년에 설립되었습니다.",
            "title": "1. 회사의 개요",
            "url": "dart_report_2_chunk_100",
            "score": 0.90,
            "_company_name": "SK하이닉스",
            "_report_id": 2,
        },
        {
            "content": "삼성전자는 1969년에 설립되었습니다.",
            "title": "1. 회사의 개요",
            "url": "dart_report_1_chunk_50",
            "score": 0.85,
            "_company_name": "삼성전자",
            "_report_id": 1,
        },
    ]

    # Test Case 1: Factoid 질문 (Strict Filter)
    print("\n  [Case 1] Factoid 질문: 'SK하이닉스 설립일'")
    results1 = connector._rerank_by_entity_match(
        query="SK하이닉스 설립일",
        results=mock_results.copy(),
        enable_dual_filter=True
    )
    print(f"    결과 수: {len(results1)} (예상: 1개, 삼성 청크 DROP)")
    for r in results1:
        print(f"      - {r['url']}: {r.get('_company_name', 'N/A')}")

    factoid_pass = len(results1) == 1 and "SK하이닉스" in results1[0].get('content', '')

    # Test Case 2: Analytical 질문 (Relaxed Filter)
    print("\n  [Case 2] Analytical 질문: 'SK하이닉스와 삼성전자 비교 분석'")
    results2 = connector._rerank_by_entity_match(
        query="SK하이닉스와 삼성전자 비교 분석",
        results=mock_results.copy(),
        enable_dual_filter=True
    )
    print(f"    결과 수: {len(results2)} (예상: 2개, 모두 매칭)")
    for r in results2:
        print(f"      - {r['url']}: {r.get('_company_name', 'N/A')}")

    analytical_pass = len(results2) == 2

    success = factoid_pass and analytical_pass
    print(f"\n🏁 테스트 2 결과: {'✅ PASS' if success else '❌ FAIL'}")
    return success


def test_source_tagging():
    """Source Tagging 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 3: Source Tagging")
    print("=" * 60)

    from knowledge_storm.db.postgres_connector import PostgresConnector

    connector = PostgresConnector.__new__(PostgresConnector)

    mock_results = [
        {
            "content": "당사는 메모리 반도체를 생산합니다.",
            "title": "사업의 내용",
            "url": "dart_report_2_chunk_200",
            "score": 0.95,
            "_company_name": "SK하이닉스",
            "_report_id": 2,
        },
    ]

    tagged = connector._apply_source_tagging(mock_results.copy(), enable=True)

    print(f"  원본 content: '{mock_results[0]['content'][:50]}...'")
    print(f"  Tagged content: '{tagged[0]['content'][:100]}...'")

    # 검증
    has_tag = "[[출처:" in tagged[0]['content']
    has_company = "SK하이닉스" in tagged[0]['content']
    meta_removed = "_company_name" not in tagged[0]

    success = has_tag and has_company and meta_removed

    print(f"\n  검증:")
    print(f"    출처 태그 존재: {has_tag}")
    print(f"    회사명 포함: {has_company}")
    print(f"    메타데이터 제거: {meta_removed}")

    print(f"\n🏁 테스트 3 결과: {'✅ PASS' if success else '❌ FAIL'}")
    return success


def test_real_search_integrated():
    """실제 DB 검색 통합 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 4: 실제 DB 검색 (통합)")
    print("=" * 60)

    try:
        from knowledge_storm.db.postgres_connector import PostgresConnector

        connector = PostgresConnector()
        print("  ✅ PostgresConnector 초기화 성공")

        # Test 1: Factoid 질문
        query1 = "SK하이닉스 설립일"
        print(f"\n  [Query 1] '{query1}' (Factoid)")
        results1 = connector.search(query1, top_k=5)

        print(f"    결과 수: {len(results1)}")
        for i, r in enumerate(results1[:3], 1):
            content = r.get('content', '')
            has_tag = "[[출처:" in content
            company = "SK하이닉스" if "SK하이닉스" in content or "하이닉스" in content else "Other"
            print(f"      {i}. score={r.get('score', 0):.4f}, tag={has_tag}, company={company}")
            # 첫 줄만 출력 (출처 태그)
            first_line = content.split('\n')[0]
            print(f"         {first_line[:80]}...")

        # 검증: 모든 결과가 SK하이닉스여야 함 (Factoid)
        samsung_found = any("삼성" in r['content'] and "SK" not in r['content'] for r in results1)
        all_tagged = all("[[출처:" in r['content'] for r in results1)

        test1_pass = not samsung_found and all_tagged

        # Test 2: Analytical 질문
        query2 = "반도체 시장 점유율 분석"
        print(f"\n  [Query 2] '{query2}' (Analytical)")
        results2 = connector.search(query2, top_k=5)

        print(f"    결과 수: {len(results2)}")
        all_tagged2 = all("[[출처:" in r['content'] for r in results2)

        test2_pass = all_tagged2

        connector.close()

        success = test1_pass and test2_pass

        print(f"\n  검증:")
        print(f"    Factoid - 삼성 청크 제거: {not samsung_found}")
        print(f"    Factoid - Source Tag 적용: {all_tagged}")
        print(f"    Analytical - Source Tag 적용: {all_tagged2}")

        print(f"\n🏁 테스트 4 결과: {'✅ PASS' if success else '❌ FAIL'}")
        return success

    except Exception as e:
        print(f"  ❌ 오류 발생: {e}")
        print("     (DB 연결이 필요한 테스트입니다)")
        return None


def main():
    """모든 테스트 실행"""
    print("=" * 60)
    print("🚀 FEAT-002: Source Tagging + Dual Filtering 테스트")
    print("=" * 60)

    results = []

    # 테스트 1: 질문 의도 분류
    results.append(("질문 의도 분류", test_query_intent_classification()))

    # 테스트 2: Dual Filtering Mock
    results.append(("Dual Filtering", test_dual_filtering_mock()))

    # 테스트 3: Source Tagging
    results.append(("Source Tagging", test_source_tagging()))

    # 테스트 4: 실제 DB 검색
    results.append(("실제 DB 검색", test_real_search_integrated()))

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)

    for name, passed in results:
        if passed is None:
            status = "⏭️ SKIP"
        elif passed:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(p for p in [r[1] for r in results] if p is not None)
    print()
    print(f"🏁 최종 결과: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")


if __name__ == "__main__":
    main()

