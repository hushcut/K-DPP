import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';

// 앱 문구가 전부 한국어인데 앱 언어가 기본값(영어)이면 Flutter가 모든 글자를
// 영어로 표시해 TalkBack이 한국어를 영어 음성으로 읽는다(2026-09-18 폰 확인).
void main() {
  testWidgets('앱 언어는 한국어로 고정되고 Flutter 기본 문구도 한국어다', (tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(
            create: (_) => ClosetProvider(storage: FakeClosetStorage()),
          ),
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
          ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
        ],
        child: const MyApp(),
      ),
    );
    await tester.pump();

    final context = tester.element(find.byType(Navigator).first);
    expect(Localizations.localeOf(context), const Locale('ko', 'KR'));
    expect(MaterialLocalizations.of(context).backButtonTooltip, '뒤로');

    // 스플래시의 최소 표시 타이머가 남지 않게 화면을 내리고 시간을 흘려보낸다.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 2));
  });
}
