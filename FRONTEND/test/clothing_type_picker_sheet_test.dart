import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothing_type_option.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';
import 'package:k_dpp/widgets/number_keyboard_toolbar.dart';

// 유형 선택 시트의 닫기 경로를 경로별로 확인한다(C21).
// PopScope는 시스템 뒤로가기만 막고, 드래그·손잡이·접근성 닫기는 Navigator.pop으로 가서
// PopScope를 거치지 않으므로 경로마다 따로 시험한다.
// - 화면을 폰 크기로 고정한다. 느린 드래그는 시트 높이의 절반을 넘기지 않으면 닫지 않아
//   가짜로 통과하므로, 드래그 경로는 fling(700px/s 초과)으로 시험한다.
// - 하단 안전 영역은 기본 테스트 화면에 없으므로 padding을 넣어 만든다.
void main() {
  group('필수 선택 시트(분석 결과 확인)', () {
    const prompt = ClothingTypePickerDiscardPrompt.analysisResult;

    testWidgets('손잡이 자리를 빠르게 끌어내려도 닫히지 않는다', (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      final rect = _sheetRect(tester);
      await tester.flingFrom(
        Offset(rect.center.dx, rect.top + 24),
        const Offset(0, 300),
        3000,
      );
      await tester.pumpAndSettle();

      expect(_isSheetOpen(), isTrue);
      expect(sheet.completed, isFalse);
    });

    testWidgets('하단 안전 영역을 빠르게 끌어내려도 닫히지 않는다', (tester) async {
      _usePhoneView(tester, bottomInset: 48);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      final rect = _sheetRect(tester);
      await tester.flingFrom(
        Offset(rect.center.dx, rect.bottom - 10),
        const Offset(0, 100),
        3000,
      );
      await tester.pumpAndSettle();

      expect(_isSheetOpen(), isTrue);
      expect(sheet.completed, isFalse);
    });

    testWidgets('손잡이의 접근성 닫기 동작이 없다', (tester) async {
      final semantics = tester.ensureSemantics();
      _usePhoneView(tester);
      await _openSheet(tester, discardPrompt: prompt);

      // Flutter 손잡이는 'Dismiss' 접근성 탭으로 시트를 닫는다(TalkBack).
      expect(find.bySemanticsLabel('Dismiss'), findsNothing);
      expect(_isSheetOpen(), isTrue);
      semantics.dispose();
    });

    testWidgets('끌어서 닫을 수 없으므로 손잡이를 그리지 않는다', (tester) async {
      _usePhoneView(tester);
      await _openSheet(tester, discardPrompt: prompt);

      expect(_dragHandles(), findsNothing);
    });

    testWidgets('직접 무게 입력에서 키보드가 올라와도 시트가 넘치지 않는다', (tester) async {
      // 2026-09-18 폰 확인(SM-N986N): 'BOTTOM OVERFLOWED BY 122 PIXELS'.
      // 키보드 높이는 그 폰 스크린샷에서 잰 삼성 키보드(숫자 줄·추천 줄 포함) 1098 물리 픽셀.
      // (정정 2026-09-19: 처음엔 '실측 418'이라 적었는데, 418은 이 테스트 배율 2.625로 나눈 값이다.
      // 그 폰의 실제 배율은 2.8125라 약 390dp — 물리 픽셀로 적어 배율과 무관하게 했다)
      _usePhoneView(tester);
      await _openSheet(tester, discardPrompt: prompt);
      await tester.scrollUntilVisible(find.text('직접 입력'), 100);
      await tester.tap(find.text('직접 입력'));
      await tester.pumpAndSettle();

      tester.view.viewInsets = const FakeViewPadding(bottom: 1098);
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets('iOS 무게 칸에는 키보드 위에 막대가 뜨고(∧ 는 의류 종류로, ∨ 는 흐림), 키보드가 올라와도 시트가 넘치지 않는다', (
      tester,
    ) async {
      // iOS 숫자 키패드에는 확인 키가 없다. 무게 뒤로 이어지는 입력란이 없어 ∨ 는 흐리다(DECISIONS 177).
      _usePhoneView(tester);
      EditableText.debugDeterministicCursor = true;
      addTearDown(() => EditableText.debugDeterministicCursor = false);
      await _openSheet(tester, discardPrompt: prompt);
      await tester.scrollUntilVisible(find.text('직접 입력'), 100);
      // iOS 스크롤은 멈춘 뒤에도 항목 중심이 화면 밖에 걸칠 수 있어 끝까지 끌어온다.
      await tester.ensureVisible(find.text('직접 입력'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('직접 입력'));
      await tester.pumpAndSettle();
      expect(find.text('직접 무게 입력'), findsOneWidget);
      // 의류 종류 칸이 먼저 포커스를 받으므로 아직 막대가 없다.
      expect(find.byType(NumberKeyboardToolbar), findsNothing);

      await tester.tap(find.widgetWithText(TextField, '실제 무게'));
      tester.view.viewInsets = const FakeViewPadding(bottom: 1098);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(_toolbarButton('완료'), findsOneWidget);
      expect(_toolbarIconButton('다음 칸').onPressed, isNull);

      // ∧ 는 앞 칸인 의류 종류로 간다. 글자 칸이라 막대는 사라진다.
      await tester.tap(_toolbarButton('이전 칸'));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<EditableText>(
              find.descendant(
                of: find.widgetWithText(TextField, '의류 종류'),
                matching: find.byType(EditableText),
              ),
            )
            .focusNode
            .hasFocus,
        isTrue,
      );
      expect(find.byType(NumberKeyboardToolbar), findsNothing);

      await tester.tap(find.widgetWithText(TextField, '실제 무게'));
      await tester.pumpAndSettle();
      await tester.tap(_toolbarButton('완료'));
      await tester.pumpAndSettle();
      expect(find.byType(NumberKeyboardToolbar), findsNothing);
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets('바깥을 탭해도 닫히지 않고 확인창도 뜨지 않는다', (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      await tester.tapAt(const Offset(5, 5));
      await tester.pumpAndSettle();

      // 바깥 탭이 허용되면 PopScope가 막아 확인창이 뜨므로, 시트 유지만으로는 부족하다.
      expect(find.byType(AlertDialog), findsNothing);
      expect(_isSheetOpen(), isTrue);
      expect(sheet.completed, isFalse);
    });

    testWidgets('뒤로가기는 확인을 거쳐, 계속하면 시트를 유지하고 버리면 null로 닫힌다', (
      tester,
    ) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text(prompt.title), findsOneWidget);

      await tester.tap(_dialogButton('선택 계속하기'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(_isSheetOpen(), isTrue);
      expect(sheet.completed, isFalse);

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      await tester.tap(_dialogButton('다시 촬영'));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(_isSheetOpen(), isFalse);
      expect(sheet.completed, isTrue);
      expect(sheet.result, isNull);
    });

    testWidgets("시트 안 '다시 촬영' 버튼도 같은 확인을 거쳐 null로 닫힌다", (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      await tester.tap(find.text('다시 촬영'));
      await tester.pumpAndSettle();
      expect(find.text(prompt.title), findsOneWidget);

      await tester.tap(_dialogButton('다시 촬영'));
      await tester.pumpAndSettle();

      expect(_isSheetOpen(), isFalse);
      expect(sheet.completed, isTrue);
      expect(sheet.result, isNull);
    });

    testWidgets('유형을 고르면 확인 없이 그 유형으로 닫힌다', (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      await tester.tap(find.text('니트'));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(_isSheetOpen(), isFalse);
      expect(sheet.completed, isTrue);
      expect(sheet.result?.label, '니트');
    });

    testWidgets('직접 입력 화면에서 뒤로가기는 확인 없이 목록으로 돌아간다', (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      await tester.scrollUntilVisible(find.text('직접 입력'), 100);
      await tester.tap(find.text('직접 입력'));
      await tester.pumpAndSettle();
      expect(find.text('직접 무게 입력'), findsWidgets);

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(find.text('의류 종류 선택'), findsOneWidget);
      expect(_isSheetOpen(), isTrue);
      expect(sheet.completed, isFalse);
    });

    testWidgets('직접 입력의 분류는 세그먼트로 고르고, 고른 분류로 닫힌다(결정 134)', (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester, discardPrompt: prompt);

      await tester.scrollUntilVisible(find.text('직접 입력'), 100);
      await tester.tap(find.text('직접 입력'));
      await tester.pumpAndSettle();

      final control = find.byType(SegmentedButton<String>);
      expect(control, findsOneWidget);
      expect(tester.widget<SegmentedButton<String>>(control).selected, {
        ClothingTypeCatalog.defaultOption.category,
      });

      await tester.enterText(find.byType(TextField).at(0), '조끼');
      await tester.enterText(find.byType(TextField).at(1), '300');
      await tester.tap(find.descendant(of: control, matching: find.text('하의')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('적용하기'));
      await tester.pumpAndSettle();

      expect(sheet.completed, isTrue);
      expect(sheet.result?.label, '조끼');
      expect(sheet.result?.category, '하의');
    });
  });

  testWidgets('분석 실패 후 직접 입력 시트는 실패 경로 문구로 확인한다', (tester) async {
    _usePhoneView(tester);
    await _openSheet(
      tester,
      discardPrompt: ClothingTypePickerDiscardPrompt.manualAfterFailure,
    );

    await tester.tap(find.text('다시 촬영'));
    await tester.pumpAndSettle();

    // 제목은 두 경로가 같으므로 버려지는 내용을 설명하는 본문으로 구분한다.
    expect(
      find.text(ClothingTypePickerDiscardPrompt.manualAfterFailure.message),
      findsOneWidget,
    );
    expect(
      find.text(ClothingTypePickerDiscardPrompt.analysisResult.message),
      findsNothing,
    );
  });

  // DECISIONS 96: 분석이 실패하면 고른 뒤 띄우던 배너 대신 시트 맨 위에서 이유를 알린다.
  // 시트가 열리면 VoiceOver 가 첫 칸부터 읽으므로 이유가 낭독 순서의 맨 앞이어야 한다.
  group('분석 실패 이유 줄', () {
    const failureMessage = '라벨을 읽지 못했어요. 직접 입력해 주세요.';

    testWidgets(
      '실패 이유를 주면 제목 위에 빨간 느낌표와 함께 보이고, 시트에서 가장 먼저 읽힌다',
      (tester) async {
        final semantics = tester.ensureSemantics();
        _usePhoneView(tester);
        await _openSheet(
          tester,
          discardPrompt: ClothingTypePickerDiscardPrompt.manualAfterFailure,
          failureMessage: failureMessage,
        );

        final reason = find.descendant(
          of: find.byType(BottomSheet),
          matching: find.text(failureMessage),
        );
        expect(reason, findsOneWidget);
        expect(
          tester.getRect(reason).top,
          lessThan(tester.getRect(find.text('의류 종류 선택')).top),
        );

        final icon = find.descendant(
          of: find.byType(BottomSheet),
          matching: find.byIcon(Icons.error_outline),
        );
        expect(icon, findsOneWidget);
        expect(tester.widget<Icon>(icon).color, Colors.redAccent);

        expect(_traversalLabels(tester).first, failureMessage);
        semantics.dispose();
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );

    testWidgets(
      '실패 이유가 없으면(분석 성공·결과 화면의 유형 변경) 이유 줄 없이 제목부터 읽힌다',
      (tester) async {
        final semantics = tester.ensureSemantics();
        _usePhoneView(tester);
        await _openSheet(
          tester,
          discardPrompt: ClothingTypePickerDiscardPrompt.analysisResult,
        );

        expect(
          find.descendant(
            of: find.byType(BottomSheet),
            matching: find.byIcon(Icons.error_outline),
          ),
          findsNothing,
        );
        expect(_traversalLabels(tester).first, '의류 종류 선택');
        semantics.dispose();
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );
  });

  group('결과 화면의 유형 변경(닫기 허용)', () {
    testWidgets("손잡이를 끌어내리면 지금처럼 null로 닫히고 '다시 촬영' 버튼은 없다", (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester);
      expect(find.text('다시 촬영'), findsNothing);

      final rect = _sheetRect(tester);
      await tester.flingFrom(
        Offset(rect.center.dx, rect.top + 24),
        const Offset(0, 300),
        3000,
      );
      await tester.pumpAndSettle();

      expect(_isSheetOpen(), isFalse);
      expect(sheet.completed, isTrue);
      expect(sheet.result, isNull);
    });

    testWidgets('끌어서 닫을 수 있으므로 손잡이를 보여 준다', (tester) async {
      _usePhoneView(tester);
      await _openSheet(tester);

      expect(_dragHandles(), findsOneWidget);
    });

    testWidgets('바깥 탭과 뒤로가기로도 확인 없이 닫힌다', (tester) async {
      _usePhoneView(tester);
      final tappedOutside = await _openSheet(tester);
      await tester.tapAt(const Offset(5, 5));
      await tester.pumpAndSettle();
      expect(tappedOutside.completed, isTrue);
      expect(_isSheetOpen(), isFalse);

      final pressedBack = await _openSheet(tester);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(pressedBack.completed, isTrue);
      expect(_isSheetOpen(), isFalse);
    });
  });
}

class _SheetResult {
  bool completed = false;
  ClothingTypeOption? result;
}

void _usePhoneView(WidgetTester tester, {double bottomInset = 0}) {
  const devicePixelRatio = 2.625;
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = devicePixelRatio;
  tester.view.padding = FakeViewPadding(bottom: bottomInset * devicePixelRatio);
  tester.view.viewPadding = FakeViewPadding(
    bottom: bottomInset * devicePixelRatio,
  );
  addTearDown(tester.view.reset);
}

/// 읽기 프로그램이 오른쪽으로 쓸어 넘기며 읽는 순서대로 이름(없으면 툴팁)을 모은다.
List<String> _traversalLabels(WidgetTester tester) {
  return tester.semantics
      .simulatedAccessibilityTraversal()
      .map((node) => node.label.isEmpty ? node.tooltip : node.label)
      .where((label) => label.isNotEmpty)
      .toList();
}

Future<_SheetResult> _openSheet(
  WidgetTester tester, {
  ClothingTypePickerDiscardPrompt? discardPrompt,
  String? failureMessage,
}) async {
  final sheet = _SheetResult();

  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              onPressed: () {
                showClothingTypePickerSheet(
                  context: context,
                  options: ClothingTypeCatalog.options,
                  initialSelection: ClothingTypeCatalog.defaultOption,
                  discardPrompt: discardPrompt,
                  failureMessage: failureMessage,
                ).then((value) {
                  sheet
                    ..completed = true
                    ..result = value;
                });
              },
              child: const Text('시트 열기'),
            ),
          ),
        ),
      ),
    ),
  );

  await tester.tap(find.text('시트 열기'));
  await tester.pumpAndSettle();
  return sheet;
}

