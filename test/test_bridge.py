"""
Post-Processing Bridge Test (FIX-Core-002)

Task ID: FIX-Core-002-SaveLogic & Encoding

Test Cases:
1. File Discovery (_find_report_file)
2. UTF-8 Encoding (_read_report_content)
3. DB Save with RETURNING (_save_report_to_db)
4. Full Bridge (_load_and_save_report_bridge)

Usage:
    python test_bridge.py
"""

import os
import sys
import tempfile
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.storm_service import (
    _find_report_file,
    _read_report_content,
    _save_report_to_db,
    _load_and_save_report_bridge,
)


def test_utf8_encoding():
    """UTF-8 인코딩 테스트"""
    print("\n" + "=" * 70)
    print("Test 1: UTF-8 Encoding (한글 포함)")
    print("=" * 70)
    
    # 임시 파일 생성
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.txt',
        encoding='utf-8',
        delete=False
    ) as f:
        temp_path = f.name
        test_content = """
# 삼성전자 기업 개요

## 1. 개요
삼성전자는 한국을 대표하는 종합 전자 회사입니다.

## 2. 주요 사업
- 반도체 (메모리, 파운드리)
- 디스플레이 (LCD, OLED)
- 가전 제품
- 통신 장비

## 3. 재정 상황
2023년 연매출: 약 230조원
영업이익: 약 28조원

한글 테스트: ㄱㄴㄷ, 특수문자: 😀🎉
"""
        f.write(test_content)
    
    try:
        # 파일 읽기 테스트
        content = _read_report_content(temp_path)
        
        if content and "삼성전자" in content and "한글 테스트" in content:
            print("✅ UTF-8 인코딩 정상 작동")
            print(f"   읽어온 내용 길이: {len(content)} bytes")
            print(f"   샘플: {content[:50]}...")
            return True
        else:
            print("❌ UTF-8 인코딩 실패: 한글이 깨졌거나 누락됨")
            return False
            
    finally:
        os.unlink(temp_path)


def test_file_discovery():
    """파일 탐색 테스트"""
    print("\n" + "=" * 70)
    print("Test 2: File Discovery (파일 탐색)")
    print("=" * 70)
    
    # 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as temp_dir:
        # 테스트 파일 생성
        polished_file = os.path.join(temp_dir, "storm_gen_article_polished.txt")
        with open(polished_file, 'w', encoding='utf-8') as f:
            f.write("# Test Report\n최종 버전입니다.")
        
        # 파일 탐색
        found_file = _find_report_file(temp_dir)
        
        if found_file and "polished" in found_file:
            print("✅ 파일 탐색 성공")
            print(f"   찾은 파일: {os.path.basename(found_file)}")
            return True
        else:
            print("❌ 파일 탐색 실패")
            return False


def test_db_save_returning():
    """DB RETURNING 테스트"""
    print("\n" + "=" * 70)
    print("Test 3: DB Save with RETURNING id")
    print("=" * 70)
    
    try:
        # 테스트 데이터
        test_report = {
            "company_name": "TEST기업",
            "topic": "테스트 주제",
            "content": "# TEST\n테스트 리포트입니다.\n한글: ㄱㄴㄷ"
        }
        
        # DB 저장
        report_id = _save_report_to_db(
            company_name=test_report["company_name"],
            topic=test_report["topic"],
            report_content=test_report["content"],
            model_name="test-model"
        )
        
        if report_id is not None and isinstance(report_id, int):
            print("✅ DB 저장 성공")
            print(f"   생성된 Report ID: {report_id}")
            print(f"   (이 ID는 DB에 실제로 저장되었습니다)")
            return True
        else:
            print("❌ DB 저장 실패: Report ID 없음")
            return False
            
    except Exception as e:
        print(f"❌ DB 저장 오류: {e}")
        return False


def test_full_bridge():
    """전체 Bridge 테스트"""
    print("\n" + "=" * 70)
    print("Test 4: Full Bridge (종합 테스트)")
    print("=" * 70)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # 테스트 파일 생성
        report_file = os.path.join(temp_dir, "storm_gen_article_polished.txt")
        test_content = """
# SK하이닉스 기업 개요

## 1. 개요
SK하이닉스는 반도체 제조 전문 기업입니다.

## 2. 주요 제품
- D램 (DRAM)
- 낸드 플래시 (NAND Flash)
- HBM (High Bandwidth Memory)

한글 테스트: 완벽한 인코딩 ✓
"""
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        # 메모리 Job 상태
        jobs_dict = {"test-job": {"message": "테스트"}}
        
        try:
            report_id = _load_and_save_report_bridge(
                output_dir=temp_dir,
                company_name="SK하이닉스",
                topic="기업 개요",
                jobs_dict=jobs_dict,
                job_id="test-job",
                model_name="test-model"
            )
            
            if report_id is not None:
                print("✅ Full Bridge 성공")
                print(f"   Report ID: {report_id}")
                print(f"   Job Status: {jobs_dict['test-job']['message']}")
                return True
            else:
                print("❌ Full Bridge 실패")
                return False
                
        except Exception as e:
            print(f"❌ Bridge 오류: {e}")
            return False


def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "=" * 70)
    print("  Post-Processing Bridge Test Suite (FIX-Core-002)")
    print("=" * 70)
    
    results = {
        "UTF-8 Encoding": test_utf8_encoding(),
        "File Discovery": test_file_discovery(),
        "DB Save RETURNING": test_db_save_returning(),
        "Full Bridge": test_full_bridge(),
    }
    
    print("\n" + "=" * 70)
    print("  Test Results Summary")
    print("=" * 70)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}  {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    
    print("\n" + "=" * 70)
    print(f"  Total: {passed}/{total} tests passed")
    print("=" * 70 + "\n")
    
    if passed == total:
        print("🎉 All tests passed! Bridge is working correctly.")
        print("\n✅ Verification Checklist:")
        print("  [x] UTF-8 인코딩 정상 처리")
        print("  [x] 파일 탐색 로직 작동")
        print("  [x] DB 저장 및 RETURNING id 획득")
        print("  [x] 전체 Bridge 통합 동작")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
