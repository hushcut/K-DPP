import 'material_name.dart';

/// 스캔 응답 `warnings` 의 공개 코드(AI 연동 협의안 R4)를 화면 안내 문구로 바꾼다.
///
/// `warnings` 에는 공개 코드와 함께 진단 경고(`generic:unpaired_ratio_rows` 같은 판정 메모,
/// 'OCR 좌표를 바탕으로…' 같은 처리 안내)가 섞여 온다. 아는 코드만 문구로 바꾸고 나머지는 버려,
/// 원문은 어떤 경우에도 화면에 나가지 않는다. 코드 표는 AI README '공개 부위·재촬영 안내
/// (`warnings`, R4)' 절이고, 가죽 추정 경고는 접두어로 판별한다(2026-10-21 사용자 결정 A).
class ScanWarningNotices {
  const ScanWarningNotices._();

  static const String _partPrefix = 'composition_part:';
  static const String _unidentifiedPart = 'composition_part:unidentified';
  static const String _retakeAction =
      'composition_action:retake_composition_region';
  static const String _implicitLeatherPrefix = 'implicit_leather_composition:';

  // 공개 부위 코드 뒷부분 → 화면에 쓰는 부위 이름이다.
  static const Map<String, String> _partNames = {
    'outer': '겉감',
    'outer_2': '겉감2',
    'lining': '안감',
    'filling': '충전재',
    'pocket': '주머니',
    'rib': '시보리',
    'sleeve': '소매',
    'color_block': '배색',
    'embroidery_yarn': '자수실',
  };

  // 부위 표기가 없는 흔한 라벨('COTTON 80% POLYESTER 20%')에서도 나오므로 오류처럼 들리지 않게
  // 한다. 계산·저장은 막지 않고 폼에서 확인하게 한다(2026-10-21 사용자 결정 A).
  static const String _unidentifiedPartNotice =
      '부위 표기를 찾지 못해 라벨의 소재를 그대로 읽었어요. 소재와 비율을 확인해 주세요.';
  static const String _implicitLeatherNotice =
      '라벨에 비율이 없어 가죽 100%로 보았어요. 확인해 주세요.';
  static const String _retakeNotice = '소재·혼용률 부분을 다시 찍어 주세요.';

  /// 분석에 성공했을 때 결과 화면에 보일 안내다.
  ///
  /// 부위 안내는 처음 나온 하나만 두고(AI 는 고른 부위 하나만 보낸다), 가죽 추정 안내가 있으면
  /// 그 뒤에 둔다. 재촬영 권고는 실패에만 오는 코드라 여기서는 버린다.
  static List<String> forSuccess(Iterable<String> warnings) {
    String? partNotice;
    var hasImplicitLeather = false;

    for (final warning in warnings) {
      if (warning.startsWith(_implicitLeatherPrefix)) {
        hasImplicitLeather = true;
      } else {
        partNotice ??= _partNotice(warning);
      }
    }

    return List.unmodifiable([
      ?partNotice,
      if (hasImplicitLeather) _implicitLeatherNotice,
    ]);
  }

  /// 분석에 실패했을 때(422) 종류 선택 시트의 실패 이유 아래에 보일 안내다. 재촬영 권고뿐이다.
  static List<String> forFailure(Iterable<String> warnings) {
    return warnings.contains(_retakeAction) ? const [_retakeNotice] : const [];
  }

  /// 서버가 `is_supported: false` 로 표시한 소재(AI 는 읽지만 서버 계수표에 없는 소재)를 저장 전에
  /// 알리는 문구다(협의안 R2). 읽은 것과 계산할 수 없는 것을 나눠 말하고, 라벨이 맞는 사용자에게
  /// 다른 소재를 고르라고 떠밀지 않는다. 이름은 편집 폼에 보이는 표시명이다.
  static String forUnsupportedMaterials(List<String> names) {
    return '${MaterialName.summarize(names)} 소재는 읽었지만 탄소 계산 기준이 없어 저장할 수 없어요. '
        '라벨과 다르면 고쳐 주세요.';
  }

  static String? _partNotice(String warning) {
    if (warning == _unidentifiedPart) return _unidentifiedPartNotice;
    if (!warning.startsWith(_partPrefix)) return null;

    final partName = _partNames[warning.substring(_partPrefix.length)];

    return partName == null ? null : '$partName 기준으로 읽었어요.';
  }
}
