import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/theme/app_palette.dart';
import 'package:k_dpp/theme/app_theme.dart';
import 'package:k_dpp/widgets/clothing_category_segmented_control.dart';

// 스캔 '직접 입력'과 리포트 '의류 정보 수정'이 함께 쓰는 분류 세그먼트 컨트롤(결정 134).
void main() {
  Future<List<String>> pumpControl(
    WidgetTester tester, {
    ThemeData? theme,
    String selected = '상의',
    List<String> options = const ['상의', '하의'],
  }) async {
    final changes = <String>[];

    await tester.pumpWidget(
      MaterialApp(
        theme: theme ?? AppTheme.light(),
        home: Scaffold(
          body: Center(
            // 두 시트처럼 왼쪽 정렬 Column 안(폭이 느슨한 제약)에 둔다.
            child: SizedBox(
              width: 320,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  StatefulBuilder(
                    builder: (context, setState) {
                      return ClothingCategorySegmentedControl(
                        options: options,
                        selected: selected,
                        onChanged: (value) {
                          changes.add(value);
                          setState(() => selected = value);
                        },
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    return changes;
  }

  testWidgets('다른 칸을 누르면 그 분류로 바뀌고, 선택된 칸을 다시 눌러도 비워지지 않는다', (tester) async {
    final changes = await pumpControl(tester);

    await tester.tap(find.text('하의'));
    await tester.pumpAndSettle();
    expect(changes, ['하의']);

    await tester.tap(find.text('하의'));
    await tester.pumpAndSettle();
    expect(changes, ['하의']);

    // 선택된 칸에만 체크 표시가 붙는다(색만으로 구분하지 않음).
    expect(find.byIcon(Icons.check), findsOneWidget);
    expect(
      find.descendant(
        of: find.ancestor(
          of: find.text('하의'),
          matching: find.byType(TextButton),
        ),
        matching: find.byIcon(Icons.check),
      ),
      findsOneWidget,
    );
  });

  testWidgets('칸은 부모 폭을 같은 폭으로 나누고, 보이는 높이도 48 이상이다', (tester) async {
    await pumpControl(tester);

    // 버튼 크기는 터치 영역(48)까지 넓혀 재므로, 보이는 칸은 그 안의 Material 로 잰다.
    Size visible(String label) => tester.getSize(
      find
          .ancestor(of: find.text(label), matching: find.byType(Material))
          .first,
    );

    final top = visible('상의');
    final bottom = visible('하의');

    expect(top.width, closeTo(bottom.width, 1));
    expect(top.width + bottom.width, closeTo(320, 4));
    expect(top.height, greaterThanOrEqualTo(48));
  });

  testWidgets(
    '낭독기는 칸마다 이름·버튼·선택 여부를 한 칸으로 읽는다',
    (tester) async {
      final handle = tester.ensureSemantics();
      await pumpControl(tester);

      expect(
        tester.getSemantics(find.text('상의')),
        isSemantics(
          label: '상의',
          isButton: true,
          isSelected: true,
          isInMutuallyExclusiveGroup: true,
        ),
      );
      expect(
        tester.getSemantics(find.text('하의')),
        isSemantics(
          label: '하의',
          isButton: true,
          isSelected: false,
          isInMutuallyExclusiveGroup: true,
        ),
      );

      await tester.tap(find.text('하의'));
      await tester.pumpAndSettle();

      expect(
        tester.getSemantics(find.text('하의')),
        isSemantics(label: '하의', isSelected: true),
      );
      expect(
        tester.getSemantics(find.text('상의')),
        isSemantics(label: '상의', isSelected: false),
      );

      handle.dispose();
    },
    variant: const TargetPlatformVariant({
      TargetPlatform.iOS,
      TargetPlatform.android,
    }),
  );

  for (final (name, theme, palette) in [
    ('라이트', AppTheme.light(), AppPalette.light),
    ('다크', AppTheme.dark(), AppPalette.dark),
  ]) {
    testWidgets('$name: 선택 칸은 강조색 바탕에 흰 글자·체크, 아닌 칸은 기본 글자색', (tester) async {
      await pumpControl(tester, theme: theme);

      Color? textColor(String label) => tester
          .renderObject<RenderParagraph>(find.text(label))
          .text
          .style
          ?.color;

      expect(textColor('상의'), Colors.white);
      expect(textColor('하의'), palette.textPrimary);

      final check = tester.widget<IconTheme>(
        find
            .ancestor(
              of: find.byIcon(Icons.check),
              matching: find.byType(IconTheme),
            )
            .first,
      );
      expect(check.data.color, Colors.white);

      final selectedMaterial = tester.widget<Material>(
        find
            .ancestor(of: find.text('상의'), matching: find.byType(Material))
            .first,
      );
      expect(selectedMaterial.color, AppPalette.accent);
    });
  }

  testWidgets('상의·하의가 아닌 옛 분류도 셋째 칸으로 보이고 선택된다', (tester) async {
    await pumpControl(
      tester,
      selected: '아우터',
      options: const ['상의', '하의', '아우터'],
    );

    expect(find.text('아우터'), findsOneWidget);
    expect(
      find.descendant(
        of: find.ancestor(
          of: find.text('아우터'),
          matching: find.byType(TextButton),
        ),
        matching: find.byIcon(Icons.check),
      ),
      findsOneWidget,
    );
  });
}
