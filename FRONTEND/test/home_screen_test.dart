import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/home_screen.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:provider/provider.dart';
import 'helpers/fake_closet_storage.dart';

/// 홈 대시보드가 옷장 집계값을 화면 문구로 옮기는 분기를 확인한다.
///
/// 합계·소나무 환산·관리 팁·최근 의류 순서는 모두 [ClosetProvider] 의 값을 그대로
/// 계산해 보여 주는데, 그동안 홈 화면을 띄운 테스트는 코튼 팁 하나뿐이라 이 계산이
/// 바뀌어도 전체 테스트가 초록이었다.
void main() {
  Clothes clothesWith({
    required String title,
    int health = 82,
    double carbonFootprint = 1.0,
    Map<String, double> materials = const {'폴리에스터': 100},
    DateTime? registeredAt,
  }) {
    return Clothes(
      title: title,
      category: '상의',
      health: health,
      materials: materials,
      careInstruction: '찬물 세탁',
      carbonFootprint: carbonFootprint,
      registeredAt: registeredAt,
    );
  }

  Future<void> pumpHome(
    WidgetTester tester,
    List<Clothes> items, {
    VoidCallback? onStartScan,
  }) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    for (final item in items) {
      await provider.addClothes(item);
    }

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          home: Scaffold(body: HomeScreen(onStartScan: onStartScan)),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('탄소 현황', () {
    testWidgets('합계를 소수 한 자리로, 벌 수와 소나무 환산을 함께 보여 준다', (tester) async {
      await pumpHome(tester, [
        clothesWith(title: '셔츠', carbonFootprint: 2.5),
        clothesWith(title: '바지', carbonFootprint: 4.5),
      ]);

      expect(find.text('7.0'), findsOneWidget);
      expect(find.text('현재 옷장에 2개의 의류가 등록되어 있어요.'), findsOneWidget);
      expect(find.text('등록된 의류 2벌 기준으로 집계된 값입니다.'), findsOneWidget);
      // 7.0 / 6 을 올림해 2그루다. 내림·반올림이면 1그루가 된다.
      expect(find.text('소나무 약 2그루 규모와 비슷해요'), findsOneWidget);
    });

    // 환산은 올림이라 아주 적은 양도 '약 1그루' 다(NEXT_WORK D12 — 고칠지는 따로).
    // 반올림으로 바뀌면 0그루가 되어 '등록해 보세요' 문구로 떨어진다.
    testWidgets('0보다 크면 아무리 적어도 소나무 1그루로 올린다', (tester) async {
      await pumpHome(tester, [clothesWith(title: '양말', carbonFootprint: 0.1)]);

      expect(find.text('0.1'), findsOneWidget);
      expect(find.text('소나무 약 1그루 규모와 비슷해요'), findsOneWidget);
    });

    testWidgets('빈 옷장은 0.0 과 등록 안내를 보여 준다', (tester) async {
      var scanRequests = 0;
      await pumpHome(tester, const [], onStartScan: () => scanRequests++);

      expect(find.text('0.0'), findsOneWidget);
      expect(
        find.text('아직 등록된 의류가 없어요. 스캔 탭에서 첫 의류를 등록해 보세요.'),
        findsOneWidget,
      );
      expect(find.text('의류를 등록하면 탄소 현황이 자동으로 집계됩니다.'), findsOneWidget);
      expect(find.text('의류를 등록해 탄소 정보를 확인해 보세요'), findsOneWidget);
      expect(find.textContaining('그루'), findsNothing);

      // 관리 팁도 옷이 없을 때의 문구다.
      expect(find.text('오늘의 관리 팁'), findsOneWidget);
      expect(
        find.text('새 의류를 등록하면 소재와 상태를 바탕으로 맞춤 관리 팁을 제공할 수 있어요.'),
        findsOneWidget,
      );

      // 최근 의류 자리에는 빈 카드와 스캔 버튼이 나온다.
      expect(find.text('아직 등록된 의류가 없습니다'), findsOneWidget);
      await tester.ensureVisible(find.text('스캔하러 가기'));
      await tester.tap(find.text('스캔하러 가기'));
      expect(scanRequests, 1);
    });
  });

  group('관리 팁', () {
    // 낮은 평균 건강도 경고는 소재 팁보다 먼저다. 가장 최근 옷이 면이어도 경고가 나온다.
    testWidgets('평균 건강도가 40 미만이면 최근 옷이 면이어도 점검 경고를 띄운다', (tester) async {
      await pumpHome(tester, [
        clothesWith(title: '낡은 니트', health: 30),
        clothesWith(title: '면 티셔츠', health: 40, materials: const {'면': 100}),
      ]);

      expect(find.text('의류 컨디션 점검이 필요해요'), findsOneWidget);
      expect(find.textContaining('현재 평균 건강도가 낮아요.'), findsOneWidget);
      expect(find.text('코튼 소재 관리 팁'), findsNothing);
    });

    // 경계는 '40 미만' 이다. 평균이 정확히 40 이면 경고 대신 소재 팁으로 간다.
    testWidgets('평균 건강도가 정확히 40 이면 점검 경고 대신 소재 팁을 띄운다', (tester) async {
      await pumpHome(tester, [
        clothesWith(title: '낡은 니트', health: 30),
        clothesWith(title: '면 티셔츠', health: 50, materials: const {'면': 100}),
      ]);

      expect(find.text('의류 컨디션 점검이 필요해요'), findsNothing);
      expect(find.text('코튼 소재 관리 팁'), findsOneWidget);
    });
  });

  group('최근 등록한 의류', () {
    double topOf(WidgetTester tester, String title) =>
        tester.getTopLeft(find.text(title)).dy;

    testWidgets('등록 시각이 최신인 두 벌만 최신순으로, 시각 없는 옛 항목은 뒤로 보낸다', (
      tester,
    ) async {
      await pumpHome(tester, [
        clothesWith(title: '8월 1일 셔츠', registeredAt: DateTime(2026, 8, 1)),
        clothesWith(title: '8월 3일 셔츠', registeredAt: DateTime(2026, 8, 3)),
        clothesWith(title: '8월 2일 셔츠', registeredAt: DateTime(2026, 8, 2)),
        // 목록 맨 뒤지만 등록 시각이 없어 시각 있는 항목보다 오래된 것으로 친다.
        clothesWith(title: '시각 없는 셔츠'),
      ]);

      expect(find.text('8월 3일 셔츠'), findsOneWidget);
      expect(find.text('8월 2일 셔츠'), findsOneWidget);
      expect(find.text('8월 1일 셔츠'), findsNothing);
      expect(find.text('시각 없는 셔츠'), findsNothing);
      expect(
        topOf(tester, '8월 3일 셔츠'),
        lessThan(topOf(tester, '8월 2일 셔츠')),
      );
    });

    testWidgets('등록 시각이 없는 옛 항목끼리는 목록 뒤쪽을 최신으로 본다', (tester) async {
      await pumpHome(tester, [
        clothesWith(title: '먼저 넣은 셔츠'),
        clothesWith(title: '나중에 넣은 셔츠'),
      ]);

      expect(
        topOf(tester, '나중에 넣은 셔츠'),
        lessThan(topOf(tester, '먼저 넣은 셔츠')),
      );
    });

    testWidgets('건강도 구간마다 다른 관리 문구를 붙인다', (tester) async {
      // 문구 경계는 20·40·70 '이하' 다. 경계값과 그 바로 위를 짝지어 본다.
      const cases = <int, String>{
        20: '수명 만료에 가까워요. 재사용 또는 분리배출 방법을 함께 확인해 보세요.',
        21: '관리 주의 단계예요. 세탁 빈도와 건조 방식을 점검해 주세요.',
        40: '관리 주의 단계예요. 세탁 빈도와 건조 방식을 점검해 주세요.',
        41: '현재 상태는 보통이에요. 세탁 지침을 지키면 더 오래 입을 수 있어요.',
        70: '현재 상태는 보통이에요. 세탁 지침을 지키면 더 오래 입을 수 있어요.',
        71: '현재 상태가 좋아요. 지금의 관리 방식을 유지해 주세요.',
      };

      for (final entry in cases.entries) {
        await pumpHome(tester, [
          clothesWith(title: '건강도 ${entry.key} 셔츠', health: entry.key),
        ]);

        expect(
          find.text(entry.value),
          findsOneWidget,
          reason: '건강도 ${entry.key} 에 맞는 문구가 아닙니다.',
        );

        // 위젯 트리를 버려 다음 케이스가 이전 상태를 재사용하지 않게 합니다.
        await tester.pumpWidget(const SizedBox.shrink());
      }
    });
  });
}
