import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/closet_screen.dart';
import 'package:k_dpp/main_screen.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/clothes.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:k_dpp/settings_screen.dart';
import 'package:k_dpp/theme/app_theme.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:k_dpp/widgets/app_back_button.dart';
import 'package:k_dpp/widgets/app_glass_button.dart';
import 'package:k_dpp/widgets/frosted_surface.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

// DECISIONS 224·225: 혼자 떠 있는 버튼은 반투명 유리 원(캡슐)이고, 누르면 iOS 는 물방울처럼 부풀며
// 당기면 늘어나고, Android 는 모서리가 줄어 둥근 네모 쪽으로 눌립니다. 계기는 "<" 를 누르면 세로로
// 긴 원이 보이던 것(앱바 칸 44×56 을 버튼이 채움, Material 3 는 splashRadius 를 쓰지 않음)이라,
// 원 크기와 모양부터 지킵니다.
final _iOS = TargetPlatformVariant.only(TargetPlatform.iOS);
final _android = TargetPlatformVariant.only(TargetPlatform.android);
final _both = TargetPlatformVariant({
  TargetPlatform.iOS,
  TargetPlatform.android,
});

bool get _isIOS => defaultTargetPlatform == TargetPlatform.iOS;

void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  group('"<" 유리 원', () {
    for (final (name, theme) in [
      ('라이트', AppTheme.light()),
      ('다크', AppTheme.dark()),
    ]) {
      testWidgets('$name: 앱바 칸 안에서 보이는 원은 44×44 원, 누를 수 있는 곳은 48×48', (
        tester,
      ) async {
        await _pumpBackButton(tester, theme: theme);
        final button = find.byType(AppBackButton);

        expect(tester.getSize(_surfaceOf(button)), const Size.square(44));
        expect(_cornerOf(tester, button), 22, reason: '반지름 = 지름의 절반이라 원');
        expect(
          tester.getSize(
            find.descendant(of: button, matching: find.byType(IconButton)),
          ),
          const Size.square(48),
        );
      });
    }

    testWidgets('iOS: 누르는 동안 물방울처럼 부풀고 바탕이 바뀌며, 떼면 제자리로 돌아온다', (tester) async {
      await _pumpBackButton(tester);
      final button = find.byType(AppBackButton);
      final context = tester.element(button);

      expect(_scaleOf(tester, button), 1);
      expect(_fillOf(tester, button), AppGlassStyle.fill(context));

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      // 원 44 가 약 55 까지 부풉니다. 모서리는 그대로 원입니다.
      expect(_scaleOf(tester, button), closeTo(1.25, 0.02));
      expect(_cornerOf(tester, button), 22);
      expect(_fillOf(tester, button), AppGlassStyle.pressedFill(context));

      await gesture.up();
      await tester.pumpAndSettle();
      expect(_scaleOf(tester, button), closeTo(1, 0.001));
    }, variant: _iOS);

    testWidgets(
      'Android: 크기는 그대로, 누르는 동안 모서리가 22 → 14 로 줄어 둥근 네모 쪽으로 눌린다',
      (tester) async {
        await _pumpBackButton(tester);
        final button = find.byType(AppBackButton);
        final context = tester.element(button);

        final gesture = await tester.startGesture(tester.getCenter(button));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));
        expect(_scaleOf(tester, button), 1);
        expect(_cornerOf(tester, button), closeTo(14, 0.5));
        expect(_fillOf(tester, button), AppGlassStyle.pressedFill(context));

        await gesture.up();
        await tester.pumpAndSettle();
        expect(_cornerOf(tester, button), closeTo(22, 0.01));
        expect(_fillOf(tester, button), AppGlassStyle.fill(context));
      },
      variant: _android,
    );

    testWidgets('물결(Material 잉크)은 그리지 않는다 — 부풂·모양 바뀜과 겹치지 않게', (tester) async {
      await _pumpBackButton(tester);
      final button = find.byType(AppBackButton);

      final inkWell = tester.widget<InkWell>(
        find.descendant(of: button, matching: find.byType(InkWell)),
      );
      expect(inkWell.splashFactory, NoSplash.splashFactory);
      expect(
        inkWell.overlayColor?.resolve({WidgetState.pressed}),
        Colors.transparent,
      );
    }, variant: _both);

    testWidgets('"동작 줄이기"가 켜져 있으면 모양은 그대로이고 바탕색만 바뀐다', (tester) async {
      await _pumpBackButton(tester, disableAnimations: true);
      final button = find.byType(AppBackButton);

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await gesture.moveBy(const Offset(40, 0));
      await tester.pump(const Duration(milliseconds: 300));
      expect(_matrixOf(tester, button), Matrix4.identity());
      expect(_cornerOf(tester, button), 22);
      expect(
        _fillOf(tester, button),
        AppGlassStyle.pressedFill(tester.element(button)),
      );
      await gesture.up();
      await tester.pumpAndSettle();
    }, variant: _iOS);

    testWidgets('Android 도 "동작 줄이기"면 모서리가 그대로이고 바탕색만 바뀐다', (tester) async {
      await _pumpBackButton(tester, disableAnimations: true);
      final button = find.byType(AppBackButton);

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(_cornerOf(tester, button), 22);
      expect(
        _fillOf(tester, button),
        AppGlassStyle.pressedFill(tester.element(button)),
      );
      await gesture.up();
      await tester.pumpAndSettle();
    }, variant: _android);

    testWidgets('누를 수 없는 버튼은 눌러도 반응하지 않는다', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(
            body: AppGlassIconButton(
              onPressed: null,
              tooltip: '설정',
              icon: Icon(Icons.settings_outlined),
            ),
          ),
        ),
      );
      final button = find.byType(AppGlassIconButton);

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(_matrixOf(tester, button), Matrix4.identity());
      expect(_cornerOf(tester, button), 22);
      await gesture.up();
      await tester.pumpAndSettle();
    }, variant: _both);

    testWidgets('누르고 있는 동안 누를 수 없게 바뀌어도 오류 없이 제자리로 돌아온다', (tester) async {
      // 스캔 저장이 시작돼 설정 버튼이 잠기는 순간 손가락이 올라가 있는 경우입니다. 버튼은 그리는
      // 도중에 눌림을 풀어 알리므로, 그때 바로 다시 그리면 Flutter 가 막습니다.
      final enabled = ValueNotifier(true);
      addTearDown(enabled.dispose);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: ValueListenableBuilder<bool>(
              valueListenable: enabled,
              builder: (context, isEnabled, _) => AppGlassIconButton(
                onPressed: isEnabled ? () {} : null,
                tooltip: '설정',
                icon: const Icon(Icons.settings_outlined),
              ),
            ),
          ),
        ),
      );
      final button = find.byType(AppGlassIconButton);

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      if (_isIOS) {
        expect(_scaleOf(tester, button), greaterThan(1.1));
      } else {
        expect(_cornerOf(tester, button), lessThan(16));
      }

      enabled.value = false;
      await tester.pump();
      expect(tester.takeException(), isNull);
      await tester.pumpAndSettle();
      expect(_scaleOf(tester, button), closeTo(1, 0.001));
      expect(_cornerOf(tester, button), closeTo(22, 0.01));

      await gesture.up();
      await tester.pumpAndSettle();
    }, variant: _both);
  });

  group('iOS 누른 채 당기기', () {
    testWidgets('당긴 쪽으로 끌려가며 그 방향으로 길쭉해지고, 밖에서 놓으면 누름 없이 제자리로 돌아온다', (
      tester,
    ) async {
      var taps = 0;
      await _pumpBackButton(tester, onPressed: () => taps++);
      final button = find.byType(AppBackButton);

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await gesture.moveBy(const Offset(12, 0));
      await tester.pump(const Duration(milliseconds: 300));
      final near = _matrixOf(tester, button);

      await gesture.moveBy(const Offset(100, 0));
      await tester.pump(const Duration(milliseconds: 16));
      final far = _matrixOf(tester, button);

      // 오른쪽으로 끌려가되 최대 10 을 넘지 않고, 많이 당길수록 덜 따라갑니다.
      expect(near.getTranslation().x, greaterThan(0));
      expect(far.getTranslation().x, greaterThan(near.getTranslation().x));
      expect(far.getTranslation().x, lessThanOrEqualTo(10));
      expect(far.getTranslation().y, closeTo(0, 0.001));
      // 가로로 늘고 세로로 줄어듭니다(부풂 1.25 위에, 늘어남은 최대 15%).
      expect(far.entry(0, 0), greaterThan(far.entry(1, 1)));
      expect(far.entry(0, 0), lessThanOrEqualTo(1.25 * 1.15 + 0.01));

      // 버튼 밖으로 끌고 나가도 놓을 때까지 눌린 색이 남습니다.
      expect(
        _fillOf(tester, button),
        AppGlassStyle.pressedFill(tester.element(button)),
      );

      // 밖에서 놓으면 누름은 취소되고, 모양은 제자리로 돌아옵니다.
      await gesture.up();
      await tester.pumpAndSettle();
      expect(taps, 0);
      expect(_matrixOf(tester, button).getTranslation().x, closeTo(0, 0.01));
      expect(_scaleOf(tester, button), closeTo(1, 0.001));
    }, variant: _iOS);

    testWidgets('조금 당겼다 버튼 안에서 놓으면 눌린 것으로 친다', (tester) async {
      var taps = 0;
      await _pumpBackButton(tester, onPressed: () => taps++);
      final button = find.byType(AppBackButton);

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await gesture.moveBy(const Offset(4, 0));
      await tester.pump(const Duration(milliseconds: 100));
      await gesture.up();
      await tester.pumpAndSettle();
      expect(taps, 1);
    }, variant: _iOS);

    testWidgets('스크롤 안의 버튼은 스크롤이 시작되면 손가락을 떼지 않아도 늘어남을 멈추고 돌아온다', (
      tester,
    ) async {
      final controller = ScrollController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: ListView(
              controller: controller,
              children: [
                const SizedBox(height: 100),
                AppGlassIconButton(
                  onPressed: () {},
                  tooltip: '의류 정보 수정',
                  icon: const Icon(Icons.edit_outlined),
                ),
                const SizedBox(height: 2000),
              ],
            ),
          ),
        ),
      );
      final button = find.byType(AppGlassIconButton);

      final gesture = await tester.startGesture(tester.getCenter(button));
      await tester.pump();
      await gesture.moveBy(const Offset(0, -30));
      await gesture.moveBy(const Offset(0, -60));
      await tester.pump();
      expect(controller.offset, greaterThan(0), reason: '스크롤이 시작됐어야 함');

      await tester.pumpAndSettle();
      expect(_matrixOf(tester, button).getTranslation().y, closeTo(0, 0.01));
      expect(_scaleOf(tester, button), closeTo(1, 0.001));

      await gesture.up();
      await tester.pumpAndSettle();
    }, variant: _iOS);
  });

  // 2026-10-14 폰 확인: 앱바(AppBar)는 기본으로 자기 높이 밖을 잘라 내서, 부풀거나 아래로 당긴
  // "<"·설정 원의 아랫부분이 평평하게 잘렸다. 버튼 위쪽 어디에도 잘라 내는 층이 없어야 합니다.
  group('부푼 원이 잘리지 않는다', () {
    testWidgets('설정 화면 "<"', (tester) async {
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider(
              create: (_) => ClosetProvider(
                storage: FakeClosetStorage(),
                authSessionStorage: FakeAuthSessionStorage(),
              ),
            ),
            ChangeNotifierProvider(create: (_) => ThemeProvider()),
            ChangeNotifierProvider(
              create: (_) => MaterialNameDisplayProvider(),
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.light(),
            home: const SettingsScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(_clipsAbove(tester, find.byType(AppBackButton)), isEmpty);
    });

    testWidgets('메인 화면 설정 톱니, 옷장 "선택"·정렬', (tester) async {
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider(
              create: (_) => ClosetProvider(storage: FakeClosetStorage()),
            ),
            ChangeNotifierProvider(
              create: (_) => MaterialNameDisplayProvider(),
            ),
            ChangeNotifierProvider(
              create: (_) => NavigationBarOpacityProvider(),
            ),
          ],
          child: MaterialApp(theme: AppTheme.light(), home: const MainScreen()),
        ),
      );
      await tester.pumpAndSettle();

      final gear = find.ancestor(
        of: find.byIcon(Icons.settings_outlined),
        matching: find.byType(AppGlassIconButton),
      );
      expect(_clipsAbove(tester, gear), isEmpty);

      await tester.tap(find.text('옷장'));
      await tester.pumpAndSettle();
      for (final button in [
        find.byType(AppGlassTextButton),
        find.ancestor(
          of: find.byIcon(Icons.sort),
          matching: find.byType(AppGlassIconButton),
        ),
      ]) {
        expect(_clipsAbove(tester, button), isEmpty);
      }
    });
  });

  group('옷장', () {
    testWidgets('"선택" 은 같은 재질의 캡슐, 정렬은 유리 원이다', (tester) async {
      await _pumpCloset(tester);

      final select = find.ancestor(
        of: find.text('선택'),
        matching: find.byType(AppGlassTextButton),
      );
      expect(tester.getSize(_surfaceOf(select)).height, 36);
      expect(_cornerOf(tester, select), 18, reason: '반지름 = 높이의 절반이라 캡슐');

      final sort = find.ancestor(
        of: find.byIcon(Icons.sort),
        matching: find.byType(AppGlassIconButton),
      );
      expect(tester.getSize(_surfaceOf(sort)), const Size.square(44));
    });

    testWidgets('휴지통은 고른 옷이 있을 때만 반응하고, 떼면 확인창이 뜬다', (tester) async {
      await _pumpCloset(tester);
      await tester.tap(find.text('선택'));
      await tester.pumpAndSettle();

      final trash = find.ancestor(
        of: find.byIcon(Icons.delete_outline),
        matching: find.byType(GlassPressBuilder),
      );
      double trashCorner() => tester
          .widget<FrostedSurface>(
            find.descendant(of: trash, matching: find.byType(FrostedSurface)),
          )
          .borderRadius
          .topLeft
          .x;

      // 아무것도 고르지 않음: 누를 수 없어 반응하지 않습니다.
      var gesture = await tester.startGesture(tester.getCenter(trash));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(_matrixOf(tester, trash), Matrix4.identity());
      expect(trashCorner(), 28);
      await gesture.up();
      await tester.pumpAndSettle();

      await tester.tap(find.text('반팔 티셔츠'));
      await tester.pumpAndSettle();

      gesture = await tester.startGesture(tester.getCenter(trash));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      if (_isIOS) {
        // 큰 원이라 위쪽 원(1.25)보다 덜 부풉니다(56 → 약 64).
        expect(_scaleOf(tester, trash), closeTo(1.14, 0.02));
        expect(trashCorner(), 28);
      } else {
        expect(_scaleOf(tester, trash), 1);
        expect(trashCorner(), closeTo(28 * 0.64, 0.5));
      }

      // 떼면 확인창이 뜨고, 바로 지워지지 않습니다.
      await gesture.up();
      await tester.pumpAndSettle();
      expect(find.text('선택한 의류 삭제'), findsOneWidget);
      expect(_scaleOf(tester, trash), closeTo(1, 0.001));
      expect(trashCorner(), closeTo(28, 0.01));
    }, variant: _both);
  });
}

