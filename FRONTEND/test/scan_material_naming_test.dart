import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/scan_result.dart';
import 'package:k_dpp/services/scan_draft_service.dart';
import 'package:k_dpp/services/scan_save_service.dart';
import 'package:k_dpp/utils/clothing_estimator.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';

/// 서버가 내려준 소재 표시명이 편집 폼 → 프리뷰 계산 → 저장까지 가는 동안
/// 배출계수·건강도 조회에 계속 걸리는지 확인한다.
///
/// 서버는 `material_details.display_name`으로 **한글명**('면')을 주고
/// [ScanDraftService]가 그것을 소재 맵의 키로 쓴다. 계수 조회가 영문 이름만
/// 알아보던 동안에는 스캔한 옷이 소재와 무관하게 전부 기본계수 10.0으로
/// 계산됐고, 탄소값은 저장 시 서버 계산으로 덮이지만 **건강도는 덮이지 않아**
/// 잘못된 값이 옷장·홈 평균에 영구 저장됐다.
void main() {
  // 가공 픽스처 대신 실제 카탈로그 유형을 쓴다. 무게 기준이 저장 요청의
  // min/max로 그대로 나가므로(clothing_type_option.dart가 라벨에서 파싱),
  // 카탈로그에 없는 무게로 세운 테스트는 저장 경로를 대표하지 못한다.
  // 반팔 티셔츠: 100~250g, 대표 무게 180g.
  final tee = ClothingTypeCatalog.defaultOption;

  ScanResult scannedCottonShirt() {
    return ScanResult.fromJson(const {
      'materials': {'cotton': 100},
      'material_details': [
        {
          'original_name': 'cotton',
          'standard_name': 'cotton',
          'display_name': '면',
          'ratio': 100,
          'is_supported': true,
        },
      ],
      'care_instruction': '라벨 표기법에 맞춰 관리하세요.',
      'title': '면 티셔츠',
      'category': '상의',
    });
  }

  test('초안은 서버 표시명을 소재 키로 쓴다 (계약 확인)', () {
    final draft = const ScanDraftService().buildFromResult(
      result: scannedCottonShirt(),
      clothingType: tee,
    );

    expect(draft.materials.keys, ['면']);
  });

  test('표시명으로 만든 초안이 소재별 계수로 계산된다', () {
    final draft = const ScanDraftService().buildFromResult(
      result: scannedCottonShirt(),
      clothingType: tee,
    );

    // 서버 시드 cotton 8.3 × 0.18kg = 1.494. 기본계수 10.0이었다면 1.8이 나온다.
    expect(
      ClothingEstimator.estimateCarbonFootprint(draft.materials, tee),
      1.5,
    );
  });

  test('저장되는 건강도가 소재 가점을 반영한다', () {
    final draft = const ScanDraftService().buildFromResult(
      result: scannedCottonShirt(),
      clothingType: tee,
    );

    final saveResult = const ScanSaveService().buildClothes(
      title: draft.title,
      category: draft.category,
      materials: draft.materials,
      careInstruction: draft.careInstruction,
      clothingType: draft.clothingType,
      originalMaterials: draft.materials,
      serverHealth: draft.serverHealth,
      serverCarbonFootprint: draft.serverCarbonFootprint,
      serverWeightGram: draft.serverWeightGram,
      serverCalculationMethod: draft.serverCalculationMethod,
    );

    expect(saveResult, isA<ScanSaveSuccess>());

    // 단일 소재 +8, 면 +5 → 93. 소재를 못 알아보면 88에 머문다.
    // 탄소값과 달리 건강도는 서버가 덮어쓰지 않으므로 이 값이 옷장에 남는다.
    expect((saveResult as ScanSaveSuccess).clothes.health, 93);
  });

  test('울 니트도 소재 감점을 받는다', () {
    final result = ScanResult.fromJson(const {
      'materials': {'wool': 100},
      'material_details': [
        {
          'original_name': 'wool',
          'standard_name': 'wool',
          'display_name': '울',
          'ratio': 100,
          'is_supported': true,
        },
      ],
      'care_instruction': '라벨 표기법에 맞춰 관리하세요.',
    });

    final draft = const ScanDraftService().buildFromResult(
      result: result,
      clothingType: tee,
    );

    expect(draft.materials.keys, ['울']);
    expect(ClothingEstimator.estimateInitialHealth(draft.materials), 83);
    // 서버 시드 wool 13.9 × 0.18kg = 2.502
    expect(ClothingEstimator.estimateCarbonFootprint(draft.materials, tee), 2.5);
  });

  test('혼방 라벨의 표시명 두 개가 모두 계수에 반영된다', () {
    final result = ScanResult.fromJson(const {
      'materials': {'cotton': 60, 'polyester': 40},
      'material_details': [
        {
          'original_name': 'cotton',
          'standard_name': 'cotton',
          'display_name': '면',
          'ratio': 60,
          'is_supported': true,
        },
        {
          'original_name': 'polyester',
          'standard_name': 'polyester',
          'display_name': '폴리에스터',
          'ratio': 40,
          'is_supported': true,
        },
      ],
      'care_instruction': '라벨 표기법에 맞춰 관리하세요.',
    });

    final draft = const ScanDraftService().buildFromResult(
      result: result,
      clothingType: tee,
    );

    expect(draft.materials.keys, ['면', '폴리에스터']);

    // (0.6 × 8.3 + 0.4 × 9.5) × 0.18kg = 1.5804.
    // 혼합계수 8.78은 서버가 같은 입력에 내는 값과 같다. 저장 후 표시는 1.54인데,
    // 서버가 대표 무게 180g이 아니라 min·max(100·250g)의 중앙값 175g으로 계산하기
    // 때문이다. 남는 차이는 계수가 아니라 무게 기준에서 온다.
    expect(
      ClothingEstimator.estimateCarbonFootprint(draft.materials, tee),
      1.6,
    );
  });

  test('서버가 알아보지 못한 소재는 원래 이름 그대로 남아 기본계수를 쓴다', () {
    final result = ScanResult.fromJson(const {
      'materials': {'unobtainium': 100},
      'material_details': [
        {
          'original_name': 'unobtainium',
          'standard_name': null,
          'display_name': 'unobtainium',
          'ratio': 100,
          'is_supported': false,
        },
      ],
      'care_instruction': '라벨 표기법에 맞춰 관리하세요.',
    });

    final draft = const ScanDraftService().buildFromResult(
      result: result,
      clothingType: tee,
    );

    expect(draft.materials.keys, ['unobtainium']);
    // 기본계수 10.0 × 0.18kg = 1.8. 이 값은 프리뷰에서 끝나지 않는다 —
    // 서버가 400 MATERIAL_NOT_FOUND로 거부해도 저장 경로는 이 추정값을 옷장에 남긴다.
    expect(
      ClothingEstimator.estimateCarbonFootprint(draft.materials, tee),
      1.8,
    );
  });
}
