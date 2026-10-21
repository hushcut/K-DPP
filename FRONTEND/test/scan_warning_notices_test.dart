import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/utils/scan_warning_notices.dart';

// AI 연동 협의안 R4: 스캔 응답 warnings 의 공개 코드만 안내 문구로 바꾸고, 모르는 코드·진단 경고는
// 버린다. 코드 표는 AI README '공개 부위·재촬영 안내 (`warnings`, R4)'(ai-integration ab2d517).
void main() {
  const unidentified =
      '부위 표기를 찾지 못해 라벨의 소재를 그대로 읽었어요. 소재와 비율을 확인해 주세요.';
  const leather = '라벨에 비율이 없어 가죽 100%로 보았어요. 확인해 주세요.';
  const retake = '소재·혼용률 부분을 다시 찍어 주세요.';

  // 지금 AI·백엔드가 실제로 보내는 진단 경고와, 공개 표에 없는 코드 모양들이다.
  const unknownOnly = [
    'generic:unpaired_ratio_rows',
    'manual_composition_review_required:outer',
    'representative_part_fallback:lining',
    'OCR 좌표를 바탕으로 재구성한 줄 순서를 사용했습니다.',
    'composition_part:shell',
    'composition_part:',
    'composition_part:outer ',
    'COMPOSITION_PART:OUTER',
    'composition_action:retake',
    'leather_composition:outer',
  ];

  group('성공 결과의 안내', () {
    for (final (code, name) in [
      ('outer', '겉감'),
      ('outer_2', '겉감2'),
      ('lining', '안감'),
      ('filling', '충전재'),
      ('pocket', '주머니'),
      ('rib', '시보리'),
      ('sleeve', '소매'),
      ('color_block', '배색'),
      ('embroidery_yarn', '자수실'),
    ]) {
      test('composition_part:$code 는 "$name 기준으로 읽었어요." 한 줄이다', () {
        expect(ScanWarningNotices.forSuccess(['composition_part:$code']), [
          '$name 기준으로 읽었어요.',
        ]);
      });
    }

    test('부위 미확정은 소재와 비율을 확인하라는 안내다', () {
      expect(
        ScanWarningNotices.forSuccess(['composition_part:unidentified']),
        [unidentified],
      );
    });

    test('가죽 추정 경고는 부위가 무엇이든 접두어로 알아보고, 부위 안내 뒤에 한 번만 둔다', () {
      expect(
        ScanWarningNotices.forSuccess([
          'implicit_leather_composition:outer',
          'composition_part:outer',
          'implicit_leather_composition:shell',
        ]),
        ['겉감 기준으로 읽었어요.', leather],
      );
      expect(
        ScanWarningNotices.forSuccess(['implicit_leather_composition:lining']),
        [leather],
      );
    });

    test('부위 코드가 여럿 와도 처음 알아본 것 하나만 보인다', () {
      expect(
        ScanWarningNotices.forSuccess([
          'composition_part:shell',
          'composition_part:lining',
          'composition_part:outer',
          'composition_part:unidentified',
        ]),
        ['안감 기준으로 읽었어요.'],
      );
    });

    test('진단 경고·모르는 코드만 있으면 아무것도 보이지 않고, 아는 코드와 섞여도 버린다', () {
      expect(ScanWarningNotices.forSuccess(unknownOnly), isEmpty);
      expect(ScanWarningNotices.forSuccess(const []), isEmpty);
      expect(
        ScanWarningNotices.forSuccess([
          ...unknownOnly,
          'composition_part:rib',
          ...unknownOnly,
        ]),
        ['시보리 기준으로 읽었어요.'],
      );
    });

    test('재촬영 권고는 실패에만 오는 코드라 성공 결과에는 보이지 않는다', () {
      expect(
        ScanWarningNotices.forSuccess([
          'composition_action:retake_composition_region',
        ]),
        isEmpty,
      );
    });
  });

  group('실패(422)의 안내', () {
    test('재촬영 권고 코드가 있으면 다시 찍으라는 안내 한 줄이다', () {
      expect(
        ScanWarningNotices.forFailure([
          'generic:unpaired_ratio_rows',
          'composition_action:retake_composition_region',
          'composition_action:retake_composition_region',
        ]),
        [retake],
      );
    });

    test('부위·가죽·모르는 코드는 실패 화면에 보이지 않는다', () {
      expect(
        ScanWarningNotices.forFailure([
          ...unknownOnly,
          'composition_part:outer',
          'composition_part:unidentified',
          'implicit_leather_composition:outer',
        ]),
        isEmpty,
      );
    });
  });

  test('어떤 입력에서도 받은 문자열을 그대로 내보내지 않는다', () {
    final inputs = [
      ...unknownOnly,
      'composition_part:outer',
      'composition_part:unidentified',
      'composition_action:retake_composition_region',
      'implicit_leather_composition:outer',
    ];
    final notices = [
      ...ScanWarningNotices.forSuccess(inputs),
      ...ScanWarningNotices.forFailure(inputs),
    ];

    expect(notices, isNotEmpty);
    for (final notice in notices) {
      expect(inputs, isNot(contains(notice)));
      // 코드는 모두 ':'·'_' 로 이뤄져 있어, 문구에 그 글자가 있으면 원문이 새어 나간 것이다.
      expect(notice, isNot(contains(':')));
      expect(notice, isNot(contains('_')));
    }
  });
}
