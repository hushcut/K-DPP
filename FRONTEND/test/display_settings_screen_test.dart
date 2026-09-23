import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/display_settings_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/material_name_display.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:k_dpp/settings_screen.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  Future<void> pumpDisplaySettings(
    WidgetTester tester,
    MaterialNameDisplayProvider materialNameDisplayProvider,
  ) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider.value(value: materialNameDisplayProvider),
          ChangeNotifierProvider(
            create: (_) => NavigationBarOpacityProvider(),
          ),
        ],
        child: const MaterialApp(home: DisplaySettingsScreen()),
      ),
    );
    await tester.pumpAndSettle();
  }

  // 소재 이름 표시 항목은 테마 미리보기 아래에 있어 스크롤해야 보입니다.
  Future<void> scrollTo(WidgetTester tester, Finder finder) async {
    await tester.scrollUntilVisible(
      finder,
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
  }

  Finder selectedIconOf(String label) {
    return find.descendant(
      of: find.ancestor(of: find.text(label), matching: find.byType(InkWell)),
      matching: find.byIcon(Icons.radio_button_checked),
    );
  }

  testWidgets('소재 이름 표시 언어를 고르면 바로 선택되고 기기에 저장된다', (tester) async {
    final provider = MaterialNameDisplayProvider();
    await pumpDisplaySettings(tester, provider);

    // 각 항목은 리포트와 같은 변환으로 만든 예시를 보여준다.
    await scrollTo(tester, find.text('면 (COTTON) 80%'));
    expect(find.text('면 80%'), findsOneWidget);
    expect(find.text('COTTON 80%'), findsOneWidget);
    expect(selectedIconOf('한글'), findsOneWidget);

    await tester.tap(find.text('영문'));
    await tester.pumpAndSettle();

    expect(provider.display, MaterialNameDisplay.english);
    expect(selectedIconOf('영문'), findsOneWidget);
    expect(selectedIconOf('한글'), findsNothing);
    expect(
      await SharedPreferencesAsync().getString('material_name_display'),
      'en',
    );
  });

  testWidgets('저장에 실패하면 이전 선택으로 돌아가고 안내한다', (tester) async {
    final provider = MaterialNameDisplayProvider(
      preferences: _FailingPreferences(),
    );
    await pumpDisplaySettings(tester, provider);

    await scrollTo(tester, find.text('한글+영문'));
    await tester.tap(find.text('한글+영문'));
    await tester.pumpAndSettle();

    expect(provider.display, MaterialNameDisplay.korean);
    expect(selectedIconOf('한글'), findsOneWidget);
    expect(
      find.text('소재 이름 표시 설정을 저장하지 못했어요. 다시 시도해 주세요.'),
      findsOneWidget,
    );
  });

  testWidgets('하단 메뉴 불투명도 슬라이더는 85%에서 시작하고, 끌면 바로 반영되며 손을 떼면 저장된다', (
    tester,
  ) async {
    await pumpDisplaySettings(tester, MaterialNameDisplayProvider());
    await scrollTo(tester, find.text('배경 불투명도'));

    expect(find.text('85%'), findsOneWidget);
    final slider = find.byType(Slider);
    expect(tester.widget<Slider>(slider).value, 0.85);

    // 오른쪽 끝까지 끌면 100%다.
    await tester.drag(slider, const Offset(400, 0));
    await tester.pumpAndSettle();

    expect(find.text('100%'), findsOneWidget);
    expect(tester.widget<Slider>(slider).value, 1.0);

    // 새 Provider는 앱을 다시 연 상황이다. 저장소에서 100%를 읽어야 한다.
    final reopened = NavigationBarOpacityProvider();
    await reopened.load();
    expect(reopened.opacity, 1.0);
  });

  testWidgets('하단 메뉴 불투명도 슬라이더는 50% 아래로 내려가지 않는다', (tester) async {
    await pumpDisplaySettings(tester, MaterialNameDisplayProvider());
    await scrollTo(tester, find.text('배경 불투명도'));

    await tester.drag(find.byType(Slider), const Offset(-400, 0));
    await tester.pumpAndSettle();

    expect(find.text('50%'), findsOneWidget);
    expect(tester.widget<Slider>(find.byType(Slider)).value, 0.5);
  });

  testWidgets('하단 메뉴 불투명도 저장에 실패하면 안내하고 이전 값으로 돌아간다', (tester) async {
    final opacityProvider = NavigationBarOpacityProvider(
      preferences: _FailingPreferences(),
    );

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ChangeNotifierProvider.value(value: opacityProvider),
        ],
        child: const MaterialApp(home: DisplaySettingsScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await scrollTo(tester, find.text('배경 불투명도'));

    await tester.drag(find.byType(Slider), const Offset(400, 0));
    await tester.pumpAndSettle();

    expect(
      find.text('하단 메뉴 설정을 저장하지 못했어요. 다시 시도해 주세요.'),
      findsOneWidget,
    );
    expect(opacityProvider.opacity, 0.85);
    expect(find.text('85%'), findsOneWidget);
  });

  testWidgets('설정 메뉴의 화면 설정 설명에 소재 이름 표시 언어가 함께 보인다', (tester) async {
    final closetProvider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: FakeAuthSessionStorage(),
    );
    final displayProvider = MaterialNameDisplayProvider();

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: closetProvider),
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider.value(value: displayProvider),
        ],
        child: const MaterialApp(home: SettingsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('시스템 설정 · 소재 이름 한글'), findsOneWidget);

    await displayProvider.setDisplay(MaterialNameDisplay.koreanAndEnglish);
    await tester.pumpAndSettle();

    expect(find.text('시스템 설정 · 소재 이름 한글+영문'), findsOneWidget);
  });
}

class _FailingPreferences extends Fake implements SharedPreferencesAsync {
  @override
  Future<void> setString(String key, String value) async {
    throw StateError('저장소 오류');
  }

  @override
  Future<void> setDouble(String key, double value) async {
    throw StateError('저장소 오류');
  }
}
