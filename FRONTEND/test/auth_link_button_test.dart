import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/theme/app_palette.dart';
import 'package:k_dpp/widgets/auth_form_widgets.dart';

void main() {
  const sentence = '계정이 없으신가요? 회원가입';

  Future<void> pumpLink(WidgetTester tester, Brightness brightness) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(brightness: brightness),
        home: Scaffold(
          body: Center(
            child: AuthLinkButton(
              prompt: '계정이 없으신가요?',
              action: '회원가입',
              onPressed: () {},
            ),
          ),
        ),
      ),
    );
  }

  /// 링크 글자의 바탕 스타일과 각 조각(앞 문장·동작 글자)입니다.
  (TextStyle?, List<TextSpan>) textOf(WidgetTester tester) {
    final text = tester.widget<Text>(find.text(sentence));
    final spans = <TextSpan>[];
    text.textSpan!.visitChildren((span) {
      if (span is TextSpan && span.text != null) spans.add(span);
      return true;
    });
    return (text.style, spans);
  }

  testWidgets('밑줄 없이 동작 글자만 진한 강조색으로 보인다', (tester) async {
    await pumpLink(tester, Brightness.light);

    final (baseStyle, spans) = textOf(tester);

    expect(baseStyle?.decoration, isNot(TextDecoration.underline));
    for (final span in spans) {
      expect(span.style?.decoration, isNot(TextDecoration.underline));
    }
    expect(spans.map((span) => span.text), ['계정이 없으신가요? ', '회원가입']);
    expect(spans.first.style?.color, isNull, reason: '앞 문장은 바탕의 회색');
    expect(spans.last.style?.color, AppPalette.accent);
    expect(spans.last.style?.fontWeight, FontWeight.w700);
  });

  testWidgets('다크 모드에서는 대비가 맞게 밝힌 강조색을 쓴다', (tester) async {
    await pumpLink(tester, Brightness.dark);

    final (_, spans) = textOf(tester);

    // 다크 배경(#121212)에서 브랜드 강조색은 대비 3.4:1 이라 글자로 쓰지 않는다.
    expect(spans.last.style?.color, AppPalette.dark.accentText);
    expect(spans.last.style?.color, isNot(AppPalette.accent));
  });

  testWidgets('낭독기는 앞 문장과 동작 글자를 이어 한 버튼으로 읽는다', (tester) async {
    final semantics = tester.ensureSemantics();
    await pumpLink(tester, Brightness.light);

    expect(
      tester.getSemantics(find.bySemanticsLabel(sentence)),
      isSemantics(label: sentence, isButton: true, hasTapAction: true),
    );

    semantics.dispose();
  });
}