Rect _sheetRect(WidgetTester tester) {
  return tester.getRect(
    find
        .descendant(
          of: find.byType(BottomSheet),
          matching: find.byType(Material),
        )
        .first,
  );
}

bool _isSheetOpen() => find.byType(BottomSheet).evaluate().isNotEmpty;

// Flutter 손잡이(_DragHandle)와 직접 그린 손잡이 모양을 모두 찾는다.
Finder _dragHandles() => find.byWidgetPredicate(
  (widget) => widget.runtimeType.toString().contains('DragHandle'),
);

Finder _dialogButton(String label) {
  return find.descendant(
    of: find.byType(AlertDialog),
    matching: find.text(label),
  );
}

// 막대의 [완료]는 글자로, ∧·∨ 는 아이콘의 낭독 이름으로 찾는다.
Finder _toolbarButton(String label) {
  return find.descendant(
    of: find.byType(NumberKeyboardToolbar),
    matching: label == '완료'
        ? find.text(label)
        : find.byWidgetPredicate(
            (widget) => widget is Icon && widget.semanticLabel == label,
          ),
  );
}

IconButton _toolbarIconButton(String label) => find
    .ancestor(of: _toolbarButton(label), matching: find.byType(IconButton))
    .evaluate()
    .single
    .widget as IconButton;
