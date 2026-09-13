import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/home_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:provider/provider.dart';
import 'helpers/fake_closet_storage.dart';

/// 스캔으로 등록한 옷도 소재별 안내를 받는지 확인한다.
///
/// 스캔 경로의 `Clothes.materials` 키는 서버 표시명(한글 '면','울')이다.
/// 리포트의 관리·보관 안내와 홈의 '코튼 소재 관리 팁'이 영문 키워드로만
/// 판별하던 동안에는, 자동완성으로 고른 옷(영문 키)만 안내를 받고
/// **스캔한 옷은 전부 일반 문구로 떨어졌다**.
void main() {
  Clothes clothesWith(Map<String, double> materials, {String title = '테스트 의류'}) {
    return Clothes(
      title: title,
      category: '상의',
      health: 82,
      materials: materials,
      careInstruction: '찬물 세탁',
      carbonFootprint: 9.2,
    );
  }

  Future<void> pumpReport(WidgetTester tester, Clothes item) async {
    final provider = ClosetProvider(storage: FakeClosetStorage());
    await provider.addClothes(item);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: provider),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MaterialApp(home: Scaffold(body: ReportScreen())),
      ),
    );
    await tester.pumpAndSettle();
  }

  group('리포트 소재별 안내', () {
    testWidgets('한글 소재명도 영문과 같은 관리·보관 안내를 받는다', (tester) async {
      const cases = <String, List<String>>{
        '면': ['면/린넨 계열은 미지근한 물', '면/린넨 계열은 충분히 건조'],
        '울': ['울/실크 계열은 마찰과 열', '니트/울 계열은 걸어두기보다'],
        '실크': ['울/실크 계열은 마찰과 열', '실크 계열은 직사광선'],
        '스판덱스': ['신축성 섬유가 포함된'],
        '폴리에스터': ['합성섬유는 높은 온도'],
      };

      for (final entry in cases.entries) {
        await pumpReport(tester, clothesWith({entry.key: 100}));

        for (final expected in entry.value) {
          expect(
            find.textContaining(expected),
            findsOneWidget,
            reason: "'${entry.key}' 의류에 '$expected' 안내가 나오지 않았습니다.",
          );
        }

        // 위젯 트리를 버려 다음 케이스가 이전 상태를 재사용하지 않게 합니다.
        await tester.pumpWidget(const SizedBox.shrink());
      }
    });

    // 서버 별칭 '모'(wool)는 '모달'의 부분 문자열이다. 표준화 없이 부분 일치를
    // 쓰면 모달 니트가 울 안내를 받는다.
    testWidgets('모달은 울 안내를 받지 않는다', (tester) async {
      await pumpReport(tester, clothesWith({'모달': 100}));

      expect(find.textContaining('울/실크 계열은 마찰과 열'), findsNothing);
      expect(find.textContaining('니트/울 계열은 걸어두기보다'), findsNothing);
      // 소재를 못 알아본 것이 아니라 해당 계열이 아닐 뿐이므로 기본 보관 문구가 나온다.
      //
      // 접두사('착용 후 바로 보관하기보다')로 찾으면 안 된다 — 같은 접두사가
      // 세탁 팁 목록에도 **무조건** 들어가므로(report_guide_sections.dart의
      // `_buildCareTips` 마지막 줄), 보관 팁이 빈 문자열이어도 단언이 참이 된다.
      // 실제로 그 기본 반환을 ''로 바꿔도 이 파일 6건이 전부 통과했다.
      expect(
        find.text(
          '착용 후 바로 보관하기보다 잠시 통풍시킨 뒤 정리하면 의류 컨디션 유지에 도움이 됩니다.',
        ),
        findsOneWidget,
      );
    });

    testWidgets('영문 소재명 동작은 그대로다 (회귀 확인)', (tester) async {
      await pumpReport(tester, clothesWith({'cotton': 100}));

      expect(find.textContaining('면/린넨 계열은 미지근한 물'), findsOneWidget);
      expect(find.textContaining('면/린넨 계열은 충분히 건조'), findsOneWidget);
    });
  });

  group('홈 코튼 관리 팁', () {
    Future<void> pumpHome(WidgetTester tester, Clothes item) async {
      final provider = ClosetProvider(storage: FakeClosetStorage());
      await provider.addClothes(item);

      await tester.pumpWidget(
        ChangeNotifierProvider.value(
          value: provider,
          child: const MaterialApp(home: Scaffold(body: HomeScreen())),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets("한글 '면'으로 저장된 옷도 코튼 팁을 받는다", (tester) async {
      await pumpHome(tester, clothesWith({'면': 100}, title: '면 티셔츠'));

      expect(find.text('코튼 소재 관리 팁'), findsOneWidget);
      expect(find.textContaining('면 소재가 포함되어 있어요'), findsOneWidget);
    });

    testWidgets('영문 cotton 동작은 그대로다 (회귀 확인)', (tester) async {
      await pumpHome(tester, clothesWith({'cotton': 100}, title: '코튼 셔츠'));

      expect(find.text('코튼 소재 관리 팁'), findsOneWidget);
    });

    testWidgets('면이 아닌 소재는 코튼 팁을 받지 않는다', (tester) async {
      await pumpHome(tester, clothesWith({'폴리에스터': 100}, title: '폴리 자켓'));

      expect(find.text('코튼 소재 관리 팁'), findsNothing);
      expect(find.text('오늘의 관리 팁'), findsOneWidget);
      // '오늘의 관리 팁'은 등록된 옷이 하나도 없을 때의 제목이기도 하다
      // (home_screen.dart의 latestItem == null 분기). 제목만 보면 옷이 화면에
      // 반영되지 않은 경우까지 통과하므로, 그 옷을 가리키는 본문으로 못박는다.
      expect(
        find.textContaining('폴리 자켓의 세탁 지침을 기준으로'),
        findsOneWidget,
      );
    });
  });
}
