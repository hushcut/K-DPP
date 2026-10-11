import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/theme/app_palette.dart';
import 'package:k_dpp/widgets/number_keyboard_toolbar.dart';

void main() {
  Future<void> pumpToolbar(WidgetTester tester, Brightness brightness) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(brightness: brightness),
        home: Scaffold(
          body: NumberKeyboardToolbar(onDone: () {}, onNext: () {}),
        ),
      ),
    );
  }

  IconButton arrowButton(WidgetTester tester, String label) =>
      tester.widget<IconButton>(
        find.ancestor(
          of: find.byWidgetPredicate(
            (widget) => widget is Icon && widget.semanticLabel == label,
          ),
          matching: find.byType(IconButton),
        ),
      );

  Color? doneColor(WidgetTester tester) => tester
      .widget<TextButton>(find.widgetWithText(TextButton, '완료'))
      .style
      ?.foregroundColor
      ?.resolve({});

  // 막대 색을 따로 두면 링크 색을 바꿀 때 막대만 남는다(DECISIONS 187).
  for (final (name, brightness, palette) in [
    ('라이트', Brightness.light, AppPalette.light),
    ('다크', Brightness.dark, AppPalette.dark),
  ]) {
    testWidgets('$name 테마에서 ∨·[완료]는 링크와 같은 글자 강조색을 쓴다', (tester) async {
      await pumpToolbar(tester, brightness);

      expect(arrowButton(tester, '다음 칸').color, palette.accentText);
      expect(doneColor(tester), palette.accentText);
    });
  }
}
