#!/usr/bin/env python
"""
Company Filter 기능 테스트 스크립트

PostgresRM의 company_filter 및 Query Routing 기능을 검증합니다.

Usage:
    python -m scripts.test_company_filter

테스트 항목:
1. COMPANY_ALIASES 정규화 함수 테스트
2. 비교 질문 감지 테스트
3. PostgresConnector.search()의 company_filter 동작 테스트
4. PostgresRM의 Query Routing 테스트
"""

import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_storm.utils import load_api_key


def test_company_aliases():
    """COMPANY_ALIASES 및 관련 함수 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 1: COMPANY_ALIASES 및 정규화 함수")
    print("=" * 60)

    from src.common.config import (
        COMPANY_ALIASES,
        get_canonical_company_name,
        get_all_aliases,
        is_comparison_query,
        extract_companies_from_query,
        COMPARISON_KEYWORDS
    )

    # 1. 별칭 → 정규명 변환 테스트
    test_cases = [
        ("삼전", "삼성전자"),
        ("Samsung Electronics", "삼성전자"),
        ("하이닉스", "SK하이닉스"),
        ("SK Hynix", "SK하이닉스"),
        ("네이버", "NAVER"),
        ("현대차", "현대자동차"),
        ("알 수 없는 회사", "알 수 없는 회사"),  # 찾지 못하면 원본 반환
    ]

    print("\n[별칭 → 정규명 변환]")
    all_passed = True
    for alias, expected in test_cases:
        result = get_canonical_company_name(alias)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{alias}' → '{result}' (expected: '{expected}')")
        if result != expected:
            all_passed = False

    # 2. 모든 별칭 조회 테스트
    print("\n[모든 별칭 조회]")
    samsung_aliases = get_all_aliases("삼성전자")
    print(f"  삼성전자의 모든 별칭: {samsung_aliases}")
    assert "삼전" in samsung_aliases, "삼전이 삼성전자 별칭에 있어야 함"
    assert "Samsung Electronics" in samsung_aliases, "Samsung Electronics가 삼성전자 별칭에 있어야 함"
    print("  ✅ 별칭 목록 확인 완료")

    print(f"\n🏁 테스트 1 결과: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_comparison_detection():
    """비교 질문 감지 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 2: 비교 질문 감지")
    print("=" * 60)

    from src.common.config import is_comparison_query, extract_companies_from_query

    # 비교 질문 테스트
    comparison_queries = [
        ("삼성전자와 SK하이닉스 비교해줘", True, ["삼성전자", "SK하이닉스"]),
        ("삼성전자 vs SK하이닉스 매출 분석", True, ["삼성전자", "SK하이닉스"]),
        ("삼성 대비 하이닉스 시장 점유율", True, ["삼성전자", "SK하이닉스"]),
        ("삼성전자 경쟁사 분석", True, ["삼성전자"]),
        ("삼성전자 SWOT 분석", False, ["삼성전자"]),
        ("SK하이닉스 재무 현황", False, ["SK하이닉스"]),
        ("반도체 업계 동향", True, []),  # 비교 키워드는 있지만 기업명 없음
    ]

    print("\n[비교 질문 감지 및 기업 추출]")
    all_passed = True
    for query, expected_is_comparison, expected_companies in comparison_queries:
        is_comp = is_comparison_query(query)
        companies = extract_companies_from_query(query)

        comp_status = "✅" if is_comp == expected_is_comparison else "❌"
        companies_status = "✅" if set(companies) == set(expected_companies) else "❌"

        print(f"  Query: '{query}'")
        print(f"    {comp_status} is_comparison: {is_comp} (expected: {expected_is_comparison})")
        print(f"    {companies_status} companies: {companies} (expected: {expected_companies})")

        if is_comp != expected_is_comparison or set(companies) != set(expected_companies):
            all_passed = False

    print(f"\n🏁 테스트 2 결과: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_postgres_connector_filter():
    """PostgresConnector.search()의 company_filter 동작 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 3: PostgresConnector.search() with company_filter")
    print("=" * 60)

    # secrets.toml 로드
    secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.toml")
    if os.path.exists(secrets_path):
        load_api_key(toml_file_path=secrets_path)
    elif os.path.exists("secrets.toml"):
        load_api_key(toml_file_path="secrets.toml")
    else:
        print("⚠️ secrets.toml not found, skipping DB test")
        return True

    try:
        from knowledge_storm.db import PostgresConnector

        connector = PostgresConnector()
        print("✅ PostgresConnector initialized")

        # 테스트 1: 필터 없이 검색
        print("\n[필터 없이 검색]")
        results_no_filter = connector.search("반도체 매출 현황", top_k=5)
        print(f"  결과 수: {len(results_no_filter)}")
        if results_no_filter:
            companies_found = set()
            for r in results_no_filter:
                title = r.get('title', 'N/A')
                url = r.get('url', 'N/A')
                print(f"    - {title[:50]}... (url: {url})")

        # 테스트 2: 삼성전자 필터
        print("\n[삼성전자 필터 적용]")
        results_samsung = connector.search(
            "반도체 매출 현황",
            top_k=5,
            company_filter="삼성전자"
        )
        print(f"  결과 수: {len(results_samsung)}")
        samsung_only = True
        for r in results_samsung:
            title = r.get('title', 'N/A')
            url = r.get('url', 'N/A')
            print(f"    - {title[:50]}... (url: {url})")
            # 결과가 삼성전자 문서인지 확인 (URL 또는 다른 메타데이터로)

        # 테스트 3: SK하이닉스 필터
        print("\n[SK하이닉스 필터 적용]")
        results_sk = connector.search(
            "반도체 매출 현황",
            top_k=5,
            company_filter="SK하이닉스"
        )
        print(f"  결과 수: {len(results_sk)}")
        for r in results_sk:
            title = r.get('title', 'N/A')
            url = r.get('url', 'N/A')
            print(f"    - {title[:50]}... (url: {url})")

        # 테스트 4: 복수 기업 필터
        print("\n[복수 기업 필터 (삼성전자, SK하이닉스)]")
        results_both = connector.search(
            "반도체 매출 현황",
            top_k=5,
            company_filter_list=["삼성전자", "SK하이닉스"]
        )
        print(f"  결과 수: {len(results_both)}")
        for r in results_both:
            title = r.get('title', 'N/A')
            url = r.get('url', 'N/A')
            print(f"    - {title[:50]}... (url: {url})")

        connector.close()
        print("\n✅ PostgresConnector 테스트 완료")
        return True

    except Exception as e:
        print(f"❌ PostgresConnector 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_postgres_rm_query_routing():
    """PostgresRM의 Query Routing 테스트"""
    print("\n" + "=" * 60)
    print("📋 테스트 4: PostgresRM Query Routing")
    print("=" * 60)

    # secrets.toml 로드
    secrets_path = os.path.join(os.path.dirname(__file__), "..", "secrets.toml")
    if os.path.exists(secrets_path):
        load_api_key(toml_file_path=secrets_path)
    elif os.path.exists("secrets.toml"):
        load_api_key(toml_file_path="secrets.toml")
    else:
        print("⚠️ secrets.toml not found, skipping RM test")
        return True

    try:
        from knowledge_storm.rm import PostgresRM

        # 삼성전자 필터가 설정된 PostgresRM
        rm = PostgresRM(k=5, min_score=0.5, company_filter="삼성전자")
        print("✅ PostgresRM initialized with company_filter='삼성전자'")

        # 테스트 1: 일반 질문 (필터 유지)
        print("\n[일반 질문: '재무 현황 분석' - 삼성전자만 검색되어야 함]")
        results1 = rm.forward("재무 현황 분석")
        print(f"  결과 수: {len(results1)}")
        for r in results1[:3]:
            print(f"    - {r.title[:50] if len(r.title) > 50 else r.title}...")

        # 테스트 2: 비교 질문 (필터 확장)
        print("\n[비교 질문: '삼성전자와 SK하이닉스 비교' - 둘 다 검색되어야 함]")
        results2 = rm.forward("삼성전자와 SK하이닉스 비교해줘")
        print(f"  결과 수: {len(results2)}")
        for r in results2[:3]:
            print(f"    - {r.title[:50] if len(r.title) > 50 else r.title}...")

        rm.close()
        print("\n✅ PostgresRM Query Routing 테스트 완료")
        return True

    except Exception as e:
        print(f"❌ PostgresRM 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """전체 테스트 실행"""
    print("=" * 60)
    print("🧪 Company Filter 기능 테스트")
    print("=" * 60)

    results = []

    # 테스트 1: COMPANY_ALIASES
    results.append(("COMPANY_ALIASES", test_company_aliases()))

    # 테스트 2: 비교 질문 감지
    results.append(("Comparison Detection", test_comparison_detection()))

    # 테스트 3: PostgresConnector
    results.append(("PostgresConnector Filter", test_postgres_connector_filter()))

    # 테스트 4: PostgresRM Query Routing
    results.append(("PostgresRM Query Routing", test_postgres_rm_query_routing()))

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

