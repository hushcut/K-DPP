import 'dart:ui' show SemanticsFlag;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/models/clothing_type_option.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/app_back_button.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';
import 'package:k_dpp/widgets/number_keyboard_toolbar.dart';

// 스캔 직후 반드시 고르는 종류 선택 화면(DECISIONS 226)과 결과 입력 중 종류를 바꾸는 시트를
// 나가는 길마다 확인한다.
// - 화면은 앱바 "<"·시스템 뒤로가기(maybePop)·iOS 왼쪽 끝 밀기가 저마다 PopScope 를 거치므로
//   길마다 따로 시험한다. 밀기는 PopScope 가 막으면 아예 꺼진다.
// - 시트는 PopScope 를 거치지 않는 드래그·손잡이로도 닫힌다. 느린 드래그는 시트 높이의 절반을
//   넘기지 않으면 닫지 않아 가짜로 통과하므로 fling(700px/s 초과)으로 시험한다.
// - 화면을 폰 크기로 고정한다.
void main() {
  group('종류 선택 화면 — 분석 성공 뒤(다시 촬영 전에 확인)', () {
    testWidgets('"<" 는 다시 촬영 확인을 거쳐, 계속하면 화면을 유지하고 다시 촬영하면 null 로 닫힌다', (
      tester,
    ) async {
      _usePhoneView(tester);
      final picker = await _openScreen(tester, confirmRetake: true);

      await tester.tap(find.byTooltip('다시 촬영'));
      await tester.pumpAndSettle();
      expect(find.text('다시 촬영할까요?'), findsOneWidget);
      expect(find.text('다시 촬영하면 현재 분석 결과가 사라져요.'), findsOneWidget);

      await tester.tap(_dialogButton('선택 계속하기'));
      await tester.pumpAndSettle();
      expect(find.byType(AlertDialog), findsNothing);
      expect(_isScreenOpen(), isTrue);
      expect(picker.completed, isFalse);

      await tester.tap(find.byTooltip('다시 촬영'));
      await tester.pumpAndSettle();
      await tester.tap(_dialogButton('다시 촬영'));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(_isScreenOpen(), isFalse);
      expect(picker.completed, isTrue);
      expect(picker.result, isNull);
    });

    testWidgets('시스템 뒤로가기도 같은 확인을 거친다', (tester) async {
      _usePhoneView(tester);
      final picker = await _openScreen(tester, confirmRetake: true);

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text('다시 촬영할까요?'), findsOneWidget);

      await tester.tap(_dialogButton('다시 촬영'));
      await tester.pumpAndSettle();

      expect(_isScreenOpen(), isFalse);
      expect(picker.completed, isTrue);
      expect(picker.result, isNull);
    });

    testWidgets(
      'iOS 왼쪽 끝을 밀어도 닫히지 않는다 — 밀기에는 확인창을 끼울 수 없다',
      (tester) async {
        _usePhoneView(tester);
        final picker = await _openScreen(tester, confirmRetake: true);

        await tester.dragFrom(const Offset(5, 300), const Offset(600, 0));
        await tester.pumpAndSettle();

        expect(find.byType(AlertDialog), findsNothing);
        expect(_isScreenOpen(), isTrue);
        expect(picker.completed, isFalse);
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );

    testWidgets('종류를 고르면 확인 없이 그 종류로 닫힌다', (tester) async {
      _usePhoneView(tester);
      final picker = await _openScreen(tester, confirmRetake: true);

      await tester.tap(find.text('니트'));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(_isScreenOpen(), isFalse);
      expect(picker.completed, isTrue);
      expect(picker.result?.label, '니트');
    });

    testWidgets('시트가 아닌 화면이고, 다시 촬영은 앱바의 유리 "<" 하나뿐이며 몸통에 글자 버튼이 없다', (
      tester,
    ) async {
      _usePhoneView(tester);
      await _openScreen(tester, confirmRetake: true);

      expect(find.byType(BottomSheet), findsNothing);
      expect(_dragHandles(), findsNothing);
      expect(find.byType(AppBackButton), findsOneWidget);
      expect(
        find.descendant(
          of: find.byType(AppBar),
          matching: find.byTooltip('다시 촬영'),
        ),
        findsOneWidget,
      );
      expect(find.text('다시 촬영'), findsNothing);
      expect(find.byType(TextButton), findsNothing);
    });
  });

  group('종류 선택 화면 — 분석 실패 뒤(확인 없이 다시 촬영)', () {
    const failureMessage = '라벨을 읽지 못했어요. 직접 입력해 주세요.';

    testWidgets('"<" 를 누르면 묻지 않고 바로 null 로 닫힌다', (tester) async {
      _usePhoneView(tester);
      final picker = await _openScreen(
        tester,
        confirmRetake: false,
        failureMessage: failureMessage,
      );

      await tester.tap(find.byTooltip('다시 촬영'));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(_isScreenOpen(), isFalse);
      expect(picker.completed, isTrue);
      expect(picker.result, isNull);
    });

    testWidgets('시스템 뒤로가기도 묻지 않고 닫힌다', (tester) async {
      _usePhoneView(tester);
      final picker = await _openScreen(
        tester,
        confirmRetake: false,
        failureMessage: failureMessage,
      );

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing);
      expect(picker.completed, isTrue);
      expect(picker.result, isNull);
    });

    testWidgets(
      'iOS 왼쪽 끝을 밀면 묻지 않고 null 로 닫힌다',
      (tester) async {
        _usePhoneView(tester);
        final picker = await _openScreen(
          tester,
          confirmRetake: false,
          failureMessage: failureMessage,
        );

        await tester.dragFrom(const Offset(5, 300), const Offset(600, 0));
        await tester.pumpAndSettle();

        expect(find.byType(AlertDialog), findsNothing);
        expect(_isScreenOpen(), isFalse);
        expect(picker.completed, isTrue);
        expect(picker.result, isNull);
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );

    // DECISIONS 96: 분석이 실패하면 고른 뒤 띄우던 배너 대신 이 화면 맨 위에서 이유를 알린다.
    // 화면이 열릴 때 읽기 프로그램은 화면 이름(namesRoute)을 먼저 말하고 첫 칸으로 가므로, 이유 줄을
    // 화면 이름으로 삼는다. 쓸어 넘기는 순서는 보이는 순서("<" → 이유 → 제목) 그대로다(DECISIONS 103).
    testWidgets(
      '실패 이유는 제목 위에 빨간 느낌표와 함께 보이고, 화면 이름이 되어 화면이 열릴 때 먼저 읽힌다',
      (tester) async {
        final semantics = tester.ensureSemantics();
        _usePhoneView(tester);
        await _openScreen(
          tester,
          confirmRetake: false,
          failureMessage: failureMessage,
        );

        final reason = find.text(failureMessage);
        expect(reason, findsOneWidget);
        expect(
          tester.getRect(reason).top,
          lessThan(tester.getRect(find.text('의류 종류 선택')).top),
        );

        final icon = find.byIcon(Icons.error_outline);
        expect(icon, findsOneWidget);
        expect(tester.widget<Icon>(icon).color, Colors.redAccent);

        expect(_routeNames(), [failureMessage]);
        expect(_traversalLabels(tester).take(3), [
          '다시 촬영',
          failureMessage,
          '의류 종류 선택',
        ]);
        semantics.dispose();
      },
      variant: const TargetPlatformVariant({
        TargetPlatform.iOS,
        TargetPlatform.android,
      }),
    );

    testWidgets(
      '실패 이유가 없으면(분석 성공) 이유 줄도 화면 이름도 없이 "<" 다음 제목부터 읽힌다',
      (tester) async {
        final semantics = tester.ensureSemantics();
        _usePhoneView(tester);
        await _openScreen(tester, confirmRetake: true);

        expect(find.byIcon(Icons.error_outline), findsNothing);
        expect(_routeNames(), isEmpty);
        expect(_traversalLabels(tester).take(2), ['다시 촬영', '의류 종류 선택']);
        semantics.dispose();
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );
  });

  group('종류 선택 화면 — 직접 무게 입력', () {
    for (final confirmRetake in [true, false]) {
      final label = confirmRetake ? '분석 성공 뒤' : '분석 실패 뒤';

      testWidgets('$label "<" 는 묻지 않고 목록으로 돌아가고, 그동안 "<" 의 이름도 목록으로 돌아가기다', (
        tester,
      ) async {
        _usePhoneView(tester);
        final picker = await _openScreen(tester, confirmRetake: confirmRetake);
        await _enterDirectInput(tester);

        expect(find.text('직접 무게 입력'), findsWidgets);
        expect(find.byTooltip('다시 촬영'), findsNothing);
        // 몸통 안에 뒤로 버튼을 또 두지 않는다 — 앱바 "<" 하나뿐이다.
        expect(find.byType(AppBackButton), findsOneWidget);
        expect(find.byIcon(Icons.arrow_back_ios_new_rounded), findsNothing);

        await tester.tap(find.byTooltip('의류 종류 목록으로 돌아가기'));
        await tester.pumpAndSettle();

        expect(find.byType(AlertDialog), findsNothing);
        expect(find.text('의류 종류 선택'), findsOneWidget);
        expect(find.byTooltip('다시 촬영'), findsOneWidget);
        expect(_isScreenOpen(), isTrue);
        expect(picker.completed, isFalse);
      });
    }

    testWidgets('분석 실패 뒤라도 시스템 뒤로가기는 목록으로 돌아간다', (tester) async {
      _usePhoneView(tester);
      final picker = await _openScreen(tester, confirmRetake: false);
      await _enterDirectInput(tester);

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();

      expect(find.text('의류 종류 선택'), findsOneWidget);
      expect(_isScreenOpen(), isTrue);
      expect(picker.completed, isFalse);
    });

    testWidgets(
      '분석 실패 뒤라도 직접 입력 중에는 iOS 왼쪽 끝 밀기로 닫히지 않는다',
      (tester) async {
        _usePhoneView(tester);
        final picker = await _openScreen(tester, confirmRetake: false);
        await _enterDirectInput(tester);

        await tester.dragFrom(const Offset(5, 300), const Offset(600, 0));
        await tester.pumpAndSettle();

        expect(_isScreenOpen(), isTrue);
        expect(picker.completed, isFalse);
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );

    testWidgets(
      '키보드가 올라와도 넘치지 않고, iOS 무게 칸 막대는 키보드 바로 위에 붙는다',
      (tester) async {
        // 화면은 Scaffold 가 본문을 키보드 위로 줄인다. 시트처럼 키보드 여백을 또 두면 막대가 떠 버린다.
        _usePhoneView(tester);
        EditableText.debugDeterministicCursor = true;
        addTearDown(() => EditableText.debugDeterministicCursor = false);
        await _openScreen(tester, confirmRetake: true);
        await _enterDirectInput(tester);

        await tester.tap(find.widgetWithText(TextField, '실제 무게'));
        tester.view.viewInsets = const FakeViewPadding(bottom: _keyboardHeight);
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);
        expect(_toolbarButton('완료'), findsOneWidget);
        final viewHeight =
            tester.view.physicalSize.height / tester.view.devicePixelRatio;
        final keyboardTop =
            viewHeight - _keyboardHeight / tester.view.devicePixelRatio;
        expect(
          tester.getRect(find.byType(NumberKeyboardToolbar)).bottom,
          moreOrLessEquals(keyboardTop),
        );
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );

    testWidgets('입력한 이름·무게와 세그먼트로 고른 분류로 닫힌다(결정 134)', (tester) async {
      _usePhoneView(tester);
      final picker = await _openScreen(tester, confirmRetake: true);
      await _enterDirectInput(tester);

      await tester.enterText(find.byType(TextField).at(0), '조끼');
      await tester.enterText(find.byType(TextField).at(1), '300');
      await tester.tap(
        find.descendant(
          of: find.byType(SegmentedButton<String>),
          matching: find.text('하의'),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('적용하기'));
      await tester.pumpAndSettle();

      expect(_isScreenOpen(), isFalse);
      expect(picker.result?.label, '조끼');
      expect(picker.result?.category, '하의');
      expect(picker.result?.estimatedWeightGram, 300);
    });
  });

  group('결과 화면의 유형 변경 시트(닫기 허용)', () {
    testWidgets("손잡이를 끌어내리면 null로 닫히고 '다시 촬영' 버튼은 없다", (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester);
      expect(find.text('다시 촬영'), findsNothing);
      expect(find.byTooltip('다시 촬영'), findsNothing);

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

    testWidgets('직접 무게 입력에서 키보드가 올라와도 시트가 넘치지 않는다', (tester) async {
      // 2026-09-18 폰 확인(SM-N986N): 'BOTTOM OVERFLOWED BY 122 PIXELS'.
      // 키보드 높이는 그 폰 스크린샷에서 잰 삼성 키보드(숫자 줄·추천 줄 포함) 1098 물리 픽셀.
      // (정정 2026-09-19: 처음엔 '실측 418'이라 적었는데, 418은 이 테스트 배율 2.625로 나눈 값이다.
      // 그 폰의 실제 배율은 2.8125라 약 390dp — 물리 픽셀로 적어 배율과 무관하게 했다)
      _usePhoneView(tester);
      await _openSheet(tester);
      await _enterDirectInput(tester);

      tester.view.viewInsets = const FakeViewPadding(bottom: _keyboardHeight);
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'iOS 무게 칸에는 키보드 위에 막대가 뜨고(∧ 는 의류 종류로, ∨ 는 흐림), 키보드가 올라와도 시트가 넘치지 않는다',
      (tester) async {
        // iOS 숫자 키패드에는 확인 키가 없다. 무게 뒤로 이어지는 입력란이 없어 ∨ 는 흐리다(DECISIONS 177).
        _usePhoneView(tester);
        EditableText.debugDeterministicCursor = true;
        addTearDown(() => EditableText.debugDeterministicCursor = false);
        await _openSheet(tester);
        await _enterDirectInput(tester);
        expect(find.text('직접 무게 입력'), findsOneWidget);
        // 의류 종류 칸이 먼저 포커스를 받으므로 아직 막대가 없다.
        expect(find.byType(NumberKeyboardToolbar), findsNothing);

        await tester.tap(find.widgetWithText(TextField, '실제 무게'));
        tester.view.viewInsets = const FakeViewPadding(bottom: _keyboardHeight);
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
      },
      variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    );

    testWidgets(
      'Android 무게 칸에는 키보드 위 막대를 그리지 않는다',
      (tester) async {
        // Android 숫자 키보드의 동작 키가 막대와 하는 일이 겹친다(DECISIONS 185).
        _usePhoneView(tester);
        await _openSheet(tester);
        await _enterDirectInput(tester);

        await tester.tap(find.widgetWithText(TextField, '실제 무게'));
        await tester.pumpAndSettle();
        expect(
          tester
              .widget<EditableText>(
                find.descendant(
                  of: find.widgetWithText(TextField, '실제 무게'),
                  matching: find.byType(EditableText),
                ),
              )
              .focusNode
              .hasFocus,
          isTrue,
        );
        expect(find.byType(NumberKeyboardToolbar), findsNothing);
      },
      variant: TargetPlatformVariant.only(TargetPlatform.android),
    );

    testWidgets('직접 입력의 분류는 세그먼트로 고르고, 고른 분류로 닫힌다(결정 134)', (tester) async {
      _usePhoneView(tester);
      final sheet = await _openSheet(tester);
      await _enterDirectInput(tester);

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
}

// 2026-09-18 폰(SM-N986N)에서 잰 삼성 키보드 높이(물리 픽셀). 위 시트 키보드 테스트 주석 참고.
const double _keyboardHeight = 1098;

class _PickerResult {
  bool completed = false;
  ClothingTypeOption? result;
}

void _usePhoneView(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.625;
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

/// 화면 이름(namesRoute) 칸의 이름들이다. 화면이 바뀌면 iOS 엔진은 새 화면에서 처음 찾은 이 칸의
/// 이름을 화면 전환 알림에 실어 VoiceOver 가 먼저 말하게 하고, Android 는 창 제목으로 알린다.
List<String> _routeNames() {
  return find.semantics
      .byFlag(SemanticsFlag.namesRoute)
      .evaluate()
      .map((node) => node.label)
      .toList();
}

Future<_PickerResult> _openScreen(
  WidgetTester tester, {
  required bool confirmRetake,
  String? failureMessage,
}) {
  return _open(
    tester,
    (context) => showClothingTypePickerScreen(
      context: context,
      options: ClothingTypeCatalog.options,
      initialSelection: ClothingTypeCatalog.defaultOption,
      confirmRetake: confirmRetake,
      failureMessage: failureMessage,
    ),
  );
}

Future<_PickerResult> _openSheet(WidgetTester tester) {
  return _open(
    tester,
    (context) => showClothingTypePickerSheet(
      context: context,
      options: ClothingTypeCatalog.options,
      initialSelection: ClothingTypeCatalog.defaultOption,
    ),
  );
}

Future<_PickerResult> _open(
  WidgetTester tester,
  Future<ClothingTypeOption?> Function(BuildContext context) open,
) async {
  final picker = _PickerResult();

  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              onPressed: () {
                open(context).then((value) {
                  picker
                    ..completed = true
                    ..result = value;
                });
              },
              child: const Text('종류 선택 열기'),
            ),
          ),
        ),
      ),
    ),
  );

  await tester.tap(find.text('종류 선택 열기'));
  await tester.pumpAndSettle();
  return picker;
}

// 목록 끝의 '직접 입력' 칸을 눌러 직접 무게 입력으로 들어간다.
Future<void> _enterDirectInput(WidgetTester tester) async {
  await tester.scrollUntilVisible(find.text('직접 입력'), 100);
  // iOS 스크롤은 멈춘 뒤에도 항목 중심이 화면 밖에 걸칠 수 있어 끝까지 끌어온다.
  await tester.ensureVisible(find.text('직접 입력'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('직접 입력'));
  await tester.pumpAndSettle();
}

bool _isScreenOpen() =>
    find.byType(ClothingTypePickerSheet).evaluate().isNotEmpty;

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

IconButton _toolbarIconButton(String label) =>
    find
            .ancestor(
              of: _toolbarButton(label),
              matching: find.byType(IconButton),
            )
            .evaluate()
            .single
            .widget
        as IconButton;