Future<void> _pumpBackButton(
  WidgetTester tester, {
  ThemeData? theme,
  bool disableAnimations = false,
  VoidCallback? onPressed,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: theme ?? AppTheme.light(),
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(disableAnimations: disableAnimations),
        child: child!,
      ),
      home: Scaffold(
        appBar: AppBar(
          leadingWidth: AppGlassStyle.leadingWidth,
          leading: Padding(
            padding: const EdgeInsets.only(left: AppGlassStyle.leadingInset),
            child: AppBackButton(onPressed: onPressed ?? () {}),
          ),
        ),
      ),
    ),
  );
}

Future<void> _pumpCloset(WidgetTester tester) async {
  final provider = ClosetProvider(
    storage: FakeClosetStorage(),
    authSessionStorage: FakeAuthSessionStorage(),
  );
  await provider.addClothes(
    Clothes(
      title: '반팔 티셔츠',
      category: '상의',
      health: 88,
      materials: const {'cotton': 100},
      careInstruction: '찬물 세탁',
      carbonFootprint: 2.1,
    ),
  );

  await tester.pumpWidget(
    ChangeNotifierProvider.value(
      value: provider,
      child: MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(body: ClosetScreen(onOpenReport: (_) {})),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// 버튼이 칠하는 바탕(색·모양을 가진 Material)입니다. 가장 안쪽 것을 고릅니다.
Finder _surfaceOf(Finder button) =>
    find.descendant(of: button, matching: find.byType(Material)).last;

Color? _fillOf(WidgetTester tester, Finder button) =>
    tester.widget<Material>(_surfaceOf(button)).color;

/// 바탕 모서리 반지름입니다. 원 44 는 22, 캡슐 36 은 18 이 평소 값입니다.
double _cornerOf(WidgetTester tester, Finder button) {
  final shape = tester.widget<Material>(_surfaceOf(button)).shape;
  return ((shape as RoundedRectangleBorder).borderRadius as BorderRadius)
      .topLeft
      .x;
}

/// 누름 반응이 그리는 변환입니다.
Matrix4 _matrixOf(WidgetTester tester, Finder button) => tester
    .widget<Transform>(
      find.descendant(
        of: button,
        matching: find.byKey(GlassPressBuilder.transformKey),
      ),
    )
    .transform;

/// 당기지 않았을 때 부푼 배율입니다.
double _scaleOf(WidgetTester tester, Finder button) =>
    _matrixOf(tester, button).entry(0, 0);

/// [button] 에서 화면(Scaffold)까지 올라가며 그림을 잘라 내는 층을 모읍니다. 비어 있으면 통과입니다.
List<String> _clipsAbove(WidgetTester tester, Finder button) {
  final clips = <String>[];
  tester.element(button).visitAncestorElements((ancestor) {
    final widget = ancestor.widget;
    if (widget is Scaffold) return false;
    final clip = switch (widget) {
      ClipRect(:final clipBehavior) => clipBehavior,
      ClipRRect(:final clipBehavior) => clipBehavior,
      ClipPath(:final clipBehavior) => clipBehavior,
      _ => Clip.none,
    };
    if (clip != Clip.none) {
      clips.add(
        '${widget.runtimeType}($clip) ← ${ancestor.findAncestorWidgetOfExactType<AppBar>() == null ? '' : 'AppBar 안'}',
      );
    }
    return true;
  });
  return clips;
}
