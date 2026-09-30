# 탄소계수·정책 관리 명령

문헌계수와 계산정책을 직접 SQL로 수정하지 않고, JSON manifest를 검증한 뒤 새 버전으로 등록하기 위한 명령이다. 기본 실행은 **검증만 수행하며 DB를 변경하지 않는다**.

## 등록 절차

```powershell
python -m carbon.policy_admin publish .\policy.json
python -m carbon.policy_admin publish .\policy.json --apply
```

첫 번째 명령으로 소재 존재 여부, key/version 중복, 단위·방법·범위·용도 호환성과 기존 활성 정책을 확인한다. 검토 결과가 정상이면 두 번째 명령으로만 반영한다. 반영은 하나의 트랜잭션에서 다음 순서로 처리한다.

1. draft 정책 생성
2. selected 계수와 출처·한계 저장
3. 소재별 계수 연결
4. DB 불변성 검사를 거쳐 active 전환

중간에 하나라도 실패하면 전체 작업을 롤백한다. 기존 계수나 정책을 덮어쓰지 않는다.

## 정책 종료

```powershell
python -m carbon.policy_admin retire POLICY_KEY VERSION
python -m carbon.policy_admin retire POLICY_KEY VERSION --apply
```

첫 번째 명령은 대상만 확인하고, `--apply`를 붙인 두 번째 명령이 active 정책을 retired로 전환한다. retired 정책은 다시 수정하거나 활성화하지 않는다. 새 정책은 새 version으로 등록한다.

## Manifest 필수 구조

```json
{
  "profile": {
    "key": "team-approved-policy",
    "version": "2026-01",
    "formula_version": "fiber_mass_v2",
    "method": "EF3.1_climate_change_total",
    "scope": "fiber_production_estimate",
    "usage_scope": "research_scenario"
  },
  "factors": [
    {
      "material": "cotton",
      "factor_key": "source-specific-cotton",
      "version": "2026-01",
      "value_decimal": "검토한 숫자",
      "unit": "kg CO2eq/kg fiber",
      "method": "EF3.1_climate_change_total",
      "scope": "fiber_production_estimate",
      "product_form": "검토한 제품 형태",
      "production_system": "검토한 생산 방식",
      "geography": "검토한 지역",
      "publication_year": 2026,
      "data_years": [2023],
      "source_name": "보고서 이름",
      "source_url": "https://example.org/report.pdf",
      "source_locator": "표·페이지",
      "evidence_type": "literature",
      "usage_scope": "research_scenario",
      "limitations": ["대표성 한계"],
      "carbon_accounting": {},
      "components": null,
      "review_note": "검토 내용",
      "selection_assumption": "이 계수를 선택한 이유"
    }
  ]
}
```

예시의 `검토한 숫자`와 설명은 그대로 사용할 수 없는 자리표시자다. 실제 보고서 검토가 끝난 값으로 교체해야 한다. 연구용 계수는 `research_scenario`로 관리하며, 공개 서비스용 `public_estimate`로 자동 승격하지 않는다.
