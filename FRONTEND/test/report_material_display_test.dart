import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/models/material_name_display.dart';
import 'package:k_dpp/report_screen.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

import 'helpers/fake_closet_storage.dart';

/// 리포트는 소재 키를 그대로 찍지 않고 표시 설정 언어로 바꿔 보여준다(D16).
///
/// 같은 면 셔츠라도 스캔·소재 선택창으로 등록하면 키가 '면', 영문을 직접 쳤거나
/// 2026-09-13 이전 자동완성으로 골랐으면 'cotton'이다. 키를 그대로 찍던 동안에는
/// 옷마다 '면 100%'와 'COTTON 100%'로 갈렸고, 한 옷에 섞이면 '면 50%, COTTON 50%'였다.
void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  Future<MaterialNameDisplayProvider> pumpReport(
    WidgetTester tester,
    Map<String, double> materials, {
    MaterialNameDisplay display = MaterialNameDisplay.korean,
  }) async {
    final closetProvider = ClosetProvider(storage: FakeClosetStorage());
    await closetProvider.addClothes(
      Clothes(
        title: '표시 테스트 셔츠',
        category: '상의',
        health: 82,
        materials: materials,
        careInstruction: '찬물 세탁',
        carbonFootprint: 4.2,
      ),
    );

    final displayProvider = MaterialNameDisplayProvider();
    if (display != displayProvider.display) {
      await displayProvider.setDisplay(display);
    }

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: closetProvider),
          ChangeNotifierProvider.value(value: displayProvider),
        ],
        child: const MaterialApp(home: Scaffold(body: ReportScreen())),
      ),
    );
    await tester.pumpAndSettle();

    return displayProvider;
  }

  testWidgets('저장 키가 한글이든 영문이든 설정 언어의 같은 이름으로 보인다', (tester) async {
    const expectedByDisplay = <MaterialNameDisplay, (String, String)>{
      // (대표 소재, 전체 소재 목록)
      MaterialNameDisplay.korean: ('면 80%', '면 80%, 폴리에스터 20%'),
      MaterialNameDisplay.english: ('COTTON 80%', 'COTTON 80%, POLYESTER 20%'),
      MaterialNameDisplay.koreanAndEnglish: (
        '면 (COTTON) 80%',
        '면 (COTTON) 80%, 폴리에스터 (POLYESTER) 20%',
      ),
    };

    for (final cottonKey in ['면', 'cotton']) {
      for (final entry in expectedByDisplay.entries) {
        final polyesterKey = cottonKey == '면' ? '폴리에스터' : 'polyester';
        await pumpReport(tester, {
          cottonKey: 80,
          polyesterKey: 20,
        }, display: entry.key);

        final (mainMaterial, materialsText) = entry.value;
        final reason = '$cottonKey 키 · ${entry.key.name}';

        // 대표 소재는 태그와 '주요 소재' 카드 값에, 전체 목록은 카드 부제와 '관리 정보' 줄에 나온다.
        expect(find.text(mainMaterial), findsNWidgets(2), reason: reason);
        expect(find.text(materialsText), findsNWidgets(2), reason: reason);
      }
    }
  });

  testWidgets("한 옷에 '면'과 'cotton' 키가 섞여 있어도 한 항목으로 합쳐 보인다", (tester) async {
    await pumpReport(tester, {'면': 50, 'cotton': 50});

    // 대표 소재·전체 목록이 모두 '면 100%'라 네 곳에 같은 글자가 나온다.
    expect(find.text('면 100%'), findsNWidgets(4));
    expect(find.textContaining('면 50%'), findsNothing);
    expect(find.textContaining('COTTON'), findsNothing);
  });

  testWidgets('대표 소재는 같은 소재를 합친 뒤에 고른다', (tester) async {
    // 합치기 전에 고르면 폴리에스터 40이 면 30·cotton 30보다 커 대표 소재가 된다.
    await pumpReport(tester, {'polyester': 40, '면': 30, 'cotton': 30});

    expect(find.text('면 60%'), findsNWidgets(2));
    expect(find.text('폴리에스터 40%, 면 60%'), findsNWidgets(2));
    expect(find.text('폴리에스터 40%'), findsNothing);
  });

  testWidgets('서버 표에 없는 이름은 어느 설정에서도 번역하지 않는다', (tester) async {
    for (final display in MaterialNameDisplay.values) {
      await pumpReport(tester, {
        'organic cotton': 60,
        '오가닉 면': 40,
      }, display: display);

      expect(
        find.text('ORGANIC COTTON 60%, 오가닉 면 40%'),
        findsNWidgets(2),
        reason: display.name,
      );
    }
  });

  testWidgets('설정을 바꾸면 열려 있는 리포트가 바로 새 언어로 다시 그려진다', (tester) async {
    final displayProvider = await pumpReport(tester, {'cotton': 100});

    expect(find.text('면 100%'), findsNWidgets(4));

    await displayProvider.setDisplay(MaterialNameDisplay.english);
    await tester.pumpAndSettle();

    expect(find.text('COTTON 100%'), findsNWidgets(4));
    expect(find.text('면 100%'), findsNothing);
  });

  testWidgets('한글+영문의 긴 소재 이름도 좁은 화면·큰 글자에서 넘치지 않는다', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final closetProvider = ClosetProvider(storage: FakeClosetStorage());
    await closetProvider.addClothes(
      Clothes(
        title: '긴 이름 소재 재킷',
        category: '상의',
        health: 70,
        materials: {'polyurethane': 55, 'cashmere': 45},
        careInstruction: '드라이클리닝',
        carbonFootprint: 12.0,
      ),
    );
    final displayProvider = MaterialNameDisplayProvider();
    await displayProvider.setDisplay(MaterialNameDisplay.koreanAndEnglish);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: closetProvider),
          ChangeNotifierProvider.value(value: displayProvider),
        ],
        child: const MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(textScaler: TextScaler.linear(1.6)),
            child: Scaffold(body: ReportScreen()),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('폴리우레탄 (POLYURETHANE) 55%'), findsNWidgets(2));
  });
}
